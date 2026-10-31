import { api } from './api'
import type { SessionResponse, User } from '@/types'

export const authApi = {
  login: (email: string, password: string) =>
    api.post<SessionResponse>('/auth/login', { email, password }).then((r) => r.data),

  logout: () => api.post('/auth/logout'),

  logoutEverywhere: () => api.post('/auth/logout-all'),

  wsTicket: () =>
    api.post<{ ticket: string; expires_in: number }>('/auth/ws-ticket').then((r) => r.data.ticket),

  me: () => api.get<User>('/users/me').then((r) => r.data),

  register: (data: any) => api.post('/auth/register', data).then((r) => r.data),
}
