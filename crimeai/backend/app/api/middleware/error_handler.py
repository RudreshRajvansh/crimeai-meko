"""Maps domain and persistence errors to a stable JSON error envelope."""
from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    AuthorizationError,
    CrimeAIError,
    DatabaseError,
    ExternalServiceError,
    GraphServiceError,
    MLServiceError,
    NLPServiceError,
    NotFoundError,
    RateLimitError,
    StorageError,
    ValidationError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

_STATUS: dict[type[CrimeAIError], tuple[int, str]] = {
    NotFoundError: (status.HTTP_404_NOT_FOUND, "not_found"),
    AlreadyExistsError: (status.HTTP_409_CONFLICT, "already_exists"),
    AuthenticationError: (status.HTTP_401_UNAUTHORIZED, "authentication_failed"),
    AuthorizationError: (status.HTTP_403_FORBIDDEN, "forbidden"),
    ValidationError: (status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error"),
    RateLimitError: (status.HTTP_429_TOO_MANY_REQUESTS, "rate_limit_exceeded"),
    DatabaseError: (status.HTTP_503_SERVICE_UNAVAILABLE, "database_error"),
    MLServiceError: (status.HTTP_503_SERVICE_UNAVAILABLE, "ml_service_error"),
    NLPServiceError: (status.HTTP_503_SERVICE_UNAVAILABLE, "nlp_service_error"),
    GraphServiceError: (status.HTTP_503_SERVICE_UNAVAILABLE, "graph_service_error"),
    StorageError: (status.HTTP_503_SERVICE_UNAVAILABLE, "storage_error"),
    ExternalServiceError: (status.HTTP_502_BAD_GATEWAY, "upstream_error"),
}


def _envelope(request: Request, status_code: int, code: str, message: str, detail: object = None) -> JSONResponse:
    body: dict = {
        "error": code,
        "message": message,
        "path": request.url.path,
        "request_id": getattr(request.state, "request_id", None),
    }
    if detail is not None and settings.exposes_error_detail:
        body["detail"] = detail
    headers = {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def domain_exception_handler(request: Request, exc: CrimeAIError) -> JSONResponse:
    status_code, code = next(
        (mapping for cls, mapping in _STATUS.items() if isinstance(exc, cls)),
        (status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error"),
    )
    logger.info("domain_error", code=code, message=exc.message, path=request.url.path)
    return _envelope(request, status_code, code, exc.message, exc.detail)


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.info("integrity_conflict", path=request.url.path, error=str(exc.orig))
    return _envelope(request, status.HTTP_409_CONFLICT, "conflict", "The request conflicts with existing data")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", exc_type=type(exc).__name__, path=request.url.path, exc_info=exc)
    return _envelope(
        request, status.HTTP_500_INTERNAL_SERVER_ERROR, "internal_error", "An internal error occurred", str(exc)
    )
