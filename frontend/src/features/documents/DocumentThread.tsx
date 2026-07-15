import {
  Bookmark,
  BookmarkCheck,
  Bot,
  CalendarDays,
  CheckCircle2,
  Eye,
  ExternalLink,
  Hash,
  MessageSquare,
  Star,
  UserRound,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { Answer, Document } from '../../types';
import { formatDate, formatNumber } from '../../utils/format';
import { cn } from '../../utils/cn';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { MarkdownContent } from '../../components/ui/MarkdownContent';
import { ExternalSourceLink } from '../../components/ui/ExternalSourceLink';
import { useSavedDocument } from './useSavedDocument';

function contentMarkdown(body: string, codeBlocks: string[]): string {
  const fence = String.fromCharCode(96).repeat(3);
  return [body, ...codeBlocks.map((code) => fence + 'python\n' + code + '\n' + fence)].join('\n\n');
}

export function DocumentThread({ document }: { document: Document }) {
  const saved = useSavedDocument(document.id, document.saved);
  const navigate = useNavigate();
  const accepted = document.answers.find((answer) => answer.accepted);
  const additional = document.answers.filter((answer) => !answer.accepted);

  const askAboutDocument = () => {
    const params = new URLSearchParams({
      q: document.title,
      view: 'answer',
      mode: 'hybrid',
      page: '1',
      sort: 'relevance',
    });
    navigate('/search?' + params.toString());
  };

  return (
    <div>
      <section className="panel overflow-hidden">
        <div className="border-b border-line bg-elevated/25 px-4 py-5 sm:px-6">
          <div className="flex flex-wrap items-center gap-2">
            {document.tags.map((tag) => (
              <Badge key={tag.slug} tone={tag.slug === 'python' ? 'accent' : 'neutral'}>
                {tag.name}
              </Badge>
            ))}
          </div>
          <h1 className="mt-4 max-w-4xl text-xl font-semibold leading-8 tracking-[-0.025em] text-ink sm:text-2xl">
            {document.title}
          </h1>
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
            <span className="flex items-center gap-1.5">
              <UserRound className="size-3.5" aria-hidden="true" />
              {document.author}
            </span>
            <span className="flex items-center gap-1.5">
              <CalendarDays className="size-3.5" aria-hidden="true" />
              {formatDate(document.publishedAt)}
            </span>
            <span className="flex items-center gap-1.5">
              <Eye className="size-3.5" aria-hidden="true" />
              {formatNumber(document.views)}
            </span>
            <span className="flex items-center gap-1.5">
              <Star className="size-3.5" aria-hidden="true" />
              {document.score}
            </span>
            <span className="flex items-center gap-1.5">
              <MessageSquare className="size-3.5" aria-hidden="true" />
              {document.answers.length}
            </span>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={saved.toggle}
              loading={saved.isPending}
              aria-label={saved.saved ? 'Удалить документ из сохранённых' : 'Сохранить документ'}
            >
              {saved.saved ? (
                <BookmarkCheck className="size-3.5 text-success" aria-hidden="true" />
              ) : (
                <Bookmark className="size-3.5" aria-hidden="true" />
              )}
              {saved.saved ? 'Сохранён' : 'Сохранить'}
            </Button>
            <Button size="sm" variant="primary" onClick={askAboutDocument}>
              <Bot className="size-3.5" aria-hidden="true" />
              Спросить ИИ по документу
            </Button>
            <ExternalSourceLink
              href={document.sourceUrl}
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs text-muted transition hover:bg-elevated hover:text-ink"
            >
              Исходная публикация
              <ExternalLink className="size-3.5" aria-hidden="true" />
            </ExternalSourceLink>
          </div>
        </div>

        <article className="px-4 py-6 sm:px-6 sm:py-7">
          <p className="technical-label">Вопрос</p>
          <MarkdownContent className="mt-4">
            {contentMarkdown(document.question.body, document.question.codeBlocks)}
          </MarkdownContent>
        </article>
      </section>

      <section className="mt-4" aria-labelledby="answers-title">
        <div className="mb-3 flex items-center justify-between">
          <h2 id="answers-title" className="text-sm font-semibold text-ink">
            Ответы · {document.answers.length}
          </h2>
          {accepted ? (
            <Badge tone="success">есть принятый ответ</Badge>
          ) : (
            <Badge>без принятого ответа</Badge>
          )}
        </div>
        <div className="space-y-3">
          {accepted ? <AnswerCard answer={accepted} /> : null}
          {additional.map((answer) => (
            <AnswerCard key={answer.id} answer={answer} />
          ))}
        </div>
      </section>

      <details className="panel mt-4 overflow-hidden">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-4 text-sm font-medium text-ink sm:px-6">
          <Hash className="size-4 text-muted" aria-hidden="true" />
          Технические сведения об индексации
          <span className="ml-auto font-mono text-[10px] text-muted">{document.id}</span>
        </summary>
        <div className="grid gap-px border-t border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          <TechnicalValue label="ID документа" value={document.id} />
          <TechnicalValue label="Количество чанков" value={String(document.chunkCount)} />
          <TechnicalValue label="Дата индексации" value={formatDate(document.indexedAt)} />
          <TechnicalValue label="BM25 status" value={document.bm25Status} success />
          <TechnicalValue label="Vector status" value={document.vectorStatus} success />
          <TechnicalValue label="Content hash" value={document.contentHash} />
        </div>
      </details>
    </div>
  );
}

function AnswerCard({ answer }: { answer: Answer }) {
  return (
    <article
      className={cn(
        'panel overflow-hidden',
        answer.accepted && 'border-success/40 shadow-[inset_3px_0_0_rgb(var(--success))]',
      )}
    >
      <header className="flex flex-wrap items-center gap-3 border-b border-line bg-elevated/25 px-4 py-3 sm:px-6">
        {answer.accepted ? (
          <span className="flex items-center gap-1.5 text-xs font-medium text-success">
            <CheckCircle2 className="size-4" aria-hidden="true" />
            Принятый ответ
          </span>
        ) : (
          <span className="text-xs font-medium text-ink">Дополнительный ответ</span>
        )}
        <span className="ml-auto flex items-center gap-1.5 text-xs text-muted">
          <UserRound className="size-3.5" aria-hidden="true" />
          {answer.author}
        </span>
        <Badge tone={answer.score >= 20 ? 'success' : 'neutral'}>
          <Star className="mr-1 size-3" aria-hidden="true" />
          {answer.score}
        </Badge>
      </header>
      <div className="px-4 py-5 sm:px-6">
        <MarkdownContent>{contentMarkdown(answer.body, answer.codeBlocks)}</MarkdownContent>
      </div>
    </article>
  );
}

function TechnicalValue({
  label,
  value,
  success = false,
}: {
  label: string;
  value: string;
  success?: boolean;
}) {
  return (
    <div className="bg-surface p-4">
      <p className="technical-label">{label}</p>
      <p className={cn('mt-2 break-all font-mono text-xs text-ink', success && 'text-success')}>
        {value}
      </p>
    </div>
  );
}
