import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BookOpen,
  Bookmark,
  BookmarkCheck,
  CheckCircle2,
  Clipboard,
  ExternalLink,
  RotateCcw,
  ThumbsDown,
  ThumbsUp,
  TriangleAlert,
  X,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import type {
  AskRequest,
  AskResponse,
  FeedbackReason,
  FeedbackRequest,
  RagSource,
  SearchFilters,
} from '../../types';
import { formatDuration, formatScore } from '../../utils/format';
import { loginUrl } from '../../utils/returnTo';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { ExternalSourceLink } from '../../components/ui/ExternalSourceLink';
import { MarkdownContent } from '../../components/ui/MarkdownContent';
import { ErrorState } from '../../components/ui/QueryStates';
import { useAuth } from '../auth/useAuth';
import { useSavedDocument } from '../documents/useSavedDocument';
import { RagProgress } from './RagProgress';
import { useRagStream } from './useRagStream';

interface RagAnswerProps {
  question: string;
  mode: AskRequest['mode'];
  filters?: SearchFilters;
  pageSize?: number;
  onResponse?: (response: AskResponse) => void;
}

export function RagAnswer({ question, mode, filters, pageSize, onResponse }: RagAnswerProps) {
  const [retryKey, setRetryKey] = useState(0);
  const [negativeDialogOpen, setNegativeDialogOpen] = useState(false);
  const request = useMemo<AskRequest>(
    () => ({ question, mode, maxSources: 3, filters, pageSize }),
    [filters, mode, pageSize, question],
  );
  const complete = useCallback((response: AskResponse) => onResponse?.(response), [onResponse]);
  const stream = useRagStream(request, retryKey, complete);
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const currentResponseId = stream.data?.responseId ?? '';
  const feedback = useQuery({
    queryKey: queryKeys.feedback.response(currentResponseId),
    queryFn: ({ signal }) => api.getFeedbackForResponse(currentResponseId, signal),
    enabled: Boolean(user && currentResponseId),
  });
  const feedbackMutation = useMutation({
    mutationFn: (value: FeedbackRequest) => api.sendFeedback(value),
    onSuccess: (savedFeedback) => {
      const wasRated = Boolean(feedback.data);
      queryClient.setQueryData(
        queryKeys.feedback.response(savedFeedback.responseId),
        savedFeedback,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.stats });
      toast.success(wasRated ? 'Оценка ответа изменена' : 'Оценка ответа сохранена');
      setNegativeDialogOpen(false);
    },
    onError: () => toast.error('Не удалось сохранить оценку'),
  });
  const deleteFeedback = useMutation({
    mutationFn: (feedbackId: string) => api.deleteFeedback(feedbackId),
    onSuccess: () => {
      queryClient.setQueryData(queryKeys.feedback.response(currentResponseId), null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.stats });
      toast.success('Оценка удалена');
    },
    onError: () => toast.error('Не удалось удалить оценку'),
  });

  const requireAccount = (): boolean => {
    if (user) return true;
    toast.info('Войдите, чтобы оценить ответ');
    navigate(loginUrl(location.pathname + location.search));
    return false;
  };

  const submitPositive = () => {
    if (!stream.data || !requireAccount()) return;
    feedbackMutation.mutate({
      responseId: stream.data.responseId,
      value: 'positive',
      question,
    });
  };

  const copyAnswer = async () => {
    const answer = stream.data?.answer ?? stream.streamedAnswer;
    try {
      await navigator.clipboard.writeText(answer);
      toast.success('Ответ скопирован');
    } catch {
      toast.error('Браузер не разрешил копирование');
    }
  };

  const scrollToSources = () => {
    document.getElementById('rag-sources')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (stream.error) return <ErrorState onRetry={() => setRetryKey((key) => key + 1)} />;

  return (
    <article className="panel overflow-hidden" aria-label="Ответ ИИ">
      <header className="flex flex-col gap-3 border-b border-line px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <div>
          <div className="flex items-center gap-2">
            <Badge tone="accent">RAG</Badge>
            <span className="font-mono text-[10px] text-muted">{mode.toUpperCase()}</span>
          </div>
          <h1 className="mt-3 text-base font-semibold leading-6 text-ink sm:text-lg">{question}</h1>
        </div>
        <Badge tone={stream.data?.insufficientContext ? 'warning' : 'success'}>
          {stream.isLoading
            ? 'формирование'
            : stream.data?.insufficientContext
              ? 'мало контекста'
              : Math.round((stream.data?.confidence ?? 0) * 100) + '% уверенности'}
        </Badge>
      </header>

      <RagProgress stage={stream.stage} />

      <div className="px-4 py-5 sm:px-6 sm:py-7">
        {stream.streamedAnswer ? (
          stream.data?.insufficientContext ? (
            <div className="flex gap-3 rounded-xl border border-warning/35 bg-warning/10 p-4 text-sm leading-6 text-warning">
              <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
              <p>{stream.streamedAnswer}</p>
            </div>
          ) : (
            <div className={stream.isLoading ? 'stream-cursor' : undefined}>
              <MarkdownContent>{stream.streamedAnswer}</MarkdownContent>
            </div>
          )
        ) : (
          <div className="space-y-3 py-2" aria-label="Генерация ответа">
            <div className="skeleton h-5 w-1/3 rounded" />
            <div className="skeleton h-3 w-full rounded" />
            <div className="skeleton h-3 w-5/6 rounded" />
            <div className="skeleton h-24 w-full rounded-lg" />
          </div>
        )}

        {stream.data ? (
          <>
            <div className="mt-6 flex flex-wrap gap-2 border-t border-line pt-4">
              <Badge>{stream.data.model}</Badge>
              <Badge>поиск {formatDuration(stream.data.searchTookMs)}</Badge>
              <Badge>генерация {formatDuration(stream.data.generationTookMs)}</Badge>
              <Badge>{stream.data.sources.length} источника</Badge>
            </div>
            <div className="mt-4 flex gap-2 rounded-lg border border-warning/25 bg-warning/5 px-3 py-2.5 text-xs leading-5 text-muted">
              <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning" aria-hidden="true" />
              Ответ сформирован на основании найденных материалов.
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => void copyAnswer()} disabled={!stream.data.answer}>
                <Clipboard className="size-3.5" aria-hidden="true" />
                Копировать ответ
              </Button>
              <Button size="sm" onClick={() => setRetryKey((key) => key + 1)}>
                <RotateCcw className="size-3.5" aria-hidden="true" />
                Повторить запрос
              </Button>
              <Button
                size="sm"
                variant={feedback.data?.value === 'positive' ? 'primary' : 'ghost'}
                disabled={feedbackMutation.isPending || deleteFeedback.isPending}
                onClick={submitPositive}
              >
                <ThumbsUp className="size-3.5" aria-hidden="true" />
                Полезно
              </Button>
              <Button
                size="sm"
                variant={feedback.data?.value === 'negative' ? 'danger' : 'ghost'}
                disabled={feedbackMutation.isPending || deleteFeedback.isPending}
                onClick={() => {
                  if (requireAccount()) setNegativeDialogOpen(true);
                }}
              >
                <ThumbsDown className="size-3.5" aria-hidden="true" />
                Не полезно
              </Button>
              {feedback.data ? (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={deleteFeedback.isPending}
                  onClick={() => {
                    if (feedback.data) deleteFeedback.mutate(feedback.data.id);
                  }}
                >
                  <X className="size-3.5" aria-hidden="true" />
                  Отменить оценку
                </Button>
              ) : null}
              <Button size="sm" variant="ghost" className="sm:ml-auto" onClick={scrollToSources}>
                <BookOpen className="size-3.5" aria-hidden="true" />
                Открыть источники
              </Button>
            </div>
          </>
        ) : null}
      </div>

      {stream.data && stream.data.sources.length > 0 ? (
        <section id="rag-sources" className="border-t border-line bg-elevated/20 px-4 py-5 sm:px-6">
          <h2 className="technical-label">Использованные источники</h2>
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            {stream.data.sources.map((source, index) => (
              <RagSourceCard key={source.documentId} source={source} index={index} />
            ))}
          </div>
          <p className="mt-4 flex items-center gap-2 text-[11px] text-muted">
            <CheckCircle2 className="size-3.5 text-success" aria-hidden="true" />
            Цитаты привязаны только к найденным документам.
          </p>
        </section>
      ) : null}

      {negativeDialogOpen ? (
        <NegativeFeedbackDialog
          open
          initialReason={feedback.data?.value === 'negative' ? feedback.data.reason : undefined}
          initialComment={feedback.data?.value === 'negative' ? feedback.data.comment : undefined}
          loading={feedbackMutation.isPending}
          onClose={() => setNegativeDialogOpen(false)}
          onSubmit={(reason, comment) => {
            if (!stream.data) return;
            feedbackMutation.mutate({
              responseId: stream.data.responseId,
              value: 'negative',
              question,
              ...(reason ? { reason } : {}),
              ...(comment.trim() ? { comment: comment.trim() } : {}),
            });
          }}
        />
      ) : null}
    </article>
  );
}

