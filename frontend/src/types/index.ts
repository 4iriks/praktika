export type UserRole = 'USER' | 'EDITOR' | 'ADMIN';
export type AccountStatus = 'ACTIVE' | 'BLOCKED';
export type Permission =
  | 'SEARCH_USE'
  | 'RAG_USE'
  | 'PROFILE_MANAGE'
  | 'HISTORY_MANAGE'
  | 'SAVED_MANAGE'
  | 'EDITOR_ACCESS'
  | 'MANAGED_DOCUMENTS_VIEW'
  | 'DOCUMENT_METADATA_EDIT'
  | 'DOCUMENT_STATUS_CHANGE'
  | 'DOCUMENT_REINDEX'
  | 'EDITOR_JOBS_VIEW'
  | 'ADMIN_ACCESS'
  | 'USERS_MANAGE'
  | 'SOURCES_MANAGE'
  | 'ADMIN_JOBS_MANAGE'
  | 'AUDIT_VIEW'
  | 'SYSTEM_VIEW'
  | 'SYSTEM_SETTINGS_MANAGE';
export type PermissionMap = Record<UserRole, readonly Permission[]>;
export type SearchMode = 'bm25' | 'vector' | 'hybrid';
export type SearchView = 'documents' | 'answer';
export type SearchSort = 'relevance' | 'date' | 'score';

export interface UserPreferences {
  defaultSearchMode: SearchMode;
  defaultSearchView: SearchView;
  defaultPageSize: 10 | 20 | 50;
  autoOpenScores: boolean;
  confirmExternalNavigation: boolean;
}

export interface User {
  id: string;
  email: string;
  displayName: string;
  role: UserRole;
  accountStatus: AccountStatus;
  createdAt: string;
  lastActiveAt: string;
  accountVersion: number;
  preferences: UserPreferences;
}

export type AuthStatus = 'initializing' | 'authenticated' | 'anonymous';

export interface AuthSession {
  userId: string;
  expiresAt: string;
  mockSessionVersion: number;
}

export interface RegisterRequest {
  displayName: string;
  email: string;
  password: string;
  acceptedTerms: boolean;
  remember: boolean;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember: boolean;
}

export type LoginCredentials = LoginRequest;

export interface UpdateProfileRequest {
  displayName?: string;
  email?: string;
  preferences?: UserPreferences;
}

export interface UserStats {
  documentSearches: number;
  ragSearches: number;
  savedDocuments: number;
  ratedAnswers: number;
}

export interface Tag {
  name: string;
  slug: string;
}

export interface SearchFilters {
  tags: string[];
  minScore: number;
  acceptedOnly: boolean;
  hasCodeOnly: boolean;
  sort: SearchSort;
}

export interface SearchRequest {
  q: string;
  view: SearchView;
  mode: SearchMode;
  page: number;
  pageSize: number;
  filters: SearchFilters;
}

export interface ScoreBreakdown {
  bm25Score: number;
  vectorScore: number;
  rerankerScore: number;
  finalScore: number;
}

export interface SearchResult extends ScoreBreakdown {
  documentId: string;
  title: string;
  snippet: string;
  tags: Tag[];
  sourceUrl: string;
  publishedAt: string;
  questionScore: number;
  answersCount: number;
  acceptedAnswer: boolean;
  hasCode: boolean;
  saved: boolean;
}

