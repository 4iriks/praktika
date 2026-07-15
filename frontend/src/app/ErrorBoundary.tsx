import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertOctagon } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  failed: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  override state: ErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { failed: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('PyAnswer UI error', error, info.componentStack);
  }

  override render(): ReactNode {
    if (this.state.failed) {
      return (
        <main className="grid min-h-screen place-items-center bg-canvas p-6">
          <div className="panel w-full max-w-lg p-7 text-center">
            <Logo className="justify-center" />
            <AlertOctagon className="mx-auto mt-8 size-9 text-danger" aria-hidden="true" />
            <h1 className="mt-4 text-xl font-semibold text-ink">Интерфейс столкнулся с ошибкой</h1>
            <p className="mt-2 text-sm leading-6 text-muted">
              Локальные данные не повреждены. Попробуйте повторно открыть рабочее пространство.
            </p>
            <Button
              className="mt-6"
              variant="primary"
              onClick={() => this.setState({ failed: false })}
            >
              Повторить
            </Button>
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}
