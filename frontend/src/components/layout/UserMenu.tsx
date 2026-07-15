import { Bookmark, Clock3, LogIn, LogOut, UserPlus, UserRound } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '../../features/auth/useAuth';

export function UserMenu() {
  const { user, logout } = useAuth();
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
          className="hidden h-9 items-center gap-1.5 rounded-lg border border-accent/35 bg-accent/10 px-3 text-xs text-indigo-300 transition hover:bg-accent/15 sm:inline-flex"
        >
          <UserPlus className="size-3.5" aria-hidden="true" />
          Создать аккаунт
        </Link>
      </div>
    );
  }

  const signOut = async () => {
    try {
      await logout();
      toast.success('Вы вышли из аккаунта');
      navigate('/');
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
          <p className="mt-1 font-mono text-[10px] text-success">Пользователь</p>
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
      className="flex h-8 items-center gap-2 rounded-md px-2 text-xs text-muted transition hover:bg-elevated hover:text-ink"
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {children}
    </Link>
  );
}
