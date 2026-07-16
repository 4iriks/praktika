import { useEffect, useId, useState } from 'react';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import type { SourceSyncMode, SourceSyncRequest } from '../../types';
import { Button } from '../ui/Button';

interface SourceSyncDialogProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onConfirm: (request: SourceSyncRequest) => void;
}

export function SourceSyncDialog({ open, loading, onClose, onConfirm }: SourceSyncDialogProps) {
  const [mode, setMode] = useState<SourceSyncMode>('AUTO');
  const [maxDocuments, setMaxDocuments] = useState('100');
  const [maxPages, setMaxPages] = useState('2');
  const [dryRun, setDryRun] = useState(false);
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useDialogFocus<HTMLElement>(open, onClose, !loading);

  useEffect(() => {
    if (!open) return;
    setMode('AUTO');
    setMaxDocuments('100');
    setMaxPages('2');
    setDryRun(false);
  }, [open]);

  if (!open) return null;
  const documents = maxDocuments ? Number(maxDocuments) : undefined;
  const pages = maxPages ? Number(maxPages) : undefined;
  const valid =
    (documents === undefined ||
      (Number.isInteger(documents) && documents >= 1 && documents <= 25_000)) &&
    (pages === undefined || (Number.isInteger(pages) && pages >= 1 && pages <= 250));

  return (
    <div className="fixed inset-0 z-[90] grid place-items-center bg-canvas/80 p-4 backdrop-blur-sm">
      <button
        className="absolute inset-0"
        type="button"
        onClick={onClose}
        aria-label="Закрыть диалог запуска синхронизации"
      />
      <section
        ref={dialogRef}
        className="panel relative z-10 w-full max-w-xl p-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <h2 id={titleId} className="text-base font-semibold text-ink">
          Запустить синхронизацию источника
        </h2>
        <p id={descriptionId} className="mt-2 text-sm leading-6 text-muted">
          Worker выполнит задание отдельно от HTTP-запроса. Полная загрузка расходует время и квоту
          Stack Exchange, поэтому безопасный запуск ограничен 100 документами и двумя страницами.
        </p>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <label className="text-xs text-muted">
            Режим
            <select
              data-autofocus
              value={mode}
              onChange={(event) => setMode(event.target.value as SourceSyncMode)}
              className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 text-sm text-ink"
            >
              <option value="AUTO">AUTO</option>
              <option value="INITIAL">INITIAL</option>
              <option value="INCREMENTAL">INCREMENTAL</option>
            </select>
          </label>
          <label className="text-xs text-muted">
            Максимум документов
            <input
              type="number"
              min={1}
              max={25_000}
              value={maxDocuments}
              onChange={(event) => setMaxDocuments(event.target.value)}
              className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 font-mono text-sm text-ink"
            />
          </label>
          <label className="text-xs text-muted">
            Максимум страниц
            <input
              type="number"
              min={1}
              max={250}
              value={maxPages}
              onChange={(event) => setMaxPages(event.target.value)}
              className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 font-mono text-sm text-ink"
            />
          </label>
          <label className="flex items-center gap-3 rounded-lg border border-line p-3 text-sm">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(event) => setDryRun(event.target.checked)}
            />
            Dry-run без сохранения документов
          </label>
        </div>
        <p className="mt-4 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs text-muted">
          Для полного импорта используется отдельная подтверждаемая команда runbook. Эта форма не
          запускает 25 000 документов без явного удаления обоих ограничений.
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" disabled={loading} onClick={onClose}>
            Отмена
          </Button>
          <Button
            type="button"
            loading={loading}
            disabled={!valid}
            onClick={() =>
              onConfirm({
                mode,
                ...(documents === undefined ? {} : { maxDocuments: documents }),
                ...(pages === undefined ? {} : { maxPages: pages }),
                dryRun,
              })
            }
          >
            Создать задание
          </Button>
        </div>
      </section>
    </div>
  );
}
