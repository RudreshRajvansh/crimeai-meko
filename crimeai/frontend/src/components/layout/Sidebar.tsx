import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Map, FileText, Bell, Navigation,
  FlaskConical, Users, ChevronLeft, ChevronRight,
  Radar, Network, Plug, Orbit,
} from 'lucide-react'
import { cn } from '@/utils'
import { useUIStore } from '@/store/ui'
import { useAlertsStore } from '@/store/alerts'
import { useAuthStore } from '@/store/auth'

const NAV_ITEMS = [
  { to: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard',       roles: ['readonly','analyst','police','admin'] },
  { to: '/crimes',      icon: Map,             label: 'Crime Map',        roles: ['police','analyst','admin'] },
  { to: '/intel',       icon: Radar,           label: 'Intelligence',     roles: ['police','analyst','admin'] },
  { to: '/graph',       icon: Network,         label: 'Link Analysis',    roles: ['police','analyst','admin'] },
  { to: '/fir',         icon: FileText,        label: 'FIR Analysis',     roles: ['police','analyst','admin'] },
  { to: '/alerts',      icon: Bell,            label: 'Alerts',           roles: ['readonly','police','analyst','admin'] },
  { to: '/patrol',      icon: Navigation,      label: 'Patrol Routes',    roles: ['police','admin'] },
  { to: '/integrations', icon: Plug,         label: 'Integrations',     roles: ['police','analyst','admin'] },
  { to: '/swarm',       icon: Orbit,           label: 'Swarm',            roles: ['police','analyst','admin'] },
  { to: '/simulation',  icon: FlaskConical,    label: 'Simulation',       roles: ['analyst','admin'] },
  { to: '/admin',       icon: Users,           label: 'Admin Panel',      roles: ['admin'] },
]

export default function Sidebar() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed)
  const toggle = useUIStore((s) => s.toggleSidebar)
  const unreadCount = useAlertsStore((s) => s.unreadCount)
  const wsConnected = useAlertsStore((s) => s.wsConnected)
  const user = useAuthStore((s) => s.user)

  const visibleItems = NAV_ITEMS.filter((item) =>
    item.roles.includes(user?.role ?? 'readonly')
  )

  return (
    <aside
      className={cn(
        'flex flex-col h-screen bg-bg-secondary border-r border-border-default',
        'transition-all duration-200 ease-in-out flex-shrink-0',
        collapsed ? 'w-14' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className={cn(
        'flex items-center gap-2 px-3 py-4 border-b border-border-subtle',
        collapsed && 'justify-center'
      )}>
        <img src="/logo.png" alt="" className="h-7 w-7 flex-shrink-0 rounded-md" />
        {!collapsed && (
          <div>
            <p className="text-sm font-semibold text-text-primary leading-none">CrimeAI</p>
            <p className="text-2xs text-text-muted mt-0.5">Intelligence Platform</p>
          </div>
        )}
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {visibleItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(isActive ? 'nav-item-active' : 'nav-item', collapsed && 'justify-center px-2')
            }
            title={collapsed ? label : undefined}
          >
            <Icon size={16} className="flex-shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
            {!collapsed && label === 'Alerts' && unreadCount > 0 && (
              <span className="ml-auto bg-severity-high text-white text-2xs font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center">
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Connection status + collapse toggle */}
      <div className="border-t border-border-subtle px-2 py-3 space-y-2">
        {/* WS status */}
        {!collapsed && (
          <div className="flex items-center gap-2 px-3 py-1.5">
            <div className={cn('w-2 h-2 rounded-full flex-shrink-0',
              wsConnected ? 'bg-status-online animate-pulse-slow' : 'bg-status-offline'
            )} />
            <span className="text-2xs text-text-muted">
              {wsConnected ? 'Live feed active' : 'Disconnected'}
            </span>
          </div>
        )}

        {/* User mini-profile */}
        {!collapsed && user && (
          <div className="px-3 py-2 rounded-md bg-bg-tertiary">
            <p className="text-xs font-medium text-text-primary truncate">{user.full_name}</p>
            <p className="text-2xs text-text-muted capitalize">{user.role}</p>
          </div>
        )}

        {/* Collapse toggle */}
        <button
          onClick={toggle}
          className={cn('btn-ghost w-full text-text-muted', collapsed && 'justify-center')}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={14} /> : <><ChevronLeft size={14} /><span>Collapse</span></>}
        </button>
      </div>
    </aside>
  )
}
