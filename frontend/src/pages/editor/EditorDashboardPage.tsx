import { useQuery } from '@tanstack/react-query';
import { ArrowRight, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  EmptyPanel,
  ErrorPanel,
  LoadingPanel,
  MetricCard,
  PageHeading,
  ProgressBar,
  StatusBadge,
} from '../../components/management/ManagementUi';

export function EditorDashboardPage() {
  const query = useQuery({
    queryKey: queryKeys.editor.dashboard,
    queryFn: ({ signal }) => api.getEditorDashboard(signal),
  });

  if (query.isPending) return <LoadingPanel label="Собираем метрики редактора…" />;
  if (query.isError) return <ErrorPanel message={query.error.message} />;
  const data = query.data;

  return (
    <>
      <PageHeading
        eyebrow="EDITOR WORKSPACE"
        title="Обзор редактора"
        description="Состояние базы документов, индексов и фоновых задач без декоративных метрик."
      />
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5" aria-label="Метрики документов">
        <MetricCard label="Всего документов" value={data.totalDocuments} to="/editor/documents" />
        <MetricCard
          label="Активные"
          value={data.statusCounts.ACTIVE}
          tone="success"
          to="/editor/documents?status=ACTIVE"
        />
        <MetricCard
          label="Скрытые"
          value={data.statusCounts.HIDDEN}
          tone="warning"
          to="/editor/documents?status=HIDDEN"
        />
        <MetricCard
          label="Ошибки"
          value={data.statusCounts.FAILED}
          tone="danger"
          to="/editor/documents?status=FAILED"
        />
        <MetricCard
          label="Устаревшие"
          value={data.statusCounts.OUTDATED}
          tone="warning"
          to="/editor/documents?status=OUTDATED"
        />
        <MetricCard
          label="BM25: ошибки"
          value={data.bm25Failed}
          tone="danger"
          to="/editor/documents?bm25=FAILED"
        />
        <MetricCard
          label="Vector: ошибки"
          value={data.vectorFailed}
          tone="danger"
          to="/editor/documents?vector=FAILED"
        />
        <MetricCard
          label="Активные задания"
          value={data.activeJobs}
          tone="info"
          to="/editor/jobs?status=RUNNING"
        />
        <MetricCard
          label="Завершено за сутки"
          value={data.completedJobsLastDay}
          tone="success"
          to="/editor/jobs?status=COMPLETED"
        />
        <MetricCard
          label="Ожидают модерации"
          value={data.statusCounts.PENDING}
          tone="warning"
          to="/editor/documents?status=PENDING"
        />
      </section>

      <div className="mt-6 grid gap-5 xl:grid-cols-2">
        <section className="panel overflow-hidden" aria-labelledby="attention-title">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 id="attention-title" className="flex items-center gap-2 text-sm font-semibold">
              <TriangleAlert className="size-4 text-warning" aria-hidden="true" />
              Требуют внимания
            </h2>
            <Link
              to="/editor/documents?status=FAILED"
              className="text-xs text-info hover:underline"
            >
              Открыть фильтр
            </Link>
          </div>
          {data.attentionDocuments.length === 0 ? (
            <EmptyPanel
              title="Нет проблем"
              description="Документы и индексы находятся в рабочем состоянии."
            />
          ) : (
            <div className="divide-y divide-line">
              {data.attentionDocuments.map((document) => (
                <Link
                  key={document.documentId}
                  to={`/editor/documents/${document.documentId}`}
                  className="flex items-center gap-3 px-4 py-3 transition hover:bg-elevated/50"
                >
                  <StatusBadge status={document.status} />
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {document.normalizedTitle}
                  </span>
                  <ArrowRight className="size-4 text-muted" aria-hidden="true" />
                </Link>
              ))}
            </div>
          )}
        </section>

        <section className="panel overflow-hidden" aria-labelledby="jobs-title">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 id="jobs-title" className="text-sm font-semibold">
              Последние задания
            </h2>
            <Link to="/editor/jobs" className="text-xs text-info hover:underline">
              Все задания
            </Link>
          </div>
          <div className="divide-y divide-line">
            {data.recentJobs.map((job) => (
              <div key={job.id} className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-info">{job.type}</span>
                  <StatusBadge status={job.status} />
                  <span className="ml-auto font-mono text-[11px] text-muted">{job.progress}%</span>
                </div>
                <div className="mt-2">
                  <ProgressBar value={job.progress} />
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
