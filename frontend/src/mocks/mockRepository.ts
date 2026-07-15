import { ApiError } from '../api/ApiError';
import type {
  AuthSession,
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
  UserPreferences,
  UserStats,
} from '../types';
import { emailPattern, isStrongPassword, normalizeEmail } from '../utils/validation';
import {
  clearMockStorage,
  mockStorageKeys,
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
  userId: string;
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
const sessionVersion = 1;

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

function isUser(value: unknown): value is User {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'email' in value &&
    typeof value.email === 'string' &&
    'displayName' in value &&
    typeof value.displayName === 'string' &&
    'role' in value &&
    ['USER', 'EDITOR', 'ADMIN'].includes(String(value.role)) &&
    'accountStatus' in value &&
    ['ACTIVE', 'BLOCKED'].includes(String(value.accountStatus)) &&
    'createdAt' in value &&
    typeof value.createdAt === 'string' &&
    'lastActiveAt' in value &&
    typeof value.lastActiveAt === 'string' &&
    'preferences' in value &&
    isPreferences(value.preferences)
  );
}

function isCredential(value: unknown): value is MockCredentialRecord {
  return (
    typeof value === 'object' &&
    value !== null &&
    'user' in value &&
    isUser(value.user) &&
    'salt' in value &&
    typeof value.salt === 'string' &&
    'digest' in value &&
    typeof value.digest === 'string'
  );
}

function isSavedRecord(value: unknown): value is MockSavedRecord {
  return (
    typeof value === 'object' &&
    value !== null &&
    'userId' in value &&
    typeof value.userId === 'string' &&
    'documentId' in value &&
    typeof value.documentId === 'string' &&
    'savedAt' in value &&
    typeof value.savedAt === 'string'
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
    'createdAt' in value &&
    typeof value.createdAt === 'string'
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
    ['positive', 'negative'].includes(String(value.value))
  );
}

function users(): MockCredentialRecord[] {
  prepareMockStorage();
  return readArray(window.localStorage, mockStorageKeys.users, isCredential);
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

async function ensureDemoUser(): Promise<void> {
  const records = users();
  if (records.some((record) => record.user.id === demoUserId)) return;
  const createdAt = '2025-01-15T10:00:00.000Z';
  const salt = createSalt();
  records.push({
    user: {
      id: demoUserId,
      email: demoEmail,
      displayName: 'Demo User',
      role: 'USER',
      accountStatus: 'ACTIVE',
      createdAt,
      lastActiveAt: createdAt,
      preferences: { ...defaultUserPreferences },
    },
    salt,
    digest: await passwordDigest('Demo123!', salt),
  });
  saveUsers(records);
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
    value.mockSessionVersion === sessionVersion
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
  return (
    readSessionFrom(window.sessionStorage) ?? readSessionFrom(window.localStorage)
  );
}

function requireUserId(): string {
  const session = currentSession();
  if (!session) throw new ApiError('Для этого действия необходимо войти.', 401);
  return session.userId;
}

function createSession(userId: string, remember: boolean): void {
  window.localStorage.removeItem(mockStorageKeys.session);
  window.sessionStorage.removeItem(mockStorageKeys.session);
  const expiresInMs = remember ? 30 * 24 * 60 * 60 * 1000 : 12 * 60 * 60 * 1000;
  const session: AuthSession = {
    userId,
    expiresAt: new Date(Date.now() + expiresInMs).toISOString(),
    mockSessionVersion: sessionVersion,
  };
  writeJson(remember ? window.localStorage : window.sessionStorage, mockStorageKeys.session, session);
}

function touchUser(record: MockCredentialRecord, records: MockCredentialRecord[]): User {
  const touched = { ...record.user, lastActiveAt: now() };
  const index = records.findIndex((item) => item.user.id === record.user.id);
  if (index >= 0) records[index] = { ...record, user: touched };
  saveUsers(records);
  return touched;
}

async function register(request: RegisterRequest): Promise<User> {
  await ensureDemoUser();
  const email = normalizeEmail(request.email);
  const displayName = request.displayName.trim();
  if (displayName.length < 2) throw new ApiError('Имя должно содержать минимум 2 символа.', 422);
  if (!emailPattern.test(email)) throw new ApiError('Укажите корректный email.', 422);
  if (!isStrongPassword(request.password)) throw new ApiError('Пароль не соответствует требованиям.', 422);
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
    preferences: { ...defaultUserPreferences },
  };
  records.push({ user, salt, digest: await passwordDigest(request.password, salt) });
  saveUsers(records);
  createSession(user.id, request.remember);
  return user;
}

async function login(request: { email: string; password: string; remember: boolean }): Promise<User> {
  await ensureDemoUser();
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
  createSession(record.user.id, request.remember);
  return touchUser(record, records);
}

