import { useQuery } from '@tanstack/react-query';
import { Activity, Bookmark, Clock3, MessageSquareText, Search } from 'lucide-react';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import { useAuth } from '../../features/auth/useAuth';
import { formatDate } from '../../utils/format';

export function AccountTechnicalPanel() {
  const { user } = useAuth();
  const stats = useQuery({
    queryKey: queryKeys.user.stats,
    queryFn: ({ signal }) => api.getUserStats(signal),
    enabled: Boolean(user),
  });

  return (
    <aside className="h-full w-[310px] shrink-0 overflow-y-auto border-l border-line bg-surface px-4 py-5">
      <div className="flex items-center gap-2">
        <Activity className="size-3.5 text-muted" aria-hidden="true" />
        <h2 className="technical-label">Аккаунт</h2>
      </div>
      {user ? (
        <div className="mt-3 rounded-lg border border-line bg-elevated/35 p-3">
          <p className="text-sm font-medium text-ink">{user.displayName}</p>
          <p className="mt-1 truncate text-xs text-muted">{user.email}</p>
          <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
            <span className="font-mono text-[10px] text-success">{user.accountStatus}</span>
            <span className="font-mono text-[10px] text-muted">{user.role}</span>
          </div>
          <p className="mt-2 text-[10px] text-muted">С нами с {formatDate(user.createdAt)}</p>
        </div>
      ) : null}

      <h2 className="technical-label mt-6">Активность</h2>
      <div className="mt-3 space-y-2">
        <Metric icon={Search} label="Поиски" value={stats.data?.documentSearches} />
        <Metric icon={MessageSquareText} label="RAG-запросы" value={stats.data?.ragSearches} />
        <Metric icon={Bookmark} label="Сохранено" value={stats.data?.savedDocuments} />
        <Metric icon={Clock3} label="Оценено" value={stats.data?.ratedAnswers} />
      </div>
    </aside>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Search;
  label: string;
  value?: number;
}) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-line bg-elevated/35 px-3 py-2.5">
      <Icon className="size-3.5 text-info" aria-hidden="true" />
      <span className="text-xs text-muted">{label}</span>
      <span className="ml-auto font-mono text-xs text-ink">{value ?? '—'}</span>
    </div>
  );
}
