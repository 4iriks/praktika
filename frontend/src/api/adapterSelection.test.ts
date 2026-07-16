import { describe, expect, it } from 'vitest';
import { httpApi } from './httpApi';
import { selectApiClient } from './index';
import { mockApi } from '../mocks/mockApi';

describe('API adapter selection', () => {
  it('сохраняет mock adapter для VITE_USE_MOCKS=true', () => {
    expect(selectApiClient(true)).toBe(mockApi);
  });

  it('выбирает HTTP adapter для VITE_USE_MOCKS=false', () => {
    expect(selectApiClient(false)).toBe(httpApi);
  });
});
