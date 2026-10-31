"""
Authentication.

Browsers receive the refresh token only as an HttpOnly cookie, so script on the
page can never read it; the short-lived access token lives in memory. Cookie
endpoints demand the X-CrimeAI-Client header, which forces a CORS preflight and
so blocks cross-site request forgery from origins not in ALLOWED_ORIGINS.
"""

import secrets
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status

from app.api.v1.dependencies.auth import Viewer, get_auth_service
from app.core.config import settings
from app.core.exceptions import AlreadyExistsError
from app.core.rate_limit import limiter
from app.core.security import UserRole, hash_password
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AccessRequestResponse,
    LoginRequest,
    RegisterRequest,
    SessionResponse,
    WebSocketTicketResponse,
)
from app.services.audit_service import record_audit
from app.services.auth_service import AuthService, IssuedSession

router = APIRouter()

CLIENT_HEADER = "X-CrimeAI-Client"
AuthDep = Annotated[AuthService, Depends(get_auth_service)]


def _require_client_header(x_crimeai_client: Annotated[str | None, Header()] = None) -> None:
    if not x_crimeai_client:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Missing {CLIENT_HEADER} header")


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.REFRESH_COOKIE_SECURE,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        path=f"{settings.API_V1_PREFIX}/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        path=f"{settings.API_V1_PREFIX}/auth",
    )


def _session_response(session: IssuedSession, response: Response) -> SessionResponse:
    _set_refresh_cookie(response, session.refresh_token)
    return SessionResponse(
        access_token=session.access_token,
        expires_in=session.expires_in,
        user_id=str(session.user.id),
        role=session.user.role,
        full_name=session.user.full_name,
        email=session.user.email,
    )


async def _new_request_id(users: UserRepository) -> str:
    """Short reference the applicant can quote, e.g. CR-2026-4F9A2C; retried on the rare collision."""
    for _ in range(5):
        candidate = f"CR-{datetime.now(UTC).year}-{secrets.token_hex(3).upper()}"
        if not await users.get_by_request_id(candidate):
            return candidate
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not allocate a request id; try again")


@router.post("/login", response_model=SessionResponse, dependencies=[Depends(_require_client_header)])
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(request: Request, response: Response, body: LoginRequest, auth: AuthDep) -> SessionResponse:
    session = await auth.authenticate(body.email, body.password)
    return _session_response(session, response)


@router.post("/refresh", response_model=SessionResponse, dependencies=[Depends(_require_client_header)])
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def refresh(
    request: Request,
    response: Response,
    auth: AuthDep,
    refresh_cookie: Annotated[str | None, Cookie(alias=settings.REFRESH_COOKIE_NAME)] = None,
) -> SessionResponse:
    if not refresh_cookie:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No active session")
    session = await auth.rotate(refresh_cookie)
    return _session_response(session, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_require_client_header)])
async def logout(
    response: Response,
    auth: AuthDep,
    refresh_cookie: Annotated[str | None, Cookie(alias=settings.REFRESH_COOKIE_NAME)] = None,
) -> Response:
    await auth.logout(refresh_cookie)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_everywhere(response: Response, user: Viewer, auth: AuthDep) -> Response:
    await auth.revoke_all(user.user_id, reason="user_requested")
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/ws-ticket", response_model=WebSocketTicketResponse)
async def websocket_ticket(user: Viewer, auth: AuthDep) -> WebSocketTicketResponse:
    """Single-use, 30-second ticket for opening the alert stream without putting a JWT in a URL."""
    ticket = await auth.issue_ws_ticket(user.user_id, user.role)
    return WebSocketTicketResponse(ticket=ticket, expires_in=settings.WS_TICKET_TTL_SECONDS)


@router.post("/register", response_model=AccessRequestResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def register(request: Request, body: RegisterRequest, auth: AuthDep) -> AccessRequestResponse:
    """
    Self-service access request. Accounts are created with status 'pending'
    and the read-only role; an administrator approves them through /users/requests.
    """
    if not settings.ALLOW_SELF_REGISTRATION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Self-registration is disabled; contact an administrator")
    users = UserRepository(auth.db)
    if await users.get_by_email(body.email):
        raise AlreadyExistsError("An account with this email already exists")
    if body.badge_number and await users.get_by_badge(body.badge_number):
        raise AlreadyExistsError("An account with this Employee ID already exists")

    request_id = await _new_request_id(users)
    user = await users.create(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=UserRole.READONLY,
        badge_number=body.badge_number,
        department=body.department,
        designation=body.designation,
        account_status="pending",
        request_id=request_id,
        requested_role=body.requested_role,
    )
    await record_audit(
        auth.db, request, user=None, action="ACCESS_REQUEST_CREATED",
        resource_type="user", resource_id=str(user.id),
        metadata={"request_id": request_id, "email": body.email, "full_name": body.full_name},
    )
    return AccessRequestResponse(
        message="Access request received and awaiting administrator approval",
        request_id=request_id,
        status="pending",
    )
