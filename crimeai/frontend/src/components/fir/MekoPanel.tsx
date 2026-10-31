import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { BookOpen, BrainCircuit, CheckCircle2, Link2, Loader2, ShieldOff, Sparkles } from 'lucide-react'
import toast from 'react-hot-toast'
import { getErrorMessage, mekoApi } from '@/services'
import { cn } from '@/utils'
import type { MekoCall, MekoIdentifier, MekoRecall, MekoRecalled } from '@/types/meko'

const TOKEN = /\b(?:PH|UPI|AC|VH)-[0-9A-F]{10}\b/g

const CATEGORY_STYLE: Record<string, string> = {
  write: 'bg-accent-blue/10 text-accent-blue',
  recall: 'bg-accent-cyan/10 text-accent-cyan',
  promote: 'bg-accent-amber/15 text-accent-amber',
  delete: 'bg-severity-high/10 text-severity-high',
  session: 'bg-bg-tertiary text-text-muted',
  admin: 'bg-bg-tertiary text-text-muted',
}

export function Tokens({ text, labels }: { text: string; labels?: Record<string, string> }) {
  const parts: ReactNode[] = []
  let last = 0
  for (const m of text.matchAll(TOKEN)) {
    if ((m.index ?? 0) > last) parts.push(text.slice(last, m.index))
    const label = labels?.[m[0]]
    parts.push(
      <span key={`${m.index}-${m[0]}`} className="rounded bg-accent-purple/10 px-1 font-mono text-[11px] text-accent-purple"
        title={label ? `${label} (keyed fingerprint; the raw value never leaves this agency)` : 'Keyed fingerprint from another agency'}>
        {label ?? m[0]}
      </span>,
    )
    last = (m.index ?? 0) + m[0].length
  }
  if (last < text.length) parts.push(text.slice(last))
  return <>{parts}</>
}

export function CallChips({ ids, calls }: { ids: (string | null)[]; calls: MekoCall[] }) {
  const byId = new Map(calls.map((c) => [c.id, c]))
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((id) => {
        const c = id ? byId.get(id) : undefined
        if (!c) return null
        return (
          <span key={c.id} title={c.summary}
            className={cn('rounded px-1.5 py-0.5 font-mono text-2xs', CATEGORY_STYLE[c.category], !c.ok && 'ring-1 ring-severity-high')}>
            {c.tool}{c.datapack ? ` · ${c.datapack}` : ''} · {c.ok ? `${c.latency_ms}ms` : 'error'}
          </span>
        )
      })}
    </span>
  )
}

function Ref({ id }: { id: string }) {
  return (
    <a href={`#meko-${id}`} className={cn('rounded px-1 font-mono text-2xs',
      id.startsWith('K') ? 'bg-accent-blue/10 text-accent-blue' : 'bg-accent-cyan/10 text-accent-cyan')}
      title="Item recalled from Meko">{id}</a>
  )
}

/**
 * Shared memory between agencies, recalled before anything is linked. With Meko off, only this agency's records
 * (the panel above) are checked; with Meko on, other agencies' sightings and officers' promoted decisions join in.
 */
