import { ApiError } from '../api/ApiError';
import type { ApiClient } from '../api/types';
import type {
  AskRequest,
  AskResponse,
  AskStreamOptions,
  Document,
  FeedbackRequest,
  HistoryFilters,
  LoginRequest,
  RagSource,
  RegisterRequest,
  SavedDocument,
  SavedDocumentsFilters,
  SavedDocumentsResponse,
  SearchRequest,
  SearchResponse,
  SearchResult,
  SearchIndexVersion,
  UpdateProfileRequest,
} from '../types';
import { clamp } from '../utils/format';
import { emptyFilters } from '../utils/searchParams';
import { mockSystemStatus } from './data';
import { mockManagementRepository } from './mockManagementRepository';
import { mockRepository } from './mockRepository';

async function initializeData(): Promise<void> {
  await mockRepository.initialize();
  mockManagementRepository.initialize();
}

const stopWords = new Set([
  'как',
  'что',
  'это',
  'для',
  'или',
  'при',
  'где',
  'почему',
  'между',
  'через',
  'нужно',
  'работает',
  'работать',
  'можно',
  'the',
  'and',
]);

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  const duration = import.meta.env.MODE === 'test' ? Math.min(ms, 5) : ms;
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Операция отменена', 'AbortError'));
      return;
    }
    const timer = window.setTimeout(resolve, duration);
    signal?.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer);
        reject(new DOMException('Операция отменена', 'AbortError'));
      },
      { once: true },
    );
  });
}

function maybeFail(): void {
  if (import.meta.env.VITE_MOCK_FORCE_ERROR === 'true') {
    throw new ApiError(
      'Mock API принудительно вернул ошибку. Отключите VITE_MOCK_FORCE_ERROR.',
      503,
    );
  }
}

function tokenize(value: string): string[] {
  return value
    .toLocaleLowerCase('ru-RU')
    .replace(/[^\p{L}\p{N}_]+/gu, ' ')
    .split(/\s+/)
    .map((token) => token.trim())
    .filter((token) => token.length > 1 && !stopWords.has(token));
}

function searchableText(document: Document): string {
  return [
    document.title,
    document.question.body,
    document.answers.map((answer) => answer.body).join(' '),
    document.tags.map((tag) => tag.name + ' ' + tag.slug).join(' '),
  ]
    .join(' ')
    .toLocaleLowerCase('ru-RU');
}

function relevanceFor(document: Document, terms: string[]): number {
  if (terms.length === 0) return 0.45;
  const title = document.title.toLocaleLowerCase('ru-RU');
  const text = searchableText(document);
  let hits = 0;
  let titleHits = 0;
  for (const term of terms) {
    if (text.includes(term)) hits += 1;
    if (title.includes(term)) titleHits += 1;
  }
  if (hits === 0) return 0;
  return clamp((hits / terms.length) * 0.68 + (titleHits / terms.length) * 0.32, 0, 1);
}

function toSearchResult(
  document: Document,
  relevance: number,
  mode: SearchRequest['mode'],
  savedIds: Set<string>,
): SearchResult {
  const sourceScores = document.scores;
  const modeBoost =
    mode === 'bm25'
      ? sourceScores.bm25Score / 16
      : mode === 'vector'
        ? sourceScores.vectorScore
        : (sourceScores.vectorScore + sourceScores.rerankerScore) / 2;
  const finalScore = clamp(relevance * 0.7 + modeBoost * 0.3, 0, 0.999);

  return {
    documentId: document.id,
    title: document.title,
    snippet: document.question.body,
    tags: document.tags,
    sourceUrl: document.sourceUrl,
    publishedAt: document.publishedAt,
    questionScore: document.score,
    answersCount: document.answers.length,
    acceptedAnswer: document.answers.some((answer) => answer.accepted),
    hasCode:
      document.question.codeBlocks.length > 0 ||
      document.answers.some((answer) => answer.codeBlocks.length > 0),
    saved: savedIds.has(document.id),
    bm25Score: Number((sourceScores.bm25Score * (0.72 + relevance * 0.28)).toFixed(3)),
    vectorScore: Number(
      clamp(sourceScores.vectorScore * 0.75 + relevance * 0.25, 0, 0.999).toFixed(3),
    ),
    rerankerScore: Number(
      clamp(sourceScores.rerankerScore * 0.62 + relevance * 0.38, 0, 0.999).toFixed(3),
    ),
    finalScore: Number(finalScore.toFixed(3)),
  };
}

