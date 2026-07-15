export type UserRole = 'USER' | 'EDITOR' | 'ADMIN';
export type AccountStatus = 'ACTIVE' | 'BLOCKED';
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
  preferences: UserPreferences;
}

export type AuthStatus = 'initializing' | 'authenticated' | 'anonymous';

export interface AuthSession {
  userId: string;
  expiresAt: string;
  mockSessionVersion: 1;
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

export type IndexStatus = 'ready' | 'pending' | 'failed';

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

export type ServiceState = 'online' | 'degraded' | 'offline' | 'ready';

export interface ServiceStatus {
  name: 'API' | 'PostgreSQL' | 'Qdrant' | 'Ollama' | 'Index';
  state: ServiceState;
  latencyMs?: number;
}

export interface SystemStatus {
  services: ServiceStatus[];
  model: string;
  modelContext: number;
  indexedDocuments: number;
  indexedChunks: number;
  updatedAt: string;
}

export interface ApiErrorPayload {
  message: string;
  status?: number;
}
