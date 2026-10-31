"""Access-request signup, admin approval, and profile-change proofs."""
import re

import pytest

from app.core.config import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
APPLICANT = {"email": "new.officer@crimeai.example", "password": "SecurePass12", "full_name": "New Officer",
             "badge_number": "DL-9001", "designation": "Sub-Inspector"}


@pytest.fixture
def signup_open(monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_SELF_REGISTRATION", True)


async def _login(client, email, password):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_request_waits_for_approval_then_can_sign_in(client, signup_open, auth_headers_admin):
    resp = await client.post("/api/v1/auth/register", json=APPLICANT)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "pending" and re.fullmatch(r"CR-\d{4}-[0-9A-F]{6}", body["request_id"])

    pending = await _login(client, APPLICANT["email"], APPLICANT["password"])
    assert pending.status_code == 403 and "awaiting" in pending.json()["message"]

    queue = (await client.get("/api/v1/users/requests", headers=auth_headers_admin)).json()
    applicant = next(u for u in queue["items"] if u["email"] == APPLICANT["email"])
    assert applicant["role"] == "readonly"
    approved = await client.patch(f"/api/v1/users/requests/{applicant['id']}/approve", headers=auth_headers_admin)
    assert approved.status_code == 200 and approved.json()["account_status"] == "approved"

    assert (await _login(client, APPLICANT["email"], APPLICANT["password"])).status_code == 200


async def test_duplicate_badge_is_rejected(client, signup_open):
    assert (await client.post("/api/v1/auth/register", json=APPLICANT)).status_code == 202
    again = await client.post("/api/v1/auth/register", json={**APPLICANT, "email": "other@crimeai.example"})
    assert again.status_code == 409


async def test_proof_must_be_a_document_not_html(client, auth_headers_readonly):
    resp = await client.post(
        "/api/v1/users/profile/change-request", headers=auth_headers_readonly,
        data={"designation": "Inspector"},
        files={"proof": ("proof.html", b"<script>alert(1)</script>", "image/png")},
    )
    assert resp.status_code == 422


async def test_proof_is_private_to_owner_and_admin(client, auth_headers_readonly, auth_headers_analyst, auth_headers_admin):
    created = await client.post(
        "/api/v1/users/profile/change-request", headers=auth_headers_readonly,
        data={"designation": "Inspector"}, files={"proof": ("order.png", PNG, "image/png")},
    )
    assert created.status_code == 200
    body = created.json()
    assert "proof_file_path" not in body, "internal storage location must not leak"
    url = "/api/v1" + body["proof_url"]

    owner = await client.get(url, headers=auth_headers_readonly)
    assert owner.status_code == 200 and owner.headers["content-type"] == "image/png"
    assert owner.headers["cache-control"] == "private, no-store"
    assert (await client.get(url, headers=auth_headers_analyst)).status_code == 404
    assert (await client.get(url, headers=auth_headers_admin)).status_code == 200


async def test_uploads_directory_is_not_served(client):
    assert (await client.get("/uploads/proofs/anything.png")).status_code == 404


async def test_admin_password_reset_replaces_password_and_ends_sessions(
    client, police_user, auth_headers_police, auth_headers_admin, auth_headers_analyst
):
    url = f"/api/v1/users/{police_user.id}/password"
    assert (await client.put(url, headers=auth_headers_analyst, json={"password": "TempPass12345"})).status_code == 403
    assert (await client.put(url, headers=auth_headers_admin, json={"password": "weak"})).status_code == 422

    assert (await client.put(url, headers=auth_headers_admin, json={"password": "TempPass12345"})).status_code == 204

    assert (await _login(client, police_user.email, "PolicePass12")).status_code == 401
    assert (await _login(client, police_user.email, "TempPass12345")).status_code == 200
    # The access token issued before the reset no longer works.
    assert (await client.get("/api/v1/users/me", headers=auth_headers_police)).status_code == 401


async def test_requested_role_is_granted_on_approval_but_admin_cannot_be_requested(
    client, signup_open, auth_headers_admin
):
    admin_ask = await client.post("/api/v1/auth/register", json={**APPLICANT, "requested_role": "admin"})
    assert admin_ask.status_code == 422

    resp = await client.post("/api/v1/auth/register", json={**APPLICANT, "requested_role": "analyst"})
    assert resp.status_code == 202
    queue = (await client.get("/api/v1/users/requests", headers=auth_headers_admin)).json()
    applicant = next(u for u in queue["items"] if u["email"] == APPLICANT["email"])
    assert applicant["role"] == "readonly" and applicant["requested_role"] == "analyst"
    approved = await client.patch(f"/api/v1/users/requests/{applicant['id']}/approve", headers=auth_headers_admin)
    assert approved.json()["role"] == "analyst"
