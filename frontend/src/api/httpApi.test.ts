import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './ApiError';
import { httpApi, resetHttpSecurityStateForTests, subscribeToUnauthorized } from './httpApi';

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const feedback = {
  id: 'feedback-1',
  userId: 'user-1',
  responseId: 'response-1',
  value: 'positive' as const,
  question: 'Как работает Python?',
  createdAt: '2026-07-15T10:00:00Z',
  updatedAt: '2026-07-15T10:00:00Z',
};

describe('HTTP API security boundary', () => {
  beforeEach(() => {
    resetHttpSecurityStateForTests();
    vi.restoreAllMocks();
  });

  it('добавляет credentials и CSRF header к mutation без Bearer', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'csrf-value' }))
      .mockResolvedValueOnce(jsonResponse(feedback));

    await httpApi.sendFeedback({
      responseId: 'response-1',
      value: 'positive',
      question: 'Как работает Python?',
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: 'include' });
    const mutation = fetchMock.mock.calls[1]?.[1];
    expect(mutation).toMatchObject({ credentials: 'include', method: 'POST' });
    expect(mutation?.headers).toMatchObject({
      'X-CSRF-Token': 'csrf-value',
      'Content-Type': 'application/json',
    });
    expect(JSON.stringify(mutation?.headers)).not.toContain('Authorization');
    expect(JSON.stringify(mutation?.headers)).not.toContain('Bearer');
  });

  it('преобразует backend error envelope в ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(
        {
          error: {
            code: 'FORBIDDEN',
            message: 'Недостаточно прав',
            details: { permission: 'AUDIT_VIEW' },
            requestId: 'request-42',
          },
        },
        403,
      ),
    );

    const error = await httpApi.getSystemStatus().catch((value: unknown) => value);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 403,
      code: 'FORBIDDEN',
      message: 'Недостаточно прав',
      requestId: 'request-42',
      details: { permission: 'AUDIT_VIEW' },
    });
  });

  it('уведомляет auth store при 401', async () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToUnauthorized(listener);
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      jsonResponse(
        { error: { code: 'UNAUTHORIZED', message: 'Сессия завершена', details: {} } },
        401,
      ),
    );

    await expect(httpApi.getCurrentUser()).rejects.toMatchObject({ code: 'UNAUTHORIZED' });
    expect(listener).toHaveBeenCalledOnce();
    unsubscribe();
  });

  it('повторяет запрос после CSRF refresh только один раз', async () => {
    const csrfError = () =>
      jsonResponse(
        {
          error: {
            code: 'CSRF_INVALID',
            message: 'CSRF истёк',
            details: { reason: 'CSRF_INVALID' },
          },
        },
        403,
      );
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'first' }))
      .mockResolvedValueOnce(csrfError())
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'second' }))
      .mockResolvedValueOnce(csrfError());

    await expect(
      httpApi.sendFeedback({
        responseId: 'response-1',
        value: 'positive',
        question: 'Вопрос',
      }),
    ).rejects.toMatchObject({ code: 'CSRF_INVALID' });

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(fetchMock.mock.calls[3]?.[1]?.headers).toMatchObject({
      'X-CSRF-Token': 'second',
    });
  });

  it('передаёт mode и безопасные limits при запуске SOURCE_SYNC', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'sync-csrf' }))
      .mockResolvedValueOnce(jsonResponse({ id: 'job-1' }));

    await httpApi.startSourceSync('source/1', {
      mode: 'INITIAL',
      maxDocuments: 100,
      maxPages: 2,
      dryRun: false,
    });

    expect(fetchMock.mock.calls[1]?.[0]).toContain('/admin/sources/source%2F1/sync');
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({
      method: 'POST',
      body: JSON.stringify({
        mode: 'INITIAL',
        maxDocuments: 100,
        maxPages: 2,
        dryRun: false,
      }),
    });
  });

  it('использует operational ingestion endpoints только через API layer', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(jsonResponse({ items: [], pagination: {} })));

    await httpApi.getAdminJobEvents('job/1');
    await httpApi.getManagedDocumentChunks('document/1');
    await httpApi.getManagedDocumentRevisions('document/1');
    await httpApi.getManagedDocumentFailures('document/1');

    const urls = fetchMock.mock.calls.map(([url]) => {
      if (typeof url === 'string') return url;
      if (url instanceof URL) return url.href;
      return url.url;
    });
    expect(urls).toEqual([
      expect.stringContaining('/admin/jobs/job%2F1/events'),
      expect.stringContaining('/editor/documents/document%2F1/chunks'),
      expect.stringContaining('/editor/documents/document%2F1/revisions'),
      expect.stringContaining('/editor/documents/document%2F1/failures'),
    ]);
  });
});
