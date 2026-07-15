import type { ApiClient } from './types';
import { httpApi } from './httpApi';
import { mockApi } from '../mocks/mockApi';

export const useMocks = import.meta.env.VITE_USE_MOCKS !== 'false';
export const api: ApiClient = useMocks ? mockApi : httpApi;

export { ApiError } from './ApiError';
export type { ApiClient } from './types';
