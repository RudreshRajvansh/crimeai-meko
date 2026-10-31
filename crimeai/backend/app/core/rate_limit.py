"""
Single shared rate limiter backed by Redis so limits hold across workers and
instances. Client IPs come from uvicorn's proxy-header handling
(--proxy-headers with FORWARDED_ALLOW_IPS), so behind a load balancer the key
is the real client address, not the proxy's.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings


def client_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=client_key,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri=settings.REDIS_URL if settings.APP_ENV != "test" else "memory://",
    strategy="moving-window",
    swallow_errors=True,
)
