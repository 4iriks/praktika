import { forwardRef, type FormEvent } from 'react';
import { ArrowRight, Bot, FileSearch, Search } from 'lucide-react';
import type { SearchView } from '../../types';
import { cn } from '../../utils/cn';
import { Button } from './Button';

interface SearchBoxProps {
  query: string;
  onQueryChange: (value: string) => void;
  view: SearchView;
  onViewChange: (view: SearchView) => void;
  onSubmit: () => void;
  compact?: boolean;
  loading?: boolean;
  showShortcut?: boolean;
}

export const SearchBox = forwardRef<HTMLInputElement, SearchBoxProps>(function SearchBox(
  {
    query,
    onQueryChange,
    view,
    onViewChange,
    onSubmit,
    compact = false,
    loading = false,
    showShortcut = false,
  },
  ref,
) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim()) onSubmit();
  };

  return (
    <form
      onSubmit={submit}
      className={cn(
        'overflow-hidden border border-line bg-surface shadow-panel transition focus-within:border-accent/70 focus-within:shadow-focus',
        compact ? 'rounded-xl' : 'rounded-2xl',
      )}
      role="search"
    >
      <div className={cn('flex items-center gap-3', compact ? 'px-3' : 'px-5')}>
        <Search
          className={cn('shrink-0 text-muted', compact ? 'size-4' : 'size-5')}
          aria-hidden="true"
        />
        <input
          ref={ref}
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          className={cn(
            'min-w-0 flex-1 bg-transparent text-ink placeholder:text-muted/75',
            compact ? 'h-12 text-sm' : 'h-[68px] text-base sm:text-lg',
          )}
          aria-label="Поисковый запрос"
          placeholder="Задайте вопрос о Python…"
          autoComplete="off"
        />
        {showShortcut ? (
          <kbd className="hidden rounded-md border border-line bg-elevated px-2 py-1 font-mono text-[10px] text-muted sm:block">
            ⌘ / Ctrl K
          </kbd>
        ) : null}
        {compact ? (
          <Button
            type="submit"
            size="icon"
            variant="primary"
            disabled={!query.trim()}
            loading={loading}
            aria-label="Запустить поиск"
          >
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
      <div
        className={cn(
          'flex flex-col gap-3 border-t border-line/80 bg-elevated/35 sm:flex-row sm:items-center sm:justify-between',
          compact ? 'px-3 py-2' : 'px-4 py-3',
        )}
      >
        <div className="grid grid-cols-2 gap-1 rounded-lg border border-line bg-canvas/45 p-1">
          <button
            type="button"
            onClick={() => onViewChange('documents')}
            className={cn(
              'flex h-8 items-center justify-center gap-2 rounded-md px-3 text-xs font-medium transition',
              view === 'documents' ? 'bg-elevated text-ink shadow-sm' : 'text-muted hover:text-ink',
            )}
            aria-pressed={view === 'documents'}
          >
            <FileSearch className="size-3.5" aria-hidden="true" />
            Найти документы
          </button>
          <button
            type="button"
            onClick={() => onViewChange('answer')}
            className={cn(
              'flex h-8 items-center justify-center gap-2 rounded-md px-3 text-xs font-medium transition',
              view === 'answer' ? 'bg-elevated text-ink shadow-sm' : 'text-muted hover:text-ink',
            )}
            aria-pressed={view === 'answer'}
          >
            <Bot className="size-3.5" aria-hidden="true" />
            Получить ответ ИИ
          </button>
        </div>
        {!compact ? (
          <Button
            type="submit"
            variant="primary"
            disabled={!query.trim()}
            loading={loading}
            className="w-full sm:w-auto"
          >
            Запустить
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </form>
  );
});
