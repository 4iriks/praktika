import { useEffect, useState } from 'react';
import { api } from '../../api';
import type { AskRequest, AskResponse, RagStage } from '../../types';

interface RagStreamState {
  data?: AskResponse;
  streamedAnswer: string;
  stage: RagStage;
  isLoading: boolean;
  error: Error | null;
}

export function useRagStream(
  request: AskRequest,
  retryKey: number,
  onComplete?: (response: AskResponse) => void,
): RagStreamState {
  const [state, setState] = useState<RagStreamState>({
    streamedAnswer: '',
    stage: 'searching',
    isLoading: true,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    setState({
      streamedAnswer: '',
      stage: 'searching',
      isLoading: true,
      error: null,
    });

    void api
      .askQuestion(request, {
        signal: controller.signal,
        onStage: (stage) => setState((current) => ({ ...current, stage })),
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
  }, [onComplete, request, retryKey]);

  return state;
}
