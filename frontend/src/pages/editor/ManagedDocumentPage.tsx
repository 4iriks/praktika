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
        </div>
        <aside className="space-y-5">
          <section className="panel p-4">
            <h2 className="text-sm font-semibold">Состояние</h2>
            <dl className="mt-4 grid grid-cols-2 gap-3 text-xs">
              <Meta label="Документ" value={document.status} badge />
              <Meta label="BM25" value={document.bm25Status} badge />
              <Meta label="Vector" value={document.vectorStatus} badge />
              <Meta label="Чанки" value={String(document.chunksCount)} />
              <Meta label="Версия" value={String(document.version)} />
              <Meta label="Content hash" value={document.contentHash} />
            </dl>
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
