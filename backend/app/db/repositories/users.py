from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.identity import Role, User


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def user_statement() -> Select[tuple[User]]:
    return select(User).options(
        selectinload(User.role).selectinload(Role.permissions),
        selectinload(User.preferences),
    )


async def get_user_by_id(
    session: AsyncSession, user_id: UUID, *, lock: bool = False
) -> User | None:
    statement = user_statement().where(User.id == user_id)
    if lock:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(
        user_statement().where(User.normalized_email == normalize_email(email))
    )
    return result.scalar_one_or_none()


async def get_role(session: AsyncSession, code: str) -> Role | None:
    result = await session.execute(
        select(Role).where(Role.code == code).options(selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()
