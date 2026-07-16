from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.identity import Role, Session, User


async def get_session_by_hash(session: AsyncSession, token_hash: str) -> Session | None:
    result = await session.execute(
        select(Session)
        .where(Session.token_hash == token_hash)
        .options(
            selectinload(Session.user).selectinload(User.role).selectinload(Role.permissions),
            selectinload(Session.user).selectinload(User.preferences),
        )
    )
    return result.scalar_one_or_none()


async def revoke_user_sessions(
    session: AsyncSession, user_id: object, revoked_at: datetime
) -> None:
    records = (
        await session.scalars(
            select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        )
    ).all()
    for record in records:
        record.revoked_at = revoked_at
