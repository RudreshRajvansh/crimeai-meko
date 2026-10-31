import { useState } from 'react'
import { CheckCheck } from 'lucide-react'
import { useAlerts, useMarkAlertRead, useResolveAlert } from '@/hooks/useAlerts'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import AlertCases from '@/components/alerts/AlertCases'
import { severityBadgeClass, timeAgo, cn } from '@/utils'

const SEVERITY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All severities' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

export default function AlertsPage() {
  const [showResolved, setShowResolved] = useState(false)
  const [severity, setSeverity] = useState('')

  const { data, isLoading } = useAlerts({
    limit: 100,
    is_resolved: showResolved ? undefined : false,
    ...(severity && { severity }),
  })

  const markRead = useMarkAlertRead()
  const resolve = useResolveAlert()

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 bg-bg-secondary rounded-lg p-1">
          {SEVERITY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setSeverity(opt.value)}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs transition-colors',
                severity === opt.value
                  ? 'bg-bg-elevated text-text-primary font-medium'
                  : 'text-text-muted hover:text-text-secondary'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer ml-auto">
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
            className="rounded"
          />
          Show resolved
        </label>

        {data && (
          <div className="text-xs text-text-muted">
            {data.unread_count} unread · {data.total} total
          </div>
        )}
      </div>

      {isLoading ? (
        <PageLoader />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={<CheckCheck size={24} />}
          title="No alerts"
          description="You're all caught up! No active alerts matching your filters."
        />
      ) : (
        <div className="space-y-2">
          {data.items.map((alert) => (
            <div
              key={alert.id}
              className={cn(
                'card p-4 transition-colors hover:bg-bg-hover',
                !alert.is_read && 'border-l-2 border-accent-blue'
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className={severityBadgeClass(alert.severity)}>{alert.severity}</span>
                    <span className="text-2xs text-text-muted bg-bg-elevated px-2 py-0.5 rounded capitalize">
                      {alert.alert_type.replace(/_/g, ' ')}
                    </span>
                    {alert.district && (
                      <span className="text-2xs text-text-muted">📍 {alert.district}</span>
                    )}
                    <span className="text-2xs text-text-muted ml-auto">{timeAgo(alert.created_at)}</span>
                  </div>
                  <p className="text-sm font-medium text-text-primary">{alert.title}</p>
                  <p className="text-xs text-text-secondary mt-1 leading-relaxed">{alert.message}</p>
                  <AlertCases alert={alert} onOpen={() => !alert.is_read && markRead.mutate(alert.id)} />
                </div>

                {/* Actions */}
                <div className="flex flex-col gap-1.5 flex-shrink-0">
                  {!alert.is_read && (
                    <button
                      onClick={() => markRead.mutate(alert.id)}
                      className="text-2xs text-accent-blue hover:underline whitespace-nowrap"
                    >
                      Mark read
                    </button>
                  )}
                  {!alert.is_resolved && (
                    <button
                      onClick={() => resolve.mutate(alert.id)}
                      className="text-2xs text-severity-low hover:underline whitespace-nowrap"
                    >
                      Resolve
                    </button>
                  )}
                  {alert.is_resolved && (
                    <span className="text-2xs text-text-muted">Resolved</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
