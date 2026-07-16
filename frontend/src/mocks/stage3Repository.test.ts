import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api/ApiError';
import type {
  AdminUserFilters,
  AuditFilters,
  JobFilters,
  ManagedDocumentFilters,
  SearchRequest,
} from '../types';
import { materializeJob } from './mockJobEngine';
import { mockApi } from './mockApi';
import { mockRepository } from './mockRepository';
import { mockStorageKeys, mockUserStorageKeys, stage2StorageKeys } from './mockStorage';

const managedFilters: ManagedDocumentFilters = {
  q: '',
  status: 'ALL',
  tags: [],
  accepted: 'all',
  hasCode: 'all',
  bm25: 'ALL',
  vector: 'ALL',
  source: '',
  updatedAfter: '',
  sort: 'updated_desc',
  page: 1,
  limit: 50,
};
const userFilters: AdminUserFilters = {
  q: '',
  role: 'ALL',
  status: 'ALL',
  registeredFrom: '',
  registeredTo: '',
  sort: 'created_desc',
  page: 1,
  limit: 100,
};
const jobFilters: JobFilters = {
  id: '',
  type: 'ALL',
  status: 'ALL',
  stage: 'ALL',
  actor: '',
  documentId: '',
  source: '',
  dateFrom: '',
  dateTo: '',
  sort: 'created_desc',
  page: 1,
  limit: 100,
};
const auditFilters: AuditFilters = {
  q: '',
  actor: '',
  role: 'ALL',
  action: 'ALL',
  entityType: 'ALL',
  outcome: 'ALL',
  dateFrom: '',
  dateTo: '',
  sort: 'created_desc',
  page: 1,
  limit: 100,
};
const publicSearch: SearchRequest = {
  q: 'дубликаты список',
  view: 'documents',
  mode: 'hybrid',
  page: 1,
  pageSize: 20,
  filters: { tags: [], minScore: 0, acceptedOnly: false, hasCodeOnly: false, sort: 'relevance' },
};

async function login(role: 'USER' | 'EDITOR' | 'ADMIN') {
  const email =
    role === 'USER'
      ? 'user@pyanswer.local'
      : role === 'EDITOR'
        ? 'editor@pyanswer.local'
        : 'admin@pyanswer.local';
  return mockApi.login({ email, password: 'Demo123!', remember: true });
}

function removeRoleAndVersion(raw: string, userId: string): string {
  const value: unknown = JSON.parse(raw);
  if (!Array.isArray(value)) return raw;
  return JSON.stringify(
    (value as unknown[]).map((record) => {
      if (typeof record !== 'object' || record === null || !('user' in record)) return record;
      const user = record.user;
      if (typeof user !== 'object' || user === null || !('id' in user) || user.id !== userId) {
        return record;
      }
      const migratedUser = { ...user } as Record<string, unknown>;
      delete migratedUser.role;
      delete migratedUser.accountVersion;
      return { ...record, user: migratedUser };
    }),
  );
}

