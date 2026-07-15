import { describe, expect, it } from 'vitest';
import { mockApi } from './mockApi';
import { mockRepository } from './mockRepository';
import { mockStorageKeys } from './mockStorage';
import type { HistoryFilters, SearchHistoryItem, SearchRequest } from '../types';
import { historyItemToParams } from '../utils/searchParams';

const historyFilters: HistoryFilters = {
  search: '',
  view: 'all',
  mode: 'all',
  dateSort: 'newest',
  page: 1,
  pageSize: 20,
};

const searchRequest: SearchRequest = {
  q: 'asyncio',
  view: 'documents',
  mode: 'hybrid',
  page: 1,
  pageSize: 10,
  filters: {
    tags: ['asyncio'],
    minScore: 0,
    acceptedOnly: false,
    hasCodeOnly: true,
    sort: 'relevance',
  },
};

async function register(email: string, displayName = 'Test User') {
  return mockRepository.register({
    displayName,
    email,
    password: 'Strong123',
    acceptedTerms: true,
    remember: true,
  });
}

describe('mock user repository', () => {
  it('успешный поиск создаёт одну дедуплицированную запись истории', async () => {
    await register('history@example.local');
    await mockApi.searchDocuments(searchRequest);
    await mockApi.searchDocuments(searchRequest);
    const history = mockRepository.getHistory(historyFilters);
    expect(history.pagination.total).toBe(1);
    expect(history.items[0]).toMatchObject({
      query: 'asyncio',
      view: 'documents',
      mode: 'hybrid',
    });
    expect(history.items[0]?.resultCount).toEqual(expect.any(Number));
  });

  it('RAG-история сохраняет фильтры и размер страницы для повтора', async () => {
    await register('rag-history@example.local');
    await mockApi.askQuestion({
      question: 'asyncio gather',
      mode: 'vector',
      maxSources: 3,
      pageSize: 20,
      filters: {
        tags: ['asyncio'],
        minScore: 10,
        acceptedOnly: true,
        hasCodeOnly: true,
        sort: 'score',
      },
    });

    const item = mockRepository.getHistory(historyFilters).items[0];
    expect(item).toMatchObject({
      view: 'answer',
      mode: 'vector',
      pageSize: 20,
      sort: 'score',
      filters: {
        tags: ['asyncio'],
        minScore: 10,
        acceptedOnly: true,
        hasCodeOnly: true,
      },
    });
  });

  it('гостевой поиск не создаёт историю будущему пользователю', async () => {
    await mockApi.searchDocuments(searchRequest);
    await register('guest-after-search@example.local');
    expect(mockRepository.getHistory(historyFilters).pagination.total).toBe(0);
  });

  it('повтор из истории восстанавливает все URL-параметры и page=1', () => {
    const item: SearchHistoryItem = {
      id: 'history-1',
      userId: 'user-1',
      query: 'asyncio gather',
      view: 'documents',
      mode: 'vector',
      filters: {
        tags: ['asyncio', 'python'],
        minScore: 50,
        acceptedOnly: true,
        hasCodeOnly: true,
      },
      sort: 'score',
      pageSize: 20,
      resultCount: 4,
      tookMs: 90,
      createdAt: '2026-07-15T12:00:00.000Z',
    };
    const params = historyItemToParams(item);
    expect(params.get('q')).toBe('asyncio gather');
    expect(params.get('mode')).toBe('vector');
    expect(params.get('tags')).toBe('asyncio,python');
    expect(params.get('accepted')).toBe('true');
    expect(params.get('has_code')).toBe('true');
    expect(params.get('min_score')).toBe('50');
    expect(params.get('sort')).toBe('score');
    expect(params.get('page')).toBe('1');
    expect(params.get('page_size')).toBe('20');
  });

  it('повторный save идемпотентен', async () => {
    await register('save@example.local');
    await mockApi.saveDocument('py-1001');
    await mockApi.saveDocument('py-1001');
    const saved = await mockApi.getSavedDocuments({
      search: '',
      tags: [],
      sort: 'savedAt',
      page: 1,
      pageSize: 10,
    });
    expect(saved.pagination.total).toBe(1);
  });

  it('unsave обновляет saved list и состояние документа', async () => {
    await register('unsave@example.local');
    await mockApi.saveDocument('py-1001');
    await mockApi.unsaveDocument('py-1001');
    const saved = await mockApi.getSavedDocuments({
      search: '',
      tags: [],
      sort: 'savedAt',
      page: 1,
      pageSize: 10,
    });
    expect(saved.items).toHaveLength(0);
    expect((await mockApi.getDocument('py-1001')).saved).toBe(false);
  });

  it('изолирует сохранённые документы разных пользователей', async () => {
    await register('first@example.local', 'First User');
    await mockApi.saveDocument('py-1001');
    mockRepository.logout();
    await register('second@example.local', 'Second User');
    expect(mockRepository.getSavedEntries()).toHaveLength(0);
    mockRepository.logout();
    await mockRepository.login({
      email: 'first@example.local',
      password: 'Strong123',
      remember: false,
    });
    expect(mockRepository.getSavedEntries()).toHaveLength(1);
  });

  it('обновляет отображаемое имя профиля', async () => {
    await register('profile@example.local', 'Before Name');
    const updated = mockRepository.updateCurrentUser({ displayName: 'After Name' });
    expect(updated.displayName).toBe('After Name');
    expect((await mockRepository.getCurrentUser())?.displayName).toBe('After Name');
  });

  it('проверяет уникальность нового email без учёта регистра', async () => {
    await register('owner@example.local');
    mockRepository.logout();
    await register('second-owner@example.local');
    expect(() => mockRepository.updateCurrentUser({ email: 'OWNER@EXAMPLE.LOCAL' })).toThrow(
      'Пользователь с таким email уже существует.',
    );
  });

  it('сохраняет positive feedback', async () => {
    await register('positive@example.local');
    const feedback = mockRepository.sendFeedback({
      responseId: 'rag-positive',
      value: 'positive',
      question: 'Вопрос',
    });
    expect(mockRepository.getFeedbackForResponse('rag-positive')).toEqual(feedback);
  });

  it('сохраняет negative feedback с причиной и нормализованным комментарием', async () => {
    await register('negative@example.local');
    const feedback = mockRepository.sendFeedback({
      responseId: 'rag-negative',
      value: 'negative',
      reason: 'factual_error',
      question: 'Вопрос',
      comment: '  Ошибка в примере  ',
    });
    expect(feedback).toMatchObject({
      value: 'negative',
      reason: 'factual_error',
      comment: 'Ошибка в примере',
    });
  });

  it('повторная оценка обновляет feedback без дубликата', async () => {
    await register('feedback-update@example.local');
    const first = mockRepository.sendFeedback({
      responseId: 'rag-update',
      value: 'positive',
      question: 'Вопрос',
    });
    const updated = mockRepository.sendFeedback({
      responseId: 'rag-update',
      value: 'negative',
      reason: 'incomplete',
      question: 'Вопрос',
    });
    expect(updated.id).toBe(first.id);
    expect(updated.value).toBe('negative');
    expect(mockRepository.getUserStats().ratedAnswers).toBe(1);
  });

  it('не хранит пароль в users или session storage', async () => {
    await register('credentials@example.local');
    expect(window.localStorage.getItem(mockStorageKeys.users)).not.toContain('Strong123');
    expect(window.localStorage.getItem(mockStorageKeys.session)).not.toContain('Strong123');
  });

  it('хранит незапомненную сессию минимально и только в sessionStorage', async () => {
    await mockRepository.register({
      displayName: 'Session User',
      email: 'short-session@example.local',
      password: 'Strong123',
      acceptedTerms: true,
      remember: false,
    });
    const stored: unknown = JSON.parse(
      window.sessionStorage.getItem(mockStorageKeys.session) ?? 'null',
    );
    expect(window.localStorage.getItem(mockStorageKeys.session)).toBeNull();
    expect(stored).not.toBeNull();
    expect(typeof stored).toBe('object');
    if (typeof stored !== 'object' || stored === null) throw new Error('Сессия не сохранена');
    expect('userId' in stored && typeof stored.userId === 'string').toBe(true);
    expect('expiresAt' in stored && typeof stored.expiresAt === 'string').toBe(true);
    expect('mockSessionVersion' in stored && stored.mockSessionVersion === 1).toBe(true);
    expect(Object.keys(stored).sort()).toEqual(['expiresAt', 'mockSessionVersion', 'userId']);
  });

  it('повреждённое mock storage безопасно сбрасывается', async () => {
    window.localStorage.setItem(mockStorageKeys.users, '{broken');
    window.localStorage.setItem(mockStorageKeys.saved, 'not-an-array');
    expect(await mockRepository.getCurrentUser()).toBeNull();
    const demo = await mockRepository.login({
      email: 'user@pyanswer.local',
      password: 'Demo123!',
      remember: true,
    });
    expect(demo.email).toBe('user@pyanswer.local');
    expect(mockRepository.getSavedEntries()).toEqual([]);
  });
});
