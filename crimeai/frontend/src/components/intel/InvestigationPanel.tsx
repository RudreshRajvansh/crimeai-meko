import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, BrainCircuit, CalendarClock, CheckCircle2, CircleDashed, FilePlus2, FileText, HelpCircle, Loader2,
  SearchCheck, Sparkles, Trash2, XCircle,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { getErrorMessage } from '@/services'
import { DOCUMENT_TYPES, investigationApi } from '@/services/investigation'
import { useAuthStore } from '@/store/auth'
import { cn, formatDate } from '@/utils'
import { Tokens } from '@/components/fir/MekoPanel'
import CustodyPanel from './CustodyPanel'
import type { CaseDocument, Finding, GeminiNote, GeminiReview, ReviewStatus, TimelineEvent } from '@/types/investigation'

const STATUS: Record<ReviewStatus, { label: string; className: string }> = {
  open: { label: 'Open', className: 'bg-bg-tertiary text-text-secondary' },
  accepted: { label: 'Accepted', className: 'bg-severity-low/15 text-severity-low' },
  rejected: { label: 'Rejected', className: 'bg-text-muted/15 text-text-muted' },
  needs_investigation: { label: 'Needs investigation', className: 'bg-severity-medium/15 text-severity-medium' },
}

const EVENT_DOT: Record<TimelineEvent['kind'], string> = {
  incident: 'bg-severity-high',
  document: 'bg-accent-blue',
  mention: 'bg-text-muted',
  evidence: 'bg-accent-cyan',
  custody: 'bg-accent-amber',
}

/**
 * Investigation intelligence: the case's documents read together. Contradictions and gaps are leads with their
 * sources quoted; an officer accepts, rejects or sends each for further investigation. Accepted findings become
 * approved context in Meko, which agents recall on later cases.
 */
export default function InvestigationPanel({ crimeId }: { crimeId: string }) {
  const [mekoOn, setMekoOn] = useState(true)
  const canAct = useAuthStore((s) => s.hasRole('police'))
  // The agents' analysis comes straight from YugabyteDB; Meko's approved context loads beside it, so the case
  // never waits on Meko.
  const view = useQuery({ queryKey: ['investigation', crimeId], queryFn: () => investigationApi.view(crimeId, false) })
  const approved = useQuery({ queryKey: ['investigation', crimeId, 'meko'], queryFn: () => investigationApi.approved(crimeId), enabled: mekoOn })
  const gemini = useMutation({ mutationFn: () => investigationApi.gemini(crimeId), onError: (err) => toast.error(getErrorMessage(err)) })

  if (view.isLoading) {
    return <section className="card p-5 text-xs text-text-muted"><Loader2 size={13} className="mr-1 inline animate-spin" />Agents are reading the case documents…</section>
  }
  if (view.error || !view.data) {
    return <section className="card p-5 text-xs text-severity-high">{getErrorMessage(view.error)}</section>
  }
  const data = view.data
  const contradictions = data.findings.filter((f) => f.kind === 'contradiction')
  const gaps = data.findings.filter((f) => f.kind === 'gap')
  const notes = gemini.data?.findings ?? {}

  return (
    <section className="card space-y-4 p-5">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
            <SearchCheck size={15} className="text-accent-purple" /> Investigation intelligence
          </h2>
          <p className="mt-0.5 text-2xs text-text-muted">
            {data.documents.length} documents read together. Every lead cites its source; officers decide.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-secondary py-1 text-2xs" disabled={gemini.isPending || data.findings.length === 0}
            onClick={() => gemini.mutate()} title="Identifiers are masked before anything is sent">
            {gemini.isPending ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} className="text-accent-blue" />}
            {gemini.data ? 'Ask Gemini again' : 'Explain with Gemini'}
          </button>
          <button type="button" role="switch" aria-checked={mekoOn} onClick={() => setMekoOn((v) => !v)}
            className={cn('inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-2xs font-semibold',
              mekoOn ? 'border-accent-purple/50 bg-accent-purple/15 text-accent-purple' : 'border-border-default text-text-muted')}>
            <span className={cn('h-2 w-2 rounded-full', mekoOn ? 'bg-accent-purple' : 'bg-text-muted')} /> Meko {mekoOn ? 'ON' : 'OFF'}
          </button>
        </div>
      </header>

      <ol className="grid gap-2 sm:grid-cols-3">
        {data.agents.map((a, i) => (
          <li key={a.name} className="rounded border border-border-subtle bg-bg-primary px-2.5 py-2">
            <p className="text-2xs font-semibold text-text-primary"><span className="mr-1 text-text-muted">{i + 1}.</span>{a.name} agent</p>
            <p className="mt-0.5 text-2xs text-text-secondary">{a.summary}</p>
          </li>
        ))}
      </ol>

      <div>
        <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-text-primary">
          <AlertTriangle size={13} className="text-severity-medium" /> Contradictions ({contradictions.length})
        </h3>
        {contradictions.length === 0 && (
          <p className="text-xs text-text-muted">The documents agree on time, date, vehicle number and amount
            (times within {data.time_tolerance_min} minutes count as the same).</p>
        )}
        <div className="space-y-2">
          {contradictions.map((f) => <FindingCard key={f.fingerprint} crimeId={crimeId} finding={f} canAct={canAct} note={notes[f.fingerprint]} />)}
        </div>
      </div>

      {gemini.data && <GeminiPlan review={gemini.data} />}

      <Timeline events={data.timeline} gaps={gaps} crimeId={crimeId} canAct={canAct} gapDays={data.gap_days} notes={notes} />

      {mekoOn && <ApprovedContext data={approved.data} />}

      <Documents crimeId={crimeId} documents={data.documents} canAct={canAct} />

      <CustodyPanel crimeId={crimeId} canAct={canAct} />
    </section>
  )
}

