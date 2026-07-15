import { ApiError } from '../api/ApiError';
import type {
  AdminDashboard,
  AuditEvent,
  AuditEventsResponse,
  AuditFilters,
  BackgroundJob,
  BulkDocumentRequest,
  BulkDocumentResult,
  Document,
  DocumentStatus,
  EditorDashboard,
  JobFilters,
  JobsResponse,
  ManagedDocument,
  ManagedDocumentDetail,
  ManagedDocumentFilters,
  ManagedDocumentsResponse,
  ManagedDocumentUpdate,
  Source,
  SourceConnectionResult,
  SourceFilters,
  SourcesResponse,
  SourceUpdateRequest,
  SystemSettings,
  SystemSettingsUpdate,
  SystemStatus,
  Tag,
} from '../types';
import { mockDocuments } from './data';
import { appendAudit, readAuditEvents } from './mockAudit';
import { materializeJob } from './mockJobEngine';
import { mockRepository } from './mockRepository';
import {
  completeMockStorageMigration,
  mockStorageKeys,
  readArray,
  readUnknown,
  writeJson,
} from './mockStorage';

type ManagedRecord = Omit<ManagedDocument, 'original'>;

const sourceId = 'source-stackoverflow-ru';
const publicStatuses = new Set<DocumentStatus>(['ACTIVE', 'OUTDATED']);

function now(): string {
  return new Date().toISOString();
}

function makeId(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2);
  return `${prefix}-${random}`;
}

function isManagedRecord(value: unknown): value is ManagedRecord {
  return (
    typeof value === 'object' &&
    value !== null &&
    'documentId' in value &&
    typeof value.documentId === 'string' &&
    'status' in value &&
    ['ACTIVE', 'HIDDEN', 'PENDING', 'FAILED', 'OUTDATED'].includes(String(value.status)) &&
    'managedTags' in value &&
    Array.isArray(value.managedTags) &&
    value.managedTags.every((tag) => typeof tag === 'string') &&
    'normalizedTitle' in value &&
    typeof value.normalizedTitle === 'string' &&
    'version' in value &&
    typeof value.version === 'number'
  );
}

function isJob(value: unknown): value is BackgroundJob {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'type' in value &&
    ['SOURCE_SYNC', 'DOCUMENT_REINDEX', 'FULL_REINDEX', 'HEALTH_CHECK'].includes(
      String(value.type),
    ) &&
    'status' in value &&
    ['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'].includes(String(value.status)) &&
    'plannedDurationMs' in value &&
    typeof value.plannedDurationMs === 'number'
  );
}

function isSource(value: unknown): value is Source {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'string' &&
    'type' in value &&
    value.type === 'STACK_EXCHANGE' &&
    'status' in value &&
    typeof value.status === 'string'
  );
}

function isSystemSettings(value: unknown): value is SystemSettings {
  return (
    typeof value === 'object' &&
    value !== null &&
    'searchCandidatesLimit' in value &&
    typeof value.searchCandidatesLimit === 'number' &&
    'rerankerLimit' in value &&
    typeof value.rerankerLimit === 'number' &&
    'ragSourcesLimit' in value &&
    typeof value.ragSourcesLimit === 'number' &&
    'allowGuestSearch' in value &&
    typeof value.allowGuestSearch === 'boolean' &&
    'allowGuestRag' in value &&
    typeof value.allowGuestRag === 'boolean'
  );
}

function isStoredSystemStatus(value: unknown): value is SystemStatus {
  return (
    typeof value === 'object' &&
    value !== null &&
    'services' in value &&
    Array.isArray(value.services) &&
    (value.services as unknown[]).every(
      (service: unknown) =>
        typeof service === 'object' &&
        service !== null &&
        'id' in service &&
        typeof service.id === 'string' &&
        'status' in service &&
        ['ONLINE', 'DEGRADED', 'OFFLINE', 'STARTING'].includes(String(service.status)),
    ) &&
    'metrics' in value &&
    typeof value.metrics === 'object' &&
    value.metrics !== null &&
    'hardware' in value &&
    typeof value.hardware === 'object' &&
    value.hardware !== null &&
    'lastCheckAt' in value &&
    typeof value.lastCheckAt === 'string'
  );
}

function managedRecords(): ManagedRecord[] {
  return readArray(window.localStorage, mockStorageKeys.managedDocuments, isManagedRecord);
}

function saveManaged(records: ManagedRecord[]): void {
  writeJson(window.localStorage, mockStorageKeys.managedDocuments, records);
}

function storedJobs(): BackgroundJob[] {
  return readArray(window.localStorage, mockStorageKeys.jobs, isJob);
}

function saveJobs(jobs: BackgroundJob[]): void {
  writeJson(window.localStorage, mockStorageKeys.jobs, jobs);
}

function storedSources(): Source[] {
  return readArray(window.localStorage, mockStorageKeys.sources, isSource);
}

function saveSources(sources: Source[]): void {
  writeJson(window.localStorage, mockStorageKeys.sources, sources);
}

const defaultSettings: SystemSettings = {
  searchCandidatesLimit: 120,
  rerankerLimit: 50,
  ragSourcesLimit: 3,
  defaultMinimumConfidence: 0.45,
  allowGuestSearch: true,
  allowGuestRag: true,
  historyRetentionDays: 365,
  auditRetentionDays: 730,
  updatedAt: '2026-07-15T08:00:00.000Z',
};

function settings(): SystemSettings {
  const value = readUnknown(window.localStorage, mockStorageKeys.systemSettings);
  return isSystemSettings(value) ? { ...defaultSettings, ...value } : { ...defaultSettings };
}

function initialStatus(index: number): DocumentStatus {
  if (index === 1) return 'HIDDEN';
  if (index === 4) return 'OUTDATED';
  if (index === 5) return 'PENDING';
  if (index === 6) return 'FAILED';
  return 'ACTIVE';
}

function seedManagedDocuments(): void {
  const current = managedRecords();
  const byId = new Map(current.map((record) => [record.documentId, record]));
  let changed = false;
  for (const [index, document] of mockDocuments.entries()) {
    if (byId.has(document.id)) continue;
    const status = initialStatus(index);
    current.push({
      documentId: document.id,
      status,
      bm25Status: status === 'FAILED' ? 'FAILED' : status === 'PENDING' ? 'PENDING' : 'READY',
      vectorStatus: status === 'FAILED' ? 'FAILED' : status === 'PENDING' ? 'NOT_INDEXED' : 'READY',
      chunksCount: document.chunkCount,
      indexedAt: document.indexedAt,
      lastSyncedAt: new Date(Date.parse(document.indexedAt) - 3_600_000).toISOString(),
      contentHash: document.contentHash,
      normalizedTitle: document.title,
      managedTags: document.tags.map((tag) => tag.slug),
      editorialNote: status === 'FAILED' ? 'Требуется повторная индексация.' : '',
      failureReason: status === 'FAILED' ? 'VECTOR_BUILD_FAILED' : undefined,
      hiddenReason: status === 'HIDDEN' ? 'Материал временно снят с публикации.' : undefined,
      version: 1,
      sourceId,
    });
    changed = true;
  }
  if (changed) saveManaged(current);
}