describe('Stage 3 mock repository', () => {
  afterEach(() => vi.useRealTimers());

  it('идемпотентно создаёт demo USER, EDITOR и ADMIN без дубликатов', async () => {
    await login('ADMIN');
    await mockRepository.initialize();
    const users = await mockApi.getAdminUsers(userFilters);
    for (const email of ['user@pyanswer.local', 'editor@pyanswer.local', 'admin@pyanswer.local']) {
      expect(users.items.filter((user) => user.email === email)).toHaveLength(1);
    }
    expect(users.pagination.total).toBeGreaterThanOrEqual(13);
  });

  it('регистрация всегда создаёт роль USER', async () => {
    const user = await mockApi.register({
      displayName: 'Новый пользователь',
      email: 'new-stage3@example.local',
      password: 'Strong123',
      acceptedTerms: true,
      remember: true,
    });
    expect(user.role).toBe('USER');
    expect(user.accountVersion).toBe(1);
  });

  it('мигрирует Stage 2 preferences, history, saved и feedback без потери', async () => {
    const user = await mockApi.register({
      displayName: 'Migration User',
      email: 'migration@example.local',
      password: 'Strong123',
      acceptedTerms: true,
      remember: true,
    });
    mockRepository.updateCurrentUser({
      preferences: { ...user.preferences, defaultSearchMode: 'vector' },
    });
    mockRepository.recordHistory({
      query: 'migration query',
      view: 'documents',
      mode: 'vector',
      filters: { tags: [], minScore: 0, acceptedOnly: false, hasCodeOnly: false },
      sort: 'relevance',
      pageSize: 10,
      resultCount: 1,
      tookMs: 42,
    });
    mockRepository.saveDocument('py-1001');
    mockRepository.sendFeedback({
      responseId: 'rag-migration',
      value: 'positive',
      question: 'migration',
    });
    const usersRaw = window.localStorage.getItem(mockStorageKeys.users);
    const sessionRaw = window.localStorage.getItem(mockStorageKeys.session);
    const historyRaw = window.localStorage.getItem(mockUserStorageKeys.history(user.id));
    const savedRaw = window.localStorage.getItem(mockUserStorageKeys.saved(user.id));
    const feedbackRaw = window.localStorage.getItem(mockUserStorageKeys.feedback(user.id));
    window.localStorage.removeItem(mockStorageKeys.users);
    window.localStorage.removeItem(mockStorageKeys.session);
    window.localStorage.removeItem(mockUserStorageKeys.history(user.id));
    window.localStorage.removeItem(mockUserStorageKeys.saved(user.id));
    window.localStorage.removeItem(mockUserStorageKeys.feedback(user.id));
    window.localStorage.removeItem(mockStorageKeys.schemaVersion);
    if (usersRaw) window.localStorage.setItem(stage2StorageKeys.users, usersRaw);
    if (sessionRaw) window.localStorage.setItem(stage2StorageKeys.session, sessionRaw);
    if (historyRaw) window.localStorage.setItem(stage2StorageKeys.history(user.id), historyRaw);
    if (savedRaw) window.localStorage.setItem(stage2StorageKeys.saved(user.id), savedRaw);
    if (feedbackRaw) window.localStorage.setItem(stage2StorageKeys.feedback(user.id), feedbackRaw);
    const restored = await mockApi.getCurrentUser();
    expect(restored?.preferences.defaultSearchMode).toBe('vector');
    expect(
      mockRepository.getHistory({
        search: '',
        view: 'all',
        mode: 'all',
        dateSort: 'newest',
        page: 1,
        pageSize: 20,
      }).items[0]?.query,
    ).toBe('migration query');
    expect(mockRepository.getSavedEntries()).toHaveLength(1);
    expect(mockRepository.getFeedbackForResponse('rag-migration')?.value).toBe('positive');
  });

  it('назначает USER и accountVersion старой учётной записи без этих полей', async () => {
    const user = await mockApi.register({
      displayName: 'Legacy User',
      email: 'legacy-role@example.local',
      password: 'Strong123',
      acceptedTerms: true,
      remember: true,
    });
    const usersRaw = window.localStorage.getItem(mockStorageKeys.users);
    const sessionRaw = window.localStorage.getItem(mockStorageKeys.session);
    expect(usersRaw).not.toBeNull();
    window.localStorage.removeItem(mockStorageKeys.users);
    window.localStorage.removeItem(mockStorageKeys.session);
    window.localStorage.removeItem(mockStorageKeys.schemaVersion);
    if (usersRaw) {
      window.localStorage.setItem(stage2StorageKeys.users, removeRoleAndVersion(usersRaw, user.id));
    }
    if (sessionRaw) window.localStorage.setItem(stage2StorageKeys.session, sessionRaw);
    const restored = await mockApi.getCurrentUser();
    expect(restored).toMatchObject({ id: user.id, role: 'USER', accountVersion: 1 });
  });

  it('повреждённые Stage 3 records безопасно восстанавливаются', async () => {
    window.localStorage.setItem(mockStorageKeys.users, '{bad');
    window.localStorage.setItem(mockStorageKeys.managedDocuments, '{bad');
    await login('EDITOR');
    expect((await mockApi.getManagedDocuments(managedFilters)).items.length).toBeGreaterThan(0);
  });

  it('EDITOR получает managed documents, а USER получает 403', async () => {
    await login('EDITOR');
    expect((await mockApi.getManagedDocuments(managedFilters)).items.length).toBeGreaterThan(0);
    await mockApi.logout();
    await login('USER');
    await expect(mockApi.getManagedDocuments(managedFilters)).rejects.toMatchObject({
      status: 403,
      code: 'FORBIDDEN',
    });
  });

  it('роль actor определяется сессией и не принимается аргументом', async () => {
    await login('USER');
    await expect(mockApi.updateUserRole('user-seed-01', { role: 'ADMIN' })).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it('metadata update нормализует tags, увеличивает version и сохраняет оригинал', async () => {
    await login('EDITOR');
    const before = await mockApi.getManagedDocument('py-1001');
    const updated = await mockApi.updateDocumentMetadata('py-1001', {
      normalizedTitle: '  Новый нормализованный заголовок  ',
      managedTags: [' Python ', 'python', '', ' Lists '],
      editorialNote: 'Проверено редактором',
    });
    expect(updated.normalizedTitle).toBe('Новый нормализованный заголовок');
    expect(updated.managedTags).toEqual(['python', 'lists']);
    expect(updated.version).toBe(before.version + 1);
    expect(updated.original.question).toEqual(before.original.question);
    expect(updated.original.title).toBe(before.original.title);
    expect(
      (await mockApi.searchDocuments(publicSearch)).results.find(
        (result) => result.documentId === 'py-1001',
      )?.title,
    ).toBe('Новый нормализованный заголовок');
  });

  it('metadata update создаёт audit event', async () => {
    await login('EDITOR');
    await mockApi.updateDocumentMetadata('py-1001', {
      normalizedTitle: 'Актуальный заголовок',
      managedTags: ['python'],
      editorialNote: '',
    });
    await mockApi.logout();
    await login('ADMIN');
    const audit = await mockApi.getAuditEvents(auditFilters);
    expect(
      audit.items.some(
        (event) => event.action === 'UPDATE_DOCUMENT_METADATA' && event.entityId === 'py-1001',
      ),
    ).toBe(true);
  });

  it('hide требует причину', async () => {
    await login('EDITOR');
    await expect(mockApi.hideDocument('py-1001', ' ')).rejects.toMatchObject({
      status: 422,
      code: 'VALIDATION_ERROR',
    });
  });

  it('HIDDEN-документ исчезает из поиска и RAG, restore возвращает его', async () => {
    await login('EDITOR');
    await mockApi.hideDocument('py-1001', 'Временная модерация');
    expect(
      (await mockApi.searchDocuments(publicSearch)).results.some(
        (item) => item.documentId === 'py-1001',
      ),
    ).toBe(false);
    const rag = await mockApi.askQuestion({
      question: 'как удалить дубликаты из списка',
      mode: 'hybrid',
      maxSources: 10,
    });
    expect(rag.sources.some((item) => item.documentId === 'py-1001')).toBe(false);
    await mockApi.restoreDocument('py-1001');
    expect(
      (await mockApi.searchDocuments(publicSearch)).results.some(
        (item) => item.documentId === 'py-1001',
      ),
    ).toBe(true);
  });

  it('скрытый document detail не раскрывается в публичном API', async () => {
    await login('EDITOR');
    await mockApi.hideDocument('py-1001', 'Модерация');
    await expect(mockApi.getDocument('py-1001')).rejects.toMatchObject({
      status: 404,
      details: { reason: 'DOCUMENT_UNAVAILABLE' },
    });
  });

  it('reindex создаёт одно активное job и второй вызов возвращает 409', async () => {
    await login('EDITOR');
    const job = await mockApi.reindexDocument('py-1001');
    expect(job.type).toBe('DOCUMENT_REINDEX');
    await expect(mockApi.reindexDocument('py-1001')).rejects.toMatchObject({
      status: 409,
      details: { jobId: job.id },
    });
  });

  it('bulk action возвращает partial result и один batch audit', async () => {
    await login('EDITOR');
    const result = await mockApi.bulkUpdateDocuments({
      action: 'HIDE',
      documentIds: ['py-1001', 'py-1002', 'missing'],
      reason: 'Пакетная модерация',
    });
    expect(result).toMatchObject({ successCount: 1, skippedCount: 1, failedCount: 1 });
    await mockApi.logout();
    await login('ADMIN');
    const audit = await mockApi.getAuditEvents(auditFilters);
    expect(audit.items.filter((event) => event.batchId === result.batchId)).toHaveLength(1);
  });

  it('ADMIN назначает EDITOR, accountVersion растёт и создаётся audit', async () => {
    await login('ADMIN');
    const before = await mockApi.getAdminUser('user-seed-01');
    const updated = await mockApi.updateUserRole('user-seed-01', { role: 'EDITOR' });
    expect(updated.role).toBe('EDITOR');
    expect(updated.accountVersion).toBe(before.accountVersion + 1);
    const audit = await mockApi.getAuditEvents(auditFilters);
    expect(
      audit.items.some(
        (event) => event.action === 'CHANGE_USER_ROLE' && event.entityId === updated.id,
      ),
    ).toBe(true);
  });

  it('EDITOR не может менять роли', async () => {
    await login('EDITOR');
    await expect(mockApi.updateUserRole('user-seed-01', { role: 'EDITOR' })).rejects.toMatchObject({
      status: 403,
    });
  });

  it('ADMIN не может изменить свою роль или заблокировать себя', async () => {
    const admin = await login('ADMIN');
    await expect(mockApi.updateUserRole(admin.id, { role: 'USER' })).rejects.toMatchObject({
      status: 409,
    });
    await expect(mockApi.blockUser(admin.id, { reason: 'Проверка запрета' })).rejects.toMatchObject(
      { status: 409 },
    );
  });

  it('нельзя понизить последнего ACTIVE ADMIN', async () => {
    const admin = await login('ADMIN');
    await mockApi.updateUserRole('user-seed-08', { role: 'USER' });
    await expect(mockApi.updateUserRole(admin.id, { role: 'USER' })).rejects.toThrow(
      'В системе должен оставаться активный администратор.',
    );
  });

  it('нельзя заблокировать последнего ACTIVE ADMIN', async () => {
    const admin = await login('ADMIN');
    await mockApi.blockUser('user-seed-08', { reason: 'Проверка защиты последнего ADMIN' });
    await expect(mockApi.blockUser(admin.id, { reason: 'Проверка защиты' })).rejects.toThrow(
      'Нельзя заблокировать последнего активного администратора.',
    );
  });

  it('BLOCKED user не входит, после unblock снова входит', async () => {
    await login('ADMIN');
    await mockApi.blockUser('user-seed-02', { reason: 'Нарушение правил' });
    expect(
      (await mockApi.getAuditEvents(auditFilters)).items.some(
        (event) => event.action === 'BLOCK_USER' && event.entityId === 'user-seed-02',
      ),
    ).toBe(true);
    await mockApi.logout();
    await expect(
      mockApi.login({ email: 'maxim@pyanswer.local', password: 'Demo123!', remember: true }),
    ).rejects.toMatchObject({ status: 403 });
    await login('ADMIN');
    await mockApi.unblockUser('user-seed-02');
    await mockApi.logout();
    expect(
      (await mockApi.login({ email: 'maxim@pyanswer.local', password: 'Demo123!', remember: true }))
        .accountStatus,
    ).toBe('ACTIVE');
  });

  it('старая сессия BLOCKED user становится недействительной', async () => {
    await mockApi.login({ email: 'maxim@pyanswer.local', password: 'Demo123!', remember: true });
    const oldSession = window.localStorage.getItem(mockStorageKeys.session);
    await mockApi.logout();
    await login('ADMIN');
    await mockApi.blockUser('user-seed-02', { reason: 'Инвалидация сессии' });
    if (oldSession) window.localStorage.setItem(mockStorageKeys.session, oldSession);
    expect(await mockApi.getCurrentUser()).toBeNull();
  });

  it('admin API не возвращает credential fields', async () => {
    await login('ADMIN');
    const payload = JSON.stringify(await mockApi.getAdminUser('user-seed-01'));
    expect(payload).not.toMatch(/digest|salt|password|session/i);
  });

  it('ADMIN запускает и останавливает source sync, повторный start даёт 409', async () => {
    await login('ADMIN');
    const job = await mockApi.startSourceSync('source-stackoverflow-ru');
    expect(job.type).toBe('SOURCE_SYNC');
    await expect(mockApi.startSourceSync('source-stackoverflow-ru')).rejects.toMatchObject({
      status: 409,
    });
    expect((await mockApi.stopSourceSync('source-stackoverflow-ru')).status).toBe('CANCELLED');
  });

  it('source connection test обновляет lastCheck и создаёт audit', async () => {
    await login('ADMIN');
    const result = await mockApi.testSourceConnection('source-stackoverflow-ru');
    expect(result.success).toBe(true);
    expect((await mockApi.getSource('source-stackoverflow-ru')).lastCheckAt).toBe(result.checkedAt);
    expect(
      (await mockApi.getAuditEvents(auditFilters)).items.some(
        (event) => event.action === 'TEST_SOURCE',
      ),
    ).toBe(true);
  });

  it('operational ingestion contract доступен ADMIN и read-only document API доступен EDITOR', async () => {
    await login('ADMIN');
    const state = await mockApi.getSourceSyncState('source-stackoverflow-ru');
    const stats = await mockApi.getIngestionStats();
    expect(state.totalQuestionsFetched).toBeGreaterThan(0);
    expect(stats.chunksCount).toBeGreaterThan(0);
    await mockApi.logout();
    await login('EDITOR');
    const document = (await mockApi.getManagedDocuments(managedFilters)).items[0];
    expect(document).toBeDefined();
    if (!document) return;
    expect(
      (await mockApi.getManagedDocumentChunks(document.documentId)).items.length,
    ).toBeGreaterThan(0);
    expect((await mockApi.getManagedDocumentRevisions(document.documentId)).items).toHaveLength(1);
  });

  it('source settings валидируются', async () => {
    await login('ADMIN');
    await expect(
      mockApi.updateSource('source-stackoverflow-ru', { targetDocuments: 100 }),
    ).rejects.toMatchObject({ status: 422, code: 'VALIDATION_ERROR' });
  });

  it('EDITOR не может запустить source sync', async () => {
    await login('EDITOR');
    await expect(mockApi.startSourceSync('source-stackoverflow-ru')).rejects.toMatchObject({
      status: 403,
    });
  });

  it('job progress вычисляется детерминированно с fake timers', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-15T12:00:05.000Z'));
    const job = materializeJob({
      id: 'job-test',
      type: 'DOCUMENT_REINDEX',
      status: 'RUNNING',
      stage: 'PREPARING',
      progress: 0,
      processedItems: 0,
      totalItems: 100,
      createdBy: 'actor',
      createdAt: '2026-07-15T11:59:59.000Z',
      startedAt: '2026-07-15T12:00:00.000Z',
      plannedDurationMs: 10_000,
      cancellable: true,
    });
    expect(job.progress).toBe(50);
    expect(job.processedItems).toBe(50);
    vi.setSystemTime(new Date('2026-07-15T12:00:11.000Z'));
    expect(materializeJob(job).status).toBe('COMPLETED');
  });

  it('COMPLETED job нельзя отменить, FAILED можно повторить, RUNNING нельзя повторить', async () => {
    await login('ADMIN');
    await expect(mockApi.cancelJob('job-seed-completed')).rejects.toMatchObject({ status: 409 });
    const retry = await mockApi.retryJob('job-seed-failed');
    expect(retry.retryOfJobId).toBe('job-seed-failed');
    await expect(mockApi.retryJob('job-seed-running')).rejects.toMatchObject({ status: 409 });
  });

  it('нельзя создать два активных FULL_REINDEX', async () => {
    await login('ADMIN');
    const job = await mockApi.startFullReindex();
    expect(job.type).toBe('FULL_REINDEX');
    await expect(mockApi.startFullReindex()).rejects.toMatchObject({
      status: 409,
      details: { jobId: job.id },
    });
  });

  it('audit недоступен EDITOR и не содержит credentials', async () => {
    await login('EDITOR');
    await expect(mockApi.getAuditEvents(auditFilters)).rejects.toMatchObject({ status: 403 });
    await mockApi.logout();
    await login('ADMIN');
    expect(JSON.stringify(await mockApi.getAuditEvents(auditFilters))).not.toMatch(
      /digest|salt|password|session reference/i,
    );
  });

  it('health check обновляет lastCheckAt и создаёт audit event', async () => {
    await login('ADMIN');
    const before = await mockApi.getSystemStatus();
    const checked = await mockApi.runSystemHealthCheck();
    expect(Date.parse(checked.lastCheckAt)).toBeGreaterThan(Date.parse(before.lastCheckAt));
    const audit = await mockApi.getAuditEvents(auditFilters);
    expect(audit.items.some((event) => event.action === 'HEALTH_CHECK')).toBe(true);
  });

  it('будущие сервисы не показываются ONLINE на Этапе 5', async () => {
    await login('ADMIN');
    const status = await mockApi.getSystemStatus();
    for (const id of ['qdrant', 'ollama', 'indexer', 'bm25', 'vector', 'embedding', 'reranker']) {
      expect(status.services.find((service) => service.id === id)?.status).toBe('OFFLINE');
    }
  });

  it('system settings доступны только ADMIN и отклоняют невалидные значения', async () => {
    await login('EDITOR');
    await expect(mockApi.getSystemSettings()).rejects.toMatchObject({ status: 403 });
    await mockApi.logout();
    await login('ADMIN');
    await expect(mockApi.updateSystemSettings({ ragSourcesLimit: 100 })).rejects.toMatchObject({
      status: 422,
    });
  });

  it('allowGuestSearch и allowGuestRag ограничивают гостевой API', async () => {
    await login('ADMIN');
    await mockApi.updateSystemSettings({ allowGuestSearch: false, allowGuestRag: false });
    await mockApi.logout();
    await expect(mockApi.searchDocuments(publicSearch)).rejects.toMatchObject({ status: 401 });
    await expect(
      mockApi.askQuestion({ question: 'asyncio', mode: 'hybrid' }),
    ).rejects.toMatchObject({ status: 401 });
  });

  it('system settings реально ограничивают число источников RAG', async () => {
    await login('ADMIN');
    await mockApi.updateSystemSettings({ ragSourcesLimit: 1 });
    const result = await mockApi.askQuestion({
      question: 'asyncio',
      mode: 'hybrid',
      maxSources: 10,
    });
    expect(result.sources.length).toBeLessThanOrEqual(1);
  });

  it('URL-фильтры managed table сохраняют page и limit в contract', async () => {
    await login('EDITOR');
    const response = await mockApi.getManagedDocuments({
      ...managedFilters,
      status: 'ACTIVE',
      page: 2,
      limit: 10,
    });
    expect(response.pagination).toMatchObject({ page: 2, pageSize: 10 });
    expect(response.items.every((item) => item.status === 'ACTIVE')).toBe(true);
  });

  it('seeded jobs содержат все основные lifecycle статусы', async () => {
    await login('ADMIN');
    const jobs = await mockApi.getAdminJobs(jobFilters);
    expect(jobs.items.map((job) => job.status)).toEqual(
      expect.arrayContaining(['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED']),
    );
  });
});
