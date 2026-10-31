"""Persistence for users."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserRole
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email.lower().strip()))
        return result.scalar_one_or_none()

    async def get_by_request_id(self, request_id: str) -> User | None:
        result = await self.db.execute(select(User).where(User.request_id == request_id))
        return result.scalar_one_or_none()

    async def get_by_badge(self, badge_number: str) -> User | None:
        result = await self.db.execute(select(User).where(User.badge_number == badge_number.strip()))
        return result.scalar_one_or_none()

    async def list_all(
        self,
        role: UserRole | None = None,
        is_active: bool | None = None,
        account_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        query = select(User)
        count_query = select(func.count(User.id))
        if role:
            query = query.where(User.role == role)
            count_query = count_query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)
            count_query = count_query.where(User.is_active == is_active)
        if account_status:
            query = query.where(User.account_status == account_status)
            count_query = count_query.where(User.account_status == account_status)
        rows = await self.db.execute(query.order_by(User.created_at.desc()).limit(limit).offset(offset))
        total = (await self.db.execute(count_query)).scalar_one()
        return list(rows.scalars().all()), total

    async def create(
        self,
        email: str,
        hashed_password: str,
        full_name: str,
        role: UserRole = UserRole.READONLY,
        badge_number: str | None = None,
        department: str | None = None,
        designation: str | None = None,
        account_status: str = "approved",
        request_id: str | None = None,
        requested_role: str | None = None,
    ) -> User:
        user = User(
            email=email.lower().strip(),
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            badge_number=badge_number,
            department=department,
            designation=designation,
            account_status=account_status,
            request_id=request_id,
            requested_role=requested_role,
            is_active=account_status == "approved",
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def record_login(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(User).where(User.id == user_id).values(last_login_at=datetime.now(UTC))
        )

    async def update_fields(self, user_id: uuid.UUID, **values: object) -> None:
        await self.db.execute(update(User).where(User.id == user_id).values(**values))

    async def bump_token_version(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(User).where(User.id == user_id).values(token_version=User.token_version + 1)
        )

    async def count(self) -> int:
        return (await self.db.execute(select(func.count(User.id)))).scalar_one()

    async def count_by_status(self, status: str) -> int:
        return (await self.db.execute(
            select(func.count(User.id)).where(User.account_status == status)
        )).scalar_one()