async function searchDocuments(
  request: SearchRequest,
  signal?: AbortSignal,
): Promise<SearchResponse> {
  await initializeData();
  await delay(320, signal);
  maybeFail();
  if (request.q === '__error__') throw new ApiError('Тестовая ошибка поискового индекса.', 503);

  const policy = mockManagementRepository.getPublicAccessPolicy();
  if (!policy.allowGuestSearch && !mockRepository.getOptionalActor()) {
    throw new ApiError('Для поиска необходимо войти.', 401, 'UNAUTHORIZED');
  }
  const terms = tokenize(request.q);
  const savedIds = mockRepository.getSavedDocumentIds();
  let ranked = mockManagementRepository
    .getPublicDocuments()
    .map((document) => ({ document, relevance: relevanceFor(document, terms) }))
    .filter(({ relevance }) => terms.length === 0 || relevance > 0)
    .filter(({ document }) =>
      request.filters.tags.length === 0
        ? true
        : request.filters.tags.every((tag) =>
            document.tags.some((documentTag) => documentTag.slug === tag),
          ),
    )
    .filter(({ document }) => document.score >= request.filters.minScore)
    .filter(({ document }) =>
      request.filters.acceptedOnly ? document.answers.some((answer) => answer.accepted) : true,
    )
    .filter(({ document }) =>
      request.filters.hasCodeOnly
        ? document.question.codeBlocks.length > 0 ||
          document.answers.some((answer) => answer.codeBlocks.length > 0)
        : true,
    )
    .map(({ document, relevance }) => ({
      document,
      result: toSearchResult(document, relevance, request.mode, savedIds),
    }));

  ranked = ranked.sort((left, right) => {
    if (request.filters.sort === 'date') {
      return Date.parse(right.document.publishedAt) - Date.parse(left.document.publishedAt);
    }
    if (request.filters.sort === 'score') return right.document.score - left.document.score;
    return right.result.finalScore - left.result.finalScore;
  });

  const total = ranked.length;
  const totalPages = Math.max(1, Math.ceil(total / request.pageSize));
  const offset = (request.page - 1) * request.pageSize;
  const results = ranked.slice(offset, offset + request.pageSize).map(({ result }) => result);
  const metrics = {
    tookMs: 54 + terms.length * 7,
    candidates: Math.min(120, total * 7 + 18),
    reranked: Math.min(50, total),
    queryTokens: Math.max(1, terms.length + 2),
  };
  const response: SearchResponse = {
    results,
    pagination: { page: request.page, pageSize: request.pageSize, total, totalPages },
    metrics,
  };

  if (request.view === 'documents' && request.page === 1 && request.q.trim()) {
    mockRepository.recordHistory({
      query: request.q,
      view: 'documents',
      mode: request.mode,
      filters: {
        tags: request.filters.tags,
        minScore: request.filters.minScore,
        acceptedOnly: request.filters.acceptedOnly,
        hasCodeOnly: request.filters.hasCodeOnly,
      },
      sort: request.filters.sort,
      pageSize: request.pageSize,
      resultCount: total,
      tookMs: metrics.tookMs,
    });
  }
  return response;
}

function sourceFromResult(result: SearchResult): RagSource {
  return {
    documentId: result.documentId,
    title: result.title,
    snippet: result.snippet,
    sourceUrl: result.sourceUrl,
    tags: result.tags,
    score: result.finalScore,
    saved: result.saved,
  };
}

function buildAnswer(question: string, documents: Document[]): string {
  const primary = documents[0];
  if (!primary) return '';
  const accepted = primary.answers.find((answer) => answer.accepted) ?? primary.answers[0];
  const code = accepted?.codeBlocks[0];
  const fence = String.fromCharCode(96).repeat(3);
  const codeSection = code ? '\n\n' + fence + 'python\n' + code + '\n' + fence : '';
  const secondReference =
    documents.length > 1 ? ' Дополнительные нюансы приведены в источнике [2](#source-2).' : '';

  return (
    '## Короткий ответ\n\n' +
    (accepted?.body ?? primary.question.body) +
    codeSection +
    '\n\n### На что обратить внимание\n\n' +
    '- проверьте версию Python и зависимости окружения;\n' +
    '- обработайте пограничные случаи до интеграции в рабочий код;\n' +
    '- добавьте небольшой воспроизводимый тест.\n\n' +
    'Основной материал: [1](#source-1).' +
    secondReference +
    '\n\n_Запрос: «' +
    question +
    '»._'
  );
}

