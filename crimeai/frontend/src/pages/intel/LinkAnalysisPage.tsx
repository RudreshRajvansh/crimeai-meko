import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useLocation } from 'react-router-dom'
import { ArrowUpRight, CalendarRange, Crosshair, FileWarning, Map as MapIcon, Network, RotateCcw, Search, Share2, X } from 'lucide-react'
import toast from 'react-hot-toast'
import LinkGraph, { type GraphMode } from '@/components/intel/LinkGraph'
import FreezePacketDialog from '@/components/intel/FreezePacketDialog'
import { useAuthStore } from '@/store/auth'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { findNetworks, type Network as SuspectedNetwork, type NetworkIndex } from '@/lib/networks'
import { NODE_COLORS, NODE_LABELS } from '@/lib/palette'
import { getErrorMessage } from '@/services/api'
import { insightApi } from '@/services/insight'
import { cn, crimeTypeLabel, formatDate } from '@/utils'
import type { GraphNode, GraphPayload } from '@/types'

const LinkMap = lazy(() => import('@/components/intel/LinkMap'))

const TYPES = ['crime', 'vehicle', 'phone', 'upi', 'account', 'series'] as const
type View = GraphMode | 'map'
const VIEWS: { id: View; label: string; icon: typeof Network; hint: string }[] = [
  { id: 'network', label: 'Network', icon: Share2, hint: 'Click to inspect · double-click to expand · scroll to zoom · drag to rearrange' },
  { id: 'timeline', label: 'Timeline', icon: CalendarRange, hint: 'Cases placed by date, one lane per network · hover a case to trace its links' },
  { id: 'map', label: 'Map', icon: MapIcon, hint: 'Identifiers sit at the centre of the cases they link · click any marker to inspect' },
]

function threat(net: SuspectedNetwork): { label: string; cls: string } {
  if (net.score >= 24 || net.districts.length >= 3) return { label: 'High', cls: 'bg-severity-high/15 text-severity-high' }
  if (net.score >= 12 || net.districts.length >= 2) return { label: 'Elevated', cls: 'bg-severity-medium/15 text-severity-medium' }
  return { label: 'Watch', cls: 'bg-accent-blue/15 text-accent-blue' }
}

