import type {
  AskRequest,
  AskResponse,
  AdminDashboard,
  AdminUser,
  AdminUserDetail,
  AdminUserFilters,
  AdminUsersResponse,
  AuditEvent,
  AuditEventsResponse,
  AuditFilters,
  BackgroundJob,
  BlockUserRequest,
  BulkDocumentRequest,
  BulkDocumentResult,
  ChangeRoleRequest,
  Document,
  DocumentChunksResponse,
  DocumentRevisionsResponse,
  EditorDashboard,
  Feedback,
  FeedbackRequest,
  HistoryFilters,
  HistoryResponse,
  IngestionFailure,
  IngestionFailureFilters,
  IngestionFailuresResponse,
  IngestionStats,
  JobEventsResponse,
  JobFilters,
  JobsResponse,
  LoginRequest,
  ManagedDocumentDetail,
  ManagedDocumentFilters,
  ManagedDocumentsResponse,
  ManagedDocumentUpdate,
  PublicAccessPolicy,
  PublicSystemStatus,
  RegisterRequest,
  SavedDocument,
  SavedDocumentsFilters,
  SavedDocumentsResponse,
  SearchRequest,
  SearchResponse,
  SearchIndexStats,
  SearchIndexVersion,
  SearchIndexVersionsResponse,
  Source,
  SourceConnectionResult,
  SourceFilters,
  SourceSyncRequest,
  SourceSyncState,
  SourcesResponse,
  SourceUpdateRequest,
  SystemSettings,
  SystemSettingsUpdate,
  SystemStatus,
  UpdateProfileRequest,
  User,
  UserStats,
} from '../types';
import { ApiError } from './ApiError';
import type { ApiClient } from './types';

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api').replace(
  /\/$/,
  '',
);

interface BackendErrorPayload {
  error?: {
    code?: unknown;
    message?: unknown;
    details?: unknown;
    requestId?: unknown;
  };
  code?: unknown;
  message?: unknown;
  details?: unknown;
  requestId?: unknown;
}

interface CsrfPayload {
  csrfToken: string;
}

const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
const apiErrorCodes = new Set([
  'BAD_REQUEST',
  'UNAUTHORIZED',
  'FORBIDDEN',
  'CSRF_INVALID',
  'NOT_FOUND',
  'CONFLICT',
  'VALIDATION_ERROR',
  'RATE_LIMITED',
  'SERVICE_UNAVAILABLE',
  'SEARCH_ENGINE_NOT_READY',
  'RAG_ENGINE_NOT_READY',
  'INTERNAL_ERROR',
]);
let csrfToken: string | null = null;
const unauthorizedListeners = new Set<() => void>();

export function subscribeToUnauthorized(listener: () => void): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