function responseId(): string {
  return 'rag-' + (globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2));
}

const mockIndexVersion: SearchIndexVersion = {
  id: '00000000-0000-4000-8000-000000000601',
  collectionName: 'pyanswer_chunks_mock_6_1',
  aliasName: 'pyanswer_chunks_current',
  status: 'ACTIVE',
  schemaVersion: '6.1',
  schemaHash: 'mock-schema-hash',
  embeddingProvider: 'ollama',
  embeddingModel: 'qwen3-embedding:0.6b',
  embeddingDimensions: 1024,
  sparseProvider: 'qdrant_bm25',
  sparseModel: 'qdrant/bm25',
  qdrantServerVersion: '1.18.2',
  qdrantClientVersion: '1.18.0',
  pointCount: 0,
  eligibleChunkCount: 0,
  createdAt: new Date(0).toISOString(),
  activatedAt: new Date(0).toISOString(),
  config: {},
};

async function askQuestion(
  request: AskRequest,
  options: AskStreamOptions = {},
): Promise<AskResponse> {
  await initializeData();
  const filters = request.filters ?? emptyFilters;
  maybeFail();
  const policy = mockManagementRepository.getPublicAccessPolicy();
  if (!policy.allowGuestRag && !mockRepository.getOptionalActor()) {
    throw new ApiError('Для ответа ИИ необходимо войти.', 401, 'UNAUTHORIZED');
  }
  options.onStage?.('searching');
  await delay(90, options.signal);
  const search = await searchDocuments(
    {
      q: request.question,
      view: 'answer',
      mode: request.mode,
      page: 1,
      pageSize: Math.min(request.maxSources ?? policy.ragSourcesLimit, policy.ragSourcesLimit),
      filters,
    },
    options.signal,
  );
  options.onStage?.('merging');
  await delay(65, options.signal);
  options.onStage?.('reranking');
  await delay(65, options.signal);
  options.onStage?.('selecting');
  await delay(55, options.signal);

  const selectedResults = search.results.slice(
    0,
    Math.min(request.maxSources ?? policy.ragSourcesLimit, policy.ragSourcesLimit),
  );
  const selectedDocuments = selectedResults
    .map((result) =>
      mockManagementRepository
        .getPublicDocuments()
        .find((document) => document.id === result.documentId),
    )
    .filter((document): document is Document => Boolean(document));
  const insufficientContext = selectedDocuments.length === 0;
  const answer = insufficientContext
    ? 'В базе не найдено достаточно информации для надёжного ответа. Попробуйте уточнить запрос.'
    : buildAnswer(request.question, selectedDocuments);

  options.onStage?.('generating');
  const chunks = answer.match(/(?:\S+\s*){1,5}/g) ?? [answer];
  for (const chunk of chunks) {
    await delay(14, options.signal);
    options.onChunk?.(chunk);
  }
  options.onStage?.('complete');

  const searchTookMs = 186 + tokenize(request.question).length * 8;
  const generationTookMs = insufficientContext ? 84 : 438 + answer.length;
  const response: AskResponse = {
    responseId: responseId(),
    answer,
    sources: selectedResults.map(sourceFromResult),
    model: 'Qwen через Ollama',
    tookMs: searchTookMs + generationTookMs,
    searchTookMs,
    generationTookMs,
    confidence: insufficientContext
      ? 0.18
      : Number(clamp(selectedResults[0]?.finalScore ?? 0.6, 0.45, 0.94).toFixed(2)),
    insufficientContext,
  };
  mockRepository.recordHistory({
    query: request.question,
    view: 'answer',
    mode: request.mode,
    filters: {
      tags: filters.tags,
      minScore: filters.minScore,
      acceptedOnly: filters.acceptedOnly,
      hasCodeOnly: filters.hasCodeOnly,
    },
    sort: filters.sort,
    pageSize: request.pageSize ?? 10,
    resultCount: selectedResults.length,
    tookMs: response.tookMs,
    answerPreview: answer
      .replace(/[#*_[\]()]/g, '')
      .replaceAll(String.fromCharCode(96), '')
      .slice(0, 220),
    insufficientContext,
  });
  return response;
}

async function getDocument(documentId: string, signal?: AbortSignal): Promise<Document> {
  await initializeData();
  await delay(220, signal);
  maybeFail();
  const document = mockManagementRepository.getPublicDocument(documentId);
  return { ...document, saved: mockRepository.getSavedDocumentIds().has(documentId) };
}

function savedDocument(documentId: string, savedAt: string): SavedDocument {
  const document = mockManagementRepository.getPublicDocument(documentId);
  return {
    ...toSearchResult(document, 0.82, 'hybrid', new Set([documentId])),
    savedAt,
  };
}

async function getSavedDocuments(
  filters: SavedDocumentsFilters,
  signal?: AbortSignal,
): Promise<SavedDocumentsResponse> {
  await initializeData();
  await delay(240, signal);
  maybeFail();
  const search = filters.search.trim().toLocaleLowerCase('ru-RU');
  let items = mockRepository
    .getSavedEntries()
    .flatMap((entry) => {
      try {
        return [savedDocument(entry.documentId, entry.savedAt)];
      } catch (error) {
        if (error instanceof ApiError && error.details?.reason === 'DOCUMENT_UNAVAILABLE')
          return [];
        throw error;
      }
    })
    .filter(
      (item) =>
        !search ||
        item.title.toLocaleLowerCase('ru-RU').includes(search) ||
        item.snippet.toLocaleLowerCase('ru-RU').includes(search),
    );
  const availableTags = [
    ...new Map(items.flatMap((item) => item.tags).map((tag) => [tag.slug, tag])).values(),
  ];
  items = items.filter((item) =>
    filters.tags.length === 0
      ? true
      : filters.tags.every((slug) => item.tags.some((tag) => tag.slug === slug)),
  );
  items = items.sort((left, right) => {
    if (filters.sort === 'score') return right.questionScore - left.questionScore;
    if (filters.sort === 'publishedAt') {
      return Date.parse(right.publishedAt) - Date.parse(left.publishedAt);
    }
    return Date.parse(right.savedAt) - Date.parse(left.savedAt);
  });
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / filters.pageSize));
  const offset = (filters.page - 1) * filters.pageSize;
  return {
    items: items.slice(offset, offset + filters.pageSize),
    availableTags,
    pagination: { page: filters.page, pageSize: filters.pageSize, total, totalPages },
  };
}

