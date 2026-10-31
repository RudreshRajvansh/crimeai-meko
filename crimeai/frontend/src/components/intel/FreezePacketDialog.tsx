import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowUpRight, Copy, Printer, Timer, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { getErrorMessage } from '@/services/api'
import { insightApi } from '@/services/insight'
import { cn, crimeTypeLabel, escapeHtml, formatDate } from '@/utils'

/** Mule accounts are typically emptied within hours; the banner turns red once the first day has passed. */
function urgency(hours: number): { label: string; cls: string } {
  if (hours <= 24) return { label: `${hours.toFixed(0)} h since the latest complaint — act now`, cls: 'border-severity-medium/40 bg-severity-medium/10 text-severity-medium' }
  const days = Math.floor(hours / 24)
  return { label: `${days} day${days === 1 ? '' : 's'} since the latest complaint — funds may already have moved`, cls: 'border-severity-high/40 bg-severity-high/10 text-severity-high' }
}

/** Review-and-send draft of one freeze/lien request covering every complaint that names this identifier. */
export default function FreezePacketDialog({ entityId, onClose }: { entityId: string; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['freeze-packet', entityId],
    queryFn: () => insightApi.freezePacket(entityId),
    retry: false,
  })
  const [draft, setDraft] = useState('')

  useEffect(() => { if (data) setDraft(data.draft) }, [data])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(draft)
      toast.success('Request copied')
    } catch {
      toast.error('Copy failed; select the text and copy it manually')
    }
  }

  const print = () => {
    const win = window.open('', '_blank', 'noopener,width=800,height=900')
    if (!win) return
    win.document.write(`<pre style="font:13px/1.5 'Times New Roman',serif;white-space:pre-wrap;margin:40px">${escapeHtml(draft)}</pre>`)
    win.document.close()
    win.print()
  }

  const level = data ? urgency(data.totals.hours_since_latest) : null

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Freeze request">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-bg-primary/70" />
      <div className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border-default bg-bg-secondary shadow-elevated">
        <header className="flex items-start justify-between gap-4 border-b border-border-subtle px-5 py-4">
          <div>
            <p className="text-2xs font-medium uppercase tracking-wider text-text-muted">Consolidated freeze / lien request</p>
            <h2 className="mt-0.5 font-mono text-base font-semibold text-text-primary">
              {data?.entity.identifier ?? data?.entity.label ?? '…'}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="btn-ghost p-1.5" aria-label="Close dialog"><X size={16} /></button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {isLoading && <PageLoader label="Assembling linked complaints…" />}
          {error && <p className="text-sm text-severity-high">{getErrorMessage(error)}</p>}
          {data && level && (
            <>
              <div className={cn('flex items-center gap-2 rounded-md border px-3 py-2 text-xs font-medium', level.cls)}>
                <Timer size={14} /> {level.label}
              </div>

              <div className="grid grid-cols-3 gap-3">
                {[
                  ['Complaints', String(data.totals.complaints)],
                  ['Reported loss', data.totals.amount ? `₹${data.totals.amount.toLocaleString('en-IN')}` : '—'],
                  ['Districts', String(data.totals.districts.length)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-md border border-border-subtle bg-bg-primary p-3 text-center">
                    <p className="text-2xs text-text-muted">{label}</p>
                    <p className="text-lg font-bold tabular-nums text-text-primary">{value}</p>
                  </div>
                ))}
              </div>

              <section>
                <h3 className="mb-1.5 text-2xs font-semibold uppercase tracking-wider text-text-secondary">Complaints cited</h3>
                <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
                  {data.complaints.map((c) => (
                    <li key={c.crime_id} className="flex items-center gap-3 px-3 py-2 text-xs">
                      <span className="font-mono text-text-primary">{c.case_number ?? c.crime_id.slice(0, 8)}</span>
                      <span className="text-text-muted">{formatDate(c.occurred_at, 'dd MMM yyyy')} · {c.district ?? '—'} · {crimeTypeLabel(c.crime_type)}</span>
                      <span className="ml-auto tabular-nums text-text-primary">{c.amount ? `₹${c.amount.toLocaleString('en-IN')}` : ''}</span>
                      <Link to={`/cases/${c.crime_id}`} onClick={onClose} className="text-text-muted hover:text-accent-blue" aria-label={`Open ${c.case_number}`}>
                        <ArrowUpRight size={13} />
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>

              <section>
                <label htmlFor="freeze-draft" className="mb-1.5 block text-2xs font-semibold uppercase tracking-wider text-text-secondary">
                  Draft (edit before sending)
                </label>
                <textarea
                  id="freeze-draft"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={14}
                  className="input font-mono text-xs leading-relaxed"
                />
              </section>

              <p className="flex items-start gap-1.5 text-2xs leading-relaxed text-text-muted">
                <AlertTriangle size={12} className="mt-0.5 shrink-0 text-severity-medium" />
                Nothing is sent from CrimeAI. The officer checks the identifier against the FIRs, confirms the legal provision, and sends the request through the official channel. Opening this draft is recorded in the audit log.
              </p>
            </>
          )}
        </div>

        {data && (
          <footer className="flex justify-end gap-2 border-t border-border-subtle px-5 py-3">
            <button type="button" onClick={print} className="btn-secondary text-xs"><Printer size={13} /> Print</button>
            <button type="button" onClick={copy} className="btn-primary text-xs"><Copy size={13} /> Copy request</button>
          </footer>
        )}
      </div>
    </div>
  )
}
