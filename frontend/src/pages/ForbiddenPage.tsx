import { ShieldX } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Logo } from '../components/ui/Logo';

export function ForbiddenPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5">
      <section className="panel w-full max-w-lg p-7 text-center">
        <Logo className="justify-center" />
        <ShieldX className="mx-auto mt-8 size-10 text-warning" aria-hidden="true" />
        <p className="mt-5 font-mono text-xs text-warning">HTTP 403</p>
        <h1 className="mt-2 text-xl font-semibold text-ink">Недостаточно прав</h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Этот раздел недоступен для текущей роли. На первом этапе демонстрационный пользователь
          получает роль USER.
        </p>
        <Link
          to="/"
          className="mt-6 inline-flex h-10 items-center rounded-lg border border-accent bg-accent px-4 text-sm font-medium text-white transition hover:bg-indigo-500"
        >
          Вернуться на главную
        </Link>
      </section>
    </main>
  );
}