export default function MekoPanel({ text, firNumber }: { text: string | null; firNumber: string }) {
  const [on, setOn] = useState(true)
  const [result, setResult] = useState<MekoRecall | null>(null)
  const status = useQuery({ queryKey: ['meko', 'status'], queryFn: mekoApi.status, staleTime: 30_000 })
  // Matches the case number CrimeAI gives a case opened from this FIR (FIR/<number>).
  const ownRef = firNumber.trim() && status.data ? `${status.data.agency}:FIR/${firNumber.trim()}` : null
  const recall = useMutation({
    mutationFn: (t: string) => mekoApi.recall(t),
    onSuccess: setResult,
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  useEffect(() => {
    setResult(null)
    if (on && text && text.trim().length >= 20) recall.mutate(text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, on])

  if (!text) return null
  const agency = status.data?.agency_name ?? 'this agency'

  return (
    <div className="rounded-md border border-accent-purple/40 bg-accent-purple/[0.04] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <BrainCircuit size={15} className="text-accent-purple" />
        <p className="text-sm font-semibold text-text-primary">Shared memory across agencies</p>
        <span className="text-2xs text-text-muted">Meko</span>
        <button type="button" onClick={() => setOn((v) => !v)} role="switch" aria-checked={on}
          className={cn('ml-auto inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-2xs font-semibold',
            on ? 'border-accent-purple/50 bg-accent-purple/15 text-accent-purple' : 'border-border-default text-text-muted')}>
          <span className={cn('h-2 w-2 rounded-full', on ? 'bg-accent-purple' : 'bg-text-muted')} />
          Meko {on ? 'ON' : 'OFF'}
        </button>
      </div>

      {!on && (
        <p className="mt-2 text-xs text-text-muted">
          Meko is off: only {agency}'s own records were checked (above). Other agencies' cases, confirmed series and
          officers' exclusions are invisible.
        </p>
      )}
      {on && recall.isPending && (
        <p className="mt-2 flex items-center gap-2 text-xs text-accent-purple">
          <Loader2 size={13} className="animate-spin" /> Agents are recalling the shared grid before linking anything…
        </p>
      )}
      {on && result && result.status !== 'ok' && (
        <p className={cn('mt-2 text-xs', result.status === 'error' ? 'text-severity-high' : 'text-text-muted')}>{result.error}</p>
      )}
      {on && result?.status === 'ok' && <RecallView result={result} ownRef={ownRef} onChanged={() => text && recall.mutate(text)} />}
    </div>
  )
}

function RecallView({ result, ownRef, onChanged }: { result: MekoRecall; ownRef: string | null; onChanged: () => void }) {
  const a = result.analysis!
  const labels = useMemo(() => Object.fromEntries(result.identifiers.map((i) => [i.token, `${i.noun} ${i.label}`])), [result])
  const nothing = !a.links.length && !a.series.length && !a.similar.length && !a.excluded.length
  const [showAll, setShowAll] = useState(false)
  const recalled = result.recalled ?? []

  return (
    <div className="mt-3 space-y-3">
      {a.series.map((s) => (
        <div key={s.series_id} className="rounded border border-accent-amber/50 bg-accent-amber/[0.07] p-2.5">
          <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-accent-amber">
            <Sparkles size={14} /> Confirmed series {s.series_id}
            <span className="text-2xs font-normal text-text-secondary">{s.confidence}{s.member ? ' · already a member' : ''}</span>
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            {s.refs.length > 0 && <>Cases: <span className="font-mono">{s.refs.join(', ')}</span>. </>}
            {s.lead && <>Lead: {s.lead}. </>}
            {s.note && <>Officer note: “{s.note}”. </>}
            {s.tokens.length > 0 && <>Shared: <Tokens text={s.tokens.join(' ')} labels={labels} />. </>}
            Evidence {s.evidence.map((e) => <Ref key={e} id={e} />)}
          </p>
          {!s.member && <AttachButton seriesId={s.series_id} ownRef={ownRef} tokens={s.tokens} onDone={onChanged} />}
        </div>
      ))}

      {a.links.length > 0 && (
        <div className="rounded border border-severity-high/50 bg-severity-high/[0.06] p-2.5">
          <p className="flex items-center gap-2 text-sm font-semibold text-severity-high">
            <Link2 size={14} /> Seen by other agencies: {a.links.length} case{a.links.length > 1 ? 's' : ''}
          </p>
          <ul className="mt-1.5 space-y-1">
            {a.links.map((l) => (
              <li key={l.ref} className="text-xs text-text-secondary">
                <span className="font-mono text-text-primary">{l.ref}</span>
                <span className="ml-1 rounded bg-bg-tertiary px-1.5 py-0.5 text-2xs">{l.agency_name}</span>
                {' '}shares <Tokens text={l.tokens.join(' ')} labels={labels} /> · {l.evidence.map((e) => <Ref key={e} id={e} />)}
              </li>
            ))}
          </ul>
          <SeriesDecision result={result} ownRef={ownRef} onDone={onChanged} />
        </div>
      )}

      {a.similar.length > 0 && (
        <div className="rounded border border-border-subtle bg-bg-primary p-2.5 text-xs text-text-secondary">
          <p className="font-semibold text-text-primary">Same method, no shared identifier</p>
          {a.similar.slice(0, 5).map((s) => (
            <p key={s.ref} className="mt-1"><span className="font-mono">{s.ref}</span> ({s.agency_name}): {s.mo_tags.join(', ')} · {s.evidence.map((e) => <Ref key={e} id={e} />)}</p>
          ))}
        </div>
      )}

      {a.excluded.length > 0 && (
        <div className="rounded border border-border-subtle bg-bg-primary p-2.5 text-xs text-text-secondary">
          {a.excluded.map((x) => (
            <p key={x.token}>
              <ShieldOff size={12} className="mr-1 inline align-[-2px]" />Not linking on <Tokens text={x.token} labels={labels} />:
              an officer recorded it is not a suspect's identifier <Ref id={x.ref} />
            </p>
          ))}
        </div>
      )}

      {nothing && (
        <p className="flex items-center gap-2 text-xs text-severity-low"><CheckCircle2 size={13} /> No other agency has seen these identifiers, and no promoted decision applies.</p>
      )}

      <details className="rounded border border-border-subtle bg-bg-primary p-2.5" open>
        <summary className="cursor-pointer text-xs font-semibold text-text-primary">Agent trace · {result.calls.length} Meko calls</summary>
        <ol className="mt-2 space-y-1.5">
          {(result.steps ?? []).map((s, i) => (
            <li key={i} className="grid grid-cols-[110px_1fr] gap-2 text-xs">
              <span className="font-mono text-2xs text-accent-purple">{s.agent}</span>
              <span className="text-text-secondary">{s.label}<span className="mt-1 block"><CallChips ids={s.calls} calls={result.calls} /></span>
                {s.errors.length > 0 && <span className="block text-severity-high">{s.errors.join('; ')}</span>}</span>
            </li>
          ))}
        </ol>
      </details>

      <div className="rounded border border-border-subtle bg-bg-primary p-2.5">
        <p className="text-xs font-semibold text-text-primary">What Meko returned ({recalled.length})</p>
        <p className="text-2xs text-text-muted">Everything above is computed from these items only. Purple chips are keyed fingerprints.</p>
        <ul className="mt-2 space-y-1.5">
          {(showAll ? recalled : recalled.slice(0, 6)).map((m) => <RecalledItem key={m.ref} m={m} labels={labels} />)}
        </ul>
        {recalled.length > 6 && (
          <button type="button" className="mt-1 text-2xs text-accent-blue hover:underline" onClick={() => setShowAll((v) => !v)}>
            {showAll ? 'Show fewer' : `Show all ${recalled.length}`}
          </button>
        )}
        {(result.kb ?? []).length > 0 && (
          <div className="mt-3">
            <p className="flex items-center gap-1 text-xs font-semibold text-text-primary"><BookOpen size={12} /> SOP passages (grid knowledge base)</p>
            {(result.kb ?? []).map((k) => (
              <p key={k.ref} id={`meko-${k.ref}`} className="mt-1 text-2xs text-text-secondary">
                <Ref id={k.ref} /> <span className="text-text-muted">{k.source}</span> {k.text.length > 300 ? `${k.text.slice(0, 300)}…` : k.text}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function RecalledItem({ m, labels }: { m: MekoRecalled; labels: Record<string, string> }) {
  return (
    <li id={`meko-${m.ref}`} className="rounded bg-bg-tertiary px-2 py-1.5 text-2xs text-text-secondary">
      <span className="mr-1 rounded bg-accent-cyan/10 px-1 font-mono text-accent-cyan">{m.ref}</span>
      <span className="mr-1 font-mono text-text-muted">{m.datapack}</span>
      {m.parsed.kind !== 'other' && <span className="mr-1 font-semibold text-text-primary">{m.parsed.kind}</span>}
      {typeof m.score === 'number' && <span className="mr-1 text-text-muted">score {m.score.toFixed(3)}</span>}
      <span className="mr-1 font-mono text-text-muted" title={m.id ?? ''}>{m.id ? `${m.id.slice(0, 8)}…` : 'no id'}</span>
      <span className="block mt-0.5 text-text-primary"><Tokens text={m.text} labels={labels} /></span>
    </li>
  )
}

function SeriesDecision({ result, ownRef, onDone }: { result: MekoRecall; ownRef: string | null; onDone: () => void }) {
  const a = result.analysis!
  const [lead, setLead] = useState('')
  const [note, setNote] = useState('')
  const confirm = useMutation({
    mutationFn: () => mekoApi.confirmSeries({
      own_ref: ownRef, refs: a.links.map((l) => l.ref), tokens: [...new Set(a.links.flatMap((l) => l.tokens))],
      mo_tags: result.mo_tags, lead, note,
    }),
    onSuccess: (d) => {
      toast.success(d.promote.ok ? `Series ${d.series_id} promoted: every agency now recalls it` : `Series ${d.series_id} stored; promotion failed`)
      onDone()
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  return (
    <div className="mt-2 space-y-2 border-t border-severity-high/20 pt-2">
      <p className="text-2xs text-text-muted">Agents only propose. If these are the same offenders, confirm it; the series is promoted to every agency on the grid.</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <input className="input py-1.5 text-xs" placeholder="Lead, e.g. Gurugram Cyber PS" value={lead} maxLength={120} onChange={(e) => setLead(e.target.value)} />
        <input className="input py-1.5 text-xs" placeholder="Note for every agency (optional)" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary py-1.5 text-xs" disabled={confirm.isPending} onClick={() => confirm.mutate()}>
          {confirm.isPending ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />} Confirm series and promote
        </button>
        {result.identifiers.filter((i) => a.links.some((l) => l.tokens.includes(i.token))).map((i) => (
          <ExcludeButton key={i.token} identifier={i} onDone={onDone} />
        ))}
      </div>
      {!ownRef && <p className="text-2xs text-text-muted">Enter the FIR number to include this case in the series.</p>}
    </div>
  )
}

function ExcludeButton({ identifier, onDone }: { identifier: MekoIdentifier; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('public bank customer-care number quoted by victims')
  const exclude = useMutation({
    mutationFn: () => mekoApi.exclude({ token: identifier.token, reason }),
    onSuccess: (d) => {
      toast.success(d.promote.ok ? `${identifier.noun} ${identifier.label} excluded on every agency's grid` : 'Exclusion stored; promotion failed')
      onDone()
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  if (!open) {
    return (
      <button type="button" className="btn-secondary py-1 text-2xs" onClick={() => setOpen(true)}
        title="Record that this identifier is not a suspect's (a public helpline, for example). Promoted to every agency.">
        <ShieldOff size={11} /> {identifier.label} is not a suspect's
      </button>
    )
  }
  return (
    <span className="flex flex-wrap items-center gap-1">
      <input className="input py-1 text-2xs" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} />
      <button type="button" className="btn-secondary py-1 text-2xs text-accent-amber" disabled={exclude.isPending} onClick={() => exclude.mutate()}>
        {exclude.isPending ? <Loader2 size={11} className="animate-spin" /> : 'Exclude everywhere'}
      </button>
    </span>
  )
}

function AttachButton({ seriesId, ownRef, tokens, onDone }: { seriesId: string; ownRef: string | null; tokens: string[]; onDone: () => void }) {
  const attach = useMutation({
    mutationFn: () => mekoApi.attach({ series_id: seriesId, own_ref: ownRef!, tokens }),
    onSuccess: () => { toast.success(`Attached to ${seriesId}; shared with every agency`); onDone() },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  return (
    <button type="button" className="btn-secondary mt-2 py-1 text-2xs text-accent-amber" disabled={!ownRef || attach.isPending}
      title={ownRef ? undefined : 'Enter the FIR number first'} onClick={() => attach.mutate()}>
      {attach.isPending ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} Attach this case to {seriesId}
    </button>
  )
}
