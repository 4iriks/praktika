import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { updateSavedDocumentCache } from '../../api/queryCache';
import { queryKeys } from '../../api/queryKeys';
import type { Document, SearchResponse } from '../../types';
import { useAuth } from '../auth/useAuth';
import { loginUrl } from '../../utils/returnTo';

export function useSavedDocument(documentId: string, initiallySaved: boolean) {
  const [saved, setSaved] = useState(initiallySaved);
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  useEffect(() => setSaved(initiallySaved), [initiallySaved]);

  const mutation = useMutation({
    mutationFn: async (nextSaved: boolean) => {
      if (nextSaved) await api.saveDocument(documentId);
      else await api.unsaveDocument(documentId);
      return nextSaved;
    },
    onMutate: (nextSaved) => {
      const previous = saved;
      const searchSnapshot = queryClient.getQueriesData<SearchResponse>({
        queryKey: queryKeys.search.root,
      });
      const documentSnapshot = queryClient.getQueryData<Document>(
        queryKeys.document.detail(documentId),
      );
      setSaved(nextSaved);
      updateSavedDocumentCache(queryClient, documentId, nextSaved);
      return { previous, searchSnapshot, documentSnapshot };
    },
    onSuccess: (nextSaved) => {
      toast.success(nextSaved ? 'Документ сохранён' : 'Документ удалён из сохранённых');
      void queryClient.invalidateQueries({ queryKey: queryKeys.saved.root });
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.stats });
    },
    onError: (_, __, context) => {
      setSaved(context?.previous ?? initiallySaved);
      for (const [queryKey, data] of context?.searchSnapshot ?? []) {
        queryClient.setQueryData(queryKey, data);
      }
      queryClient.setQueryData(queryKeys.document.detail(documentId), context?.documentSnapshot);
      toast.error('Не удалось изменить сохранённые документы');
    },
  });

  const toggle = () => {
    if (!user) {
      const returnTo = location.pathname + location.search;
      toast.info('Войдите, чтобы сохранять документы');
      navigate(loginUrl(returnTo));
      return;
    }
    if (!mutation.isPending) mutation.mutate(!saved);
  };

  return { saved, isPending: mutation.isPending, toggle };
}
