"""Authentication and role-based authorisation dependencies."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, TokenType, UserRole, decode_token, has_required_role
from app.db.redis import get_redis
from app.db.session import get_db
from app.services.auth_service import AuthService

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: uuid.UUID
    role: UserRole

    def can(self, minimum: UserRole) -> bool:
        return has_required_role(self.role, minimum)


def _unauthorised(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_auth_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> AuthService:
    return AuthService(db=db, redis=redis)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentUser:
    if credentials is None:
        raise _unauthorised("Missing authentication token")
    try:
        claims = decode_token(credentials.credentials, TokenType.ACCESS)
        user_id = uuid.UUID(claims.subject)
    except (InvalidTokenError, ValueError) as exc:
        raise _unauthorised("Invalid or expired token") from exc

    state = await auth.load_state(user_id)
    if state is None or not state.is_active or state.token_version != claims.token_version:
        raise _unauthorised("Session has been revoked")

    role = UserRole(state.role)
    request.state.user_id = str(user_id)
    request.state.user_role = str(role)
    return CurrentUser(user_id=user_id, role=role)


def require_role(minimum_role: UserRole):
    async def _check(current_user: Annotated[CurrentUser, Depends(get_current_user)]) -> CurrentUser:
        if not current_user.can(minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum_role}' or higher required",
            )
        return current_user

    return _check


Viewer = Annotated[CurrentUser, Depends(require_role(UserRole.READONLY))]
Analyst = Annotated[CurrentUser, Depends(require_role(UserRole.ANALYST))]
Officer = Annotated[CurrentUser, Depends(require_role(UserRole.POLICE))]
Admin = Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))]
