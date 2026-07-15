import { ApiError } from '../api/ApiError';
import type {
  AccountStatus,
  AdminUser,
  AdminUserDetail,
  AdminUserFilters,
  AdminUsersResponse,
  AuthSession,
  BlockUserRequest,
  ChangeRoleRequest,
  Feedback,
  FeedbackRequest,
  HistoryFilters,
  HistoryResponse,
  RegisterRequest,
  SearchFilters,
  SearchHistoryItem,
  SearchMode,
  SearchSort,
  SearchView,
  UpdateProfileRequest,
  User,
  UserRole,
  UserPreferences,
  UserStats,
} from '../types';
import type { Permission } from '../types';
import { hasPermission } from '../features/auth/permissions';
import { emailPattern, isStrongPassword, normalizeEmail } from '../utils/validation';
import { appendAudit, readAuditEvents } from './mockAudit';
import {
  clearMockStorage,
  mockStorageKeys,
  mockUserStorageKeys,
  prepareMockStorage,
  readArray,
  readUnknown,
  writeJson,
} from './mockStorage';

interface MockCredentialRecord {
  user: User;
  salt: string;
  digest: string;
}

interface MockSavedRecord {
  documentId: string;
  savedAt: string;
}

export interface HistoryRecordInput {
  query: string;
  view: SearchView;
  mode: SearchMode;
  filters: Omit<SearchFilters, 'sort'>;
  sort: SearchSort;
  pageSize: number;
  resultCount: number;
  tookMs: number;
  answerPreview?: string;
  insufficientContext?: boolean;
}

export const defaultUserPreferences: UserPreferences = {
  defaultSearchMode: 'hybrid',
  defaultSearchView: 'documents',
  defaultPageSize: 10,
  autoOpenScores: false,
  confirmExternalNavigation: true,
};

const demoUserId = 'user-demo-1';
const demoEmail = 'user@pyanswer.local';

interface SeedAccount {
  id: string;
  email: string;
  displayName: string;
  role: UserRole;
  accountStatus: AccountStatus;
  createdAt: string;
  lastActiveAt: string;
}

const seedAccounts: SeedAccount[] = [
  {
    id: demoUserId,
    email: demoEmail,
    displayName: 'Demo User',
    role: 'USER',
    accountStatus: 'ACTIVE',
    createdAt: '2025-01-15T10:00:00.000Z',
    lastActiveAt: '2026-07-15T08:40:00.000Z',
  },
  {
    id: 'user-demo-editor',
    email: 'editor@pyanswer.local',
    displayName: 'Елена Редактор',
    role: 'EDITOR',
    accountStatus: 'ACTIVE',
    createdAt: '2025-02-04T11:30:00.000Z',
    lastActiveAt: '2026-07-15T08:32:00.000Z',
  },
  {
    id: 'user-demo-admin',
    email: 'admin@pyanswer.local',
    displayName: 'Алексей Администратор',
    role: 'ADMIN',
    accountStatus: 'ACTIVE',
    createdAt: '2025-01-03T09:00:00.000Z',
    lastActiveAt: '2026-07-15T08:55:00.000Z',
  },
  ...[
    ['user-seed-01', 'Анна Петрова', 'anna@pyanswer.local', 'USER', 'ACTIVE'],
    ['user-seed-02', 'Максим Волков', 'maxim@pyanswer.local', 'USER', 'ACTIVE'],
    ['user-seed-03', 'Дарья Орлова', 'daria@pyanswer.local', 'EDITOR', 'ACTIVE'],
    ['user-seed-04', 'Илья Морозов', 'ilya@pyanswer.local', 'USER', 'BLOCKED'],
    ['user-seed-05', 'Ольга Соколова', 'olga@pyanswer.local', 'USER', 'ACTIVE'],
    ['user-seed-06', 'Никита Смирнов', 'nikita@pyanswer.local', 'EDITOR', 'BLOCKED'],
    ['user-seed-07', 'Мария Лебедева', 'maria@pyanswer.local', 'USER', 'ACTIVE'],
    ['user-seed-08', 'Павел Кузнецов', 'pavel@pyanswer.local', 'ADMIN', 'ACTIVE'],
    ['user-seed-09', 'Вера Попова', 'vera@pyanswer.local', 'USER', 'BLOCKED'],
    ['user-seed-10', 'Роман Новиков', 'roman@pyanswer.local', 'USER', 'ACTIVE'],
  ].map(([id, displayName, email, role, accountStatus], index) => ({
    id: id ?? '',
    displayName: displayName ?? '',
    email: email ?? '',
    role: (role ?? 'USER') as UserRole,
    accountStatus: (accountStatus ?? 'ACTIVE') as AccountStatus,
    createdAt: new Date(Date.UTC(2025, 3 + (index % 8), 2 + index, 10)).toISOString(),
    lastActiveAt: new Date(Date.UTC(2026, 6, 14 - (index % 7), 8 + (index % 5))).toISOString(),
  })),
];

