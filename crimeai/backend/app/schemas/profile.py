"""Schemas for profile change requests."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


class ProfileChangeRequestCreate(BaseModel):
    department: str | None = Field(default=None, max_length=100)
    designation: str | None = Field(default=None, max_length=100)


class ProfileChangeRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    requested_changes: dict
    proof_file_path: str = Field(exclude=True)
    status: str
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: uuid.UUID | None = None
    rejection_reason: str | None = None

    @computed_field
    @property
    def proof_url(self) -> str:
        """API path (under /api/v1) that streams the proof to its owner or an administrator."""
        return f"/users/profile-requests/{self.id}/proof"


class ProfileChangeRequestListResponse(BaseModel):
    items: list[ProfileChangeRequestResponse]
    total: int
