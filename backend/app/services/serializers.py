from __future__ import annotations

import re

from app.core.enums import AccountStatus, Permission, UserRole
from app.db.models.identity import User
from app.schemas.auth import UserOut, UserPreferencesOut

CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def code_blocks(text: str) -> list[str]:
    return [match.strip() for match in CODE_BLOCK_RE.findall(text)]


def user_to_schema(user: User) -> UserOut:
    preferences = user.preferences
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.name,
        role=UserRole(user.role.code),
        account_status=AccountStatus(user.status),
        created_at=user.registered_at,
        last_active_at=user.last_active_at,
        account_version=user.account_version,
        preferences=UserPreferencesOut(
            default_search_mode=preferences.default_search_mode,
            default_search_view=preferences.default_search_view,
            default_page_size=preferences.default_page_size,
            auto_open_scores=preferences.auto_expand_scores,
            confirm_external_navigation=preferences.confirm_external_links,
        ),
        permissions=[Permission(item.code) for item in user.role.permissions],
    )
