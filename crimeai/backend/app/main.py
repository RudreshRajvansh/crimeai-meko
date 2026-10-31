"""CrimeAI API entry point."""
from __future__ import annotations

import hmac
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import IntegrityError

from app.api.middleware.audit_log import AuditLogMiddleware
from app.api.middleware.error_handler import (
    domain_exception_handler,
    integrity_error_handler,
    unhandled_exception_handler,
)
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.exceptions import CrimeAIError
from app.core.logging import get_logger, setup_logging
from app.core.metrics import PrometheusMiddleware, metrics_endpoint
from app.core.rate_limit import limiter
from app.db.redis import close_redis_pool, eviction_policy, get_redis_pool
from app.db.session import check_db_connection, engine
from app.realtime.broker import broker

setup_logging(log_level=settings.LOG_LEVEL, log_format=settings.LOG_FORMAT)
logger = get_logger(__name__)

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.APP_ENV,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )


class ProbeAwareTrustedHostMiddleware(TrustedHostMiddleware):
    """Platform health checkers often use an internal Host header; probes carry no data, so let them through."""

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[override]
        if scope["type"] == "http" and scope.get("path") in {"/health", "/ready"}:
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("application_starting", version=settings.APP_VERSION, env=settings.APP_ENV)
    if not await check_db_connection():
        raise RuntimeError("Database unreachable at startup")
    redis = await get_redis_pool()
    await redis.ping()
    policy = await eviction_policy(redis)
    if policy not in (None, "noeviction"):
        # Refresh-token allow-lists, Celery messages and locks live in Redis; eviction silently drops them.
        logger.error("redis_eviction_policy_unsafe", policy=policy, required="noeviction")
    broker.start(redis)
    logger.info("application_ready")
    yield
    await broker.stop()
    await close_redis_pool()
    await engine.dispose()
    logger.info("application_stopped")


app = FastAPI(
    title=settings.APP_NAME,
    description="Crime analytics, FIR intelligence and patrol decision support for police units.",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(CrimeAIError, domain_exception_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Starlette runs the last-added middleware first; the order below is innermost to outermost.
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(AuditLogMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-CrimeAI-Client"],
    expose_headers=["X-Request-ID", "Retry-After"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ProbeAwareTrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
if settings.METRICS_ENABLED:
    app.add_middleware(PrometheusMiddleware)

app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["observability"], summary="Liveness probe")
async def health() -> dict:
    return {"status": "ok", "version": settings.APP_VERSION, "timestamp": time.time()}


@app.get("/ready", tags=["observability"], summary="Readiness probe")
async def ready() -> JSONResponse:
    db_ok = await check_db_connection()
    try:
        await (await get_redis_pool()).ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    healthy = db_ok and redis_ok
    policy = await eviction_policy(await get_redis_pool()) if redis_ok else None
    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ready" if healthy else "degraded",
            "checks": {
                "database": "ok" if db_ok else "fail",
                "redis": "ok" if redis_ok else "fail",
                # Reported, not enforced: managed Redis may forbid CONFIG, and a wrong policy degrades, not stops.
                "redis_eviction_policy": policy or "unknown",
            },
        },
    )


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    if not settings.METRICS_ENABLED:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    if settings.METRICS_TOKEN:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
        if not hmac.compare_digest(supplied, settings.METRICS_TOKEN):
            return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    return await metrics_endpoint(request)
