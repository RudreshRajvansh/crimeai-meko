/**
 * HTTP client. Attaches the in-memory access token, sends the CSRF guard
 * header, and transparently refreshes the session once on a 401: concurrent
 * failures share a single refresh call instead of stampeding the endpoint.
 */
import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios'
import { useAuthStore } from '@/store/auth'
import type { SessionResponse } from '@/types'

// Empty base URL = same origin. In production the SPA host proxies /api to the backend,
// which keeps the refresh cookie first-party.
export const API_BASE = `${import.meta.env.VITE_API_URL || ''}/api/v1`
const CLIENT_HEADER = { 'X-CrimeAI-Client': 'web' }

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json', ...CLIENT_HEADER },
})

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshInFlight: Promise<string | null> | null = null

/** Exchange the refresh cookie for a new access token. Resolves null when the session is gone. */
export function refreshSession(): Promise<string | null> {
  refreshInFlight ??= axios
    .post<SessionResponse>(`${API_BASE}/auth/refresh`, null, { withCredentials: true, headers: CLIENT_HEADER })
    .then(({ data }) => {
      useAuthStore.getState().setSession(data)
      return data.access_token
    })
    .catch(() => {
      useAuthStore.getState().clearSession()
      return null
    })
    .finally(() => {
      refreshInFlight = null
    })
  return refreshInFlight
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
    const isAuthCall = original?.url?.startsWith('/auth/')
    if (error.response?.status !== 401 || !original || original._retried || isAuthCall) {
      return Promise.reject(error)
    }
    original._retried = true
    const token = await refreshSession()
    if (!token) return Promise.reject(error)
    original.headers.Authorization = `Bearer ${token}`
    return api(original)
  },
)

// Messages from the language-model layer name the upstream provider; the UI shows the product's own wording.
const PROVIDER_NAMES = /gemini|google|googleapis|generativelanguage|vertex/i

export function brandSafe(message: string): string {
  if (!PROVIDER_NAMES.test(message)) return message
  if (/not configured/i.test(message)) return 'The CrimeAI language engine is switched off on this server.'
  return 'The CrimeAI language engine is busy right now. Try again in a few seconds.'
}

export function getErrorMessage(err: unknown): string {
  return brandSafe(rawErrorMessage(err))
}

function rawErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { message?: string; detail?: unknown } | undefined
    if (data?.message) return data.message
    if (Array.isArray(data?.detail)) return (data.detail as { msg: string }[]).map((d) => d.msg).join('; ')
    if (typeof data?.detail === 'string') return data.detail
    return err.message || 'Request failed'
  }
  return err instanceof Error ? err.message : 'An unexpected error occurred'
}
