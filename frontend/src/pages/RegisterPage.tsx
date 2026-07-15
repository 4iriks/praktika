import { useMemo, useState, type FormEvent } from 'react';
import { ArrowLeft, Check, Circle, Eye, EyeOff, LockKeyhole, Mail, UserRound } from 'lucide-react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ApiError } from '../api';
import { Button } from '../components/ui/Button';
import { Logo } from '../components/ui/Logo';
import { useAuth } from '../features/auth/useAuth';
import { getSafeReturnTo, loginUrl } from '../utils/returnTo';
import { emailPattern, getPasswordChecks } from '../utils/validation';

interface RegisterErrors {
  displayName?: string;
  email?: string;
  password?: string;
  confirmation?: string;
  terms?: string;
}

export function RegisterPage() {
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [confirmationVisible, setConfirmationVisible] = useState(false);
  const [errors, setErrors] = useState<RegisterErrors>({});
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { user, status, register } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const returnTo = getSafeReturnTo(location.search, location.state, '/profile');
  const checks = useMemo(() => getPasswordChecks(password), [password]);

  if (status !== 'initializing' && user) return <Navigate to={returnTo} replace />;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    const name = displayName.trim();
    const normalizedEmail = email.trim();
    const nextErrors: RegisterErrors = {};
    if (name.length < 2) nextErrors.displayName = 'Имя должно содержать минимум 2 символа';
    if (!normalizedEmail) nextErrors.email = 'Введите email';
    else if (!emailPattern.test(normalizedEmail)) nextErrors.email = 'Укажите корректный email';
    if (!Object.values(checks).every(Boolean))
      nextErrors.password = 'Пароль не соответствует требованиям';
    if (!confirmation) nextErrors.confirmation = 'Подтвердите пароль';
    else if (confirmation !== password) nextErrors.confirmation = 'Пароли не совпадают';
    if (!acceptedTerms) nextErrors.terms = 'Необходимо принять правила использования';
    setErrors(nextErrors);
    setFormError('');
    if (Object.keys(nextErrors).length > 0) return;

    setSubmitting(true);
    try {
      const created = await register({
        displayName: name,
        email: normalizedEmail,
        password,
        acceptedTerms,
        remember: true,
      });
      setPassword('');
      setConfirmation('');
      toast.success('Аккаунт создан', { description: 'Вы вошли как ' + created.displayName });
      navigate(returnTo, { replace: true });
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Не удалось создать аккаунт.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-canvas px-4 py-8">
      <main className="w-full max-w-lg">
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
            <h1 className="mt-6 text-xl font-semibold tracking-tight text-ink">
              Создание аккаунта
            </h1>
            <p className="mt-2 text-sm leading-6 text-muted">
              Локальный профиль для истории, настроек и сохранённых материалов.
            </p>
          </header>
          <form className="space-y-4 px-6 py-6" onSubmit={(event) => void submit(event)} noValidate>
            <Field
              label="Имя"
              icon={<UserRound className="size-4" aria-hidden="true" />}
              error={errors.displayName}
            >
              <input
                autoFocus
                value={displayName}
                onChange={(event) => {
                  setDisplayName(event.target.value);
                  setErrors((current) => ({ ...current, displayName: undefined }));
                }}
                disabled={submitting}
                className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-3 text-sm text-ink disabled:opacity-60"
                autoComplete="name"
                aria-label="Имя"
                aria-invalid={Boolean(errors.displayName)}
              />
            </Field>
            <Field
              label="Email"
              icon={<Mail className="size-4" aria-hidden="true" />}
              error={errors.email}
            >
              <input
                type="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                  setErrors((current) => ({ ...current, email: undefined }));
                }}
                disabled={submitting}
                className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-3 text-sm text-ink disabled:opacity-60"
                autoComplete="email"
                aria-label="Email"
                aria-invalid={Boolean(errors.email)}
              />
            </Field>
            <Field
              label="Пароль"
              icon={<LockKeyhole className="size-4" aria-hidden="true" />}
              error={errors.password}
              action={
                <VisibilityButton
                  visible={passwordVisible}
                  onClick={() => setPasswordVisible((visible) => !visible)}
                  disabled={submitting}
                  label="пароль"
                />
              }
            >
              <input
                type={passwordVisible ? 'text' : 'password'}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setErrors((current) => ({ ...current, password: undefined }));
                }}
                disabled={submitting}
                className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-10 text-sm text-ink disabled:opacity-60"
                autoComplete="new-password"
                aria-label="Пароль"
                aria-invalid={Boolean(errors.password)}
              />
            </Field>

            <div className="grid grid-cols-2 gap-x-3 gap-y-1 rounded-lg border border-line bg-elevated/35 p-3">
              <PasswordRule passed={checks.minLength}>Минимум 8 символов</PasswordRule>
              <PasswordRule passed={checks.lowercase}>Строчная буква</PasswordRule>
              <PasswordRule passed={checks.uppercase}>Заглавная буква</PasswordRule>
              <PasswordRule passed={checks.digit}>Цифра</PasswordRule>
            </div>

            <Field
              label="Подтверждение пароля"
              icon={<LockKeyhole className="size-4" aria-hidden="true" />}
              error={errors.confirmation}
              action={
                <VisibilityButton
                  visible={confirmationVisible}
                  onClick={() => setConfirmationVisible((visible) => !visible)}
                  disabled={submitting}
                  label="подтверждение пароля"
                />
              }
            >
              <input
                type={confirmationVisible ? 'text' : 'password'}
                value={confirmation}
                onChange={(event) => {
                  setConfirmation(event.target.value);
                  setErrors((current) => ({ ...current, confirmation: undefined }));
                }}
                disabled={submitting}
                className="h-10 w-full rounded-lg border border-line bg-elevated pl-9 pr-10 text-sm text-ink disabled:opacity-60"
                autoComplete="new-password"
                aria-label="Подтверждение пароля"
                aria-invalid={Boolean(errors.confirmation)}
              />
            </Field>

            <label className="flex cursor-pointer items-start gap-2 text-xs leading-5 text-muted">
              <input
                type="checkbox"
                checked={acceptedTerms}
                onChange={(event) => {
                  setAcceptedTerms(event.target.checked);
                  setErrors((current) => ({ ...current, terms: undefined }));
                }}
                disabled={submitting}
                className="mt-0.5 size-3.5 rounded border-line bg-canvas accent-indigo-500"
              />
              Я принимаю правила использования локальной базы знаний
            </label>
            {errors.terms ? <p className="text-xs text-danger">{errors.terms}</p> : null}
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
              Создать аккаунт
            </Button>
            <Link
              to={loginUrl(returnTo)}
              className="block rounded-lg py-2 text-center text-sm text-muted transition hover:bg-elevated hover:text-ink"
            >
              Уже есть аккаунт? Войти
            </Link>
          </form>
        </section>
      </main>
    </div>
  );
}

