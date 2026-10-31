"""Who may see an alert. One rule shared by the REST API, SQL filters and the WebSocket stream."""
from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, or_

from app.core.security import ROLE_HIERARCHY, UserRole, has_required_role
from app.models.alert import Alert


def roles_at_or_below(role: UserRole) -> list[str]:
    rank = ROLE_HIERARCHY[role]
    return [str(r) for r, r_rank in ROLE_HIERARCHY.items() if r_rank <= rank]


def is_visible(target_role: str | None, assigned_to: str | uuid.UUID | None, user_id: uuid.UUID, role: UserRole) -> bool:
    if role == UserRole.ADMIN:
        return True
    if assigned_to is not None and str(assigned_to) != str(user_id):
        return False
    if target_role is None:
        return True
    try:
        return has_required_role(role, UserRole(target_role))
    except ValueError:
        return False


def visibility_clause(user_id: uuid.UUID, role: UserRole) -> ColumnElement[bool] | None:
    if role == UserRole.ADMIN:
        return None
    return (
        or_(Alert.target_role.is_(None), Alert.target_role.in_(roles_at_or_below(role)))
        & or_(Alert.assigned_to.is_(None), Alert.assigned_to == user_id)
    )