function FindingCard({ crimeId, finding, canAct, note: gemini }: {
  crimeId: string; finding: Finding; canAct: boolean; note?: GeminiNote
}) {
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const review = useMutation({
    mutationFn: (decision: ReviewStatus) => investigationApi.review(crimeId, finding.fingerprint, decision, note),
    onSuccess: (r) => {
      const shared = r.meko.status === 'ok' ? ' and saved to Meko as approved context' : ''
      toast.success(`${STATUS[r.status].label}${shared}`)
      qc.invalidateQueries({ queryKey: ['investigation', crimeId] })
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const status = STATUS[finding.status]
  return (
    <article className={cn('rounded border p-3', finding.kind === 'gap' ? 'border-accent-blue/40 bg-accent-blue/[0.04]'
      : 'border-severity-medium/50 bg-severity-medium/[0.05]')}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold text-text-primary">{finding.title}</p>
        <span className={cn('ml-auto rounded px-1.5 py-0.5 text-2xs font-semibold', status.className)}>{status.label}</span>
      </div>
      <p className="mt-0.5 text-2xs text-text-secondary">Difference: <b className="text-text-primary">{finding.difference}</b></p>
      {finding.claims.length > 0 && (
        <table className="mt-2 w-full text-left text-2xs">
          <thead className="text-text-muted"><tr><th className="pr-2 font-medium">Document</th><th className="pr-2 font-medium">Says</th><th className="font-medium">Where</th></tr></thead>
          <tbody>
            {finding.claims.map((c) => (
              <tr key={`${c.doc_id}-${c.value}`} className="border-t border-border-subtle align-top">
                <td className="py-1 pr-2 text-text-primary">{c.doc_title}</td>
                <td className="py-1 pr-2 font-mono font-semibold text-text-primary">{c.display}</td>
                <td className="py-1 italic text-text-secondary">“{c.quote}”</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="mt-2 text-2xs text-text-secondary"><span className="font-semibold text-text-primary">Suggested action:</span> {finding.suggested_action}</p>
      {gemini && (
        <div className="mt-2 rounded border border-accent-blue/30 bg-accent-blue/[0.05] p-2 text-2xs text-text-secondary">
          <p className="mb-0.5 flex items-center gap-1 font-semibold text-accent-blue"><Sparkles size={10} /> Gemini (a draft, not a finding)</p>
          <p className="text-text-primary">{gemini.explanation}</p>
          {gemini.likely_cause && <p><span className="font-semibold">Likely cause:</span> {gemini.likely_cause}</p>}
          {gemini.verify_with && <p><span className="font-semibold">Verify with:</span> {gemini.verify_with}</p>}
          {gemini.next_step && <p><span className="font-semibold">Next step:</span> {gemini.next_step}</p>}
        </div>
      )}
      {finding.review_note && <p className="mt-1 text-2xs text-text-muted">Officer's note: {finding.review_note}</p>}
      {canAct && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <input className="input min-w-[180px] flex-1 py-1 text-2xs" placeholder="Note (optional)" value={note} maxLength={1000}
            onChange={(e) => setNote(e.target.value)} />
          <button type="button" className="btn-secondary py-1 text-2xs text-severity-low" disabled={review.isPending} onClick={() => review.mutate('accepted')}>
            <CheckCircle2 size={11} /> Accept
          </button>
          <button type="button" className="btn-secondary py-1 text-2xs" disabled={review.isPending} onClick={() => review.mutate('rejected')}>
            <XCircle size={11} /> Reject
          </button>
          <button type="button" className="btn-secondary py-1 text-2xs text-severity-medium" disabled={review.isPending}
            onClick={() => review.mutate('needs_investigation')}>
            <HelpCircle size={11} /> Needs investigation
          </button>
          {review.isPending && <Loader2 size={12} className="animate-spin text-text-muted" />}
        </div>
      )}
    </article>
  )
}

function Timeline({ events, gaps, crimeId, canAct, gapDays, notes }: {
  events: TimelineEvent[]; gaps: Finding[]; crimeId: string; canAct: boolean; gapDays: number; notes: Record<string, GeminiNote>
}) {
  const gapAfter = new Map(gaps.map((g) => [g.from, g]))
  const shownGaps = new Set<string>()
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold text-text-primary">
        <CalendarClock size={13} className="text-accent-blue" /> Timeline ({events.length} events, {gaps.length} gap{gaps.length === 1 ? '' : 's'} of {gapDays}+ days)
      </h3>
      <ol className="relative space-y-1.5 border-l border-border-default pl-4">
        {events.map((e, i) => {
          const day = e.at.slice(0, 10)
          const isLastOfDay = events[i + 1]?.at.slice(0, 10) !== day
          const gap = isLastOfDay && !shownGaps.has(day) ? gapAfter.get(day) : undefined
          if (gap) shownGaps.add(day)
          return (
            <li key={`${e.at}-${i}`}>
              <span className={cn('absolute -left-[4.5px] mt-1.5 h-2 w-2 rounded-full', EVENT_DOT[e.kind])} />
              <p className="text-2xs text-text-muted">{formatDate(e.at, e.date_only ? 'dd MMM yyyy' : 'dd MMM yyyy, HH:mm')}</p>
              <p className="text-xs text-text-primary">{e.label} <span className="text-2xs text-text-muted">· {e.source}</span></p>
              {e.quote && <p className="text-2xs italic text-text-secondary">“{e.quote}”</p>}
              {gap && <div className="my-2"><FindingCard crimeId={crimeId} finding={gap} canAct={canAct} note={notes[gap.fingerprint]} /></div>}
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function GeminiPlan({ review }: { review: GeminiReview }) {
  const masked = Object.values(review.redactions).reduce((a, b) => a + b, 0)
  return (
    <div className="rounded border border-accent-blue/40 bg-accent-blue/[0.04] p-3">
      <h3 className="flex items-center gap-2 text-xs font-semibold text-text-primary">
        <Sparkles size={13} className="text-accent-blue" /> Draft investigation plan · Gemini
      </h3>
      <p className="mt-0.5 text-2xs text-text-muted">
        {review.model} · {review.chars_sent.toLocaleString()} characters sent, {masked} identifier{masked === 1 ? '' : 's'} masked
        first. A draft for the investigating officer.
      </p>
      {review.plan.length > 0 && (
        <ol className="mt-2 list-decimal space-y-0.5 pl-4 text-xs text-text-primary">
          {review.plan.map((step) => <li key={step}>{step}</li>)}
        </ol>
      )}
      {review.missing_documents.length > 0 && (
        <p className="mt-2 text-2xs text-text-secondary">
          <span className="font-semibold text-text-primary">Missing from the file:</span> {review.missing_documents.join('; ')}
        </p>
      )}
    </div>
  )
}

function ApprovedContext({ data }: { data?: { status: string; error?: string; items: { ref: string; id: string | null; text: string }[] } }) {
  return (
    <div className="rounded border border-accent-purple/40 bg-accent-purple/[0.04] p-3">
      <h3 className="flex items-center gap-2 text-xs font-semibold text-text-primary">
        <BrainCircuit size={13} className="text-accent-purple" /> Approved context from earlier investigations (Meko)
      </h3>
      {!data && <p className="mt-1 text-2xs text-text-muted"><Loader2 size={11} className="mr-1 inline animate-spin" />Agents are recalling approved findings from Meko…</p>}
      {data && data.status !== 'ok' && <p className="mt-1 text-2xs text-text-muted">{data.error ?? 'Meko is off.'}</p>}
      {data?.status === 'ok' && data.items.length === 0 && (
        <p className="mt-1 text-2xs text-text-muted">No officer-approved finding from another case mentions this case's vehicles.</p>
      )}
      <ul className="mt-1 space-y-1">
        {data?.items.map((m) => (
          <li key={m.ref} className="rounded bg-bg-tertiary px-2 py-1 text-2xs text-text-primary">
            <span className="mr-1 font-mono text-accent-cyan">{m.ref}</span><Tokens text={m.text} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function Documents({ crimeId, documents, canAct }: { crimeId: string; documents: CaseDocument[]; canAct: boolean }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ doc_type: 'witness_statement', title: '', recorded_at: '', text: '' })
  const add = useMutation({
    mutationFn: () => investigationApi.addDocument(crimeId, {
      doc_type: form.doc_type, title: form.title, text: form.text,
      recorded_at: form.recorded_at ? new Date(form.recorded_at).toISOString() : undefined,
    }),
    onSuccess: () => {
      toast.success('Document added; the agents have re-read the case')
      setForm({ doc_type: 'witness_statement', title: '', recorded_at: '', text: '' })
      setAdding(false)
      qc.invalidateQueries({ queryKey: ['investigation', crimeId] })
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const remove = useMutation({
    mutationFn: (id: string) => investigationApi.removeDocument(crimeId, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['investigation', crimeId] }),
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <h3 className="flex items-center gap-2 text-xs font-semibold text-text-primary"><FileText size={13} /> Documents ({documents.length})</h3>
        {canAct && (
          <button type="button" className="btn-ghost ml-auto py-0.5 text-2xs" onClick={() => setAdding((v) => !v)}>
            <FilePlus2 size={12} /> Add document
          </button>
        )}
      </div>
      {adding && (
        <div className="mb-2 space-y-2 rounded border border-border-subtle bg-bg-primary p-2.5">
          <div className="grid gap-2 sm:grid-cols-3">
            <select className="input py-1 text-xs" value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })}>
              {Object.entries(DOCUMENT_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input className="input py-1 text-xs" placeholder="Title, e.g. Statement of PW-2" value={form.title} maxLength={200}
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <input className="input py-1 text-xs" type="datetime-local" value={form.recorded_at} onChange={(e) => setForm({ ...form, recorded_at: e.target.value })} />
          </div>
          <textarea className="input min-h-[80px] text-xs" placeholder="Text of the statement, report or memo (any language). Phone, Aadhaar, bank and UPI numbers are redacted before storage."
            value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} />
          <button type="button" className="btn-primary py-1 text-xs" disabled={add.isPending || form.title.length < 3 || form.text.length < 10} onClick={() => add.mutate()}>
            {add.isPending ? <Loader2 size={12} className="animate-spin" /> : <FilePlus2 size={12} />} Add and re-analyse
          </button>
        </div>
      )}
      <ul className="space-y-1">
        {documents.map((d) => (
          <li key={d.id} className="rounded border border-border-subtle bg-bg-primary px-2.5 py-1.5">
            <div className="flex flex-wrap items-center gap-2 text-2xs">
              <span className="rounded bg-bg-tertiary px-1.5 py-0.5 font-semibold text-text-secondary">{d.type_label}</span>
              <button type="button" className="text-left text-xs text-text-primary hover:underline" onClick={() => setOpen(open === d.id ? null : d.id)}>{d.title}</button>
              {d.recorded_at && <span className="text-text-muted">{formatDate(d.recorded_at, 'dd MMM yyyy, HH:mm')}</span>}
              {d.language && <span className="text-text-muted">{d.language}</span>}
              {canAct && d.removable && (
                <button type="button" className="ml-auto text-text-muted hover:text-severity-high" title="Remove document"
                  onClick={() => { if (confirm('Remove this document from the case?')) remove.mutate(d.id) }}>
                  <Trash2 size={12} />
                </button>
              )}
            </div>
            {open === d.id && <p className="mt-1 whitespace-pre-wrap text-2xs text-text-secondary">{d.text}</p>}
          </li>
        ))}
        {documents.length === 0 && <li className="flex items-center gap-1 text-2xs text-text-muted"><CircleDashed size={11} /> No documents yet.</li>}
      </ul>
    </div>
  )
}
