"""Password hashing and token handling."""
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    UserRole,
    create_access_token,
    create_refresh_token,
    decode_token,
    has_required_role,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("SecurePass12")
    assert hashed.startswith("$2b$")
    assert verify_password("SecurePass12", hashed)
    assert not verify_password("WrongPass12", hashed)


def test_password_over_bcrypt_limit_rejected_not_truncated():
    with pytest.raises(ValueError):
        hash_password("a" * 73)
    assert verify_password("a" * 73, hash_password("a" * 72)) is False


def test_access_token_roundtrip_carries_version():
    claims = decode_token(create_access_token("user-1", UserRole.POLICE, token_version=4), TokenType.ACCESS)
    assert (claims.subject, claims.role, claims.token_version) == ("user-1", UserRole.POLICE, 4)


def test_refresh_token_not_accepted_as_access():
    token, _ = create_refresh_token("user-1", UserRole.ADMIN)
    with pytest.raises(InvalidTokenError):
        decode_token(token, TokenType.ACCESS)


def test_refresh_tokens_have_unique_ids():
    _, first = create_refresh_token("u", UserRole.POLICE)
    _, second = create_refresh_token("u", UserRole.POLICE)
    assert first != second


def test_tampered_signature_rejected():
    token = create_access_token("user-1", UserRole.READONLY)
    forged = jwt.encode(
        {**jwt.decode(token, options={"verify_signature": False}), "role": "admin"}, "attacker-secret-" * 4, algorithm="HS256"
    )
    with pytest.raises(InvalidTokenError):
        decode_token(forged, TokenType.ACCESS)


def test_alg_none_rejected():
    payload = jwt.decode(create_access_token("u", UserRole.ADMIN), options={"verify_signature": False})
    unsigned = jwt.encode(payload, key=None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_token(unsigned, TokenType.ACCESS)


def test_expired_token_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "u", "role": "admin", "type": "access", "jti": "x", "iss": settings.JWT_ISSUER,
         "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
        settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_token(token, TokenType.ACCESS)


def test_wrong_issuer_rejected():
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "u", "role": "admin", "type": "access", "jti": "x", "iss": "someone-else",
         "iat": now, "exp": now + timedelta(minutes=5)},
        settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(InvalidTokenError):
        decode_token(token, TokenType.ACCESS)


@pytest.mark.parametrize(
    ("user", "required", "allowed"),
    [
        (UserRole.ADMIN, UserRole.POLICE, True),
        (UserRole.POLICE, UserRole.ANALYST, True),
        (UserRole.ANALYST, UserRole.POLICE, False),
        (UserRole.READONLY, UserRole.ANALYST, False),
    ],
)
def test_role_hierarchy(user, required, allowed):
    assert has_required_role(user, required) is allowed
