import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Search } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api';
import { queryKeys } from '../api/queryKeys';
import { DocumentThread } from '../features/documents/DocumentThread';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { ErrorState, ResultsSkeleton } from '../components/ui/QueryStates';
import { ApiError } from '../api/ApiError';

export function DocumentPage() {
  const { documentId = '' } = useParams();
  const query = useQuery({
    queryKey: queryKeys.document.detail(documentId),
    queryFn: ({ signal }) => api.getDocument(documentId, signal),
    enabled: Boolean(documentId),
  });

  return (
    <div className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-30 border-b border-line bg-surface/95 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:px-6">
          <Logo />
          <div className="ml-auto flex items-center gap-2">
            <Link
              to="/search?q=python&view=documents&mode=hybrid&page=1&sort=relevance"
              className="hidden h-9 items-center gap-2 rounded-lg px-3 text-xs text-muted transition hover:bg-elevated hover:text-ink sm:flex"
            >
              <Search className="size-3.5" aria-hidden="true" />К поиску
            </Link>
            <Button
              size="icon"
              variant="ghost"
              onClick={() => window.history.back()}
              aria-label="Назад"
            >
              <ArrowLeft className="size-4" aria-hidden="true" />
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-6 sm:py-8">
        {query.isLoading ? (
          <ResultsSkeleton />
        ) : query.isError ? (
          query.error instanceof ApiError &&
          query.error.details?.reason === 'DOCUMENT_UNAVAILABLE' ? (
            <section className="panel p-8 text-center">
              <p className="font-mono text-xs text-warning">DOCUMENT_UNAVAILABLE</p>
              <h1 className="mt-3 text-xl font-semibold">Документ временно недоступен</h1>
              <p className="mt-2 text-sm text-muted">
                Материал скрыт редактором или ожидает повторной индексации. Содержимое не
                раскрывается.
              </p>
              <Link
                to="/search"
                className="mt-5 inline-flex h-10 items-center rounded-lg border border-line px-4 text-sm text-info"
              >
                Вернуться к поиску
              </Link>
            </section>
          ) : (
            <ErrorState onRetry={() => void query.refetch()} />
          )
        ) : query.data ? (
          <DocumentThread document={query.data} />
        ) : null}
      </main>
    </div>
  );
}
