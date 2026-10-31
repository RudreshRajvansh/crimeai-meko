"""Password hashing, JWT issuance/verification and the role model."""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import bcrypt
import jwt

from app.core.config import settings

_BCRYPT_ROUNDS = 12
_BCRYPT_MAX_BYTES = 72


class UserRole(StrEnum):
    ADMIN = "admin"
    POLICE = "police"
    ANALYST = "analyst"
    READONLY = "readonly"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.READONLY: 0,
    UserRole.ANALYST: 1,
    UserRole.POLICE: 2,
    UserRole.ADMIN: 3,
}


class InvalidTokenError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str
    role: UserRole
    token_type: TokenType
    token_version: int
    jti: str
    issued_at: datetime
    expires_at: datetime


def _password_bytes(password: str) -> bytes:
    encoded = password.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password exceeds 72 bytes, the bcrypt input limit")
    return encoded


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(_password_bytes(plain_password), hashed_password.encode())
    except ValueError:
        return False


_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check() -> None:
    """Spend the same time as a real check so unknown emails are not distinguishable by latency."""
    bcrypt.checkpw(b"timing-equaliser", _DUMMY_HASH.encode())


def _encode(subject: str, role: UserRole, token_type: TokenType, token_version: int, ttl: timedelta) -> tuple[str, str]:
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": subject,
        "role": str(role),
        "type": str(token_type),
        "ver": token_version,
        "jti": jti,
        "iss": settings.JWT_ISSUER,
        "iat": now,
        "nbf": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), jti


def create_access_token(subject: str | uuid.UUID, role: UserRole, token_version: int = 0) -> str:
    token, _ = _encode(
        str(subject), role, TokenType.ACCESS, token_version,
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return token


def create_refresh_token(subject: str | uuid.UUID, role: UserRole, token_version: int = 0) -> tuple[str, str]:
    return _encode(
        str(subject), role, TokenType.REFRESH, token_version,
        timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            options={"require": ["sub", "type", "exp", "iat", "jti", "iss"]},
        )
        claims = TokenClaims(
            subject=payload["sub"],
            role=UserRole(payload["role"]),
            token_type=TokenType(payload["type"]),
            token_version=int(payload.get("ver", 0)),
            jti=payload["jti"],
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise InvalidTokenError(str(exc)) from exc
    if claims.token_type != expected_type:
        raise InvalidTokenError(f"expected {expected_type} token")
    return claims


def has_required_role(user_role: UserRole, required_role: UserRole) -> bool:
    return ROLE_HIERARCHY.get(user_role, -1) >= ROLE_HIERARCHY.get(required_role, 999)
