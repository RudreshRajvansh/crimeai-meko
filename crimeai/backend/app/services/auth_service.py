"""
Session lifecycle: login, refresh-token rotation with reuse detection, logout,
global revocation and single-use WebSocket tickets.

Postgres is the source of truth for whether a user may act (is_active, role,
token_version). Redis caches that state for AUTH_STATE_CACHE_TTL seconds and
holds the allow-list of live refresh-token IDs. If Redis loses a refresh entry
the user is asked to sign in again: failures close, they never open.
"""
from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import asdict, dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging import get_logger
from app.core.security import (
    InvalidTokenError,
    TokenType,
    UserRole,
    burn_password_check,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)

_STATE_KEY = "auth:state:{}"
_REFRESH_KEY = "auth:refresh:{}"
_WS_TICKET_KEY = "auth:ws:{}"


@dataclass(frozen=True, slots=True)
class AuthState:
    user_id: str
    role: str
    is_active: bool
    token_version: int


@dataclass(frozen=True, slots=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    expires_in: int
    user: User


class AuthService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self.db = db
        self.redis = redis
        self.users = UserRepository(db)

    async def load_state(self, user_id: uuid.UUID) -> AuthState | None:
        key = _STATE_KEY.format(user_id)
        cached = await self.redis.get(key)
        if cached:
            return AuthState(**json.loads(cached))
        user = await self.users.get_by_id(user_id)
        if user is None:
            return None
        state = AuthState(str(user.id), user.role, user.is_active, user.token_version)
        await self.redis.set(key, json.dumps(asdict(state)), ex=settings.AUTH_STATE_CACHE_TTL)
        return state

    async def invalidate_state(self, user_id: uuid.UUID) -> None:
        await self.redis.delete(_STATE_KEY.format(user_id))

    async def authenticate(self, email: str, password: str) -> IssuedSession:
        user = await self.users.get_by_email(email)
        if user is None:
            burn_password_check()
            raise AuthenticationError("Invalid email or password")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        # Check account status before allowing login
        status = getattr(user, "account_status", "approved")
        if status == "pending":
            raise AuthorizationError("Your access request is awaiting administrator approval.")
        if status == "rejected":
            raise AuthorizationError("Your access request was not approved. Please contact the administrator.")
        if status == "suspended":
            raise AuthorizationError("Your account has been suspended. Please contact the administrator.")
        if not user.is_active:
            raise AuthorizationError("Account is deactivated. Contact an administrator.")
        await self.users.record_login(user.id)
        return await self._issue(user)

    async def rotate(self, refresh_token: str) -> IssuedSession:
        try:
            claims = decode_token(refresh_token, TokenType.REFRESH)
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid or expired refresh token") from exc

        user_id = uuid.UUID(claims.subject)
        owner = await self.redis.getdel(_REFRESH_KEY.format(claims.jti))
        if isinstance(owner, bytes):
            owner = owner.decode("utf-8")
        if owner != claims.subject:
            await self.revoke_all(user_id, reason="refresh_token_reuse")
            raise AuthenticationError("Refresh token is no longer valid; sign in again")

        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active or user.token_version != claims.token_version:
            raise AuthenticationError("Session has been revoked; sign in again")
        return await self._issue(user)

    async def logout(self, refresh_token: str | None) -> None:
        if not refresh_token:
            return
        try:
            claims = decode_token(refresh_token, TokenType.REFRESH)
        except InvalidTokenError:
            return
        await self.redis.delete(_REFRESH_KEY.format(claims.jti))

    async def revoke_all(self, user_id: uuid.UUID, reason: str) -> None:
        await self.users.bump_token_version(user_id)
        # Commit now: callers usually raise right after, which would roll this back.
        await self.db.commit()
        await self.invalidate_state(user_id)
        logger.warning("sessions_revoked", user_id=str(user_id), reason=reason)

    async def issue_ws_ticket(self, user_id: uuid.UUID, role: UserRole) -> str:
        ticket = secrets.token_urlsafe(32)
        await self.redis.set(
            _WS_TICKET_KEY.format(ticket),
            json.dumps({"user_id": str(user_id), "role": str(role)}),
            ex=settings.WS_TICKET_TTL_SECONDS,
        )
        return ticket

    async def redeem_ws_ticket(self, ticket: str) -> tuple[uuid.UUID, UserRole] | None:
        raw = await self.redis.getdel(_WS_TICKET_KEY.format(ticket))
        if not raw:
            return None
        data = json.loads(raw)
        return uuid.UUID(data["user_id"]), UserRole(data["role"])

    async def _issue(self, user: User) -> IssuedSession:
        role = UserRole(user.role)
        access = create_access_token(user.id, role, user.token_version)
        refresh, jti = create_refresh_token(user.id, role, user.token_version)
        await self.redis.set(
            _REFRESH_KEY.format(jti),
            str(user.id),
            ex=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
        return IssuedSession(access, refresh, settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60, user)
