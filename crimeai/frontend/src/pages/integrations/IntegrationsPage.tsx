import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDownToLine, ArrowUpFromLine, FileUp, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { getErrorMessage } from '@/services/api'
import { integrationsApi } from '@/services/integrations'
import { alertsApi } from '@/services/alerts'
import { crimesApi } from '@/services/crimes'
import { intelApi } from '@/services/intel'
import { useAuthStore } from '@/store/auth'
import { cn } from '@/utils'
import type { Connector, ImportReport } from '@/types'

const W = 1000
const H = 640
const TOP = 92
const LAYERS = [
  { key: 'src', title: 'SOURCES', x: 115, color: '#3fb950' },
  { key: 'ing', title: 'INGEST', x: 365, color: '#39c5cf' },
  { key: 'int', title: 'INTELLIGENCE', x: 600, color: '#a371f7' },
  { key: 'out', title: 'ACTION', x: 828, color: '#58a6ff' },
] as const
type Layer = (typeof LAYERS)[number]['key']

const NODES: Array<{ id: string; label: string; layer: Layer }> = [
  { id: 'cctns', label: 'CCTNS', layer: 'src' },
  { id: 'ncrp', label: 'NCRP · 1930', layer: 'src' },
  { id: 'esakshya', label: 'e-Sakshya', layer: 'src' },
  { id: 'scan', label: 'FIR scans', layer: 'src' },
  { id: 'erss', label: 'Dial 112', layer: 'src' },
  { id: 'ecourts', label: 'e-Courts', layer: 'src' },
  { id: 'eprisons', label: 'e-Prisons', layer: 'src' },
  { id: 'nafis', label: 'Face / NAFIS', layer: 'src' },
  { id: 'parse', label: 'Schema mapper', layer: 'ing' },
  { id: 'ocr', label: 'OCR · HTR', layer: 'ing' },
  { id: 'nlp', label: 'NLP · 13 langs', layer: 'ing' },
  { id: 'gemini', label: 'AI case brief', layer: 'ing' },
  { id: 'bns', label: 'IPC→BNS', layer: 'ing' },
  { id: 'geo', label: 'Geo-coder', layer: 'ing' },
  { id: 'hmac', label: 'HMAC vault', layer: 'ing' },
  { id: 'graph', label: 'Entity graph', layer: 'int' },
  { id: 'net', label: 'Network finder', layer: 'int' },
  { id: 'series', label: 'Series detect', layer: 'int' },
  { id: 'embed', label: 'Semantic e5', layer: 'int' },
  { id: 'risk', label: 'Risk model', layer: 'int' },
  { id: 'near', label: 'Near-repeat', layer: 'int' },
  { id: 'custody', label: 'Custody clock', layer: 'int' },
  { id: 'alerts', label: 'Link alerts', layer: 'out' },
  { id: 'freeze', label: 'Freeze packet', layer: 'out' },
  { id: 'dossier', label: 'Case dossier', layer: 'out' },
  { id: 'enrich', label: 'CCTNS enrich', layer: 'out' },
  { id: 'patrol', label: 'Patrol plan', layer: 'out' },
  { id: 'remand', label: 'Remand alerts', layer: 'out' },
  { id: 's105', label: 's.105 check', layer: 'out' },
]

const EDGES: Array<[string, string]> = [
  ['cctns', 'parse'], ['cctns', 'nlp'], ['cctns', 'geo'],
  ['ncrp', 'parse'], ['ncrp', 'hmac'], ['ncrp', 'geo'],
  ['esakshya', 'parse'], ['scan', 'ocr'], ['cctns', 'gemini'], ['scan', 'gemini'],
  ['erss', 'geo'], ['ecourts', 'parse'], ['eprisons', 'parse'],
  ['parse', 'graph'], ['parse', 'custody'], ['parse', 'risk'],
  ['ocr', 'nlp'], ['nlp', 'bns'], ['nlp', 'embed'], ['nlp', 'graph'],
  ['bns', 'custody'], ['bns', 'series'],
  ['geo', 'risk'], ['geo', 'near'], ['geo', 'series'], ['hmac', 'graph'],
  ['graph', 'net'], ['graph', 'alerts'], ['graph', 'dossier'], ['graph', 'enrich'],
  ['net', 'alerts'], ['net', 'freeze'], ['series', 'alerts'], ['series', 'enrich'],
  ['embed', 'series'], ['embed', 'dossier'], ['risk', 'patrol'], ['near', 'patrol'], ['near', 'alerts'],
  ['custody', 'remand'], ['custody', 'dossier'], ['parse', 's105'], ['gemini', 'dossier'],
]

