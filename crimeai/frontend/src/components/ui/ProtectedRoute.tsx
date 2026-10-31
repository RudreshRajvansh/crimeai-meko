import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { isAuthenticated, ROLE_RANK, useAuthStore } from '@/store/auth'
import type { UserRole } from '@/types'

interface ProtectedRouteProps {
  minimumRole?: UserRole
}

/** Client-side gating is for navigation only; every API call is authorised again on the server. */
export default function ProtectedRoute({ minimumRole = 'readonly' }: ProtectedRouteProps) {
  const bootstrapped = useAuthStore((s) => s.bootstrapped)
  const authenticated = useAuthStore(isAuthenticated)
  const role = useAuthStore((s) => s.user?.role)
  const location = useLocation()

  if (!bootstrapped) return <PageLoader />
  if (!authenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (ROLE_RANK[role ?? 'readonly'] < ROLE_RANK[minimumRole]) return <Navigate to="/dashboard" replace />
  return <Outlet />
}
