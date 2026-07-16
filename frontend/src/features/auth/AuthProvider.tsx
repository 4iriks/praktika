import { useCallback, useEffect, useMemo, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api';
import { subscribeToUnauthorized } from '../../api/httpApi';
import { clearUserQueryCache } from '../../api/queryCache';
import { queryKeys } from '../../api/queryKeys';
import type { AuthStatus, LoginRequest, RegisterRequest, User } from '../../types';
import { AuthContext, type AuthContextValue } from './AuthContext';

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const queryClient = useQueryClient();
  const currentUser = useQuery({
    queryKey: queryKeys.auth.current,
    queryFn: () => api.getCurrentUser(),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });

  useEffect(
    () =>
      subscribeToUnauthorized(() => {
        clearUserQueryCache(queryClient);
        queryClient.setQueryData(queryKeys.auth.current, null);
      }),
    [queryClient],
  );

  const setAuthenticatedUser = useCallback(
    (user: User) => {
      clearUserQueryCache(queryClient);
      queryClient.setQueryData(queryKeys.auth.current, user);
    },
    [queryClient],
  );

  const login = useCallback(
    async (request: LoginRequest) => {
      const user = await api.login(request);
      setAuthenticatedUser(user);
      return user;
    },
    [setAuthenticatedUser],
  );

  const register = useCallback(
    async (request: RegisterRequest) => {
      const user = await api.register(request);
      setAuthenticatedUser(user);
      return user;
    },
    [setAuthenticatedUser],
  );

  const logout = useCallback(async () => {
    await api.logout();
    clearUserQueryCache(queryClient);
    queryClient.setQueryData(queryKeys.auth.current, null);
  }, [queryClient]);

  const status: AuthStatus = currentUser.isPending
    ? 'initializing'
    : currentUser.data
      ? 'authenticated'
      : 'anonymous';
  const value = useMemo<AuthContextValue>(
    () => ({
      user: currentUser.data ?? null,
      status,
      isLoading: status === 'initializing',
      login,
      register,
      logout,
    }),
    [currentUser.data, login, logout, register, status],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
