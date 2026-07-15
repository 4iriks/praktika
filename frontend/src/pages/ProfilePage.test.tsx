import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockRepository } from '../mocks/mockRepository';
import { renderWithProviders } from '../test/render';
import { ProfilePage } from './ProfilePage';

async function register(email: string, displayName: string) {
  return mockRepository.register({
    displayName,
    email,
    password: 'Strong123',
    acceptedTerms: true,
    remember: true,
  });
}

describe('ProfilePage', () => {
  it('обновляет имя во всём профиле', async () => {
    await register('profile-page@example.local', 'Старое Имя');
    const user = userEvent.setup();
    renderWithProviders(<ProfilePage />, '/profile');

    const nameInput = await screen.findByLabelText('Имя');
    await user.clear(nameInput);
    await user.type(nameInput, 'Новое Имя');
    await user.click(screen.getByRole('button', { name: 'Сохранить профиль' }));

    expect(await screen.findByRole('heading', { name: 'Новое Имя' })).toBeInTheDocument();
    expect((await mockRepository.getCurrentUser())?.displayName).toBe('Новое Имя');
  });

  it('показывает ошибку для занятого email без учёта регистра', async () => {
    await register('email-owner@example.local', 'Первый Пользователь');
    mockRepository.logout();
    await register('current-profile@example.local', 'Второй Пользователь');
    const user = userEvent.setup();
    renderWithProviders(<ProfilePage />, '/profile');

    const emailInput = await screen.findByLabelText('Email');
    await user.clear(emailInput);
    await user.type(emailInput, 'EMAIL-OWNER@EXAMPLE.LOCAL');
    await user.click(screen.getByRole('button', { name: 'Сохранить профиль' }));

    expect(
      await screen.findByText('Пользователь с таким email уже существует.'),
    ).toBeInTheDocument();
  });
});
