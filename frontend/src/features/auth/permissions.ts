import type { Permission, PermissionMap, User, UserRole } from '../../types';

const userPermissions = [
  'SEARCH_USE',
  'RAG_USE',
  'PROFILE_MANAGE',
  'HISTORY_MANAGE',
  'SAVED_MANAGE',
] as const satisfies readonly Permission[];

const editorPermissions = [
  ...userPermissions,
  'EDITOR_ACCESS',
  'MANAGED_DOCUMENTS_VIEW',
  'DOCUMENT_METADATA_EDIT',
  'DOCUMENT_STATUS_CHANGE',
  'DOCUMENT_REINDEX',
  'EDITOR_JOBS_VIEW',
] as const satisfies readonly Permission[];

export const permissionMatrix: PermissionMap = {
  USER: userPermissions,
  EDITOR: editorPermissions,
  ADMIN: [
    ...editorPermissions,
    'ADMIN_ACCESS',
    'USERS_MANAGE',
    'SOURCES_MANAGE',
    'ADMIN_JOBS_MANAGE',
    'AUDIT_VIEW',
    'SYSTEM_VIEW',
    'SYSTEM_SETTINGS_MANAGE',
    'SEARCH_INDEX_VIEW',
    'SEARCH_INDEX_MANAGE',
  ],
};

export const roleLabels: Record<UserRole, string> = {
  USER: 'Пользователь',
  EDITOR: 'Редактор',
  ADMIN: 'Администратор',
};

export function hasPermission(
  subject: Pick<User, 'role' | 'accountStatus'> | UserRole | null | undefined,
  permission: Permission,
): boolean {
  if (!subject) return false;
  const role = typeof subject === 'string' ? subject : subject.role;
  if (typeof subject !== 'string' && subject.accountStatus !== 'ACTIVE') return false;
  return permissionMatrix[role].includes(permission);
}

export function hasAnyPermission(
  subject: Pick<User, 'role' | 'accountStatus'> | UserRole | null | undefined,
  permissions: readonly Permission[],
): boolean {
  return permissions.some((permission) => hasPermission(subject, permission));
}

export function hasAllPermissions(
  subject: Pick<User, 'role' | 'accountStatus'> | UserRole | null | undefined,
  permissions: readonly Permission[],
): boolean {
  return permissions.every((permission) => hasPermission(subject, permission));
}
