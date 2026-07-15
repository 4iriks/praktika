import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bot,
  CalendarClock,
  ExternalLink,
  FileSearch,
  Filter,
  Play,
  Search,
  Trash2,
  TriangleAlert,
} from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../api';
import { queryKeys } from '../api/queryKeys';
import { AccountTechnicalPanel } from '../components/layout/AccountTechnicalPanel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { ErrorState } from '../components/ui/QueryStates';
import { Pagination } from '../features/search/Pagination';
import { WorkspaceLayout } from '../layouts/WorkspaceLayout';
import type { HistoryFilters, SearchHistoryItem } from '../types';
import { formatDateTime, formatDuration } from '../utils/format';
import { historyItemToParams } from '../utils/searchParams';

const defaultFilters: HistoryFilters = {
  search: '',
  view: 'all',
  mode: 'all',
  dateSort: 'newest',
  page: 1,
  pageSize: 10,
};

export function HistoryPage() {
  const [filters, setFilters] = useState(defaultFilters);
  const [deleteTarget, setDeleteTarget] = useState<SearchHistoryItem | 'all' | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const history = useQuery({
    queryKey: queryKeys.history.list(filters),
    queryFn: ({ signal }) => api.getHistory(filters, signal),
  });
  const deletion = useMutation({
    mutationFn: async (target: SearchHistoryItem | 'all') => {
      if (target === 'all') await api.clearHistory();
      else await api.deleteHistoryItem(target.id);
      return target;
    },
    onSuccess: (target) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.history.root });
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.stats });
      toast.success(target === 'all' ? 'История очищена' : 'Запись удалена');
      setDeleteTarget(null);
    },
    onError: () => toast.error('Не удалось изменить историю'),
  });

  const updateFilters = (changes: Partial<HistoryFilters>) => {
    setFilters((current) => ({ ...current, ...changes, page: changes.page ?? 1 }));
  };

  return (
    <WorkspaceLayout technicalPanel={<AccountTechnicalPanel />}>
      <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="technical-label">Личная активность</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">История запросов</h1>
            <p className="mt-2 text-sm text-muted">
              Успешные поиски и RAG-ответы записываются автоматически.
            </p>
          </div>
          <Button
            variant="danger"
            size="sm"
            disabled={!history.data?.pagination.total || deletion.isPending}
            onClick={() => setDeleteTarget('all')}
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
            Очистить историю
          </Button>
        </header>

        <section className="panel mt-5 grid gap-3 p-3 md:grid-cols-[1fr_auto_auto_auto]">
          <label className="relative">
            <Search className="absolute left-3 top-3 size-4 text-muted" aria-hidden="true" />
            <input
              value={filters.search}
              onChange={(event) => updateFilters({ search: event.target.value })}
              className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-3 text-sm text-ink placeholder:text-muted/60"
              placeholder="Поиск по своей истории"
              aria-label="Поиск по истории"
            />
          </label>
          <HistorySelect
            label="Тип истории"
            value={filters.view}
            onChange={(view) => updateFilters({ view: view as HistoryFilters['view'] })}
            options={[
              ['all', 'Все типы'],
              ['documents', 'Документы'],
              ['answer', 'Ответы ИИ'],
            ]}
          />
          <HistorySelect
            label="Режим истории"
            value={filters.mode}
            onChange={(mode) => updateFilters({ mode: mode as HistoryFilters['mode'] })}
            options={[
              ['all', 'Все режимы'],
              ['bm25', 'BM25'],
              ['vector', 'Vector'],
              ['hybrid', 'Hybrid'],
            ]}
          />
          <HistorySelect
            label="Сортировка истории"
            value={filters.dateSort}
            onChange={(dateSort) =>
              updateFilters({ dateSort: dateSort as HistoryFilters['dateSort'] })
            }
            options={[
              ['newest', 'Сначала новые'],
              ['oldest', 'Сначала старые'],
            ]}
          />
        </section>

        <div className="mt-4">
          {history.isLoading ? (
            <HistorySkeleton />
          ) : history.isError ? (
            <ErrorState onRetry={() => void history.refetch()} />
          ) : history.data?.items.length ? (
            <div className="space-y-3">
              {history.data.items.map((item) => (
                <HistoryCard
                  key={item.id}
                  item={item}
                  onRepeat={() => navigate('/search?' + historyItemToParams(item).toString())}
                  onDelete={() => setDeleteTarget(item)}
                />
              ))}
              <Pagination
                value={history.data.pagination}
                onPageChange={(page) => updateFilters({ page })}
              />
            </div>
          ) : (
            <div className="panel grid min-h-72 place-items-center p-8 text-center">
              <div>
                <CalendarClock className="mx-auto size-9 text-muted" aria-hidden="true" />
                <h2 className="mt-4 font-semibold text-ink">История пока пуста</h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-muted">
                  Выполните поиск документов или получите ответ ИИ. Неудачные запросы не записываются.
                </p>
                <Link
                  to="/"
                  className="mt-5 inline-flex h-9 items-center rounded-lg border border-accent bg-accent px-3 text-xs font-medium text-white"
                >
                  Начать поиск
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={deleteTarget === 'all' ? 'Очистить всю историю?' : 'Удалить запись истории?'}
        description={
          deleteTarget === 'all'
            ? 'Все поисковые и RAG-запросы текущего пользователя будут удалены.'
            : 'Эту запись нельзя будет восстановить.'
        }
        confirmLabel={deleteTarget === 'all' ? 'Очистить' : 'Удалить'}
        onConfirm={() => {
          if (deleteTarget) deletion.mutate(deleteTarget);
        }}
        onClose={() => setDeleteTarget(null)}
      />
    </WorkspaceLayout>
  );
}

function HistoryCard({
  item,
  onRepeat,
  onDelete,
}: {
  item: SearchHistoryItem;
  onRepeat: () => void;
  onDelete: () => void;
}) {
  const params = historyItemToParams(item);
  const activeFilters = [
    ...item.filters.tags.map((tag) => '#' + tag),
    item.filters.acceptedOnly ? 'принятый ответ' : '',
    item.filters.hasCodeOnly ? 'с кодом' : '',
    item.filters.minScore > 0 ? 'рейтинг ≥ ' + item.filters.minScore : '',
  ].filter(Boolean);

  return (
    <article className="panel p-4 sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={item.view === 'answer' ? 'accent' : 'info'}>
          {item.view === 'answer' ? (
            <Bot className="mr-1 size-3" aria-hidden="true" />
          ) : (
            <FileSearch className="mr-1 size-3" aria-hidden="true" />
          )}
          {item.view === 'answer' ? 'Ответ ИИ' : 'Поиск документов'}
        </Badge>
        <Badge>{item.mode.toUpperCase()}</Badge>
        <span className="ml-auto text-[11px] text-muted">{formatDateTime(item.createdAt)}</span>
      </div>
      <h2 className="mt-3 text-base font-semibold leading-6 text-ink">{item.query}</h2>
      {item.answerPreview ? (
        <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted">{item.answerPreview}</p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted">
        <span className="font-mono">{formatDuration(item.tookMs)}</span>
        <span>·</span>
        <span>{item.resultCount} результатов</span>
        {item.insufficientContext ? (
          <span className="flex items-center gap-1 text-warning">
            <TriangleAlert className="size-3" aria-hidden="true" />
            недостаточно контекста
          </span>
        ) : null}
      </div>
      {activeFilters.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <Filter className="size-3 text-muted" aria-hidden="true" />
          {activeFilters.map((filter) => (
            <span key={filter} className="rounded border border-line px-1.5 py-0.5 text-[10px] text-muted">
              {filter}
            </span>
          ))}
        </div>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-3">
        <Button size="sm" variant="primary" onClick={onRepeat}>
          <Play className="size-3.5" aria-hidden="true" />
          Повторить запрос
        </Button>
        <Link
          to={'/search?' + params.toString()}
          className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-muted transition hover:bg-elevated hover:text-ink"
        >
          <ExternalLink className="size-3.5" aria-hidden="true" />
          Открыть поиск
        </Link>
        <Button size="sm" variant="ghost" className="sm:ml-auto" onClick={onDelete}>
          <Trash2 className="size-3.5" aria-hidden="true" />
          Удалить
        </Button>
      </div>
    </article>
  );
}

function HistorySelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<[string, string]>;
}) {
  return (
    <label>
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-lg border border-line bg-elevated px-3 text-xs text-ink"
        aria-label={label}
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function HistorySkeleton() {
  return (
    <div className="space-y-3" aria-label="Загрузка истории">
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="panel p-5">
          <div className="skeleton h-5 w-40 rounded" />
          <div className="skeleton mt-4 h-5 w-3/4 rounded" />
          <div className="skeleton mt-3 h-3 w-1/2 rounded" />
        </div>
      ))}
    </div>
  );
}
