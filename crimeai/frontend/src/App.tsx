import { Routes, Route, Navigate } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import ProtectedRoute from '@/components/ui/ProtectedRoute'
import AppLayout from '@/components/layout/AppLayout'
import LoginPage from '@/pages/auth/LoginPage'
import RequestAccessPage from '@/pages/auth/RequestAccessPage'
import RequestSubmittedPage from '@/pages/auth/RequestSubmittedPage'
import { useSessionBootstrap } from '@/hooks/useAuth'
import { useWebSocket } from '@/hooks/useWebSocket'

// Lazy-load heavy pages
const DashboardPage   = lazy(() => import('@/pages/dashboard/DashboardPage'))
const CrimeMapPage    = lazy(() => import('@/pages/crimes/CrimeMapPage'))
const CrimeListPage   = lazy(() => import('@/pages/crimes/CrimeListPage'))
const FIRPage         = lazy(() => import('@/pages/fir/FIRPage'))
const AlertsPage      = lazy(() => import('@/pages/alerts/AlertsPage'))
const PatrolPage      = lazy(() => import('@/pages/patrol/PatrolPage'))
const IntegrationsPage = lazy(() => import('@/pages/integrations/IntegrationsPage'))
const SimulationPage  = lazy(() => import('@/pages/simulation/SimulationPage'))
const SwarmPage = lazy(() => import('@/pages/swarm/SwarmPage'))
const AdminPage       = lazy(() => import('@/pages/admin/AdminPage'))
const IntelPage       = lazy(() => import('@/pages/intel/IntelPage'))
const LinkAnalysisPage = lazy(() => import('@/pages/intel/LinkAnalysisPage'))
const DossierPage     = lazy(() => import('@/pages/intel/DossierPage'))
const ProfilePage     = lazy(() => import('@/pages/profile/ProfilePage'))

export default function App() {
  useSessionBootstrap()
  // One alert stream for the whole session, not one per page layout.
  useWebSocket()
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/request-access" element={<RequestAccessPage />} />
      <Route path="/request-submitted" element={<RequestSubmittedPage />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      {/* Protected: all authenticated users */}
      <Route element={<ProtectedRoute minimumRole="readonly" />}>
        <Route element={<AppLayout title="Dashboard" subtitle="Real-time crime intelligence" />}>
          <Route path="/dashboard" element={<Suspense fallback={<PageLoader />}><DashboardPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Alerts" subtitle="Active notifications & warnings" />}>
          <Route path="/alerts" element={<Suspense fallback={<PageLoader />}><AlertsPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Profile" subtitle="Manage your account" />}>
          <Route path="/profile" element={<Suspense fallback={<PageLoader />}><ProfilePage /></Suspense>} />
        </Route>
      </Route>

      {/* Protected: police and above */}
      <Route element={<ProtectedRoute minimumRole="police" />}>
        <Route element={<AppLayout title="Patrol Optimizer" subtitle="AI-driven patrol route planning" />}>
          <Route path="/patrol" element={<Suspense fallback={<PageLoader />}><PatrolPage /></Suspense>} />
        </Route>
      </Route>

      {/* Protected: analyst and above. Pages that also write (FIR upload) hide those controls below police. */}
      <Route element={<ProtectedRoute minimumRole="analyst" />}>
        <Route element={<AppLayout title="Crime Map" subtitle="Geospatial crime intelligence" />}>
          <Route path="/crimes" element={<Suspense fallback={<PageLoader />}><CrimeMapPage /></Suspense>} />
          <Route path="/crimes/list" element={<Suspense fallback={<PageLoader />}><CrimeListPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="FIR Analysis" subtitle="NLP-powered FIR processing" />}>
          <Route path="/fir" element={<Suspense fallback={<PageLoader />}><FIRPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Integrations" subtitle="Click a system" />}>
          <Route path="/integrations" element={<Suspense fallback={<PageLoader />}><IntegrationsPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Intelligence" subtitle="Linked crime series, custody deadlines and daily briefing" />}>
          <Route path="/intel" element={<Suspense fallback={<PageLoader />}><IntelPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Link Analysis" subtitle="Vehicles, phones and UPI IDs that connect separate cases" />}>
          <Route path="/graph" element={<Suspense fallback={<PageLoader />}><LinkAnalysisPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Case Dossier" subtitle="Everything known about one case" />}>
          <Route path="/cases/:id" element={<Suspense fallback={<PageLoader />}><DossierPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="Swarm" subtitle="Hundreds of simulated futures for one case's network" />}>
          <Route path="/swarm" element={<Suspense fallback={<PageLoader />}><SwarmPage /></Suspense>} />
          <Route path="/swarm/:id" element={<Suspense fallback={<PageLoader />}><SwarmPage /></Suspense>} />
        </Route>
        <Route element={<AppLayout title="What-If Simulation" subtitle="Monte Carlo crime intervention modelling" />}>
          <Route path="/simulation" element={<Suspense fallback={<PageLoader />}><SimulationPage /></Suspense>} />
        </Route>
      </Route>

      {/* Protected: admin only */}
      <Route element={<ProtectedRoute minimumRole="admin" />}>
        <Route element={<AppLayout title="Admin Panel" subtitle="System administration & user management" />}>
          <Route path="/admin" element={<Suspense fallback={<PageLoader />}><AdminPage /></Suspense>} />
        </Route>
      </Route>

      {/* 404 fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
