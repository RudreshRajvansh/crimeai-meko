import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, Languages, MapPin, Package, RefreshCw, ShieldCheck, Sparkles, Swords } from 'lucide-react'
import toast from 'react-hot-toast'
import { firApi } from '@/services/fir'
import { getErrorMessage } from '@/services/api'
import { cn, timeAgo } from '@/utils'
import type { GeminiBrief, GeminiSection } from '@/types'

const STATUS: Record<GeminiSection['status'], { label: string; cls: string; title: string }> = {
  cited_in_fir: { label: 'in FIR', cls: 'bg-severity-low/15 text-severity-low', title: 'The FIR already cites this section' },
  new: { label: 'suggested', cls: 'bg-accent-blue/15 text-accent-blue', title: 'Not cited in the FIR: check before adding' },
  wrong_code: { label: 'old code', cls: 'bg-severity-medium/15 text-severity-medium', title: 'Uses the code that did not govern this incident date' },
  title_differs: { label: 'check title', cls: 'bg-severity-high/15 text-severity-high', title: "The AI's reason does not match this section's official title: it may have the wrong number" },
}

export function useGeminiStatus() {
  return useQuery({ queryKey: ['gemini', 'status'], queryFn: firApi.geminiStatus, staleTime: 5 * 60_000 })
}

/** Gemini's English reading of a saved FIR: generated on demand, then kept with the FIR. */
export function FirGeminiSection({ firId, cached }: { firId: string; cached?: GeminiBrief }) {
  const status = useGeminiStatus()
  const qc = useQueryClient()
  const [brief, setBrief] = useState<GeminiBrief | undefined>(cached)
  const run = useMutation({
    mutationFn: (refresh: boolean) => firApi.geminiBrief(firId, refresh),
    onSuccess: (b) => { setBrief(b); qc.invalidateQueries({ queryKey: ['fir', firId] }) },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  if (!brief && !status.data?.enabled) return null
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary">
          <Sparkles size={12} className="text-accent-purple" /> AI case brief
        </h3>
        {brief && status.data?.enabled && (
          <button type="button" onClick={() => run.mutate(true)} disabled={run.isPending} className="btn-ghost py-0.5 text-2xs" title="Generate the brief again">
            <RefreshCw size={11} className={cn(run.isPending && 'animate-spin')} /> Refresh
          </button>
        )}
      </div>
      {brief ? <GeminiBriefCard brief={brief} /> : (
        <button type="button" onClick={() => run.mutate(false)} disabled={run.isPending}
                className="flex w-full items-center justify-center gap-2 rounded-md border border-dashed border-accent-purple/50 bg-accent-purple/5 py-3 text-xs font-medium text-accent-purple hover:bg-accent-purple/10">
          <Sparkles size={14} className={cn(run.isPending && 'animate-pulse')} />
          {run.isPending ? 'Reading the FIR…' : 'Translate & brief with CrimeAI'}
        </button>
      )}
    </section>
  )
}

export function GeminiBriefCard({ brief }: { brief: GeminiBrief }) {
  const masked = Object.values(brief.redactions ?? {}).reduce((a, b) => a + b, 0)
  const facts = [
    { icon: Clock, label: 'When', value: brief.facts.when },
    { icon: MapPin, label: 'Where', value: brief.facts.where },
    { icon: Package, label: 'Property', value: brief.facts.property },
    { icon: Swords, label: 'Weapon', value: brief.facts.weapon },
  ]
  return (
    <div className="space-y-3 rounded-md border border-accent-purple/30 bg-accent-purple/[0.04] p-3">
      <div className="flex flex-wrap items-center gap-2">
        {brief.offence && <span className="rounded-full bg-accent-purple/15 px-2 py-0.5 text-2xs font-semibold text-accent-purple">{brief.offence}</span>}
        <span className="ml-auto inline-flex items-center gap-1 text-2xs text-text-muted" title="Personal identifiers are masked before the text leaves the server">
          <ShieldCheck size={11} className="text-severity-low" /> {masked} masked · CrimeAI engine · {timeAgo(brief.generated_at)}
        </span>
      </div>

      {brief.summary && <p className="text-sm leading-relaxed text-text-primary">{brief.summary}</p>}

      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
        {facts.map(({ icon: Icon, label, value }) => (
          <div key={label} className="rounded border border-border-subtle bg-bg-primary px-2 py-1.5" title={value || undefined}>
            <p className="flex items-center gap-1 text-2xs text-text-muted"><Icon size={10} /> {label}</p>
            <p className={cn('truncate text-xs', value ? 'text-text-primary' : 'text-text-muted')}>{value || '—'}</p>
          </div>
        ))}
      </div>

      {brief.modus_operandi.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {brief.modus_operandi.map((m) => <span key={m} className="rounded bg-bg-elevated px-1.5 py-0.5 text-2xs text-text-secondary">{m}</span>)}
        </div>
      )}

      {brief.suggested_sections.length > 0 && (
        <ul className="divide-y divide-border-subtle rounded border border-border-subtle bg-bg-primary">
          {brief.suggested_sections.map((s) => (
            <li key={`${s.code}-${s.section}`} className="grid grid-cols-[90px_1fr_auto] items-center gap-2 px-2.5 py-1.5 text-xs">
              <span className="font-mono text-accent-purple">{s.code} {s.section}</span>
              <span className="min-w-0">
                <span className="block truncate text-text-secondary" title={s.reason}>{s.reason}</span>
                {s.official_title && (
                  <span className={cn('block truncate text-2xs', s.status === 'title_differs' ? 'text-severity-high' : 'text-text-muted')} title="Official title from the IPC-BNS crosswalk">
                    Law: {s.official_title}
                  </span>
                )}
              </span>
              <span title={STATUS[s.status].title} className={cn('rounded px-1.5 py-0.5 text-2xs font-semibold', STATUS[s.status].cls)}>{STATUS[s.status].label}</span>
            </li>
          ))}
        </ul>
      )}

      {brief.missing.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-2xs font-semibold text-severity-medium">Missing:</span>
          {brief.missing.map((m) => <span key={m} className="rounded border border-severity-medium/40 px-1.5 py-0.5 text-2xs text-severity-medium">{m}</span>)}
        </div>
      )}

      {brief.english && (
        <details className="group">
          <summary className="flex cursor-pointer items-center gap-1 text-2xs font-medium text-accent-blue">
            <Languages size={11} /> English translation
          </summary>
          <p className="mt-1.5 whitespace-pre-wrap rounded bg-bg-primary p-2.5 text-xs leading-relaxed text-text-primary">{brief.english}</p>
        </details>
      )}
    </div>
  )
}
