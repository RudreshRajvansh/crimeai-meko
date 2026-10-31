"""Refresh rotation, reuse detection and revocation, with Redis faked and the user table stubbed."""
import uuid
from types import SimpleNamespace

import fakeredis.aioredis
import pytest

from app.core.exceptions import AuthenticationError
from app.core.security import UserRole, hash_password
from app.services.auth_service import AuthService

pytestmark = pytest.mark.asyncio


class StubUsers:
    def __init__(self, user):
        self.user = user

    async def get_by_id(self, user_id):
        return self.user if user_id == self.user.id else None

    async def get_by_email(self, email):
        return self.user if email == self.user.email else None

    async def record_login(self, user_id):
        pass

    async def bump_token_version(self, user_id):
        self.user.token_version += 1


class StubDb:
    async def commit(self):
        pass


@pytest.fixture
def user():
    return SimpleNamespace(
        id=uuid.uuid4(), email="o@x.in", hashed_password=hash_password("PolicePass12"),
        role="police", is_active=True, token_version=0, full_name="Officer",
    )


@pytest.fixture
def service(user):
    svc = AuthService(StubDb(), fakeredis.aioredis.FakeRedis(decode_responses=True))
    svc.users = StubUsers(user)
    return svc


async def test_rotation_issues_new_refresh_and_invalidates_old(service):
    session = await service.authenticate("o@x.in", "PolicePass12")
    rotated = await service.rotate(session.refresh_token)
    assert rotated.refresh_token != session.refresh_token
    with pytest.raises(AuthenticationError):
        await service.rotate(session.refresh_token)


async def test_reuse_revokes_every_session(service, user):
    session = await service.authenticate("o@x.in", "PolicePass12")
    rotated = await service.rotate(session.refresh_token)
    with pytest.raises(AuthenticationError):
        await service.rotate(session.refresh_token)
    assert user.token_version == 1
    with pytest.raises(AuthenticationError):
        await service.rotate(rotated.refresh_token)


async def test_logout_invalidates_refresh(service):
    session = await service.authenticate("o@x.in", "PolicePass12")
    await service.logout(session.refresh_token)
    with pytest.raises(AuthenticationError):
        await service.rotate(session.refresh_token)


async def test_deactivated_user_cannot_refresh(service, user):
    session = await service.authenticate("o@x.in", "PolicePass12")
    user.is_active = False
    with pytest.raises(AuthenticationError):
        await service.rotate(session.refresh_token)


async def test_state_cache_reflects_revocation(service, user):
    assert (await service.load_state(user.id)).token_version == 0
    await service.revoke_all(user.id, reason="test")
    assert (await service.load_state(user.id)).token_version == 1


async def test_ws_ticket_single_use(service, user):
    ticket = await service.issue_ws_ticket(user.id, UserRole.POLICE)
    assert await service.redeem_ws_ticket(ticket) == (user.id, UserRole.POLICE)
    assert await service.redeem_ws_ticket(ticket) is None
