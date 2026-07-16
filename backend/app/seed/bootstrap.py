from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.enums import AccountStatus, Permission, SourceStatus, SourceType, UserRole
from app.core.permissions import PERMISSION_MATRIX
from app.core.security import PasswordService
from app.db.base import utc_now
from app.db.models.identity import Role, User, UserPreference
from app.db.models.operations import PermissionRecord, Source, SystemSetting
from app.db.repositories.users import normalize_email

ROLE_LABELS = {
    UserRole.USER: ("Пользователь", "Пользовательский поиск, профиль и коллекции"),
    UserRole.EDITOR: ("Редактор", "Управление документами и редакторскими заданиями"),
    UserRole.ADMIN: ("Администратор", "Полное управление локальной системой"),
}


async def bootstrap_roles_and_permissions(db: AsyncSession) -> dict[UserRole, Role]:
    permission_records: dict[Permission, PermissionRecord] = {}
    for permission in Permission:
        record = await db.scalar(
            select(PermissionRecord).where(PermissionRecord.code == permission.value)
        )
        if record is None:
            record = PermissionRecord(
                code=permission.value,
                description=f"Разрешение PyAnswer: {permission.value}",
            )
            db.add(record)
            await db.flush()
        permission_records[permission] = record

    roles: dict[UserRole, Role] = {}
    for code, permissions in PERMISSION_MATRIX.items():
        role = await db.scalar(
            select(Role).where(Role.code == code.value).options(selectinload(Role.permissions))
        )
        label, description = ROLE_LABELS[code]
        assigned_permissions = [permission_records[item] for item in sorted(permissions, key=str)]
        if role is None:
            role = Role(
                code=code.value,
                name=label,
                description=description,
                permissions=assigned_permissions,
            )
            db.add(role)
        else:
            role.name = label
            role.description = description
            role.permissions = assigned_permissions
        roles[code] = role
    await db.flush()
    return roles


async def bootstrap_system_records(db: AsyncSession, settings: Settings) -> Source:
    system = await db.get(SystemSetting, 1)
    if system is None:
        db.add(SystemSetting(singleton_id=1))
    source = await db.scalar(select(Source).where(Source.name == "Stack Overflow на русском"))
    if source is None:
        source = Source(
            name="Stack Overflow на русском",
            type=SourceType.STACK_EXCHANGE,
            base_url="https://ru.stackoverflow.com",
            site=settings.stack_exchange_site,
            tag=settings.stack_exchange_tag,
            enabled=True,
            status=SourceStatus.IDLE,
            target_documents=settings.stack_exchange_target_documents,
            max_additional_answers=3,
            page_size=100,
            documents_count=0,
            api_key_configured=False,
        )
        db.add(source)
    await db.flush()
    return source


async def create_bootstrap_admin(
    db: AsyncSession, settings: Settings, roles: dict[UserRole, Role]
) -> User | None:
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return None
    normalized = normalize_email(settings.bootstrap_admin_email)
    existing = await db.scalar(select(User).where(User.normalized_email == normalized))
    if existing is not None:
        return existing
    password_hash = PasswordService.from_settings(settings).hash(settings.bootstrap_admin_password)
    now = utc_now()
    user = User(
        role=roles[UserRole.ADMIN],
        name=settings.bootstrap_admin_name,
        email=settings.bootstrap_admin_email.strip(),
        normalized_email=normalized,
        password_hash=password_hash,
        status=AccountStatus.ACTIVE,
        account_version=1,
        registered_at=now,
        last_active_at=now,
        preferences=UserPreference(),
    )
    db.add(user)
    await db.flush()
    return user


async def bootstrap_all(db: AsyncSession, settings: Settings) -> None:
    roles = await bootstrap_roles_and_permissions(db)
    await bootstrap_system_records(db, settings)
    await create_bootstrap_admin(db, settings, roles)