function RagSourceCard({ source, index }: { source: RagSource; index: number }) {
  const saved = useSavedDocument(source.documentId, source.saved);
  return (
    <article id={'source-' + (index + 1)} className="rounded-lg border border-line bg-surface p-4">
      <div className="flex items-center justify-between">
        <Badge tone="info">[{index + 1}]</Badge>
        <span className="font-mono text-[10px] text-muted">{formatScore(source.score)}</span>
      </div>
      <h3 className="mt-3 text-sm font-medium leading-5 text-ink">{source.title}</h3>
      <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted">{source.snippet}</p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Link
          to={'/documents/' + source.documentId}
          className="rounded text-xs font-medium text-info hover:text-info/80"
        >
          Открыть документ
        </Link>
        <ExternalSourceLink
          href={source.sourceUrl}
          className="flex items-center gap-1 rounded text-xs text-muted hover:text-ink"
        >
          Оригинал
          <ExternalLink className="size-3" aria-hidden="true" />
        </ExternalSourceLink>
        <button
          type="button"
          onClick={saved.toggle}
          disabled={saved.isPending}
          className="ml-auto flex items-center gap-1 rounded text-xs text-muted hover:text-ink disabled:opacity-50"
          aria-label={saved.saved ? 'Удалить источник из сохранённых' : 'Сохранить источник'}
        >
          {saved.saved ? (
            <BookmarkCheck className="size-3.5 text-success" aria-hidden="true" />
          ) : (
            <Bookmark className="size-3.5" aria-hidden="true" />
          )}
          {saved.saved ? 'Сохранён' : 'Сохранить'}
        </button>
      </div>
    </article>
  );
}