const STATUS_COLOR = { planned: '#d29922', excluded: '#6e7681' } as const
const IMPORTS: Record<string, { run: (f: File) => Promise<ImportReport>; sample: string; role: 'police' | 'admin' }> = {
  ncrp: { run: integrationsApi.importNcrp, sample: '/samples/ncrp_complaints.csv', role: 'police' },
  cctns: { run: integrationsApi.importCctns, sample: '/samples/cctns_fir_export.json', role: 'admin' },
}

function layout() {
  const pos: Record<string, { x: number; y: number; layer: Layer }> = {}
  for (const L of LAYERS) {
    const col = NODES.filter((n) => n.layer === L.key)
    const span = H - TOP - 40
    col.forEach((n, i) => {
      pos[n.id] = { x: L.x, y: TOP + (span / (col.length - 1)) * i, layer: L.key }
    })
  }
  return pos
}

function curve(a: { x: number; y: number }, b: { x: number; y: number }) {
  const dx = (b.x - a.x) * 0.5
  return `M${a.x},${a.y} C${a.x + dx},${a.y} ${b.x - dx},${b.y} ${b.x},${b.y}`
}

/** Every path from India's systems of record through CrimeAI's models to an officer's action. */
export default function IntegrationsPage() {
  const { data: connectors, isLoading } = useQuery({ queryKey: ['integrations'], queryFn: integrationsApi.connectors })
  const stats = useQuery({ queryKey: ['crimes', 'stats'], queryFn: () => crimesApi.stats() })
  const alerts = useQuery({ queryKey: ['alerts', 'count'], queryFn: () => alertsApi.list({ limit: 1 }) })
  const custody = useQuery({ queryKey: ['custody', 'summary'], queryFn: () => intelApi.custodyDeadlines() })
  const [focus, setFocus] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  const pos = useMemo(layout, [])
  const status = useMemo(() => {
    const s: Record<string, Connector['status'] | 'live'> = {}
    for (const c of connectors ?? []) s[c.id] = c.status
    s.scan = 'live'
    return s
  }, [connectors])

  const lit = useMemo(() => (focus ? reach(focus) : null), [focus])

  if (isLoading || !connectors) return <PageLoader label="Wiring the network…" />

  const dead = (id: string) => status[id] === 'planned' || status[id] === 'excluded'
  const nodeColor = (id: string) => {
    const st = status[id]
    if (st === 'planned' || st === 'excluded') return STATUS_COLOR[st]
    return LAYERS.find((l) => l.key === pos[id].layer)!.color
  }
  const live = connectors.filter((c) => c.status === 'file' || c.status === 'manual').length
  const selected = connectors.find((c) => c.id === open)

  // Faint fully-connected mesh between adjacent layers: the "network" texture behind the real wiring.
  const mesh: string[] = []
  for (let l = 0; l < LAYERS.length - 1; l++) {
    const a = NODES.filter((n) => n.layer === LAYERS[l].key)
    const b = NODES.filter((n) => n.layer === LAYERS[l + 1].key)
    for (const p of a) for (const q of b) mesh.push(curve(pos[p.id], pos[q.id]))
  }

  return (
    <div className="p-5 animate-fade-in">
      <div className="card relative overflow-hidden bg-[radial-gradient(ellipse_at_center,rgb(var(--accent-blue)/0.08),transparent_70%)] p-0">
        <div className="grid grid-cols-2 gap-px border-b border-border-subtle bg-border-subtle md:grid-cols-5">
          <Hud label="Live feeds" value={`${live}/${connectors.length}`} tone="text-severity-low" />
          <Hud label="Cases ingested" value={stats.data?.total_crimes} tone="text-accent-cyan" />
          <Hud label="Model paths" value={EDGES.length} tone="text-accent-purple" />
          <Hud label="Unread alerts" value={alerts.data?.unread_count} tone="text-accent-blue" />
          <Hud label="Custody overdue" value={custody.data?.overdue} tone="text-severity-high" />
        </div>

        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full min-w-[720px]" role="img"
               aria-label="CrimeAI integration network" onMouseLeave={() => setFocus(null)}>
            <defs>
              <filter id="nn-glow" x="-100%" y="-100%" width="300%" height="300%">
                <feGaussianBlur stdDeviation="4" result="b" />
                <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
              </filter>
              {LAYERS.slice(0, -1).map((l, i) => (
                <linearGradient key={l.key} id={`nn-g-${l.key}`} x1={l.x} x2={LAYERS[i + 1].x} gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor={l.color} />
                  <stop offset="100%" stopColor={LAYERS[i + 1].color} />
                </linearGradient>
              ))}
            </defs>

            {LAYERS.map((l) => (
              <g key={l.key}>
                <rect x={l.x - 70} y={TOP - 46} width={140} height={H - TOP + 20} rx={14}
                      fill={l.color} fillOpacity="0.035" stroke={l.color} strokeOpacity="0.12" />
                <text x={l.x} y={TOP - 26} textAnchor="middle" fontSize="11" fontWeight="800" letterSpacing="3" fill={l.color}>
                  {l.title}
                </text>
              </g>
            ))}

            <g stroke="rgb(var(--text-muted))" strokeOpacity={focus ? 0.02 : 0.06} fill="none" strokeWidth="0.6">
              {mesh.map((d, i) => <path key={i} d={d} />)}
            </g>

            {EDGES.map(([a, b]) => {
              const d = curve(pos[a], pos[b])
              const off = dead(a) || dead(b)
              const on = !lit || (lit.has(a) && lit.has(b))
              const grad = `url(#nn-g-${pos[a].layer})`
              return (
                <g key={`${a}-${b}`} opacity={on ? 1 : 0.08} className="transition-opacity duration-300">
                  <path d={d} fill="none" stroke={off ? STATUS_COLOR.planned : grad} strokeWidth={lit && on ? 2.4 : 1.4}
                        strokeOpacity={off ? 0.5 : 0.7} strokeDasharray={off ? '5 6' : undefined} />
                  {!off && (
                    <circle r={lit && on ? 3.6 : 2.6} fill="#fff" filter="url(#nn-glow)">
                      <animateMotion dur={`${1.6 + ((a.length * 7 + b.length * 3) % 10) / 6}s`}
                                     begin={`${((a.charCodeAt(0) + b.charCodeAt(1)) % 20) / 10}s`}
                                     repeatCount="indefinite" path={d} />
                    </circle>
                  )}
                </g>
              )
            })}

            {NODES.map((n, i) => {
              const p = pos[n.id]
              const c = nodeColor(n.id)
              const on = !lit || lit.has(n.id)
              const left = n.layer === 'src'
              const clickable = connectors.some((k) => k.id === n.id)
              return (
                <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={on ? 1 : 0.18}
                   className={cn('transition-opacity duration-300', clickable && 'cursor-pointer')}
                   onMouseEnter={() => setFocus(n.id)} onClick={() => clickable && setOpen(open === n.id ? null : n.id)}>
                  <title>{n.label}</title>
                  {!dead(n.id) && (
                    <circle r="14" fill="none" stroke={c} strokeWidth="1.5">
                      <animate attributeName="r" values="14;26" dur="2.8s" begin={`${(i % 7) * 0.4}s`} repeatCount="indefinite" />
                      <animate attributeName="stroke-opacity" values="0.6;0" dur="2.8s" begin={`${(i % 7) * 0.4}s`} repeatCount="indefinite" />
                    </circle>
                  )}
                  <circle r="15" fill="rgb(var(--bg-primary))" stroke={c} strokeWidth={open === n.id ? 3.5 : 2}
                          strokeDasharray={status[n.id] === 'excluded' ? '3 3' : undefined} />
                  <circle r="7" fill={c} fillOpacity={dead(n.id) ? 0.25 : 0.9} filter={dead(n.id) ? undefined : 'url(#nn-glow)'} />
                  {status[n.id] === 'excluded' && <line x1="-11" y1="-11" x2="11" y2="11" stroke={c} strokeWidth="2" />}
                  <text x={left ? -24 : 24} y="4" textAnchor={left ? 'end' : 'start'} fontSize="13" fontWeight="600"
                        className="fill-text-primary">{n.label}</text>
                  {status[n.id] === 'planned' && (
                    <text x={left ? -24 : 24} y="17" textAnchor={left ? 'end' : 'start'} fontSize="9" fill={c}>needs ICJS</text>
                  )}
                </g>
              )
            })}
          </svg>
        </div>

        {selected && <NodeCard connector={selected} onClose={() => setOpen(null)} />}
      </div>
    </div>
  )
}