async function getCurrentUser(): Promise<User | null> {
  await ensureDemoUser();
  const session = currentSession();
  if (!session) return null;
  const records = users();
  const record = records.find((item) => item.user.id === session.userId);
  if (!record) {
    logout();
    return null;
  }
  return touchUser(record, records);
}

function logout(): void {
  prepareMockStorage();
  window.localStorage.removeItem(mockStorageKeys.session);
  window.sessionStorage.removeItem(mockStorageKeys.session);
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
    records.some(
      (item) => item.user.id !== userId && normalizeEmail(item.user.email) === email,
    )
  ) {
    throw new ApiError('Пользователь с таким email уже существует.', 409);
  }
  const user: User = {
    ...record.user,
    displayName,
    email,
    lastActiveAt: now(),
    preferences: request.preferences
      ? { ...request.preferences }
      : { ...record.user.preferences },
  };
  records[index] = { ...record, user };
  saveUsers(records);
  return user;
}

function savedRecords(): MockSavedRecord[] {
  return readArray(window.localStorage, mockStorageKeys.saved, isSavedRecord);
}

function getSavedEntries(): Array<{ documentId: string; savedAt: string }> {
  const userId = requireUserId();
  return savedRecords()
    .filter((record) => record.userId === userId)
    .map(({ documentId, savedAt }) => ({ documentId, savedAt }));
}

function getSavedDocumentIds(): Set<string> {
  const session = currentSession();
  if (!session) return new Set<string>();
  return new Set(
    savedRecords()
      .filter((record) => record.userId === session.userId)
      .map((record) => record.documentId),
  );
}

function saveDocument(documentId: string): { documentId: string; savedAt: string } {
  const userId = requireUserId();
  const records = savedRecords();
  const existing = records.find(
    (record) => record.userId === userId && record.documentId === documentId,
  );
  if (existing) return { documentId: existing.documentId, savedAt: existing.savedAt };
  const record = { userId, documentId, savedAt: now() };
  records.push(record);
  writeJson(window.localStorage, mockStorageKeys.saved, records);
  return { documentId, savedAt: record.savedAt };
}

function unsaveDocument(documentId: string): void {
  const userId = requireUserId();
  const records = savedRecords();
  writeJson(
    window.localStorage,
    mockStorageKeys.saved,
    records.filter((record) => !(record.userId === userId && record.documentId === documentId)),
  );
}

function historyRecords(): SearchHistoryItem[] {
  return readArray(window.localStorage, mockStorageKeys.history, isHistoryItem);
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
  const records = historyRecords();
  const latest = records
    .filter((record) => record.userId === session.userId)
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))[0];
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
  writeJson(window.localStorage, mockStorageKeys.history, records);
  return item;
}

function getHistory(filters: HistoryFilters): HistoryResponse {
  const userId = requireUserId();
  const search = filters.search.trim().toLocaleLowerCase('ru-RU');
  const items = historyRecords()
    .filter((item) => item.userId === userId)
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
    mockStorageKeys.history,
    historyRecords().filter((item) => !(item.userId === userId && item.id === historyId)),
  );
}

function clearHistory(): void {
  const userId = requireUserId();
  writeJson(
    window.localStorage,
    mockStorageKeys.history,
    historyRecords().filter((item) => item.userId !== userId),
  );
}

function feedbackRecords(): Feedback[] {
  return readArray(window.localStorage, mockStorageKeys.feedback, isFeedback);
}

function sendFeedback(request: FeedbackRequest): Feedback {
  const userId = requireUserId();
  const records = feedbackRecords();
  const index = records.findIndex(
    (item) => item.userId === userId && item.responseId === request.responseId,
  );
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
  writeJson(window.localStorage, mockStorageKeys.feedback, records);
  return feedback;
}

function getFeedbackForResponse(responseId: string): Feedback | null {
  const userId = requireUserId();
  return (
    feedbackRecords().find(
      (item) => item.userId === userId && item.responseId === responseId,
    ) ?? null
  );
}

function deleteFeedback(feedbackId: string): void {
  const userId = requireUserId();
  writeJson(
    window.localStorage,
    mockStorageKeys.feedback,
    feedbackRecords().filter((item) => !(item.userId === userId && item.id === feedbackId)),
  );
}

function getUserStats(): UserStats {
  const userId = requireUserId();
  const history = historyRecords().filter((item) => item.userId === userId);
  return {
    documentSearches: history.filter((item) => item.view === 'documents').length,
    ragSearches: history.filter((item) => item.view === 'answer').length,
    savedDocuments: savedRecords().filter((item) => item.userId === userId).length,
    ratedAnswers: feedbackRecords().filter((item) => item.userId === userId).length,
  };
}

export const mockRepository = {
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
  reset: clearMockStorage,
};
