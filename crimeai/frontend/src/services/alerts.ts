import { api } from './api'
import type { Alert, AlertListResponse } from '@/types'

export const alertsApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<AlertListResponse>('/alerts/', { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<Alert>(`/alerts/${id}`).then((r) => r.data),

  create: (payload: Partial<Alert>) =>
    api.post<Alert>('/alerts/', payload).then((r) => r.data),

  markRead: (id: string) => api.patch(`/alerts/${id}/read`).then(() => undefined),

  resolve: (id: string) => api.patch(`/alerts/${id}/resolve`).then(() => undefined),
}