export interface Pagination {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface SearchMetrics {
  tookMs: number;
  candidates: number;
  reranked: number;
  queryTokens: number;
}

export interface SearchResponse {
  results: SearchResult[];
  pagination: Pagination;
  metrics: SearchMetrics;
}

export interface AskRequest {
  question: string;
  mode: SearchMode;
  maxSources?: number;
  documentId?: string;
  filters?: SearchFilters;
  pageSize?: number;
}

export type RagResponseId = string;

export interface RagSource {
  documentId: string;
  title: string;
  snippet: string;
  sourceUrl: string;
  tags: Tag[];
  score: number;
  saved: boolean;
}

export interface AskResponse {
  responseId: RagResponseId;
  answer: string;
  sources: RagSource[];
  model: string;
  tookMs: number;
  searchTookMs: number;
  generationTookMs: number;
  confidence: number;
  insufficientContext: boolean;
}

export type RagStage =
  | 'searching'
  | 'merging'
  | 'reranking'
  | 'selecting'
  | 'generating'
  | 'complete';

export interface AskStreamOptions {
  signal?: AbortSignal;
  onChunk?: (chunk: string) => void;
  onStage?: (stage: RagStage) => void;
}

export interface Question {
  body: string;
  codeBlocks: string[];
}

export interface Answer {
  id: string;
  author: string;
  body: string;
  codeBlocks: string[];
  score: number;
  accepted: boolean;
  createdAt: string;
}

export type IndexStatus = 'READY' | 'PENDING' | 'FAILED' | 'NOT_INDEXED' | 'OUTDATED';

export interface Document {
  id: string;
  title: string;
  sourceUrl: string;
  publishedAt: string;
  author: string;
  views: number;
  score: number;
  tags: Tag[];
  question: Question;
  answers: Answer[];
  chunkCount: number;
  indexedAt: string;
  bm25Status: IndexStatus;
  vectorStatus: IndexStatus;
  contentHash: string;
  saved: boolean;
  scores: ScoreBreakdown;
}

export interface SearchHistoryItem {
  id: string;
  userId: string;
  query: string;
  view: SearchView;
  mode: SearchMode;
  filters: Omit<SearchFilters, 'sort'>;
  sort: SearchSort;
  pageSize: number;
  resultCount: number;
  tookMs: number;
  createdAt: string;
  answerPreview?: string;
  insufficientContext?: boolean;
}

export type HistoryTypeFilter = 'all' | SearchView;
export type HistoryDateSort = 'newest' | 'oldest';

export interface HistoryFilters {
  search: string;
  view: HistoryTypeFilter;
  mode: 'all' | SearchMode;
  dateSort: HistoryDateSort;
  page: number;
  pageSize: number;
}

export interface HistoryResponse {
  items: SearchHistoryItem[];
  pagination: Pagination;
}

export interface SavedDocument extends SearchResult {
  savedAt: string;
}

export type SavedDocumentsSort = 'savedAt' | 'score' | 'publishedAt';

export interface SavedDocumentsFilters {
  search: string;
  tags: string[];
  sort: SavedDocumentsSort;
  page: number;
  pageSize: number;
}

export interface SavedDocumentsResponse {
  items: SavedDocument[];
  availableTags: Tag[];
  pagination: Pagination;
}

export type FeedbackValue = 'positive' | 'negative';
export type FeedbackReason =
  | 'irrelevant_sources'
  | 'factual_error'
  | 'incomplete'
  | 'unclear'
  | 'other';

export interface FeedbackRequest {
  responseId: RagResponseId;
  value: FeedbackValue;
  reason?: FeedbackReason;
  question: string;
  comment?: string;
}

export interface Feedback {
  id: string;
  userId: string;
  responseId: RagResponseId;
  value: FeedbackValue;
  reason?: FeedbackReason;
  question: string;
  comment?: string;
  createdAt: string;
  updatedAt: string;
}

export type PublicServiceState = 'online' | 'degraded' | 'offline' | 'ready';

export interface PublicServiceStatus {
  name: 'API' | 'PostgreSQL' | 'Qdrant' | 'Ollama' | 'Index';
  state: PublicServiceState;
  latencyMs?: number;
}

export interface PublicSystemStatus {
  services: PublicServiceStatus[];
  model: string;
  modelContext: number;
  indexedDocuments: number;
  indexedChunks: number;
  updatedAt: string;
}

export interface ApiErrorPayload {
  message: string;
  status: number;
  code: ApiErrorCode;
  details?: JsonObject;
}

export type ApiErrorCode =
  | 'BAD_REQUEST'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'CSRF_INVALID'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'VALIDATION_ERROR'
  | 'RATE_LIMITED'
  | 'SERVICE_UNAVAILABLE'
  | 'SEARCH_ENGINE_NOT_READY'
  | 'RAG_ENGINE_NOT_READY'
  | 'INTERNAL_ERROR';

export type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];

