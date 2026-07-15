import { ShieldX } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { Logo } from '../components/ui/Logo';
import { Button } from '../components/ui/Button';
import { useAuth } from '../features/auth/useAuth';
import { roleLabels } from '../features/auth/permissions';

export function ForbiddenPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5">
      <section className="panel w-full max-w-lg p-7 text-center">
        <Logo className="justify-center" />
        <ShieldX className="mx-auto mt-8 size-10 text-warning" aria-hidden="true" />
        <p className="mt-5 font-mono text-xs text-warning">HTTP 403</p>
        <h1 className="mt-2 text-xl font-semibold text-ink">Доступ запрещён</h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Этот раздел недоступен для текущей роли
          {user ? ` «${roleLabels[user.role]}»` : ''}. Вернитесь в доступную пользовательскую часть
          PyAnswer.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
            Назад
          </Button>
          <Link
            to="/search"
            className="inline-flex h-10 items-center rounded-lg border border-line bg-elevated px-4 text-sm font-medium text-ink transition hover:border-muted"
          >
            Перейти к поиску
          </Link>
          <Link
            to="/"
            className="inline-flex h-10 items-center rounded-lg border border-accent bg-accent px-4 text-sm font-medium text-white transition hover:bg-indigo-500"
          >
            На главную
          </Link>
        </div>
      </section>
    </main>
  );
}
