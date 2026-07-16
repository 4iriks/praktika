import type { ApiClient } from './types';
import { httpApi } from './httpApi';
import { mockApi } from '../mocks/mockApi';

export const useMocks = import.meta.env.VITE_USE_MOCKS !== 'false';

export function selectApiClient(mockMode: boolean): ApiClient {
  return mockMode ? mockApi : httpApi;
}

export const api: ApiClient = selectApiClient(useMocks);

export { ApiError } from './ApiError';
export type { ApiClient } from './types';
