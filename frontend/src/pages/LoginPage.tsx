import { useState, type FormEvent } from 'react';
import { ArrowLeft, Eye, EyeOff, KeyRound, LockKeyhole, Mail, UserPlus } from 'lucide-react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ApiError, useMocks } from '../api';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { useAuth } from '../features/auth/useAuth';
import { getSafeReturnTo, registerUrl } from '../utils/returnTo';
import { emailPattern } from '../utils/validation';

interface FormErrors {
  email?: string;
  password?: string;
}

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { user, status, login } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const returnTo = getSafeReturnTo(location.search, location.state, '/profile');

  if (status !== 'initializing' && user) return <Navigate to={returnTo} replace />;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    const normalizedEmail = email.trim();
    const nextErrors: FormErrors = {};
    if (!normalizedEmail) nextErrors.email = 'Введите email';
    else if (!emailPattern.test(normalizedEmail)) nextErrors.email = 'Укажите корректный email';
    if (!password) nextErrors.password = 'Введите пароль';
    setErrors(nextErrors);
    setFormError('');
    if (Object.keys(nextErrors).length > 0) return;

    setSubmitting(true);
    try {
      await login({ email: normalizedEmail, password, remember });
      setPassword('');
      toast.success('Вход выполнен');
      navigate(returnTo, { replace: true });
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Не удалось выполнить вход.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-canvas px-4 py-8">
      <main className="w-full max-w-md">
        <Link
          to="/"
          className="mb-5 inline-flex items-center gap-2 rounded-lg text-xs text-muted transition hover:text-ink"
        >
          <ArrowLeft className="size-3.5" aria-hidden="true" />
          На главную
        </Link>
        <section className="panel overflow-hidden">
          <header className="border-b border-line bg-elevated/25 px-6 py-5">
            <Logo />
            <h1 className="mt-6 text-xl font-semibold tracking-tight text-ink">Вход в PyAnswer</h1>
            <p className="mt-2 text-sm leading-6 text-muted">
              История, сохранённые документы и настройки привязаны к пользователю.
            </p>
          </header>
          <form className="space-y-4 px-6 py-6" onSubmit={(event) => void submit(event)} noValidate>
            <label className="block text-xs font-medium text-muted">
              Email
              <span className="relative mt-2 block">
                <Mail className="absolute left-3 top-3 size-4 text-muted" aria-hidden="true" />
                <input
                  type="email"
                  value={email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setErrors((current) => ({ ...current, email: undefined }));
                  }}
                  disabled={submitting}
                  className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-3 text-sm text-ink placeholder:text-muted/60 disabled:opacity-60"
                  placeholder="user@pyanswer.local"
                  autoComplete="email"
                  aria-invalid={Boolean(errors.email)}
                  aria-describedby={errors.email ? 'email-error' : undefined}
                />
              </span>
              {errors.email ? (
                <span id="email-error" className="mt-1.5 block text-xs text-danger">
                  {errors.email}
                </span>
              ) : null}
            </label>

            <label className="block text-xs font-medium text-muted">
              Пароль
              <span className="relative mt-2 block">
                <LockKeyhole
                  className="absolute left-3 top-3 size-4 text-muted"
                  aria-hidden="true"
                />
                <input
                  type={passwordVisible ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setErrors((current) => ({ ...current, password: undefined }));
                  }}
                  disabled={submitting}
                  className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-10 text-sm text-ink placeholder:text-muted/60 disabled:opacity-60"
                  placeholder="Введите пароль"
                  autoComplete="current-password"
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? 'password-error' : undefined}
                />
                <button
                  type="button"
                  onClick={() => setPasswordVisible((visible) => !visible)}
                  disabled={submitting}
                  className="absolute right-2 top-2 grid size-6 place-items-center rounded text-muted transition hover:text-ink disabled:opacity-50"
                  aria-label={passwordVisible ? 'Скрыть пароль' : 'Показать пароль'}
                >
                  {passwordVisible ? (
                    <EyeOff className="size-4" aria-hidden="true" />
                  ) : (
                    <Eye className="size-4" aria-hidden="true" />
                  )}
                </button>
              </span>
              {errors.password ? (
                <span id="password-error" className="mt-1.5 block text-xs text-danger">
                  {errors.password}
                </span>
              ) : null}
            </label>

            <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                disabled={submitting}
                className="size-3.5 rounded border-line bg-canvas accent-indigo-500"
              />
              Запомнить меня
            </label>

            {formError ? (
              <p
                className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2.5 text-xs text-danger"
                role="alert"
              >
                {formError}
              </p>
            ) : null}

            <Button
              type="submit"
              variant="primary"
              className="w-full"
              loading={submitting}
              disabled={submitting}
            >
              <KeyRound className="size-4" aria-hidden="true" />
              Войти
            </Button>
            <Link
              to={registerUrl(returnTo)}
              className="flex h-10 items-center justify-center gap-2 rounded-lg text-sm text-muted transition hover:bg-elevated hover:text-ink"
            >
              <UserPlus className="size-4" aria-hidden="true" />
              Создать аккаунт
            </Link>
          </form>
          {useMocks ? (
            <div className="border-t border-line bg-elevated/20 px-6 py-4">
              <p className="technical-label">Mock-аккаунты ролей</p>
              <div className="mt-2 space-y-2">
                {[
                  ['USER', 'user@pyanswer.local'],
                  ['EDITOR', 'editor@pyanswer.local'],
                  ['ADMIN', 'admin@pyanswer.local'],
                ].map(([role, accountEmail]) => (
                  <button
                    key={accountEmail}
                    type="button"
                    disabled={submitting}
                    onClick={() => {
                      setEmail(accountEmail ?? '');
                      setPassword('Demo123!');
                      setErrors({});
                    }}
                    className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 text-left font-mono text-xs text-muted transition hover:border-accent/45 hover:text-ink disabled:opacity-50"
                  >
                    <span className="mr-2 text-info">{role}</span>
                    {accountEmail} · Demo123!
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      </main>
    </div>
  );
}
