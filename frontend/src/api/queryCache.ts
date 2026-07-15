import type { QueryClient } from '@tanstack/react-query';
import type { Document, SearchResponse } from '../types';
import { queryKeys } from './queryKeys';

const userScopedRoots = new Set([
  'user',
  'history',
  'saved',
  'feedback',
  'search',
  'document',
  'editor',
  'admin',
]);

export function clearUserQueryCache(queryClient: QueryClient): void {
  queryClient.removeQueries({
    predicate: (query) => {
      const root = query.queryKey[0];
      return typeof root === 'string' && userScopedRoots.has(root);
    },
  });
}

export function updateSavedDocumentCache(
  queryClient: QueryClient,
  documentId: string,
  saved: boolean,
): void {
  queryClient.setQueriesData<SearchResponse>({ queryKey: queryKeys.search.root }, (current) =>
    current
      ? {
          ...current,
          results: current.results.map((result) =>
            result.documentId === documentId ? { ...result, saved } : result,
          ),
        }
      : current,
  );
  queryClient.setQueryData<Document>(queryKeys.document.detail(documentId), (current) =>
    current ? { ...current, saved } : current,
  );
}
