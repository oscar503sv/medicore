"""Users router (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from medicore.application.use_cases.sessions import (
    ListUserSessions,
    RevokeAllUserSessions,
    RevokeUserSession,
)
from medicore.application.use_cases.users import (
    InviteUser,
    InviteUserCommand,
    ListUsers,
    ReactivateUser,
    ResetUserPassword,
    ResetUserPasswordCommand,
    SuspendUser,
    UpdateUser,
    UpdateUserRole,
)
from medicore.domain.enums import Role, Sex
from medicore.domain.repositories._support import Paging, UserFilter
from medicore.domain.shared.identifiers import SessionId, UserId
from medicore.presentation.dependencies import Actor, Clock, Hasher, UoW
from medicore.presentation.schemas.auth import SessionListResponse
from medicore.presentation.schemas.users import (
    InviteUserRequest,
    ResetPasswordRequest,
    UpdateRoleRequest,
    UpdateUserRequest,
    UserListResponse,
    UserResponse,
)
from medicore.presentation.serializers import ser_session_info, ser_user

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
def invite_user(body: InviteUserRequest, actor: Actor, uow: UoW, hasher: Hasher, clock: Clock):
    cmd = InviteUserCommand(
        name=body.name,
        email=body.email,
        role=Role(body.role),
        password=body.password,
        sex=Sex(body.sex) if body.sex else None,
        phone=body.phone,
        specialty=body.specialty,
    )
    user = InviteUser(uow, hasher, clock).execute(actor, cmd)
    return ser_user(user)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: str, body: UpdateUserRequest, actor: Actor, uow: UoW, clock: Clock):
    changes = body.model_dump(exclude_none=True)
    if "role" in changes:
        changes["role"] = Role(changes["role"])
    if "sex" in changes:
        changes["sex"] = Sex(changes["sex"])
    user = UpdateUser(uow, clock).execute(actor, UserId.parse(user_id), **changes)
    return ser_user(user)


@router.put("/{user_id}/role", response_model=UserResponse)
def update_role(user_id: str, body: UpdateRoleRequest, actor: Actor, uow: UoW, clock: Clock):
    user = UpdateUserRole(uow, clock).execute(actor, UserId.parse(user_id), Role(body.role))
    return ser_user(user)


@router.post("/{user_id}/suspend", response_model=UserResponse)
def suspend_user(user_id: str, actor: Actor, uow: UoW, clock: Clock):
    user = SuspendUser(uow, clock).execute(actor, UserId.parse(user_id))
    return ser_user(user)


@router.post("/{user_id}/reactivate", response_model=UserResponse)
def reactivate_user(user_id: str, actor: Actor, uow: UoW, clock: Clock):
    user = ReactivateUser(uow, clock).execute(actor, UserId.parse(user_id))
    return ser_user(user)


@router.get("/{user_id}/sessions", response_model=SessionListResponse)
def list_user_sessions(user_id: str, actor: Actor, uow: UoW, clock: Clock):
    sessions = ListUserSessions(uow, clock).execute(actor, UserId.parse(user_id))
    return SessionListResponse(items=[ser_session_info(s) for s in sessions])


@router.delete("/{user_id}/sessions/{session_id}", status_code=204)
def revoke_user_session(user_id: str, session_id: str, actor: Actor, uow: UoW, clock: Clock):
    RevokeUserSession(uow, clock).execute(
        actor, UserId.parse(user_id), SessionId.parse(session_id)
    )


@router.delete("/{user_id}/sessions", status_code=204)
def revoke_all_user_sessions(user_id: str, actor: Actor, uow: UoW, clock: Clock):
    RevokeAllUserSessions(uow, clock).execute(actor, UserId.parse(user_id))


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: str, body: ResetPasswordRequest, actor: Actor, uow: UoW, hasher: Hasher, clock: Clock
):
    cmd = ResetUserPasswordCommand(user_id=UserId.parse(user_id), password=body.password)
    user = ResetUserPassword(uow, hasher, clock).execute(actor, cmd)
    return ser_user(user)
