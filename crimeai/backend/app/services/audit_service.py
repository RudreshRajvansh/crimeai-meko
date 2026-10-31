"""Durable audit trail for sensitive reads and every state-changing request."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def record_audit(
    db: AsyncSession,
    request: Request,
    user: Any,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Written inside the caller's transaction: the audit row commits or rolls back with the action."""
    db.add(
        AuditLog(
            user_id=getattr(user, "user_id", None),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            method=request.method,
            path=request.url.path,
            ip_address=_client_ip(request),
            request_id=getattr(request.state, "request_id", None),
            extra_metadata=metadata,
        )
    )


def build_request_audit(
    *,
    method: str,
    path: str,
    status_code: int,
    user_id: str | None,
    ip_address: str | None,
    request_id: str,
    duration_ms: float,
) -> AuditLog:
    parts = [p for p in path.split("/") if p]
    resource_type = parts[2] if len(parts) > 2 else "root"
    resource_id = parts[3] if len(parts) > 3 else None
    return AuditLog(
        user_id=uuid.UUID(user_id) if user_id else None,
        action=f"{resource_type}.{method.lower()}",
        resource_type=resource_type[:50],
        resource_id=resource_id[:100] if resource_id else None,
        method=method,
        path=path[:500],
        ip_address=ip_address,
        request_id=request_id,
        extra_metadata={"status": status_code, "duration_ms": duration_ms},
    )
