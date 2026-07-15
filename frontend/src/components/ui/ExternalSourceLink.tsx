import { useState, type ReactNode } from 'react';
import { useAuth } from '../../features/auth/useAuth';
import { ConfirmDialog } from './ConfirmDialog';

interface ExternalSourceLinkProps {
  href: string;
  children: ReactNode;
  className: string;
}

export function ExternalSourceLink({ href, children, className }: ExternalSourceLinkProps) {
  const [confirming, setConfirming] = useState(false);
  const { user } = useAuth();
  const requiresConfirmation = user?.preferences.confirmExternalNavigation ?? false;

  if (!requiresConfirmation) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={className}>
        {children}
      </a>
    );
  }

  return (
    <>
      <button type="button" className={className} onClick={() => setConfirming(true)}>
        {children}
      </button>
      <ConfirmDialog
        open={confirming}
        title="Открыть внешний источник?"
        description="Ссылка ведёт на исходную публикацию за пределами локального интерфейса PyAnswer."
        confirmLabel="Открыть"
        onConfirm={() => window.open(href, '_blank', 'noopener,noreferrer')}
        onClose={() => setConfirming(false)}
      />
    </>
  );
}
