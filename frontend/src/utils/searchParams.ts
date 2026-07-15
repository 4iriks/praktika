import type {
  SearchFilters,
  SearchHistoryItem,
  SearchMode,
  SearchRequest,
  SearchSort,
  SearchView,
  UserPreferences,
} from '../types';

const modes: SearchMode[] = ['bm25', 'vector', 'hybrid'];
const views: SearchView[] = ['documents', 'answer'];
const sorts: SearchSort[] = ['relevance', 'date', 'score'];

function oneOf<T extends string>(value: string | null, values: T[], fallback: T): T {
  return value && values.includes(value as T) ? (value as T) : fallback;
}

function positiveInteger(value: string | null, fallback: number): number {
  const parsed = Number.parseInt(value ?? '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function parseSearchRequest(
  params: URLSearchParams,
  preferences?: UserPreferences,
): SearchRequest {
  const filters: SearchFilters = {
    tags: (params.get('tags') ?? '')
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean),
    minScore: Math.max(0, Number(params.get('min_score') ?? 0) || 0),
    acceptedOnly: params.get('accepted') === 'true',
    hasCodeOnly: params.get('has_code') === 'true',
    sort: oneOf(params.get('sort'), sorts, 'relevance'),
  };

  return {
    q: params.get('q')?.trim() ?? '',
    view: oneOf(params.get('view'), views, preferences?.defaultSearchView ?? 'documents'),
    mode: oneOf(params.get('mode'), modes, preferences?.defaultSearchMode ?? 'hybrid'),
    page: positiveInteger(params.get('page'), 1),
    pageSize: positiveInteger(params.get('page_size'), preferences?.defaultPageSize ?? 6),
    filters,
  };
}

export function requestToParams(request: SearchRequest): URLSearchParams {
  const params = new URLSearchParams({
    q: request.q,
    view: request.view,
    mode: request.mode,
    page: String(request.page),
    sort: request.filters.sort,
  });

  if (request.filters.tags.length > 0) params.set('tags', request.filters.tags.join(','));
  if (request.filters.minScore > 0) params.set('min_score', String(request.filters.minScore));
  if (request.filters.acceptedOnly) params.set('accepted', 'true');
  if (request.filters.hasCodeOnly) params.set('has_code', 'true');
  if (request.pageSize !== 6) params.set('page_size', String(request.pageSize));

  return params;
}

export function historyItemToParams(item: SearchHistoryItem): URLSearchParams {
  return requestToParams({
    q: item.query,
    view: item.view,
    mode: item.mode,
    page: 1,
    pageSize: item.pageSize,
    filters: { ...item.filters, sort: item.sort },
  });
}

export function hasActiveFilters(filters: SearchFilters): boolean {
  return (
    filters.tags.length > 0 ||
    filters.minScore > 0 ||
    filters.acceptedOnly ||
    filters.hasCodeOnly ||
    filters.sort !== 'relevance'
  );
}

export const emptyFilters: SearchFilters = {
  tags: [],
  minScore: 0,
  acceptedOnly: false,
  hasCodeOnly: false,
  sort: 'relevance',
};
