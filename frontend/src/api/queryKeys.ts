import type {
  AdminUserFilters,
  AuditFilters,
  HistoryFilters,
  JobFilters,
  ManagedDocumentFilters,
  RagResponseId,
  SavedDocumentsFilters,
  SourceFilters,
} from '../types';

export const queryKeys = {
  auth: {
    current: ['auth', 'current'] as const,
  },
  user: {
    root: ['user'] as const,
    profile: ['user', 'profile'] as const,
    stats: ['user', 'stats'] as const,
  },
  history: {
    root: ['history'] as const,
    list: (filters: HistoryFilters) => ['history', 'list', filters] as const,
  },
  saved: {
    root: ['saved'] as const,
    list: (filters: SavedDocumentsFilters) => ['saved', 'list', filters] as const,
  },
  feedback: {
    root: ['feedback'] as const,
    response: (responseId: RagResponseId) => ['feedback', 'response', responseId] as const,
  },
  search: {
    root: ['search'] as const,
  },
  document: {
    root: ['document'] as const,
    detail: (documentId: string) => ['document', documentId] as const,
  },
  system: {
    status: ['system-status'] as const,
    publicPolicy: ['public-policy'] as const,
  },
  editor: {
    root: ['editor'] as const,
    dashboard: ['editor', 'dashboard'] as const,
    documents: (filters: ManagedDocumentFilters) => ['editor', 'documents', filters] as const,
    document: (documentId: string) => ['editor', 'document', documentId] as const,
    jobs: (filters: JobFilters) => ['editor', 'jobs', filters] as const,
  },
  admin: {
    root: ['admin'] as const,
    dashboard: ['admin', 'dashboard'] as const,
    users: (filters: AdminUserFilters) => ['admin', 'users', filters] as const,
    user: (userId: string) => ['admin', 'user', userId] as const,
    sources: (filters: SourceFilters) => ['admin', 'sources', filters] as const,
    source: (sourceId: string) => ['admin', 'source', sourceId] as const,
    jobs: (filters: JobFilters) => ['admin', 'jobs', filters] as const,
    job: (jobId: string) => ['admin', 'job', jobId] as const,
    audit: (filters: AuditFilters) => ['admin', 'audit', filters] as const,
    auditEvent: (eventId: string) => ['admin', 'audit-event', eventId] as const,
    systemStatus: ['admin', 'system-status'] as const,
    systemSettings: ['admin', 'system-settings'] as const,
  },
};
