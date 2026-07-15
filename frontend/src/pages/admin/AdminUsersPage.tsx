import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Ban, Search, ShieldCheck, UserRoundCheck, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
import {
  ErrorPanel,
  LoadingPanel,
  EmptyPanel,
  PageHeading,
  StatusBadge,
} from '../../components/management/ManagementUi';
import { ReasonDialog } from '../../components/management/ReasonDialog';
import { Button } from '../../components/ui/Button';
import { roleLabels } from '../../features/auth/permissions';
import type { AdminUser, UserRole } from '../../types';
import { adminUserFilters, setParam } from '../../utils/managementParams';

export function AdminUsersPage() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => adminUserFilters(params), [params]);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [roleTarget, setRoleTarget] = useState<AdminUser | null>(null);
  const [nextRole, setNextRole] = useState<UserRole>('USER');
  const [blockTarget, setBlockTarget] = useState<AdminUser | null>(null);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: queryKeys.admin.users(filters),
    queryFn: ({ signal }) => api.getAdminUsers(filters, signal),
  });
  const detail = useQuery({
    queryKey: queryKeys.admin.user(detailId ?? ''),
    queryFn: ({ signal }) => api.getAdminUser(detailId ?? '', signal),
    enabled: Boolean(detailId),
  });
  const mutation = useMutation({
    mutationFn: ({
      type,
      userId,
      role,
      reason,
    }: {
      type: 'role' | 'block' | 'unblock';
      userId: string;
      role?: UserRole;
      reason?: string;
    }) =>
      type === 'role'
        ? api.updateUserRole(userId, { role: role ?? 'USER' })
        : type === 'block'
          ? api.blockUser(userId, { reason: reason ?? '' })
          : api.unblockUser(userId),
    onSuccess: async (_, variables) => {
      toast.success(
        variables.type === 'role'
          ? 'Роль пользователя изменена'
          : variables.type === 'block'
            ? 'Пользователь заблокирован'
            : 'Пользователь разблокирован',
      );
      setRoleTarget(null);
      setBlockTarget(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.root }),
        queryClient.invalidateQueries({ queryKey: queryKeys.auth.current }),
      ]);
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <>
      <PageHeading
        eyebrow="USER MANAGEMENT"
        title="Пользователи"
        description="Роли и статусы изменяются через server-like API. Self-block, self-demotion и последний активный ADMIN защищены repository-правилами."
      />
      <section className="panel mb-4 grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="relative sm:col-span-2">
          <Search className="absolute left-3 top-2.5 size-4 text-muted" />
          <span className="sr-only">Поиск пользователей</span>
          <input
            value={filters.q}
            onChange={(event) => setParams(setParam(params, 'q', event.target.value))}
            placeholder="Имя или email"
            className="h-9 w-full rounded-md border border-line bg-elevated pl-9 pr-3 text-sm"
          />
        </label>
        <Select
          label="Роль"
          value={filters.role}
          options={['ALL', 'USER', 'EDITOR', 'ADMIN']}
          onChange={(value) => setParams(setParam(params, 'role', value))}
        />
        <Select
          label="Статус"
          value={filters.status}
          options={['ALL', 'ACTIVE', 'BLOCKED']}
          onChange={(value) => setParams(setParam(params, 'status', value))}
        />
        <Select
          label="Сортировка"
          value={filters.sort}
          options={['created_desc', 'created_asc', 'activity_desc', 'name_asc']}
          onChange={(value) => setParams(setParam(params, 'sort', value))}
        />
      </section>
      {query.isPending ? <LoadingPanel /> : null}
      {query.isError ? <ErrorPanel message={query.error.message} /> : null}
      {query.data?.items.length === 0 ? (
        <EmptyPanel title="Пользователи не найдены" description="Попробуйте изменить фильтры." />
      ) : null}
      {query.data?.items.length ? (
        <>
          <div className="panel overflow-x-auto">
            <table className="w-full min-w-[980px] text-left text-xs">
              <thead className="bg-elevated/70 text-muted">
                <tr>
                  {[
                    'Пользователь',
                    'Роль',
                    'Статус',
                    'Регистрация',
                    'Активность',
                    'Запросы',
                    'Saved',
                    'Feedback',
                    'Действия',
                  ].map((label) => (
                    <th key={label} className="border-b border-line px-3 py-2 font-medium">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {query.data.items.map((user) => (
                  <tr key={user.id} className="hover:bg-elevated/30">
                    <td className="px-3 py-3">
                      <button
                        type="button"
                        className="flex items-center gap-2 text-left"
                        onClick={() => setDetailId(user.id)}
                      >
                        <span className="grid size-8 place-items-center rounded-md bg-accent/15 font-mono text-[10px] text-indigo-300">
                          {initials(user.displayName)}
                        </span>
                        <span>
                          <b className="block text-sm text-ink">{user.displayName}</b>
                          <span className="text-muted">{user.email}</span>
                        </span>
                      </button>
                    </td>
                    <td className="px-3 py-3">
                      <span className="font-mono text-info">{user.role}</span>
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge status={user.accountStatus} />
                    </td>
                    <td className="px-3 py-3 text-muted">
                      {new Date(user.createdAt).toLocaleDateString('ru-RU')}
                    </td>
                    <td className="px-3 py-3 text-muted">
                      {new Date(user.lastActiveAt).toLocaleString('ru-RU')}
                    </td>
                    <td className="px-3 py-3 font-mono">
                      {user.stats.documentSearches + user.stats.ragSearches}
                    </td>
                    <td className="px-3 py-3 font-mono">{user.stats.savedDocuments}</td>
                    <td className="px-3 py-3 font-mono">{user.stats.ratedAnswers}</td>
                    <td className="px-3 py-3">
                      <div className="flex gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setRoleTarget(user);
                            setNextRole(user.role);
                          }}
                        >
                          <ShieldCheck className="size-3.5" />
                          Роль
                        </Button>
                        {user.accountStatus === 'ACTIVE' ? (
                          <Button size="sm" variant="danger" onClick={() => setBlockTarget(user)}>
                            <Ban className="size-3.5" />
                            Блокировать
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            onClick={() => mutation.mutate({ type: 'unblock', userId: user.id })}
                          >
                            <UserRoundCheck className="size-3.5" />
                            Разблокировать
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <p className="text-xs text-muted">{query.data.pagination.total} пользователей</p>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={filters.page <= 1}
                onClick={() => setParams(setParam(params, 'page', filters.page - 1, false))}
              >
                Назад
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={filters.page >= query.data.pagination.totalPages}
                onClick={() => setParams(setParam(params, 'page', filters.page + 1, false))}
              >
                Далее
              </Button>
            </div>
          </div>
        </>
      ) : null}
      {detailId ? (
        <div className="fixed inset-0 z-[80] flex justify-end bg-canvas/70">
          <button
            type="button"
            className="absolute inset-0"
            aria-label="Закрыть детали пользователя"
            onClick={() => setDetailId(null)}
          />
          <aside
            className="relative z-10 h-full w-full max-w-lg overflow-y-auto border-l border-line bg-surface p-5"
            aria-label="Детали пользователя"
          >
            <Button
              size="icon"
              variant="ghost"
              className="absolute right-3 top-3"
              onClick={() => setDetailId(null)}
              aria-label="Закрыть"
            >
              <X className="size-5" />
            </Button>
            {detail.isPending ? (
              <LoadingPanel />
            ) : detail.isError ? (
              <ErrorPanel message={detail.error.message} />
            ) : detail.data ? (
              <>
                <div className="flex items-center gap-3">
                  <span className="grid size-12 place-items-center rounded-lg bg-accent/15 font-mono text-indigo-300">
                    {initials(detail.data.displayName)}
                  </span>
                  <div>
                    <h2 className="text-lg font-semibold">{detail.data.displayName}</h2>
                    <p className="text-sm text-muted">{detail.data.email}</p>
                  </div>
                </div>
                <div className="mt-5 flex gap-2">
                  <StatusBadge status={detail.data.accountStatus} />
                  <span className="font-mono text-xs text-info">
                    {roleLabels[detail.data.role]}
                  </span>
                </div>
                <h3 className="mt-6 text-sm font-semibold">Статистика</h3>
                <dl className="mt-3 grid grid-cols-2 gap-3">
                  {Object.entries(detail.data.stats).map(([key, value]) => (
                    <div key={key} className="rounded-lg border border-line p-3">
                      <dt className="font-mono text-[10px] text-muted">{key}</dt>
                      <dd className="mt-1 text-lg font-semibold">{value}</dd>
                    </div>
                  ))}
                </dl>
                <h3 className="mt-6 text-sm font-semibold">Последние запросы</h3>
                <div className="mt-3 space-y-2">
                  {detail.data.recentHistory.map((item) => (
                    <div key={item.id} className="rounded-lg border border-line p-3">
                      <p className="text-xs text-ink">{item.query}</p>
                      <p className="mt-1 font-mono text-[10px] text-muted">
                        {item.mode} · {item.view}
                      </p>
                    </div>
                  ))}
                </div>
                <h3 className="mt-6 text-sm font-semibold">Административные события</h3>
                <div className="mt-3 space-y-2">
                  {detail.data.recentAuditEvents.map((event) => (
                    <div key={event.id} className="border-l border-line pl-3 text-xs">
                      <p>{event.summary}</p>
                      <p className="mt-1 text-[10px] text-muted">
                        {new Date(event.createdAt).toLocaleString('ru-RU')}
                      </p>
                    </div>
                  ))}
                </div>
              </>
            ) : null}
          </aside>
        </div>
      ) : null}
      {roleTarget ? (
        <div className="fixed inset-0 z-[90] grid place-items-center bg-canvas/80 p-4">
          <section
            className="panel w-full max-w-md p-5"
            role="dialog"
            aria-modal="true"
            aria-labelledby="role-title"
          >
            <h2 id="role-title" className="text-base font-semibold">
              Изменить роль
            </h2>
            <p className="mt-2 text-sm text-muted">
              {roleTarget.displayName} · {roleTarget.email}
            </p>
            <select
              aria-label="Новая роль"
              value={nextRole}
              onChange={(event) => setNextRole(event.target.value as UserRole)}
              className="mt-4 h-10 w-full rounded-lg border border-line bg-elevated px-3"
            >
              <option value="USER">USER</option>
              <option value="EDITOR">EDITOR</option>
              <option value="ADMIN">ADMIN</option>
            </select>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setRoleTarget(null)}>
                Отмена
              </Button>
              <Button
                loading={mutation.isPending}
                onClick={() =>
                  mutation.mutate({ type: 'role', userId: roleTarget.id, role: nextRole })
                }
              >
                Подтвердить
              </Button>
            </div>
          </section>
        </div>
      ) : null}
      <ReasonDialog
        open={Boolean(blockTarget)}
        title="Заблокировать пользователя?"
        description="Существующие пользовательские данные сохранятся, а выданная mock-сессия станет недействительной."
        confirmLabel="Заблокировать"
        reasonRequired
        loading={mutation.isPending}
        onClose={() => setBlockTarget(null)}
        onConfirm={(reason) =>
          blockTarget && mutation.mutate({ type: 'block', userId: blockTarget.id, reason })
        }
      />
    </>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-9 rounded-md border border-line bg-elevated px-2 text-xs"
    >
      {options.map((option) => (
        <option key={option}>{option}</option>
      ))}
    </select>
  );
}
function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('');
}
