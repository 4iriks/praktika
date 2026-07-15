import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockApi } from '../mocks/mockApi';
import { mockRepository } from '../mocks/mockRepository';
import { renderWithProviders } from '../test/render';
import { SavedPage } from './SavedPage';

describe('SavedPage', () => {
  it('удаляет документ и обновляет страницу без reload', async () => {
    await mockRepository.register({
      displayName: 'Saved User',
      email: 'saved-page@example.local',
      password: 'Strong123',
      acceptedTerms: true,
      remember: true,
    });
    await mockApi.saveDocument('py-1001');
    const user = userEvent.setup();
    renderWithProviders(<SavedPage />, '/saved');

    expect(
      await screen.findByText('Как удалить дубликаты из списка, сохранив порядок элементов?'),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Удалить' }));

    expect(await screen.findByText('Нет сохранённых документов')).toBeInTheDocument();
    expect(mockRepository.getSavedEntries()).toEqual([]);
  });
});
