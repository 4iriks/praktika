const currentSchemaVersion = 2;
const currentPrefix = `pyanswer:mock:v${currentSchemaVersion}:`;
const previousPrefix = 'pyanswer:mock:v1:';
const namespacePrefix = 'pyanswer:mock:';
const schemaVersionKey = namespacePrefix + 'schema-version';

export const mockStorageKeys = {
  schemaVersion: schemaVersionKey,
  users: currentPrefix + 'users',
  session: currentPrefix + 'session',
  managedDocuments: currentPrefix + 'managed-documents',
  jobs: currentPrefix + 'jobs',
  sources: currentPrefix + 'sources',
  audit: currentPrefix + 'audit',
  systemSettings: currentPrefix + 'system-settings',
  systemStatus: currentPrefix + 'system-status',
} as const;

export const stage2StorageKeys = {
  users: previousPrefix + 'users',
  session: previousPrefix + 'session',
  history: (userId: string) => previousPrefix + 'user:' + encodeURIComponent(userId) + ':history',
  saved: (userId: string) => previousPrefix + 'user:' + encodeURIComponent(userId) + ':saved',
  feedback: (userId: string) => previousPrefix + 'user:' + encodeURIComponent(userId) + ':feedback',
} as const;

export const mockUserStorageKeys = {
  history: (userId: string) => currentPrefix + 'user:' + encodeURIComponent(userId) + ':history',
  saved: (userId: string) => currentPrefix + 'user:' + encodeURIComponent(userId) + ':saved',
  feedback: (userId: string) => currentPrefix + 'user:' + encodeURIComponent(userId) + ':feedback',
} as const;

const obsoleteUnversionedKeys = [
  'pyanswer.mock.session',
  'pyanswer.mock.saved',
  'pyanswer.mock.feedback',
  previousPrefix + 'history',
  previousPrefix + 'saved',
  previousPrefix + 'feedback',
];

function available(): boolean {
  return typeof window !== 'undefined';
}

export function readUnknown(storage: Storage, key: string): unknown {
  try {
    const raw = storage.getItem(key);
    return raw ? (JSON.parse(raw) as unknown) : null;
  } catch {
    storage.removeItem(key);
    if (import.meta.env.DEV) console.warn(`PyAnswer: повреждённые mock-данные удалены (${key}).`);
    return null;
  }
}

export function writeJson(storage: Storage, key: string, value: unknown): void {
  storage.setItem(key, JSON.stringify(value));
}

function copyIfMissing(storage: Storage, from: string, to: string): void {
  if (storage.getItem(to) !== null) return;
  const value = readUnknown(storage, from);
  if (value !== null) writeJson(storage, to, value);
}

function migrateUserScopedKeys(storage: Storage): void {
  const keys: string[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key?.startsWith(previousPrefix + 'user:')) keys.push(key);
  }
  for (const key of keys)
    copyIfMissing(storage, key, currentPrefix + key.slice(previousPrefix.length));
}

/**
 * Copies Stage 2 records into the new namespace without deleting the source. The
 * repository validates and enriches those values before completeMockStorageMigration
 * switches the schema marker, so an interrupted migration is safe to repeat.
 */
export function prepareMockStorage(): void {
  if (!available()) return;
  const marker = Number(window.localStorage.getItem(schemaVersionKey) ?? 1);
  if (!Number.isFinite(marker) || marker > currentSchemaVersion || marker < 1) {
    window.localStorage.removeItem(schemaVersionKey);
  }

  copyIfMissing(window.localStorage, stage2StorageKeys.users, mockStorageKeys.users);
  copyIfMissing(window.localStorage, stage2StorageKeys.session, mockStorageKeys.session);
  copyIfMissing(window.sessionStorage, stage2StorageKeys.session, mockStorageKeys.session);
  migrateUserScopedKeys(window.localStorage);
  migrateUserScopedKeys(window.sessionStorage);

  for (const storage of [window.localStorage, window.sessionStorage]) {
    for (const key of obsoleteUnversionedKeys) storage.removeItem(key);
  }
}

export function completeMockStorageMigration(): void {
  if (!available()) return;
  window.localStorage.setItem(schemaVersionKey, String(currentSchemaVersion));
}

export function getMockStorageVersion(): number {
  if (!available()) return currentSchemaVersion;
  return Number(window.localStorage.getItem(schemaVersionKey) ?? 1);
}

export function readArray<T>(
  storage: Storage,
  key: string,
  guard: (value: unknown) => value is T,
): T[] {
  const value = readUnknown(storage, key);
  if (value === null) return [];
  if (!Array.isArray(value)) {
    storage.removeItem(key);
    return [];
  }
  const valid = value.filter(guard);
  if (valid.length !== value.length) writeJson(storage, key, valid);
  return valid;
}

export function clearMockStorage(): void {
  if (!available()) return;
  for (const storage of [window.localStorage, window.sessionStorage]) {
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key && (key.startsWith(namespacePrefix) || obsoleteUnversionedKeys.includes(key))) {
        keys.push(key);
      }
    }
    for (const key of keys) storage.removeItem(key);
  }
}
