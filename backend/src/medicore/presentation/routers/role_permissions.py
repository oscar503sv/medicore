"""Role-permission customization router (tenant admin, gated by permissions.manage)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from medicore.application.use_cases.role_permissions import (
    GetPermissionsMatrix,
    PermissionsMatrixDTO,
    ResetRolePermissions,
    UpdateRolePermissions,
)
from medicore.domain.enums import Role
from medicore.presentation.dependencies import Actor, Clock, UoW
from medicore.presentation.schemas.role_permissions import (
    PermissionsMatrixResponse,
    RolePermissionsResponse,
    UpdateRolePermissionsRequest,
)

router = APIRouter(prefix="/permissions", tags=["permissions"])


def parse_role(value: str) -> Role:
    try:
        return Role(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"unknown role: {value}"
        ) from exc


def ser_matrix(matrix: PermissionsMatrixDTO) -> PermissionsMatrixResponse:
    return PermissionsMatrixResponse(
        catalog=list(matrix.catalog),
        roles={
            str(role): RolePermissionsResponse(
                defaults=list(entry.defaults),
                effective=list(entry.effective),
                customized=entry.customized,
            )
            for role, entry in matrix.roles.items()
        },
    )


@router.get("", response_model=PermissionsMatrixResponse)
def get_matrix(actor: Actor, uow: UoW):
    with uow:
        return ser_matrix(GetPermissionsMatrix(uow).execute(actor))


@router.put("/roles/{role}", response_model=PermissionsMatrixResponse)
def update_role(
    role: str, body: UpdateRolePermissionsRequest, actor: Actor, uow: UoW, clock: Clock
):
    matrix = UpdateRolePermissions(uow, clock).execute(actor, parse_role(role), body.permissions)
    return ser_matrix(matrix)


@router.delete("/roles/{role}", response_model=PermissionsMatrixResponse)
def reset_role(role: str, actor: Actor, uow: UoW, clock: Clock):
    matrix = ResetRolePermissions(uow, clock).execute(actor, parse_role(role))
    return ser_matrix(matrix)
