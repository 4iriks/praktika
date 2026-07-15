import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { mockRepository } from '../../mocks/mockRepository';
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

  it('сохраняет positive feedback из интерфейса', async () => {
    await registerFeedbackUser('positive-ui@example.local');
    const user = userEvent.setup();
    renderWithProviders(<RagAnswer question="asyncio gather" mode="hybrid" />);
    await screen.findByText('Qwen через Ollama', {}, { timeout: 4000 });

    await user.click(screen.getByRole('button', { name: 'Полезно' }));

    expect(await screen.findByRole('button', { name: 'Отменить оценку' })).toBeInTheDocument();
    expect(mockRepository.getUserStats().ratedAnswers).toBe(1);
  });

  it('отправляет negative feedback через диалог с причиной', async () => {
    await registerFeedbackUser('negative-ui@example.local');
    const user = userEvent.setup();
    renderWithProviders(<RagAnswer question="asyncio gather" mode="hybrid" />);
    await screen.findByText('Qwen через Ollama', {}, { timeout: 4000 });

    await user.click(screen.getByRole('button', { name: 'Не полезно' }));
    await user.click(screen.getByLabelText('Ответ содержит ошибку'));
    await user.type(
      screen.getByRole('textbox', { name: 'Дополнительный комментарий' }),
      'Ошибка в примере',
    );
    await user.click(screen.getByRole('button', { name: 'Сохранить оценку' }));

    expect(await screen.findByRole('button', { name: 'Отменить оценку' })).toBeInTheDocument();
    expect(mockRepository.getUserStats().ratedAnswers).toBe(1);
  });
});

async function registerFeedbackUser(email: string) {
  return mockRepository.register({
    displayName: 'Feedback User',
    email,
    password: 'Strong123',
    acceptedTerms: true,
    remember: true,
  });
}
