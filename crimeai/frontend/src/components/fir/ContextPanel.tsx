import { Brain, Flag, Users } from 'lucide-react'
import type { FirContext } from '@/types'
import { cn, crimeTypeLabel } from '@/utils'

const ROLE_STYLE: Record<string, string> = {
  accused: 'bg-severity-high-bg text-severity-high',
  suspect: 'bg-severity-high-bg text-severity-high',
  victim: 'bg-accent-blue/15 text-accent-blue',
  complainant: 'bg-accent-blue/15 text-accent-blue',
  witness: 'bg-severity-low/15 text-severity-low',
}

// The contextual reading of a FIR: who did what to whom, in what order, and why.
export default function ContextPanel({ context, rulesCrimeType }: { context: FirContext; rulesCrimeType?: string | null }) {
  const traits = [
    context.premeditated && 'Premeditated',
    context.violence && 'Violent',
    context.injury && 'Injury',
  ].filter(Boolean) as string[]
  return (
    <div className="space-y-3 rounded-lg border border-accent-blue/30 bg-accent-blue/5 p-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 font-semibold text-accent-blue"><Brain size={13} /> Context understanding</p>
        <span className="font-mono text-2xs text-text-muted">severity {context.severity}/5</span>
      </div>

      <div>
        <p className="font-medium text-text-primary">
          {crimeTypeLabel(context.crime_type)}
          <span className="ml-2 font-mono text-2xs text-text-muted">{Math.round(context.confidence * 100)}%</span>
        </p>
        {context.reasoning && <p className="mt-0.5 text-text-secondary">{context.reasoning}</p>}
        {rulesCrimeType && rulesCrimeType !== context.crime_type && (
          <p className="mt-0.5 text-2xs text-severity-medium">Keyword match said {crimeTypeLabel(rulesCrimeType)}; the narrative reads as {crimeTypeLabel(context.crime_type)}.</p>
        )}
      </div>

      {(context.motive || context.relationship || traits.length > 0) && (
        <div className="flex flex-wrap gap-1">
          {context.motive && <span className="rounded bg-bg-tertiary px-2 py-0.5 text-2xs text-text-secondary">Motive: {context.motive}</span>}
          {context.relationship && <span className="rounded bg-bg-tertiary px-2 py-0.5 text-2xs text-text-secondary">{context.relationship}</span>}
          {traits.map((t) => <span key={t} className="rounded bg-severity-high-bg px-2 py-0.5 text-2xs text-severity-high">{t}</span>)}
        </div>
      )}

      {context.people.length > 0 && (
        <div>
          <p className="mb-1 flex items-center gap-1.5 text-text-muted"><Users size={12} /> People and roles</p>
          <div className="space-y-1">
            {context.people.map((p, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className={cn('w-20 flex-shrink-0 rounded px-1.5 py-0.5 text-center text-2xs capitalize', ROLE_STYLE[p.role] ?? 'bg-bg-tertiary text-text-secondary')}>{p.role}</span>
                <span className="text-text-primary">{p.name}{p.detail && <span className="text-text-muted"> · {p.detail}</span>}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {context.timeline.length > 0 && (
        <div>
          <p className="mb-1 text-text-muted">Sequence of events</p>
          <ol className="space-y-1 border-l border-accent-blue/40 pl-3">
            {context.timeline.map((t, i) => (
              <li key={i} className="relative text-text-secondary">
                <span className="absolute -left-[15px] top-1.5 h-1.5 w-1.5 rounded-full bg-accent-blue" />
                {t}
              </li>
            ))}
          </ol>
        </div>
      )}

      {context.red_flags.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <Flag size={12} className="text-severity-medium" />
          {context.red_flags.map((f) => <span key={f} className="rounded bg-severity-medium/15 px-2 py-0.5 text-2xs capitalize text-severity-medium">{f}</span>)}
        </div>
      )}
    </div>
  )
}
