import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { AuthProvider } from './AuthProvider';
import { ProtectedRoute } from './ProtectedRoute';

describe('ProtectedRoute', () => {
  it('перенаправляет неавторизованного пользователя', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={['/private']}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <AuthProvider>
            <Routes>
              <Route
                path="/private"
                element={
                  <ProtectedRoute>
                    <div>Закрытый раздел</div>
                  </ProtectedRoute>
                }
              />
              <Route path="/login" element={<div>Страница входа</div>} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Страница входа')).toBeInTheDocument();
    expect(screen.queryByText('Закрытый раздел')).not.toBeInTheDocument();
  });
});
