"""Users router (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    ListUsers,
    SuspendUser,
    UpdateUserRole,
)
from medicore.domain.enums import Role
from medicore.domain.repositories._support import Paging, UserFilter
from medicore.domain.shared.identifiers import UserId
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.users import (
    InviteUserRequest,
    UpdateRoleRequest,
    UserListResponse,
    UserResponse,
)
from medicore.presentation.serializers import ser_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=UserListResponse)
def list_users(
    actor: Actor,
    uow: UoW,
    role: str | None = Query(None),
    status: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    with uow:
        f = UserFilter(role=role, status=status) if (role or status) else None
        page = ListUsers(uow).execute(actor, f, Paging(offset=offset, limit=limit))
    return UserListResponse(
        items=[ser_user(u) for u in page.items],
        total=page.total,
        offset=page.offset,
        limit=page.limit,
    )


@router.post("", response_model=UserResponse, status_code=201)
def invite_user(body: InviteUserRequest, actor: Actor, uow: UoW, clock: Clock):
    cmd = InviteUserCommand(
        name=body.name, email=body.email, role=Role(body.role), specialty=body.specialty
    )
    user = InviteUser(uow, clock).execute(actor, cmd)
    return ser_user(user)


@router.put("/{user_id}/role", response_model=UserResponse)
def update_role(user_id: str, body: UpdateRoleRequest, actor: Actor, uow: UoW, clock: Clock):
    user = UpdateUserRole(uow, clock).execute(actor, UserId.parse(user_id), Role(body.role))
    return ser_user(user)


@router.post("/{user_id}/suspend", response_model=UserResponse)
def suspend_user(user_id: str, actor: Actor, uow: UoW, clock: Clock):
    user = SuspendUser(uow, clock).execute(actor, UserId.parse(user_id))
    return ser_user(user)