export interface JsonObject {
  [key: string]: JsonValue;
}

export type DocumentStatus = 'ACTIVE' | 'HIDDEN' | 'PENDING' | 'FAILED' | 'OUTDATED';

export interface ManagedDocument {
  documentId: string;
  status: DocumentStatus;
  bm25Status: IndexStatus;
  vectorStatus: IndexStatus;
  chunksCount: number;
  indexedAt: string;
  lastSyncedAt: string;
  contentHash: string;
  normalizedTitle: string;
  managedTags: string[];
  editorialNote: string;
  failureReason?: string;
  hiddenReason?: string;
  lastEditedBy?: string;
  lastEditedAt?: string;
  version: number;
  sourceId: string;
  original: Document;
}

export type ManagedDocumentSort =
  | 'updated_desc'
  | 'updated_asc'
  | 'rating_desc'
  | 'title_asc'
  | 'status_asc';

export interface ManagedDocumentFilters {
  q: string;
  status: 'ALL' | DocumentStatus;
  tags: string[];
  accepted: 'all' | 'true' | 'false';
  hasCode: 'all' | 'true' | 'false';
  bm25: 'ALL' | IndexStatus;
  vector: 'ALL' | IndexStatus;
  source: string;
  updatedAfter: string;
  sort: ManagedDocumentSort;
  page: number;
  limit: number;
}

export interface ManagedDocumentUpdate {
  normalizedTitle: string;
  managedTags: string[];
  editorialNote: string;
}

export interface ManagedDocumentsResponse {
  items: ManagedDocument[];
  availableTags: string[];
  pagination: Pagination;
}

export interface ManagedDocumentDetail extends ManagedDocument {
  auditEvents: AuditEvent[];
  relatedJobs: BackgroundJob[];
}

export type BulkDocumentAction = 'HIDE' | 'RESTORE' | 'REINDEX';
export type BulkItemOutcome = 'SUCCESS' | 'SKIPPED' | 'FAILED';

export interface BulkDocumentRequest {
  documentIds: string[];
  action: BulkDocumentAction;
  reason?: string;
}

export interface BulkDocumentItemResult {
  documentId: string;
  outcome: BulkItemOutcome;
  reason?: string;
  jobId?: string;
}

export interface BulkDocumentResult {
  batchId: string;
  action: BulkDocumentAction;
  successCount: number;
  skippedCount: number;
  failedCount: number;
  items: BulkDocumentItemResult[];
}

export interface EditorDashboard {
  totalDocuments: number;
  statusCounts: Record<DocumentStatus, number>;
  bm25Failed: number;
  vectorFailed: number;
  activeJobs: number;
  completedJobsLastDay: number;
  attentionDocuments: ManagedDocument[];
  recentlyEditedDocuments: ManagedDocument[];
  recentJobs: BackgroundJob[];
  recentFailedJobs: BackgroundJob[];
}

export type JobType = 'SOURCE_SYNC' | 'DOCUMENT_REINDEX' | 'FULL_REINDEX' | 'HEALTH_CHECK';
export type JobStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
export type JobErrorCode = 'VECTOR_BUILD_FAILED' | 'SOURCE_UNAVAILABLE' | 'INDEX_WRITE_FAILED';
export type JobStage =
  | 'PREPARING'
  | 'CRAWLING'
  | 'CLEANING'
  | 'DEDUPLICATING'
  | 'CHUNKING'
  | 'EMBEDDING'
  | 'INDEXING_BM25'
  | 'INDEXING_VECTOR'
  | 'FINALIZING';

