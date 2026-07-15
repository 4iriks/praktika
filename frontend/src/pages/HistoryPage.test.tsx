import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockRepository } from '../mocks/mockRepository';
import { renderWithProviders } from '../test/render';
import type { HistoryFilters } from '../types';
import { HistoryPage } from './HistoryPage';

const allHistory: HistoryFilters = {
  search: '',
  view: 'all',
  mode: 'all',
  dateSort: 'newest',
  page: 1,
  pageSize: 10,
};

describe('HistoryPage', () => {
  it('очищает историю только после подтверждения', async () => {
    await mockRepository.register({
      displayName: 'История Тест',
      email: 'history-page@example.local',
      password: 'Strong123',
      acceptedTerms: true,
      remember: true,
    });
    mockRepository.recordHistory({
      query: 'Как работает asyncio gather?',
      view: 'documents',
      mode: 'hybrid',
      filters: {
        tags: ['asyncio'],
        minScore: 0,
        acceptedOnly: false,
        hasCodeOnly: true,
      },
      sort: 'relevance',
      pageSize: 10,
      resultCount: 3,
      tookMs: 64,
    });

    const user = userEvent.setup();
    renderWithProviders(<HistoryPage />, '/history');

    expect(await screen.findByText('Как работает asyncio gather?')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Очистить историю' }));

    const dialog = screen.getByRole('alertdialog', { name: 'Очистить всю историю?' });
    expect(mockRepository.getHistory(allHistory).pagination.total).toBe(1);
    await user.click(within(dialog).getByRole('button', { name: 'Очистить' }));

    await waitFor(() => {
      expect(mockRepository.getHistory(allHistory).pagination.total).toBe(0);
    });
    expect(await screen.findByText('История пока пуста')).toBeInTheDocument();
  });
});