function notifyUnauthorized(): void {
  unauthorizedListeners.forEach((listener) => listener());
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

async function responseError(response: Response): Promise<ApiError> {
  let message = response.statusText || 'Сервис временно недоступен.';
  let code: ConstructorParameters<typeof ApiError>[2];
  let details: ConstructorParameters<typeof ApiError>[3];
  let requestId: string | undefined;
  try {
    const payload = (await response.json()) as BackendErrorPayload;
    const envelope = isObject(payload.error) ? payload.error : payload;
    if (typeof envelope.message === 'string') message = envelope.message;
    if (typeof envelope.code === 'string' && apiErrorCodes.has(envelope.code)) {
      code = envelope.code as ConstructorParameters<typeof ApiError>[2];
    }
    if (isObject(envelope.details)) {
      details = envelope.details as ConstructorParameters<typeof ApiError>[3];
    }
    if (typeof envelope.requestId === 'string') requestId = envelope.requestId;
  } catch {
    // A non-JSON gateway error still becomes the same typed ApiError.
  }
  return new ApiError(message, response.status, code, details, requestId);
}

async function refreshCsrf(signal?: AbortSignal): Promise<string> {
  const response = await fetch(baseUrl + '/auth/csrf', {
    credentials: 'include',
    headers: { Accept: 'application/json' },
    signal,
  });
  if (!response.ok) throw await responseError(response);
  const payload = (await response.json()) as CsrfPayload;
  if (typeof payload.csrfToken !== 'string' || !payload.csrfToken) {
    throw new ApiError('Сервис вернул некорректный CSRF-токен.', 500, 'INTERNAL_ERROR');
  }
  csrfToken = payload.csrfToken;
  return csrfToken;
}

async function request<T>(path: string, init: RequestInit = {}, csrfRetried = false): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const unsafe = unsafeMethods.has(method);
  const token = unsafe ? (csrfToken ?? (await refreshCsrf(init.signal ?? undefined))) : null;
  const response = await fetch(baseUrl + path, {
    credentials: 'include',
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'X-CSRF-Token': token } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    const error = await responseError(response);
    if (unsafe && error.code === 'CSRF_INVALID' && !csrfRetried) {
      csrfToken = null;
      await refreshCsrf(init.signal ?? undefined);
      return request<T>(path, init, true);
    }
    if (response.status === 401) notifyUnauthorized();
    throw error;
  }

  if (path === '/auth/login' || path === '/auth/register' || path === '/auth/logout') {
    csrfToken = null;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function resetHttpSecurityStateForTests(): void {
  csrfToken = null;
  unauthorizedListeners.clear();
}

function searchQuery(value: SearchRequest): string {
  const params = new URLSearchParams({
    q: value.q,
    view: value.view,
    mode: value.mode,
    page: String(value.page),
    page_size: String(value.pageSize),
    sort: value.filters.sort,
    min_score: String(value.filters.minScore),
    accepted: String(value.filters.acceptedOnly),
    has_code: String(value.filters.hasCodeOnly),
  });
  if (value.filters.tags.length > 0) params.set('tags', value.filters.tags.join(','));
  return params.toString();
}

function historyQuery(filters: HistoryFilters): string {
  return new URLSearchParams({
    search: filters.search,
    view: filters.view,
    mode: filters.mode,
    date_sort: filters.dateSort,
    page: String(filters.page),
    page_size: String(filters.pageSize),
  }).toString();
}

function savedQuery(filters: SavedDocumentsFilters): string {
  const params = new URLSearchParams({
    search: filters.search,
    sort: filters.sort,
    page: String(filters.page),
    page_size: String(filters.pageSize),
  });
  if (filters.tags.length > 0) params.set('tags', filters.tags.join(','));
  return params.toString();
}

function managedDocumentsQuery(filters: ManagedDocumentFilters): string {
  const params = new URLSearchParams({
    q: filters.q,
    status: filters.status,
    accepted: filters.accepted,
    has_code: filters.hasCode,
    bm25: filters.bm25,
    vector: filters.vector,
    source: filters.source,
    updated_after: filters.updatedAfter,
    sort: filters.sort,
    page: String(filters.page),
    limit: String(filters.limit),
  });
  if (filters.tags.length > 0) params.set('tags', filters.tags.join(','));
  return params.toString();
}

function jobsQuery(filters: JobFilters): string {
  return new URLSearchParams({
    id: filters.id,
    type: filters.type,
    status: filters.status,
    stage: filters.stage,
    actor: filters.actor,
    document_id: filters.documentId,
    source: filters.source,
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    sort: filters.sort,
    page: String(filters.page),
    limit: String(filters.limit),
  }).toString();
}

function usersQuery(filters: AdminUserFilters): string {
  return new URLSearchParams({
    q: filters.q,
    role: filters.role,
    status: filters.status,
    registered_from: filters.registeredFrom,
    registered_to: filters.registeredTo,
    sort: filters.sort,
    page: String(filters.page),
    limit: String(filters.limit),
  }).toString();
}

function sourcesQuery(filters: SourceFilters): string {
  return new URLSearchParams({
    q: filters.q,
    status: filters.status,
    enabled: filters.enabled,
    page: String(filters.page),
    limit: String(filters.limit),
  }).toString();
}

function auditQuery(filters: AuditFilters): string {
  return new URLSearchParams({
    q: filters.q,
    actor: filters.actor,
    role: filters.role,
    action: filters.action,
    entity_type: filters.entityType,
    outcome: filters.outcome,
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    sort: filters.sort,
    page: String(filters.page),
    limit: String(filters.limit),
  }).toString();
}

function ingestionFailuresQuery(filters: IngestionFailureFilters): string {
  const params = new URLSearchParams({
    retryable: filters.retryable ?? 'all',
    resolved: filters.resolved ?? 'all',
    sort: filters.sort ?? 'created_desc',
    page: String(filters.page),
    limit: String(filters.limit),
  });
  if (filters.sourceId) params.set('source_id', filters.sourceId);
  if (filters.jobId) params.set('job_id', filters.jobId);
  if (filters.documentId) params.set('document_id', filters.documentId);
  if (filters.externalId) params.set('external_id', filters.externalId);
  if (filters.errorCode) params.set('error_code', filters.errorCode);
  return params.toString();
}

export const httpApi: ApiClient = {
  searchDocuments(value, signal) {
    return request<SearchResponse>('/search?' + searchQuery(value), { signal });
  },
  async askQuestion(value: AskRequest, options = {}) {
    const response = await request<AskResponse>('/ask', {
      method: 'POST',
      body: JSON.stringify(value),
      signal: options.signal,
    });
    options.onStage?.('complete');
    options.onChunk?.(response.answer);
    return response;
  },
  getDocument(documentId, signal) {
    return request<Document>('/documents/' + encodeURIComponent(documentId), { signal });
  },
  register(value: RegisterRequest) {
    return request<User>('/auth/register', { method: 'POST', body: JSON.stringify(value) });
  },
  login(value: LoginRequest) {
    return request<User>('/auth/login', { method: 'POST', body: JSON.stringify(value) });
  },
  logout() {
    return request<void>('/auth/logout', { method: 'POST' });
  },
  getCurrentUser() {
    return request<User | null>('/auth/me');
  },
  updateCurrentUser(value: UpdateProfileRequest) {
    return request<User>('/users/me', { method: 'PATCH', body: JSON.stringify(value) });
  },
  getUserStats(signal) {
    return request<UserStats>('/users/me/stats', { signal });
  },
  getHistory(filters, signal) {
    return request<HistoryResponse>('/history?' + historyQuery(filters), { signal });
  },
  deleteHistoryItem(historyId) {
    return request<void>('/history/' + encodeURIComponent(historyId), { method: 'DELETE' });
  },
  clearHistory() {
    return request<void>('/history', { method: 'DELETE' });
  },
  getSavedDocuments(filters, signal) {
    return request<SavedDocumentsResponse>('/saved?' + savedQuery(filters), { signal });
  },
  saveDocument(documentId) {
    return request<SavedDocument>('/saved/' + encodeURIComponent(documentId), { method: 'POST' });
  },
  unsaveDocument(documentId) {
    return request<void>('/saved/' + encodeURIComponent(documentId), { method: 'DELETE' });
  },
  sendFeedback(value: FeedbackRequest) {
    return request<Feedback>('/feedback', { method: 'POST', body: JSON.stringify(value) });
  },
  deleteFeedback(feedbackId) {
    return request<void>('/feedback/' + encodeURIComponent(feedbackId), { method: 'DELETE' });
  },
  getFeedbackForResponse(responseId, signal) {
    return request<Feedback | null>('/feedback/by-response/' + encodeURIComponent(responseId), {
      signal,
    });
  },
  getPublicSystemStatus(signal) {
    return request<PublicSystemStatus>('/status', { signal });
  },
  getPublicAccessPolicy(signal) {
    return request<PublicAccessPolicy>('/system/public-policy', { signal });
  },
  getEditorDashboard(signal) {
    return request<EditorDashboard>('/editor/dashboard', { signal });
  },
  getManagedDocuments(filters, signal) {
    return request<ManagedDocumentsResponse>(
      '/editor/documents?' + managedDocumentsQuery(filters),
      { signal },
    );
  },
  getManagedDocument(documentId, signal) {
    return request<ManagedDocumentDetail>('/editor/documents/' + encodeURIComponent(documentId), {
      signal,
    });
  },
  getManagedDocumentChunks(documentId, signal) {
    return request<DocumentChunksResponse>(
      '/editor/documents/' + encodeURIComponent(documentId) + '/chunks',
      { signal },
    );
  },
  getManagedDocumentRevisions(documentId, signal) {
    return request<DocumentRevisionsResponse>(
      '/editor/documents/' + encodeURIComponent(documentId) + '/revisions',
      { signal },
    );
  },
  getManagedDocumentFailures(documentId, signal) {
    return request<IngestionFailuresResponse>(
      '/editor/documents/' + encodeURIComponent(documentId) + '/failures',
      { signal },
    );
  },
  updateDocumentMetadata(documentId, value: ManagedDocumentUpdate) {
    return request<ManagedDocumentDetail>(
      '/editor/documents/' + encodeURIComponent(documentId) + '/metadata',
      { method: 'PATCH', body: JSON.stringify(value) },
    );
  },
  hideDocument(documentId, reason) {
    return request<ManagedDocumentDetail>(
      '/editor/documents/' + encodeURIComponent(documentId) + '/hide',
      { method: 'POST', body: JSON.stringify({ reason }) },
    );
  },
  restoreDocument(documentId) {
    return request<ManagedDocumentDetail>(
      '/editor/documents/' + encodeURIComponent(documentId) + '/restore',
      { method: 'POST' },
    );
  },
  reindexDocument(documentId) {
    return request<BackgroundJob>(
      '/editor/documents/' + encodeURIComponent(documentId) + '/reindex',
      { method: 'POST' },
    );
  },
  bulkUpdateDocuments(value: BulkDocumentRequest) {
    return request<BulkDocumentResult>('/editor/documents/bulk', {
      method: 'POST',
      body: JSON.stringify(value),
    });
  },
  getEditorJobs(filters, signal) {
    return request<JobsResponse>('/editor/jobs?' + jobsQuery(filters), { signal });
  },
  getEditorJobEvents(jobId, signal) {
    return request<JobEventsResponse>('/editor/jobs/' + encodeURIComponent(jobId) + '/events', {
      signal,
    });
  },
  getAdminDashboard(signal) {
    return request<AdminDashboard>('/admin/dashboard', { signal });
  },
  getAdminUsers(filters, signal) {
    return request<AdminUsersResponse>('/admin/users?' + usersQuery(filters), { signal });
  },
  getAdminUser(userId, signal) {
    return request<AdminUserDetail>('/admin/users/' + encodeURIComponent(userId), { signal });
  },
  updateUserRole(userId, value: ChangeRoleRequest) {
    return request<AdminUser>('/admin/users/' + encodeURIComponent(userId) + '/role', {
      method: 'PATCH',
      body: JSON.stringify(value),
    });
  },
  blockUser(userId, value: BlockUserRequest) {
    return request<AdminUser>('/admin/users/' + encodeURIComponent(userId) + '/block', {
      method: 'POST',
      body: JSON.stringify(value),
    });
  },
  unblockUser(userId) {
    return request<AdminUser>('/admin/users/' + encodeURIComponent(userId) + '/unblock', {
      method: 'POST',
    });
  },
  getSources(filters, signal) {
    return request<SourcesResponse>('/admin/sources?' + sourcesQuery(filters), { signal });
  },
  getSource(sourceId, signal) {
    return request<Source>('/admin/sources/' + encodeURIComponent(sourceId), { signal });
  },
  updateSource(sourceId, value: SourceUpdateRequest) {
    return request<Source>('/admin/sources/' + encodeURIComponent(sourceId), {
      method: 'PATCH',
      body: JSON.stringify(value),
    });
  },
  testSourceConnection(sourceId) {
    return request<SourceConnectionResult>(
      '/admin/sources/' + encodeURIComponent(sourceId) + '/test',
      { method: 'POST' },
    );
  },
  getSourceSyncState(sourceId, signal) {
    return request<SourceSyncState>(
      '/admin/sources/' + encodeURIComponent(sourceId) + '/sync-state',
      { signal },
    );
  },
  startSourceSync(sourceId, value?: SourceSyncRequest) {
    return request<BackgroundJob>('/admin/sources/' + encodeURIComponent(sourceId) + '/sync', {
      method: 'POST',
      ...(value ? { body: JSON.stringify(value) } : {}),
    });
  },
  stopSourceSync(sourceId) {
    return request<BackgroundJob>('/admin/sources/' + encodeURIComponent(sourceId) + '/stop', {
      method: 'POST',
    });
  },
  getIngestionStats(signal) {
    return request<IngestionStats>('/admin/ingestion/stats', { signal });
  },
  getIngestionFailures(filters, signal) {
    return request<IngestionFailuresResponse>(
      '/admin/ingestion/failures?' + ingestionFailuresQuery(filters),
      { signal },
    );
  },
  getIngestionFailure(failureId, signal) {
    return request<IngestionFailure>('/admin/ingestion/failures/' + encodeURIComponent(failureId), {
      signal,
    });
  },
  getAdminJobs(filters, signal) {
    return request<JobsResponse>('/admin/jobs?' + jobsQuery(filters), { signal });
  },
  getAdminJob(jobId, signal) {
    return request<BackgroundJob>('/admin/jobs/' + encodeURIComponent(jobId), { signal });
  },
  getAdminJobEvents(jobId, signal) {
    return request<JobEventsResponse>('/admin/jobs/' + encodeURIComponent(jobId) + '/events', {
      signal,
    });
  },
  retryJob(jobId) {
    return request<BackgroundJob>('/admin/jobs/' + encodeURIComponent(jobId) + '/retry', {
      method: 'POST',
    });
  },
  cancelJob(jobId) {
    return request<BackgroundJob>('/admin/jobs/' + encodeURIComponent(jobId) + '/cancel', {
      method: 'POST',
    });
  },
  startFullReindex() {
    return request<BackgroundJob>('/admin/jobs/full-reindex', { method: 'POST' });
  },
  getSearchIndexes(signal) {
    return request<SearchIndexVersionsResponse>('/admin/indexes', { signal });
  },
  getActiveSearchIndex(signal) {
    return request<SearchIndexVersion | null>('/admin/indexes/active', { signal });
  },
  getSearchIndexStats(signal) {
    return request<SearchIndexStats>('/admin/indexes/stats', { signal });
  },
  startSearchIndexFullReindex() {
    return request<BackgroundJob>('/admin/indexes/full-reindex', {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    });
  },
  validateSearchIndex(indexVersionId) {
    return request<BackgroundJob>(
      '/admin/indexes/' + encodeURIComponent(indexVersionId) + '/validate',
      { method: 'POST', body: JSON.stringify({ confirm: true }) },
    );
  },
  cleanupSearchIndexes(dryRun, confirm = false) {
    return request<BackgroundJob>('/admin/indexes/cleanup', {
      method: 'POST',
      body: JSON.stringify({ dryRun, confirm }),
    });
  },
  getAuditEvents(filters, signal) {
    return request<AuditEventsResponse>('/admin/audit?' + auditQuery(filters), { signal });
  },
  getAuditEvent(eventId, signal) {
    return request<AuditEvent>('/admin/audit/' + encodeURIComponent(eventId), { signal });
  },
  getSystemStatus(signal) {
    return request<SystemStatus>('/admin/system', { signal });
  },
  runSystemHealthCheck() {
    return request<SystemStatus>('/admin/system/health-check', { method: 'POST' });
  },
  getSystemSettings(signal) {
    return request<SystemSettings>('/admin/system/settings', { signal });
  },
  updateSystemSettings(value: SystemSettingsUpdate) {
    return request<SystemSettings>('/admin/system/settings', {
      method: 'PATCH',
      body: JSON.stringify(value),
    });
  },
};
