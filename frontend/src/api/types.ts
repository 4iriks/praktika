import type {
  AdminDashboard,
  AdminUser,
  AdminUserDetail,
  AdminUserFilters,
  AdminUsersResponse,
  AskRequest,
  AskResponse,
  AskStreamOptions,
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
  JobFilters,
  JobEventsResponse,
  JobsResponse,
  LoginRequest,
  ManagedDocumentDetail,
  ManagedDocumentFilters,
  ManagedDocumentsResponse,
  ManagedDocumentUpdate,
  IngestionFailureFilters,
  IngestionFailuresResponse,
  IngestionStats,
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

export interface ApiClient {
  searchDocuments(request: SearchRequest, signal?: AbortSignal): Promise<SearchResponse>;
  askQuestion(request: AskRequest, options?: AskStreamOptions): Promise<AskResponse>;
  getDocument(documentId: string, signal?: AbortSignal): Promise<Document>;

  register(request: RegisterRequest): Promise<User>;
  login(request: LoginRequest): Promise<User>;
  logout(): Promise<void>;
  getCurrentUser(): Promise<User | null>;
  updateCurrentUser(request: UpdateProfileRequest): Promise<User>;
  getUserStats(signal?: AbortSignal): Promise<UserStats>;

  getHistory(filters: HistoryFilters, signal?: AbortSignal): Promise<HistoryResponse>;
  deleteHistoryItem(historyId: string): Promise<void>;
  clearHistory(): Promise<void>;

  getSavedDocuments(
    filters: SavedDocumentsFilters,
    signal?: AbortSignal,
  ): Promise<SavedDocumentsResponse>;
  saveDocument(documentId: string): Promise<SavedDocument>;
  unsaveDocument(documentId: string): Promise<void>;

  sendFeedback(request: FeedbackRequest): Promise<Feedback>;
  deleteFeedback(feedbackId: string): Promise<void>;
  getFeedbackForResponse(responseId: string, signal?: AbortSignal): Promise<Feedback | null>;

  getPublicSystemStatus(signal?: AbortSignal): Promise<PublicSystemStatus>;
  getPublicAccessPolicy(signal?: AbortSignal): Promise<PublicAccessPolicy>;

  getEditorDashboard(signal?: AbortSignal): Promise<EditorDashboard>;
  getManagedDocuments(
    filters: ManagedDocumentFilters,
    signal?: AbortSignal,
  ): Promise<ManagedDocumentsResponse>;
  getManagedDocument(documentId: string, signal?: AbortSignal): Promise<ManagedDocumentDetail>;
  getManagedDocumentChunks(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<DocumentChunksResponse>;
  getManagedDocumentRevisions(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<DocumentRevisionsResponse>;
  getManagedDocumentFailures(
    documentId: string,
    signal?: AbortSignal,
  ): Promise<IngestionFailuresResponse>;
  updateDocumentMetadata(
    documentId: string,
    request: ManagedDocumentUpdate,
  ): Promise<ManagedDocumentDetail>;
  hideDocument(documentId: string, reason: string): Promise<ManagedDocumentDetail>;
  restoreDocument(documentId: string): Promise<ManagedDocumentDetail>;
  reindexDocument(documentId: string): Promise<BackgroundJob>;
  bulkUpdateDocuments(request: BulkDocumentRequest): Promise<BulkDocumentResult>;
  getEditorJobs(filters: JobFilters, signal?: AbortSignal): Promise<JobsResponse>;
  getEditorJobEvents(jobId: string, signal?: AbortSignal): Promise<JobEventsResponse>;

  getAdminDashboard(signal?: AbortSignal): Promise<AdminDashboard>;
  getAdminUsers(filters: AdminUserFilters, signal?: AbortSignal): Promise<AdminUsersResponse>;
  getAdminUser(userId: string, signal?: AbortSignal): Promise<AdminUserDetail>;
  updateUserRole(userId: string, request: ChangeRoleRequest): Promise<AdminUser>;
  blockUser(userId: string, request: BlockUserRequest): Promise<AdminUser>;
  unblockUser(userId: string): Promise<AdminUser>;

  getSources(filters: SourceFilters, signal?: AbortSignal): Promise<SourcesResponse>;
  getSource(sourceId: string, signal?: AbortSignal): Promise<Source>;
  updateSource(sourceId: string, request: SourceUpdateRequest): Promise<Source>;
  testSourceConnection(sourceId: string): Promise<SourceConnectionResult>;
  getSourceSyncState(sourceId: string, signal?: AbortSignal): Promise<SourceSyncState>;
  startSourceSync(sourceId: string, request?: SourceSyncRequest): Promise<BackgroundJob>;
  stopSourceSync(sourceId: string): Promise<BackgroundJob>;
  getIngestionStats(signal?: AbortSignal): Promise<IngestionStats>;
  getIngestionFailures(
    filters: IngestionFailureFilters,
    signal?: AbortSignal,
  ): Promise<IngestionFailuresResponse>;
  getIngestionFailure(failureId: string, signal?: AbortSignal): Promise<IngestionFailure>;

  getAdminJobs(filters: JobFilters, signal?: AbortSignal): Promise<JobsResponse>;
  getAdminJob(jobId: string, signal?: AbortSignal): Promise<BackgroundJob>;
  getAdminJobEvents(jobId: string, signal?: AbortSignal): Promise<JobEventsResponse>;
  retryJob(jobId: string): Promise<BackgroundJob>;
  cancelJob(jobId: string): Promise<BackgroundJob>;
  startFullReindex(): Promise<BackgroundJob>;

  getAuditEvents(filters: AuditFilters, signal?: AbortSignal): Promise<AuditEventsResponse>;
  getAuditEvent(eventId: string, signal?: AbortSignal): Promise<AuditEvent>;

  getSystemStatus(signal?: AbortSignal): Promise<SystemStatus>;
  runSystemHealthCheck(): Promise<SystemStatus>;
  getSystemSettings(signal?: AbortSignal): Promise<SystemSettings>;
  updateSystemSettings(request: SystemSettingsUpdate): Promise<SystemSettings>;
}
