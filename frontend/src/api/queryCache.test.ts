import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { clearUserQueryCache } from './queryCache';
import { queryKeys } from './queryKeys';

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
});
