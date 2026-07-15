import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { mockRepository } from '../../mocks/mockRepository';
import { AuthProvider } from './AuthProvider';
import { useAuth } from './useAuth';

function StatusProbe() {
  const { status, user } = useAuth();
  return <div>{status + ' ' + (user?.email ?? '')}</div>;
}

describe('AuthProvider', () => {
  it('восстанавливает сохранённую mock-сессию после инициализации', async () => {
    await mockRepository.register({
      displayName: 'Session User',
      email: 'session@example.local',
      password: 'Strong123',
      acceptedTerms: true,
      remember: true,
    });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StatusProbe />
        </AuthProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('authenticated session@example.local')).toBeInTheDocument();
  });
});
