import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DatabaseZap, Search, ShieldCheck, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  MetricCard,
  PageHeading,
  StatusBadge,
} from '../../components/management/ManagementUi';
import { Button } from '../../components/ui/Button';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import type { SearchMode, SearchResponse } from '../../types';

export function IndexesPage() {
  const queryClient = useQueryClient();
  const [fullConfirm, setFullConfirm] = useState(false);
  const [cleanupConfirm, setCleanupConfirm] = useState(false);
  const [diagnosticQuery, setDiagnosticQuery] = useState('asyncio gather');
  const [diagnosticMode, setDiagnosticMode] = useState<SearchMode>('hybrid');
  const [diagnosticResult, setDiagnosticResult] = useState<SearchResponse>();
  const stats = useQuery({
    queryKey: queryKeys.admin.indexStats,
    queryFn: ({ signal }) => api.getSearchIndexStats(signal),
    refetchInterval: (query) => (query.state.data?.currentFullReindexJob ? 3000 : false),
  });
  const versions = useQuery({
    queryKey: queryKeys.admin.indexes,
    queryFn: ({ signal }) => api.getSearchIndexes(signal),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.admin.indexes });
  };
  const full = useMutation({
    mutationFn: () => api.startSearchIndexFullReindex(),
    onSuccess: async () => {
      toast.success('Blue-green переиндексация поставлена в очередь');
      await refresh();
    },
    onError: (error) => toast.error(error.message),
  });
  const validate = useMutation({
    mutationFn: (id: string) => api.validateSearchIndex(id),
    onSuccess: async () => {
      toast.success('Проверка индекса поставлена в очередь');
      await refresh();
    },
    onError: (error) => toast.error(error.message),
  });
  const cleanup = useMutation({
    mutationFn: (confirmed: boolean) => api.cleanupSearchIndexes(!confirmed, confirmed),
    onSuccess: async (_, confirmed) => {
      toast.success(confirmed ? 'Очистка поставлена в очередь' : 'Dry-run поставлен в очередь');
      await refresh();
    },
    onError: (error) => toast.error(error.message),
  });
  const diagnose = useMutation({
    mutationFn: () =>
      api.searchDocuments({
        q: diagnosticQuery,
        view: 'documents',
        mode: diagnosticMode,
        page: 1,
        pageSize: 5,
        filters: {
          tags: [],
          minScore: 0,
          acceptedOnly: false,
          hasCodeOnly: false,
          sort: 'relevance',
        },
      }),
    onSuccess: setDiagnosticResult,
    onError: (error) => toast.error(error.message),
  });

  if (stats.isPending || versions.isPending) return <LoadingPanel label="Загружаем индекс…" />;
  if (stats.isError) return <ErrorPanel message={stats.error.message} />;
  if (versions.isError) return <ErrorPanel message={versions.error.message} />;
  const data = stats.data;
  return (
    <>
      <PageHeading
        eyebrow="QDRANT SEARCH INDEX"
        title="Поисковый индекс"
        description="Производный индекс PostgreSQL: dense qwen3 embeddings, native BM25 и безопасное переключение alias."
        actions={
          <>
            <Button onClick={() => cleanup.mutate(false)} loading={cleanup.isPending}>
              <Trash2 className="size-4" /> Dry-run cleanup
            </Button>
            <Button variant="primary" onClick={() => setFullConfirm(true)}>
              <DatabaseZap className="size-4" /> Full reindex
            </Button>
          </>
        }
      />
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Qdrant"
          value={data.qdrantOnline ? 'ONLINE' : 'OFFLINE'}
          detail={data.qdrantMessage}
        />
        <MetricCard label="Alias" value={data.aliasTarget ?? 'не создан'} detail={data.aliasName} />
        <MetricCard label="Points" value={data.pointsCount.toLocaleString('ru-RU')} />
        <MetricCard
          label="Eligible / stale"
          value={`${data.eligibleChunks} / ${data.staleChunks}`}
        />
        <MetricCard label="Indexer" value={data.indexerOnline ? 'ONLINE' : 'OFFLINE'} />
        <MetricCard
          label="Embedding"
          value={data.embeddingModel}
          detail={`${data.embeddingDimensions} dimensions`}
        />
        <MetricCard
          label="Model"
          value={data.embeddingModelInstalled ? 'установлена' : 'отсутствует'}
        />
        <MetricCard label="Qdrant version" value={data.qdrantVersion ?? '—'} />
      </section>
      <section className="panel mt-6 overflow-x-auto">
        <table className="w-full min-w-[900px] text-left text-sm">
          <thead className="border-b border-line text-xs text-muted">
            <tr>
              <th className="p-4">Статус</th>
              <th>Collection</th>
              <th>Модели</th>
              <th>Points</th>
              <th>Создан</th>
              <th className="p-4 text-right">Действия</th>
            </tr>
          </thead>
          <tbody>
            {versions.data.items.map((version) => (
              <tr key={version.id} className="border-b border-line/70 last:border-0">
                <td className="p-4">
                  <StatusBadge status={version.status} />
                </td>
                <td className="font-mono text-xs">{version.collectionName}</td>
                <td className="text-xs">
                  {version.embeddingModel}
                  <br />
                  {version.sparseModel}
                </td>
                <td className="font-mono">{version.pointCount}</td>
                <td className="text-xs text-muted">
                  {new Date(version.createdAt).toLocaleString('ru-RU')}
                </td>
                <td className="p-4 text-right">
                  <Button
                    size="sm"
                    onClick={() => validate.mutate(version.id)}
                    loading={validate.isPending}
                  >
                    <ShieldCheck className="size-4" /> Validate
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <section className="panel mt-6 p-5">
        <h2 className="text-base font-semibold text-ink">Search diagnostics</h2>
        <p className="mt-1 text-xs text-muted">
          Реальный запрос к active alias с component scores и фактическими timings.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <input
            className="min-w-64 flex-1 rounded-lg border border-line bg-elevated px-3 py-2 text-sm text-ink"
            value={diagnosticQuery}
            onChange={(event) => setDiagnosticQuery(event.target.value)}
            aria-label="Диагностический запрос"
          />
          <select
            className="rounded-lg border border-line bg-elevated px-3 py-2 text-sm text-ink"
            value={diagnosticMode}
            onChange={(event) => setDiagnosticMode(event.target.value as SearchMode)}
            aria-label="Режим диагностики"
          >
            <option value="bm25">BM25</option>
            <option value="vector">Vector</option>
            <option value="hybrid">Hybrid</option>
          </select>
          <Button
            onClick={() => diagnose.mutate()}
            loading={diagnose.isPending}
            disabled={!diagnosticQuery.trim()}
          >
            <Search className="size-4" /> Выполнить
          </Button>
        </div>
        {diagnosticResult ? (
          <div className="mt-4 space-y-2">
            <p className="font-mono text-xs text-muted">
              {diagnosticResult.metrics.tookMs} ms · {diagnosticResult.metrics.candidates}{' '}
              candidates · reranker{' '}
              {diagnosticResult.metrics.rerankerApplied === false ? 'fallback' : 'applied'}
            </p>
            {diagnosticResult.results.map((result) => (
              <div key={result.documentId} className="rounded-lg border border-line p-3 text-xs">
                <p className="font-medium text-ink">{result.title}</p>
                <p className="mt-1 font-mono text-muted">
                  BM25 {result.bm25Score ?? '—'} · vector {result.vectorScore ?? '—'} · fusion{' '}
                  {result.fusionScore ?? '—'} · reranker {result.rerankerScore ?? '—'}
                </p>
              </div>
            ))}
          </div>
        ) : null}
      </section>
      <Button className="mt-4" variant="danger" onClick={() => setCleanupConfirm(true)}>
        Очистить устаревшие collections
      </Button>
      <ConfirmDialog
        open={fullConfirm}
        title="Запустить полную переиндексацию?"
        description="Будет создана новая физическая collection. Alias переключится только после полной проверки."
        confirmLabel="Запустить"
        onClose={() => setFullConfirm(false)}
        onConfirm={() => full.mutate()}
      />
      <ConfirmDialog
        open={cleanupConfirm}
        title="Удалить устаревшие collections?"
        description="ACTIVE collection и текущий alias защищены от удаления."
        confirmLabel="Очистить"
        onClose={() => setCleanupConfirm(false)}
        onConfirm={() => cleanup.mutate(true)}
      />
    </>
  );
}
