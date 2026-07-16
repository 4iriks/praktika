import { useQuery } from '@tanstack/react-query';
import { Box, Clock3, Cpu, Database, Gauge, Layers3 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import type { AskResponse, SearchRequest, SearchResponse } from '../../types';
import { formatDuration, formatNumber, formatScore } from '../../utils/format';
import { Badge } from '../ui/Badge';

interface TechnicalPanelProps {
  request: SearchRequest;
  searchResponse?: SearchResponse;
  askResponse?: AskResponse;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5 text-xs">
      <span className="text-muted">{label}</span>
      <span className="font-mono text-ink">{value}</span>
    </div>
  );
}

export function TechnicalPanel({ request, searchResponse, askResponse }: TechnicalPanelProps) {
  const status = useQuery({
    queryKey: queryKeys.system.status,
    queryFn: ({ signal }) => api.getPublicSystemStatus(signal),
  });
  const sources = askResponse?.sources ?? [];

  return (
    <aside className="h-full w-[310px] shrink-0 overflow-y-auto border-l border-line bg-surface px-4 py-5">
      <section aria-labelledby="services-title">
        <div className="mb-3 flex items-center gap-2">
          <Database className="size-3.5 text-muted" aria-hidden="true" />
          <h2 id="services-title" className="technical-label">
            Состояние сервисов
          </h2>
        </div>
        <div className="space-y-1 rounded-lg border border-line bg-elevated/35 p-2">
          {(status.data?.services ?? []).map((service) => (
            <div key={service.name} className="flex h-7 items-center gap-2 px-1.5 text-xs">
              <span
                className="size-1.5 rounded-full bg-success shadow-[0_0_0_3px_rgb(52_211_153_/_0.09)]"
                aria-hidden="true"
              />
              <span className="text-muted">{service.name}</span>
              <span className="ml-auto font-mono text-[10px] text-success">{service.state}</span>
            </div>
          ))}
          {status.isLoading ? (
            <p className="px-2 py-3 text-xs text-muted">Проверяем сервисы…</p>
          ) : null}
          {status.isError ? (
            <p className="px-2 py-3 text-xs text-danger">Статусы недоступны</p>
          ) : null}
        </div>
      </section>

      <section className="mt-6" aria-labelledby="request-title">
        <div className="mb-3 flex items-center gap-2">
          <Layers3 className="size-3.5 text-muted" aria-hidden="true" />
          <h2 id="request-title" className="technical-label">
            Параметры запроса
          </h2>
        </div>
        <div className="rounded-lg border border-line bg-elevated/35 px-3 py-2">
          <Metric label="Режим" value={request.mode.toUpperCase()} />
          <Metric label="Представление" value={request.view === 'answer' ? 'RAG' : 'DOCS'} />
          <Metric label="Страница" value={String(request.page)} />
          <Metric label="Сортировка" value={request.filters.sort} />
          <Metric label="Теги" value={request.filters.tags.join(', ') || '—'} />
        </div>
      </section>

      {searchResponse ? (
        <section className="mt-6" aria-labelledby="metrics-title">
          <div className="mb-3 flex items-center gap-2">
            <Gauge className="size-3.5 text-muted" aria-hidden="true" />
            <h2 id="metrics-title" className="technical-label">
              Метрики поиска
            </h2>
          </div>
          <div className="rounded-lg border border-line bg-elevated/35 px-3 py-2">
            <Metric label="Время" value={formatDuration(searchResponse.metrics.tookMs)} />
            <Metric label="Кандидаты" value={String(searchResponse.metrics.candidates)} />
            <Metric label="Переранжировано" value={String(searchResponse.metrics.reranked)} />
            <Metric
              label="Reranker"
              value={searchResponse.metrics.rerankerApplied === false ? 'FALLBACK' : 'APPLIED'}
            />
            <Metric
              label="Index"
              value={searchResponse.metrics.indexVersion?.slice(0, 12) ?? '—'}
            />
            <Metric
              label="Stale отброшено"
              value={String(searchResponse.metrics.staleDiscarded ?? 0)}
            />
            <Metric label="Токены запроса" value={String(searchResponse.metrics.queryTokens)} />
          </div>
        </section>
      ) : null}

      {askResponse ? (
        <section className="mt-6" aria-labelledby="model-title">
          <div className="mb-3 flex items-center gap-2">
            <Cpu className="size-3.5 text-muted" aria-hidden="true" />
            <h2 id="model-title" className="technical-label">
              Локальная модель
            </h2>
          </div>
          <div className="rounded-lg border border-line bg-elevated/35 px-3 py-2">
            <Metric label="Модель" value="Qwen" />
            <Metric label="Среда" value="Ollama" />
            <Metric label="Поиск" value={formatDuration(askResponse.searchTookMs)} />
            <Metric label="Генерация" value={formatDuration(askResponse.generationTookMs)} />
            <Metric label="Уверенность" value={Math.round(askResponse.confidence * 100) + '%'} />
          </div>
        </section>
      ) : null}

      {sources.length > 0 ? (
        <section className="mt-6" aria-labelledby="sources-title">
          <div className="mb-3 flex items-center gap-2">
            <Box className="size-3.5 text-muted" aria-hidden="true" />
            <h2 id="sources-title" className="technical-label">
              Использованные источники
            </h2>
          </div>
          <div className="space-y-2">
            {sources.map((source, index) => (
              <Link
                key={source.documentId}
                to={'/documents/' + source.documentId}
                className="block rounded-lg border border-line bg-elevated/35 p-3 transition hover:border-accent/50"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge tone="info">[{index + 1}]</Badge>
                  <span className="font-mono text-[10px] text-muted">
                    {formatScore(source.score)}
                  </span>
                </div>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-ink">{source.title}</p>
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      <div className="mt-6 rounded-lg border border-line bg-elevated/35 p-3 text-xs text-muted">
        <div className="flex items-center gap-2 text-ink">
          <Clock3 className="size-3.5" aria-hidden="true" />
          <span className="font-medium">Локальный индекс</span>
        </div>
        <p className="mt-2 leading-5">
          {formatNumber(status.data?.indexedDocuments ?? 25_000)} документов ·{' '}
          {formatNumber(status.data?.indexedChunks ?? 82_460)} чанков
        </p>
        <p className="mt-1">Обновлён {status.data?.updatedAt ?? '12 минут назад'}</p>
      </div>
    </aside>
  );
}
