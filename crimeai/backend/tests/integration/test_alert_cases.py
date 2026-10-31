"""Alerts carry the cases behind them, so an analyst can open each one directly."""
from datetime import UTC, datetime, timedelta

from app.models.alert import Alert
from app.models.crime import Crime
from app.models.entity import Entity, EntityMention


async def _linked_cases(db, n: int) -> tuple[Entity, list[Crime]]:
    now = datetime.now(UTC)
    crimes = [
        Crime(crime_type="fraud", severity=3, city="Delhi", district=f"District {i % 2}", latitude=28.6, longitude=77.2,
              occurred_at=now - timedelta(days=i), case_number=f"DL-TEST-{i}")
        for i in range(n)
    ]
    entity = Entity(kind="phone", key="hmac-test", label="98••••••10", case_count=n)
    db.add_all([*crimes, entity])
    await db.flush()
    db.add_all([EntityMention(entity_id=entity.id, crime_id=c.id) for c in crimes])
    db.add(Alert(title=f"Phone number links {n} cases", message="Shared phone across cases.", alert_type="pattern",
                 severity="high", target_role="analyst", dedupe_key=f"link:{entity.id}"))
    await db.commit()
    return entity, crimes


async def test_link_alert_lists_its_cases_newest_first(client, db_session, auth_headers_analyst):
    entity, crimes = await _linked_cases(db_session, 4)

    body = (await client.get("/api/v1/alerts/", headers=auth_headers_analyst)).json()

    alert = body["items"][0]
    assert alert["graph_node"] == f"entity:{entity.id}"
    assert alert["entity_kind"] == "phone"
    assert [c["case_number"] for c in alert["cases"]] == [c.case_number for c in crimes]
    assert {"id", "crime_type", "district", "occurred_at"} <= set(alert["cases"][0])


async def test_case_details_withheld_below_analyst(client, db_session, auth_headers_readonly):
    entity, _ = await _linked_cases(db_session, 2)
    alert = (await db_session.execute(Alert.__table__.select())).first()
    await db_session.execute(Alert.__table__.update().where(Alert.id == alert.id).values(target_role=None))
    await db_session.commit()

    item = (await client.get("/api/v1/alerts/", headers=auth_headers_readonly)).json()["items"][0]

    assert item["cases"] == [] and item["graph_node"] is None
