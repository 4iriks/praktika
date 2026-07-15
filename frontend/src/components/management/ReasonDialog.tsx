import { useEffect, useId, useState } from 'react';
import { useDialogFocus } from '../../hooks/useDialogFocus';
import { Button } from '../ui/Button';

interface ReasonDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  reasonRequired?: boolean;
  loading?: boolean;
  onConfirm: (reason: string) => void;
  onClose: () => void;
}

export function ReasonDialog({
  open,
  title,
  description,
  confirmLabel,
  reasonRequired = false,
  loading = false,
  onConfirm,
  onClose,
}: ReasonDialogProps) {
  const [reason, setReason] = useState('');
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useDialogFocus<HTMLElement>(open, onClose, !loading);

  useEffect(() => {
    if (!open) return;
    setReason('');
  }, [open]);

  if (!open) return null;
  const valid = !reasonRequired || reason.trim().length >= 3;
  return (
    <div className="fixed inset-0 z-[90] grid place-items-center bg-canvas/80 p-4 backdrop-blur-sm">
      <button
        className="absolute inset-0"
        type="button"
        onClick={onClose}
        aria-label="Закрыть диалог"
      />
      <section
        ref={dialogRef}
        className="panel relative z-10 w-full max-w-lg p-5"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <h2 id={titleId} className="text-base font-semibold text-ink">
          {title}
        </h2>
        <p id={descriptionId} className="mt-2 text-sm leading-6 text-muted">
          {description}
        </p>
        <label className="mt-4 block text-xs font-medium text-muted" htmlFor={`${titleId}-reason`}>
          Причина {reasonRequired ? '(обязательно)' : '(необязательно)'}
        </label>
        <textarea
          data-autofocus
          id={`${titleId}-reason`}
          value={reason}
          onChange={(event) => setReason(event.target.value.slice(0, 500))}
          className="mt-2 min-h-24 w-full resize-y rounded-lg border border-line bg-elevated px-3 py-2 text-sm text-ink placeholder:text-muted focus:border-accent"
          placeholder="Кратко опишите причину операции"
        />
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={loading}>
            Отмена
          </Button>
          <Button
            type="button"
            variant="danger"
            loading={loading}
            disabled={!valid}
            onClick={() => onConfirm(reason.trim())}
          >
            {confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  );
}
