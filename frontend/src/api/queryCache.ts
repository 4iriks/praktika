import type { QueryClient } from '@tanstack/react-query';

const userScopedRoots = new Set(['user', 'history', 'saved', 'feedback', 'search', 'document']);

export function clearUserQueryCache(queryClient: QueryClient): void {
  queryClient.removeQueries({
    predicate: (query) => {
      const root = query.queryKey[0];
      return typeof root === 'string' && userScopedRoots.has(root);
    },
  });
}