function seedSources(): void {
  if (storedSources().length > 0) return;
  const createdAt = '2025-01-02T08:00:00.000Z';
  saveSources([
    {
      id: sourceId,
      name: 'Stack Overflow на русском',
      type: 'STACK_EXCHANGE',
      baseUrl: 'https://ru.stackoverflow.com',
      site: 'ru.stackoverflow',
      tag: 'python',
      enabled: true,
      status: 'IDLE',
      targetDocuments: 25_000,
      maxAdditionalAnswers: 3,
      pageSize: 100,
      documentsCount: 25_000,
      lastSyncAt: '2026-07-15T07:43:00.000Z',
      lastSuccessfulSyncAt: '2026-07-15T07:43:00.000Z',
      lastCheckAt: '2026-07-15T08:10:00.000Z',
      rateLimitRemaining: 8_742,
      rateLimitTotal: 10_000,
      quotaResetAt: '2026-07-16T00:00:00.000Z',
      apiKeyConfigured: false,
      createdAt,
      updatedAt: createdAt,
    },
  ]);
}

function seedJobs(): void {
  if (storedJobs().length > 0) return;
  const clock = Date.now();
  saveJobs([
    {
      id: 'job-seed-running',
      type: 'SOURCE_SYNC',
      status: 'RUNNING',
      stage: 'CHUNKING',
      progress: 20,
      processedItems: 5_000,
      totalItems: 25_000,
      createdBy: 'user-demo-admin',
      createdAt: new Date(clock - 18_000).toISOString(),
      startedAt: new Date(clock - 16_000).toISOString(),
      plannedDurationMs: 180_000,
      cancellable: true,
    },
    {
      id: 'job-seed-queued',
      type: 'DOCUMENT_REINDEX',
      status: 'QUEUED',
      stage: 'PREPARING',
      progress: 0,
      processedItems: 0,
      totalItems: 8,
      documentId: mockDocuments[8]?.id,
      createdBy: 'user-demo-editor',
      createdAt: new Date(clock + 45_000).toISOString(),
      plannedDurationMs: 42_000,
      cancellable: true,
    },
    {
      id: 'job-seed-completed',
      type: 'FULL_REINDEX',
      status: 'COMPLETED',
      stage: 'FINALIZING',
      progress: 100,
      processedItems: 82_460,
      totalItems: 82_460,
      createdBy: 'user-demo-admin',
      createdAt: new Date(clock - 86_400_000).toISOString(),
      startedAt: new Date(clock - 86_390_000).toISOString(),
      finishedAt: new Date(clock - 86_100_000).toISOString(),
      durationMs: 290_000,
      plannedDurationMs: 290_000,
      cancellable: false,
    },
    {
      id: 'job-seed-failed',
      type: 'DOCUMENT_REINDEX',
      status: 'FAILED',
      stage: 'INDEXING_VECTOR',
      progress: 76,
      processedItems: 5,
      totalItems: 7,
      documentId: mockDocuments[6]?.id,
      createdBy: 'user-demo-editor',
      createdAt: new Date(clock - 7_200_000).toISOString(),
      startedAt: new Date(clock - 7_198_000).toISOString(),
      finishedAt: new Date(clock - 7_150_000).toISOString(),
      durationMs: 48_000,
      plannedDurationMs: 60_000,
      errorCode: 'VECTOR_BUILD_FAILED',
      errorMessage: 'Недостаточно данных для построения вектора.',
      cancellable: false,
    },
    {
      id: 'job-seed-cancelled',
      type: 'SOURCE_SYNC',
      status: 'CANCELLED',
      stage: 'CRAWLING',
      progress: 14,
      processedItems: 3_500,
      totalItems: 25_000,
      sourceId,
      createdBy: 'user-demo-admin',
      createdAt: new Date(clock - 172_800_000).toISOString(),
      startedAt: new Date(clock - 172_798_000).toISOString(),
      finishedAt: new Date(clock - 172_760_000).toISOString(),
      durationMs: 38_000,
      plannedDurationMs: 180_000,
      cancellable: false,
    },
  ]);
}

function initialize(): void {
  seedManagedDocuments();
  seedSources();
  seedJobs();
  if (!isSystemSettings(readUnknown(window.localStorage, mockStorageKeys.systemSettings))) {
    writeJson(window.localStorage, mockStorageKeys.systemSettings, defaultSettings);
  }
  completeMockStorageMigration();
}

function documentById(documentId: string): Document {
  const document = mockDocuments.find((item) => item.id === documentId);
  if (!document) throw new ApiError('Документ не найден.', 404, 'NOT_FOUND');
  return document;
}

function recordById(documentId: string, records = managedRecords()): ManagedRecord {
  const record = records.find((item) => item.documentId === documentId);
  if (!record) throw new ApiError('Управляемый документ не найден.', 404, 'NOT_FOUND');
  return record;
}

function managedTag(slug: string, original: Document): Tag {
  return original.tags.find((tag) => tag.slug === slug) ?? { slug, name: slug };
}

function publicDocument(record: ManagedRecord): Document {
  const original = documentById(record.documentId);
  return {
    ...original,
    title: record.normalizedTitle,
    tags: record.managedTags.map((slug) => managedTag(slug, original)),
    chunkCount: record.chunksCount,
    indexedAt: record.indexedAt,
    bm25Status: record.bm25Status,
    vectorStatus: record.vectorStatus,
    contentHash: record.contentHash,
  };
}

function toManaged(record: ManagedRecord): ManagedDocument {
  return { ...record, original: documentById(record.documentId) };
}

function getPublicDocuments(): Document[] {
  initialize();
  return managedRecords()
    .filter((record) => publicStatuses.has(record.status))
    .map(publicDocument);
}

function getPublicDocument(documentId: string): Document {
  initialize();
  const record = recordById(documentId);
  if (!publicStatuses.has(record.status)) {
    throw new ApiError('Документ временно недоступен.', 404, 'NOT_FOUND', {
      reason: 'DOCUMENT_UNAVAILABLE',
      status: record.status,
    });
  }
  return publicDocument(record);
}

