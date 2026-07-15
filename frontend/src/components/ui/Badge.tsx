import type { HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

type BadgeTone = 'neutral' | 'accent' | 'info' | 'success' | 'warning' | 'danger';

const tones: Record<BadgeTone, string> = {
  neutral: 'border-line bg-elevated text-muted',
  accent: 'border-accent/35 bg-accent/10 text-indigo-300',
  info: 'border-info/35 bg-info/10 text-info',
  success: 'border-success/35 bg-success/10 text-success',
  warning: 'border-warning/35 bg-warning/10 text-warning',
  danger: 'border-danger/35 bg-danger/10 text-danger',
};

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
}

export function Badge({ className, tone = 'neutral', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium leading-5',
        tones[tone],
        className,
      )}
      {...props}
    />
  );
}
