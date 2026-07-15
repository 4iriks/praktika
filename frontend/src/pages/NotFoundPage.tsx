import { SearchX } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Logo } from '../components/ui/Logo';

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-canvas p-5">
      <section className="panel w-full max-w-lg p-7 text-center">
        <Logo className="justify-center" />
        <SearchX className="mx-auto mt-8 size-10 text-info" aria-hidden="true" />
        <p className="mt-5 font-mono text-xs text-info">HTTP 404</p>
        <h1 className="mt-2 text-xl font-semibold text-ink">Страница не найдена</h1>
        <p className="mt-2 text-sm leading-6 text-muted">
          Адрес мог измениться или содержать опечатку. Поисковый индекс продолжает работать.
        </p>
        <Link
          to="/"
          className="mt-6 inline-flex h-10 items-center rounded-lg border border-accent bg-accent px-4 text-sm font-medium text-white transition hover:bg-indigo-500"
        >
          Открыть поиск
        </Link>
      </section>
    </main>
  );
}
