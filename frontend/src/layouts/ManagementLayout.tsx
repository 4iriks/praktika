import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowLeft,
  BookOpenCheck,
  Boxes,
  BriefcaseBusiness,
  Database,
  FileClock,
  Files,
  Gauge,
  Menu,
  Moon,
  ServerCog,
  ShieldCheck,
  Sun,
  Users,
  X,
} from 'lucide-react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { UserMenu } from '../components/layout/UserMenu';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { useAuth } from '../features/auth/useAuth';
import { usePermissions } from '../features/auth/usePermissions';
import { roleLabels } from '../features/auth/permissions';
import { useTheme } from '../store/useTheme';
import type { Permission } from '../types';
import { cn } from '../utils/cn';

interface ManagementLink {
  to: string;
  label: string;
  icon: typeof Gauge;
  permission: Permission;
  end?: boolean;
}

const links: ManagementLink[] = [
  { to: '/editor', label: 'Обзор редактора', icon: Gauge, permission: 'EDITOR_ACCESS', end: true },
  {
    to: '/editor/documents',
    label: 'Документы',
    icon: Files,
    permission: 'MANAGED_DOCUMENTS_VIEW',
  },
  {
    to: '/editor/jobs',
    label: 'Задания редактора',
    icon: BriefcaseBusiness,
    permission: 'EDITOR_JOBS_VIEW',
  },
  {
    to: '/admin',
    label: 'Обзор администратора',
    icon: Activity,
    permission: 'ADMIN_ACCESS',
    end: true,
  },
  { to: '/admin/users', label: 'Пользователи', icon: Users, permission: 'USERS_MANAGE' },
  { to: '/admin/sources', label: 'Источники', icon: Database, permission: 'SOURCES_MANAGE' },
  { to: '/admin/jobs', label: 'Все задания', icon: Boxes, permission: 'ADMIN_JOBS_MANAGE' },
  {
    to: '/admin/indexes',
    label: 'Поисковый индекс',
    icon: ShieldCheck,
    permission: 'SEARCH_INDEX_VIEW',
  },
  { to: '/admin/audit', label: 'Аудит', icon: FileClock, permission: 'AUDIT_VIEW' },
  { to: '/admin/system', label: 'Система', icon: ServerCog, permission: 'SYSTEM_VIEW' },
];

export function ManagementLayout() {
  const [open, setOpen] = useState(false);
  const { user } = useAuth();
  const { can } = usePermissions();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const adminArea = location.pathname.startsWith('/admin');
  const visibleLinks = useMemo(
    () =>
      links.filter(
        (item) => can(item.permission) && item.to.startsWith(adminArea ? '/admin' : '/editor'),
      ),
    [adminArea, can],
  );

  useEffect(() => setOpen(false), [location.pathname]);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [open]);

  return (
    <div className="min-h-dvh bg-canvas text-ink">
      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center border-b border-line bg-surface px-3 lg:left-64 lg:px-6">
        <Button
          size="icon"
          variant="ghost"
          className="mr-2 lg:hidden"
          onClick={() => setOpen(true)}
          aria-label="Открыть меню управления"
        >
          <Menu className="size-5" aria-hidden="true" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="technical-label">Панель управления</p>
          <p className="mt-0.5 truncate text-sm text-muted">{breadcrumb(location.pathname)}</p>
        </div>
        {import.meta.env.VITE_USE_MOCKS === 'true' ? (
          <Badge tone="warning" className="mr-2 hidden sm:inline-flex">
            mock-режим
          </Badge>
        ) : null}
        <Button
          size="icon"
          variant="ghost"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
        >
          {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </Button>
        <UserMenu />
      </header>

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-line bg-surface transition-transform lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
        aria-label="Навигация панели управления"
      >
        <div className="flex h-16 items-center justify-between border-b border-line px-4">
          <Logo />
          <Button
            size="icon"
            variant="ghost"
            className="lg:hidden"
            onClick={() => setOpen(false)}
            aria-label="Закрыть меню"
          >
            <X className="size-5" aria-hidden="true" />
          </Button>
        </div>
        <div className="border-b border-line p-3">
          <div className="flex items-center gap-2 rounded-lg bg-elevated p-2.5">
            <ShieldCheck className="size-4 text-info" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate text-xs font-medium">{user?.displayName}</p>
              <p className="font-mono text-[10px] text-info">{user ? roleLabels[user.role] : ''}</p>
            </div>
          </div>
        </div>
        <nav className="min-h-0 flex-1 space-y-1 overflow-y-auto p-3">
          {visibleLinks.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm transition',
                    isActive
                      ? 'bg-accent/15 text-indigo-300'
                      : 'text-muted hover:bg-elevated hover:text-ink',
                  )
                }
              >
                <Icon className="size-4" aria-hidden="true" />
                {item.label}
              </NavLink>
            );
          })}
          {can('ADMIN_ACCESS') ? (
            <NavLink
              to={adminArea ? '/editor' : '/admin'}
              className="mt-3 flex h-9 items-center gap-2.5 rounded-lg border border-line px-3 text-sm text-muted transition hover:bg-elevated hover:text-ink"
            >
              <BookOpenCheck className="size-4" aria-hidden="true" />
              {adminArea ? 'Раздел редактора' : 'Администрирование'}
            </NavLink>
          ) : null}
        </nav>
        <div className="border-t border-line p-3">
          <Link
            to="/search"
            className="flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm text-muted transition hover:bg-elevated hover:text-ink"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Вернуться к поиску
          </Link>
        </div>
      </aside>

      {open ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-canvas/75 lg:hidden"
          onClick={() => setOpen(false)}
          aria-label="Закрыть меню"
        />
      ) : null}

      <main className="min-h-dvh pt-16 lg:pl-64">
        <div className="mx-auto w-full max-w-[1600px] p-4 sm:p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function breadcrumb(pathname: string): string {
  const labels: Record<string, string> = {
    '/editor': 'Редактор / Обзор',
    '/editor/documents': 'Редактор / Документы',
    '/editor/jobs': 'Редактор / Задания',
    '/admin': 'Администратор / Обзор',
    '/admin/users': 'Администратор / Пользователи',
    '/admin/sources': 'Администратор / Источники',
    '/admin/jobs': 'Администратор / Задания',
    '/admin/audit': 'Администратор / Аудит',
    '/admin/system': 'Администратор / Система',
    '/admin/indexes': 'Администратор / Поисковый индекс',
  };
  if (pathname.startsWith('/editor/documents/')) return 'Редактор / Документы / Карточка';
  return labels[pathname] ?? 'PyAnswer / Управление';
}
