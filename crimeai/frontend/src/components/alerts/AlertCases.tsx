import { Link, useNavigate } from 'react-router-dom'
import { ArrowUpRight, Network } from 'lucide-react'
import { crimeColor } from '@/lib/palette'
import { crimeTypeLabel, formatDate } from '@/utils'
import type { Alert } from '@/types'

interface AlertCasesProps {
  alert: Alert
  /** Number of case buttons before the rest collapse into "+N more"; all are shown when omitted. */
  limit?: number
  /** Called before navigating away, e.g. to mark the alert read or close a panel. */
  onOpen?: () => void
}

/** The cases behind an alert as one-click buttons, plus the network view when several cases share a link. */
export default function AlertCases({ alert, limit, onOpen }: AlertCasesProps) {
  const navigate = useNavigate()
  const cases = alert.cases ?? []
  if (!cases.length) return null

  const shown = limit ? cases.slice(0, limit) : cases
  const hidden = cases.length - shown.length
  const openNetwork = () => {
    onOpen?.()
    navigate('/graph', { state: { node: alert.graph_node } })
  }

  return (
    <div className="mt-2.5">
      <div className="flex flex-wrap gap-1.5">
        {shown.map((c) => (
          <Link
            key={c.id}
            to={`/cases/${c.id}`}
            onClick={onOpen}
            title={`${crimeTypeLabel(c.crime_type)} · ${c.district ?? 'Unknown district'}${c.occurred_at ? ` · ${formatDate(c.occurred_at, 'dd MMM yyyy')}` : ''}`}
            className="group inline-flex items-center gap-1.5 rounded-md border border-border-default bg-bg-primary px-2 py-1 text-2xs transition-colors hover:border-accent-blue hover:bg-accent-blue/10"
          >
            <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: crimeColor(c.crime_type) }} />
            <span className="font-mono text-text-primary">{c.case_number ?? c.id.slice(0, 8)}</span>
            {c.district && <span className="hidden text-text-muted sm:inline">{c.district}</span>}
            <ArrowUpRight size={11} className="text-text-muted group-hover:text-accent-blue" />
          </Link>
        ))}
        {hidden > 0 && (
          <button type="button" onClick={openNetwork} className="rounded-md px-2 py-1 text-2xs text-text-muted hover:text-text-primary">
            +{hidden} more
          </button>
        )}
      </div>
      {alert.graph_node && cases.length > 1 && (
        <button
          type="button"
          onClick={openNetwork}
          className="mt-2 inline-flex items-center gap-1.5 text-2xs font-medium text-accent-blue hover:underline"
        >
          <Network size={12} /> Open all {cases.length} cases as a network
        </button>
      )}
    </div>
  )
}
