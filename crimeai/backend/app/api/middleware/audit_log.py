"""
Request context and audit middleware.

Every request gets an X-Request-ID that is bound into all log lines. Every
state-changing request by an authenticated user is persisted to audit_logs,
including rejected ones, because failed attempts matter as much as successful
ones in an evidence system.
"""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.services.audit_service import build_request_audit

logger = get_logger(__name__)

_SKIP_PATHS = {"/health", "/ready", "/metrics", "/favicon.ico", "/docs", "/redoc", "/openapi.json"}
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_NOT_AUDITED_PREFIXES = ("/api/v1/auth/refresh", "/api/v1/auth/ws-ticket")


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if 8 <= len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            path = request.url.path
            if path in _SKIP_PATHS:
                response = await call_next(request)
                response.headers["X-Request-ID"] = request_id
                return response

            start = time.perf_counter()
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            user_id = getattr(request.state, "user_id", None)
            ip = request.client.host if request.client else None
            (logger.warning if response.status_code >= 500 else logger.info)(
                "api_request",
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                user_id=user_id,
                ip=ip,
            )

            if request.method in _MUTATING and user_id and not path.startswith(_NOT_AUDITED_PREFIXES):
                await self._persist(request.method, path, response.status_code, user_id, ip, request_id, duration_ms)

            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id")

    @staticmethod
    async def _persist(method: str, path: str, status_code: int, user_id: str, ip: str | None,
                       request_id: str, duration_ms: float) -> None:
        try:
            async with AsyncSessionLocal() as session:
                session.add(build_request_audit(
                    method=method, path=path, status_code=status_code, user_id=user_id,
                    ip_address=ip, request_id=request_id, duration_ms=duration_ms,
                ))
                await session.commit()
        except Exception as exc:
            logger.error("audit_persist_failed", error=str(exc), path=path)
