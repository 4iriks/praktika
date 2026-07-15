import type {
  AdminUserFilters,
  AuditFilters,
  JobFilters,
  ManagedDocumentFilters,
  SourceFilters,
} from '../types';

function positiveInt(value: string | null, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function oneOf<T extends string>(value: string | null, values: readonly T[], fallback: T): T {
  return value && values.includes(value as T) ? (value as T) : fallback;
}

export function managedDocumentFilters(params: URLSearchParams): ManagedDocumentFilters {
  return {
    q: params.get('q') ?? '',
    status: oneOf(
      params.get('status'),
      ['ALL', 'ACTIVE', 'HIDDEN', 'PENDING', 'FAILED', 'OUTDATED'],
      'ALL',
    ),
    tags: (params.get('tags') ?? '')
      .split(',')
      .map((tag) => tag.trim())
      .filter(Boolean),
    accepted: oneOf(params.get('accepted'), ['all', 'true', 'false'], 'all'),
    hasCode: oneOf(params.get('has_code'), ['all', 'true', 'false'], 'all'),
    bm25: oneOf(
      params.get('bm25'),
      ['ALL', 'READY', 'PENDING', 'FAILED', 'NOT_INDEXED', 'OUTDATED'],
      'ALL',
    ),
    vector: oneOf(
      params.get('vector'),
      ['ALL', 'READY', 'PENDING', 'FAILED', 'NOT_INDEXED', 'OUTDATED'],
      'ALL',
    ),
    source: params.get('source') ?? '',
    updatedAfter: params.get('updated_after') ?? '',
    sort: oneOf(
      params.get('sort'),
      ['updated_desc', 'updated_asc', 'rating_desc', 'title_asc', 'status_asc'],
      'updated_desc',
    ),
    page: positiveInt(params.get('page'), 1),
    limit:
      oneOf(params.get('limit'), ['10', '20', '50'], '20') === '10'
        ? 10
        : oneOf(params.get('limit'), ['10', '20', '50'], '20') === '50'
          ? 50
          : 20,
  };
}

export function jobFilters(params: URLSearchParams): JobFilters {
  return {
    id: params.get('id') ?? '',
    type: oneOf(
      params.get('type'),
      ['ALL', 'SOURCE_SYNC', 'DOCUMENT_REINDEX', 'FULL_REINDEX', 'HEALTH_CHECK'],
      'ALL',
    ),
    status: oneOf(
      params.get('status'),
      ['ALL', 'QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'],
      'ALL',
    ),
    stage: oneOf(
      params.get('stage'),
      [
        'ALL',
        'PREPARING',
        'CRAWLING',
        'CLEANING',
        'DEDUPLICATING',
        'CHUNKING',
        'EMBEDDING',
        'INDEXING_BM25',
        'INDEXING_VECTOR',
        'FINALIZING',
      ],
      'ALL',
    ),
    actor: params.get('actor') ?? '',
    documentId: params.get('documentId') ?? '',
    source: params.get('source') ?? '',
    dateFrom: params.get('dateFrom') ?? '',
    dateTo: params.get('dateTo') ?? '',
    sort: oneOf(
      params.get('sort'),
      ['created_desc', 'created_asc', 'progress_desc'],
      'created_desc',
    ),
    page: positiveInt(params.get('page'), 1),
    limit: positiveInt(params.get('limit'), 20),
  };
}

export function adminUserFilters(params: URLSearchParams): AdminUserFilters {
  return {
    q: params.get('q') ?? '',
    role: oneOf(params.get('role'), ['ALL', 'USER', 'EDITOR', 'ADMIN'], 'ALL'),
    status: oneOf(params.get('status'), ['ALL', 'ACTIVE', 'BLOCKED'], 'ALL'),
    registeredFrom: params.get('registeredFrom') ?? '',
    registeredTo: params.get('registeredTo') ?? '',
    sort: oneOf(
      params.get('sort'),
      ['created_desc', 'created_asc', 'activity_desc', 'name_asc'],
      'created_desc',
    ),
    page: positiveInt(params.get('page'), 1),
    limit: positiveInt(params.get('limit'), 20),
  };
}

export function sourceFilters(params: URLSearchParams): SourceFilters {
  return {
    q: params.get('q') ?? '',
    status: oneOf(
      params.get('status'),
      ['ALL', 'IDLE', 'CHECKING', 'SYNCING', 'PAUSED', 'ERROR', 'DISABLED'],
      'ALL',
    ),
    enabled: oneOf(params.get('enabled'), ['all', 'true', 'false'], 'all'),
    page: positiveInt(params.get('page'), 1),
    limit: positiveInt(params.get('limit'), 20),
  };
}

export function auditFilters(params: URLSearchParams): AuditFilters {
  return {
    q: params.get('q') ?? '',
    actor: params.get('actor') ?? '',
    role: oneOf(params.get('role'), ['ALL', 'USER', 'EDITOR', 'ADMIN'], 'ALL'),
    action: oneOf(
      params.get('action'),
      [
        'ALL',
        'LOGIN',
        'LOGOUT',
        'REGISTER',
        'UPDATE_PROFILE',
        'UPDATE_DOCUMENT_METADATA',
        'HIDE_DOCUMENT',
        'RESTORE_DOCUMENT',
        'REINDEX_DOCUMENT',
        'BULK_HIDE_DOCUMENTS',
        'BULK_RESTORE_DOCUMENTS',
        'BULK_REINDEX_DOCUMENTS',
        'CHANGE_USER_ROLE',
        'BLOCK_USER',
        'UNBLOCK_USER',
        'UPDATE_SOURCE',
        'TEST_SOURCE',
        'START_SOURCE_SYNC',
        'STOP_SOURCE_SYNC',
        'RETRY_JOB',
        'CANCEL_JOB',
        'START_FULL_REINDEX',
        'HEALTH_CHECK',
        'UPDATE_SYSTEM_SETTINGS',
      ],
      'ALL',
    ),
    entityType: oneOf(
      params.get('entityType'),
      ['ALL', 'AUTH', 'USER', 'DOCUMENT', 'DOCUMENT_BATCH', 'SOURCE', 'JOB', 'SYSTEM'],
      'ALL',
    ),
    outcome: oneOf(params.get('outcome'), ['ALL', 'SUCCESS', 'FAILURE'], 'ALL'),
    dateFrom: params.get('dateFrom') ?? '',
    dateTo: params.get('dateTo') ?? '',
    sort: oneOf(params.get('sort'), ['created_desc', 'created_asc'], 'created_desc'),
    page: positiveInt(params.get('page'), 1),
    limit: positiveInt(params.get('limit'), 20),
  };
}

export function setParam(
  current: URLSearchParams,
  key: string,
  value: string | number,
  resetPage = true,
): URLSearchParams {
  const next = new URLSearchParams(current);
  if (String(value)) next.set(key, String(value));
  else next.delete(key);
  if (resetPage) next.set('page', '1');
  return next;
}
