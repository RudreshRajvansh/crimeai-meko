"""Swarm simulation of a linked pattern's next move."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import func

from app.models.crime import Crime
from app.models.entity import Entity, EntityMention
from app.services.entity_graph import _keyed


async def _network(db, *, kind: str, crime_type: str) -> Crime:
    now = datetime.now(UTC)
    crimes = []
    for i in range(5):
        lat, lng = 28.60 + i * 0.004, 77.05 + i * 0.003
        crimes.append(Crime(
            crime_type=crime_type, severity=3, city="Delhi", district=("Dwarka", "Janakpuri")[i % 2],
            latitude=lat, longitude=lng, geom=func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326),
            occurred_at=now - timedelta(days=20 - 4 * i, hours=i), case_number=f"DL-SW-{i}", description="linked",
        ))
    key = "DL8CAF2210" if kind == "vehicle" else _keyed("mule@okaxis")
    entity = Entity(kind=kind, key=key, label="DL8CAF2210" if kind == "vehicle" else "mu••••le@okaxis", case_count=5)
    db.add_all([*crimes, entity])
    await db.flush()
    db.add_all([EntityMention(entity_id=entity.id, crime_id=c.id) for c in crimes])
    await db.commit()
    return crimes[-1]


async def test_street_pattern_simulates_with_and_without_patrols(client, db_session, auth_headers_analyst):
    seed = await _network(db_session, kind="vehicle", crime_type="burglary")
    resp = await client.post(f"/api/v1/intel/swarm/{seed.id}", headers=auth_headers_analyst,
                             json={"days": 14, "runs": 200, "patrols": 6, "freeze": False})
    assert resp.status_code == 200
    r = resp.json()
    assert r["basis"] == "linked" and len(r["cases"]) == 5
    assert r["agents"][0]["label"] == "DL8CAF2210" and len(r["agents"][0]["case_ids"]) == 5
    assert r["params"]["street_pattern"] and r["patrol_posts"]
    o = r["outlook"]
    # Same random stream with and without action: the intervention can only remove hits.
    assert o["expected_hits_intervention"] <= o["expected_hits_baseline"]
    assert all(a <= b for a, b in zip(r["curve"]["intervention"], r["curve"]["baseline"], strict=True))
    assert r["curve"]["baseline"] == sorted(r["curve"]["baseline"])
    assert abs(sum(r["hours"]) - 1) < 0.01


async def test_freezing_the_money_trail_prevents_hits_and_patrols_do_not(client, db_session, auth_headers_analyst):
    seed = await _network(db_session, kind="upi", crime_type="fraud")
    resp = await client.post(f"/api/v1/intel/swarm/{seed.id}", headers=auth_headers_analyst,
                             json={"days": 30, "runs": 200, "patrols": 6, "freeze": True})
    r = resp.json()
    assert not r["params"]["street_pattern"] and r["patrol_posts"] == []
    assert r["agents"][0]["frozen"]
    assert r["outlook"]["prevented_pct"] > 50 and set(r["outlook"]["prevented_by"]) == {"freeze"}


async def test_swarm_needs_analyst_and_a_real_case(client, db_session, auth_headers_readonly, auth_headers_analyst):
    seed = await _network(db_session, kind="vehicle", crime_type="burglary")
    assert (await client.post(f"/api/v1/intel/swarm/{seed.id}", headers=auth_headers_readonly, json={})).status_code == 403
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/intel/swarm/{missing}", headers=auth_headers_analyst, json={})).status_code == 404
    seeds = (await client.get("/api/v1/intel/swarm/seeds", headers=auth_headers_analyst)).json()
    assert seeds and seeds[0]["cases"] == 5
