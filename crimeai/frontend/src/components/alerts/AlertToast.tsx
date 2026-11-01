/**
 * Live alert pop-up: an icon for what raised the alert (shared identifier, series, district risk, custody clock)
 * on a tile coloured by severity, so an officer can tell what happened before reading the title.
 */
import { Flame, Link2, Repeat2, Siren, Timer, X, type LucideIcon } from 'lucide-react'
import toast, { type Toast } from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/utils'
import type { AlertSeverity } from '@/types'

const KIND: Record<string, { icon: LucideIcon; label: string }> = {
  pattern: { icon: Link2, label: 'Linked identifier' },
  crime_series: { icon: Repeat2, label: 'Crime series' },
  high_risk: { icon: Flame, label: 'District risk' },
  custody_deadline: { icon: Timer, label: 'Custody deadline' },
}

const TONE: Record<AlertSeverity, { tile: string; ring: string; bar: string }> = {
  critical: { tile: 'bg-severity-critical-bg text-severity-critical', ring: 'ring-severity-critical/40', bar: 'bg-severity-critical' },
  high: { tile: 'bg-severity-high-bg text-severity-high', ring: 'ring-severity-high/30', bar: 'bg-severity-high' },
  medium: { tile: 'bg-severity-medium-bg text-severity-medium', ring: 'ring-severity-medium/30', bar: 'bg-severity-medium' },
  low: { tile: 'bg-severity-low-bg text-severity-low', ring: 'ring-severity-low/30', bar: 'bg-severity-low' },
}

interface AlertToastProps {
  t: Toast
  title: string
  severity: AlertSeverity
  alertType: string
  district: string | null
}

function AlertToast({ t, title, severity, alertType, district }: AlertToastProps) {
  const navigate = useNavigate()
  const { icon: Icon, label } = KIND[alertType] ?? { icon: Siren, label: 'Alert' }
  const tone = TONE[severity] ?? TONE.high

  return (
    <div
      role="alert"
      className={cn(
        'pointer-events-auto relative flex w-[22rem] max-w-[calc(100vw-2rem)] items-start gap-3 overflow-hidden',
        'rounded-lg border border-border-default bg-bg-elevated py-3 pl-4 pr-3 shadow-lg',
        t.visible ? 'animate-fade-in' : 'opacity-0 transition-opacity',
      )}
    >
      <span className={cn('absolute inset-y-0 left-0 w-1', tone.bar)} aria-hidden="true" />
      <span className={cn('relative flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg ring-1', tone.tile, tone.ring)}>
        <Icon size={20} strokeWidth={2.25} aria-hidden="true" />
        {severity === 'critical' && (
          <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5" aria-hidden="true">
            <span className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-75', tone.bar)} />
            <span className={cn('relative inline-flex h-2.5 w-2.5 rounded-full', tone.bar)} />
          </span>
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-2xs font-medium uppercase tracking-wide text-text-muted">
          {severity} · {label}{district ? ` · ${district}` : ''}
        </p>
        <p className="mt-0.5 text-xs font-medium leading-snug text-text-primary">{title}</p>
        <button
          onClick={() => { toast.dismiss(t.id); navigate('/alerts') }}
          className="mt-1.5 text-2xs font-medium text-accent-blue hover:underline"
        >
          View alert
        </button>
      </div>
      <button
        onClick={() => toast.dismiss(t.id)}
        className="flex-shrink-0 rounded p-0.5 text-text-muted hover:bg-bg-hover hover:text-text-primary"
        aria-label="Dismiss alert"
      >
        <X size={14} />
      </button>
    </div>
  )
}

export function showAlertToast(alert: Omit<AlertToastProps, 't'>) {
  toast.custom((t) => <AlertToast t={t} {...alert} />, { duration: 8000 })
}
