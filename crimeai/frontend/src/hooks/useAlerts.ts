import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { alertsApi } from '@/services/alerts'
import { getErrorMessage } from '@/services/api'

export const alertKeys = {
  all: ['alerts'] as const,
  list: (params?: Record<string, unknown>) => [...alertKeys.all, params] as const,
}

export function useAlerts(params?: Record<string, unknown>) {
  return useQuery({
    queryKey: alertKeys.list(params),
    queryFn: () => alertsApi.list(params),
    refetchInterval: 30_000,
  })
}

export function useMarkAlertRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => alertsApi.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: alertKeys.all }),
    onError: (err) => toast.error(getErrorMessage(err)),
  })
}

export function useResolveAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => alertsApi.resolve(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: alertKeys.all })
      toast.success('Alert resolved')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
}