export default function LinkAnalysisPage() {
  const overview = useQuery({ queryKey: ['graph', 'overview'], queryFn: insightApi.graphOverview })
  const [focus, setFocus] = useState<GraphPayload | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<View>('network')
  const [spotlight, setSpotlight] = useState<number | null>(null)
  const location = useLocation()
  const sectionRef = useRef<HTMLElement>(null)
  const toolbarRef = useRef<HTMLDivElement>(null)
  // The toolbar wraps on narrow screens; the canvas starts below it and fills the rest of the section.
  const [box, setBox] = useState({ top: 49, height: 600 })
  useEffect(() => {
    const section = sectionRef.current
    const toolbar = toolbarRef.current
    if (!section || !toolbar) return
    const measure = () => setBox({ top: toolbar.offsetHeight, height: section.clientHeight - toolbar.offsetHeight })
    const observer = new ResizeObserver(measure)
    observer.observe(section)
    observer.observe(toolbar)
    measure()
    return () => observer.disconnect()
  }, [overview.isLoading])

  const source = focus ?? overview.data
  const visible = useMemo<GraphPayload | null>(() => {
    if (!source) return null
    const nodes = source.nodes.filter((n) => !hidden.has(n.type))
    const ids = new Set(nodes.map((n) => n.id))
    return { ...source, nodes, links: source.links.filter((l) => ids.has(l.source) && ids.has(l.target)) }
  }, [source, hidden])
  const networks = useMemo<NetworkIndex>(() => (visible ? findNetworks(visible) : { networks: [], networkOf: new Map() }), [visible])

  const expand = async (node: GraphNode) => {
    setBusy(true)
    try {
      const graph = await insightApi.graphNeighbourhood(node.id, 2)
      setFocus(graph)
      setSpotlight(null)
      setSelected(graph.nodes.find((n) => n.id === node.id) ?? node)
    } catch (err) {
      toast.error(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    const node = (location.state as { node?: string } | null)?.node
    if (!node) return
    const type = node.startsWith('series:') ? 'series' : node.startsWith('crime:') ? 'crime' : 'phone'
    void expand({ id: node, type, label: '' })
  }, [location.state])

  const runSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (query.trim().length < 2) return
    try {
      const hits = await insightApi.graphSearch(query.trim())
      if (!hits.length) {
        toast('No vehicle, phone or UPI ID matches that.')
        return
      }
      await expand(hits[0])
    } catch (err) {
      toast.error(getErrorMessage(err))
    }
  }

  if (overview.isLoading) return <PageLoader label="Building link graph…" />
  const stats = source?.stats
  const spotlit = spotlight != null ? networks.networks.find((n) => n.rank === spotlight) ?? null : null
  const hint = VIEWS.find((v) => v.id === view)!.hint

  return (
    <div className="flex h-[calc(100vh-57px)] animate-fade-in">
      <section ref={sectionRef} className="relative flex-1 overflow-hidden bg-bg-primary">
        <div ref={toolbarRef} className="absolute inset-x-0 top-0 z-[600] flex flex-wrap items-center gap-3 border-b border-border-subtle bg-bg-primary/90 px-4 py-2.5 backdrop-blur">
          <div className="flex rounded-lg bg-bg-secondary p-0.5" role="tablist" aria-label="Graph view">
            {VIEWS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={view === id}
                onClick={() => setView(id)}
                className={cn('flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
                  view === id ? 'bg-bg-elevated text-text-primary shadow-inner-sm' : 'text-text-muted hover:text-text-secondary')}
              >
                <Icon size={13} /> {label}
              </button>
            ))}
          </div>
          <form onSubmit={runSearch} className="relative w-60">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="input pl-8 py-1.5 text-xs"
              placeholder="Vehicle no., phone or UPI ID"
              aria-label="Search the link graph"
            />
          </form>
          <div className="flex flex-wrap items-center gap-1.5">
            {TYPES.map((t) => {
              const off = hidden.has(t)
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => setHidden((h) => {
                    const next = new Set(h)
                    if (next.has(t)) next.delete(t)
                    else next.add(t)
                    return next
                  })}
                  aria-pressed={!off}
                  className={cn(
                    'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-2xs font-medium transition-colors',
                    off ? 'border-border-subtle text-text-muted' : 'border-border-default text-text-primary bg-bg-elevated',
                  )}
                >
                  <span className="h-2 w-2 rounded-full" style={{ background: off ? 'rgb(var(--border-strong))' : NODE_COLORS[t] }} />
                  {NODE_LABELS[t]}
                </button>
              )
            })}
          </div>
          {focus && (
            <button type="button" onClick={() => { setFocus(null); setSelected(null); setSpotlight(null) }} className="btn-ghost py-1 text-xs">
              <RotateCcw size={13} /> All links
            </button>
          )}
          <div className="ml-auto flex items-center gap-4 text-2xs text-text-secondary tabular-nums">
            <span><b className="text-text-primary">{networks.networks.length}</b> networks</span>
            <span><b className="text-text-primary">{stats?.cases ?? 0}</b> cases</span>
            <span><b className="text-text-primary">{stats?.entities ?? 0}</b> identifiers</span>
            <span><b className="text-text-primary">{stats?.districts ?? 0}</b> districts</span>
          </div>
        </div>

        {spotlit && (
          <div className="absolute left-1/2 z-[600] flex max-w-[92%] -translate-x-1/2 items-center gap-3 whitespace-nowrap rounded-full border bg-bg-secondary/95 px-4 py-1.5 text-xs shadow-elevated backdrop-blur"
               style={{ top: box.top + 12, borderColor: `${spotlit.color}88` }}>
            <span className="h-2 w-2 rounded-full" style={{ background: spotlit.color }} />
            <span className="font-semibold text-text-primary">Network {spotlit.rank}</span>
            <span className="truncate text-text-secondary tabular-nums">{spotlit.cases.length} cases · {spotlit.identifiers.length} identifiers · {spotlit.districts.join(', ')}</span>
            <button type="button" onClick={() => setSpotlight(null)} className="text-text-muted hover:text-text-primary" aria-label="Clear spotlight"><X size={13} /></button>
          </div>
        )}

        {visible && visible.nodes.length > 0 ? (
          <div className="absolute inset-x-0 bottom-0" style={{ top: box.top }}>
            {view === 'map' ? (
              <Suspense fallback={<PageLoader label="Loading map…" />}>
                <LinkMap data={visible} networks={networks} selectedId={selected?.id} focusNetwork={spotlight} onSelect={setSelected} />
              </Suspense>
            ) : (
              <LinkGraph
                data={visible}
                networks={networks}
                mode={view}
                height={box.height}
                selectedId={selected?.id}
                focusNetwork={spotlight}
                onSelect={setSelected}
                onExpand={expand}
              />
            )}
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-text-muted">
            <Network size={28} className="opacity-40" />
            <p className="text-sm">No linked cases yet. Links appear once FIRs share a vehicle, phone or UPI ID.</p>
          </div>
        )}
        <p className="pointer-events-none absolute bottom-3 left-4 z-[600] rounded bg-bg-primary/70 px-2 py-0.5 text-2xs text-text-muted">
          {busy ? 'Expanding…' : hint}
        </p>
      </section>

      <Inspector
        node={selected}
        graph={visible}
        networks={networks}
        spotlight={spotlight}
        onSpotlight={(rank) => { setSpotlight(rank); setSelected(null) }}
        onSelect={setSelected}
        onExpand={expand}
      />
    </div>
  )
}

