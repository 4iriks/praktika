import type { ReactNode } from 'react';
import {
  Bookmark,
  Clock3,
  FilePlus2,
  LogIn,
  LogOut,
  Moon,
  SlidersHorizontal,
  Sun,
  UserPlus,
  UserRound,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '../../features/auth/useAuth';
import { useTheme } from '../../store/useTheme';
import { cn } from '../../utils/cn';
import { Button } from '../ui/Button';
import { Logo } from '../ui/Logo';

interface SidebarProps {
  filters?: ReactNode;
  onNavigate?: () => void;
  className?: string;
}

const userLinks = [
  { to: '/history', label: 'История', icon: Clock3 },
  { to: '/saved', label: 'Сохранённые', icon: Bookmark },
  { to: '/profile', label: 'Профиль', icon: UserRound },
];

export function Sidebar({ filters, onNavigate, className }: SidebarProps) {
  const { theme, toggleTheme } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const signOut = async () => {
    try {
      await logout();
      toast.success('Вы вышли из аккаунта');
      navigate('/');
      onNavigate?.();
    } catch {
      toast.error('Не удалось завершить сессию');
    }
  };

  return (
    <aside
      className={cn(
        'flex h-full min-h-0 w-[260px] shrink-0 flex-col border-r border-line bg-surface',
        className,
      )}
      aria-label="Основная навигация"
    >
      <div className="flex h-16 shrink-0 items-center border-b border-line px-4">
        <Logo />
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        <Link
          to="/"
          onClick={onNavigate}
          className={cn(
            'flex h-10 items-center gap-2.5 rounded-lg border px-3 text-sm font-medium transition',
            location.pathname === '/'
              ? 'border-accent/40 bg-accent/10 text-indigo-300'
              : 'border-line bg-elevated/40 text-muted hover:text-ink',
          )}
        >
          <FilePlus2 className="size-4" aria-hidden="true" />
          Новый поиск
          <span className="ml-auto font-mono text-[10px] text-muted">⌘K</span>
        </Link>

        {user ? (
          <nav className="mt-4 space-y-1" aria-label="Пользовательские разделы">
            {userLinks.map((item) => {
              const Icon = item.icon;
              const active = location.pathname === item.to;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  onClick={onNavigate}
                  className={cn(
                    'flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm transition',
                    active
                      ? 'bg-elevated text-ink shadow-sm'
                      : 'text-muted hover:bg-elevated/60 hover:text-ink',
                  )}
                  aria-current={active ? 'page' : undefined}
                >
                  <Icon className={cn('size-4', active && 'text-info')} aria-hidden="true" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        ) : (
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Link
              to="/login"
              onClick={onNavigate}
              className="flex h-9 items-center justify-center gap-1.5 rounded-lg border border-line bg-elevated text-xs text-muted transition hover:text-ink"
            >
              <LogIn className="size-3.5" aria-hidden="true" />
              Войти
            </Link>
            <Link
              to="/register"
              onClick={onNavigate}
              className="flex h-9 items-center justify-center gap-1.5 rounded-lg border border-accent/35 bg-accent/10 text-xs text-indigo-300 transition hover:bg-accent/15"
            >
              <UserPlus className="size-3.5" aria-hidden="true" />
              Регистрация
            </Link>
          </div>
        )}

        {filters ? (
          <section className="mt-5 border-t border-line pt-5" aria-labelledby="filters-title">
            <div className="mb-3 flex items-center gap-2 px-1">
              <SlidersHorizontal className="size-3.5 text-muted" aria-hidden="true" />
              <h2 id="filters-title" className="technical-label">
                Фильтры
              </h2>
            </div>
            {filters}
          </section>
        ) : null}
      </div>

      <div className="shrink-0 border-t border-line p-3">
        <Button
          variant="ghost"
          className="w-full justify-start"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
        >
          {theme === 'dark' ? (
            <Sun className="size-4" aria-hidden="true" />
          ) : (
            <Moon className="size-4" aria-hidden="true" />
          )}
          {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
        </Button>
        {user ? (
          <div className="mt-2 rounded-lg border border-line bg-elevated/60 p-2">
            <div className="flex items-center gap-2">
              <span className="grid size-8 shrink-0 place-items-center rounded-md bg-accent/15 text-xs font-semibold text-indigo-300">
                {initials(user.displayName)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-medium text-ink">{user.displayName}</p>
                <p className="truncate text-[10px] text-muted">{user.email}</p>
              </div>
              <Button size="icon" variant="ghost" onClick={() => void signOut()} aria-label="Выйти">
                <LogOut className="size-4" aria-hidden="true" />
              </Button>
            </div>
            <p className="mt-2 border-t border-line pt-2 font-mono text-[10px] text-success">
              Пользователь · ACTIVE
            </p>
          </div>
        ) : null}
      </div>
    </aside>
  );
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase('ru-RU') ?? '')
    .join('');
}
