import type {
  AskRequest,
  AskResponse,
  Document,
  Feedback,
  FeedbackRequest,
  HistoryFilters,
  HistoryResponse,
  LoginRequest,
  RegisterRequest,
  SavedDocument,
  SavedDocumentsFilters,
  SavedDocumentsResponse,
  SearchRequest,
  SearchResponse,
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
    } catch {
      message = response.statusText || message;
    }
    throw new ApiError(message, response.status);
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
  getSystemStatus(signal) {
    return request<SystemStatus>('/status', { signal });
  },
};
