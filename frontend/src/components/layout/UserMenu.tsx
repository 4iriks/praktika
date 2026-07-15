import {
  Bookmark,
  Clock3,
  Gauge,
  LogIn,
  LogOut,
  ShieldCheck,
  UserPlus,
  UserRound,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '../../features/auth/useAuth';
import { usePermissions } from '../../features/auth/usePermissions';
import { roleLabels } from '../../features/auth/permissions';

export function UserMenu() {
  const { user, logout } = useAuth();
  const { can } = usePermissions();
  const navigate = useNavigate();

  if (!user) {
    return (
      <div className="flex items-center gap-2">
        <Link
          to="/login"
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-xs text-muted transition hover:text-ink"
        >
          <LogIn className="size-3.5" aria-hidden="true" />
          Войти
        </Link>
        <Link
          to="/register"
          className="inline-flex size-9 items-center justify-center rounded-lg border border-accent/35 bg-accent/10 text-xs text-indigo-300 transition hover:bg-accent/15 sm:h-9 sm:w-auto sm:gap-1.5 sm:px-3"
          aria-label="Создать аккаунт"
        >
          <UserPlus className="size-3.5" aria-hidden="true" />
          <span className="hidden sm:inline">Создать аккаунт</span>
        </Link>
      </div>
    );
  }

  const signOut = async () => {
    try {
      navigate('/', { replace: true });
      await logout();
      toast.success('Вы вышли из аккаунта');
    } catch {
      toast.error('Не удалось завершить сессию');
    }
  };

  return (
    <details className="relative">
      <summary className="flex h-9 cursor-pointer list-none items-center gap-2 rounded-lg border border-line bg-surface px-2.5 text-xs text-ink transition hover:border-muted/60">
        <span className="grid size-6 place-items-center rounded-md bg-accent/15 font-mono text-[10px] text-indigo-300">
          {user.displayName.slice(0, 1).toLocaleUpperCase('ru-RU')}
        </span>
        <span className="hidden max-w-28 truncate sm:block">{user.displayName}</span>
      </summary>
      <div className="absolute right-0 top-11 z-50 w-64 rounded-xl border border-line bg-surface p-2 shadow-panel">
        <div className="border-b border-line px-2 pb-2">
          <p className="truncate text-xs font-medium text-ink">{user.displayName}</p>
          <p className="mt-0.5 truncate text-[11px] text-muted">{user.email}</p>
          <p className="mt-1 font-mono text-[10px] text-success">{roleLabels[user.role]}</p>
        </div>
        <nav className="py-1">
          <MenuLink to="/profile" icon={UserRound}>
            Профиль
          </MenuLink>
          <MenuLink to="/history" icon={Clock3}>
            История
          </MenuLink>
          <MenuLink to="/saved" icon={Bookmark}>
            Сохранённые
          </MenuLink>
          {can('EDITOR_ACCESS') ? (
            <MenuLink to="/editor" icon={Gauge}>
              Панель редактора
            </MenuLink>
          ) : null}
          {can('ADMIN_ACCESS') ? (
            <MenuLink to="/admin" icon={ShieldCheck}>
              Панель администратора
            </MenuLink>
          ) : null}
        </nav>
        <button
          type="button"
          onClick={() => void signOut()}
          className="flex h-8 w-full items-center gap-2 rounded-md border-t border-line px-2 text-xs text-muted transition hover:bg-elevated hover:text-danger"
        >
          <LogOut className="size-3.5" aria-hidden="true" />
          Выйти
        </button>
      </div>
    </details>
  );
}

function MenuLink({
  to,
  icon: Icon,
  children,
}: {
  to: string;
  icon: typeof UserRound;
  children: string;
}) {
  return (
    <Link
      to={to}
      onClick={(event) => event.currentTarget.closest('details')?.removeAttribute('open')}
      className="flex h-8 items-center gap-2 rounded-md px-2 text-xs text-muted transition hover:bg-elevated hover:text-ink"
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {children}
    </Link>
  );
}