function refreshJobs(): BackgroundJob[] {
  const previous = storedJobs();
  const refreshed = previous.map((job) => materializeJob(job));
  const completedIds = new Set(
    refreshed
      .filter((job, index) => job.status === 'COMPLETED' && previous[index]?.status !== 'COMPLETED')
      .map((job) => job.id),
  );
  if (completedIds.size > 0) {
    const records = managedRecords();
    let documentsChanged = false;
    for (const job of refreshed.filter((item) => completedIds.has(item.id))) {
      if (job.documentId) {
        const index = records.findIndex((record) => record.documentId === job.documentId);
        const record = records[index];
        if (record) {
          records[index] = {
            ...record,
            bm25Status: 'READY',
            vectorStatus: 'READY',
            indexedAt: job.finishedAt ?? now(),
            failureReason: undefined,
          };
          documentsChanged = true;
        }
      }
      if (job.sourceId) {
        const sources = storedSources();
        const index = sources.findIndex((source) => source.id === job.sourceId);
        const source = sources[index];
        if (source) {
          sources[index] = {
            ...source,
            status: 'IDLE',
            currentJobId: undefined,
            lastSyncAt: job.finishedAt ?? now(),
            lastSuccessfulSyncAt: job.finishedAt ?? now(),
            updatedAt: now(),
          };
          saveSources(sources);
        }
      }
    }
    if (documentsChanged) saveManaged(records);
  }
  if (JSON.stringify(previous) !== JSON.stringify(refreshed)) saveJobs(refreshed);
  return refreshed;
}

function createJob(
  values: Pick<BackgroundJob, 'type' | 'createdBy' | 'totalItems' | 'plannedDurationMs'> &
    Partial<Pick<BackgroundJob, 'sourceId' | 'documentId' | 'retryOfJobId'>>,
): BackgroundJob {
  const job: BackgroundJob = {
    id: makeId('job'),
    type: values.type,
    status: 'QUEUED',
    stage: 'PREPARING',
    progress: 0,
    processedItems: 0,
    totalItems: values.totalItems,
    sourceId: values.sourceId,
    documentId: values.documentId,
    createdBy: values.createdBy,
    createdAt: now(),
    plannedDurationMs: values.plannedDurationMs,
    retryOfJobId: values.retryOfJobId,
    cancellable: true,
  };
  const jobs = refreshJobs();
  jobs.push(job);
  saveJobs(jobs);
  return job;
}

function getManagedDocuments(filters: ManagedDocumentFilters): ManagedDocumentsResponse {
  mockRepository.requirePermission('MANAGED_DOCUMENTS_VIEW');
  initialize();
  refreshJobs();
  const search = filters.q.trim().toLocaleLowerCase('ru-RU');
  let items = managedRecords()
    .map(toManaged)
    .filter(
      (item) =>
        !search ||
        item.documentId.toLocaleLowerCase('ru-RU').includes(search) ||
        item.normalizedTitle.toLocaleLowerCase('ru-RU').includes(search),
    )
    .filter((item) => filters.status === 'ALL' || item.status === filters.status)
    .filter((item) =>
      filters.tags.length === 0
        ? true
        : filters.tags.every((tag) => item.managedTags.includes(tag)),
    )
    .filter((item) => {
      const accepted = item.original.answers.some((answer) => answer.accepted);
      return filters.accepted === 'all' || String(accepted) === filters.accepted;
    })
    .filter((item) => {
      const hasCode =
        item.original.question.codeBlocks.length > 0 ||
        item.original.answers.some((answer) => answer.codeBlocks.length > 0);
      return filters.hasCode === 'all' || String(hasCode) === filters.hasCode;
    })
    .filter((item) => filters.bm25 === 'ALL' || item.bm25Status === filters.bm25)
    .filter((item) => filters.vector === 'ALL' || item.vectorStatus === filters.vector)
    .filter((item) => !filters.source || item.sourceId === filters.source)
    .filter(
      (item) =>
        !filters.updatedAfter || (item.lastEditedAt ?? item.lastSyncedAt) >= filters.updatedAfter,
    );

  items = items.sort((left, right) => {
    if (filters.sort === 'updated_asc') {
      return (left.lastEditedAt ?? left.lastSyncedAt).localeCompare(
        right.lastEditedAt ?? right.lastSyncedAt,
      );
    }
    if (filters.sort === 'rating_desc') return right.original.score - left.original.score;
    if (filters.sort === 'title_asc')
      return left.normalizedTitle.localeCompare(right.normalizedTitle, 'ru');
    if (filters.sort === 'status_asc') return left.status.localeCompare(right.status);
    return (right.lastEditedAt ?? right.lastSyncedAt).localeCompare(
      left.lastEditedAt ?? left.lastSyncedAt,
    );
  });
  const availableTags = [
    ...new Set(managedRecords().flatMap((record) => record.managedTags)),
  ].sort();
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / filters.limit));
  const offset = (filters.page - 1) * filters.limit;
  return {
    items: items.slice(offset, offset + filters.limit),
    availableTags,
    pagination: { page: filters.page, pageSize: filters.limit, total, totalPages },
  };
}

function getManagedDocument(documentId: string): ManagedDocumentDetail {
  mockRepository.requirePermission('MANAGED_DOCUMENTS_VIEW');
  initialize();
  const jobs = refreshJobs();
  const record = recordById(documentId);
  return {
    ...toManaged(record),
    auditEvents: readAuditEvents()
      .filter((event) => event.entityType === 'DOCUMENT' && event.entityId === documentId)
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt)),
    relatedJobs: jobs
      .filter((job) => job.documentId === documentId)
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt)),
  };
}

function normalizeTags(tags: string[]): string[] {
  return [...new Set(tags.map((tag) => tag.trim().toLocaleLowerCase('ru-RU')).filter(Boolean))];
}

function updateDocumentMetadata(
  documentId: string,
  update: ManagedDocumentUpdate,
): ManagedDocumentDetail {
  const actor = mockRepository.requirePermission('DOCUMENT_METADATA_EDIT');
  const title = update.normalizedTitle.trim();
  const tags = normalizeTags(update.managedTags);
  const note = update.editorialNote.trim();
  if (!title || title.length > 180) {
    throw new ApiError('Заголовок должен содержать от 1 до 180 символов.', 422, 'VALIDATION_ERROR');
  }
  if (tags.length === 0) {
    throw new ApiError('Добавьте минимум один тег.', 422, 'VALIDATION_ERROR');
  }
  if (note.length > 1_000) {
    throw new ApiError(
      'Редакторская заметка не должна превышать 1000 символов.',
      422,
      'VALIDATION_ERROR',
    );
  }
  const records = managedRecords();
  const index = records.findIndex((record) => record.documentId === documentId);
  const record = records[index];
  if (!record) throw new ApiError('Документ не найден.', 404, 'NOT_FOUND');
  const updated: ManagedRecord = {
    ...record,
    normalizedTitle: title,
    managedTags: tags,
    editorialNote: note,
    lastEditedBy: actor.id,
    lastEditedAt: now(),
    version: record.version + 1,
  };
  records[index] = updated;
  saveManaged(records);
  appendAudit({
    actor,
    action: 'UPDATE_DOCUMENT_METADATA',
    entityType: 'DOCUMENT',
    entityId: documentId,
    entityLabel: title,
    summary: 'Обновлены управленческие метаданные документа',
    before: {
      normalizedTitle: record.normalizedTitle,
      managedTags: record.managedTags,
      editorialNote: record.editorialNote,
      version: record.version,
    },
    after: {
      normalizedTitle: title,
      managedTags: tags,
      editorialNote: note,
      version: updated.version,
    },
  });
  return getManagedDocument(documentId);
}