export interface BackgroundJob {
  id: string;
  type: JobType;
  status: JobStatus;
  stage: JobStage;
  progress: number;
  processedItems: number;
  totalItems: number;
  sourceId?: string;
  documentId?: string;
  createdBy: string;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  plannedDurationMs: number;
  errorCode?: JobErrorCode;
  errorMessage?: string;
  retryOfJobId?: string;
  cancellable: boolean;
}

export type JobSort = 'created_desc' | 'created_asc' | 'progress_desc';

export interface JobFilters {
  id: string;
  type: 'ALL' | JobType;
  status: 'ALL' | JobStatus;
  stage: 'ALL' | JobStage;
  actor: string;
  documentId: string;
  source: string;
  dateFrom: string;
  dateTo: string;
  sort: JobSort;
  page: number;
  limit: number;
}

export interface JobsResponse {
  items: BackgroundJob[];
  pagination: Pagination;
}

export interface AdminUser extends User {
  stats: UserStats;
}

export type AdminUserSort = 'created_desc' | 'created_asc' | 'activity_desc' | 'name_asc';

export interface AdminUserFilters {
  q: string;
  role: 'ALL' | UserRole;
  status: 'ALL' | AccountStatus;
  registeredFrom: string;
  registeredTo: string;
  sort: AdminUserSort;
  page: number;
  limit: number;
}

export interface AdminUsersResponse {
  items: AdminUser[];
  pagination: Pagination;
}

export interface AdminUserDetail extends AdminUser {
  recentHistory: SearchHistoryItem[];
  recentAuditEvents: AuditEvent[];
}

export interface ChangeRoleRequest {
  role: UserRole;
}

export interface BlockUserRequest {
  reason: string;
}

export type SourceType = 'STACK_EXCHANGE';
export type SourceStatus = 'IDLE' | 'CHECKING' | 'SYNCING' | 'PAUSED' | 'ERROR' | 'DISABLED';