/** Everything upstream and downstream of a node, so hovering lights the whole path it sits on. */
function reach(id: string) {
  const seen = new Set([id])
  const walk = (from: string, forward: boolean) => {
    for (const [a, b] of EDGES) {
      const [src, dst] = forward ? [a, b] : [b, a]
      if (src === from && !seen.has(dst)) {
        seen.add(dst)
        walk(dst, forward)
      }
    }
  }
  walk(id, true)
  walk(id, false)
  return seen
}

function Hud({ label, value, tone }: { label: string; value: number | string | undefined; tone: string }) {
  return (
    <div className="bg-bg-secondary px-4 py-3">
      <p className={cn('text-xl font-bold tabular-nums', tone)}>{value ?? '—'}</p>
      <p className="text-2xs uppercase tracking-wider text-text-muted">{label}</p>
    </div>
  )
}

function NodeCard({ connector: c, onClose }: { connector: Connector; onClose: () => void }) {
  const hasRole = useAuthStore((s) => s.hasRole)
  const importer = IMPORTS[c.id]
  return (
    <div className="absolute bottom-4 left-1/2 w-80 -translate-x-1/2 rounded-lg border border-border-default bg-bg-secondary/95 p-3 shadow-elevated backdrop-blur animate-fade-in">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-text-primary">{c.name}</p>
          <p className="text-2xs text-text-muted">{c.owner}</p>
        </div>
        <button type="button" onClick={onClose} className="text-text-muted hover:text-text-primary" aria-label="Close"><X size={14} /></button>
      </div>
      <ul className="mt-2 space-y-1 text-xs text-text-secondary">
        {c.receives.map((r) => (
          <li key={r} className="flex gap-1.5" title={r}>
            <ArrowDownToLine size={12} className="mt-0.5 shrink-0 text-severity-low" /><span className="line-clamp-1">{r.split(':')[0]}</span>
          </li>
        ))}
        {c.sends.map((s) => (
          <li key={s} className="flex gap-1.5" title={s}>
            <ArrowUpFromLine size={12} className="mt-0.5 shrink-0 text-accent-blue" /><span className="line-clamp-1">{s.split(':')[0]}</span>
          </li>
        ))}
        {c.guardrail && <li className="text-2xs text-accent-purple" title={c.guardrail}>🛡 {c.guardrail.split(':')[0]}</li>}
      </ul>
      {importer && hasRole(importer.role) && <ImportButton run={importer.run} sample={importer.sample} />}
    </div>
  )
}

