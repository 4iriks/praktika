import { AlertCircle, Inbox, RotateCcw, SearchX } from 'lucide-react';
import { Button } from './Button';

export function ResultsSkeleton() {
  return (
    <div className="space-y-3" aria-label="Загрузка результатов">
      {Array.from({ length: 4 }, (_, index) => (
        <div className="panel p-5" key={index}>
          <div className="skeleton h-4 w-20 rounded" />
          <div className="skeleton mt-4 h-6 w-4/5 rounded" />
          <div className="skeleton mt-4 h-3 w-full rounded" />
          <div className="skeleton mt-2 h-3 w-2/3 rounded" />
          <div className="mt-5 flex gap-2">
            <div className="skeleton h-6 w-16 rounded-md" />
            <div className="skeleton h-6 w-20 rounded-md" />
          </div>
        </div>
      ))}
    </div>
  );
}

interface StateProps {
  onRetry?: () => void;
}

export function ErrorState({ onRetry }: StateProps) {
  return (
    <div className="panel grid min-h-72 place-items-center p-8 text-center" role="alert">
      <div>
        <span className="mx-auto grid size-11 place-items-center rounded-xl border border-danger/30 bg-danger/10 text-danger">
          <AlertCircle className="size-5" aria-hidden="true" />
        </span>
        <h2 className="mt-4 font-semibold text-ink">Не удалось выполнить запрос</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">
          Проверьте состояние локальных сервисов или повторите попытку.
        </p>
        {onRetry ? (
          <Button className="mt-5" onClick={onRetry}>
            <RotateCcw className="size-4" aria-hidden="true" />
            Повторить
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function NoResultsState() {
  return (
    <div className="panel grid min-h-72 place-items-center p-8 text-center">
      <div>
        <SearchX className="mx-auto size-8 text-muted" aria-hidden="true" />
        <h2 className="mt-4 font-semibold text-ink">Ничего не найдено</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-muted">
          Уточните формулировку, уберите часть фильтров или попробуйте другой режим поиска.
        </p>
      </div>
    </div>
  );
}

export function EmptyQueryState() {
  return (
    <div className="panel grid min-h-72 place-items-center p-8 text-center">
      <div>
        <Inbox className="mx-auto size-8 text-muted" aria-hidden="true" />
        <h2 className="mt-4 font-semibold text-ink">Введите вопрос о Python</h2>
        <p className="mt-2 text-sm text-muted">Результаты и технические метрики появятся здесь.</p>
      </div>
    </div>
  );
}