function now(): string {
  return new Date().toISOString();
}

function makeId(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return prefix + '-' + random;
}

function isPreferences(value: unknown): value is UserPreferences {
  return (
    typeof value === 'object' &&
    value !== null &&
    'defaultSearchMode' in value &&
    ['bm25', 'vector', 'hybrid'].includes(String(value.defaultSearchMode)) &&
    'defaultSearchView' in value &&
    ['documents', 'answer'].includes(String(value.defaultSearchView)) &&
    'defaultPageSize' in value &&
    [10, 20, 50].includes(Number(value.defaultPageSize)) &&
    'autoOpenScores' in value &&
    typeof value.autoOpenScores === 'boolean' &&
    'confirmExternalNavigation' in value &&
    typeof value.confirmExternalNavigation === 'boolean'
  );
}

function toUser(value: unknown): User | null {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('id' in value) ||
    typeof value.id !== 'string' ||
    !('email' in value) ||
    typeof value.email !== 'string' ||
    !('displayName' in value) ||
    typeof value.displayName !== 'string' ||
    !('createdAt' in value) ||
    typeof value.createdAt !== 'string' ||
    !('lastActiveAt' in value) ||
    typeof value.lastActiveAt !== 'string'
  ) {
    return null;
  }
  const role =
    'role' in value && ['USER', 'EDITOR', 'ADMIN'].includes(String(value.role))
      ? (value.role as UserRole)
      : 'USER';
  const accountStatus =
    'accountStatus' in value && ['ACTIVE', 'BLOCKED'].includes(String(value.accountStatus))
      ? (value.accountStatus as AccountStatus)
      : 'ACTIVE';
  const preferences =
    'preferences' in value && isPreferences(value.preferences)
      ? value.preferences
      : defaultUserPreferences;
  const accountVersion =
    'accountVersion' in value &&
    typeof value.accountVersion === 'number' &&
    Number.isInteger(value.accountVersion) &&
    value.accountVersion > 0
      ? value.accountVersion
      : 1;

  return {
    id: value.id,
    email: normalizeEmail(value.email),
    displayName: value.displayName,
    role,
    accountStatus,
    createdAt: value.createdAt,
    lastActiveAt: value.lastActiveAt,
    accountVersion,
    preferences: { ...preferences },
  };
}

function toCredential(value: unknown): MockCredentialRecord | null {
  if (
    typeof value !== 'object' ||
    value === null ||
    !('user' in value) ||
    !('salt' in value) ||
    typeof value.salt !== 'string' ||
    !('digest' in value) ||
    typeof value.digest !== 'string'
  ) {
    return null;
  }
  const user = toUser(value.user);
  return user ? { user, salt: value.salt, digest: value.digest } : null;
}

function isSavedRecord(value: unknown): value is MockSavedRecord {
  return (
    typeof value === 'object' &&
    value !== null &&
    'documentId' in value &&
    typeof value.documentId === 'string' &&
    'savedAt' in value &&
    typeof value.savedAt === 'string'
  );
}

function isHistoryFilters(value: unknown): value is Omit<SearchFilters, 'sort'> {
  return (
    typeof value === 'object' &&
    value !== null &&
    'tags' in value &&
    Array.isArray(value.tags) &&
    value.tags.every((tag) => typeof tag === 'string') &&
    'minScore' in value &&
    typeof value.minScore === 'number' &&
    'acceptedOnly' in value &&
    typeof value.acceptedOnly === 'boolean' &&
    'hasCodeOnly' in value &&
    typeof value.hasCodeOnly === 'boolean'
  );
}

