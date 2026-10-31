import { api } from './api'
import type { Crime, CrimeCreatePayload, CrimeListResponse, CrimeStats, HeatmapPoint, HotspotData } from '@/types'

export const crimesApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<CrimeListResponse>('/crimes/', { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<Crime>(`/crimes/${id}`).then((r) => r.data),

  create: (payload: CrimeCreatePayload) =>
    api.post<Crime>('/crimes/', payload).then((r) => r.data),

  update: (id: string, payload: Partial<CrimeCreatePayload>) =>
    api.patch<Crime>(`/crimes/${id}`, payload).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/crimes/${id}`),

  stats: (params?: { from_date?: string; to_date?: string; city?: string }) =>
    api.get<CrimeStats>('/crimes/stats', { params }).then((r) => r.data),

  heatmap: (params?: { from_date?: string; to_date?: string; crime_type?: string }) =>
    api.get<HeatmapPoint[]>('/crimes/heatmap', { params }).then((r) => r.data),

  nearby: (lat: number, lng: number, radius_km = 2, params?: Record<string, unknown>) =>
    api.get<Crime[]>('/crimes/nearby', { params: { latitude: lat, longitude: lng, radius_km, ...params } }).then((r) => r.data),

  exportGeoJSON: (params?: Record<string, unknown>) =>
    api.get('/crimes/export/geojson', { params }).then((r) => r.data),

  hotspots: (params?: { from_date?: string; to_date?: string; city?: string }) =>
    api.get<HotspotData[]>('/hotspots/', { params }).then((r) => r.data),
}
