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
  EditorDashboard,
  Feedback,
  FeedbackRequest,
  HistoryFilters,
  HistoryResponse,
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
  Source,
  SourceConnectionResult,
  SourceFilters,
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(baseUrl + path, {
    credentials: 'include',
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      ...init.headers,
    },
  });

  if (!response.ok) {
    let message = 'Сервис временно недоступен.';
    let code: ConstructorParameters<typeof ApiError>[2];
    let details: ConstructorParameters<typeof ApiError>[3];
    try {
      const payload: unknown = await response.json();
      if (
        typeof payload === 'object' &&
        payload !== null &&
        'message' in payload &&
        typeof payload.message === 'string'
      ) {
        message = payload.message;
      }
      if (
        typeof payload === 'object' &&
        payload !== null &&
        'code' in payload &&
        [
          'BAD_REQUEST',
          'UNAUTHORIZED',
          'FORBIDDEN',
          'NOT_FOUND',
          'CONFLICT',
          'VALIDATION_ERROR',
          'INTERNAL_ERROR',
        ].includes(String(payload.code))
      ) {
        code = payload.code as ConstructorParameters<typeof ApiError>[2];
      }
      if (
        typeof payload === 'object' &&
        payload !== null &&
        'details' in payload &&
        typeof payload.details === 'object' &&
        payload.details !== null
      ) {
        details = payload.details as ConstructorParameters<typeof ApiError>[3];
      }
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(message, response.status, code, details);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
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
  startSourceSync(sourceId) {
    return request<BackgroundJob>('/admin/sources/' + encodeURIComponent(sourceId) + '/sync', {
      method: 'POST',
    });
  },
  stopSourceSync(sourceId) {
    return request<BackgroundJob>('/admin/sources/' + encodeURIComponent(sourceId) + '/stop', {
      method: 'POST',
    });
  },
  getAdminJobs(filters, signal) {
    return request<JobsResponse>('/admin/jobs?' + jobsQuery(filters), { signal });
  },
  getAdminJob(jobId, signal) {
    return request<BackgroundJob>('/admin/jobs/' + encodeURIComponent(jobId), { signal });
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
