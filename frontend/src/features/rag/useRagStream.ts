import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api';
import type { AskRequest, AskResponse, RagSource, RagStage } from '../../types';

interface RagStreamState {
  data?: AskResponse;
  streamedAnswer: string;
  sources: RagSource[];
  stage: RagStage;
  isLoading: boolean;
  error: Error | null;
  cancel: () => void;
}

export function useRagStream(
  request: AskRequest,
  retryKey: number,
  onComplete?: (response: AskResponse) => void,
): RagStreamState {
  const [state, setState] = useState<RagStreamState>({
    streamedAnswer: '',
    sources: [],
    stage: 'searching',
    isLoading: true,
    error: null,
    cancel: () => undefined,
  });
  const controllerRef = useRef<AbortController | null>(null);
  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    setState((current) => ({ ...current, isLoading: false }));
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setState({
      streamedAnswer: '',
      sources: [],
      stage: 'searching',
      isLoading: true,
      error: null,
      cancel,
    });

    void api
      .askQuestion(request, {
        signal: controller.signal,
        onStage: (stage) => setState((current) => ({ ...current, stage })),
        onSources: (sources) => setState((current) => ({ ...current, sources })),
        onChunk: (chunk) =>
          setState((current) => ({
            ...current,
            streamedAnswer: current.streamedAnswer + chunk,
          })),
      })
      .then((data) => {
        setState((current) => ({
          ...current,
          data,
          sources: data.sources,
          streamedAnswer: data.answer,
          stage: 'complete',
          isLoading: false,
        }));
        onComplete?.(data);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setState((current) => ({
          ...current,
          isLoading: false,
          error: error instanceof Error ? error : new Error('Неизвестная ошибка'),
        }));
      });

    return () => controller.abort();
  }, [cancel, onComplete, request, retryKey]);

  return state;
}
