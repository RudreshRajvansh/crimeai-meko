"""Authentication, session lifecycle and authorisation, end to end."""
import pytest
from httpx import AsyncClient

from app.core.config import settings

pytestmark = pytest.mark.asyncio

COOKIE = settings.REFRESH_COOKIE_NAME


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_login_sets_httponly_refresh_cookie_and_no_refresh_in_body(client, police_user):
    resp = await _login(client, police_user.email, "PolicePass12")
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body and "refresh_token" not in body
    set_cookie = resp.headers["set-cookie"].lower()
    assert COOKIE in set_cookie and "httponly" in set_cookie


async def test_login_requires_client_header(client, police_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": police_user.email, "password": "PolicePass12"},
        headers={"X-CrimeAI-Client": ""},
    )
    assert resp.status_code == 400


async def test_wrong_password_and_unknown_email_look_identical(client, police_user):
    wrong = await _login(client, police_user.email, "WrongPass123")
    unknown = await _login(client, "nobody@crimeai.example", "WrongPass123")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["message"] == unknown.json()["message"]


async def test_self_registration_disabled_by_default(client, monkeypatch):
    assert type(settings).model_fields["ALLOW_SELF_REGISTRATION"].default is False
    monkeypatch.setattr(settings, "ALLOW_SELF_REGISTRATION", False)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "x@test.com", "password": "SecurePass12", "full_name": "Xavier"},
    )
    assert resp.status_code == 403


async def test_register_cannot_choose_role(client, monkeypatch):
    """Regression: the original endpoint let anyone self-register as admin."""
    monkeypatch.setattr(settings, "ALLOW_SELF_REGISTRATION", True)
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "attacker@test.com", "password": "SecurePass12", "full_name": "Attacker", "role": "admin"},
    )
    assert resp.status_code == 202
    login = await _login(client, "attacker@test.com", "SecurePass12")
    assert login.status_code == 403  # created inactive, pending approval


async def test_refresh_rotates_and_detects_reuse(client, police_user):
    await _login(client, police_user.email, "PolicePass12")
    first_cookie = client.cookies.get(COOKIE)

    rotated = await client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    assert client.cookies.get(COOKIE) != first_cookie

    # Replaying the old token is treated as theft: every session for the user is revoked.
    client.cookies.set(COOKIE, first_cookie, path="/api/v1/auth")
    replay = await client.post("/api/v1/auth/refresh")
    assert replay.status_code == 401
    me = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"})
    assert me.status_code == 401


async def test_deactivation_revokes_access_immediately(client, admin_user, police_user, auth_headers_admin):
    login = await _login(client, police_user.email, "PolicePass12")
    officer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get("/api/v1/users/me", headers=officer_headers)).status_code == 200

    assert (await client.delete(f"/api/v1/users/{police_user.id}", headers=auth_headers_admin)).status_code == 204
    assert (await client.get("/api/v1/users/me", headers=officer_headers)).status_code == 401


async def test_role_change_takes_effect_without_new_login(client, admin_user, police_user, auth_headers_admin):
    login = await _login(client, police_user.email, "PolicePass12")
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await client.patch(f"/api/v1/users/{police_user.id}", json={"role": "readonly"}, headers=auth_headers_admin)
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token(client, police_user):
    await _login(client, police_user.email, "PolicePass12")
    resp = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {client.cookies.get(COOKIE)}"})
    assert resp.status_code == 401


async def test_ws_ticket_is_single_use(client, police_user, auth_headers_police):
    from app.db.redis import get_redis_pool
    from app.db.session import AsyncSessionLocal
    from app.services.auth_service import AuthService

    ticket = (await client.post("/api/v1/auth/ws-ticket", headers=auth_headers_police)).json()["ticket"]
    async with AsyncSessionLocal() as db:
        service = AuthService(db, await get_redis_pool())
        assert await service.redeem_ws_ticket(ticket) is not None
        assert await service.redeem_ws_ticket(ticket) is None


async def test_users_list_requires_admin(client, auth_headers_police, auth_headers_admin):
    assert (await client.get("/api/v1/users/", headers=auth_headers_police)).status_code == 403
    assert (await client.get("/api/v1/users/", headers=auth_headers_admin)).status_code == 200


async def test_admin_cannot_demote_self(client, admin_user, auth_headers_admin):
    resp = await client.patch(f"/api/v1/users/{admin_user.id}", json={"role": "police"}, headers=auth_headers_admin)
    assert resp.status_code == 400
