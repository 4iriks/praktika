import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowRight, Database, Moon, Sun, Zap } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import type { SearchMode, SearchView } from '../types';
import { useAuth } from '../features/auth/useAuth';
import { useSearchShortcut } from '../hooks/useSearchShortcut';
import { useTheme } from '../store/useTheme';
import { formatNumber } from '../utils/format';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { SearchBox } from '../components/ui/SearchBox';
import { UserMenu } from '../components/layout/UserMenu';
import { SearchModeControl } from '../features/search/SearchModeControl';

const examples = [
  'Как удалить дубликаты из списка?',
  'Почему возникает ModuleNotFoundError?',
  'В чём разница между asyncio.gather и create_task?',
  'Как прочитать большой CSV через pandas?',
  'Как работает dependency injection в FastAPI?',
];

const stats = [
  { value: 25_000, label: 'документов' },
  { value: 82_460, label: 'чанков' },
  { value: 1_240, label: 'тегов' },
];

const pipeline = ['BM25', 'HNSW', 'Hybrid', 'Reranker', 'Local LLM'];

export function HomePage() {
  const [query, setQuery] = useState('');
  const [view, setView] = useState<SearchView>('documents');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const inputRef = useRef<HTMLInputElement>(null);
  const viewTouched = useRef(false);
  const modeTouched = useRef(false);
  const navigate = useNavigate();
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  useSearchShortcut(inputRef);

  useEffect(() => {
    if (!user) return;
    if (!viewTouched.current) setView(user.preferences.defaultSearchView);
    if (!modeTouched.current) setMode(user.preferences.defaultSearchMode);
  }, [user]);

  const search = (value = query) => {
    const normalized = value.trim();
    if (!normalized) return;
    const params = new URLSearchParams({
      q: normalized,
      view,
      mode,
      page: '1',
      sort: 'relevance',
    });
    if (user) params.set('page_size', String(user.preferences.defaultPageSize));
    navigate('/search?' + params.toString());
  };

  return (
    <div className="min-h-screen bg-canvas">
      <header className="mx-auto flex h-16 w-full max-w-[1440px] items-center justify-between px-4 sm:px-6">
        <Logo />
        <div className="flex items-center gap-2">
          <span className="hidden items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-muted sm:flex">
            <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
            Локальный индекс готов
          </span>
          <Button
            size="icon"
            variant="ghost"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'}
          >
            {theme === 'dark' ? (
              <Sun className="size-4" aria-hidden="true" />
            ) : (
              <Moon className="size-4" aria-hidden="true" />
            )}
          </Button>
          <UserMenu />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-col px-4 pb-10 pt-[7vh] sm:px-6 sm:pt-[10vh]">
        <section aria-labelledby="home-title">
          <div className="mb-7 text-center">
            <div className="mx-auto mb-4 grid size-12 place-items-center rounded-xl border border-accent/35 bg-accent/15 text-indigo-300 shadow-panel">
              <Database className="size-6" aria-hidden="true" />
            </div>
            <h1
              id="home-title"
              className="text-3xl font-semibold tracking-[-0.04em] text-ink sm:text-4xl"
            >
              Py<span className="text-indigo-400">Answer</span>
            </h1>
            <p className="mt-2 text-sm text-muted sm:text-base">
              Поиск и ответы по русскоязычной базе знаний Python
            </p>
          </div>

          <SearchBox
            ref={inputRef}
            query={query}
            onQueryChange={setQuery}
            view={view}
            onViewChange={(nextView) => {
              viewTouched.current = true;
              setView(nextView);
            }}
            onSubmit={search}
            showShortcut
          />

          <div className="mt-3 flex justify-center">
            <SearchModeControl
              value={mode}
              onChange={(nextMode) => {
                modeTouched.current = true;
                setMode(nextMode);
              }}
            />
          </div>

          <div className="mt-5 flex flex-wrap justify-center gap-x-2 gap-y-2">
            <span className="mr-1 py-1.5 text-[11px] uppercase tracking-wider text-muted">
              Примеры
            </span>
            {examples.map((example) => (
              <button
                key={example}
                type="button"
                onClick={() => {
                  setQuery(example);
                  search(example);
                }}
                className="rounded-lg border border-line/80 bg-surface/65 px-3 py-1.5 text-left text-xs text-muted transition hover:border-accent/45 hover:bg-surface hover:text-ink"
              >
                {example}
              </button>
            ))}
          </div>
        </section>

        <section className="mt-10 grid gap-3 sm:grid-cols-[1fr_auto]">
          <div className="panel flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-5">
            {stats.map((stat) => (
              <div key={stat.label} className="min-w-[90px]">
                <p className="font-mono text-sm font-semibold text-ink">
                  {formatNumber(stat.value)}
                </p>
                <p className="mt-0.5 text-[10px] uppercase tracking-wider text-muted">
                  {stat.label}
                </p>
              </div>
            ))}
            <div className="sm:ml-auto">
              <p className="flex items-center gap-1.5 text-xs text-success">
                <Zap className="size-3.5" aria-hidden="true" />
                локальная модель доступна
              </p>
              <p className="mt-1 text-[10px] text-muted">индекс обновлён 12 минут назад</p>
            </div>
          </div>
          <Link
            to="/search?q=asyncio&view=documents&mode=hybrid&page=1&sort=relevance"
            className="panel flex min-h-16 items-center gap-3 px-5 text-xs text-muted transition hover:border-accent/45 hover:text-ink"
          >
            <Activity className="size-4 text-info" aria-hidden="true" />
            Открыть workspace
            <ArrowRight className="ml-auto size-4" aria-hidden="true" />
          </Link>
        </section>

        <section
          className="mt-3 rounded-xl border border-line/70 bg-surface/55 px-4 py-3"
          aria-label="Поисковый конвейер"
        >
          <div className="flex flex-wrap items-center justify-center gap-2">
            <span className="technical-label mr-2">Конвейер</span>
            {pipeline.map((stage, index) => (
              <div key={stage} className="flex items-center gap-2">
                <span className="rounded-md border border-line bg-elevated px-2 py-1 font-mono text-[10px] text-muted">
                  {stage}
                </span>
                {index < pipeline.length - 1 ? (
                  <ArrowRight className="size-3 text-muted/55" aria-hidden="true" />
                ) : null}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
