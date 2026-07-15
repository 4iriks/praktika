import { describe, expect, it } from 'vitest';
import { hasAllPermissions, hasPermission, permissionMatrix } from './permissions';

describe('permission matrix', () => {
  it('USER не имеет editor permissions', () => {
    expect(hasPermission('USER', 'SEARCH_USE')).toBe(true);
    expect(hasPermission('USER', 'EDITOR_ACCESS')).toBe(false);
    expect(hasPermission('USER', 'ADMIN_ACCESS')).toBe(false);
  });

  it('EDITOR наследует все USER permissions', () => {
    expect(hasAllPermissions('EDITOR', permissionMatrix.USER)).toBe(true);
    expect(hasPermission('EDITOR', 'DOCUMENT_METADATA_EDIT')).toBe(true);
    expect(hasPermission('EDITOR', 'USERS_MANAGE')).toBe(false);
  });

  it('ADMIN наследует USER и EDITOR permissions', () => {
    expect(hasAllPermissions('ADMIN', permissionMatrix.USER)).toBe(true);
    expect(hasAllPermissions('ADMIN', permissionMatrix.EDITOR)).toBe(true);
    expect(hasPermission('ADMIN', 'SYSTEM_SETTINGS_MANAGE')).toBe(true);
  });
});
