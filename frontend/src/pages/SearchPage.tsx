import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { FileSearch, SlidersHorizontal } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { queryKeys } from '../api/queryKeys';
import type { AskResponse, SearchFilters, SearchMode, SearchView } from '../types';
import { useSearchShortcut } from '../hooks/useSearchShortcut';
import { parseSearchRequest, requestToParams } from '../utils/searchParams';
import { WorkspaceLayout } from '../layouts/WorkspaceLayout';
import { TechnicalPanel } from '../components/layout/TechnicalPanel';
import { Badge } from '../components/ui/Badge';
import { SearchBox } from '../components/ui/SearchBox';
import {
  EmptyQueryState,
  ErrorState,
  NoResultsState,
  ResultsSkeleton,
} from '../components/ui/QueryStates';
import { FiltersPanel } from '../features/search/FiltersPanel';
import { Pagination } from '../features/search/Pagination';
import { ResultCard } from '../features/search/ResultCard';
import { SearchModeControl } from '../features/search/SearchModeControl';
import { RagAnswer } from '../features/rag/RagAnswer';
import { useAuth } from '../features/auth/useAuth';

export function SearchPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const request = useMemo(
    () => parseSearchRequest(searchParams, user?.preferences),
    [searchParams, user?.preferences],
  );
  const [queryInput, setQueryInput] = useState(request.q);
  const [askResponse, setAskResponse] = useState<AskResponse>();
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  useSearchShortcut(inputRef);

  useEffect(() => setQueryInput(request.q), [request.q]);

  const documentsQuery = useQuery({
    queryKey: [...queryKeys.search.root, request],
    queryFn: ({ signal }) => api.searchDocuments(request, signal),
    enabled: request.view === 'documents' && request.q.length > 0,
  });

  useEffect(() => {
    if (!user || !documentsQuery.data || request.page !== 1) return;
    void queryClient.invalidateQueries({ queryKey: queryKeys.history.root });
    void queryClient.invalidateQueries({ queryKey: queryKeys.user.stats });
  }, [documentsQuery.data, queryClient, request.page, user]);

  const setRequest = useCallback(
    (changes: Partial<typeof request>) => {
      const next = { ...request, ...changes };
      setSearchParams(requestToParams(next));
    },
    [request, setSearchParams],
  );

  const changeFilters = (filters: SearchFilters) => {
    setRequest({ filters, page: 1 });
  };
  const changeMode = (mode: SearchMode) => setRequest({ mode, page: 1 });
  const changeView = (view: SearchView) => {
    setAskResponse(undefined);
    setRequest({ view, page: 1 });
  };
  const completeRag = useCallback(
    (response: AskResponse) => {
      setAskResponse(response);
      if (user) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.history.root });
        void queryClient.invalidateQueries({ queryKey: queryKeys.user.stats });
      }
    },
    [queryClient, user],
  );

  const filters = <FiltersPanel filters={request.filters} onChange={changeFilters} />;
  const technicalPanel = (
    <TechnicalPanel
      request={request}
      searchResponse={documentsQuery.data}
      askResponse={askResponse}
    />
  );

  return (
    <WorkspaceLayout filters={filters} technicalPanel={technicalPanel}>
      <div className="mx-auto w-full max-w-5xl px-3 py-4 sm:px-5 sm:py-5 lg:px-7">
        <div className="sticky top-0 z-20 -mx-3 -mt-4 border-b border-line/70 bg-canvas/95 px-3 pb-4 pt-4 backdrop-blur-md sm:-mx-5 sm:px-5 lg:-mx-7 lg:px-7">
          <SearchBox
            ref={inputRef}
            query={queryInput}
            onQueryChange={setQueryInput}
            view={request.view}
            onViewChange={changeView}
            onSubmit={() => setRequest({ q: queryInput.trim(), page: 1 })}
            compact
            loading={documentsQuery.isFetching}
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <SearchModeControl value={request.mode} onChange={changeMode} />
            <div className="flex items-center gap-2 text-[11px] text-muted">
              <SlidersHorizontal className="size-3.5 lg:hidden" aria-hidden="true" />
              {request.view === 'documents' ? (
                documentsQuery.data ? (
                  <>
                    Найдено{' '}
                    <span className="font-mono text-ink">
                      {documentsQuery.data.pagination.total}
                    </span>
                  </>
                ) : (
                  'Поиск по документам'
                )
              ) : (
                'Локальный RAG'
              )}
            </div>
          </div>
        </div>

        <div className="mt-5">
          {!request.q ? (
            <EmptyQueryState />
          ) : request.view === 'answer' ? (
            <RagAnswer
              question={request.q}
              mode={request.mode}
              filters={request.filters}
              pageSize={request.pageSize}
              onResponse={completeRag}
            />
          ) : documentsQuery.isLoading ? (
            <ResultsSkeleton />
          ) : documentsQuery.isError ? (
            <ErrorState onRetry={() => void documentsQuery.refetch()} />
          ) : documentsQuery.data && documentsQuery.data.results.length === 0 ? (
            <NoResultsState />
          ) : documentsQuery.data ? (
            <>
              <div className="mb-3 flex items-center gap-2">
                <FileSearch className="size-4 text-info" aria-hidden="true" />
                <h1 className="text-sm font-medium text-ink">Результаты для «{request.q}»</h1>
                <Badge className="ml-auto font-mono" tone="neutral">
                  {documentsQuery.data.metrics.tookMs} ms
                </Badge>
              </div>
              <div className="space-y-3">
                {documentsQuery.data.results.map((result, index) => (
                  <ResultCard
                    key={result.documentId}
                    result={result}
                    position={(request.page - 1) * request.pageSize + index + 1}
                    query={request.q}
                  />
                ))}
              </div>
              <Pagination
                value={documentsQuery.data.pagination}
                onPageChange={(page) => {
                  setRequest({ page });
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
              />
            </>
          ) : null}
        </div>
      </div>
    </WorkspaceLayout>
  );
}
