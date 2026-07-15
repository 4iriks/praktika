import { useState, type ReactNode } from 'react';
import { Activity, Menu, X } from 'lucide-react';
import { cn } from '../utils/cn';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { Sidebar } from '../components/layout/Sidebar';

interface WorkspaceLayoutProps {
  children: ReactNode;
  filters?: ReactNode;
  technicalPanel: ReactNode;
}

export function WorkspaceLayout({ children, filters, technicalPanel }: WorkspaceLayoutProps) {
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  return (
    <div className="h-dvh min-h-[560px] overflow-hidden bg-canvas">
      <div className="flex h-full">
        <Sidebar filters={filters} className="hidden lg:flex" />

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-surface px-3 lg:hidden">
            <Button
              size="icon"
              variant="ghost"
              onClick={() => setLeftOpen(true)}
              aria-label="Открыть навигацию и фильтры"
            >
              <Menu className="size-5" aria-hidden="true" />
            </Button>
            <Logo compact />
            <Button
              size="icon"
              variant="ghost"
              onClick={() => setRightOpen(true)}
              aria-label="Открыть техническую панель"
            >
              <Activity className="size-5" aria-hidden="true" />
            </Button>
          </header>
          <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
        </div>

        <div className="hidden xl:block">{technicalPanel}</div>
      </div>

      <Drawer open={leftOpen} side="left" onClose={() => setLeftOpen(false)}>
        <Sidebar
          filters={filters}
          onNavigate={() => setLeftOpen(false)}
          className="w-full border-r-0"
        />
      </Drawer>
      <Drawer open={rightOpen} side="right" onClose={() => setRightOpen(false)}>
        <div className="h-full pt-12">{technicalPanel}</div>
      </Drawer>
    </div>
  );
}

interface DrawerProps {
  open: boolean;
  side: 'left' | 'right';
  onClose: () => void;
  children: ReactNode;
}

function Drawer({ open, side, onClose, children }: DrawerProps) {
  return (
    <div
      className={cn(
        'fixed inset-0 z-50 xl:hidden',
        open ? 'pointer-events-auto' : 'pointer-events-none',
      )}
      aria-hidden={!open}
    >
      <button
        type="button"
        className={cn(
          'absolute inset-0 bg-canvas/75 backdrop-blur-sm transition-opacity',
          open ? 'opacity-100' : 'opacity-0',
        )}
        onClick={onClose}
        aria-label="Закрыть панель"
        tabIndex={open ? 0 : -1}
      />
      <div
        className={cn(
          'absolute inset-y-0 w-[min(88vw,340px)] bg-surface shadow-panel transition-transform duration-200',
          side === 'left' ? 'left-0' : 'right-0',
          open ? 'translate-x-0' : side === 'left' ? '-translate-x-full' : 'translate-x-full',
        )}
      >
        <Button
          size="icon"
          variant="ghost"
          className="absolute right-2 top-2 z-10"
          onClick={onClose}
          aria-label="Закрыть"
          tabIndex={open ? 0 : -1}
        >
          <X className="size-5" aria-hidden="true" />
        </Button>
        {children}
      </div>
    </div>
  );
}
