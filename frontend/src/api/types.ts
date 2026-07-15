import type {
  AskRequest,
  AskResponse,
  AskStreamOptions,
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

  getSystemStatus(signal?: AbortSignal): Promise<SystemStatus>;
}
