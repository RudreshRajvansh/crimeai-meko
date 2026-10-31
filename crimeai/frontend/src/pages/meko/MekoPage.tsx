import { Fragment, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrainCircuit, Database, FileText, Loader2, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { getErrorMessage, mekoApi } from '@/services'
import { useAuthStore } from '@/store/auth'
import { CallChips, Tokens } from '@/components/fir/MekoPanel'
import { cn } from '@/utils'
import type { MekoCall, MekoDatapack, MekoMemoryItem } from '@/types/meko'

const DEMO_FIRS = [
  {
    title: 'Courier customs fraud (Hinglish)',
    text: 'Shikayatkarta (M, 52) ko 90000 11223 se call aaya. Caller ne bola ki uska parcel customs mein ruka hai aur release ke liye Rs 4,999 customs fee UPI ID parcelfee.clear@okdemo pe bhejni hogi. Usne GPay se payment kar diya. Baad mein shak hua to usne bank ki WhatsApp customer care 90000 55555 pe account freeze karwaya.',
    expect: 'Delhi has never seen these numbers; Gurugram and Noida have. The customer-care number also matches two unrelated KYC cases until an officer excludes it.',
  },
  {
    title: 'Same ring, new SIM and UPI',
    text: 'Complainant (F, 29) received a WhatsApp call from 90000 22334 claiming a FedEx parcel in her name was stuck at customs. She was told to pay Rs 5,999 as customs clearance to UPI ID customs.desk@okdemo. She paid, and messaged the bank\'s WhatsApp customer care 90000 55555 when the caller asked for more.',
    expect: 'No shared identifier. Once the series is confirmed, Meko recalls it here by method, with the lead and note, and ignores the excluded number.',
  },
]

const AGENTS = ['dlp-intake', 'ggm-intake', 'noi-intake', 'linker', 'briefer', 'curator', 'setup']
const DATAPACKS = ['agency', 'ggm', 'noi', 'grid']
const EDGE: Record<string, string> = {
  write: 'rgb(var(--accent-blue))', recall: 'rgb(var(--accent-cyan))', promote: 'rgb(var(--accent-amber))', delete: 'rgb(var(--severity-high))',
}

function GridMap({ calls }: { calls: MekoCall[] }) {
  const edges = useMemo(() => {
    const out = new Map<string, { a: number; d: number; cat: string; n: number }>()
    for (const c of calls) {
      const a = AGENTS.indexOf(c.agent), d = DATAPACKS.indexOf(c.datapack ?? '')
      if (a < 0 || d < 0 || !(c.category in EDGE)) continue
      const key = `${a}|${d}|${c.category}`
      const e = out.get(key) ?? { a, d, cat: c.category, n: 0 }
      e.n += 1
      out.set(key, e)
    }
    return [...out.values()]
  }, [calls])
  const ay = (i: number) => 10 + i * 32
  const dy = (i: number) => 30 + i * 48
  const shift: Record<string, number> = { write: -3, recall: 0, promote: 3, delete: 6 }
  return (
    <svg viewBox="0 0 360 240" className="w-full max-w-md" role="img" aria-label="Which agent wrote to or recalled from which datapack">
      {edges.map((e) => (
        <path key={`${e.a}-${e.d}-${e.cat}`} fill="none" stroke={EDGE[e.cat]} strokeLinecap="round" opacity={0.75}
          strokeWidth={Math.min(1.2 + Math.log2(e.n + 1), 5)}
          d={`M120 ${ay(e.a) + 11 + shift[e.cat]} C 170 ${ay(e.a) + 11}, 190 ${dy(e.d) + 11}, 236 ${dy(e.d) + 11 + shift[e.cat]}`}>
          <title>{`${AGENTS[e.a]} → ${DATAPACKS[e.d]}: ${e.n} ${e.cat}`}</title>
        </path>
      ))}
      {AGENTS.map((a, i) => (
        <g key={a}><rect x="2" y={ay(i)} width="118" height="22" rx="5" className="fill-bg-tertiary stroke-border-default" />
          <text x="10" y={ay(i) + 15} className="fill-text-secondary font-mono" fontSize="11">{a}</text></g>
      ))}
      {DATAPACKS.map((d, i) => (
        <g key={d}><rect x="236" y={dy(i)} width="120" height="22" rx="5" className="fill-accent-purple/10 stroke-accent-purple/40" />
          <text x="244" y={dy(i) + 15} className="fill-accent-purple font-mono" fontSize="11">{d === 'grid' ? 'grid (shared)' : d === 'agency' ? 'agency (DLP)' : d}</text></g>
      ))}
    </svg>
  )
}

function MemoryRow({ m, datapack }: { m: MekoMemoryItem; datapack: MekoDatapack }) {
  const qc = useQueryClient()
  const canEdit = useAuthStore((s) => s.hasRole('police'))
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(m.text)
  const [gone, setGone] = useState(false)
  const save = useMutation({
    mutationFn: () => mekoApi.editMemory(datapack, m.id!, text),
    onSuccess: (r) => { if (!r.ok) throw new Error(r.error ?? 'Meko rejected the update'); toast.success('Corrected in Meko'); setEditing(false); qc.invalidateQueries({ queryKey: ['meko'] }) },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const forget = useMutation({
    mutationFn: () => mekoApi.forgetMemory(datapack, m.id!),
    onSuccess: (r) => { if (!r.ok) throw new Error(r.error ?? 'Meko rejected the delete'); toast.success('Forgotten in Meko'); setGone(true); qc.invalidateQueries({ queryKey: ['meko', 'calls'] }) },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  return (
    <li className={cn('rounded border border-border-subtle bg-bg-primary p-2 text-xs', gone && 'opacity-40')}>
      <div className="flex flex-wrap items-center gap-2 text-2xs text-text-muted">
        {m.parsed.kind !== 'other' && <span className="font-semibold text-text-primary">{m.parsed.kind}</span>}
        <span className="font-mono" title={m.id ?? ''}>{m.id ? `${m.id.slice(0, 10)}…` : 'no id'}</span>
        <span>{m.writer ? `written by ${m.writer}` : 'extracted by Meko or written elsewhere'}</span>
        {m.local_status && m.local_status !== 'active' && <span className="text-accent-amber">{m.local_status}</span>}
        {canEdit && m.id && !gone && (
          <span className="ml-auto flex gap-1">
            <button type="button" className="btn-ghost px-1.5 py-0.5 text-2xs" onClick={() => setEditing((v) => !v)}><Pencil size={11} /> Correct</button>
            <button type="button" className="btn-ghost px-1.5 py-0.5 text-2xs text-severity-high"
              onClick={() => { if (confirm('Forget this memory in Meko? Agents will no longer recall it.')) forget.mutate() }}>
              {forget.isPending ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />} Forget
            </button>
          </span>
        )}
      </div>
      <p className={cn('mt-1 text-text-primary', gone && 'line-through')}><Tokens text={m.text} /></p>
      {editing && (
        <div className="mt-2 space-y-1">
          <textarea className="input min-h-[70px] text-xs" value={text} onChange={(e) => setText(e.target.value)} />
          <div className="flex items-center gap-2">
            <button type="button" className="btn-primary py-1 text-2xs" disabled={save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? <Loader2 size={11} className="animate-spin" /> : 'Save to Meko'}
            </button>
            <span className="text-2xs text-text-muted">Personal identifiers are redacted before the text is sent.</span>
          </div>
        </div>
      )}
    </li>
  )
}

export default function MekoPage() {
  const navigate = useNavigate()
  const [datapack, setDatapack] = useState<MekoDatapack>('grid')
  const [promoted, setPromoted] = useState(false)
  const [openCall, setOpenCall] = useState<string | null>(null)
  const status = useQuery({ queryKey: ['meko', 'status'], queryFn: mekoApi.status, refetchInterval: 5000 })
  const calls = useQuery({ queryKey: ['meko', 'calls'], queryFn: () => mekoApi.calls(150), refetchInterval: 4000 })
  const memories = useQuery({
    queryKey: ['meko', 'memories', datapack, promoted],
    queryFn: () => mekoApi.memories(datapack, promoted),
    enabled: !!status.data?.ready,
  })
  const recent = useMemo(() => {
    const since = Date.now() - 15 * 60_000
    return (calls.data ?? []).filter((c) => c.ts && new Date(c.ts).getTime() >= since)
  }, [calls.data])
  const s = status.data

  return (
    <div className="space-y-4 p-3 sm:p-5 animate-fade-in">
      <div className="card flex flex-wrap items-center gap-3 p-4">
        <BrainCircuit className="text-accent-purple" size={20} />
        <div>
          <p className="text-sm font-semibold text-text-primary">Meko shared memory</p>
          <p className="text-2xs text-text-muted">{s ? `${s.agency_name} on the grid · ${s.mcp_url}` : 'Loading…'}</p>
        </div>
        <span className={cn('rounded-full px-2.5 py-1 text-2xs font-semibold',
          s?.ready ? 'bg-severity-low/15 text-severity-low' : 'bg-severity-high/15 text-severity-high')}>
          {s?.ready ? 'Connected · datapacks ready' : s?.enabled ? 'Datapacks not set up (run scripts/meko_setup.py)' : 'Off (MEKO_API_KEY not set)'}
        </span>
        <div className="ml-auto flex flex-wrap gap-2">
          {s && (['write', 'recall', 'promote', 'delete', 'errors', 'total'] as const).map((k) => (
            <span key={k} className="rounded border border-border-subtle bg-bg-tertiary px-2 py-1 text-2xs text-text-secondary">
              <b className="mr-1 text-sm text-text-primary">{s.stats[k] ?? 0}</b>{k === 'total' ? 'calls' : k}
            </span>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="card p-4">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Database size={15} className="text-accent-purple" />
            <h3 className="text-sm font-semibold text-text-primary">What Meko holds</h3>
            <div className="ml-2 inline-flex overflow-hidden rounded border border-border-default">
              {(['grid', 'agency'] as const).map((d) => (
                <button key={d} type="button" onClick={() => setDatapack(d)}
                  className={cn('px-3 py-1 text-2xs', datapack === d ? 'bg-accent-purple/15 text-accent-purple' : 'text-text-muted')}>
                  {d === 'grid' ? 'Grid (shared)' : `${s?.agency ?? 'Agency'} (private)`}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-1 text-2xs text-text-secondary">
              <input type="checkbox" checked={promoted} onChange={(e) => setPromoted(e.target.checked)} /> promoted only
            </label>
            <button type="button" className="btn-ghost ml-auto py-1 text-2xs" onClick={() => memories.refetch()}>
              <RefreshCw size={12} className={cn(memories.isFetching && 'animate-spin')} /> Refresh
            </button>
          </div>
          <p className="mb-2 text-2xs text-text-muted">Live <span className="font-mono">memory_get_all</span>, exactly as Meko returns it (about the 20 most recent).</p>
          {memories.isLoading && <p className="text-xs text-text-muted"><Loader2 size={12} className="mr-1 inline animate-spin" />Asking Meko…</p>}
          {memories.error && <p className="text-xs text-severity-high">{getErrorMessage(memories.error)}</p>}
          {memories.data && (
            <ul className="space-y-1.5">
              {memories.data.items.length === 0 && <li className="text-xs text-text-muted">Empty.</li>}
              {memories.data.items.map((m, i) => <MemoryRow key={m.id ?? i} m={m} datapack={datapack} />)}
            </ul>
          )}
        </div>

        <div className="space-y-4">
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-text-primary">Agents and datapacks · last 15 min</h3>
            <GridMap calls={recent} />
            <p className="text-2xs text-text-muted">
              <span className="text-accent-blue">write</span> · <span className="text-accent-cyan">recall</span> ·{' '}
              <span className="text-accent-amber">promote</span> · <span className="text-severity-high">forget</span>
            </p>
          </div>
          <div className="card p-4">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-text-primary"><FileText size={14} /> Demo FIRs</h3>
            {DEMO_FIRS.map((d) => (
              <div key={d.title} className="mb-2 rounded border border-border-subtle bg-bg-primary p-2">
                <p className="text-xs font-semibold text-text-primary">{d.title}</p>
                <p className="mt-0.5 text-2xs text-text-muted">{d.expect}</p>
                <button type="button" className="btn-secondary mt-1.5 py-1 text-2xs" onClick={() => navigate('/fir', { state: { text: d.text } })}>
                  Scan on the FIR page
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card p-4">
        <h3 className="mb-2 text-sm font-semibold text-text-primary">Every Meko call this deployment made</h3>
        <p className="mb-2 text-2xs text-text-muted">Stored in YugabyteDB (meko_calls). Click a row for the exact arguments and response.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-2xs uppercase text-text-muted">
              <tr><th className="py-1 pr-2">Time</th><th className="pr-2">Agent</th><th className="pr-2">Tool</th><th className="pr-2">Datapack</th><th className="pr-2">Result</th><th>ms</th></tr>
            </thead>
            <tbody>
              {(calls.data ?? []).map((c) => (
                <Fragment key={c.id}>
                  <tr className="cursor-pointer border-t border-border-subtle hover:bg-bg-hover" onClick={() => setOpenCall(openCall === c.id ? null : c.id)}>
                    <td className="py-1 pr-2 text-text-muted">{c.ts ? new Date(c.ts).toLocaleTimeString() : ''}</td>
                    <td className="pr-2 font-mono text-2xs text-accent-purple">{c.agent}</td>
                    <td className="pr-2"><CallChips ids={[c.id]} calls={[c]} /></td>
                    <td className="pr-2 font-mono text-2xs">{c.datapack ?? ''}</td>
                    <td className={cn('pr-2', !c.ok && 'text-severity-high')}>{c.summary}</td>
                    <td className="font-mono text-2xs text-text-muted">{c.latency_ms}</td>
                  </tr>
                  {openCall === c.id && (
                    <tr><td colSpan={6}>
                      <pre className="my-1 max-h-72 overflow-auto rounded bg-bg-tertiary p-2 text-2xs">{JSON.stringify({ args: c.args, result: c.result }, null, 2)}</pre>
                    </td></tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
