import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SearchResult } from '../../types';
import { renderWithProviders } from '../../test/render';
import { ResultCard } from './ResultCard';

const result: SearchResult = {
  documentId: 'py-test',
  title: 'Как работает asyncio gather',
  snippet: 'Конкурентный запуск нескольких задач.',
  tags: [
    { name: 'Python', slug: 'python' },
    { name: 'asyncio', slug: 'asyncio' },
  ],
  sourceUrl: 'https://example.com/question',
  publishedAt: '2025-01-05T00:00:00.000Z',
  questionScore: 42,
  answersCount: 3,
  acceptedAnswer: true,
  hasCode: true,
  saved: false,
  bm25Score: 11.2,
  vectorScore: 0.882,
  rerankerScore: 0.924,
  finalScore: 0.912,
};

describe('ResultCard', () => {
  it('показывает итоговый score и теги', () => {
    renderWithProviders(<ResultCard result={result} position={1} query="asyncio" />);
    expect(screen.getByText('score 0.912')).toBeInTheDocument();
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getAllByText('asyncio').length).toBeGreaterThan(0);
  });
});