function hideDocument(documentId: string, reasonValue: string): ManagedDocumentDetail {
  const actor = mockRepository.requirePermission('DOCUMENT_STATUS_CHANGE');
  const reason = reasonValue.trim();
  if (reason.length < 3) throw new ApiError('Укажите причину скрытия.', 422, 'VALIDATION_ERROR');
  const records = managedRecords();
  const index = records.findIndex((record) => record.documentId === documentId);
  const record = records[index];
  if (!record) throw new ApiError('Документ не найден.', 404, 'NOT_FOUND');
  if (!['ACTIVE', 'OUTDATED'].includes(record.status)) {
    throw new ApiError('Документ в текущем статусе нельзя скрыть.', 409, 'CONFLICT');
  }
  records[index] = {
    ...record,
    status: 'HIDDEN',
    hiddenReason: reason.slice(0, 500),
    lastEditedBy: actor.id,
    lastEditedAt: now(),
    version: record.version + 1,
  };
  saveManaged(records);
  appendAudit({
    actor,
    action: 'HIDE_DOCUMENT',
    entityType: 'DOCUMENT',
    entityId: documentId,
    entityLabel: record.normalizedTitle,
    summary: 'Документ скрыт из публичного поиска',
    before: { status: record.status },
    after: { status: 'HIDDEN', hiddenReason: reason.slice(0, 500) },
  });
  return getManagedDocument(documentId);
}

function restoreDocument(documentId: string): ManagedDocumentDetail {
  const actor = mockRepository.requirePermission('DOCUMENT_STATUS_CHANGE');
  const records = managedRecords();
  const index = records.findIndex((record) => record.documentId === documentId);
  const record = records[index];
  if (!record) throw new ApiError('Документ не найден.', 404, 'NOT_FOUND');
  if (record.status !== 'HIDDEN') {
    throw new ApiError('Восстановить можно только скрытый документ.', 409, 'CONFLICT');
  }
  records[index] = {
    ...record,
    status: 'ACTIVE',
    hiddenReason: undefined,
    lastEditedBy: actor.id,
    lastEditedAt: now(),
    version: record.version + 1,
  };
  saveManaged(records);
  appendAudit({
    actor,
    action: 'RESTORE_DOCUMENT',
    entityType: 'DOCUMENT',
    entityId: documentId,
    entityLabel: record.normalizedTitle,
    summary: 'Документ возвращён в публичный поиск',
    before: { status: 'HIDDEN' },
    after: { status: 'ACTIVE' },
  });
  return getManagedDocument(documentId);
}

function reindexDocument(documentId: string): BackgroundJob {
  const actor = mockRepository.requirePermission('DOCUMENT_REINDEX');
  const jobs = refreshJobs();
  const active = jobs.find(
    (job) =>
      job.type === 'DOCUMENT_REINDEX' &&
      job.documentId === documentId &&
      (job.status === 'QUEUED' || job.status === 'RUNNING'),
  );
  if (active) {
    throw new ApiError('Для документа уже выполняется переиндексация.', 409, 'CONFLICT', {
      jobId: active.id,
    });
  }
  const records = managedRecords();
  const index = records.findIndex((record) => record.documentId === documentId);
  const record = records[index];
  if (!record) throw new ApiError('Документ не найден.', 404, 'NOT_FOUND');
  const job = createJob({
    type: 'DOCUMENT_REINDEX',
    createdBy: actor.id,
    documentId,
    totalItems: Math.max(1, record.chunksCount),
    plannedDurationMs: 42_000,
  });
  records[index] = { ...record, bm25Status: 'PENDING', vectorStatus: 'PENDING' };
  saveManaged(records);
  appendAudit({
    actor,
    action: 'REINDEX_DOCUMENT',
    entityType: 'DOCUMENT',
    entityId: documentId,
    entityLabel: record.normalizedTitle,
    summary: 'Создано задание переиндексации документа',
    metadata: { jobId: job.id },
  });
  return job;
}

function bulkUpdateDocuments(request: BulkDocumentRequest): BulkDocumentResult {
  const permission = request.action === 'REINDEX' ? 'DOCUMENT_REINDEX' : 'DOCUMENT_STATUS_CHANGE';
  const actor = mockRepository.requirePermission(permission);
  const uniqueIds = [...new Set(request.documentIds)];
  if (uniqueIds.length === 0 || uniqueIds.length > 100) {
    throw new ApiError('Выберите от 1 до 100 документов.', 422, 'VALIDATION_ERROR');
  }
  const reason = request.reason?.trim() ?? '';
  if (request.action === 'HIDE' && reason.length < 3) {
    throw new ApiError('Укажите причину массового скрытия.', 422, 'VALIDATION_ERROR');
  }
  const records = managedRecords();
  const jobs = refreshJobs();
  const batchId = makeId('batch');
  const items: BulkDocumentResult['items'] = [];
  for (const documentId of uniqueIds) {
    const index = records.findIndex((record) => record.documentId === documentId);
    const record = records[index];
    if (!record) {
      items.push({ documentId, outcome: 'FAILED', reason: 'Документ не найден' });
      continue;
    }
    if (request.action === 'HIDE') {
      if (!['ACTIVE', 'OUTDATED'].includes(record.status)) {
        items.push({ documentId, outcome: 'SKIPPED', reason: 'Несовместимый статус' });
        continue;
      }
      records[index] = {
        ...record,
        status: 'HIDDEN',
        hiddenReason: reason.slice(0, 500),
        lastEditedAt: now(),
        lastEditedBy: actor.id,
        version: record.version + 1,
      };
      items.push({ documentId, outcome: 'SUCCESS' });
      continue;
    }
    if (request.action === 'RESTORE') {
      if (record.status !== 'HIDDEN') {
        items.push({ documentId, outcome: 'SKIPPED', reason: 'Документ не скрыт' });
        continue;
      }
      records[index] = {
        ...record,
        status: 'ACTIVE',
        hiddenReason: undefined,
        lastEditedAt: now(),
        lastEditedBy: actor.id,
        version: record.version + 1,
      };
      items.push({ documentId, outcome: 'SUCCESS' });
      continue;
    }
    const active = jobs.find(
      (job) =>
        job.documentId === documentId &&
        job.type === 'DOCUMENT_REINDEX' &&
        (job.status === 'QUEUED' || job.status === 'RUNNING'),
    );
    if (active) {
      items.push({
        documentId,
        outcome: 'SKIPPED',
        reason: 'Задание уже активно',
        jobId: active.id,
      });
      continue;
    }
    const job = createJob({
      type: 'DOCUMENT_REINDEX',
      documentId,
      createdBy: actor.id,
      totalItems: Math.max(1, record.chunksCount),
      plannedDurationMs: 42_000,
    });
    jobs.push(job);
    records[index] = { ...record, bm25Status: 'PENDING', vectorStatus: 'PENDING' };
    items.push({ documentId, outcome: 'SUCCESS', jobId: job.id });
  }
  saveManaged(records);
  const result: BulkDocumentResult = {
    batchId,
    action: request.action,
    successCount: items.filter((item) => item.outcome === 'SUCCESS').length,
    skippedCount: items.filter((item) => item.outcome === 'SKIPPED').length,
    failedCount: items.filter((item) => item.outcome === 'FAILED').length,
    items,
  };
  const action =
    request.action === 'HIDE'
      ? 'BULK_HIDE_DOCUMENTS'
      : request.action === 'RESTORE'
        ? 'BULK_RESTORE_DOCUMENTS'
        : 'BULK_REINDEX_DOCUMENTS';
  appendAudit({
    actor,
    action,
    entityType: 'DOCUMENT_BATCH',
    entityId: batchId,
    entityLabel: `${uniqueIds.length} документов`,
    batchId,
    summary: `Массовая операция: успешно ${result.successCount}, пропущено ${result.skippedCount}`,
    metadata: {
      documentIds: uniqueIds,
      reason: reason || null,
      successCount: result.successCount,
      skippedCount: result.skippedCount,
      failedCount: result.failedCount,
    },
  });
  return result;
}

