import { Braces, Combine, Orbit } from 'lucide-react';
import type { SearchMode } from '../../types';
import { cn } from '../../utils/cn';

interface SearchModeControlProps {
  value: SearchMode;
  onChange: (mode: SearchMode) => void;
}

const modes: Array<{ value: SearchMode; label: string; icon: typeof Braces }> = [
  { value: 'bm25', label: 'BM25', icon: Braces },
  { value: 'vector', label: 'Vector', icon: Orbit },
  { value: 'hybrid', label: 'Hybrid', icon: Combine },
];

export function SearchModeControl({ value, onChange }: SearchModeControlProps) {
  return (
    <div className="inline-grid grid-cols-3 gap-1 rounded-lg border border-line bg-surface p-1">
      {modes.map((mode) => {
        const Icon = mode.icon;
        return (
          <button
            key={mode.value}
            type="button"
            onClick={() => onChange(mode.value)}
            className={cn(
              'flex h-8 items-center justify-center gap-1.5 rounded-md px-2.5 font-mono text-[11px] transition',
              value === mode.value
                ? 'bg-elevated text-ink shadow-sm'
                : 'text-muted hover:bg-elevated/55 hover:text-ink',
            )}
            aria-pressed={value === mode.value}
          >
            <Icon className="size-3.5" aria-hidden="true" />
            {mode.label}
          </button>
        );
      })}
    </div>
  );
}
