import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Eye, EyeOff, RotateCcw, Save, Workflow } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  PageHeading,
  ProgressBar,
  StatusBadge,
} from '../../components/management/ManagementUi';
import { ReasonDialog } from '../../components/management/ReasonDialog';
import { Button } from '../../components/ui/Button';
import { ExternalSourceLink } from '../../components/ui/ExternalSourceLink';
import type { BulkDocumentAction, ManagedDocumentUpdate } from '../../types';

export function ManagedDocumentPage() {
  const { documentId = '' } = useParams();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ManagedDocumentUpdate>({
    normalizedTitle: '',
    managedTags: [],
    editorialNote: '',
  });
  const [tagText, setTagText] = useState('');
  const [action, setAction] = useState<BulkDocumentAction | null>(null);
  const query = useQuery({
    queryKey: queryKeys.editor.document(documentId),
    queryFn: ({ signal }) => api.getManagedDocument(documentId, signal),
    enabled: Boolean(documentId),
  });
  const chunks = useQuery({
    queryKey: queryKeys.editor.documentChunks(documentId),
    queryFn: ({ signal }) => api.getManagedDocumentChunks(documentId, signal),
    enabled: Boolean(documentId),
  });
  const revisions = useQuery({
    queryKey: queryKeys.editor.documentRevisions(documentId),
    queryFn: ({ signal }) => api.getManagedDocumentRevisions(documentId, signal),
    enabled: Boolean(documentId),
  });
  const failures = useQuery({
    queryKey: queryKeys.editor.documentFailures(documentId),
    queryFn: ({ signal }) => api.getManagedDocumentFailures(documentId, signal),
    enabled: Boolean(documentId),
  });
  useEffect(() => {
    if (!query.data) return;
    setForm({
      normalizedTitle: query.data.normalizedTitle,
      managedTags: query.data.managedTags,
      editorialNote: query.data.editorialNote,
    });
    setTagText(query.data.managedTags.join(', '));
  }, [query.data]);

  const invalidate = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.editor.root }),
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.root }),
      queryClient.invalidateQueries({ queryKey: queryKeys.search.root }),
      queryClient.invalidateQueries({ queryKey: queryKeys.document.root }),
      queryClient.invalidateQueries({ queryKey: queryKeys.saved.root }),
    ]);
  };
  const saveMutation = useMutation({
    mutationFn: () =>
      api.updateDocumentMetadata(documentId, { ...form, managedTags: tagText.split(',') }),
    onSuccess: async () => {
      toast.success('Метаданные документа сохранены');
      await invalidate();
    },
    onError: (error) => toast.error(error.message),
  });
  const actionMutation = useMutation({
    mutationFn: async ({ value, reason }: { value: BulkDocumentAction; reason: string }) => {
      if (value === 'HIDE') return api.hideDocument(documentId, reason);
      if (value === 'RESTORE') return api.restoreDocument(documentId);
      return api.reindexDocument(documentId);
    },
    onSuccess: async (_, variables) => {
      toast.success(
        variables.value === 'HIDE'
          ? 'Документ скрыт'
          : variables.value === 'RESTORE'
            ? 'Документ восстановлен'
            : 'Задание переиндексации создано',
      );
      setAction(null);
      await invalidate();
    },
    onError: (error) => toast.error(error.message),
  });

  if (query.isPending) return <LoadingPanel />;
  if (query.isError) return <ErrorPanel message={query.error.message} />;
  const document = query.data;
  return (
    <>
      <PageHeading
        eyebrow={`DOCUMENT ${document.documentId}`}
        title={document.normalizedTitle}
        description={`Версия ${document.version}. Исходный текст и идентификатор доступны только для чтения.`}
        actions={
          <>
            <Link
              to={`/documents/${document.documentId}`}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-line px-3 text-sm text-muted hover:text-ink"
            >
              <Eye className="size-4" />
              Пользовательский вид
            </Link>
            <ExternalSourceLink
              href={document.original.sourceUrl}
              className="inline-flex h-10 items-center rounded-lg border border-line px-3 text-sm text-info"
            >
              Открыть источник
            </ExternalSourceLink>
          </>
        }
      />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.8fr)]">
        <div className="space-y-5">
          <section className="panel p-5">
            <h2 className="text-sm font-semibold">Управленческие метаданные</h2>
            <div className="mt-4 space-y-4">
              <label className="block text-xs text-muted">
                Нормализованный заголовок
                <input
                  value={form.normalizedTitle}
                  maxLength={180}
                  onChange={(event) =>
                    setForm((value) => ({ ...value, normalizedTitle: event.target.value }))
                  }
                  className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 text-sm text-ink"
                />
              </label>
              <label className="block text-xs text-muted">
                Управляемые теги
                <input
                  value={tagText}
                  onChange={(event) => setTagText(event.target.value)}
                  className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 font-mono text-sm text-ink"
                  placeholder="python, asyncio"
                />
              </label>
              <label className="block text-xs text-muted">
                Редакторская заметка
                <textarea
                  value={form.editorialNote}
                  maxLength={1000}
                  onChange={(event) =>
                    setForm((value) => ({ ...value, editorialNote: event.target.value }))
                  }
                  className="mt-2 min-h-28 w-full rounded-lg border border-line bg-elevated p-3 text-sm text-ink"
                />
              </label>
              <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                <Save className="size-4" />
                Сохранить
              </Button>
            </div>
          </section>
          <section className="panel p-5">
            <p className="technical-label">Оригинальный вопрос · только чтение</p>
            <h2 className="mt-2 text-lg font-semibold">{document.original.title}</h2>
            <p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-muted">
              {document.original.question.body}
            </p>
            {document.original.question.codeBlocks.map((code, index) => (
              <pre
                key={`${document.documentId}-question-${index}`}
                className="mt-4 overflow-x-auto rounded-lg border border-line bg-canvas p-4 font-mono text-xs text-info"
              >
                <code>{code}</code>
              </pre>
            ))}
          </section>
          <section className="space-y-3" aria-labelledby="answers-title">
            <h2 id="answers-title" className="text-sm font-semibold">
              Ответы ({document.original.answers.length})
            </h2>
            {document.original.answers.map((answer) => (
              <article key={answer.id} className="panel p-5">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted">{answer.author}</span>
                  <span className="font-mono text-xs text-ink">+{answer.score}</span>
                  {answer.accepted ? <StatusBadge status="ACTIVE" /> : null}
                </div>
                <p className="mt-3 text-sm leading-7 text-muted">{answer.body}</p>
                {answer.codeBlocks.map((code, index) => (
                  <pre
                    key={`${answer.id}-${index}`}
                    className="mt-4 overflow-x-auto rounded-lg border border-line bg-canvas p-4 font-mono text-xs text-info"
                  >
                    <code>{code}</code>
                  </pre>
                ))}
              </article>
            ))}
          </section>
          <section className="panel p-5" aria-labelledby="selected-answers-title">
            <h2 id="selected-answers-title" className="text-sm font-semibold">
              Ответы, выбранные для корпуса ({document.selectedAnswers.length})
            </h2>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              {document.selectedAnswers.map((answer) => (
                <div key={answer.id} className="rounded-lg border border-line p-3 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-info">#{answer.selectionRank ?? '—'}</span>
                    <span className="text-ink">{answer.authorName}</span>
                    {answer.isAccepted ? <StatusBadge status="ACCEPTED" /> : null}
                  </div>
                  <p className="mt-2 text-muted">
                    Stack Exchange ID: {answer.externalId} · score {answer.score}
                  </p>
                </div>
              ))}
              {document.selectedAnswers.length === 0 ? (
                <p className="text-xs text-muted">Ответы для canonical document не выбраны.</p>
              ) : null}
            </div>
          </section>
          <section className="panel p-5" aria-labelledby="chunks-title">
            <div className="flex items-center justify-between gap-3">
              <h2 id="chunks-title" className="text-sm font-semibold">
                Чанки · только чтение
              </h2>
              <span className="font-mono text-xs text-muted">
                {chunks.data?.pagination.total ?? document.chunksCount}
              </span>
            </div>
            {chunks.isPending ? <p className="mt-3 text-xs text-muted">Загружаем чанки…</p> : null}
            {chunks.isError ? (
              <p className="mt-3 text-xs text-danger">{chunks.error.message}</p>
            ) : null}
            <div className="mt-3 space-y-3">
              {chunks.data?.items.map((chunk) => (
                <article key={chunk.id} className="rounded-lg border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2 text-[10px]">
                    <StatusBadge status={chunk.sectionType} />
                    <span className="font-mono text-info">#{chunk.ordinal}</span>
                    <span className="text-muted">{chunk.tokenCount} токенов</span>
                    <span className="text-muted">v{chunk.documentVersion}</span>
                    {chunk.hasCode ? <span className="font-mono text-info">CODE</span> : null}
                  </div>
                  <pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap font-sans text-xs leading-6 text-muted">
                    {chunk.text}
                  </pre>
                </article>
              ))}
              {chunks.data?.items.length === 0 ? (
                <p className="text-xs text-muted">У документа пока нет чанков.</p>
              ) : null}
            </div>
          </section>
          <section className="panel p-5" aria-labelledby="revisions-title">
            <h2 id="revisions-title" className="text-sm font-semibold">
              Ревизии · только чтение
            </h2>
            {revisions.isPending ? (
              <p className="mt-3 text-xs text-muted">Загружаем ревизии…</p>
            ) : null}
            {revisions.isError ? (
              <p className="mt-3 text-xs text-danger">{revisions.error.message}</p>
            ) : null}
            <div className="mt-3 space-y-3">
              {revisions.data?.items.map((revision) => (
                <article key={revision.id} className="rounded-lg border border-line p-3 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={`VERSION ${revision.version}`} />
                    <span className="font-mono text-info">{revision.changeReason}</span>
                    <time className="ml-auto text-muted">
                      {new Date(revision.createdAt).toLocaleString('ru-RU')}
                    </time>
                  </div>
                  <p className="mt-2 break-all font-mono text-[10px] text-muted">
                    content {revision.contentHash} · metadata {revision.metadataHash}
                  </p>
                </article>
              ))}
              {revisions.data?.items.length === 0 ? (
                <p className="text-xs text-muted">Ревизий пока нет.</p>
              ) : null}
            </div>
          </section>
        </div>
        <aside className="space-y-5">
          <section className="panel p-4">
            <h2 className="text-sm font-semibold">Состояние</h2>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
              <Meta label="Документ" value={document.status} badge />
              <Meta label="BM25" value={document.bm25Status} badge />
              <Meta label="Vector" value={document.vectorStatus} badge />
              <Meta label="Processing" value={document.processingStatus} badge />
              <Meta label="Дедупликация" value={document.deduplicationStatus} badge />
              <Meta label="Чанки" value={String(document.chunksCount)} />
              <Meta label="Выбрано ответов" value={String(document.selectedAnswersCount)} />
              <Meta label="Версия" value={String(document.version)} />
              <Meta label="Content hash" value={document.contentHash} />
              <Meta label="Metadata hash" value={document.metadataHash ?? '—'} />
              <Meta label="Последний source update" value={formatDate(document.sourceUpdatedAt)} />
              <Meta label="Последний seen" value={formatDate(document.lastSeenAt)} />
            </dl>
            {document.duplicateOfDocumentId ? (
              <Link
                className="mt-4 inline-block text-xs text-info hover:underline"
                to={`/editor/documents/${document.duplicateOfDocumentId}`}
              >
                Открыть оригинал exact duplicate
              </Link>
            ) : null}
            {document.processingError ? (
              <p className="mt-4 rounded-lg border border-danger/30 bg-danger/5 p-3 text-xs text-danger">
                {document.processingError}
              </p>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-2">
              {['ACTIVE', 'OUTDATED'].includes(document.status) ? (
                <Button size="sm" variant="danger" onClick={() => setAction('HIDE')}>
                  <EyeOff className="size-4" />
                  Скрыть
                </Button>
              ) : null}
              {document.status === 'HIDDEN' ? (
                <Button size="sm" onClick={() => setAction('RESTORE')}>
                  <RotateCcw className="size-4" />
                  Восстановить
                </Button>
              ) : null}
              <Button size="sm" onClick={() => setAction('REINDEX')}>
                <Workflow className="size-4" />
                Переиндексировать
              </Button>
            </div>
          </section>
          <section className="panel p-4">
            <h2 className="text-sm font-semibold">Ошибки ingestion</h2>
            {failures.isPending ? (
              <p className="mt-3 text-xs text-muted">Проверяем ошибки…</p>
            ) : null}
            {failures.isError ? (
              <p className="mt-3 text-xs text-danger">{failures.error.message}</p>
            ) : null}
            <div className="mt-3 space-y-3">
              {failures.data?.items.map((failure) => (
                <div key={failure.id} className="rounded-lg border border-line p-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={failure.retryable ? 'RETRYABLE' : 'TERMINAL'} />
                    <span className="font-mono text-[10px] text-danger">{failure.errorCode}</span>
                  </div>
                  <p className="mt-2 text-xs text-muted">{failure.safeMessage}</p>
                </div>
              ))}
              {failures.data?.items.length === 0 ? (
                <p className="text-xs text-muted">Ошибок ingestion нет.</p>
              ) : null}
            </div>
          </section>
          <section className="panel p-4">
            <h2 className="text-sm font-semibold">Связанные задания</h2>
            <div className="mt-3 space-y-3">
              {document.relatedJobs.length ? (
                document.relatedJobs.map((job) => (
                  <div key={job.id} className="rounded-lg border border-line p-3">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-info">{job.type}</span>
                      <StatusBadge status={job.status} />
                      <span className="ml-auto text-[10px] text-muted">{job.progress}%</span>
                    </div>
                    <div className="mt-2">
                      <ProgressBar value={job.progress} />
                    </div>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted">Связанных заданий пока нет.</p>
              )}
            </div>
          </section>
          <section className="panel p-4">
            <h2 className="text-sm font-semibold">История изменений</h2>
            <div className="mt-3 space-y-3">
              {document.auditEvents.length ? (
                document.auditEvents.map((event) => (
                  <div key={event.id} className="border-l border-line pl-3">
                    <p className="text-xs text-ink">{event.summary}</p>
                    <p className="mt-1 font-mono text-[10px] text-muted">
                      {new Date(event.createdAt).toLocaleString('ru-RU')} · {event.actorName}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted">Административных изменений пока нет.</p>
              )}
            </div>
          </section>
        </aside>
      </div>
      <ReasonDialog
        open={Boolean(action)}
        title={
          action === 'HIDE'
            ? 'Скрыть документ?'
            : action === 'RESTORE'
              ? 'Восстановить документ?'
              : 'Переиндексировать документ?'
        }
        description="Операция изменит управленческое состояние, обновит связанные cache и создаст событие аудита."
        confirmLabel="Подтвердить"
        reasonRequired={action === 'HIDE'}
        loading={actionMutation.isPending}
        onClose={() => !actionMutation.isPending && setAction(null)}
        onConfirm={(reason) => action && actionMutation.mutate({ value: action, reason })}
      />
    </>
  );
}

function Meta({ label, value, badge = false }: { label: string; value: string; badge?: boolean }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-1 break-all font-mono text-ink">
        {badge ? <StatusBadge status={value} /> : value}
      </dd>
    </div>
  );
}

function formatDate(value?: string): string {
  return value ? new Date(value).toLocaleString('ru-RU') : '—';
}
