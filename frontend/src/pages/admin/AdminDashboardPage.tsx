import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DatabaseZap, FileClock, ServerCog, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  MetricCard,
  PageHeading,
} from '../../components/management/ManagementUi';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';

const colors = ['#34d399', '#fb923c', '#f87171', '#38bdf8', '#818cf8'];

export function AdminDashboardPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.admin.dashboard,
    queryFn: ({ signal }) => api.getAdminDashboard(signal),
  });
  const sync = useMutation({
    mutationFn: () => api.startSourceSync('source-stackoverflow-ru'),
    onSuccess: async () => {
      toast.success('Синхронизация источника запущена');
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.root });
    },
    onError: (error) => toast.error(error.message),
  });
  if (query.isPending) return <LoadingPanel label="Собираем административные KPI…" />;
  if (query.isError) return <ErrorPanel message={query.error.message} />;
  const data = query.data;
  return (
    <>
      <PageHeading
        eyebrow="ADMIN CONTROL CENTER"
        title="Обзор администратора"
        description="Операционные показатели пользователей, поиска, документов и фоновых задач."
        actions={
          import.meta.env.VITE_USE_MOCKS === 'true' ? (
            <Badge tone="warning">Демонстрационные данные</Badge>
          ) : undefined
        }
      />
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        <MetricCard
          label="Пользователи"
          value={data.totalUsers}
          detail={`${data.activeUsers} активных`}
          to="/admin/users"
        />
        <MetricCard
          label="Заблокированы"
          value={data.blockedUsers}
          tone="danger"
          to="/admin/users?status=BLOCKED"
        />
        <MetricCard
          label="USER / EDITOR / ADMIN"
          value={`${data.usersByRole.USER} / ${data.usersByRole.EDITOR} / ${data.usersByRole.ADMIN}`}
          to="/admin/users"
        />
        <MetricCard
          label="Документы"
          value={data.documentsCount.toLocaleString('ru-RU')}
          detail={`${data.chunksCount.toLocaleString('ru-RU')} чанков`}
          to="/editor/documents"
        />
        <MetricCard
          label="Запросы за 24ч"
          value={data.searchesLastDay}
          detail={`RAG: ${data.ragLastDay}`}
          tone="info"
        />
        <MetricCard
          label="Success rate jobs"
          value={`${data.jobSuccessRate}%`}
          tone="success"
          to="/admin/jobs"
        />
        <MetricCard label="Средний поиск" value={`${data.averageSearchMs} мс`} />
        <MetricCard label="Средний RAG" value={`${data.averageRagMs} мс`} />
        <MetricCard label="Размер индекса" value={`${data.indexSizeGb} ГБ`} to="/admin/system" />
      </section>
      <section
        className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5"
        aria-label="Быстрые действия"
      >
        <QuickLink to="/admin/users" icon={Users} label="Открыть пользователей" />
        <QuickLink to="/admin/sources" icon={DatabaseZap} label="Открыть источники" />
        <Button
          className="justify-start"
          variant="secondary"
          loading={sync.isPending}
          onClick={() => sync.mutate()}
        >
          <DatabaseZap className="size-4" />
          Запустить source sync
        </Button>
        <QuickLink to="/admin/audit" icon={FileClock} label="Открыть аудит" />
        <QuickLink to="/admin/system" icon={ServerCog} label="Статус системы" />
      </section>
      <div className="mt-6 grid gap-5 xl:grid-cols-2">
        <ChartPanel title="Поиск и RAG · 7 дней" className="xl:col-span-2">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={data.querySeries}>
              <CartesianGrid stroke="#2b384f" strokeDasharray="3 3" />
              <XAxis dataKey="date" tick={{ fill: '#8e9cb4', fontSize: 11 }} />
              <YAxis tick={{ fill: '#8e9cb4', fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  background: '#0d1423',
                  border: '1px solid #2b384f',
                  borderRadius: 8,
                }}
              />
              <Line
                type="monotone"
                dataKey="searches"
                name="Поиск"
                stroke="#818cf8"
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="ragRequests"
                name="RAG"
                stroke="#38bdf8"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartPanel>
        <ChartPanel title="Документы по статусам">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.documentStatuses}>
              <CartesianGrid stroke="#2b384f" strokeDasharray="3 3" />
              <XAxis dataKey="status" tick={{ fill: '#8e9cb4', fontSize: 10 }} />
              <YAxis tick={{ fill: '#8e9cb4', fontSize: 11 }} />
              <Tooltip
                contentStyle={{
                  background: '#0d1423',
                  border: '1px solid #2b384f',
                  borderRadius: 8,
                }}
              />
              <Bar dataKey="count" name="Документы">
                {data.documentStatuses.map((entry, index) => (
                  <Cell key={entry.status} fill={colors[index % colors.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
        <ChartPanel title="Популярные Python-теги">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.popularTags} layout="vertical">
              <CartesianGrid stroke="#2b384f" strokeDasharray="3 3" />
              <XAxis type="number" tick={{ fill: '#8e9cb4', fontSize: 11 }} />
              <YAxis
                dataKey="tag"
                type="category"
                width={76}
                tick={{ fill: '#8e9cb4', fontSize: 11 }}
              />
              <Tooltip
                contentStyle={{
                  background: '#0d1423',
                  border: '1px solid #2b384f',
                  borderRadius: 8,
                }}
              />
              <Bar dataKey="count" fill="#38bdf8" />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>
      </div>
    </>
  );
}

function QuickLink({ to, icon: Icon, label }: { to: string; icon: typeof Users; label: string }) {
  return (
    <Link
      to={to}
      className="flex h-10 items-center gap-2 rounded-lg border border-line bg-elevated px-3 text-sm text-ink transition hover:border-muted"
    >
      <Icon className="size-4 text-info" />
      {label}
    </Link>
  );
}
function ChartPanel({
  title,
  className = '',
  children,
}: {
  title: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`panel p-4 ${className}`}>
      <h2 className="mb-4 text-sm font-semibold">{title}</h2>
      {children}
    </section>
  );
}