export const mockApi: ApiClient = {
  searchDocuments,
  askQuestion,
  getDocument,
  async register(value: RegisterRequest) {
    await delay(280);
    maybeFail();
    const user = await mockRepository.register(value);
    mockManagementRepository.initialize();
    return user;
  },
  async login(value: LoginRequest) {
    await delay(280);
    maybeFail();
    const user = await mockRepository.login(value);
    mockManagementRepository.initialize();
    return user;
  },
  async logout() {
    await delay(100);
    mockRepository.logout();
  },
  async getCurrentUser() {
    await delay(80);
    const user = await mockRepository.getCurrentUser();
    mockManagementRepository.initialize();
    return user;
  },
  async updateCurrentUser(value: UpdateProfileRequest) {
    await delay(180);
    maybeFail();
    return mockRepository.updateCurrentUser(value);
  },
  async getUserStats(signal) {
    await delay(120, signal);
    maybeFail();
    return mockRepository.getUserStats();
  },
  async getHistory(filters: HistoryFilters, signal) {
    await delay(220, signal);
    maybeFail();
    return mockRepository.getHistory(filters);
  },
  async deleteHistoryItem(historyId) {
    await delay(120);
    maybeFail();
    mockRepository.deleteHistoryItem(historyId);
  },
  async clearHistory() {
    await delay(140);
    maybeFail();
    mockRepository.clearHistory();
  },
  getSavedDocuments,
  async saveDocument(documentId) {
    await initializeData();
    await delay(140);
    maybeFail();
    mockManagementRepository.getPublicDocument(documentId);
    const entry = mockRepository.saveDocument(documentId);
    return savedDocument(entry.documentId, entry.savedAt);
  },
  async unsaveDocument(documentId) {
    await delay(140);
    maybeFail();
    mockRepository.unsaveDocument(documentId);
  },
  async sendFeedback(value: FeedbackRequest) {
    await delay(120);
    maybeFail();
    return mockRepository.sendFeedback(value);
  },
  async deleteFeedback(feedbackId) {
    await delay(100);
    maybeFail();
    mockRepository.deleteFeedback(feedbackId);
  },
  async getFeedbackForResponse(responseId, signal) {
    await delay(90, signal);
    maybeFail();
    return mockRepository.getFeedbackForResponse(responseId);
  },
  async getPublicSystemStatus(signal) {
    await initializeData();
    await delay(110, signal);
    maybeFail();
    return mockSystemStatus;
  },
  async getPublicAccessPolicy(signal) {
    await initializeData();
    await delay(40, signal);
    return mockManagementRepository.getPublicAccessPolicy();
  },
  async getEditorDashboard(signal) {
    await initializeData();
    await delay(160, signal);
    maybeFail();
    return mockManagementRepository.getEditorDashboard();
  },
  async getManagedDocuments(filters, signal) {
    await initializeData();
    await delay(180, signal);
    maybeFail();
    return mockManagementRepository.getManagedDocuments(filters);
  },
  async getManagedDocument(documentId, signal) {
    await initializeData();
    await delay(140, signal);
    maybeFail();
    return mockManagementRepository.getManagedDocument(documentId);
  },
  async getManagedDocumentChunks(documentId, signal) {
    await initializeData();
    await delay(110, signal);
    return mockManagementRepository.getManagedDocumentChunks(documentId);
  },
  async getManagedDocumentRevisions(documentId, signal) {
    await initializeData();
    await delay(110, signal);
    return mockManagementRepository.getManagedDocumentRevisions(documentId);
  },
  async getManagedDocumentFailures(documentId, signal) {
    await initializeData();
    await delay(100, signal);
    return mockManagementRepository.getManagedDocumentFailures(documentId);
  },
  async updateDocumentMetadata(documentId, request) {
    await initializeData();
    await delay(160);
    maybeFail();
    return mockManagementRepository.updateDocumentMetadata(documentId, request);
  },
  async hideDocument(documentId, reason) {
    await initializeData();
    await delay(140);
    maybeFail();
    return mockManagementRepository.hideDocument(documentId, reason);
  },
  async restoreDocument(documentId) {
    await initializeData();
    await delay(140);
    maybeFail();
    return mockManagementRepository.restoreDocument(documentId);
  },
  async reindexDocument(documentId) {
    await initializeData();
    await delay(140);
    maybeFail();
    return mockManagementRepository.reindexDocument(documentId);
  },
  async bulkUpdateDocuments(request) {
    await initializeData();
    await delay(190);
    maybeFail();
    return mockManagementRepository.bulkUpdateDocuments(request);
  },
  async getEditorJobs(filters, signal) {
    await initializeData();
    await delay(140, signal);
    maybeFail();
    return mockManagementRepository.getEditorJobs(filters);
  },
  async getEditorJobEvents(jobId, signal) {
    await initializeData();
    await delay(90, signal);
    return mockManagementRepository.getEditorJobEvents(jobId);
  },
  async getAdminDashboard(signal) {
    await initializeData();
    await delay(180, signal);
    maybeFail();
    return mockManagementRepository.getAdminDashboard();
  },
  async getAdminUsers(filters, signal) {
    await initializeData();
    await delay(170, signal);
    maybeFail();
    return mockRepository.getAdminUsers(filters);
  },
  async getAdminUser(userId, signal) {
    await initializeData();
    await delay(130, signal);
    maybeFail();
    return mockRepository.getAdminUser(userId);
  },
  async updateUserRole(userId, request) {
    await initializeData();
    await delay(150);
    maybeFail();
    return mockRepository.updateUserRole(userId, request);
  },
  async blockUser(userId, request) {
    await initializeData();
    await delay(150);
    maybeFail();
    return mockRepository.blockUser(userId, request);
  },
  async unblockUser(userId) {
    await initializeData();
    await delay(140);
    maybeFail();
    return mockRepository.unblockUser(userId);
  },
  async getSources(filters, signal) {
    await initializeData();
    await delay(150, signal);
    maybeFail();
    return mockManagementRepository.getSources(filters);
  },
  async getSource(sourceIdValue, signal) {
    await initializeData();
    await delay(110, signal);
    maybeFail();
    return mockManagementRepository.getSource(sourceIdValue);
  },
  async updateSource(sourceIdValue, request) {
    await initializeData();
    await delay(150);
    maybeFail();
    return mockManagementRepository.updateSource(sourceIdValue, request);
  },
  async testSourceConnection(sourceIdValue) {
    await initializeData();
    await delay(180);
    maybeFail();
    return mockManagementRepository.testSourceConnection(sourceIdValue);
  },
  async getSourceSyncState(sourceIdValue, signal) {
    await initializeData();
    await delay(90, signal);
    return mockManagementRepository.getSourceSyncState(sourceIdValue);
  },
  async startSourceSync(sourceIdValue, request) {
    await initializeData();
    await delay(150);
    maybeFail();
    return mockManagementRepository.startSourceSync(sourceIdValue, request);
  },
  async stopSourceSync(sourceIdValue) {
    await initializeData();
    await delay(150);
    maybeFail();
    return mockManagementRepository.stopSourceSync(sourceIdValue);
  },
  async getIngestionStats(signal) {
    await initializeData();
    await delay(110, signal);
    return mockManagementRepository.getIngestionStats();
  },
  async getIngestionFailures(filters, signal) {
    await initializeData();
    await delay(110, signal);
    return mockManagementRepository.getIngestionFailures(filters);
  },
  async getIngestionFailure(failureId, signal) {
    await initializeData();
    await delay(90, signal);
    return mockManagementRepository.getIngestionFailure(failureId);
  },
  async getAdminJobs(filters, signal) {
    await initializeData();
    await delay(140, signal);
    maybeFail();
    return mockManagementRepository.getAdminJobs(filters);
  },
  async getAdminJob(jobId, signal) {
    await initializeData();
    await delay(100, signal);
    maybeFail();
    return mockManagementRepository.getAdminJob(jobId);
  },
  async getAdminJobEvents(jobId, signal) {
    await initializeData();
    await delay(90, signal);
    return mockManagementRepository.getAdminJobEvents(jobId);
  },
  async retryJob(jobId) {
    await initializeData();
    await delay(130);
    maybeFail();
    return mockManagementRepository.retryJob(jobId);
  },
  async cancelJob(jobId) {
    await initializeData();
    await delay(130);
    maybeFail();
    return mockManagementRepository.cancelJob(jobId);
  },
  async startFullReindex() {
    await initializeData();
    await delay(150);
    maybeFail();
    return mockManagementRepository.startFullReindex();
  },
  async getSearchIndexes(signal) {
    await initializeData();
    await delay(80, signal);
    return {
      items: [mockIndexVersion],
      pagination: { page: 1, pageSize: 20, total: 1, totalPages: 1 },
    };
  },
  async getActiveSearchIndex(signal) {
    await initializeData();
    await delay(60, signal);
    return mockIndexVersion;
  },
  async getSearchIndexStats(signal) {
    await initializeData();
    await delay(80, signal);
    return {
      aliasName: mockIndexVersion.aliasName,
      aliasTarget: mockIndexVersion.collectionName,
      activeVersion: mockIndexVersion,
      eligibleChunks: 0,
      indexedChunks: 0,
      staleChunks: 0,
      pointsCount: 0,
      qdrantOnline: false,
      qdrantVersion: mockIndexVersion.qdrantServerVersion,
      qdrantMessage: 'Mock-режим не подключается к Qdrant',
      embeddingProvider: 'ollama',
      embeddingModel: mockIndexVersion.embeddingModel,
      embeddingDimensions: 1024,
      embeddingOnline: false,
      embeddingModelInstalled: false,
      indexerOnline: false,
    };
  },
  async startSearchIndexFullReindex() {
    await initializeData();
    return mockManagementRepository.startFullReindex();
  },
  async validateSearchIndex() {
    await initializeData();
    return mockManagementRepository.startFullReindex();
  },
  async cleanupSearchIndexes() {
    await initializeData();
    return mockManagementRepository.startFullReindex();
  },
  async getAuditEvents(filters, signal) {
    await initializeData();
    await delay(150, signal);
    maybeFail();
    return mockManagementRepository.getAuditEvents(filters);
  },
  async getAuditEvent(eventId, signal) {
    await initializeData();
    await delay(100, signal);
    maybeFail();
    return mockManagementRepository.getAuditEvent(eventId);
  },
  async getSystemStatus(signal) {
    await initializeData();
    await delay(130, signal);
    maybeFail();
    return mockManagementRepository.getSystemStatus();
  },
  async runSystemHealthCheck() {
    await initializeData();
    await delay(190);
    maybeFail();
    return mockManagementRepository.runSystemHealthCheck();
  },
  async getSystemSettings(signal) {
    await initializeData();
    await delay(110, signal);
    maybeFail();
    return mockManagementRepository.getSystemSettings();
  },
  async updateSystemSettings(request) {
    await initializeData();
    await delay(150);
    maybeFail();
    return mockManagementRepository.updateSystemSettings(request);
  },
};