function filterJobs(filters: JobFilters, allJobs: BackgroundJob[]): JobsResponse {
  let items = allJobs
    .filter((job) => !filters.id || job.id.includes(filters.id.trim()))
    .filter((job) => filters.type === 'ALL' || job.type === filters.type)
    .filter((job) => filters.status === 'ALL' || job.status === filters.status)
    .filter((job) => filters.stage === 'ALL' || job.stage === filters.stage)
    .filter((job) => !filters.actor || job.createdBy === filters.actor)
    .filter((job) => !filters.documentId || job.documentId?.includes(filters.documentId))
    .filter((job) => !filters.source || job.sourceId === filters.source)
    .filter((job) => !filters.dateFrom || job.createdAt >= filters.dateFrom)
    .filter((job) => !filters.dateTo || job.createdAt <= filters.dateTo);
  items = items.sort((left, right) => {
    if (filters.sort === 'created_asc') return left.createdAt.localeCompare(right.createdAt);
    if (filters.sort === 'progress_desc') return right.progress - left.progress;
    return right.createdAt.localeCompare(left.createdAt);
  });
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / filters.limit));
  const offset = (filters.page - 1) * filters.limit;
  return {
    items: items.slice(offset, offset + filters.limit),
    pagination: { page: filters.page, pageSize: filters.limit, total, totalPages },
  };
}

function getEditorJobs(filters: JobFilters): JobsResponse {
  mockRepository.requirePermission('EDITOR_JOBS_VIEW');
  return filterJobs(filters, refreshJobs());
}

function getAdminJobs(filters: JobFilters): JobsResponse {
  mockRepository.requirePermission('ADMIN_JOBS_MANAGE');
  return filterJobs(filters, refreshJobs());
}

function getAdminJob(jobId: string): BackgroundJob {
  mockRepository.requirePermission('ADMIN_JOBS_MANAGE');
  const job = refreshJobs().find((item) => item.id === jobId);
  if (!job) throw new ApiError('Задание не найдено.', 404, 'NOT_FOUND');
  return job;
}

function cancelJob(jobId: string): BackgroundJob {
  const actor = mockRepository.requirePermission('ADMIN_JOBS_MANAGE');
  const jobs = refreshJobs();
  const index = jobs.findIndex((job) => job.id === jobId);
  const job = jobs[index];
  if (!job) throw new ApiError('Задание не найдено.', 404, 'NOT_FOUND');
  if (!job.cancellable || !['QUEUED', 'RUNNING'].includes(job.status)) {
    throw new ApiError('Это задание нельзя отменить.', 409, 'CONFLICT');
  }
  const updated: BackgroundJob = {
    ...job,
    status: 'CANCELLED',
    finishedAt: now(),
    durationMs: job.startedAt ? Math.max(0, Date.now() - Date.parse(job.startedAt)) : 0,
    cancellable: false,
  };
  jobs[index] = updated;
  saveJobs(jobs);
  if (job.sourceId) {
    const sources = storedSources();
    const sourceIndex = sources.findIndex((source) => source.id === job.sourceId);
    const source = sources[sourceIndex];
    if (source) {
      sources[sourceIndex] = {
        ...source,
        status: 'PAUSED',
        currentJobId: undefined,
        updatedAt: now(),
      };
      saveSources(sources);
    }
  }
  appendAudit({
    actor,
    action: 'CANCEL_JOB',
    entityType: 'JOB',
    entityId: job.id,
    entityLabel: job.type,
    summary: 'Фоновое задание отменено',
    before: { status: job.status },
    after: { status: updated.status },
  });
  return updated;
}

function retryJob(jobId: string): BackgroundJob {
  const actor = mockRepository.requirePermission('ADMIN_JOBS_MANAGE');
  const original = refreshJobs().find((job) => job.id === jobId);
  if (!original) throw new ApiError('Задание не найдено.', 404, 'NOT_FOUND');
  if (!['FAILED', 'CANCELLED'].includes(original.status)) {
    throw new ApiError('Повторить можно только неудачное или отменённое задание.', 409, 'CONFLICT');
  }
  const job = createJob({
    type: original.type,
    createdBy: actor.id,
    totalItems: original.totalItems,
    plannedDurationMs: original.plannedDurationMs,
    sourceId: original.sourceId,
    documentId: original.documentId,
    retryOfJobId: original.id,
  });
  appendAudit({
    actor,
    action: 'RETRY_JOB',
    entityType: 'JOB',
    entityId: job.id,
    entityLabel: job.type,
    summary: 'Создан повтор фонового задания',
    metadata: { retryOfJobId: original.id },
  });
  return job;
}

function startFullReindex(): BackgroundJob {
  const actor = mockRepository.requirePermission('ADMIN_JOBS_MANAGE');
  const active = refreshJobs().find(
    (job) => job.type === 'FULL_REINDEX' && (job.status === 'QUEUED' || job.status === 'RUNNING'),
  );
  if (active) {
    throw new ApiError('Полная переиндексация уже выполняется.', 409, 'CONFLICT', {
      jobId: active.id,
    });
  }
  const job = createJob({
    type: 'FULL_REINDEX',
    createdBy: actor.id,
    totalItems: managedRecords().reduce((sum, record) => sum + record.chunksCount, 0),
    plannedDurationMs: 300_000,
  });
  appendAudit({
    actor,
    action: 'START_FULL_REINDEX',
    entityType: 'JOB',
    entityId: job.id,
    entityLabel: 'Полная переиндексация',
    summary: 'Запущена полная переиндексация',
  });
  return job;
}

