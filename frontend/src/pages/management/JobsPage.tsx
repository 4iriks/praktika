import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronUp, Pause, Play, RefreshCw, RotateCcw, Square } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  EmptyPanel,
  PageHeading,
  ProgressBar,
  StatusBadge,
} from '../../components/management/ManagementUi';
import { ReasonDialog } from '../../components/management/ReasonDialog';
import { Button } from '../../components/ui/Button';
import type { BackgroundJob } from '../../types';
import { jobFilters, setParam } from '../../utils/managementParams';

export function EditorJobsPage() {
  return <JobsPage admin={false} />;
}
export function AdminJobsPage() {
  return <JobsPage admin />;
}

function JobsPage({ admin }: { admin: boolean }) {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => jobFilters(params), [params]);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [fullReindexOpen, setFullReindexOpen] = useState(false);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: admin ? queryKeys.admin.jobs(filters) : queryKeys.editor.jobs(filters),
    queryFn: ({ signal }) =>
      admin ? api.getAdminJobs(filters, signal) : api.getEditorJobs(filters, signal),
    refetchInterval: (state) =>
      autoRefresh &&
      state.state.data?.items.some((job) => ['QUEUED', 'RUNNING'].includes(job.status))
        ? 2_000
        : false,
  });
  const mutation = useMutation({
    mutationFn: ({ type, jobId }: { type: 'cancel' | 'retry' | 'full'; jobId?: string }) =>
      type === 'cancel'
        ? api.cancelJob(jobId ?? '')
        : type === 'retry'
          ? api.retryJob(jobId ?? '')
          : api.startFullReindex(),
    onSuccess: async (_, variables) => {
      toast.success(
        variables.type === 'cancel'
          ? 'Задание отменено'
          : variables.type === 'retry'
            ? 'Повторное задание создано'
            : 'Полная переиндексация запущена',
      );
      setFullReindexOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.root }),
        queryClient.invalidateQueries({ queryKey: queryKeys.editor.root }),
      ]);
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <>
      <PageHeading
        eyebrow={admin ? 'ADMIN JOBS' : 'EDITOR JOBS'}
        title={admin ? 'Все фоновые задания' : 'Задания редактора'}
        description={
          admin
            ? 'Durable PostgreSQL-очередь: checkpoint, lease, heartbeat, события, отмена и безопасный retry.'
            : 'Read-only наблюдение за заданиями и событиями worker. Управление доступно только ADMIN.'
        }
        actions={
          <>
            <Button size="sm" variant="ghost" onClick={() => setAutoRefresh((value) => !value)}>
              {autoRefresh ? <Pause className="size-4" /> : <Play className="size-4" />}
              {autoRefresh ? 'Пауза auto-refresh' : 'Включить auto-refresh'}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              loading={query.isFetching}
              onClick={() => void query.refetch()}
            >
              <RefreshCw className="size-4" />
              Обновить
            </Button>
            {admin ? (
              <Button size="sm" variant="danger" onClick={() => setFullReindexOpen(true)}>
                Полная переиндексация
              </Button>
            ) : null}
          </>
        }
      />
      <section className="panel mb-4 grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-6">
        <input
          aria-label="ID задания"
          value={filters.id}
          onChange={(event) => setParams(setParam(params, 'id', event.target.value))}
          placeholder="ID задания"
          className="h-9 rounded-md border border-line bg-elevated px-3 text-sm"
        />
        <Select
          label="Тип"
          value={filters.type}
          options={[
            'ALL',
            'SOURCE_SYNC',
            'DOCUMENT_REPROCESS',
            'DOCUMENT_REINDEX',
            'FULL_REINDEX',
            'HEALTH_CHECK',
          ]}
          onChange={(value) => setParams(setParam(params, 'type', value))}
        />
        <Select
          label="Статус"
          value={filters.status}
          options={['ALL', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED']}
          onChange={(value) => setParams(setParam(params, 'status', value))}
        />
        <Select
          label="Этап"
          value={filters.stage}
          options={[
            'ALL',
            'PREPARING',
            'FETCHING_QUESTIONS',
            'FETCHING_ANSWERS',
            'WAITING_BACKOFF',
            'PROCESSING',
            'CRAWLING',
            'CLEANING',
            'DEDUPLICATING',
            'CHUNKING',
            'EMBEDDING',
            'INDEXING_BM25',
            'INDEXING_VECTOR',
            'FINALIZING',
          ]}
          onChange={(value) => setParams(setParam(params, 'stage', value))}
        />
        <input
          aria-label="ID документа"
          value={filters.documentId}
          onChange={(event) => setParams(setParam(params, 'documentId', event.target.value))}
          placeholder="ID документа"
          className="h-9 rounded-md border border-line bg-elevated px-3 text-sm"
        />
        <Button size="sm" variant="ghost" onClick={() => setParams({ page: '1', limit: '20' })}>
          Сбросить
        </Button>
      </section>
      {query.isPending ? <LoadingPanel label="Читаем состояние очереди…" /> : null}
      {query.isError ? <ErrorPanel message={query.error.message} /> : null}
      {query.data?.items.length === 0 ? (
        <EmptyPanel title="Заданий нет" description="По выбранным фильтрам задания не найдены." />
      ) : null}
      {query.data?.items.length ? (
        <div className="space-y-3">
          {query.data.items.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              admin={admin}
              busy={mutation.isPending}
              onAction={(type) => mutation.mutate({ type, jobId: job.id })}
            />
          ))}
          <div className="flex items-center justify-between pt-2">
            <p className="text-xs text-muted">{query.data.pagination.total} заданий</p>
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
        </div>
      ) : null}
      <ReasonDialog
        open={fullReindexOpen}
        title="Запустить полную переиндексацию?"
        description="Будут перестроены BM25 и Vector индексы. Документы не удаляются, но операция создаст системное задание и audit event."
        confirmLabel="Запустить"
        loading={mutation.isPending}
        onClose={() => !mutation.isPending && setFullReindexOpen(false)}
        onConfirm={() => mutation.mutate({ type: 'full' })}
      />
    </>
  );
}

