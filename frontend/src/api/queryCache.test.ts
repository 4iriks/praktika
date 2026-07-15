import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { clearUserQueryCache, updateSavedDocumentCache } from './queryCache';
import { queryKeys } from './queryKeys';
import type { SearchResponse } from '../types';

describe('clearUserQueryCache', () => {
  it('удаляет пользовательский cache при logout и сохраняет системный', () => {
    const queryClient = new QueryClient();
    queryClient.setQueryData(queryKeys.history.root, ['private']);
    queryClient.setQueryData(queryKeys.saved.root, ['private']);
    queryClient.setQueryData(queryKeys.system.status, { online: true });
    clearUserQueryCache(queryClient);
    expect(queryClient.getQueryData(queryKeys.history.root)).toBeUndefined();
    expect(queryClient.getQueryData(queryKeys.saved.root)).toBeUndefined();
    expect(queryClient.getQueryData(queryKeys.system.status)).toEqual({ online: true });
  });

  it('синхронно обновляет saved-флаг в поисковом cache без повторного запроса', () => {
    const queryClient = new QueryClient();
    const response: SearchResponse = {
      results: [
        {
          documentId: 'py-1001',
          title: 'Документ',
          snippet: 'Фрагмент',
          tags: [],
          sourceUrl: 'https://example.com',
          publishedAt: '2026-01-01T00:00:00.000Z',
          questionScore: 5,
          answersCount: 1,
          acceptedAnswer: true,
          hasCode: true,
          saved: true,
          bm25Score: 1,
          vectorScore: 0.8,
          rerankerScore: 0.9,
          finalScore: 0.85,
        },
      ],
      pagination: { page: 1, pageSize: 10, total: 1, totalPages: 1 },
      metrics: { tookMs: 20, candidates: 3, reranked: 1, queryTokens: 2 },
    };
    const searchKey = [...queryKeys.search.root, 'asyncio'] as const;
    queryClient.setQueryData(searchKey, response);

    updateSavedDocumentCache(queryClient, 'py-1001', false);

    expect(queryClient.getQueryData<SearchResponse>(searchKey)?.results[0]?.saved).toBe(false);
  });
});
