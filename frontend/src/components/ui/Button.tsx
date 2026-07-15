import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { LoaderCircle } from 'lucide-react';
import { cn } from '../../utils/cn';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg' | 'icon';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'border-accent bg-accent text-white shadow-sm hover:border-indigo-400 hover:bg-indigo-500 disabled:border-accent/40 disabled:bg-accent/40',
  secondary:
    'border-line bg-elevated text-ink hover:border-muted/70 hover:bg-line/60 disabled:text-muted',
  ghost:
    'border-transparent bg-transparent text-muted hover:bg-elevated hover:text-ink disabled:text-muted/50',
  danger:
    'border-danger/40 bg-danger/10 text-danger hover:border-danger/70 hover:bg-danger/15 disabled:opacity-50',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 gap-1.5 rounded-md px-2.5 text-xs',
  md: 'h-10 gap-2 rounded-lg px-3.5 text-sm',
  lg: 'h-12 gap-2 rounded-lg px-5 text-sm',
  icon: 'size-9 rounded-lg',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, children, variant = 'secondary', size = 'md', loading = false, disabled, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn(
        'inline-flex shrink-0 items-center justify-center border font-medium transition duration-150 disabled:cursor-not-allowed',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> : null}
      {children}
    </button>
  );
});
