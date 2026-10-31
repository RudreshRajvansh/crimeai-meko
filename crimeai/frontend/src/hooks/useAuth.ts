import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { authApi } from '@/services/auth'
import { getErrorMessage, refreshSession } from '@/services/api'
import { isAuthenticated, useAuthStore } from '@/store/auth'

/** On first load, trade the refresh cookie (if any) for an access token before rendering protected routes. */
export function useSessionBootstrap() {
  const bootstrapped = useAuthStore((s) => s.bootstrapped)
  useEffect(() => {
    if (bootstrapped) return
    const { user, markBootstrapped } = useAuthStore.getState()
    if (!user) {
      markBootstrapped()
      return
    }
    refreshSession().finally(markBootstrapped)
  }, [bootstrapped])
  return bootstrapped
}

export function useLogin() {
  const setSession = useAuthStore((s) => s.setSession)
  const navigate = useNavigate()
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) => authApi.login(email, password),
    onSuccess: (session) => {
      setSession(session)
      navigate('/dashboard')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
}

export function useLogout() {
  const clearSession = useAuthStore((s) => s.clearSession)
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return async () => {
    try {
      await authApi.logout()
    } finally {
      clearSession()
      queryClient.clear()
      navigate('/login')
      toast.success('Signed out')
    }
  }
}

export function useCurrentUser() {
  const authenticated = useAuthStore(isAuthenticated)
  const setUser = useAuthStore((s) => s.setUser)
  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const user = await authApi.me()
      setUser(user)
      return user
    },
    enabled: authenticated,
    staleTime: 5 * 60_000,
  })
}
