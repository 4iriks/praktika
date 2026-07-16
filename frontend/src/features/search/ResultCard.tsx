import { useState } from 'react';
import {
  Bookmark,
  BookmarkCheck,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Code2,
  ExternalLink,
  MessageSquare,
  Star,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import type { SearchResult } from '../../types';
import { formatDate, formatScore } from '../../utils/format';
import { cn } from '../../utils/cn';
import { useSavedDocument } from '../documents/useSavedDocument';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { HighlightText } from './HighlightText';
import { useAuth } from '../auth/useAuth';
import { ExternalSourceLink } from '../../components/ui/ExternalSourceLink';

interface ResultCardProps {
  result: SearchResult;
  position: number;
  query: string;
}

export function ResultCard({ result, position, query }: ResultCardProps) {
  const { user } = useAuth();
  const [detailsOpen, setDetailsOpen] = useState(user?.preferences.autoOpenScores ?? false);
  const saved = useSavedDocument(result.documentId, result.saved);

  return (
    <article className="panel overflow-hidden transition hover:border-muted/55">
      <div className="p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[11px] text-muted">
          <span className="font-mono text-info">#{position}</span>
          <span className="flex items-center gap-1">
            <CalendarDays className="size-3" aria-hidden="true" />
            {formatDate(result.publishedAt)}
          </span>
          <span className="flex items-center gap-1">
            <Star className="size-3" aria-hidden="true" />
            {result.questionScore}
          </span>
          <span className="flex items-center gap-1">
            <MessageSquare className="size-3" aria-hidden="true" />
            {result.answersCount}
          </span>
          {result.acceptedAnswer ? (
            <span className="flex items-center gap-1 text-success">
              <CheckCircle2 className="size-3" aria-hidden="true" />
              принят
            </span>
          ) : null}
          {result.hasCode ? (
            <span className="flex items-center gap-1 text-info">
              <Code2 className="size-3" aria-hidden="true" />
              код
            </span>
          ) : null}
          <span className="ml-auto rounded-md border border-accent/25 bg-accent/10 px-2 py-1 font-mono text-indigo-300">
            score {formatScore(result.finalScore)}
          </span>
        </div>

        <h2 className="mt-3 text-base font-semibold leading-6 tracking-[-0.015em] text-ink sm:text-lg">
          <Link
            to={'/documents/' + result.documentId}
            className="rounded transition hover:text-info"
          >
            <HighlightText text={result.title} query={query} />
          </Link>
        </h2>
        <p className="mt-2 text-sm leading-6 text-muted">
          <HighlightText text={result.snippet} query={query} />
        </p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          {result.tags.map((tag) => (
            <Badge key={tag.slug} tone={tag.slug === 'python' ? 'accent' : 'neutral'}>
              {tag.name}
            </Badge>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line/70 pt-4">
          <Link
            to={'/documents/' + result.documentId}
            className="inline-flex h-9 items-center justify-center rounded-lg border border-line bg-elevated px-3 text-xs font-medium text-ink transition hover:border-accent/50"
          >
            Открыть документ
          </Link>
          <ExternalSourceLink
            href={result.sourceUrl}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs text-muted transition hover:bg-elevated hover:text-ink"
          >
            Источник
            <ExternalLink className="size-3.5" aria-hidden="true" />
          </ExternalSourceLink>
          <Button
            size="sm"
            variant="ghost"
            loading={saved.isPending}
            onClick={saved.toggle}
            className="sm:ml-auto"
            aria-label={saved.saved ? 'Удалить документ из сохранённых' : 'Сохранить документ'}
          >
            {saved.saved ? (
              <BookmarkCheck className="size-4 text-success" aria-hidden="true" />
            ) : (
              <Bookmark className="size-4" aria-hidden="true" />
            )}
            {saved.saved ? 'Сохранён' : 'Сохранить'}
          </Button>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setDetailsOpen((open) => !open)}
        className="flex h-10 w-full items-center gap-2 border-t border-line bg-elevated/30 px-4 text-left text-[11px] font-medium text-muted transition hover:bg-elevated/55 hover:text-ink sm:px-5"
        aria-expanded={detailsOpen}
      >
        Почему этот результат найден
        <ChevronDown
          className={cn('ml-auto size-3.5 transition', detailsOpen && 'rotate-180')}
          aria-hidden="true"
        />
      </button>
      {detailsOpen ? (
        <div className="grid grid-cols-2 gap-3 border-t border-line bg-canvas/35 px-4 py-4 sm:grid-cols-4 sm:px-5">
          <ScoreMetric label="BM25 score" value={result.bm25Score} />
          <ScoreMetric label="Vector score" value={result.vectorScore} />
          <ScoreMetric label="Reranker score" value={result.rerankerScore} />
          <ScoreMetric label="Final score" value={result.finalScore} accent />
        </div>
      ) : null}
    </article>
  );
}

function ScoreMetric({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: number | null;
  accent?: boolean;
}) {
  return (
    <div>
      <p className="text-[10px] text-muted">{label}</p>
      <p className={cn('mt-1 font-mono text-xs text-ink', accent && 'text-info')}>
        {value === null ? '—' : formatScore(value)}
      </p>
    </div>
  );
}
