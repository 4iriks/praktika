import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleStop, Play, PlugZap, Save } from 'lucide-react';
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
import type { Source, SourceUpdateRequest } from '../../types';
import { sourceFilters } from '../../utils/managementParams';

export function SourcesPage() {
  const [params] = useSearchParams();
  const filters = useMemo(() => sourceFilters(params), [params]);
  const query = useQuery({
    queryKey: queryKeys.admin.sources(filters),
    queryFn: ({ signal }) => api.getSources(filters, signal),
  });
  if (query.isPending) return <LoadingPanel label="Загружаем источники…" />;
  if (query.isError) return <ErrorPanel message={query.error.message} />;
  return (
    <>
      <PageHeading
        eyebrow="DATA SOURCES"
        title="Источники данных"
        description="Конфигурация синтетического Stack Exchange source и управление его mock-синхронизацией."
      />
      {query.data.items.length === 0 ? (
        <EmptyPanel title="Источников нет" description="По заданным фильтрам ничего не найдено." />
      ) : (
        <div className="space-y-5">
          {query.data.items.map((source) => (
            <SourceCard key={source.id} source={source} />
          ))}
        </div>
      )}
    </>
  );
}

function SourceCard({ source }: { source: Source }) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<SourceUpdateRequest>({
    targetDocuments: source.targetDocuments,
    maxAdditionalAnswers: source.maxAdditionalAnswers,
    pageSize: source.pageSize,
    enabled: source.enabled,
  });
  const [stopOpen, setStopOpen] = useState(false);
  useEffect(
    () =>
      setForm({
        targetDocuments: source.targetDocuments,
        maxAdditionalAnswers: source.maxAdditionalAnswers,
        pageSize: source.pageSize,
        enabled: source.enabled,
      }),
    [source],
  );
  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.root }),
      queryClient.invalidateQueries({ queryKey: queryKeys.editor.root }),
    ]);
  const update = useMutation({
    mutationFn: () => api.updateSource(source.id, form),
    onSuccess: async () => {
      toast.success('Настройки источника сохранены');
      await invalidate();
    },
    onError: (error) => toast.error(error.message),
  });
  const test = useMutation({
    mutationFn: () => api.testSourceConnection(source.id),
    onSuccess: async (result) => {
      toast.success(`${result.message} ${result.latencyMs} мс`);
      await invalidate();
    },
    onError: (error) => toast.error(error.message),
  });
  const sync = useMutation({
    mutationFn: () => api.startSourceSync(source.id),
    onSuccess: async () => {
      toast.success('Синхронизация запущена');
      await invalidate();
    },
    onError: (error) => toast.error(error.message),
  });
  const stop = useMutation({
    mutationFn: () => api.stopSourceSync(source.id),
    onSuccess: async () => {
      toast.success('Синхронизация остановлена');
      setStopOpen(false);
      await invalidate();
    },
    onError: (error) => toast.error(error.message),
  });
  const quota = Math.round((source.rateLimitRemaining / source.rateLimitTotal) * 100);
  return (
    <article className="panel overflow-hidden">
      <div className="flex flex-col gap-4 border-b border-line p-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold">{source.name}</h2>
            <StatusBadge status={source.status} />
            <span className="font-mono text-[10px] text-info">{source.type}</span>
          </div>
          <p className="mt-2 text-sm text-muted">
            {source.baseUrl} · tag: <span className="font-mono">{source.tag}</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" loading={test.isPending} onClick={() => test.mutate()}>
            <PlugZap className="size-4" />
            Проверить
          </Button>
          {source.status === 'SYNCING' ? (
            <Button size="sm" variant="danger" onClick={() => setStopOpen(true)}>
              <CircleStop className="size-4" />
              Остановить
            </Button>
          ) : (
            <Button
              size="sm"
              loading={sync.isPending}
              disabled={!source.enabled}
              onClick={() => sync.mutate()}
            >
              <Play className="size-4" />
              Синхронизировать
            </Button>
          )}
        </div>
      </div>
      <div className="grid gap-5 p-5 xl:grid-cols-[1fr_0.8fr]">
        <section>
          <h3 className="text-sm font-semibold">Настройки загрузки</h3>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <NumberField
              label="Целевое число документов"
              value={form.targetDocuments ?? 25000}
              min={5000}
              max={100000}
              onChange={(value) => setForm((current) => ({ ...current, targetDocuments: value }))}
            />
            <NumberField
              label="Дополнительные ответы"
              value={form.maxAdditionalAnswers ?? 3}
              min={0}
              max={3}
              onChange={(value) =>
                setForm((current) => ({ ...current, maxAdditionalAnswers: value }))
              }
            />
            <NumberField
              label="Page size"
              value={form.pageSize ?? 100}
              min={1}
              max={100}
              onChange={(value) => setForm((current) => ({ ...current, pageSize: value }))}
            />
            <label className="flex items-center gap-2 rounded-lg border border-line p-3 text-sm">
              <input
                type="checkbox"
                checked={form.enabled ?? true}
                onChange={(event) =>
                  setForm((current) => ({ ...current, enabled: event.target.checked }))
                }
              />
              Источник включён
            </label>
          </div>
          <Button className="mt-4" loading={update.isPending} onClick={() => update.mutate()}>
            <Save className="size-4" />
            Сохранить настройки
          </Button>
        </section>
        <section className="rounded-lg border border-line bg-elevated/40 p-4">
          <h3 className="text-sm font-semibold">Техническое состояние</h3>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-xs">
            <Meta label="Документов" value={source.documentsCount.toLocaleString('ru-RU')} />
            <Meta
              label="Последняя синхронизация"
              value={
                source.lastSuccessfulSyncAt
                  ? new Date(source.lastSuccessfulSyncAt).toLocaleString('ru-RU')
                  : '—'
              }
            />
            <Meta
              label="API key"
              value={source.apiKeyConfigured ? 'настроен' : 'не требуется в mock'}
            />
            <Meta label="Текущее задание" value={source.currentJobId ?? '—'} />
          </dl>
          <div className="mt-4">
            <div className="mb-2 flex justify-between text-xs text-muted">
              <span>Синтетическая квота</span>
              <span>
                {source.rateLimitRemaining} / {source.rateLimitTotal}
              </span>
            </div>
            <ProgressBar value={quota} />
          </div>
          {source.currentJobId ? (
            <Link
              to={`/admin/jobs?id=${source.currentJobId}`}
              className="mt-4 inline-block text-xs text-info hover:underline"
            >
              Открыть связанное задание
            </Link>
          ) : null}
        </section>
      </div>
      <ReasonDialog
        open={stopOpen}
        title="Остановить синхронизацию?"
        description="Активное job будет переведено в CANCELLED, а источник — в PAUSED."
        confirmLabel="Остановить"
        loading={stop.isPending}
        onClose={() => setStopOpen(false)}
        onConfirm={() => stop.mutate()}
      />
    </article>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="text-xs text-muted">
      {label}
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 font-mono text-sm text-ink"
      />
    </label>
  );
}
function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-1 break-all font-mono text-ink">{value}</dd>
    </div>
  );
}
