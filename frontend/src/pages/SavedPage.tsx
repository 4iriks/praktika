import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Bookmark,
  Bot,
  CalendarDays,
  CheckCircle2,
  ExternalLink,
  MessageSquare,
  Search,
  Star,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api';
import { queryKeys } from '../api/queryKeys';
import { AccountTechnicalPanel } from '../components/layout/AccountTechnicalPanel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { ExternalSourceLink } from '../components/ui/ExternalSourceLink';
import { ErrorState } from '../components/ui/QueryStates';
import { useSavedDocument } from '../features/documents/useSavedDocument';
import { Pagination } from '../features/search/Pagination';
import { WorkspaceLayout } from '../layouts/WorkspaceLayout';
import type { SavedDocument, SavedDocumentsFilters } from '../types';
import { formatDate, formatDateTime } from '../utils/format';

const initialFilters: SavedDocumentsFilters = {
  search: '',
  tags: [],
  sort: 'savedAt',
  page: 1,
  pageSize: 10,
};

export function SavedPage() {
  const [filters, setFilters] = useState(initialFilters);
  const saved = useQuery({
    queryKey: queryKeys.saved.list(filters),
    queryFn: ({ signal }) => api.getSavedDocuments(filters, signal),
  });

  const updateFilters = (changes: Partial<SavedDocumentsFilters>) => {
    setFilters((current) => ({ ...current, ...changes, page: changes.page ?? 1 }));
  };
  const toggleTag = (slug: string) => {
    updateFilters({
      tags: filters.tags.includes(slug)
        ? filters.tags.filter((tag) => tag !== slug)
        : [...filters.tags, slug],
    });
  };

  return (
    <WorkspaceLayout technicalPanel={<AccountTechnicalPanel />}>
      <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
        <header>
          <p className="technical-label">Личная библиотека</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">
            Сохранённые документы
          </h1>
          <p className="mt-2 text-sm text-muted">
            Отмеченные вопросы доступны только текущему пользователю.
          </p>
        </header>

        <section className="panel mt-5 p-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
            <label className="relative">
              <Search className="absolute left-3 top-3 size-4 text-muted" aria-hidden="true" />
              <input
                value={filters.search}
                onChange={(event) => updateFilters({ search: event.target.value })}
                className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-3 text-sm text-ink"
                placeholder="Поиск по сохранённым"
                aria-label="Поиск по сохранённым документам"
              />
            </label>
            <select
              value={filters.sort}
              onChange={(event) =>
                updateFilters({ sort: event.target.value as SavedDocumentsFilters['sort'] })
              }
              className="h-10 rounded-lg border border-line bg-elevated px-3 text-xs text-ink"
              aria-label="Сортировка сохранённых документов"
            >
              <option value="savedAt">По дате сохранения</option>
              <option value="score">По рейтингу</option>
              <option value="publishedAt">По дате публикации</option>
            </select>
          </div>
          {saved.data?.availableTags.length ? (
            <div className="mt-3 flex flex-wrap gap-1.5 border-t border-line pt-3">
              {saved.data.availableTags.map((tag) => (
                <button
                  key={tag.slug}
                  type="button"
                  onClick={() => toggleTag(tag.slug)}
                  className={
                    filters.tags.includes(tag.slug)
                      ? 'rounded-md border border-accent/40 bg-accent/10 px-2 py-1 text-[11px] text-indigo-300'
                      : 'rounded-md border border-line px-2 py-1 text-[11px] text-muted hover:text-ink'
                  }
                  aria-pressed={filters.tags.includes(tag.slug)}
                >
                  {tag.name}
                </button>
              ))}
            </div>
          ) : null}
        </section>

        <div className="mt-4">
          {saved.isLoading ? (
            <SavedSkeleton />
          ) : saved.isError ? (
            <ErrorState onRetry={() => void saved.refetch()} />
          ) : saved.data?.items.length ? (
            <div className="space-y-3">
              {saved.data.items.map((document) => (
                <SavedCard key={document.documentId} document={document} />
              ))}
              <Pagination
                value={saved.data.pagination}
                onPageChange={(page) => updateFilters({ page })}
              />
            </div>
          ) : (
            <div className="panel grid min-h-72 place-items-center p-8 text-center">
              <div>
                <Bookmark className="mx-auto size-9 text-muted" aria-hidden="true" />
                <h2 className="mt-4 font-semibold text-ink">Нет сохранённых документов</h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-muted">
                  Сохраняйте полезные результаты поиска и источники RAG, чтобы вернуться к ним позже.
                </p>
                <Link
                  to="/"
                  className="mt-5 inline-flex h-9 items-center rounded-lg border border-accent bg-accent px-3 text-xs font-medium text-white"
                >
                  Перейти к поиску
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>
    </WorkspaceLayout>
  );
}

function SavedCard({ document }: { document: SavedDocument }) {
  const saved = useSavedDocument(document.documentId, document.saved);
  const navigate = useNavigate();
  const ask = () => {
    const params = new URLSearchParams({
      q: document.title,
      view: 'answer',
      mode: 'hybrid',
      page: '1',
      sort: 'relevance',
    });
    navigate('/search?' + params.toString());
  };

  return (
    <article className="panel p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[11px] text-muted">
        <span className="flex items-center gap-1 text-info">
          <Bookmark className="size-3" aria-hidden="true" />
          сохранён {formatDateTime(document.savedAt)}
        </span>
        <span className="flex items-center gap-1">
          <CalendarDays className="size-3" aria-hidden="true" />
          {formatDate(document.publishedAt)}
        </span>
        <span className="flex items-center gap-1">
          <Star className="size-3" aria-hidden="true" />
          {document.questionScore}
        </span>
        <span className="flex items-center gap-1">
          <MessageSquare className="size-3" aria-hidden="true" />
          {document.answersCount}
        </span>
        {document.acceptedAnswer ? (
          <span className="flex items-center gap-1 text-success">
            <CheckCircle2 className="size-3" aria-hidden="true" />
            принят
          </span>
        ) : null}
      </div>
      <h2 className="mt-3 text-lg font-semibold leading-6 text-ink">
        <Link to={'/documents/' + document.documentId} className="hover:text-info">
          {document.title}
        </Link>
      </h2>
      <p className="mt-2 text-sm leading-6 text-muted">{document.snippet}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {document.tags.map((tag) => (
          <Badge key={tag.slug} tone={tag.slug === 'python' ? 'accent' : 'neutral'}>
            {tag.name}
          </Badge>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap gap-2 border-t border-line pt-4">
        <Link
          to={'/documents/' + document.documentId}
          className="inline-flex h-8 items-center rounded-md border border-line bg-elevated px-2.5 text-xs text-ink"
        >
          Открыть документ
        </Link>
        <ExternalSourceLink
          href={document.sourceUrl}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-muted hover:bg-elevated hover:text-ink"
        >
          Источник
          <ExternalLink className="size-3.5" aria-hidden="true" />
        </ExternalSourceLink>
        <Button size="sm" variant="ghost" onClick={ask}>
          <Bot className="size-3.5" aria-hidden="true" />
          Спросить ИИ
        </Button>
        <Button
          size="sm"
          variant="danger"
          className="sm:ml-auto"
          onClick={saved.toggle}
          loading={saved.isPending}
        >
          Удалить
        </Button>
      </div>
    </article>
  );
}

function SavedSkeleton() {
  return (
    <div className="space-y-3" aria-label="Загрузка сохранённых документов">
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="panel p-5">
          <div className="skeleton h-3 w-44 rounded" />
          <div className="skeleton mt-4 h-6 w-4/5 rounded" />
          <div className="skeleton mt-3 h-3 w-full rounded" />
          <div className="skeleton mt-2 h-3 w-2/3 rounded" />
        </div>
      ))}
    </div>
  );
}