function getEditorDashboard(): EditorDashboard {
  mockRepository.requirePermission('EDITOR_ACCESS');
  const documents = managedRecords().map(toManaged);
  const jobs = refreshJobs();
  const statusCounts = {
    ACTIVE: 0,
    HIDDEN: 0,
    PENDING: 0,
    FAILED: 0,
    OUTDATED: 0,
  } satisfies Record<DocumentStatus, number>;
  for (const document of documents) statusCounts[document.status] += 1;
  return {
    totalDocuments: documents.length,
    statusCounts,
    bm25Failed: documents.filter((document) => document.bm25Status === 'FAILED').length,
    vectorFailed: documents.filter((document) => document.vectorStatus === 'FAILED').length,
    activeJobs: jobs.filter((job) => ['QUEUED', 'RUNNING'].includes(job.status)).length,
    completedJobsLastDay: jobs.filter(
      (job) =>
        job.status === 'COMPLETED' && Date.now() - Date.parse(job.finishedAt ?? '') < 86_400_000,
    ).length,
    attentionDocuments: documents
      .filter(
        (document) =>
          ['FAILED', 'OUTDATED', 'PENDING'].includes(document.status) ||
          document.bm25Status === 'FAILED' ||
          document.vectorStatus === 'FAILED',
      )
      .slice(0, 5),
    recentlyEditedDocuments: [...documents]
      .sort((left, right) =>
        (right.lastEditedAt ?? right.lastSyncedAt).localeCompare(
          left.lastEditedAt ?? left.lastSyncedAt,
        ),
      )
      .slice(0, 5),
    recentJobs: [...jobs]
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
      .slice(0, 5),
    recentFailedJobs: jobs
      .filter((job) => job.status === 'FAILED')
      .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
      .slice(0, 5),
  };
}

function getSources(filters: SourceFilters): SourcesResponse {
  mockRepository.requirePermission('SOURCES_MANAGE');
  refreshJobs();
  const search = filters.q.trim().toLocaleLowerCase('ru-RU');
  const items = storedSources()
    .filter(
      (source) =>
        !search ||
        source.name.toLocaleLowerCase('ru-RU').includes(search) ||
        source.site.toLocaleLowerCase('ru-RU').includes(search),
    )
    .filter((source) => filters.status === 'ALL' || source.status === filters.status)
    .filter((source) => filters.enabled === 'all' || String(source.enabled) === filters.enabled);
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / filters.limit));
  const offset = (filters.page - 1) * filters.limit;
  return {
    items: items.slice(offset, offset + filters.limit),
    pagination: { page: filters.page, pageSize: filters.limit, total, totalPages },
  };
}

function getSource(id: string): Source {
  mockRepository.requirePermission('SOURCES_MANAGE');
  refreshJobs();
  const source = storedSources().find((item) => item.id === id);
  if (!source) throw new ApiError('Источник не найден.', 404, 'NOT_FOUND');
  return source;
}

function validateSourceUpdate(update: SourceUpdateRequest): void {
  if (
    update.targetDocuments !== undefined &&
    (!Number.isInteger(update.targetDocuments) ||
      update.targetDocuments < 5_000 ||
      update.targetDocuments > 100_000)
  ) {
    throw new ApiError('Лимит документов должен быть от 5000 до 100000.', 422, 'VALIDATION_ERROR');
  }
  if (
    update.maxAdditionalAnswers !== undefined &&
    (!Number.isInteger(update.maxAdditionalAnswers) ||
      update.maxAdditionalAnswers < 0 ||
      update.maxAdditionalAnswers > 3)
  ) {
    throw new ApiError(
      'Число дополнительных ответов должно быть от 0 до 3.',
      422,
      'VALIDATION_ERROR',
    );
  }
  if (
    update.pageSize !== undefined &&
    (!Number.isInteger(update.pageSize) || update.pageSize < 1 || update.pageSize > 100)
  ) {
    throw new ApiError('Размер страницы должен быть от 1 до 100.', 422, 'VALIDATION_ERROR');
  }
}

function updateSource(id: string, update: SourceUpdateRequest): Source {
  const actor = mockRepository.requirePermission('SOURCES_MANAGE');
  validateSourceUpdate(update);
  const sources = storedSources();
  const index = sources.findIndex((source) => source.id === id);
  const source = sources[index];
  if (!source) throw new ApiError('Источник не найден.', 404, 'NOT_FOUND');
  if (update.enabled === false && source.status === 'SYNCING') {
    throw new ApiError('Сначала остановите синхронизацию.', 409, 'CONFLICT');
  }
  const updated: Source = {
    ...source,
    ...update,
    status:
      update.enabled === false
        ? 'DISABLED'
        : update.enabled === true && source.status === 'DISABLED'
          ? 'IDLE'
          : source.status,
    updatedAt: now(),
  };
  sources[index] = updated;
  saveSources(sources);
  appendAudit({
    actor,
    action: 'UPDATE_SOURCE',
    entityType: 'SOURCE',
    entityId: id,
    entityLabel: source.name,
    summary: 'Обновлены настройки источника',
    before: {
      targetDocuments: source.targetDocuments,
      maxAdditionalAnswers: source.maxAdditionalAnswers,
      pageSize: source.pageSize,
      enabled: source.enabled,
    },
    after: {
      targetDocuments: updated.targetDocuments,
      maxAdditionalAnswers: updated.maxAdditionalAnswers,
      pageSize: updated.pageSize,
      enabled: updated.enabled,
    },
  });
  return updated;
}

function testSourceConnection(id: string): SourceConnectionResult {
  const actor = mockRepository.requirePermission('SOURCES_MANAGE');
  const sources = storedSources();
  const index = sources.findIndex((source) => source.id === id);
  const source = sources[index];
  if (!source) throw new ApiError('Источник не найден.', 404, 'NOT_FOUND');
  const checkedAt = now();
  sources[index] = { ...source, lastCheckAt: checkedAt, updatedAt: checkedAt };
  saveSources(sources);
  appendAudit({
    actor,
    action: 'TEST_SOURCE',
    entityType: 'SOURCE',
    entityId: id,
    entityLabel: source.name,
    summary: 'Mock-подключение к источнику успешно проверено',
  });
  return {
    sourceId: id,
    success: true,
    latencyMs: 84,
    checkedAt,
    message: 'Источник отвечает, синтетическая квота доступна.',
  };
}