function Field({
  label,
  icon,
  error,
  action,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  error?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-xs font-medium text-muted">
      {label}
      <span className="relative mt-2 block">
        <span className="absolute left-3 top-3 text-muted">{icon}</span>
        {children}
        {action}
      </span>
      {error ? <span className="mt-1.5 block text-xs text-danger">{error}</span> : null}
    </label>
  );
}

function VisibilityButton({
  visible,
  onClick,
  disabled,
  label,
}: {
  visible: boolean;
  onClick: () => void;
  disabled: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="absolute right-2 top-2 grid size-6 place-items-center rounded text-muted hover:text-ink disabled:opacity-50"
      aria-label={visible ? 'Скрыть ' + label : 'Показать ' + label}
    >
      {visible ? (
        <EyeOff className="size-4" aria-hidden="true" />
      ) : (
        <Eye className="size-4" aria-hidden="true" />
      )}
    </button>
  );
}

function PasswordRule({ passed, children }: { passed: boolean; children: React.ReactNode }) {
  return (
    <span
      className={
        passed
          ? 'flex items-center gap-1.5 text-[11px] text-success'
          : 'flex items-center gap-1.5 text-[11px] text-muted'
      }
    >
      {passed ? (
        <Check className="size-3" aria-hidden="true" />
      ) : (
        <Circle className="size-2.5" aria-hidden="true" />
      )}
      {children}
    </span>
  );
}
