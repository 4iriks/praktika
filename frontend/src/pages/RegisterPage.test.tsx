import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { useAuth } from '../features/auth/useAuth';
import { renderWithProviders } from '../test/render';
import { RegisterPage } from './RegisterPage';

function AuthProbe() {
  const { user } = useAuth();
  return <div>{user ? user.email + ' ' + user.role : 'anonymous'}</div>;
}

async function fillRegistration(
  user: ReturnType<typeof userEvent.setup>,
  values: { email?: string; password?: string; confirmation?: string } = {},
) {
  await user.type(screen.getByLabelText('Имя'), 'Новый Пользователь');
  await user.type(screen.getByLabelText('Email'), values.email ?? 'new@example.local');
  await user.type(screen.getByLabelText('Пароль'), values.password ?? 'Strong123');
  await user.type(
    screen.getByLabelText('Подтверждение пароля'),
    values.confirmation ?? values.password ?? 'Strong123',
  );
  await user.click(screen.getByRole('checkbox', { name: /Я принимаю правила/ }));
}

describe('RegisterPage', () => {
  it('проверяет обязательные поля', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />, '/register');
    await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }));
    expect(screen.getByText('Имя должно содержать минимум 2 символа')).toBeInTheDocument();
    expect(screen.getByText('Введите email')).toBeInTheDocument();
    expect(screen.getByText('Подтвердите пароль')).toBeInTheDocument();
    expect(screen.getByText('Необходимо принять правила использования')).toBeInTheDocument();
  });

  it('отклоняет несовпадающие пароли', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />, '/register');
    await fillRegistration(user, { password: 'Strong123', confirmation: 'Different123' });
    await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }));
    expect(screen.getByText('Пароли не совпадают')).toBeInTheDocument();
  });

  it('отклоняет существующий email без учёта регистра', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterPage />, '/register');
    await fillRegistration(user, { email: 'USER@PYANSWER.LOCAL' });
    await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }));
    expect(
      await screen.findByText('Пользователь с таким email уже существует.'),
    ).toBeInTheDocument();
  });

  it('автоматически авторизует нового пользователя с ролью USER', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/profile" element={<AuthProbe />} />
      </Routes>,
      '/register',
    );
    await fillRegistration(user, { email: 'registered@example.local' });
    await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }));
    expect(await screen.findByText('registered@example.local USER')).toBeInTheDocument();
  });
});
