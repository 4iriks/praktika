import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '../../test/render';
import { RagAnswer } from './RagAnswer';

describe('RagAnswer', () => {
  it('отображает источники и сведения о локальной модели', async () => {
    renderWithProviders(<RagAnswer question="asyncio gather" mode="hybrid" />);

    expect(await screen.findByText('Qwen через Ollama', {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText('Использованные источники')).toBeInTheDocument();
    expect(screen.getByText('[1]')).toBeInTheDocument();
  });

  it('показывает сообщение при недостаточном контексте', async () => {
    renderWithProviders(<RagAnswer question="квантовая хромодинамика" mode="hybrid" />);

    expect(
      await screen.findByText(
        'В базе не найдено достаточно информации для надёжного ответа. Попробуйте уточнить запрос.',
        {},
        { timeout: 4000 },
      ),
    ).toBeInTheDocument();
  });
});
