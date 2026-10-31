"""Schemas for authentication and user administration."""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import UserRole


class AccountStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


def _strong_password(value: str) -> str:
    if len(value.encode()) > 72:
        raise ValueError("Password must be at most 72 bytes")
    checks = (
        any(c.isupper() for c in value),
        any(c.islower() for c in value),
        any(c.isdigit() for c in value),
    )
    if not all(checks):
        raise ValueError("Password needs upper-case, lower-case and numeric characters")
    return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str
    full_name: str
    email: str


class WebSocketTicketResponse(BaseModel):
    ticket: str
    expires_in: int


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    full_name: str = Field(min_length=2, max_length=100)
    badge_number: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)
    # Admin is never self-requestable; an administrator promotes accounts explicitly.
    requested_role: Literal["police", "analyst", "readonly"] | None = None

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        return _strong_password(value)


class AccessRequestResponse(BaseModel):
    message: str
    request_id: str
    status: str


class UserCreateRequest(RegisterRequest):
    role: UserRole = UserRole.READONLY


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None
    badge_number: str | None = Field(default=None, max_length=20)
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=10, max_length=72)

    @field_validator("password")
    @classmethod
    def _password_policy(cls, value: str) -> str:
        return _strong_password(value)


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: str
    badge_number: str | None
    department: str | None
    designation: str | None = None
    is_active: bool
    account_status: str = "approved"
    request_id: str | None = None
    requested_role: str | None = None
    last_login_at: datetime | None
    created_at: datetime
    approved_at: datetime | None = None
    approved_by: uuid.UUID | None = None
    rejection_reason: str | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


class UserStatsResponse(BaseModel):
    total_users: int
    pending_requests: int
    approved_users: int
    rejected_users: int
    suspended_users: int


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    method: str
    path: str
    ip_address: str | None
    extra_metadata: dict | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
