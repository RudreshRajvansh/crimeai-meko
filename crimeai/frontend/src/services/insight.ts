import { api } from './api'
import type {
  CaseMap,
  FreezePacket,
  Dossier,
  GraphPayload,
  GraphNode,
  LanguageMix,
  SearchResults,
  SystemStatus,
  TemporalMatrix,
  TimelinePayload,
} from '@/types'

export const insightApi = {
  graphOverview: () => api.get<GraphPayload>('/graph/overview').then((r) => r.data),
  graphNeighbourhood: (node: string, depth = 2) =>
    api.get<GraphPayload>('/graph/neighbourhood', { params: { node, depth } }).then((r) => r.data),
  freezePacket: (entityId: string) =>
    api.get<FreezePacket>(`/graph/entities/${entityId}/freeze-packet`).then((r) => r.data),
  caseMap: (crimeId: string) => api.get<CaseMap>(`/graph/case-map/${crimeId}`).then((r) => r.data),
  graphSearch: (q: string) => api.get<GraphNode[]>('/graph/search', { params: { q } }).then((r) => r.data),
  dossier: (crimeId: string) => api.get<Dossier>(`/crimes/${crimeId}/dossier`).then((r) => r.data),
  temporalMatrix: (params?: { crime_type?: string; district?: string; days?: number }) =>
    api.get<TemporalMatrix>('/analytics/temporal-matrix', { params }).then((r) => r.data),
  languages: () => api.get<LanguageMix>('/analytics/languages').then((r) => r.data),
  timeline: (days = 90) => api.get<TimelinePayload>('/analytics/timeline', { params: { days } }).then((r) => r.data),
  search: (q: string) => api.get<SearchResults>('/analytics/search', { params: { q } }).then((r) => r.data),
  system: () => api.get<SystemStatus>('/system/status').then((r) => r.data),
  tiger: (params?: { months?: number; days?: number; district?: string }) =>
    api.get<TigerOverview>('/analytics/tiger', { params, timeout: 60_000 }).then((r) => r.data),
  tigerSync: () => api.post<{ enabled?: boolean; synced?: number; watermark?: string }>('/analytics/tiger/sync', {}, { timeout: 120_000 }).then((r) => r.data),
}

export interface TigerOverview {
  enabled: boolean
  monthly?: { year: number; month: number; count: number }[]
  hours?: { hour: number; count: number }[]
  rows?: number
  chunks?: number
  compressed_chunks?: number
  aggregates?: string[]
  timescaledb?: string
  synced_at?: string | null
  days?: number
  months?: number
  district?: string | null
}