export interface Source {
  id: string;
  name: string;
  type: SourceType;
  baseUrl: string;
  site: string;
  tag: string;
  enabled: boolean;
  status: SourceStatus;
  targetDocuments: number;
  maxAdditionalAnswers: number;
  pageSize: number;
  documentsCount: number;
  lastSyncAt?: string;
  lastSuccessfulSyncAt?: string;
  lastCheckAt?: string;
  rateLimitRemaining: number;
  rateLimitTotal: number;
  quotaResetAt: string;
  currentJobId?: string;
  lastError?: string;
  apiKeyConfigured: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface SourceFilters {
  q: string;
  status: 'ALL' | SourceStatus;
  enabled: 'all' | 'true' | 'false';
  page: number;
  limit: number;
}

export interface SourcesResponse {
  items: Source[];
  pagination: Pagination;
}

export interface SourceUpdateRequest {
  targetDocuments?: number;
  maxAdditionalAnswers?: number;
  pageSize?: number;
  enabled?: boolean;
}

export interface SourceConnectionResult {
  sourceId: string;
  success: boolean;
  latencyMs: number;
  checkedAt: string;
  message: string;
}

export type AuditAction =
  | 'LOGIN'
  | 'LOGOUT'
  | 'REGISTER'
  | 'UPDATE_PROFILE'
  | 'UPDATE_DOCUMENT_METADATA'
  | 'HIDE_DOCUMENT'
  | 'RESTORE_DOCUMENT'
  | 'REINDEX_DOCUMENT'
  | 'BULK_HIDE_DOCUMENTS'
  | 'BULK_RESTORE_DOCUMENTS'
  | 'BULK_REINDEX_DOCUMENTS'
  | 'CHANGE_USER_ROLE'
  | 'BLOCK_USER'
  | 'UNBLOCK_USER'
  | 'UPDATE_SOURCE'
  | 'TEST_SOURCE'
  | 'START_SOURCE_SYNC'
  | 'STOP_SOURCE_SYNC'
  | 'RETRY_JOB'
  | 'CANCEL_JOB'
  | 'START_FULL_REINDEX'
  | 'HEALTH_CHECK'
  | 'UPDATE_SYSTEM_SETTINGS';

export type AuditEntityType =
  | 'AUTH'
  | 'USER'
  | 'DOCUMENT'
  | 'DOCUMENT_BATCH'
  | 'SOURCE'
  | 'JOB'
  | 'SYSTEM';
export type AuditOutcome = 'SUCCESS' | 'FAILURE';

export interface AuditEvent {
  id: string;
  actorUserId?: string;
  actorName: string;
  actorRole?: UserRole;
  action: AuditAction;
  entityType: AuditEntityType;
  entityId: string;
  entityLabel: string;
  outcome: AuditOutcome;
  ipAddress: string;
  requestId: string;
  batchId?: string;
  createdAt: string;
  summary: string;
  before?: JsonObject;
  after?: JsonObject;
  metadata?: JsonObject;
  errorCode?: ApiErrorCode;
}

export type AuditSort = 'created_desc' | 'created_asc';

export interface AuditFilters {
  q: string;
  actor: string;
  role: 'ALL' | UserRole;
  action: 'ALL' | AuditAction;
  entityType: 'ALL' | AuditEntityType;
  outcome: 'ALL' | AuditOutcome;
  dateFrom: string;
  dateTo: string;
  sort: AuditSort;
  page: number;
  limit: number;
}

export interface AuditEventsResponse {
  items: AuditEvent[];
  pagination: Pagination;
}

export type SystemServiceStatus = 'ONLINE' | 'DEGRADED' | 'OFFLINE' | 'STARTING';

export interface SystemService {
  id: string;
  name: string;
  status: SystemServiceStatus;
  latencyMs: number;
  version: string;
  lastCheckAt: string;
  message: string;
}

export interface SystemMetrics {
  cpuUsage: number;
  ramUsageGb: number;
  vramUsageGb: number;
  diskUsageGb: number;
  databaseSizeGb: number;
  vectorIndexSizeGb: number;
  modelSizeGb: number;
  dockerImagesEstimateGb: number;
  documentsCount: number;
  chunksCount: number;
  applicationVersion: string;
}

export interface SystemHardware {
  operatingSystem: string;
  cpu: string;
  ramGb: number;
  gpu: string;
  vramGb: number;
  projectDiskLimitGb: number;
}

export interface SystemStatus {
  services: SystemService[];
  metrics: SystemMetrics;
  hardware: SystemHardware;
  lastCheckAt: string;
}

export interface SystemSettings {
  searchCandidatesLimit: number;
  rerankerLimit: number;
  ragSourcesLimit: number;
  defaultMinimumConfidence: number;
  allowGuestSearch: boolean;
  allowGuestRag: boolean;
  historyRetentionDays: number;
  auditRetentionDays: number;
  updatedAt: string;
  updatedBy?: string;
}

export type SystemSettingsUpdate = Omit<Partial<SystemSettings>, 'updatedAt' | 'updatedBy'>;

export interface PublicAccessPolicy {
  allowGuestSearch: boolean;
  allowGuestRag: boolean;
  ragSourcesLimit: number;
}

export interface DashboardTimeSeries {
  date: string;
  searches: number;
  ragRequests: number;
}

export interface DashboardTagMetric {
  tag: string;
  count: number;
}

export interface DashboardStatusMetric {
  status: DocumentStatus;
  count: number;
}

export interface AdminDashboard {
  totalUsers: number;
  activeUsers: number;
  blockedUsers: number;
  usersByRole: Record<UserRole, number>;
  documentsCount: number;
  chunksCount: number;
  searchesLastDay: number;
  ragLastDay: number;
  averageSearchMs: number;
  averageRagMs: number;
  jobSuccessRate: number;
  indexSizeGb: number;
  lastSyncAt?: string;
  querySeries: DashboardTimeSeries[];
  documentStatuses: DashboardStatusMetric[];
  popularTags: DashboardTagMetric[];
}
