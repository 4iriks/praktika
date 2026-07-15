import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Clipboard, Search, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  EmptyPanel,
  PageHeading,
  StatusBadge,
} from '../../components/management/ManagementUi';
import { Button } from '../../components/ui/Button';
import type { AuditEvent } from '../../types';
import { auditFilters, setParam } from '../../utils/managementParams';

const actions = [
  'ALL',
  'LOGIN',
  'LOGOUT',
  'REGISTER',
  'UPDATE_PROFILE',
  'UPDATE_DOCUMENT_METADATA',
  'HIDE_DOCUMENT',
  'RESTORE_DOCUMENT',
  'REINDEX_DOCUMENT',
  'BULK_HIDE_DOCUMENTS',
  'BULK_RESTORE_DOCUMENTS',
  'BULK_REINDEX_DOCUMENTS',
  'CHANGE_USER_ROLE',
  'BLOCK_USER',
  'UNBLOCK_USER',
  'UPDATE_SOURCE',
  'TEST_SOURCE',
  'START_SOURCE_SYNC',
  'STOP_SOURCE_SYNC',
  'RETRY_JOB',
  'CANCEL_JOB',
  'START_FULL_REINDEX',
  'HEALTH_CHECK',
  'UPDATE_SYSTEM_SETTINGS',
];

export function AuditPage() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => auditFilters(params), [params]);
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const query = useQuery({
    queryKey: queryKeys.admin.audit(filters),
    queryFn: ({ signal }) => api.getAuditEvents(filters, signal),
  });
  return (
    <>
      <PageHeading
        eyebrow="IMMUTABLE AUDIT LOG"
        title="Журнал аудита"
        description="События создаются внутри business/mock repository вместе с операцией. Редактирование и удаление журнала не предусмотрено."
      />
      <section className="panel mb-4 grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-5">
        <label className="relative sm:col-span-2">
          <Search className="absolute left-3 top-2.5 size-4 text-muted" />
          <span className="sr-only">Поиск по аудиту</span>
          <input
            value={filters.q}
            onChange={(event) => setParams(setParam(params, 'q', event.target.value))}
            placeholder="Событие, сущность, requestId"
            className="h-9 w-full rounded-md border border-line bg-elevated pl-9 pr-3 text-sm"
          />
        </label>
        <Select
          label="Действие"
          value={filters.action}
          options={actions}
          onChange={(value) => setParams(setParam(params, 'action', value))}
        />
        <Select
          label="Сущность"
          value={filters.entityType}
          options={['ALL', 'AUTH', 'USER', 'DOCUMENT', 'DOCUMENT_BATCH', 'SOURCE', 'JOB', 'SYSTEM']}
          onChange={(value) => setParams(setParam(params, 'entityType', value))}
        />
        <Select
          label="Результат"
          value={filters.outcome}
          options={['ALL', 'SUCCESS', 'FAILURE']}
          onChange={(value) => setParams(setParam(params, 'outcome', value))}
        />
      </section>
      {query.isPending ? <LoadingPanel /> : null}
      {query.isError ? <ErrorPanel message={query.error.message} /> : null}
      {query.data?.items.length === 0 ? (
        <EmptyPanel
          title="События не найдены"
          description="Выполните административное действие или измените фильтры."
        />
      ) : null}
      {query.data?.items.length ? (
        <>
          <div className="panel overflow-x-auto">
            <table className="w-full min-w-[1040px] text-left text-xs">
              <thead className="bg-elevated/70 text-muted">
                <tr>
                  {[
                    'Время',
                    'Actor',
                    'Роль',
                    'Действие',
                    'Сущность',
                    'Результат',
                    'Summary',
                    'Request ID',
                  ].map((label) => (
                    <th key={label} className="border-b border-line px-3 py-2 font-medium">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {query.data.items.map((event) => (
                  <tr
                    key={event.id}
                    className="cursor-pointer hover:bg-elevated/30"
                    onClick={() => setSelected(event)}
                  >
                    <td className="px-3 py-3 text-muted">
                      {new Date(event.createdAt).toLocaleString('ru-RU')}
                    </td>
                    <td className="px-3 py-3">{event.actorName}</td>
                    <td className="px-3 py-3 font-mono text-info">{event.actorRole ?? 'SYSTEM'}</td>
                    <td className="px-3 py-3 font-mono text-[10px]">{event.action}</td>
                    <td className="px-3 py-3">
                      <span className="font-mono text-[10px] text-muted">{event.entityType}</span>
                      <p className="mt-1 max-w-36 truncate">{event.entityLabel}</p>
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge status={event.outcome} />
                    </td>
                    <td className="max-w-xs px-3 py-3 text-muted">{event.summary}</td>
                    <td className="px-3 py-3 font-mono text-[10px] text-info">{event.requestId}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-muted">{query.data.pagination.total} событий</p>
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
      {selected ? (
        <div className="fixed inset-0 z-[90] grid place-items-center bg-canvas/80 p-4">
          <button
            type="button"
            className="absolute inset-0"
            aria-label="Закрыть детали события"
            onClick={() => setSelected(null)}
          />
          <section
            className="panel relative z-10 max-h-[90vh] w-full max-w-3xl overflow-y-auto p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="audit-detail-title"
          >
            <Button
              size="icon"
              variant="ghost"
              className="absolute right-3 top-3"
              onClick={() => setSelected(null)}
              aria-label="Закрыть"
            >
              <X className="size-5" />
            </Button>
            <p className="technical-label">{selected.action}</p>
            <h2 id="audit-detail-title" className="mt-1 pr-10 text-lg font-semibold">
              {selected.summary}
            </h2>
            <dl className="mt-5 grid gap-4 text-xs sm:grid-cols-3">
              <Meta label="Actor" value={selected.actorName} />
              <Meta label="Сущность" value={`${selected.entityType} · ${selected.entityLabel}`} />
              <Meta label="Время" value={new Date(selected.createdAt).toLocaleString('ru-RU')} />
            </dl>
            <div className="mt-4 flex items-center gap-2 rounded-lg border border-line bg-elevated p-3">
              <code className="min-w-0 flex-1 truncate text-xs text-info">
                {selected.requestId}
              </code>
              <Button
                size="icon"
                variant="ghost"
                onClick={() =>
                  void navigator.clipboard
                    .writeText(selected.requestId)
                    .then(() => toast.success('Request ID скопирован'))
                }
                aria-label="Копировать requestId"
              >
                <Clipboard className="size-4" />
              </Button>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <JsonBlock title="До" value={selected.before} />
              <JsonBlock title="После" value={selected.after} />
            </div>
            {selected.metadata ? (
              <div className="mt-4">
                <JsonBlock title="Метаданные" value={selected.metadata} />
              </div>
            ) : null}
          </section>
        </div>
      ) : null}
    </>
  );
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
function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-1 text-ink">{value}</dd>
    </div>
  );
}
function JsonBlock({ title, value }: { title: string; value: AuditEvent['before'] }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-semibold">{title}</h3>
      <pre className="max-h-64 overflow-auto rounded-lg border border-line bg-canvas p-3 font-mono text-[11px] leading-5 text-muted">
        {value ? JSON.stringify(value, null, 2) : 'Нет данных'}
      </pre>
    </section>
  );
}