const feedbackReasons: Array<[FeedbackReason, string]> = [
  ['irrelevant_sources', 'Источники не отвечают на вопрос'],
  ['factual_error', 'Ответ содержит ошибку'],
  ['incomplete', 'Ответ неполный'],
  ['unclear', 'Ответ трудно понять'],
  ['other', 'Другое'],
];

function NegativeFeedbackDialog({
  open,
  initialReason,
  initialComment,
  loading,
  onClose,
  onSubmit,
}: {
  open: boolean;
  initialReason?: FeedbackReason;
  initialComment?: string;
  loading: boolean;
  onClose: () => void;
  onSubmit: (reason: FeedbackReason | undefined, comment: string) => void;
}) {
  const [reason, setReason] = useState<FeedbackReason | undefined>(initialReason);
  const [comment, setComment] = useState(initialComment ?? '');
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] grid place-items-center bg-canvas/80 p-4 backdrop-blur-sm">
      <button
        type="button"
        className="absolute inset-0"
        onClick={onClose}
        aria-label="Закрыть форму оценки"
      />
      <div
        className="panel relative z-10 w-full max-w-lg p-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby="negative-feedback-title"
      >
        <h2 id="negative-feedback-title" className="text-base font-semibold text-ink">
          Что можно улучшить?
        </h2>
        <p className="mt-2 text-xs leading-5 text-muted">
          Причину и комментарий можно не указывать.
        </p>
        <div className="mt-4 space-y-2">
          {feedbackReasons.map(([value, label]) => (
            <label
              key={value}
              className="flex cursor-pointer items-center gap-2 text-sm text-muted"
            >
              <input
                type="radio"
                name="feedback-reason"
                checked={reason === value}
                onChange={() => setReason(value)}
                className="accent-indigo-500"
              />
              {label}
            </label>
          ))}
        </div>
        <label
          htmlFor="negative-feedback-comment"
          className="mt-4 block text-xs font-medium text-muted"
        >
          Дополнительный комментарий
        </label>
        <textarea
          id="negative-feedback-comment"
          aria-describedby="negative-feedback-counter"
          value={comment}
          onChange={(event) => setComment(event.target.value.slice(0, 500))}
          rows={3}
          maxLength={500}
          className="mt-2 w-full resize-none rounded-lg border border-line bg-elevated p-3 text-sm text-ink"
        />
        <span
          id="negative-feedback-counter"
          className="mt-1 block text-right font-mono text-[10px] text-muted"
        >
          {comment.length}/500
        </span>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button variant="danger" loading={loading} onClick={() => onSubmit(reason, comment)}>
            Сохранить оценку
          </Button>
        </div>
      </div>
    </div>
  );
}
