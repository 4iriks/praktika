import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { api } from '../../api';
import { queryKeys } from '../../api/queryKeys';
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
      setSaved(nextSaved);
      return { previous };
    },
    onSuccess: (nextSaved) => {
      toast.success(nextSaved ? 'Документ сохранён' : 'Документ удалён из сохранённых');
      void queryClient.invalidateQueries({ queryKey: queryKeys.document.detail(documentId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.search.root });
      void queryClient.invalidateQueries({ queryKey: queryKeys.saved.root });
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.stats });
    },
    onError: (_, __, context) => {
      setSaved(context?.previous ?? initiallySaved);
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
