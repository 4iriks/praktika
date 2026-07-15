import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Route, Routes, useLocation } from 'react-router-dom';
import { renderWithProviders } from '../test/render';
import { LoginPage } from './LoginPage';

describe('LoginPage', () => {
  it('проверяет обязательные поля', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LoginPage />, '/login');

    await user.click(screen.getByRole('button', { name: 'Войти' }));

    expect(screen.getByText('Введите email')).toBeInTheDocument();
    expect(screen.getByText('Введите пароль')).toBeInTheDocument();
  });

  it('возвращает пользователя на безопасный returnTo', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/saved" element={<LocationProbe />} />
      </Routes>,
      '/login?returnTo=%2Fsaved',
    );
    await user.click(screen.getByText('user@pyanswer.local · Demo123!'));
    await user.click(screen.getByRole('button', { name: 'Войти' }));
    expect(await screen.findByTestId('login-return')).toHaveTextContent('/saved');
  });
});

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="login-return">{location.pathname}</div>;
}
