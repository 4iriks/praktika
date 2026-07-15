import { SearchCode, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '../../utils/cn';

interface LogoProps {
  compact?: boolean;
  className?: string;
}

export function Logo({ compact = false, className }: LogoProps) {
  return (
    <Link
      to="/"
      className={cn('inline-flex items-center gap-2.5 rounded-lg text-ink', className)}
      aria-label="PyAnswer — на главную"
    >
      <span className="relative grid size-9 shrink-0 place-items-center rounded-lg border border-accent/35 bg-accent/15 text-indigo-300">
        <SearchCode className="size-5" aria-hidden="true" />
        <Sparkles
          className="absolute -right-1 -top-1 size-3.5 rounded-full bg-surface text-info"
          aria-hidden="true"
        />
      </span>
      {!compact ? (
        <span className="text-[17px] font-semibold tracking-[-0.03em]">
          Py<span className="text-indigo-400">Answer</span>
        </span>
      ) : null}
    </Link>
  );
}