interface InspectorProps {
  node: GraphNode | null
  graph: GraphPayload | null
  networks: NetworkIndex
  spotlight: number | null
  onSpotlight: (rank: number | null) => void
  onSelect: (node: GraphNode) => void
  onExpand: (node: GraphNode) => void
}

const FREEZABLE = new Set(['upi', 'account', 'phone'])

function Inspector({ node, graph, networks, spotlight, onSpotlight, onSelect, onExpand }: InspectorProps) {
  const canDraftFreeze = useAuthStore((s) => s.hasRole('police'))
  const [freezeFor, setFreezeFor] = useState<string | null>(null)
  if (!node || !graph) return <NetworkList graph={graph} networks={networks} spotlight={spotlight} onSpotlight={onSpotlight} onSelect={onSelect} />

  const neighbourIds = new Set(
    graph.links.flatMap((l) => (l.source === node.id ? [l.target] : l.target === node.id ? [l.source] : [])),
  )
  const neighbours = graph.nodes.filter((n) => neighbourIds.has(n.id))
  const network = networks.networkOf.get(node.id)

  return (
    <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-border-default bg-bg-secondary lg:block">
      <div className="border-b border-border-subtle p-5">
        <p className="flex items-center gap-2 text-2xs font-medium text-text-secondary">
          <span className="h-2 w-2 rounded-full" style={{ background: NODE_COLORS[node.type] }} />
          {NODE_LABELS[node.type]}
        </p>
        <h2 className="mt-1 break-all font-mono text-base font-semibold text-text-primary">{node.label}</h2>
        {node.type === 'crime' ? (
          <dl className="mt-3 grid grid-cols-2 gap-y-2 text-xs">
            <dt className="text-text-muted">Offence</dt><dd className="text-text-primary">{crimeTypeLabel(node.crime_type ?? '')}</dd>
            <dt className="text-text-muted">District</dt><dd className="text-text-primary">{node.district ?? '—'}</dd>
            <dt className="text-text-muted">Date</dt><dd className="text-text-primary">{node.occurred_at ? formatDate(node.occurred_at, 'dd MMM yyyy, HH:mm') : '—'}</dd>
            <dt className="text-text-muted">Severity</dt><dd className="text-text-primary">{node.severity}/5</dd>
          </dl>
        ) : node.type === 'series' ? (
          <p className="mt-2 text-xs text-text-secondary">{node.size} linked incidents with a shared modus operandi.</p>
        ) : (
          <dl className="mt-3 grid grid-cols-2 gap-y-2 text-xs">
            <dt className="text-text-muted">Cases linked</dt><dd className="text-text-primary tabular-nums">{node.case_count}</dd>
            <dt className="text-text-muted">First seen</dt><dd className="text-text-primary">{node.first_seen ? formatDate(node.first_seen, 'dd MMM yyyy') : '—'}</dd>
            <dt className="text-text-muted">Last seen</dt><dd className="text-text-primary">{node.last_seen ? formatDate(node.last_seen, 'dd MMM yyyy') : '—'}</dd>
          </dl>
        )}
        {network && (
          <button
            type="button"
            onClick={() => onSpotlight(network.rank)}
            className="mt-3 flex w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-xs hover:bg-bg-hover"
            style={{ borderColor: `${network.color}66` }}
          >
            <Crosshair size={13} style={{ color: network.color }} />
            <span className="text-text-primary">Part of Network {network.rank}</span>
            <span className="ml-auto text-2xs text-text-muted">{network.cases.length} cases</span>
          </button>
        )}
        {canDraftFreeze && FREEZABLE.has(node.type) && (node.case_count ?? 0) > 0 && (
          <button
            type="button"
            onClick={() => setFreezeFor(node.id.split(':')[1])}
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-md border border-severity-high/40 bg-severity-high/10 px-2.5 py-1.5 text-xs font-medium text-severity-high hover:bg-severity-high/20"
          >
            <FileWarning size={13} /> Draft freeze request ({node.case_count} complaints)
          </button>
        )}
        {freezeFor && <FreezePacketDialog entityId={freezeFor} onClose={() => setFreezeFor(null)} />}
        <div className="mt-3 flex gap-2">
          <button type="button" onClick={() => onExpand(node)} className="btn-secondary flex-1 justify-center py-1.5 text-xs">
            <Network size={13} /> Expand
          </button>
          {node.type === 'crime' && (
            <Link to={`/cases/${node.id.split(':')[1]}`} className="btn-primary flex-1 justify-center py-1.5 text-xs">
              Dossier <ArrowUpRight size={13} />
            </Link>
          )}
        </div>
      </div>
      <div className="p-5">
        <h3 className="text-2xs font-semibold uppercase tracking-wider text-text-secondary">Connected ({neighbours.length})</h3>
        <ul className="mt-2 space-y-1">
          {neighbours.map((n) => (
            <li key={n.id} className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => onSelect(n)}
                className="flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1.5 text-left text-xs hover:bg-bg-hover"
              >
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: NODE_COLORS[n.type] }} />
                <span className="truncate font-mono text-text-primary">{n.label}</span>
                <span className="ml-auto shrink-0 text-2xs text-text-muted">
                  {n.type === 'crime' ? `${crimeTypeLabel(n.crime_type ?? '')} · ${n.district ?? ''}` : NODE_LABELS[n.type]}
                </span>
              </button>
              {n.type === 'crime' && (
                <Link to={`/cases/${n.id.split(':')[1]}`} className="rounded p-1 text-text-muted hover:bg-bg-hover hover:text-accent-blue" aria-label={`Open ${n.label}`}>
                  <ArrowUpRight size={12} />
                </Link>
              )}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}

function NetworkList({ graph, networks, spotlight, onSpotlight, onSelect }: Omit<InspectorProps, 'node' | 'onExpand'>) {
  const connectors = (graph?.nodes ?? [])
    .filter((n) => n.type !== 'crime' && n.type !== 'series')
    .sort((a, b) => (b.case_count ?? 0) - (a.case_count ?? 0))
    .slice(0, 6)
  const maxCount = Math.max(1, ...connectors.map((c) => c.case_count ?? 0))

  return (
    <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-border-default bg-bg-secondary lg:block">
      <div className="border-b border-border-subtle p-5">
        <h2 className="text-sm font-semibold text-text-primary">Suspected networks</h2>
        <p className="mt-1 text-xs leading-relaxed text-text-secondary">
          Cases tied together by a shared vehicle, phone, UPI ID or series. Ranked by reach: more cases, identifiers and districts first.
        </p>
      </div>
      <ul className="space-y-2 p-3">
        {networks.networks.map((net) => {
          const level = threat(net)
          const active = spotlight === net.rank
          return (
            <li key={net.rank}>
              <button
                type="button"
                onClick={() => onSpotlight(active ? null : net.rank)}
                aria-pressed={active}
                className={cn('relative w-full overflow-hidden rounded-lg border p-3 text-left transition-colors hover:bg-bg-hover',
                  active ? 'bg-bg-elevated' : 'border-border-subtle')}
                style={active ? { borderColor: net.color } : undefined}
              >
                <span className="absolute inset-y-0 left-0 w-1" style={{ background: net.color }} />
                <div className="flex items-center gap-2 pl-1.5">
                  <span className="text-xs font-semibold text-text-primary">Network {net.rank}</span>
                  <span className={cn('rounded px-1.5 py-0.5 text-2xs font-medium', level.cls)}>{level.label}</span>
                  <span className="ml-auto text-2xs tabular-nums text-text-muted">score {net.score}</span>
                </div>
                <p className="mt-1.5 pl-1.5 text-2xs tabular-nums text-text-secondary">
                  {net.cases.length} cases · {net.identifiers.length} identifiers{net.series.length ? ` · ${net.series.length} series` : ''}
                </p>
                <p className="mt-0.5 truncate pl-1.5 text-2xs text-text-muted">{net.districts.join(' · ') || 'No district'}</p>
                {net.firstSeen && net.lastSeen && (
                  <p className="mt-0.5 pl-1.5 text-2xs tabular-nums text-text-muted">
                    {formatDate(net.firstSeen, 'dd MMM')} – {formatDate(net.lastSeen, 'dd MMM yyyy')}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-1 pl-1.5">
                  {net.identifiers.slice(0, 4).map((i) => (
                    <span key={i.id} className="inline-flex items-center gap-1 rounded bg-bg-primary px-1.5 py-0.5 font-mono text-2xs text-text-primary">
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: NODE_COLORS[i.type] }} />{i.label}
                    </span>
                  ))}
                </div>
              </button>
            </li>
          )
        })}
        {!networks.networks.length && <li className="p-2 text-xs text-text-muted">No networks of two or more cases yet.</li>}
      </ul>
      {connectors.length > 0 && (
        <div className="border-t border-border-subtle p-5">
          <h3 className="text-2xs font-semibold uppercase tracking-wider text-text-secondary">Top connectors</h3>
          <ul className="mt-2 space-y-1.5">
            {connectors.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => onSelect(c)} className="w-full rounded px-1.5 py-1 text-left hover:bg-bg-hover">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="h-2 w-2 rounded-full" style={{ background: NODE_COLORS[c.type] }} />
                    <span className="truncate font-mono text-text-primary">{c.label}</span>
                    <span className="ml-auto tabular-nums text-text-secondary">{c.case_count}</span>
                  </div>
                  <div className="mt-1 h-1 rounded-full bg-bg-primary">
                    <div className="h-1 rounded-full" style={{ width: `${((c.case_count ?? 0) / maxCount) * 100}%`, background: NODE_COLORS[c.type] }} />
                  </div>
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-2xs text-text-muted">Phone numbers and UPI IDs are stored only as keyed hashes and shown masked.</p>
        </div>
      )}
    </aside>
  )
}
