from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import DB, require_permission
from app.api.pagination import parse_optional_datetime
from app.core.enums import Permission
from app.db.models.identity import User
from app.schemas.management import (
    AdminUserDetailOut,
    AdminUserOut,
    AdminUsersResponse,
    BlockUserRequest,
    ChangeRoleRequest,
)
from app.services.admin_users import (
    block_user,
    change_user_role,
    get_admin_user,
    list_admin_users,
    unblock_user,
)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
UsersAdmin = Annotated[User, Depends(require_permission(Permission.USERS_MANAGE))]


@router.get(
    "",
    response_model=AdminUsersResponse,
    summary="Получить пользователей",
    operation_id="getAdminUsers",
)
async def users(
    db: DB,
    actor: UsersAdmin,
    q: str = "",
    role: str = "ALL",
    status: str = "ALL",
    registered_from: str = "",
    registered_to: str = "",
    sort: str = "created_desc",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> AdminUsersResponse:
    return await list_admin_users(
        db,
        q=q,
        role=role,
        status=status,
        registered_from=parse_optional_datetime(registered_from),
        registered_to=parse_optional_datetime(registered_to),
        sort=sort,
        page=page,
        limit=limit,
    )


@router.get(
    "/{user_id}",
    response_model=AdminUserDetailOut,
    summary="Получить пользователя",
    operation_id="getAdminUser",
)
async def user_detail(user_id: UUID, db: DB, actor: UsersAdmin) -> AdminUserDetailOut:
    return await get_admin_user(db, user_id)


@router.patch(
    "/{user_id}/role",
    response_model=AdminUserOut,
    summary="Изменить роль пользователя",
    operation_id="updateUserRole",
)
async def role(
    user_id: UUID,
    payload: ChangeRoleRequest,
    request: Request,
    db: DB,
    actor: UsersAdmin,
) -> AdminUserOut:
    return await change_user_role(db, request, actor, user_id, payload.role)


@router.post(
    "/{user_id}/block",
    response_model=AdminUserOut,
    summary="Заблокировать пользователя",
    operation_id="blockUser",
)
async def block(
    user_id: UUID,
    payload: BlockUserRequest,
    request: Request,
    db: DB,
    actor: UsersAdmin,
) -> AdminUserOut:
    return await block_user(db, request, actor, user_id, payload.reason)


@router.post(
    "/{user_id}/unblock",
    response_model=AdminUserOut,
    summary="Разблокировать пользователя",
    operation_id="unblockUser",
)
async def unblock(user_id: UUID, request: Request, db: DB, actor: UsersAdmin) -> AdminUserOut:
    return await unblock_user(db, request, actor, user_id)
