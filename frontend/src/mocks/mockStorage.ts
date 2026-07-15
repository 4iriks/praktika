const prefix = 'pyanswer:mock:v1:';
const namespacePrefix = 'pyanswer:mock:';

export const mockStorageKeys = {
  users: prefix + 'users',
  session: prefix + 'session',
} as const;

export const mockUserStorageKeys = {
  history: (userId: string) => prefix + 'user:' + encodeURIComponent(userId) + ':history',
  saved: (userId: string) => prefix + 'user:' + encodeURIComponent(userId) + ':saved',
  feedback: (userId: string) => prefix + 'user:' + encodeURIComponent(userId) + ':feedback',
} as const;

const legacyKeys = [
  'pyanswer.mock.session',
  'pyanswer.mock.saved',
  'pyanswer.mock.feedback',
  prefix + 'history',
  prefix + 'saved',
  prefix + 'feedback',
];

function available(): boolean {
  return typeof window !== 'undefined';
}

export function prepareMockStorage(): void {
  if (!available()) return;
  for (const storage of [window.localStorage, window.sessionStorage]) {
    for (const key of legacyKeys) storage.removeItem(key);
    const unknownKeys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key?.startsWith(namespacePrefix) && !key.startsWith(prefix)) unknownKeys.push(key);
    }
    for (const key of unknownKeys) storage.removeItem(key);
  }
}

export function readUnknown(storage: Storage, key: string): unknown {
  try {
    const raw = storage.getItem(key);
    return raw ? (JSON.parse(raw) as unknown) : null;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

export function writeJson(storage: Storage, key: string, value: unknown): void {
  storage.setItem(key, JSON.stringify(value));
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
      if (key && (key.startsWith(namespacePrefix) || legacyKeys.includes(key))) keys.push(key);
    }
    for (const key of keys) storage.removeItem(key);
  }
}