function startSourceSync(id: string): BackgroundJob {
  const actor = mockRepository.requirePermission('SOURCES_MANAGE');
  const sources = storedSources();
  const index = sources.findIndex((source) => source.id === id);
  const source = sources[index];
  if (!source) throw new ApiError('Источник не найден.', 404, 'NOT_FOUND');
  if (!source.enabled || source.status === 'DISABLED') {
    throw new ApiError('Отключённый источник нельзя синхронизировать.', 409, 'CONFLICT');
  }
  const active = refreshJobs().find(
    (job) =>
      job.sourceId === id &&
      job.type === 'SOURCE_SYNC' &&
      ['QUEUED', 'RUNNING'].includes(job.status),
  );
  if (active) {
    throw new ApiError('Синхронизация источника уже выполняется.', 409, 'CONFLICT', {
      jobId: active.id,
    });
  }
  const job = createJob({
    type: 'SOURCE_SYNC',
    sourceId: id,
    createdBy: actor.id,
    totalItems: source.targetDocuments,
    plannedDurationMs: 180_000,
  });
  sources[index] = {
    ...source,
    status: 'SYNCING',
    currentJobId: job.id,
    lastSyncAt: now(),
    updatedAt: now(),
  };
  saveSources(sources);
  appendAudit({
    actor,
    action: 'START_SOURCE_SYNC',
    entityType: 'SOURCE',
    entityId: id,
    entityLabel: source.name,
    summary: 'Запущена синхронизация источника',
    metadata: { jobId: job.id },
  });
  return job;
}

function stopSourceSync(id: string): BackgroundJob {
  const actor = mockRepository.requirePermission('SOURCES_MANAGE');
  const sources = storedSources();
  const index = sources.findIndex((source) => source.id === id);
  const source = sources[index];
  if (!source) throw new ApiError('Источник не найден.', 404, 'NOT_FOUND');
  const jobs = refreshJobs();
  const jobIndex = jobs.findIndex(
    (job) =>
      job.sourceId === id &&
      job.type === 'SOURCE_SYNC' &&
      ['QUEUED', 'RUNNING'].includes(job.status),
  );
  const job = jobs[jobIndex];
  if (!job) throw new ApiError('Активная синхронизация не найдена.', 409, 'CONFLICT');
  const updated: BackgroundJob = {
    ...job,
    status: 'CANCELLED',
    finishedAt: now(),
    durationMs: job.startedAt ? Math.max(0, Date.now() - Date.parse(job.startedAt)) : 0,
    cancellable: false,
  };
  jobs[jobIndex] = updated;
  saveJobs(jobs);
  sources[index] = { ...source, status: 'PAUSED', currentJobId: undefined, updatedAt: now() };
  saveSources(sources);
  appendAudit({
    actor,
    action: 'STOP_SOURCE_SYNC',
    entityType: 'SOURCE',
    entityId: id,
    entityLabel: source.name,
    summary: 'Синхронизация источника остановлена',
    metadata: { jobId: job.id },
  });
  return updated;
}

function getAuditEvents(filters: AuditFilters): AuditEventsResponse {
  mockRepository.requirePermission('AUDIT_VIEW');
  const search = filters.q.trim().toLocaleLowerCase('ru-RU');
  let items = readAuditEvents()
    .filter(
      (event) =>
        !search ||
        event.summary.toLocaleLowerCase('ru-RU').includes(search) ||
        event.entityLabel.toLocaleLowerCase('ru-RU').includes(search) ||
        event.requestId.toLocaleLowerCase('ru-RU').includes(search),
    )
    .filter((event) => !filters.actor || event.actorUserId === filters.actor)
    .filter((event) => filters.role === 'ALL' || event.actorRole === filters.role)
    .filter((event) => filters.action === 'ALL' || event.action === filters.action)
    .filter((event) => filters.entityType === 'ALL' || event.entityType === filters.entityType)
    .filter((event) => filters.outcome === 'ALL' || event.outcome === filters.outcome)
    .filter((event) => !filters.dateFrom || event.createdAt >= filters.dateFrom)
    .filter((event) => !filters.dateTo || event.createdAt <= filters.dateTo);
  items = items.sort((left, right) =>
    filters.sort === 'created_asc'
      ? left.createdAt.localeCompare(right.createdAt)
      : right.createdAt.localeCompare(left.createdAt),
  );
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / filters.limit));
  const offset = (filters.page - 1) * filters.limit;
  return {
    items: items.slice(offset, offset + filters.limit),
    pagination: { page: filters.page, pageSize: filters.limit, total, totalPages },
  };
}

function getAuditEvent(eventId: string): AuditEvent {
  mockRepository.requirePermission('AUDIT_VIEW');
  const event = readAuditEvents().find((item) => item.id === eventId);
  if (!event) throw new ApiError('Событие аудита не найдено.', 404, 'NOT_FOUND');
  return event;
}

function systemStatus(lastCheckAt = now()): SystemStatus {
  const documents = managedRecords();
  return {
    services: [
      ['frontend', 'Frontend', 'ONLINE', 4, '1.3.0', 'Vite production bundle готов'],
      ['api', 'Backend API', 'ONLINE', 18, 'mock', 'Работает mock adapter'],
      ['postgresql', 'PostgreSQL', 'ONLINE', 7, '16.3', 'Синтетический статус'],
      ['qdrant', 'Qdrant', 'ONLINE', 12, '1.9', 'Синтетический статус'],
      ['ollama', 'Ollama', 'DEGRADED', 34, '0.2', 'Модель доступна в mock-режиме'],
      ['crawler', 'Crawler', 'ONLINE', 21, 'mock', 'Ожидает задания'],
      ['indexer', 'Indexer', 'ONLINE', 16, 'mock', 'Очередь доступна'],
      ['bm25', 'BM25 index', 'ONLINE', 9, 'v1', 'Индекс готов'],
      ['vector', 'Vector index', 'ONLINE', 14, 'v1', 'Индекс готов'],
      ['embedding', 'Embedding model', 'ONLINE', 27, 'bge-m3', 'Mock telemetry'],
      ['reranker', 'Reranker', 'STARTING', 31, 'bge-reranker', 'Прогрев модели'],
    ].map(([id, name, status, latencyMs, version, message]) => ({
      id: String(id),
      name: String(name),
      status: status as 'ONLINE' | 'DEGRADED' | 'OFFLINE' | 'STARTING',
      latencyMs: Number(latencyMs),
      version: String(version),
      lastCheckAt,
      message: String(message),
    })),
    metrics: {
      cpuUsage: 34,
      ramUsageGb: 17.8,
      vramUsageGb: 7.4,
      diskUsageGb: 21.6,
      databaseSizeGb: 3.2,
      vectorIndexSizeGb: 7.8,
      modelSizeGb: 6.4,
      dockerImagesEstimateGb: 4.1,
      documentsCount: 25_000,
      chunksCount: documents.reduce((sum, document) => sum + document.chunksCount, 0) + 82_000,
      applicationVersion: '1.3.0-mock',
    },
    hardware: {
      operatingSystem: 'Ubuntu',
      cpu: 'Intel Core i5-13400F',
      ramGb: 32,
      gpu: 'NVIDIA RTX 3080 Ti',
      vramGb: 12,
      projectDiskLimitGb: 35,
    },
    lastCheckAt,
  };
}

function getSystemStatus(): SystemStatus {
  mockRepository.requirePermission('SYSTEM_VIEW');
  const value = readUnknown(window.localStorage, mockStorageKeys.systemStatus);
  if (isStoredSystemStatus(value)) return value;
  const status = systemStatus('2026-07-15T08:10:00.000Z');
  writeJson(window.localStorage, mockStorageKeys.systemStatus, status);
  return status;
}

