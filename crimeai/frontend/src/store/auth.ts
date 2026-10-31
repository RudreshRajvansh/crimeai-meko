/**
 * Session state.
 *
 * The access token lives only in memory, so an XSS payload cannot lift a
 * long-lived credential from storage. The refresh token is an HttpOnly cookie
 * the browser sends to /auth/refresh by itself. Only the non-secret user
 * profile is persisted, so a reload can restore the shell and then silently
 * refresh the session.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { SessionResponse, User, UserRole } from '@/types'

export const ROLE_RANK: Record<UserRole, number> = { readonly: 0, analyst: 1, police: 2, admin: 3 }

interface AuthState {
  accessToken: string | null
  user: User | null
  /** True once the startup refresh attempt has finished, successfully or not. */
  bootstrapped: boolean

  setSession: (session: SessionResponse) => void
  clearSession: () => void
  markBootstrapped: () => void
  setUser: (user: User) => void
  hasRole: (minimum: UserRole) => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      accessToken: null,
      user: null,
      bootstrapped: false,

      setSession: (session) =>
        set({
          accessToken: session.access_token,
          user: {
            ...(get().user ?? {}),
            id: session.user_id,
            email: session.email,
            full_name: session.full_name,
            role: session.role,
            badge_number: get().user?.badge_number ?? null,
            department: get().user?.department ?? null,
          },
        }),
      clearSession: () => set({ accessToken: null, user: null }),
      markBootstrapped: () => set({ bootstrapped: true }),
      setUser: (user) => set({ user }),
      hasRole: (minimum) => ROLE_RANK[get().user?.role ?? 'readonly'] >= ROLE_RANK[minimum],
    }),
    {
      name: 'crimeai-profile',
      partialize: (state) => ({ user: state.user }),
    },
  ),
)

export const isAuthenticated = (state: AuthState) => Boolean(state.accessToken && state.user)