function isHistoryItem(value: unknown): value is SearchHistoryItem {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'userId' in value &&
    typeof value.userId === 'string' &&
    'query' in value &&
    typeof value.query === 'string' &&
    'view' in value &&
    ['documents', 'answer'].includes(String(value.view)) &&
    'mode' in value &&
    ['bm25', 'vector', 'hybrid'].includes(String(value.mode)) &&
    'filters' in value &&
    isHistoryFilters(value.filters) &&
    'sort' in value &&
    ['relevance', 'date', 'score'].includes(String(value.sort)) &&
    'pageSize' in value &&
    typeof value.pageSize === 'number' &&
    'resultCount' in value &&
    typeof value.resultCount === 'number' &&
    'tookMs' in value &&
    typeof value.tookMs === 'number' &&
    'createdAt' in value &&
    typeof value.createdAt === 'string' &&
    (!('answerPreview' in value) || typeof value.answerPreview === 'string') &&
    (!('insufficientContext' in value) || typeof value.insufficientContext === 'boolean')
  );
}

function isFeedback(value: unknown): value is Feedback {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'userId' in value &&
    typeof value.userId === 'string' &&
    'responseId' in value &&
    typeof value.responseId === 'string' &&
    'value' in value &&
    ['positive', 'negative'].includes(String(value.value)) &&
    'question' in value &&
    typeof value.question === 'string' &&
    'createdAt' in value &&
    typeof value.createdAt === 'string' &&
    'updatedAt' in value &&
    typeof value.updatedAt === 'string' &&
    (!('reason' in value) ||
      ['irrelevant_sources', 'factual_error', 'incomplete', 'unclear', 'other'].includes(
        String(value.reason),
      )) &&
    (!('comment' in value) || typeof value.comment === 'string')
  );
}

function users(): MockCredentialRecord[] {
  prepareMockStorage();
  const value = readUnknown(window.localStorage, mockStorageKeys.users);
  if (value === null) return [];
  if (!Array.isArray(value)) {
    window.localStorage.removeItem(mockStorageKeys.users);
    return [];
  }
  const records = value
    .map(toCredential)
    .filter((record): record is MockCredentialRecord => Boolean(record));
  if (records.length !== value.length || records.some((record, index) => record !== value[index])) {
    saveUsers(records);
  }
  return records;
}

function saveUsers(records: MockCredentialRecord[]): void {
  writeJson(window.localStorage, mockStorageKeys.users, records);
}

