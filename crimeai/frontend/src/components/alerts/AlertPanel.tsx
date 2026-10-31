import { X, Bell, CheckCheck } from 'lucide-react'
import { useUIStore } from '@/store/ui'
import { useAlerts, useMarkAlertRead, useResolveAlert } from '@/hooks/useAlerts'
import { severityBadgeClass, timeAgo, cn } from '@/utils'
import AlertCases from '@/components/alerts/AlertCases'
import type { Alert } from '@/types'

interface AlertPanelProps { open: boolean }

export default function AlertPanel({ open }: AlertPanelProps) {
  const close = useUIStore((s) => s.toggleAlertPanel)
  const { data } = useAlerts({ limit: 50, is_resolved: false })
  const markRead = useMarkAlertRead()
  const resolve = useResolveAlert()

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/40 z-40 lg:hidden"
          onClick={close}
          aria-hidden
        />
      )}

      {/* Panel */}
      <aside className={cn(
        'fixed right-0 top-0 h-full w-80 bg-bg-secondary border-l border-border-default',
        'z-50 flex flex-col transition-transform duration-200',
        open ? 'translate-x-0' : 'translate-x-full'
      )}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <div className="flex items-center gap-2">
            <Bell size={14} className="text-text-secondary" />
            <span className="text-sm font-medium text-text-primary">Alerts</span>
            {data && data.unread_count > 0 && (
              <span className="text-2xs bg-severity-high text-white px-1.5 py-0.5 rounded-full font-bold">
                {data.unread_count}
              </span>
            )}
          </div>
          <button onClick={close} className="btn-ghost p-1">
            <X size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {!data || data.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-text-muted">
              <CheckCheck size={24} className="mb-2 opacity-40" />
              <p className="text-sm">No active alerts</p>
            </div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {data.items.map((alert) => (
                <AlertItem
                  key={alert.id}
                  alert={alert}
                  onRead={() => markRead.mutate(alert.id)}
                  onResolve={() => resolve.mutate(alert.id)}
                  onOpen={() => {
                    if (!alert.is_read) markRead.mutate(alert.id)
                    close()
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  )
}

function AlertItem({ alert, onRead, onResolve, onOpen }: {
  alert: Alert; onRead: () => void; onResolve: () => void; onOpen: () => void
}) {
  return (
    <div
      className={cn(
        'px-4 py-3 hover:bg-bg-hover transition-colors',
        !alert.is_read && 'border-l-2 border-accent-blue'
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <span className={severityBadgeClass(alert.severity)}>{alert.severity}</span>
        <span className="text-2xs text-text-muted flex-shrink-0">{timeAgo(alert.created_at)}</span>
      </div>
      <p className="text-xs font-medium text-text-primary mb-0.5">{alert.title}</p>
      <p className="text-2xs text-text-secondary leading-relaxed">{alert.message}</p>
      {alert.district && (
        <p className="text-2xs text-text-muted mt-1">📍 {alert.district}</p>
      )}
      <AlertCases alert={alert} limit={4} onOpen={onOpen} />
      <div className="flex gap-2 mt-2">
        {!alert.is_read && (
          <button onClick={onRead} className="text-2xs text-accent-blue hover:underline">
            Mark read
          </button>
        )}
        {!alert.is_resolved && (
          <button onClick={onResolve} className="text-2xs text-severity-low hover:underline">
            Resolve
          </button>
        )}
      </div>
    </div>
  )
}
