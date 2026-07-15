import { useMemo } from 'react';
import type { Permission } from '../../types';
import { hasAllPermissions, hasAnyPermission, hasPermission } from './permissions';
import { useAuth } from './useAuth';

export function usePermissions() {
  const { user } = useAuth();

  return useMemo(
    () => ({
      can: (permission: Permission) => hasPermission(user, permission),
      canAny: (permissions: readonly Permission[]) => hasAnyPermission(user, permissions),
      canAll: (permissions: readonly Permission[]) => hasAllPermissions(user, permissions),
    }),
    [user],
  );
}
