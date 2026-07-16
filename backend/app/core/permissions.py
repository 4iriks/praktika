from __future__ import annotations

from app.core.enums import Permission, UserRole

USER_PERMISSIONS = frozenset(
    {
        Permission.SEARCH_USE,
        Permission.RAG_USE,
        Permission.PROFILE_MANAGE,
        Permission.HISTORY_MANAGE,
        Permission.SAVED_MANAGE,
    }
)
EDITOR_PERMISSIONS = USER_PERMISSIONS | {
    Permission.EDITOR_ACCESS,
    Permission.MANAGED_DOCUMENTS_VIEW,
    Permission.DOCUMENT_METADATA_EDIT,
    Permission.DOCUMENT_STATUS_CHANGE,
    Permission.DOCUMENT_REINDEX,
    Permission.EDITOR_JOBS_VIEW,
}
PERMISSION_MATRIX: dict[UserRole, frozenset[Permission]] = {
    UserRole.USER: USER_PERMISSIONS,
    UserRole.EDITOR: frozenset(EDITOR_PERMISSIONS),
    UserRole.ADMIN: frozenset(
        EDITOR_PERMISSIONS
        | {
            Permission.ADMIN_ACCESS,
            Permission.USERS_MANAGE,
            Permission.SOURCES_MANAGE,
            Permission.ADMIN_JOBS_MANAGE,
            Permission.AUDIT_VIEW,
            Permission.SYSTEM_VIEW,
            Permission.SYSTEM_SETTINGS_MANAGE,
            Permission.SEARCH_INDEX_VIEW,
            Permission.SEARCH_INDEX_MANAGE,
        }
    ),
}


def has_permission(role: UserRole | str, permission: Permission) -> bool:
    try:
        normalized = UserRole(role)
    except ValueError:
        return False
    return permission in PERMISSION_MATRIX[normalized]


def has_any_permission(role: UserRole | str, permissions: set[Permission]) -> bool:
    return any(has_permission(role, permission) for permission in permissions)


def has_all_permissions(role: UserRole | str, permissions: set[Permission]) -> bool:
    return all(has_permission(role, permission) for permission in permissions)
