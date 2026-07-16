import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '../../test/render';
import { IndexesPage } from './IndexesPage';

describe('IndexesPage', () => {
  it('показывает active version и честные offline состояния mock-инфраструктуры', async () => {
    renderWithProviders(<IndexesPage />);
    expect((await screen.findAllByText('pyanswer_chunks_mock_6_1')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('OFFLINE').length).toBeGreaterThan(0);
    expect(screen.getAllByText('qwen3-embedding:0.6b').length).toBeGreaterThan(0);
  });

  it('требует confirmation перед full reindex', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IndexesPage />);
    await screen.findAllByText('pyanswer_chunks_mock_6_1');
    await user.click(screen.getByRole('button', { name: /Full reindex/i }));
    expect(screen.getByRole('alertdialog')).toHaveTextContent('полную переиндексацию');
  });
});
