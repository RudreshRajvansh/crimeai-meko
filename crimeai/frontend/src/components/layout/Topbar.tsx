import { ArrowLeft, Bell, LogOut, Moon, Sun, User } from 'lucide-react'
import { useAlertsStore } from '@/store/alerts'
import { useAuthStore } from '@/store/auth'
import { useUIStore } from '@/store/ui'
import { useLogout } from '@/hooks/useAuth'
import { Link, useLocation } from 'react-router-dom'
import { useIsMobile } from '@/hooks/useIsMobile'

interface TopbarProps {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}

export default function Topbar({ title, subtitle, actions }: TopbarProps) {
  const unreadCount = useAlertsStore((s) => s.unreadCount)
  const toggleAlertPanel = useUIStore((s) => s.toggleAlertPanel)
  const isDark = useUIStore((s) => s.isDark)
  const toggleTheme = useUIStore((s) => s.toggleTheme)
  const user = useAuthStore((s) => s.user)
  const logout = useLogout()
  const mobile = useIsMobile()
  const { pathname } = useLocation()

  return (
    <header className="flex items-center justify-between gap-2 px-3 sm:px-5 py-3 border-b border-border-subtle bg-bg-primary flex-shrink-0">
      <div className="flex items-center gap-2 min-w-0">
        {mobile && pathname !== '/fir' && (
          <Link to="/fir" className="btn-ghost p-1.5 rounded-full" aria-label="Back to FIR Analysis"><ArrowLeft size={16} /></Link>
        )}
        <div className="min-w-0">
        <h1 className="text-sm font-semibold text-text-primary whitespace-nowrap">{title}</h1>
        {subtitle && <p className="text-2xs text-text-muted mt-0.5 hidden sm:block">{subtitle}</p>}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {actions}

        <button
          onClick={toggleTheme}
          className="btn-ghost p-2 rounded-full"
          aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          title={isDark ? 'Light mode' : 'Dark mode'}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <button
          onClick={toggleAlertPanel}
          className="relative btn-ghost p-2 rounded-full"
          aria-label="Alerts"
        >
          <Bell size={16} />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-severity-high rounded-full text-2xs text-white flex items-center justify-center font-bold">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </button>

        <div className="flex items-center gap-2 pl-2 border-l border-border-subtle">
          <Link to="/profile" className="flex items-center gap-2 hover:bg-bg-elevated px-2 py-1 rounded-md transition-colors">
            <div className="w-6 h-6 rounded-full bg-accent-blue/20 flex items-center justify-center">
              <User size={12} className="text-accent-blue" />
            </div>
            {user && <span className="text-xs text-text-secondary hidden sm:block">{user.full_name}</span>}
          </Link>
          <button onClick={logout} className="btn-ghost p-1.5" title="Logout">
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </header>
  )
}
