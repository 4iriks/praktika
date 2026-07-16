import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { BrainCircuit, Play } from 'lucide-react';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  MetricCard,
  PageHeading,
} from '../../components/management/ManagementUi';
import { Button } from '../../components/ui/Button';
import { MarkdownContent } from '../../components/ui/MarkdownContent';
import type { AskResponse } from '../../types';

export function RagDiagnosticsPage() {
  const [question, setQuestion] = useState('В чём разница между asyncio.gather и create_task?');
  const [response, setResponse] = useState<AskResponse>();
  const status = useQuery({
    queryKey: queryKeys.admin.rag,
    queryFn: ({ signal }) => api.getRagDiagnostics(signal),
    refetchInterval: 10_000,
  });
  const test = useMutation({
    mutationFn: () =>
      api.testRag({
        question,
        mode: 'hybrid',
        maxSources: 5,
        clientRequestId: crypto.randomUUID(),
      }),
    onSuccess: setResponse,
    onError: (error) => toast.error(error.message),
  });
  if (status.isPending) return <LoadingPanel label="Проверяем локальный RAG…" />;
  if (status.isError) return <ErrorPanel message={status.error.message} />;
  const data = status.data;
  return (
    <>
      <PageHeading
        eyebrow="LOCAL GROUNDED GENERATION"
        title="Локальный RAG"
        description="Диагностика retrieval, контекста, Ollama qwen3:8b и проверяемых цитат. Hidden reasoning не сохраняется и не отображается."
      />
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Ollama" value={data.online ? 'ONLINE' : 'OFFLINE'} />
        <MetricCard
          label="qwen3:8b"
          value={data.modelInstalled ? (data.modelLoaded ? 'LOADED' : 'INSTALLED') : 'MISSING'}
        />
        <MetricCard
          label="Очередь"
          value={`${data.queueActive} / ${data.queueWaiting}`}
          detail={`limit ${data.queueLimit}`}
        />
        <MetricCard label="Context" value={`${data.contextTokens} tokens`} />
        <MetricCard label="Prompt" value={data.promptVersion} />
        <MetricCard label="Index" value={data.activeIndex?.slice(0, 12) ?? 'нет'} />
        <MetricCard
          label="Citation valid"
          value={`${Math.round(data.citationValidationRate * 100)}%`}
        />
        <MetricCard label="Средняя генерация" value={`${data.averageGenerationMs} мс`} />
      </section>
      <section className="panel mt-6 p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-ink">
          <BrainCircuit className="size-4" /> Диагностический запрос ADMIN
        </div>
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          className="mt-4 min-h-24 w-full rounded-lg border border-line bg-canvas p-3 text-sm"
          aria-label="Диагностический RAG-запрос"
        />
        <Button
          className="mt-3"
          variant="primary"
          loading={test.isPending}
          disabled={!question.trim()}
          onClick={() => test.mutate()}
        >
          <Play className="size-4" /> Проверить
        </Button>
        {response ? (
          <div className="mt-5 border-t border-line pt-5">
            <MarkdownContent>{response.answer}</MarkdownContent>
            <p className="mt-3 text-xs text-muted">
              Источники: {response.sources.length}; confidence{' '}
              {Math.round(response.confidence * 100)}%; citations{' '}
              {response.citationValidationPassed === false ? 'invalid' : 'valid'}
            </p>
          </div>
        ) : null}
      </section>
    </>
  );
}
