import { api } from './api'
import type { MekoCall, MekoDatapack, MekoDecision, MekoMemoryList, MekoRecall, MekoStatus } from '@/types/meko'

// Meko calls go to a remote service: allow longer than the default 30 s.
const SLOW = { timeout: 120_000 }

export const mekoApi = {
  status: () => api.get<MekoStatus>('/meko/status').then((r) => r.data),

  recall: (text: string) => api.post<MekoRecall>('/meko/recall', { text }, SLOW).then((r) => r.data),

  share: (crimeId: string) => api.post(`/meko/cases/${crimeId}/share`, null, SLOW).then((r) => r.data),

  confirmSeries: (body: { own_ref?: string | null; refs: string[]; tokens: string[]; mo_tags: string[]; lead: string; note: string }) =>
    api.post<MekoDecision>('/meko/decisions/series', body, SLOW).then((r) => r.data),

  attach: (body: { series_id: string; own_ref: string; tokens: string[] }) =>
    api.post<MekoDecision>('/meko/decisions/attach', body, SLOW).then((r) => r.data),

  exclude: (body: { token: string; reason: string }) =>
    api.post<MekoDecision>('/meko/decisions/exclusion', body, SLOW).then((r) => r.data),

  memories: (datapack: MekoDatapack, promoted?: boolean) =>
    api.get<MekoMemoryList>(`/meko/memories/${datapack}`, { ...SLOW, params: promoted ? { promoted: true } : {} }).then((r) => r.data),

  editMemory: (datapack: MekoDatapack, id: string, text: string) =>
    api.patch<{ ok: boolean; error: string | null; text: string }>(`/meko/memories/${datapack}/${encodeURIComponent(id)}`, { text }, SLOW).then((r) => r.data),

  forgetMemory: (datapack: MekoDatapack, id: string) =>
    api.delete<{ ok: boolean; error: string | null }>(`/meko/memories/${datapack}/${encodeURIComponent(id)}`, SLOW).then((r) => r.data),

  calls: (limit = 100) => api.get<MekoCall[]>('/meko/calls', { params: { limit } }).then((r) => r.data),
}