function bytesToHex(bytes: Uint8Array): string {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function createSalt(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto?.getRandomValues?.(bytes);
  if (bytes.every((value) => value === 0)) {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  return bytesToHex(bytes);
}

async function passwordDigest(password: string, salt: string): Promise<string> {
  const value = new TextEncoder().encode(salt + ':' + password);
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest('SHA-256', value);
    return bytesToHex(new Uint8Array(digest));
  }
  let hash = 2_166_136_261;
  for (const byte of value) {
    hash ^= byte;
    hash = Math.imul(hash, 16_777_619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

async function ensureSeedUsers(): Promise<void> {
  const records = users();
  let changed = false;
  for (const seed of seedAccounts) {
    if (
      records.some(
        (record) =>
          record.user.id === seed.id ||
          normalizeEmail(record.user.email) === normalizeEmail(seed.email),
      )
    ) {
      continue;
    }
    const salt = createSalt();
    records.push({
      user: {
        ...seed,
        accountVersion: 1,
        preferences: { ...defaultUserPreferences },
      },
      salt,
      digest: await passwordDigest('Demo123!', salt),
    });
    changed = true;
  }
  if (changed) saveUsers(records);
  seedSyntheticUserData();
}

function seedSyntheticUserData(): void {
  seedAccounts.slice(3).forEach((account, index) => {
    const historyKey = mockUserStorageKeys.history(account.id);
    if (window.localStorage.getItem(historyKey) === null) {
      const items: SearchHistoryItem[] = Array.from({ length: index % 5 }, (_, itemIndex) => ({
        id: `history-seed-${index}-${itemIndex}`,
        userId: account.id,
        query:
          ['asyncio task', 'pandas csv', 'FastAPI Depends', 'pytest fixture'][itemIndex % 4] ??
          'python',
        view: itemIndex % 2 === 0 ? 'documents' : 'answer',
        mode: itemIndex % 3 === 0 ? 'hybrid' : itemIndex % 3 === 1 ? 'bm25' : 'vector',
        filters: { tags: [], minScore: 0, acceptedOnly: false, hasCodeOnly: false },
        sort: 'relevance',
        pageSize: 10,
        resultCount: 4 + itemIndex,
        tookMs: 64 + itemIndex * 120,
        createdAt: new Date(Date.UTC(2026, 6, 14 - itemIndex, 9, index)).toISOString(),
        answerPreview:
          itemIndex % 2
            ? 'Синтетический preview ответа для административной статистики.'
            : undefined,
      }));
      writeJson(window.localStorage, historyKey, items);
    }
    const savedKey = mockUserStorageKeys.saved(account.id);
    if (window.localStorage.getItem(savedKey) === null) {
      const items: MockSavedRecord[] = Array.from({ length: index % 4 }, (_, itemIndex) => ({
        documentId: `py-${String(1001 + itemIndex).padStart(4, '0')}`,
        savedAt: new Date(Date.UTC(2026, 6, 10 + itemIndex, 12)).toISOString(),
      }));
      writeJson(window.localStorage, savedKey, items);
    }
    const feedbackKey = mockUserStorageKeys.feedback(account.id);
    if (window.localStorage.getItem(feedbackKey) === null) {
      const items: Feedback[] = Array.from({ length: index % 3 }, (_, itemIndex) => ({
        id: `feedback-seed-${index}-${itemIndex}`,
        userId: account.id,
        responseId: `rag-seed-${index}-${itemIndex}`,
        value: itemIndex % 2 === 0 ? 'positive' : 'negative',
        question: 'Синтетический вопрос',
        createdAt: new Date(Date.UTC(2026, 6, 12, 10, itemIndex)).toISOString(),
        updatedAt: new Date(Date.UTC(2026, 6, 12, 10, itemIndex)).toISOString(),
      }));
      writeJson(window.localStorage, feedbackKey, items);
    }
  });
}

function isSession(value: unknown): value is AuthSession {
  return (
    typeof value === 'object' &&
    value !== null &&
    'userId' in value &&
    typeof value.userId === 'string' &&
    'expiresAt' in value &&
    typeof value.expiresAt === 'string' &&
    'mockSessionVersion' in value &&
    typeof value.mockSessionVersion === 'number'
  );
}

function readSessionFrom(storage: Storage): AuthSession | null {
  const value = readUnknown(storage, mockStorageKeys.session);
  if (!isSession(value) || Date.parse(value.expiresAt) <= Date.now()) {
    storage.removeItem(mockStorageKeys.session);
    return null;
  }
  return value;
}

function currentSession(): AuthSession | null {
  prepareMockStorage();
  return readSessionFrom(window.sessionStorage) ?? readSessionFrom(window.localStorage);
}

function activeRecord(): MockCredentialRecord | null {
  const session = currentSession();
  if (!session) return null;
  const record = users().find((item) => item.user.id === session.userId);
  if (
    !record ||
    record.user.accountStatus !== 'ACTIVE' ||
    record.user.accountVersion !== session.mockSessionVersion
  ) {
    logout();
    return null;
  }
  return record;
}

function requireUser(): User {
  const record = activeRecord();
  if (!record) throw new ApiError('Для этого действия необходимо войти.', 401, 'UNAUTHORIZED');
  return record.user;
}

function requireUserId(): string {
  return requireUser().id;
}

function requirePermission(permission: Permission): User {
  const user = requireUser();
  if (!hasPermission(user, permission)) {
    throw new ApiError('Недостаточно прав для выполнения действия.', 403, 'FORBIDDEN');
  }
  return user;
}

function createSession(user: User, remember: boolean): void {
  window.localStorage.removeItem(mockStorageKeys.session);
  window.sessionStorage.removeItem(mockStorageKeys.session);
  const expiresInMs = remember ? 30 * 24 * 60 * 60 * 1000 : 12 * 60 * 60 * 1000;
  const session: AuthSession = {
    userId: user.id,
    expiresAt: new Date(Date.now() + expiresInMs).toISOString(),
    mockSessionVersion: user.accountVersion,
  };
  writeJson(
    remember ? window.localStorage : window.sessionStorage,
    mockStorageKeys.session,
    session,
  );
}

function touchUser(record: MockCredentialRecord, records: MockCredentialRecord[]): User {
  const touched = { ...record.user, lastActiveAt: now() };
  const index = records.findIndex((item) => item.user.id === record.user.id);
  if (index >= 0) records[index] = { ...record, user: touched };
  saveUsers(records);
  return touched;
}

async function register(request: RegisterRequest): Promise<User> {
  await ensureSeedUsers();
  const email = normalizeEmail(request.email);
  const displayName = request.displayName.trim();
  if (displayName.length < 2) throw new ApiError('Имя должно содержать минимум 2 символа.', 422);
  if (!emailPattern.test(email)) throw new ApiError('Укажите корректный email.', 422);
  if (!isStrongPassword(request.password))
    throw new ApiError('Пароль не соответствует требованиям.', 422);
  if (!request.acceptedTerms) throw new ApiError('Необходимо принять правила использования.', 422);
  const records = users();
  if (records.some((record) => normalizeEmail(record.user.email) === email)) {
    throw new ApiError('Пользователь с таким email уже существует.', 409);
  }
  const createdAt = now();
  const salt = createSalt();
  const user: User = {
    id: makeId('user'),
    displayName,
    email,
    role: 'USER',
    accountStatus: 'ACTIVE',
    createdAt,
    lastActiveAt: createdAt,
    accountVersion: 1,
    preferences: { ...defaultUserPreferences },
  };
  records.push({ user, salt, digest: await passwordDigest(request.password, salt) });
  saveUsers(records);
  createSession(user, request.remember);
  appendAudit({
    actor: user,
    action: 'REGISTER',
    entityType: 'USER',
    entityId: user.id,
    entityLabel: user.email,
    summary: 'Создана пользовательская учётная запись',
    after: { role: user.role, accountStatus: user.accountStatus },
  });
  return user;
}

async function login(request: {
  email: string;
  password: string;
  remember: boolean;
}): Promise<User> {
  await ensureSeedUsers();
  const records = users();
  const record = records.find(
    (item) => normalizeEmail(item.user.email) === normalizeEmail(request.email),
  );
  if (!record || (await passwordDigest(request.password, record.salt)) !== record.digest) {
    throw new ApiError('Неверный email или пароль.', 401);
  }
  if (record.user.accountStatus === 'BLOCKED') {
    throw new ApiError('Учётная запись заблокирована.', 403);
  }
  const user = touchUser(record, records);
  createSession(user, request.remember);
  appendAudit({
    actor: user,
    action: 'LOGIN',
    entityType: 'AUTH',
    entityId: user.id,
    entityLabel: user.email,
    summary: 'Выполнен вход в демонстрационную сессию',
  });
  return user;
}

async function getCurrentUser(): Promise<User | null> {
  await ensureSeedUsers();
  const record = activeRecord();
  if (!record) return null;
  const records = users();
  const stored = records.find((item) => item.user.id === record.user.id);
  return stored ? touchUser(stored, records) : null;
}

function logout(): void {
  prepareMockStorage();
  const session = readSessionFrom(window.sessionStorage) ?? readSessionFrom(window.localStorage);
  const actor = session ? users().find((item) => item.user.id === session.userId)?.user : undefined;
  window.localStorage.removeItem(mockStorageKeys.session);
  window.sessionStorage.removeItem(mockStorageKeys.session);
  if (actor) {
    appendAudit({
      actor,
      action: 'LOGOUT',
      entityType: 'AUTH',
      entityId: actor.id,
      entityLabel: actor.email,
      summary: 'Завершена демонстрационная сессия',
    });
  }
}

function updateCurrentUser(request: UpdateProfileRequest): User {
  const userId = requireUserId();
  const records = users();
  const index = records.findIndex((record) => record.user.id === userId);
  const record = records[index];
  if (!record) throw new ApiError('Пользователь не найден.', 404);
  const displayName = request.displayName?.trim() ?? record.user.displayName;
  const email = request.email ? normalizeEmail(request.email) : record.user.email;
  if (displayName.length < 2) throw new ApiError('Имя должно содержать минимум 2 символа.', 422);
  if (!emailPattern.test(email)) throw new ApiError('Укажите корректный email.', 422);
  if (
    records.some((item) => item.user.id !== userId && normalizeEmail(item.user.email) === email)
  ) {
    throw new ApiError('Пользователь с таким email уже существует.', 409);
  }
  const user: User = {
    ...record.user,
    displayName,
    email,
    lastActiveAt: now(),
    preferences: request.preferences ? { ...request.preferences } : { ...record.user.preferences },
  };
  records[index] = { ...record, user };
  saveUsers(records);
  appendAudit({
    actor: user,
    action: 'UPDATE_PROFILE',
    entityType: 'USER',
    entityId: user.id,
    entityLabel: user.email,
    summary: 'Обновлён пользовательский профиль',
    before: { displayName: record.user.displayName, email: record.user.email },
    after: { displayName: user.displayName, email: user.email },
  });
  return user;
}

function savedRecords(userId: string): MockSavedRecord[] {
  return readArray(window.localStorage, mockUserStorageKeys.saved(userId), isSavedRecord);
}

function getSavedEntries(): Array<{ documentId: string; savedAt: string }> {
  const userId = requireUserId();
  return savedRecords(userId).map(({ documentId, savedAt }) => ({ documentId, savedAt }));
}

function getSavedDocumentIds(): Set<string> {
  const session = currentSession();
  if (!session) return new Set<string>();
  return new Set(savedRecords(session.userId).map((record) => record.documentId));
}

function saveDocument(documentId: string): { documentId: string; savedAt: string } {
  const userId = requireUserId();
  const records = savedRecords(userId);
  const existing = records.find((record) => record.documentId === documentId);
  if (existing) return { documentId: existing.documentId, savedAt: existing.savedAt };
  const record = { documentId, savedAt: now() };
  records.push(record);
  writeJson(window.localStorage, mockUserStorageKeys.saved(userId), records);
  return { documentId, savedAt: record.savedAt };
}

function unsaveDocument(documentId: string): void {
  const userId = requireUserId();
  const records = savedRecords(userId);
  writeJson(
    window.localStorage,
    mockUserStorageKeys.saved(userId),
    records.filter((record) => record.documentId !== documentId),
  );
}

function historyRecords(userId: string): SearchHistoryItem[] {
  return readArray(window.localStorage, mockUserStorageKeys.history(userId), isHistoryItem).filter(
    (item) => item.userId === userId,
  );
}

function getHistoryForAdmin(userId: string): SearchHistoryItem[] {
  requirePermission('USERS_MANAGE');
  return historyRecords(userId);
}

function historyFingerprint(value: HistoryRecordInput | SearchHistoryItem): string {
  return JSON.stringify({
    query: value.query.trim().toLocaleLowerCase('ru-RU'),
    view: value.view,
    mode: value.mode,
    filters: value.filters,
    sort: value.sort,
    pageSize: value.pageSize,
  });
}

function recordHistory(input: HistoryRecordInput): SearchHistoryItem | null {
  const session = currentSession();
  if (!session || !input.query.trim()) return null;
  const records = historyRecords(session.userId);
  const latest = records.sort(
    (left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt),
  )[0];
  if (
    latest &&
    Date.now() - Date.parse(latest.createdAt) < 5_000 &&
    historyFingerprint(latest) === historyFingerprint(input)
  ) {
    return latest;
  }
  const item: SearchHistoryItem = {
    ...input,
    id: makeId('history'),
    userId: session.userId,
    createdAt: now(),
  };
  records.push(item);
  writeJson(window.localStorage, mockUserStorageKeys.history(session.userId), records);
  return item;
}

function getHistory(filters: HistoryFilters): HistoryResponse {
  const userId = requireUserId();
  const search = filters.search.trim().toLocaleLowerCase('ru-RU');
  const items = historyRecords(userId)
    .filter((item) => !search || item.query.toLocaleLowerCase('ru-RU').includes(search))
    .filter((item) => filters.view === 'all' || item.view === filters.view)
    .filter((item) => filters.mode === 'all' || item.mode === filters.mode)
    .sort((left, right) =>
      filters.dateSort === 'newest'
        ? Date.parse(right.createdAt) - Date.parse(left.createdAt)
        : Date.parse(left.createdAt) - Date.parse(right.createdAt),
    );
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / filters.pageSize));
  const offset = (filters.page - 1) * filters.pageSize;
  return {
    items: items.slice(offset, offset + filters.pageSize),
    pagination: { page: filters.page, pageSize: filters.pageSize, total, totalPages },
  };
}

function deleteHistoryItem(historyId: string): void {
  const userId = requireUserId();
  writeJson(
    window.localStorage,
    mockUserStorageKeys.history(userId),
    historyRecords(userId).filter((item) => item.id !== historyId),
  );
}

function clearHistory(): void {
  const userId = requireUserId();
  window.localStorage.removeItem(mockUserStorageKeys.history(userId));
}

function feedbackRecords(userId: string): Feedback[] {
  return readArray(window.localStorage, mockUserStorageKeys.feedback(userId), isFeedback).filter(
    (item) => item.userId === userId,
  );
}

function sendFeedback(request: FeedbackRequest): Feedback {
  const userId = requireUserId();
  const records = feedbackRecords(userId);
  const index = records.findIndex((item) => item.responseId === request.responseId);
  const existing = records[index];
  const timestamp = now();
  const feedback: Feedback = {
    id: existing?.id ?? makeId('feedback'),
    userId,
    responseId: request.responseId,
    value: request.value,
    question: request.question,
    createdAt: existing?.createdAt ?? timestamp,
    updatedAt: timestamp,
    ...(request.reason ? { reason: request.reason } : {}),
    ...(request.comment?.trim() ? { comment: request.comment.trim().slice(0, 500) } : {}),
  };
  if (index >= 0) records[index] = feedback;
  else records.push(feedback);
  writeJson(window.localStorage, mockUserStorageKeys.feedback(userId), records);
  return feedback;
}

function getFeedbackForResponse(responseId: string): Feedback | null {
  const userId = requireUserId();
  return feedbackRecords(userId).find((item) => item.responseId === responseId) ?? null;
}

function deleteFeedback(feedbackId: string): void {
  const userId = requireUserId();
  writeJson(
    window.localStorage,
    mockUserStorageKeys.feedback(userId),
    feedbackRecords(userId).filter((item) => item.id !== feedbackId),
  );
}

function getUserStats(): UserStats {
  const userId = requireUserId();
  const history = historyRecords(userId);
  return {
    documentSearches: history.filter((item) => item.view === 'documents').length,
    ragSearches: history.filter((item) => item.view === 'answer').length,
    savedDocuments: savedRecords(userId).length,
    ratedAnswers: feedbackRecords(userId).length,
  };
}

function statsForUser(userId: string): UserStats {
  const history = historyRecords(userId);
  return {
    documentSearches: history.filter((item) => item.view === 'documents').length,
    ragSearches: history.filter((item) => item.view === 'answer').length,
    savedDocuments: savedRecords(userId).length,
    ratedAnswers: feedbackRecords(userId).length,
  };
}

function toAdminUser(record: MockCredentialRecord): AdminUser {
  return { ...record.user, stats: statsForUser(record.user.id) };
}

function getAdminUsers(filters: AdminUserFilters): AdminUsersResponse {
  requirePermission('USERS_MANAGE');
  const search = filters.q.trim().toLocaleLowerCase('ru-RU');
  const filtered = users()
    .map(toAdminUser)
    .filter(
      (user) =>
        !search ||
        user.displayName.toLocaleLowerCase('ru-RU').includes(search) ||
        user.email.toLocaleLowerCase('ru-RU').includes(search),
    )
    .filter((user) => filters.role === 'ALL' || user.role === filters.role)
    .filter((user) => filters.status === 'ALL' || user.accountStatus === filters.status)
    .filter((user) => !filters.registeredFrom || user.createdAt >= filters.registeredFrom)
    .filter((user) => !filters.registeredTo || user.createdAt <= filters.registeredTo)
    .sort((left, right) => {
      if (filters.sort === 'created_asc') return left.createdAt.localeCompare(right.createdAt);
      if (filters.sort === 'activity_desc') {
        return right.lastActiveAt.localeCompare(left.lastActiveAt);
      }
      if (filters.sort === 'name_asc')
        return left.displayName.localeCompare(right.displayName, 'ru');
      return right.createdAt.localeCompare(left.createdAt);
    });
  const total = filtered.length;
  const totalPages = Math.max(1, Math.ceil(total / filters.limit));
  const offset = (filters.page - 1) * filters.limit;
  return {
    items: filtered.slice(offset, offset + filters.limit),
    pagination: { page: filters.page, pageSize: filters.limit, total, totalPages },
  };
}

function getAdminUser(userId: string): AdminUserDetail {
  requirePermission('USERS_MANAGE');
  const record = users().find((item) => item.user.id === userId);
  if (!record) throw new ApiError('Пользователь не найден.', 404, 'NOT_FOUND');
  return {
    ...toAdminUser(record),
    recentHistory: historyRecords(userId)
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
      .slice(0, 5),
    recentAuditEvents: readAuditEvents()
      .filter((event) => event.entityType === 'USER' && event.entityId === userId)
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
      .slice(0, 8),
  };
}

function activeAdminCount(records: MockCredentialRecord[]): number {
  return records.filter(
    (record) => record.user.role === 'ADMIN' && record.user.accountStatus === 'ACTIVE',
  ).length;
}

function updateUserRole(userId: string, request: ChangeRoleRequest): AdminUser {
  const actor = requirePermission('USERS_MANAGE');
  if (!['USER', 'EDITOR', 'ADMIN'].includes(request.role)) {
    throw new ApiError('Неизвестная роль.', 422, 'VALIDATION_ERROR');
  }
  const records = users();
  const index = records.findIndex((record) => record.user.id === userId);
  const record = records[index];
  if (!record) throw new ApiError('Пользователь не найден.', 404, 'NOT_FOUND');
  if (
    record.user.role === 'ADMIN' &&
    record.user.accountStatus === 'ACTIVE' &&
    request.role !== 'ADMIN' &&
    activeAdminCount(records) <= 1
  ) {
    throw new ApiError('В системе должен оставаться активный администратор.', 409, 'CONFLICT');
  }
  if (actor.id === userId) {
    throw new ApiError('Нельзя изменить собственную роль.', 409, 'CONFLICT');
  }
  if (record.user.role === request.role) return toAdminUser(record);
  const updated: User = {
    ...record.user,
    role: request.role,
    accountVersion: record.user.accountVersion + 1,
    lastActiveAt: now(),
  };
  records[index] = { ...record, user: updated };
  saveUsers(records);
  appendAudit({
    actor,
    action: 'CHANGE_USER_ROLE',
    entityType: 'USER',
    entityId: updated.id,
    entityLabel: updated.email,
    summary: `Роль изменена: ${record.user.role} → ${updated.role}`,
    before: { role: record.user.role, accountVersion: record.user.accountVersion },
    after: { role: updated.role, accountVersion: updated.accountVersion },
  });
  return toAdminUser(records[index]);
}

function blockUser(userId: string, request: BlockUserRequest): AdminUser {
  const actor = requirePermission('USERS_MANAGE');
  const reason = request.reason.trim();
  if (reason.length < 3) {
    throw new ApiError('Укажите причину блокировки.', 422, 'VALIDATION_ERROR');
  }
  const records = users();
  const index = records.findIndex((record) => record.user.id === userId);
  const record = records[index];
  if (!record) throw new ApiError('Пользователь не найден.', 404, 'NOT_FOUND');
  if (record.user.accountStatus === 'BLOCKED') return toAdminUser(record);
  if (record.user.role === 'ADMIN' && activeAdminCount(records) <= 1) {
    throw new ApiError(
      'Нельзя заблокировать последнего активного администратора.',
      409,
      'CONFLICT',
    );
  }
  if (actor.id === userId) throw new ApiError('Нельзя заблокировать себя.', 409, 'CONFLICT');
  const updated: User = {
    ...record.user,
    accountStatus: 'BLOCKED',
    accountVersion: record.user.accountVersion + 1,
  };
  records[index] = { ...record, user: updated };
  saveUsers(records);
  appendAudit({
    actor,
    action: 'BLOCK_USER',
    entityType: 'USER',
    entityId: updated.id,
    entityLabel: updated.email,
    summary: 'Учётная запись заблокирована',
    before: { accountStatus: record.user.accountStatus },
    after: { accountStatus: updated.accountStatus },
    metadata: { reason: reason.slice(0, 300) },
  });
  return toAdminUser(records[index]);
}

function unblockUser(userId: string): AdminUser {
  const actor = requirePermission('USERS_MANAGE');
  const records = users();
  const index = records.findIndex((record) => record.user.id === userId);
  const record = records[index];
  if (!record) throw new ApiError('Пользователь не найден.', 404, 'NOT_FOUND');
  if (record.user.accountStatus === 'ACTIVE') return toAdminUser(record);
  const updated: User = {
    ...record.user,
    accountStatus: 'ACTIVE',
    accountVersion: record.user.accountVersion + 1,
  };
  records[index] = { ...record, user: updated };
  saveUsers(records);
  appendAudit({
    actor,
    action: 'UNBLOCK_USER',
    entityType: 'USER',
    entityId: updated.id,
    entityLabel: updated.email,
    summary: 'Учётная запись разблокирована',
    before: { accountStatus: record.user.accountStatus },
    after: { accountStatus: updated.accountStatus },
  });
  return toAdminUser(records[index]);
}

async function initialize(): Promise<void> {
  await ensureSeedUsers();
}

export const mockRepository = {
  initialize,
  register,
  login,
  logout,
  getCurrentUser,
  updateCurrentUser,
  getUserStats,
  getHistory,
  recordHistory,
  deleteHistoryItem,
  clearHistory,
  getSavedEntries,
  getSavedDocumentIds,
  saveDocument,
  unsaveDocument,
  sendFeedback,
  deleteFeedback,
  getFeedbackForResponse,
  getAdminUsers,
  getAdminUser,
  getHistoryForAdmin,
  updateUserRole,
  blockUser,
  unblockUser,
  getActor: requireUser,
  getOptionalActor: () => activeRecord()?.user ?? null,
  requirePermission,
  reset: clearMockStorage,
};
