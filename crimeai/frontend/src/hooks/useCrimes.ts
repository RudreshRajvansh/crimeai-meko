import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { crimesApi } from '@/services/crimes'
import { getErrorMessage } from '@/services/api'
import type { CrimeCreatePayload } from '@/types'

export const crimeKeys = {
  all: ['crimes'] as const,
  lists: () => [...crimeKeys.all, 'list'] as const,
  list: (params: Record<string, unknown>) => [...crimeKeys.lists(), params] as const,
  detail: (id: string) => [...crimeKeys.all, 'detail', id] as const,
  stats: (params?: Record<string, unknown>) => [...crimeKeys.all, 'stats', params] as const,
  heatmap: (params?: Record<string, unknown>) => [...crimeKeys.all, 'heatmap', params] as const,
  hotspots: (params?: Record<string, unknown>) => [...crimeKeys.all, 'hotspots', params] as const,
}

export function useCrimeList(params: Record<string, unknown> = {}) {
  return useQuery({
    queryKey: crimeKeys.list(params),
    queryFn: () => crimesApi.list(params),
    placeholderData: (prev) => prev,
  })
}

export function useCrime(id: string) {
  return useQuery({
    queryKey: crimeKeys.detail(id),
    queryFn: () => crimesApi.get(id),
    enabled: !!id,
  })
}

export function useCrimeStats(params?: Record<string, unknown>) {
  return useQuery({
    queryKey: crimeKeys.stats(params),
    queryFn: () => crimesApi.stats(params),
    staleTime: 1000 * 60 * 5,
  })
}

export function useHeatmap(params?: Record<string, unknown>) {
  return useQuery({
    queryKey: crimeKeys.heatmap(params),
    queryFn: () => crimesApi.heatmap(params),
    staleTime: 1000 * 60 * 10,
  })
}

export function useHotspots(params?: Record<string, unknown>) {
  return useQuery({
    queryKey: crimeKeys.hotspots(params),
    queryFn: () => crimesApi.hotspots(params),
    staleTime: 1000 * 60 * 10,
  })
}

export function useCreateCrime() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: CrimeCreatePayload) => crimesApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crimeKeys.all })
      toast.success('Crime record created')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
}

export function useUpdateCrime(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: Partial<CrimeCreatePayload>) => crimesApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crimeKeys.detail(id) })
      qc.invalidateQueries({ queryKey: crimeKeys.lists() })
      toast.success('Crime record updated')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
}

export function useDeleteCrime() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => crimesApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: crimeKeys.all })
      toast.success('Crime record deleted')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
}
