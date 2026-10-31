"""User administration. Any change to role or status revokes the user's live sessions."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func, select

from app.api.v1.dependencies.auth import Admin, Viewer, get_auth_service
from app.api.v1.uploads import read_capped
from app.core.config import settings
from app.core.exceptions import AlreadyExistsError, NotFoundError, ValidationError
from app.core.security import UserRole, hash_password
from app.models.audit_log import AuditLog
from app.models.profile_request import ProfileChangeRequest
from app.nlp.documents import sniff_content_type
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AuditLogListResponse,
    AuditLogResponse,
    PasswordResetRequest,
    RejectRequest,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserStatsResponse,
    UserUpdateRequest,
)
from app.schemas.profile import ProfileChangeRequestListResponse, ProfileChangeRequestResponse
from app.services.audit_service import record_audit
from app.services.auth_service import AuthService
from app.services.storage import load_document, store_object

router = APIRouter()
AuthDep = Annotated[AuthService, Depends(get_auth_service)]


@router.get("/me", response_model=UserResponse)
async def get_me(user: Viewer, auth: AuthDep) -> UserResponse:
    record = await UserRepository(auth.db).get_by_id(user.user_id)
    if record is None:
        raise NotFoundError("User not found")
    return UserResponse.model_validate(record)


@router.get("/", response_model=UserListResponse)
async def list_users(
    admin: Admin,
    auth: AuthDep,
    role: UserRole | None = None,
    is_active: bool | None = None,
    account_status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> UserListResponse:
    items, total = await UserRepository(auth.db).list_all(
        role=role, is_active=is_active, account_status=account_status,
        limit=limit, offset=offset,
    )
    return UserListResponse(items=[UserResponse.model_validate(u) for u in items], total=total)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreateRequest, admin: Admin, auth: AuthDep) -> UserResponse:
    users = UserRepository(auth.db)
    if await users.get_by_email(body.email):
        raise AlreadyExistsError("Email already registered")
    user = await users.create(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
        badge_number=body.badge_number,
        department=body.department,
        designation=body.designation,
    )
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: UUID, body: UserUpdateRequest, admin: Admin, auth: AuthDep) -> UserResponse:
    users = UserRepository(auth.db)
    user = await users.get_by_id(user_id)
    if user is None:
        raise NotFoundError("User not found")
    changes = body.model_dump(exclude_unset=True)
    if user_id == admin.user_id and (changes.get("is_active") is False or changes.get("role", UserRole.ADMIN) != UserRole.ADMIN):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Administrators cannot demote or deactivate themselves")
    if changes:
        await users.update_fields(user_id, **changes)
        if {"role", "is_active"} & changes.keys():
            await auth.revoke_all(user_id, reason="admin_changed_access")
        await auth.db.refresh(user)
    return UserResponse.model_validate(user)


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT,
            summary="Set a temporary password; signs the user out everywhere (admin, audited)")
async def reset_password(user_id: UUID, body: PasswordResetRequest, request: Request, admin: Admin,
                         auth: AuthDep) -> None:
    users = UserRepository(auth.db)
    if await users.get_by_id(user_id) is None:
        raise NotFoundError("User not found")
    await users.update_fields(user_id, hashed_password=hash_password(body.password))
    await record_audit(auth.db, request, admin, action="user.password_reset", resource_type="user",
                       resource_id=str(user_id))
    # Commits the new hash and the audit row, and ends every session opened with the old password.
    await auth.revoke_all(user_id, reason="password_reset")


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(user_id: UUID, admin: Admin, auth: AuthDep) -> None:
    if user_id == admin.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot deactivate your own account")
    users = UserRepository(auth.db)
    if await users.get_by_id(user_id) is None:
        raise NotFoundError("User not found")
    await users.update_fields(user_id, is_active=False, account_status="suspended")
    await auth.revoke_all(user_id, reason="deactivated")


# ─── Access Requests ───────────────────────────────────────────────────────────

@router.get("/requests", response_model=UserListResponse)
async def list_access_requests(
    admin: Admin,
    auth: AuthDep,
    account_status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> UserListResponse:
    """List access requests (users who registered via the public form)."""
    users_repo = UserRepository(auth.db)
    # If no filter, show pending requests by default
    status_filter = account_status or "pending"
    items, total = await users_repo.list_all(
        account_status=status_filter, limit=limit, offset=offset,
    )
    return UserListResponse(items=[UserResponse.model_validate(u) for u in items], total=total)


@router.get("/requests/{user_id}", response_model=UserResponse)
async def get_access_request(user_id: UUID, admin: Admin, auth: AuthDep) -> UserResponse:
    user = await UserRepository(auth.db).get_by_id(user_id)
    if user is None:
        raise NotFoundError("Access request not found")
    return UserResponse.model_validate(user)


@router.patch("/requests/{user_id}/approve", response_model=UserResponse)
async def approve_access_request(user_id: UUID, admin: Admin, auth: AuthDep) -> UserResponse:
    users = UserRepository(auth.db)
    user = await users.get_by_id(user_id)
    if user is None:
        raise NotFoundError("Access request not found")
    if user.account_status not in ("pending", "rejected"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot approve a user with status '{user.account_status}'")
    kwargs = {
        "account_status": "approved",
        "is_active": True,
        "approved_at": datetime.now(UTC),
        "approved_by": admin.user_id,
    }
    if user.requested_role:
        kwargs["role"] = user.requested_role

    await users.update_fields(user_id, **kwargs)
    await auth.db.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/requests/{user_id}/reject", response_model=UserResponse)
async def reject_access_request(user_id: UUID, body: RejectRequest, admin: Admin, auth: AuthDep) -> UserResponse:
    users = UserRepository(auth.db)
    user = await users.get_by_id(user_id)
    if user is None:
        raise NotFoundError("Access request not found")
    if user.account_status not in ("pending",):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot reject a user with status '{user.account_status}'")
    await users.update_fields(
        user_id,
        account_status="rejected",
        is_active=False,
        rejection_reason=body.reason,
    )
    if user.is_active:
        await auth.revoke_all(user_id, reason="access_rejected")
    await auth.db.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/suspend", response_model=UserResponse)
async def suspend_user(user_id: UUID, admin: Admin, auth: AuthDep) -> UserResponse:
    if user_id == admin.user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot suspend your own account")
    users = UserRepository(auth.db)
    user = await users.get_by_id(user_id)
    if user is None:
        raise NotFoundError("User not found")
    await users.update_fields(user_id, account_status="suspended", is_active=False)
    await auth.revoke_all(user_id, reason="suspended")
    await auth.db.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}/reactivate", response_model=UserResponse)
async def reactivate_user(user_id: UUID, admin: Admin, auth: AuthDep) -> UserResponse:
    users = UserRepository(auth.db)
    user = await users.get_by_id(user_id)
    if user is None:
        raise NotFoundError("User not found")
    await users.update_fields(user_id, account_status="approved", is_active=True)
    await auth.db.refresh(user)
    return UserResponse.model_validate(user)


# ─── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=UserStatsResponse)
async def user_stats(admin: Admin, auth: AuthDep) -> UserStatsResponse:
    users = UserRepository(auth.db)
    return UserStatsResponse(
        total_users=await users.count(),
        pending_requests=await users.count_by_status("pending"),
        approved_users=await users.count_by_status("approved"),
        rejected_users=await users.count_by_status("rejected"),
        suspended_users=await users.count_by_status("suspended"),
    )


# ─── Audit Logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    admin: Admin,
    auth: AuthDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AuditLogListResponse:
    query = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
    count_query = select(func.count(AuditLog.id))
    rows = await auth.db.execute(query)
    total = (await auth.db.execute(count_query)).scalar_one()
    items = [AuditLogResponse.model_validate(log) for log in rows.scalars().all()]
    return AuditLogListResponse(items=items, total=total)


# ─── Profile Change Requests ───────────────────────────────────────────────────

# Proofs are identity documents: sniffed by content, size-capped, stored privately, read through an audited route.
_PROOF_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}


@router.post("/profile/change-request", response_model=ProfileChangeRequestResponse)
async def create_profile_change_request(
    user: Viewer,
    auth: AuthDep,
    department: str | None = Form(None, max_length=100),
    designation: str | None = Form(None, max_length=100),
    proof: UploadFile = File(...),
) -> ProfileChangeRequestResponse:
    if not department and not designation:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Must provide at least one field to change")
    data = await read_capped(proof, settings.MAX_UPLOAD_BYTES)
    content_type = sniff_content_type(data)
    if content_type not in _PROOF_TYPES:
        raise ValidationError("Proof must be a PDF or an image (PNG, JPEG or WebP)")
    stored = await store_object(f"proofs/{user.user_id}", proof.filename, data, content_type)

    changes = {}
    if department:
        changes["department"] = department
    if designation:
        changes["designation"] = designation

    req = ProfileChangeRequest(user_id=user.user_id, requested_changes=changes, proof_file_path=stored.url)
    auth.db.add(req)
    await auth.db.commit()
    await auth.db.refresh(req)
    return ProfileChangeRequestResponse.model_validate(req)


@router.get("/profile-requests/{req_id}/proof", summary="Proof attached to a profile change request (owner or admin, audited)")
async def get_profile_request_proof(req_id: UUID, request: Request, user: Viewer, auth: AuthDep) -> Response:
    req = await auth.db.get(ProfileChangeRequest, req_id)
    # Someone else's request reads as missing rather than forbidden, so ids cannot be probed.
    if req is None or (req.user_id != user.user_id and not user.can(UserRole.ADMIN)) or "://" not in req.proof_file_path:
        raise NotFoundError("Proof not found")
    data = await load_document(req.proof_file_path)
    await record_audit(auth.db, request, user, action="profile_request.read_proof",
                       resource_type="profile_change_request", resource_id=str(req_id))
    return Response(
        data,
        media_type=sniff_content_type(data) or "application/octet-stream",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
                 "Content-Disposition": f'inline; filename="proof-{req_id}"'},
    )


@router.get("/profile/change-requests", response_model=ProfileChangeRequestListResponse)
async def list_my_profile_requests(user: Viewer, auth: AuthDep) -> ProfileChangeRequestListResponse:
    query = select(ProfileChangeRequest).where(ProfileChangeRequest.user_id == user.user_id).order_by(ProfileChangeRequest.created_at.desc())
    count_query = select(func.count(ProfileChangeRequest.id)).where(ProfileChangeRequest.user_id == user.user_id)
    rows = await auth.db.execute(query)
    total = (await auth.db.execute(count_query)).scalar_one()
    items = [ProfileChangeRequestResponse.model_validate(r) for r in rows.scalars().all()]
    return ProfileChangeRequestListResponse(items=items, total=total)


@router.get("/profile-requests", response_model=ProfileChangeRequestListResponse)
async def list_all_profile_requests(
    admin: Admin,
    auth: AuthDep,
    request_status: str | None = Query("pending", alias="status"),
    limit: int = Query(50),
    offset: int = Query(0)
) -> ProfileChangeRequestListResponse:
    query = select(ProfileChangeRequest)
    count_query = select(func.count(ProfileChangeRequest.id))
    if request_status:
        query = query.where(ProfileChangeRequest.status == request_status)
        count_query = count_query.where(ProfileChangeRequest.status == request_status)

    query = query.order_by(ProfileChangeRequest.created_at.desc()).limit(limit).offset(offset)
    rows = await auth.db.execute(query)
    total = (await auth.db.execute(count_query)).scalar_one()

    items = [ProfileChangeRequestResponse.model_validate(r) for r in rows.scalars().all()]
    return ProfileChangeRequestListResponse(items=items, total=total)


@router.patch("/profile-requests/{req_id}/approve", response_model=ProfileChangeRequestResponse)
async def approve_profile_request(req_id: UUID, admin: Admin, auth: AuthDep) -> ProfileChangeRequestResponse:
    req = await auth.db.get(ProfileChangeRequest, req_id)
    if not req:
        raise NotFoundError("Request not found")
    if req.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Request is already resolved")

    req.status = "approved"
    req.resolved_at = datetime.now(UTC)
    req.resolved_by = admin.user_id

    users = UserRepository(auth.db)
    await users.update_fields(req.user_id, **req.requested_changes)

    await auth.db.commit()
    await auth.db.refresh(req)
    return ProfileChangeRequestResponse.model_validate(req)


@router.patch("/profile-requests/{req_id}/reject", response_model=ProfileChangeRequestResponse)
async def reject_profile_request(req_id: UUID, body: RejectRequest, admin: Admin, auth: AuthDep) -> ProfileChangeRequestResponse:
    req = await auth.db.get(ProfileChangeRequest, req_id)
    if not req:
        raise NotFoundError("Request not found")
    if req.status != "pending":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Request is already resolved")

    req.status = "rejected"
    req.rejection_reason = body.reason
    req.resolved_at = datetime.now(UTC)
    req.resolved_by = admin.user_id

    await auth.db.commit()
    await auth.db.refresh(req)
    return ProfileChangeRequestResponse.model_validate(req)
