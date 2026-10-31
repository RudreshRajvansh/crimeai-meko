import { api } from './api'
import type { UserListResponse, User, UserStatsResponse, AuditLogListResponse } from '@/types'

export const adminApi = {
  getStats: () => api.get<UserStatsResponse>('/users/stats').then((r) => r.data),

  getAccessRequests: (params?: { limit?: number; offset?: number; account_status?: string }) =>
    api.get<UserListResponse>('/users/requests', { params }).then((r) => r.data),

  approveAccessRequest: (id: string) => api.patch<User>(`/users/requests/${id}/approve`).then((r) => r.data),

  rejectAccessRequest: (id: string, reason?: string) =>
    api.patch<User>(`/users/requests/${id}/reject`, { reason }).then((r) => r.data),

  getUsers: (params?: { limit?: number; offset?: number; role?: string; is_active?: boolean; account_status?: string }) =>
    api.get<UserListResponse>('/users/', { params }).then((r) => r.data),

  suspendUser: (id: string) => api.patch<User>(`/users/${id}/suspend`).then((r) => r.data),

  resetPassword: (id: string, password: string) => api.put(`/users/${id}/password`, { password }),

  reactivateUser: (id: string) => api.patch<User>(`/users/${id}/reactivate`).then((r) => r.data),

  /** Opens a profile-change proof in a new tab; the file needs the session token, so it is fetched, not linked. */
  openProof: async (proofUrl: string) => {
    const blob = await api.get(proofUrl, { responseType: 'blob' }).then((r) => r.data as Blob)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank', 'noopener')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  },

  getAuditLogs: (params?: { limit?: number; offset?: number }) =>
    api.get<AuditLogListResponse>('/users/audit-logs', { params }).then((r) => r.data),
}
