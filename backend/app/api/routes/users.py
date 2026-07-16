from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.dependencies import DB, CurrentUser
from app.schemas.auth import UpdateProfileRequest, UserOut, UserStatsOut
from app.services.serializers import user_to_schema
from app.services.user import update_profile, user_stats

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserOut,
    summary="Получить профиль",
    operation_id="getProfile",
)
async def get_profile(user: CurrentUser) -> UserOut:
    return user_to_schema(user)


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Обновить профиль и настройки",
    operation_id="updateCurrentUser",
)
async def patch_profile(
    payload: UpdateProfileRequest, request: Request, db: DB, user: CurrentUser
) -> UserOut:
    return await update_profile(db, request, user, payload)


@router.get(
    "/me/stats",
    response_model=UserStatsOut,
    summary="Получить статистику пользователя",
    operation_id="getUserStats",
)
async def get_stats(db: DB, user: CurrentUser) -> UserStatsOut:
    return await user_stats(db, user)
