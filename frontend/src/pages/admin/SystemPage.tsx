import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, Save } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  MetricCard,
  PageHeading,
  ProgressBar,
  StatusBadge,
} from '../../components/management/ManagementUi';
import { ReasonDialog } from '../../components/management/ReasonDialog';
import { Button } from '../../components/ui/Button';
import type { SystemSettings } from '../../types';

type SettingsForm = Omit<SystemSettings, 'updatedAt' | 'updatedBy'>;

export function SystemPage() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: queryKeys.admin.systemStatus,
    queryFn: ({ signal }) => api.getSystemStatus(signal),
  });
  const settings = useQuery({
    queryKey: queryKeys.admin.systemSettings,
    queryFn: ({ signal }) => api.getSystemSettings(signal),
  });
  const [form, setForm] = useState<SettingsForm | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  useEffect(() => {
    if (settings.data) {
      setForm({
        searchCandidatesLimit: settings.data.searchCandidatesLimit,
        rerankerLimit: settings.data.rerankerLimit,
        ragSourcesLimit: settings.data.ragSourcesLimit,
        defaultMinimumConfidence: settings.data.defaultMinimumConfidence,
        allowGuestSearch: settings.data.allowGuestSearch,
        allowGuestRag: settings.data.allowGuestRag,
        historyRetentionDays: settings.data.historyRetentionDays,
        auditRetentionDays: settings.data.auditRetentionDays,
      });
    }
  }, [settings.data]);
  const health = useMutation({
    mutationFn: () => api.runSystemHealthCheck(),
    onSuccess: async () => {
      toast.success('Состояние сервисов обновлено');
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.root });
    },
    onError: (error) => toast.error(error.message),
  });
  const update = useMutation({
    mutationFn: () => api.updateSystemSettings(form ?? {}),
    onSuccess: async () => {
      toast.success('Системные настройки сохранены');
      setConfirmOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.root }),
        queryClient.invalidateQueries({ queryKey: ['public-policy'] }),
      ]);
    },
    onError: (error) => toast.error(error.message),
  });
  if (status.isPending || settings.isPending)
    return <LoadingPanel label="Загружаем системную панель…" />;
  if (status.isError) return <ErrorPanel message={status.error.message} />;
  if (settings.isError) return <ErrorPanel message={settings.error.message} />;
  const data = status.data;
  return (
    <>
      <PageHeading
        eyebrow="SYSTEM & TELEMETRY"
        title="Система"
        description="Фактическое состояние API, PostgreSQL, workers, Qdrant, локальных моделей и корпуса. Недоступные метрики явно показаны как UNKNOWN."
        actions={
          <Button loading={health.isPending} onClick={() => health.mutate()}>
            <Activity className="size-4" />
            Проверить состояние сервисов
          </Button>
        }
      />
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data.services.map((service) => (
          <article key={service.id} className="panel p-4">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">{service.name}</h2>
              <StatusBadge status={service.status} />
            </div>
            <p className="mt-3 text-xs text-muted">{service.message}</p>
            <div className="mt-3 flex justify-between font-mono text-[10px] text-muted">
              <span>v{service.version}</span>
              <span>{service.latencyMs} мс</span>
            </div>
            <p className="mt-1 font-mono text-[9px] text-muted">
              {new Date(service.lastCheckAt).toLocaleString('ru-RU')}
            </p>
          </article>
        ))}
      </section>
      <section className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="CPU" value={formatMetric(data.metrics.cpuUsage, '%')} />
        <UsageCard
          label="RAM"
          value={data.metrics.ramUsageGb}
          limit={data.hardware.ramGb}
          unit="ГБ"
        />
        <UsageCard
          label="VRAM"
          value={data.metrics.vramUsageGb}
          limit={data.hardware.vramGb}
          unit="ГБ"
        />
        <UsageCard
          label="Диск проекта"
          value={data.metrics.diskUsageGb}
          limit={data.hardware.projectDiskLimitGb}
          unit="ГБ"
        />
        <MetricCard label="База данных" value={`${data.metrics.databaseSizeGb} ГБ`} />
        <MetricCard
          label="Vector index"
          value={formatMetric(data.metrics.vectorIndexSizeGb, ' ГБ')}
        />
        <MetricCard label="Модель" value={formatMetric(data.metrics.modelSizeGb, ' ГБ')} />
        <MetricCard
          label="Docker images"
          value={formatMetric(data.metrics.dockerImagesEstimateGb, ' ГБ')}
        />
        <MetricCard label="Документы" value={data.metrics.documentsCount.toLocaleString('ru-RU')} />
        <MetricCard label="Ответы" value={data.metrics.answersCount.toLocaleString('ru-RU')} />
        <MetricCard label="Чанки" value={data.metrics.chunksCount.toLocaleString('ru-RU')} />
        <MetricCard label="Ревизии" value={data.metrics.revisionsCount.toLocaleString('ru-RU')} />
        <MetricCard
          label="Ошибки ingestion"
          value={data.metrics.failuresCount.toLocaleString('ru-RU')}
        />
        <MetricCard
          label="Активные задания"
          value={data.metrics.activeJobs.toLocaleString('ru-RU')}
        />
        <MetricCard
          label="Последняя ingestion-активность"
          value={
            data.metrics.lastIngestionAt
              ? new Date(data.metrics.lastIngestionAt).toLocaleString('ru-RU')
              : '—'
          }
        />
      </section>
      <div className="mt-6 grid gap-5 xl:grid-cols-[0.75fr_1.25fr]">
        <section className="panel p-5">
          <h2 className="text-sm font-semibold">Локальная конфигурация</h2>
          <dl className="mt-4 space-y-3 text-sm">
            <Hardware label="ОС" value={data.hardware.operatingSystem} />
            <Hardware label="CPU" value={data.hardware.cpu} />
            <Hardware label="RAM" value={formatMetric(data.hardware.ramGb, ' ГБ')} />
            <Hardware label="GPU" value={data.hardware.gpu} />
            <Hardware label="VRAM" value={formatMetric(data.hardware.vramGb, ' ГБ')} />
            <Hardware label="Лимит проекта" value={`${data.hardware.projectDiskLimitGb} ГБ`} />
            <Hardware label="Приложение" value={data.metrics.applicationVersion} />
            <Hardware
              label="Документы / ответы / чанки"
              value={`${data.metrics.documentsCount.toLocaleString('ru-RU')} / ${data.metrics.answersCount.toLocaleString('ru-RU')} / ${data.metrics.chunksCount.toLocaleString('ru-RU')}`}
            />
          </dl>
        </section>
        {form ? (
          <section className="panel p-5">
            <h2 className="text-sm font-semibold">Системные настройки</h2>
            <p className="mt-1 text-xs text-muted">
              Публичные ограничения сохраняются в PostgreSQL и применяются к реальным Search/RAG.
            </p>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <NumberField
                label="Кандидаты поиска"
                value={form.searchCandidatesLimit}
                min={20}
                max={1000}
                onChange={(value) => setForm({ ...form, searchCandidatesLimit: value })}
              />
              <NumberField
                label="Лимит reranker"
                value={form.rerankerLimit}
                min={5}
                max={200}
                onChange={(value) => setForm({ ...form, rerankerLimit: value })}
              />
              <NumberField
                label="Источники RAG"
                value={form.ragSourcesLimit}
                min={1}
                max={10}
                onChange={(value) => setForm({ ...form, ragSourcesLimit: value })}
              />
              <NumberField
                label="Минимальная уверенность"
                value={form.defaultMinimumConfidence}
                min={0}
                max={1}
                step={0.05}
                onChange={(value) => setForm({ ...form, defaultMinimumConfidence: value })}
              />
              <NumberField
                label="Хранение истории, дней"
                value={form.historyRetentionDays}
                min={7}
                max={3650}
                onChange={(value) => setForm({ ...form, historyRetentionDays: value })}
              />
              <NumberField
                label="Хранение аудита, дней"
                value={form.auditRetentionDays}
                min={30}
                max={3650}
                onChange={(value) => setForm({ ...form, auditRetentionDays: value })}
              />
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <Toggle
                label="Разрешить гостевой поиск"
                checked={form.allowGuestSearch}
                onChange={(checked) => setForm({ ...form, allowGuestSearch: checked })}
              />
              <Toggle
                label="Разрешить гостевой RAG"
                checked={form.allowGuestRag}
                onChange={(checked) => setForm({ ...form, allowGuestRag: checked })}
              />
            </div>
            <Button className="mt-5" onClick={() => setConfirmOpen(true)}>
              <Save className="size-4" />
              Сохранить настройки
            </Button>
          </section>
        ) : null}
      </div>
      <ReasonDialog
        open={confirmOpen}
        title="Изменить системные настройки?"
        description="Изменения немедленно повлияют на гостевой поиск, гостевой RAG и число используемых источников в mock API."
        confirmLabel="Сохранить"
        loading={update.isPending}
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => update.mutate()}
      />
    </>
  );
}

function UsageCard({
  label,
  value,
  limit,
  unit,
}: {
  label: string;
  value: number | null;
  limit: number | null;
  unit: string;
}) {
  const percent =
    value !== null && limit !== null && limit > 0 ? Math.round((value / limit) * 100) : 0;
  return (
    <div className="panel p-4">
      <p className="technical-label">{label}</p>
      <p className="mt-2 font-mono text-xl font-semibold">
        {value === null ? 'UNKNOWN' : value} / {limit === null ? 'UNKNOWN' : limit} {unit}
      </p>
      <div className="mt-3">
        <ProgressBar value={percent} />
      </div>
    </div>
  );
}
function formatMetric(value: number | null, suffix: string) {
  return value === null ? 'UNKNOWN' : `${value}${suffix}`;
}
function Hardware({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line pb-2">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-mono text-xs text-ink">{value}</dd>
    </div>
  );
}
function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
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
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 font-mono text-sm text-ink"
      />
    </label>
  );
}
function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-3 rounded-lg border border-line p-3 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}
