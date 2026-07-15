import type { ReactNode } from 'react';
import { AlertTriangle, Inbox, LoaderCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Badge } from '../ui/Badge';

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-4 border-b border-line pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="technical-label text-info">{eyebrow}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-muted">{description}</p>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  to,
  tone = 'neutral',
}: {
  label: string;
  value: string | number;
  detail?: string;
  to?: string;
  tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
}) {
  const body = (
    <>
      <p className="technical-label">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold text-ink">{value}</p>
      {detail ? <p className="mt-1 text-xs text-muted">{detail}</p> : null}
      <span
        className={
          'absolute inset-y-0 left-0 w-0.5 ' +
          (tone === 'danger'
            ? 'bg-danger'
            : tone === 'warning'
              ? 'bg-warning'
              : tone === 'success'
                ? 'bg-success'
                : tone === 'info'
                  ? 'bg-info'
                  : 'bg-line')
        }
      />
    </>
  );
  const classes =
    'panel relative block min-h-28 overflow-hidden p-4 text-left transition hover:border-muted/60';
  return to ? (
    <Link to={to} className={classes}>
      {body}
    </Link>
  ) : (
    <div className={classes}>{body}</div>
  );
}

const statusLabels: Record<string, string> = {
  ACTIVE: 'Активен',
  HIDDEN: 'Скрыт',
  PENDING: 'Ожидает',
  FAILED: 'Ошибка',
  OUTDATED: 'Устарел',
  READY: 'Готов',
  NOT_INDEXED: 'Не индексирован',
  QUEUED: 'В очереди',
  RUNNING: 'Выполняется',
  COMPLETED: 'Завершено',
  CANCELLED: 'Отменено',
  BLOCKED: 'Заблокирован',
  IDLE: 'Ожидает',
  CHECKING: 'Проверка',
  SYNCING: 'Синхронизация',
  PAUSED: 'Приостановлен',
  ERROR: 'Ошибка',
  DISABLED: 'Отключён',
  ONLINE: 'Онлайн',
  DEGRADED: 'Снижена доступность',
  OFFLINE: 'Офлайн',
  STARTING: 'Запускается',
  SUCCESS: 'Успешно',
  FAILURE: 'Ошибка',
};

export function StatusBadge({ status }: { status: string }) {
  const tone = ['ACTIVE', 'READY', 'COMPLETED', 'ONLINE', 'SUCCESS', 'IDLE'].includes(status)
    ? 'success'
    : ['FAILED', 'ERROR', 'OFFLINE', 'BLOCKED', 'FAILURE'].includes(status)
      ? 'danger'
      : ['PENDING', 'QUEUED', 'STARTING', 'OUTDATED', 'DEGRADED', 'PAUSED'].includes(status)
        ? 'warning'
        : status === 'RUNNING' || status === 'SYNCING' || status === 'CHECKING'
          ? 'info'
          : 'neutral';
  return <Badge tone={tone}>{statusLabels[status] ?? status}</Badge>;
}

export function LoadingPanel({ label = 'Загружаем данные…' }: { label?: string }) {
  return (
    <div className="panel grid min-h-64 place-items-center p-8 text-sm text-muted" role="status">
      <div className="flex items-center gap-2">
        <LoaderCircle className="size-4 animate-spin text-info" aria-hidden="true" />
        {label}
      </div>
    </div>
  );
}

export function ErrorPanel({ message }: { message: string }) {
  return (
    <div className="panel grid min-h-48 place-items-center border-danger/30 p-8 text-center">
      <div>
        <AlertTriangle className="mx-auto size-7 text-danger" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-ink">Не удалось получить данные</p>
        <p className="mt-1 text-xs text-muted">{message}</p>
      </div>
    </div>
  );
}

export function EmptyPanel({ title, description }: { title: string; description: string }) {
  return (
    <div className="panel grid min-h-48 place-items-center p-8 text-center">
      <div>
        <Inbox className="mx-auto size-7 text-muted" aria-hidden="true" />
        <p className="mt-3 text-sm font-medium text-ink">{title}</p>
        <p className="mt-1 text-xs text-muted">{description}</p>
      </div>
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div
      className="h-1.5 overflow-hidden rounded-full bg-elevated"
      aria-label={`Прогресс ${value}%`}
    >
      <div className="h-full rounded-full bg-info transition-all" style={{ width: `${value}%` }} />
    </div>
  );
}