function runSystemHealthCheck(): SystemStatus {
  const actor = mockRepository.requirePermission('SYSTEM_VIEW');
  const status = systemStatus();
  writeJson(window.localStorage, mockStorageKeys.systemStatus, status);
  const job = createJob({
    type: 'HEALTH_CHECK',
    createdBy: actor.id,
    totalItems: status.services.length,
    plannedDurationMs: 4_000,
  });
  appendAudit({
    actor,
    action: 'HEALTH_CHECK',
    entityType: 'SYSTEM',
    entityId: 'services',
    entityLabel: 'Состояние сервисов',
    summary: 'Выполнена проверка состояния mock-сервисов',
    metadata: { jobId: job.id },
  });
  return status;
}

function getSystemSettings(): SystemSettings {
  mockRepository.requirePermission('SYSTEM_SETTINGS_MANAGE');
  return settings();
}

function getPublicAccessPolicy() {
  const value = settings();
  return {
    allowGuestSearch: value.allowGuestSearch,
    allowGuestRag: value.allowGuestRag,
    ragSourcesLimit: value.ragSourcesLimit,
  };
}

function validateSettings(value: SystemSettings): void {
  const valid =
    Number.isInteger(value.searchCandidatesLimit) &&
    value.searchCandidatesLimit >= 20 &&
    value.searchCandidatesLimit <= 1_000 &&
    Number.isInteger(value.rerankerLimit) &&
    value.rerankerLimit >= 5 &&
    value.rerankerLimit <= 200 &&
    Number.isInteger(value.ragSourcesLimit) &&
    value.ragSourcesLimit >= 1 &&
    value.ragSourcesLimit <= 10 &&
    value.defaultMinimumConfidence >= 0 &&
    value.defaultMinimumConfidence <= 1 &&
    Number.isInteger(value.historyRetentionDays) &&
    value.historyRetentionDays >= 7 &&
    value.historyRetentionDays <= 3_650 &&
    Number.isInteger(value.auditRetentionDays) &&
    value.auditRetentionDays >= 30 &&
    value.auditRetentionDays <= 3_650;
  if (!valid)
    throw new ApiError('Проверьте допустимые диапазоны настроек.', 422, 'VALIDATION_ERROR');
}

function updateSystemSettings(update: SystemSettingsUpdate): SystemSettings {
  const actor = mockRepository.requirePermission('SYSTEM_SETTINGS_MANAGE');
  const previous = settings();
  const updated: SystemSettings = { ...previous, ...update, updatedAt: now(), updatedBy: actor.id };
  validateSettings(updated);
  writeJson(window.localStorage, mockStorageKeys.systemSettings, updated);
  appendAudit({
    actor,
    action: 'UPDATE_SYSTEM_SETTINGS',
    entityType: 'SYSTEM',
    entityId: 'settings',
    entityLabel: 'Системные настройки',
    summary: 'Обновлены системные настройки',
    before: {
      allowGuestSearch: previous.allowGuestSearch,
      allowGuestRag: previous.allowGuestRag,
      ragSourcesLimit: previous.ragSourcesLimit,
    },
    after: {
      allowGuestSearch: updated.allowGuestSearch,
      allowGuestRag: updated.allowGuestRag,
      ragSourcesLimit: updated.ragSourcesLimit,
    },
  });
  return updated;
}

function getAdminDashboard(): AdminDashboard {
  mockRepository.requirePermission('ADMIN_ACCESS');
  const users = mockRepository.getAdminUsers({
    q: '',
    role: 'ALL',
    status: 'ALL',
    registeredFrom: '',
    registeredTo: '',
    sort: 'created_desc',
    page: 1,
    limit: 100,
  }).items;
  const documents = managedRecords();
  const jobs = refreshJobs();
  const completed = jobs.filter((job) => job.status === 'COMPLETED').length;
  const finished = jobs.filter((job) =>
    ['COMPLETED', 'FAILED', 'CANCELLED'].includes(job.status),
  ).length;
  const histories = users.flatMap((user) => mockRepository.getHistoryForAdmin(user.id));
  const lastDay = histories.filter((item) => Date.now() - Date.parse(item.createdAt) <= 86_400_000);
  const tags = mockDocuments.flatMap((document) => document.tags.map((tag) => tag.slug));
  const tagCounts = new Map<string, number>();
  for (const tag of tags) tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1);
  return {
    totalUsers: users.length,
    activeUsers: users.filter((user) => user.accountStatus === 'ACTIVE').length,
    blockedUsers: users.filter((user) => user.accountStatus === 'BLOCKED').length,
    usersByRole: {
      USER: users.filter((user) => user.role === 'USER').length,
      EDITOR: users.filter((user) => user.role === 'EDITOR').length,
      ADMIN: users.filter((user) => user.role === 'ADMIN').length,
    },
    documentsCount: 25_000,
    chunksCount: 82_460,
    searchesLastDay: lastDay.filter((item) => item.view === 'documents').length,
    ragLastDay: lastDay.filter((item) => item.view === 'answer').length,
    averageSearchMs: 72,
    averageRagMs: 886,
    jobSuccessRate: finished ? Math.round((completed / finished) * 100) : 100,
    indexSizeGb: 7.8,
    lastSyncAt: storedSources()[0]?.lastSuccessfulSyncAt,
    querySeries: Array.from({ length: 7 }, (_, index) => ({
      date: new Date(Date.now() - (6 - index) * 86_400_000).toISOString().slice(0, 10),
      searches: 72 + index * 13,
      ragRequests: 28 + index * 7,
    })),
    documentStatuses: (['ACTIVE', 'HIDDEN', 'PENDING', 'FAILED', 'OUTDATED'] as const).map(
      (status) => ({
        status,
        count: documents.filter((document) => document.status === status).length,
      }),
    ),
    popularTags: [...tagCounts.entries()]
      .map(([tag, count]) => ({ tag, count }))
      .sort((left, right) => right.count - left.count)
      .slice(0, 7),
  };
}

export const mockManagementRepository = {
  initialize,
  getPublicDocuments,
  getPublicDocument,
  getEditorDashboard,
  getManagedDocuments,
  getManagedDocument,
  updateDocumentMetadata,
  hideDocument,
  restoreDocument,
  reindexDocument,
  bulkUpdateDocuments,
  getEditorJobs,
  getAdminDashboard,
  getSources,
  getSource,
  updateSource,
  testSourceConnection,
  startSourceSync,
  stopSourceSync,
  getAdminJobs,
  getAdminJob,
  retryJob,
  cancelJob,
  startFullReindex,
  getAuditEvents,
  getAuditEvent,
  getSystemStatus,
  runSystemHealthCheck,
  getSystemSettings,
  updateSystemSettings,
  getPublicAccessPolicy,
};