function JobCard({
  job,
  admin,
  busy,
  onAction,
}: {
  job: BackgroundJob;
  admin: boolean;
  busy: boolean;
  onAction: (type: 'cancel' | 'retry') => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const events = useQuery({
    queryKey: admin ? queryKeys.admin.jobEvents(job.id) : queryKeys.editor.jobEvents(job.id),
    queryFn: ({ signal }) =>
      admin ? api.getAdminJobEvents(job.id, signal) : api.getEditorJobEvents(job.id, signal),
    enabled: expanded,
    refetchInterval: expanded && ['QUEUED', 'RUNNING'].includes(job.status) ? 2_000 : false,
  });
  return (
    <article className="panel p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-info">{job.id}</span>
        <StatusBadge status={job.type} />
        <StatusBadge status={job.status} />
        <span className="font-mono text-[10px] text-muted">{job.stage}</span>
        <span className="ml-auto font-mono text-xs text-ink">{job.progress}%</span>
      </div>
      <div className="mt-3">
        <ProgressBar value={job.progress} />
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted">
        <span>
          {job.processedItems.toLocaleString('ru-RU')} / {job.totalItems.toLocaleString('ru-RU')}
        </span>
        <span>Создано: {new Date(job.createdAt).toLocaleString('ru-RU')}</span>
        {job.documentId ? (
          <Link className="text-info hover:underline" to={`/editor/documents/${job.documentId}`}>
            Документ {job.documentId}
          </Link>
        ) : null}
        {job.sourceId && admin ? (
          <Link className="text-info hover:underline" to="/admin/sources">
            Источник
          </Link>
        ) : null}
        {job.retryOfJobId ? <span>Повтор: {job.retryOfJobId}</span> : null}
        <span>
          Попытка {job.attempt ?? 0} / {job.maxAttempts ?? 5}
        </span>
        <span>Запросов: {(job.requestCount ?? 0).toLocaleString('ru-RU')}</span>
        <span>Получено: {formatBytes(job.bytesReceived ?? 0)}</span>
      </div>
      {job.errorMessage ? (
        <div className="mt-3 rounded-lg border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
          <b>{job.errorCode}</b> · {job.errorMessage}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="ghost"
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          {expanded ? 'Скрыть детали' : 'Детали и события'}
        </Button>
        {admin ? (
          <>
            {job.cancellable && ['QUEUED', 'RUNNING'].includes(job.status) ? (
              <Button size="sm" variant="danger" disabled={busy} onClick={() => onAction('cancel')}>
                <Square className="size-3.5" />
                Отменить
              </Button>
            ) : null}
            {['FAILED', 'CANCELLED'].includes(job.status) ? (
              <Button size="sm" disabled={busy} onClick={() => onAction('retry')}>
                <RotateCcw className="size-3.5" />
                Повторить
              </Button>
            ) : null}
          </>
        ) : null}
      </div>
      {expanded ? (
        <div className="mt-4 grid gap-4 border-t border-line pt-4 xl:grid-cols-[0.9fr_1.1fr]">
          <section aria-label="Технические детали задания">
            <dl className="grid grid-cols-2 gap-3 text-xs">
              <JobMeta label="Claimed by" value={job.claimedBy ?? '—'} />
              <JobMeta label="Claimed at" value={formatDate(job.claimedAt)} />
              <JobMeta label="Lease до" value={formatDate(job.leaseExpiresAt)} />
              <JobMeta label="Heartbeat" value={formatDate(job.heartbeatAt)} />
              <JobMeta label="Следующая попытка" value={formatDate(job.nextAttemptAt)} />
              <JobMeta label="Запрошена отмена" value={formatDate(job.cancellationRequestedAt)} />
            </dl>
            <JsonBlock label="Checkpoint" value={job.checkpoint} />
            <JsonBlock label="Результат" value={job.result} />
          </section>
          <section aria-label="События задания">
            <h3 className="text-sm font-semibold">Timeline событий</h3>
            {events.isPending ? (
              <p className="mt-3 text-xs text-muted">Загружаем события…</p>
            ) : null}
            {events.isError ? (
              <p className="mt-3 text-xs text-danger">{events.error.message}</p>
            ) : null}
            <ol className="mt-3 space-y-3">
              {events.data?.items.map((event) => (
                <li key={event.id} className="border-l border-line pl-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={event.level} />
                    <span className="font-mono text-[10px] text-info">{event.code}</span>
                    <span className="font-mono text-[10px] text-muted">{event.stage}</span>
                  </div>
                  <p className="mt-1 text-xs text-ink">{event.message}</p>
                  <time className="mt-1 block font-mono text-[10px] text-muted">
                    {new Date(event.createdAt).toLocaleString('ru-RU')}
                  </time>
                </li>
              ))}
            </ol>
            {events.data?.items.length === 0 ? (
              <p className="mt-3 text-xs text-muted">Событий пока нет.</p>
            ) : null}
          </section>
        </div>
      ) : null}
    </article>
  );
}

function JobMeta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-1 break-all font-mono text-ink">{value}</dd>
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value?: object }) {
  if (!value || Object.keys(value).length === 0) return null;
  return (
    <div className="mt-4">
      <p className="text-xs text-muted">{label}</p>
      <pre className="mt-2 max-h-44 overflow-auto rounded-lg border border-line bg-canvas p-3 font-mono text-[10px] text-info">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleString('ru-RU') : '—';
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} Б`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} КБ`;
  return `${(value / 1024 ** 2).toFixed(1)} МБ`;
}

function Select({
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
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-9 rounded-md border border-line bg-elevated px-2 text-xs"
    >
      {options.map((option) => (
        <option key={option}>{option}</option>
      ))}
    </select>
  );
}
