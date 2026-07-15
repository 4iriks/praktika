import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Bookmark,
  CheckCircle2,
  Clock3,
  MessageSquareText,
  Save,
  Search,
  UserRound,
} from 'lucide-react';
import { toast } from 'sonner';
import { api, ApiError } from '../api';
import { queryKeys } from '../api/queryKeys';
import { AccountTechnicalPanel } from '../components/layout/AccountTechnicalPanel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { useAuth } from '../features/auth/useAuth';
import { WorkspaceLayout } from '../layouts/WorkspaceLayout';
import type { User, UserPreferences } from '../types';
import { formatDate } from '../utils/format';
import { emailPattern } from '../utils/validation';

export function ProfilePage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [displayName, setDisplayName] = useState(user?.displayName ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [profileError, setProfileError] = useState('');
  const [preferences, setPreferences] = useState<UserPreferences>(
    user?.preferences ?? {
      defaultSearchMode: 'hybrid',
      defaultSearchView: 'documents',
      defaultPageSize: 10,
      autoOpenScores: false,
      confirmExternalNavigation: true,
    },
  );
  const stats = useQuery({
    queryKey: queryKeys.user.stats,
    queryFn: ({ signal }) => api.getUserStats(signal),
  });

  useEffect(() => {
    if (!user) return;
    setDisplayName(user.displayName);
    setEmail(user.email);
    setPreferences(user.preferences);
  }, [user]);

  const updateUserCache = (updated: User) => {
    queryClient.setQueryData(queryKeys.auth.current, updated);
    queryClient.setQueryData(queryKeys.user.profile, updated);
  };

  const profileMutation = useMutation({
    mutationFn: () =>
      api.updateCurrentUser({
        displayName: displayName.trim(),
        email: email.trim(),
      }),
    onSuccess: (updated) => {
      updateUserCache(updated);
      setProfileError('');
      toast.success('Профиль обновлён');
    },
    onError: (error) => {
      setProfileError(error instanceof ApiError ? error.message : 'Не удалось обновить профиль.');
    },
  });

  const preferencesMutation = useMutation({
    mutationFn: () => api.updateCurrentUser({ preferences }),
    onSuccess: (updated) => {
      updateUserCache(updated);
      toast.success('Настройки поиска сохранены');
    },
    onError: () => toast.error('Не удалось сохранить настройки'),
  });

  const submitProfile = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = displayName.trim();
    const normalizedEmail = email.trim();
    if (name.length < 2) {
      setProfileError('Имя должно содержать минимум 2 символа.');
      return;
    }
    if (!emailPattern.test(normalizedEmail)) {
      setProfileError('Укажите корректный email.');
      return;
    }
    profileMutation.mutate();
  };

  if (!user) return null;

  return (
    <WorkspaceLayout technicalPanel={<AccountTechnicalPanel />}>
      <div className="mx-auto w-full max-w-5xl px-4 py-6 sm:px-6 lg:px-8">
        <header className="mb-6">
          <p className="technical-label">Личный контур</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">Профиль</h1>
          <p className="mt-2 text-sm text-muted">
            Учётная запись и параметры новых поисковых запросов.
          </p>
        </header>

        <section className="panel overflow-hidden">
          <div className="flex flex-col gap-5 border-b border-line bg-elevated/25 p-5 sm:flex-row sm:items-center sm:p-6">
            <div className="grid size-16 shrink-0 place-items-center rounded-xl border border-accent/35 bg-accent/15 text-xl font-semibold text-indigo-300">
              {initials(user.displayName)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold text-ink">{user.displayName}</h2>
                <Badge tone="success">
                  <CheckCircle2 className="mr-1 size-3" aria-hidden="true" />
                  Активен
                </Badge>
              </div>
              <p className="mt-1 text-sm text-muted">{user.email}</p>
              <p className="mt-2 font-mono text-[11px] text-muted">USER · Пользователь</p>
            </div>
            <div className="grid gap-1 text-xs text-muted sm:text-right">
              <span>Регистрация: {formatDate(user.createdAt)}</span>
              <span>Активность: {formatDate(user.lastActiveAt)}</span>
            </div>
          </div>
          <div className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-4">
            <Stat icon={Search} label="Поиски" value={stats.data?.documentSearches} />
            <Stat icon={MessageSquareText} label="RAG-запросы" value={stats.data?.ragSearches} />
            <Stat icon={Bookmark} label="Сохранено" value={stats.data?.savedDocuments} />
            <Stat icon={Activity} label="Оценено" value={stats.data?.ratedAnswers} />
          </div>
        </section>

        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          <section className="panel p-5 sm:p-6">
            <div className="flex items-center gap-2">
              <UserRound className="size-4 text-info" aria-hidden="true" />
              <h2 className="text-sm font-semibold text-ink">Основные данные</h2>
            </div>
            <form className="mt-5 space-y-4" onSubmit={submitProfile} noValidate>
              <label className="block text-xs font-medium text-muted">
                Имя
                <input
                  value={displayName}
                  onChange={(event) => {
                    setDisplayName(event.target.value);
                    setProfileError('');
                  }}
                  disabled={profileMutation.isPending}
                  className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 text-sm text-ink disabled:opacity-60"
                />
              </label>
              <label className="block text-xs font-medium text-muted">
                Email
                <input
                  type="email"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setProfileError('');
                  }}
                  disabled={profileMutation.isPending}
                  className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 text-sm text-ink disabled:opacity-60"
                />
              </label>
              {profileError ? (
                <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger" role="alert">
                  {profileError}
                </p>
              ) : null}
              <Button type="submit" variant="primary" loading={profileMutation.isPending}>
                <Save className="size-4" aria-hidden="true" />
                Сохранить профиль
              </Button>
            </form>
          </section>

          <section className="panel p-5 sm:p-6">
            <div className="flex items-center gap-2">
              <Clock3 className="size-4 text-info" aria-hidden="true" />
              <h2 className="text-sm font-semibold text-ink">Настройки поиска</h2>
            </div>
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <PreferenceSelect
                label="Режим по умолчанию"
                value={preferences.defaultSearchMode}
                onChange={(value) =>
                  setPreferences((current) => ({
                    ...current,
                    defaultSearchMode: value as UserPreferences['defaultSearchMode'],
                  }))
                }
                options={[
                  ['bm25', 'BM25'],
                  ['vector', 'Vector'],
                  ['hybrid', 'Hybrid'],
                ]}
              />
              <PreferenceSelect
                label="Представление"
                value={preferences.defaultSearchView}
                onChange={(value) =>
                  setPreferences((current) => ({
                    ...current,
                    defaultSearchView: value as UserPreferences['defaultSearchView'],
                  }))
                }
                options={[
                  ['documents', 'Документы'],
                  ['answer', 'Ответ ИИ'],
                ]}
              />
              <PreferenceSelect
                label="Результатов на странице"
                value={String(preferences.defaultPageSize)}
                onChange={(value) =>
                  setPreferences((current) => ({
                    ...current,
                    defaultPageSize: Number(value) as UserPreferences['defaultPageSize'],
                  }))
                }
                options={[
                  ['10', '10'],
                  ['20', '20'],
                  ['50', '50'],
                ]}
              />
            </div>
            <div className="mt-5 space-y-3 border-t border-line pt-4">
              <PreferenceToggle
                checked={preferences.autoOpenScores}
                onChange={(checked) =>
                  setPreferences((current) => ({ ...current, autoOpenScores: checked }))
                }
              >
                Автоматически открывать технические score
              </PreferenceToggle>
              <PreferenceToggle
                checked={preferences.confirmExternalNavigation}
                onChange={(checked) =>
                  setPreferences((current) => ({
                    ...current,
                    confirmExternalNavigation: checked,
                  }))
                }
              >
                Подтверждать переход на внешний источник
              </PreferenceToggle>
            </div>
            <Button
              className="mt-5"
              variant="primary"
              loading={preferencesMutation.isPending}
              onClick={() => preferencesMutation.mutate()}
            >
              <Save className="size-4" aria-hidden="true" />
              Сохранить настройки
            </Button>
          </section>
        </div>
      </div>
    </WorkspaceLayout>
  );
}

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toLocaleUpperCase('ru-RU') ?? '')
    .join('');
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Search;
  label: string;
  value?: number;
}) {
  return (
    <div className="bg-surface p-4">
      <Icon className="size-4 text-info" aria-hidden="true" />
      <p className="mt-3 font-mono text-xl font-semibold text-ink">{value ?? '—'}</p>
      <p className="mt-1 text-xs text-muted">{label}</p>
    </div>
  );
}

function PreferenceSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<[string, string]>;
}) {
  return (
    <label className="text-xs font-medium text-muted">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 h-10 w-full rounded-lg border border-line bg-elevated px-3 text-sm text-ink"
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function PreferenceToggle({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: string;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-muted">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-3.5 rounded border-line bg-canvas accent-indigo-500"
      />
      {children}
    </label>
  );
}
