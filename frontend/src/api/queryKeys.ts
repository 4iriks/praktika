import type { HistoryFilters, RagResponseId, SavedDocumentsFilters } from '../types';

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
  },
};