function ImportButton({ run, sample }: { run: (f: File) => Promise<ImportReport>; sample: string }) {
  const input = useRef<HTMLInputElement>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const qc = useQueryClient()
  const mutation = useMutation({
    mutationFn: run,
    onSuccess: (r) => {
      setReport(r)
      qc.invalidateQueries()
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  return (
    <div className="mt-3 border-t border-border-subtle pt-3">
      <input ref={input} type="file" accept=".csv,.json" className="hidden"
             onChange={(e) => { const f = e.target.files?.[0]; if (f) mutation.mutate(f); e.target.value = '' }} />
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => input.current?.click()} disabled={mutation.isPending} className="btn-primary py-1.5 text-xs">
          <FileUp size={13} /> {mutation.isPending ? 'Importing…' : 'Import'}
        </button>
        <a href={sample} download className="text-2xs text-accent-blue hover:underline">sample</a>
      </div>
      {report && (
        <div className="mt-2 flex flex-wrap gap-1.5 text-2xs font-semibold tabular-nums">
          <Chip cls="bg-severity-low/15 text-severity-low">+{report.created}</Chip>
          <Chip cls="bg-bg-elevated text-text-muted">{report.skipped} dup</Chip>
          {report.error_count > 0 && <Chip cls="bg-severity-high/15 text-severity-high" title={report.errors.map((e) => `Row ${e.row}: ${e.error}`).join('\n')}>{report.error_count} errors</Chip>}
          {report.link_alerts ? <Chip cls="bg-accent-blue/15 text-accent-blue">{report.link_alerts} links</Chip> : null}
        </div>
      )}
    </div>
  )
}

function Chip({ children, cls, title }: { children: React.ReactNode; cls: string; title?: string }) {
  return <span title={title} className={cn('rounded px-1.5 py-0.5', cls)}>{children}</span>
}
