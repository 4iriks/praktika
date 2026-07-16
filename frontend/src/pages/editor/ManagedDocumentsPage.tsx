import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { EyeOff, RotateCcw, Search, SquarePen, Workflow } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  PageHeading,
  LoadingPanel,
  ErrorPanel,
  EmptyPanel,
  StatusBadge,
} from '../../components/management/ManagementUi';
import { ReasonDialog } from '../../components/management/ReasonDialog';
import { Button } from '../../components/ui/Button';
import type { BulkDocumentAction, ManagedDocument } from '../../types';
import { managedDocumentFilters, setParam } from '../../utils/managementParams';

interface PendingAction {
  action: BulkDocumentAction;
  documentIds: string[];
}

export function ManagedDocumentsPage() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => managedDocumentFilters(params), [params]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<PendingAction | null>(null);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.editor.documents(filters),
    queryFn: ({ signal }) => api.getManagedDocuments(filters, signal),
  });
  const mutation = useMutation({
    mutationFn: ({ action, documentIds, reason }: PendingAction & { reason: string }) =>
      api.bulkUpdateDocuments({ action, documentIds, reason: reason || undefined }),
    onSuccess: async (result) => {
      toast.success(
        `Готово: ${result.successCount}; пропущено: ${result.skippedCount}; ошибок: ${result.failedCount}`,
      );
      setSelected(new Set());
      setPending(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.editor.root }),
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.root }),
        queryClient.invalidateQueries({ queryKey: queryKeys.search.root }),
        queryClient.invalidateQueries({ queryKey: queryKeys.document.root }),
        queryClient.invalidateQueries({ queryKey: queryKeys.saved.root }),
      ]);
    },
    onError: (error) => toast.error(error.message),
  });

  const act = (action: BulkDocumentAction, ids: string[]) =>
    setPending({ action, documentIds: ids });
  const allPageSelected =
    Boolean(query.data?.items.length) &&
    query.data?.items.every((item) => selected.has(item.documentId));
  const togglePage = () => {
    const next = new Set(selected);
    if (allPageSelected) query.data?.items.forEach((item) => next.delete(item.documentId));
    else query.data?.items.forEach((item) => next.add(item.documentId));
    setSelected(next);
  };

  return (
    <>
      <PageHeading
        eyebrow="DOCUMENT MANAGEMENT"
        title="Управляемые документы"
        description="Оригинальный контент остаётся неизменным; processing, deduplication и поисковые индексы показаны раздельно."
      />
      <section
        className="panel mb-4 grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-6"
        aria-label="Фильтры документов"
      >
        <label className="relative sm:col-span-2">
          <span className="sr-only">Поиск по ID и заголовку</span>
          <Search
            className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted"
            aria-hidden="true"
          />
          <input
            value={filters.q}
            onChange={(event) => setParams(setParam(params, 'q', event.target.value))}
            placeholder="ID или заголовок"
            className="h-9 w-full rounded-md border border-line bg-elevated pl-9 pr-3 text-sm"
          />
        </label>
        <FilterSelect
          label="Статус"
          value={filters.status}
          onChange={(value) => setParams(setParam(params, 'status', value))}
          options={['ALL', 'ACTIVE', 'HIDDEN', 'PENDING', 'FAILED', 'OUTDATED']}
        />
        <FilterSelect
          label="BM25"
          value={filters.bm25}
          onChange={(value) => setParams(setParam(params, 'bm25', value))}
          options={['ALL', 'READY', 'PENDING', 'FAILED', 'NOT_INDEXED', 'OUTDATED']}
        />
        <FilterSelect
          label="Vector"
          value={filters.vector}
          onChange={(value) => setParams(setParam(params, 'vector', value))}
          options={['ALL', 'READY', 'PENDING', 'FAILED', 'NOT_INDEXED', 'OUTDATED']}
        />
        <FilterSelect
          label="Сортировка"
          value={filters.sort}
          onChange={(value) => setParams(setParam(params, 'sort', value))}
          options={['updated_desc', 'updated_asc', 'rating_desc', 'title_asc', 'status_asc']}
        />
        <FilterSelect
          label="Принятый ответ"
          value={filters.accepted}
          onChange={(value) => setParams(setParam(params, 'accepted', value))}
          options={['all', 'true', 'false']}
        />
        <FilterSelect
          label="С кодом"
          value={filters.hasCode}
          onChange={(value) => setParams(setParam(params, 'has_code', value))}
          options={['all', 'true', 'false']}
        />
        <input
          value={filters.tags.join(',')}
          onChange={(event) => setParams(setParam(params, 'tags', event.target.value))}
          placeholder="Теги через запятую"
          aria-label="Теги"
          className="h-9 rounded-md border border-line bg-elevated px-3 text-sm"
        />
        <FilterSelect
          label="Строк на странице"
          value={String(filters.limit)}
          onChange={(value) => setParams(setParam(params, 'limit', value))}
          options={['10', '20', '50']}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setParams({ page: '1', limit: '20' })}
        >
          Сбросить
        </Button>
      </section>

      <div className="mb-3 flex min-h-9 flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={togglePage}
          disabled={!query.data?.items.length}
        >
          {allPageSelected ? 'Снять выбор страницы' : 'Выбрать страницу'}
        </Button>
        <span className="font-mono text-xs text-muted">Выбрано: {selected.size}</span>
        {selected.size ? (
          <>
            <Button
              type="button"
              size="sm"
              variant="danger"
              onClick={() => act('HIDE', [...selected])}
            >
              Скрыть
            </Button>
            <Button type="button" size="sm" onClick={() => act('RESTORE', [...selected])}>
              Восстановить
            </Button>
            <Button type="button" size="sm" onClick={() => act('REINDEX', [...selected])}>
              Переиндексировать
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              Очистить выбор
            </Button>
          </>
        ) : null}
      </div>

      {query.isPending ? <LoadingPanel /> : null}
      {query.isError ? <ErrorPanel message={query.error.message} /> : null}
      {query.data?.items.length === 0 ? (
        <EmptyPanel
          title="Документы не найдены"
          description="Измените фильтры или сбросьте URL-параметры."
        />
      ) : null}
      {query.data?.items.length ? (
        <>
          <DesktopTable
            items={query.data.items}
            selected={selected}
            onToggle={(id) => setSelected(toggleSet(selected, id))}
            onAction={act}
          />
          <MobileCards
            items={query.data.items}
            selected={selected}
            onToggle={(id) => setSelected(toggleSet(selected, id))}
            onAction={act}
          />
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-muted">
              Страница {query.data.pagination.page} из {query.data.pagination.totalPages} ·{' '}
              {query.data.pagination.total} документов
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={filters.page <= 1}
                onClick={() => setParams(setParam(params, 'page', filters.page - 1, false))}
              >
                Назад
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={filters.page >= query.data.pagination.totalPages}
                onClick={() => setParams(setParam(params, 'page', filters.page + 1, false))}
              >
                Далее
              </Button>
            </div>
          </div>
        </>
      ) : null}

      <ReasonDialog
        open={Boolean(pending)}
        title={
          pending?.action === 'HIDE'
            ? 'Скрыть документы?'
            : pending?.action === 'RESTORE'
              ? 'Восстановить документы?'
              : 'Запустить переиндексацию?'
        }
        description={`Операция будет применена к ${pending?.documentIds.length ?? 0} документам. Несовместимые статусы будут безопасно пропущены.`}
        confirmLabel="Подтвердить"
        reasonRequired={pending?.action === 'HIDE'}
        loading={mutation.isPending}
        onClose={() => !mutation.isPending && setPending(null)}
        onConfirm={(reason) => pending && mutation.mutate({ ...pending, reason })}
      />
    </>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="sr-only">
      {label}
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="not-sr-only h-9 w-full rounded-md border border-line bg-elevated px-2 text-xs"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function DesktopTable({
  items,
  selected,
  onToggle,
  onAction,
}: {
  items: ManagedDocument[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onAction: (action: BulkDocumentAction, ids: string[]) => void;
}) {
  return (
    <div className="panel hidden overflow-x-auto md:block">
      <table className="w-full min-w-[1380px] border-collapse text-left text-xs">
        <thead className="bg-elevated/70 text-muted">
          <tr>
            {[
              '',
              'ID / заголовок',
              'Статус',
              'Обработка',
              'Дедупликация',
              'Рейтинг',
              'Ответы',
              'Чанки',
              'BM25',
              'Vector',
              'Синхронизация',
              'Изменение',
              'Действия',
            ].map((label, index) => (
              <th key={`${label}-${index}`} className="border-b border-line px-3 py-2 font-medium">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {items.map((item) => (
            <DocumentRow
              key={item.documentId}
              item={item}
              selected={selected.has(item.documentId)}
              onToggle={onToggle}
              onAction={onAction}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentRow({
  item,
  selected,
  onToggle,
  onAction,
}: {
  item: ManagedDocument;
  selected: boolean;
  onToggle: (id: string) => void;
  onAction: (action: BulkDocumentAction, ids: string[]) => void;
}) {
  return (
    <tr className="hover:bg-elevated/35">
      <td className="px-3 py-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={() => onToggle(item.documentId)}
          aria-label={`Выбрать ${item.documentId}`}
        />
      </td>
      <td className="max-w-sm px-3 py-3">
        <Link
          to={`/editor/documents/${item.documentId}`}
          className="font-mono text-[10px] text-info"
        >
          {item.documentId}
        </Link>
        <p className="mt-1 truncate text-sm text-ink">{item.normalizedTitle}</p>
        <p className="mt-1 truncate text-[10px] text-muted">{item.managedTags.join(' · ')}</p>
      </td>
      <td className="px-3 py-3">
        <StatusBadge status={item.status} />
      </td>
      <td className="px-3 py-3">
        <StatusBadge status={item.processingStatus} />
      </td>
      <td className="px-3 py-3">
        <StatusBadge status={item.deduplicationStatus} />
        {item.duplicateOfDocumentId ? (
          <Link
            className="mt-1 block font-mono text-[9px] text-info hover:underline"
            to={`/editor/documents/${item.duplicateOfDocumentId}`}
          >
            оригинал
          </Link>
        ) : null}
      </td>
      <td className="px-3 py-3 font-mono">{item.original.score}</td>
      <td className="px-3 py-3">
        {item.original.answers.length}
        {item.original.answers.some((answer) => answer.accepted) ? ' · принят' : ''}
      </td>
      <td className="px-3 py-3 font-mono">{item.chunksCount}</td>
      <td className="px-3 py-3">
        <StatusBadge status={item.bm25Status} />
      </td>
      <td className="px-3 py-3">
        <StatusBadge status={item.vectorStatus} />
      </td>
      <td className="px-3 py-3 text-muted">
        {new Date(item.lastSyncedAt).toLocaleDateString('ru-RU')}
      </td>
      <td className="px-3 py-3 text-muted">
        {item.lastEditedAt ? new Date(item.lastEditedAt).toLocaleString('ru-RU') : '—'}
      </td>
      <td className="px-3 py-3">
        <RowActions item={item} onAction={onAction} />
      </td>
    </tr>
  );
}

function MobileCards({
  items,
  selected,
  onToggle,
  onAction,
}: {
  items: ManagedDocument[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onAction: (action: BulkDocumentAction, ids: string[]) => void;
}) {
  return (
    <div className="space-y-3 md:hidden">
      {items.map((item) => (
        <article key={item.documentId} className="panel p-4">
          <div className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={selected.has(item.documentId)}
              onChange={() => onToggle(item.documentId)}
              aria-label={`Выбрать ${item.documentId}`}
            />
            <div className="min-w-0 flex-1">
              <p className="font-mono text-[10px] text-info">{item.documentId}</p>
              <h2 className="mt-1 text-sm font-medium">{item.normalizedTitle}</h2>
            </div>
            <StatusBadge status={item.status} />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-muted">
            <span>
              Чанки <b className="text-ink">{item.chunksCount}</b>
            </span>
            <span>
              BM25 <b className="text-ink">{item.bm25Status}</b>
            </span>
            <span>
              Vector <b className="text-ink">{item.vectorStatus}</b>
            </span>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <StatusBadge status={item.processingStatus} />
            <StatusBadge status={item.deduplicationStatus} />
          </div>
          <div className="mt-3">
            <RowActions item={item} onAction={onAction} />
          </div>
        </article>
      ))}
    </div>
  );
}

function RowActions({
  item,
  onAction,
}: {
  item: ManagedDocument;
  onAction: (action: BulkDocumentAction, ids: string[]) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <Link
        to={`/editor/documents/${item.documentId}`}
        className="grid size-8 place-items-center rounded-md text-muted hover:bg-elevated hover:text-ink"
        aria-label={`Редактировать ${item.documentId}`}
      >
        <SquarePen className="size-3.5" />
      </Link>
      {['ACTIVE', 'OUTDATED'].includes(item.status) ? (
        <Button
          size="icon"
          variant="ghost"
          className="size-8"
          onClick={() => onAction('HIDE', [item.documentId])}
          aria-label={`Скрыть ${item.documentId}`}
        >
          <EyeOff className="size-3.5" />
        </Button>
      ) : null}
      {item.status === 'HIDDEN' ? (
        <Button
          size="icon"
          variant="ghost"
          className="size-8"
          onClick={() => onAction('RESTORE', [item.documentId])}
          aria-label={`Восстановить ${item.documentId}`}
        >
          <RotateCcw className="size-3.5" />
        </Button>
      ) : null}
      <Button
        size="icon"
        variant="ghost"
        className="size-8"
        onClick={() => onAction('REINDEX', [item.documentId])}
        aria-label={`Переиндексировать ${item.documentId}`}
      >
        <Workflow className="size-3.5" />
      </Button>
    </div>
  );
}

function toggleSet(current: Set<string>, value: string): Set<string> {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}
