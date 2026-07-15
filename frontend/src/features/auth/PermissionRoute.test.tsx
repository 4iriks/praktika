import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { User, UserRole } from '../../types';
import { AuthContext, type AuthContextValue } from './AuthContext';
import { PermissionRoute } from './PermissionRoute';
import { UserMenu } from '../../components/layout/UserMenu';

function user(role: UserRole): User {
  return {
    id: `user-${role}`,
    email: `${role.toLowerCase()}@example.local`,
    displayName: role,
    role,
    accountStatus: 'ACTIVE',
    accountVersion: 1,
    createdAt: '2026-01-01T00:00:00.000Z',
    lastActiveAt: '2026-01-01T00:00:00.000Z',
    preferences: {
      defaultSearchMode: 'hybrid',
      defaultSearchView: 'documents',
      defaultPageSize: 10,
      autoOpenScores: false,
      confirmExternalNavigation: true,
    },
  };
}

function renderRoute(role: UserRole | null, path: '/editor' | '/admin') {
  const current = role ? user(role) : null;
  const value: AuthContextValue = {
    user: current,
    status: current ? 'authenticated' : 'anonymous',
    isLoading: false,
    login: () => Promise.resolve(user('USER')),
    register: () => Promise.resolve(user('USER')),
    logout: () => Promise.resolve(),
  };
  const permission = path === '/editor' ? 'EDITOR_ACCESS' : 'ADMIN_ACCESS';
  return render(
    <AuthContext.Provider value={value}>
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route
            path={path}
            element={
              <PermissionRoute permissions={[permission]}>
                <div>Закрытая панель</div>
              </PermissionRoute>
            }
          />
          <Route path="/login" element={<div>Страница входа</div>} />
          <Route path="/403" element={<div>Доступ запрещён</div>} />
        </Routes>
      </MemoryRouter>
    </AuthContext.Provider>,
  );
}

describe('PermissionRoute', () => {
  it.each(['/editor', '/admin'] as const)('перенаправляет гостя с %s на login', async (path) => {
    renderRoute(null, path);
    expect(await screen.findByText('Страница входа')).toBeInTheDocument();
  });

  it.each(['/editor', '/admin'] as const)(
    'показывает 403 пользователю USER на %s',
    async (path) => {
      renderRoute('USER', path);
      expect(await screen.findByText('Доступ запрещён')).toBeInTheDocument();
    },
  );

  it('разрешает EDITOR открыть editor route', () => {
    renderRoute('EDITOR', '/editor');
    expect(screen.getByText('Закрытая панель')).toBeInTheDocument();
  });

  it('не разрешает EDITOR открыть admin route', async () => {
    renderRoute('EDITOR', '/admin');
    expect(await screen.findByText('Доступ запрещён')).toBeInTheDocument();
  });

  it.each(['/editor', '/admin'] as const)('разрешает ADMIN открыть %s', (path) => {
    renderRoute('ADMIN', path);
    expect(screen.getByText('Закрытая панель')).toBeInTheDocument();
  });

  it('скрывает недоступные navigation items и показывает их ADMIN', () => {
    const value = (role: UserRole): AuthContextValue => ({
      user: user(role),
      status: 'authenticated',
      isLoading: false,
      login: () => Promise.resolve(user('USER')),
      register: () => Promise.resolve(user('USER')),
      logout: () => Promise.resolve(),
    });
    const view = render(
      <AuthContext.Provider value={value('USER')}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <UserMenu />
        </MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(screen.queryByText('Панель редактора')).not.toBeInTheDocument();
    expect(screen.queryByText('Панель администратора')).not.toBeInTheDocument();
    view.rerender(
      <AuthContext.Provider value={value('ADMIN')}>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <UserMenu />
        </MemoryRouter>
      </AuthContext.Provider>,
    );
    expect(screen.getByText('Панель редактора')).toBeInTheDocument();
    expect(screen.getByText('Панель администратора')).toBeInTheDocument();
  });
});
