import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d'
import { crimeColor, NODE_COLORS } from '@/lib/palette'
import { convexHull, findNetworks, type NetworkIndex } from '@/lib/networks'
import { useThemeColors } from '@/lib/theme'
import type { GraphNode, GraphPayload } from '@/types'

type Node = NodeObject<GraphNode & { degree: number }>
type Link = LinkObject<Node> & { kind: string }
export type GraphMode = 'network' | 'timeline'

interface LinkGraphProps {
  data: GraphPayload
  networks?: NetworkIndex
  mode?: GraphMode
  selectedId?: string | null
  /** Rank of a network to spotlight; everything else dims and the view zooms to it. */
  focusNetwork?: number | null
  onSelect?: (node: GraphNode) => void
  onExpand?: (node: GraphNode) => void
  height: number
  compact?: boolean
}

const LANE_GAP = 80
const HULL_PAD = 16
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function radius(node: Node): number {
  if (node.type === 'series') return 8
  if (node.type === 'crime') return 3.2 + (node.severity ?? 1) * 0.55
  return 5 + Math.min(node.case_count ?? 1, 8) * 1.1
}

const idOf = (end: Link['source']) => String(typeof end === 'object' ? end?.id : end)

/** A force pulling each node toward a target position; null leaves that axis free. */
function targetForce(target: (n: Node) => [number | null, number | null], strength: number) {
  let nodes: Node[] = []
  const force = (alpha: number) => {
    for (const n of nodes) {
      const [tx, ty] = target(n)
      if (tx != null) n.vx = (n.vx ?? 0) + (tx - (n.x ?? 0)) * strength * alpha
      if (ty != null) n.vy = (n.vy ?? 0) + (ty - (n.y ?? 0)) * strength * alpha
    }
  }
  force.initialize = (ns: Node[]) => { nodes = ns }
  return force
}

function shapePath(ctx: CanvasRenderingContext2D, kind: string, x: number, y: number, r: number) {
  ctx.beginPath()
  if (kind === 'vehicle') {
    const k = r * 0.38
    ctx.moveTo(x - r + k, y - r)
    ctx.arcTo(x + r, y - r, x + r, y + r, k)
    ctx.arcTo(x + r, y + r, x - r, y + r, k)
    ctx.arcTo(x - r, y + r, x - r, y - r, k)
    ctx.arcTo(x - r, y - r, x + r, y - r, k)
  } else if (kind === 'phone') {
    ctx.moveTo(x, y - r * 1.25)
    ctx.lineTo(x + r * 1.05, y)
    ctx.lineTo(x, y + r * 1.25)
    ctx.lineTo(x - r * 1.05, y)
  } else if (kind === 'upi' || kind === 'account') {
    const sides = kind === 'upi' ? 6 : 3
    for (let i = 0; i < sides; i++) {
      const a = (Math.PI * 2 * i) / sides - Math.PI / 2
      const px = x + r * 1.12 * Math.cos(a)
      const py = y + r * 1.12 * Math.sin(a)
      if (i === 0) ctx.moveTo(px, py)
      else ctx.lineTo(px, py)
    }
  } else {
    ctx.arc(x, y, r, 0, 2 * Math.PI)
  }
  ctx.closePath()
}

/** Smooth closed curve through hull points, padded outward so nodes sit inside it. */
function hullPath(ctx: CanvasRenderingContext2D, points: [number, number][], pad: number) {
  const ring: [number, number][] = []
  for (const [x, y] of points) {
    for (let i = 0; i < 10; i++) {
      const a = (Math.PI * 2 * i) / 10
      ring.push([x + pad * Math.cos(a), y + pad * Math.sin(a)])
    }
  }
  const hull = convexHull(ring)
  if (hull.length < 3) return false
  ctx.beginPath()
  const mid = (a: [number, number], b: [number, number]) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
  const start = mid(hull[hull.length - 1], hull[0])
  ctx.moveTo(start[0], start[1])
  hull.forEach((p, i) => {
    const m = mid(p, hull[(i + 1) % hull.length])
    ctx.quadraticCurveTo(p[0], p[1], m[0], m[1])
  })
  ctx.closePath()
  return true
}

function text(ctx: CanvasRenderingContext2D, value: string, x: number, y: number, size: number, color: string, scale: number, halo: string) {
  ctx.font = `600 ${size}px Inter, system-ui, sans-serif`
  ctx.lineWidth = 3 / scale
  ctx.strokeStyle = halo
  ctx.strokeText(value, x, y)
  ctx.fillStyle = color
  ctx.fillText(value, x, y)
}

/** Link chart: cases, the identifiers they share, and the series they belong to, grouped into suspected networks. */
export default function LinkGraph({
  data, networks: given, mode = 'network', selectedId, focusNetwork = null, onSelect, onExpand, height, compact = false,
}: LinkGraphProps) {
  const theme = useThemeColors()
  const halo = theme.c('bg-primary', 0.85)
  const ref = useRef<ForceGraphMethods<Node, Link>>()
  const wrapRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  const [hovered, setHovered] = useState<string | null>(null)
  const lastClick = useRef<{ id: string; at: number } | null>(null)
  const fitted = useRef(false)

  const networks = useMemo(() => given ?? findNetworks(data), [given, data])

  const graph = useMemo(() => {
    const degree = new Map<string, number>()
    for (const l of data.links) {
      degree.set(l.source, (degree.get(l.source) ?? 0) + 1)
      degree.set(l.target, (degree.get(l.target) ?? 0) + 1)
    }
    return {
      nodes: data.nodes.map((n) => ({ ...n, degree: degree.get(n.id) ?? 0 })) as Node[],
      links: data.links.map((l) => ({ ...l })) as Link[],
    }
  }, [data])

  const kindOf = useMemo(() => new Map(data.nodes.map((n) => [n.id, n.type])), [data.nodes])

  const timeline = useMemo(() => {
    const times = data.nodes.filter((n) => n.type === 'crime' && n.occurred_at).map((n) => Date.parse(n.occurred_at!))
    const min = Math.min(...times)
    const max = Math.max(...times)
    const span = Math.max(900, data.nodes.length * 12)
    const lanes = networks.networks.length
    return {
      min, max, span,
      x: (iso?: string | null) => (iso && max > min ? -span / 2 + ((Date.parse(iso) - min) / (max - min)) * span : 0),
      laneY: (rank: number) => (rank - 1 - (lanes - 1) / 2) * LANE_GAP,
    }
  }, [data.nodes, networks])

  const neighbours = useMemo(() => {
    const focus = hovered ?? selectedId
    if (!focus) return null
    const set = new Set<string>([focus])
    for (const l of data.links) {
      if (l.source === focus) set.add(l.target)
      if (l.target === focus) set.add(l.source)
    }
    return set
  }, [hovered, selectedId, data.links])

  const spotlight = focusNetwork != null ? networks.networks.find((n) => n.rank === focusNetwork) ?? null : null
  const isDim = (id: string) => (spotlight ? !spotlight.nodeIds.has(id) : false) || (neighbours ? !neighbours.has(id) : false)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const fg = ref.current
    if (!fg) return
    fitted.current = false
    // The default centring force translates every node to keep the mean at the origin; gravity does that job here.
    fg.d3Force('center', null)
    if (mode === 'timeline') {
      // A timeline is exact, not physical: pin each case at its date in its network's lane, staggered so
      // same-day cases do not overlap, and each identifier or series just above the cases it ties together.
      const laneOf = (id: string) => {
        const net = networks.networkOf.get(id)
        return net ? timeline.laneY(net.rank) : 0
      }
      const stagger = [0, -11, 11, -22, 22]
      const cases = graph.nodes.filter((n) => n.type === 'crime').sort((a, b) => timeline.x(a.occurred_at) - timeline.x(b.occurred_at))
      const lastX = new Map<number, number>()
      const slot = new Map<number, number>()
      for (const n of cases) {
        const lane = laneOf(String(n.id))
        const x = timeline.x(n.occurred_at)
        const crowded = x - (lastX.get(lane) ?? -Infinity) < 14
        const k = crowded ? ((slot.get(lane) ?? 0) + 1) % stagger.length : 0
        slot.set(lane, k)
        lastX.set(lane, x)
        n.fx = n.x = x
        n.fy = n.y = lane + 8 + stagger[k] * 0.6
      }
      const at = new Map(cases.map((n) => [String(n.id), n.fx!]))
      for (const n of graph.nodes) {
        if (n.type === 'crime') continue
        const xs = data.links
          .flatMap((l) => (l.source === n.id ? [l.target] : l.target === n.id ? [l.source] : []))
          .map((id) => at.get(id))
          .filter((x): x is number => x != null)
        n.fx = n.x = xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0
        n.fy = n.y = laneOf(String(n.id)) - 22
      }
      fg.d3Force('gravity', null)
    } else {
      for (const n of graph.nodes) {
        n.fx = undefined
        n.fy = undefined
      }
      fg.d3Force('charge')?.strength(compact ? -55 : -95).distanceMax(320)
      fg.d3Force('link')?.distance((l: Link) => (l.kind === 'member_of' ? 22 : 34)).strength(0.7)
      // Disconnected networks otherwise drift apart until zoom-to-fit makes them specks.
      fg.d3Force('gravity', targetForce(() => [0, 0], compact ? 0.06 : 0.035))
    }
    fg.d3ReheatSimulation()
    if (mode === 'timeline') {
      const timer = setTimeout(() => {
        fitted.current = true
        fg.zoomToFit(500, 75)
      }, 60)
      return () => clearTimeout(timer)
    }
  }, [graph, data.links, mode, compact, networks, timeline])

  useEffect(() => {
    const fg = ref.current
    if (!fg) return
    if (spotlight) fg.zoomToFit(700, 90, (n: Node) => spotlight.nodeIds.has(String(n.id)))
    else if (fitted.current) fg.zoomToFit(700, compact ? 45 : 60)
  }, [spotlight, compact])

  const drawBackdrop = (ctx: CanvasRenderingContext2D, scale: number) => {
    if (mode === 'timeline') {
      if (!(timeline.max > timeline.min)) return
      const lanes = networks.networks
      const top = timeline.laneY(1) - LANE_GAP / 2
      const bottom = timeline.laneY(Math.max(lanes.length, 1)) + LANE_GAP / 2
      for (const net of lanes) {
        const y = timeline.laneY(net.rank)
        ctx.fillStyle = `${net.color}0d`
        ctx.fillRect(-timeline.span / 2 - 60, y - LANE_GAP / 2 + 4, timeline.span + 120, LANE_GAP - 8)
        ctx.textAlign = 'right'
        ctx.textBaseline = 'middle'
        text(ctx, `N${net.rank}`, -timeline.span / 2 - 70, y, Math.max(11 / scale, 3), net.color, scale, halo)
      }
      const start = new Date(timeline.min)
      const cursor = new Date(start.getFullYear(), start.getMonth() + 1, 1)
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      while (cursor.getTime() <= timeline.max) {
        const x = timeline.x(cursor.toISOString())
        ctx.strokeStyle = theme.c('text-secondary', 0.16)
        ctx.lineWidth = 1 / scale
        ctx.beginPath()
        ctx.moveTo(x, top)
        ctx.lineTo(x, bottom)
        ctx.stroke()
        text(ctx, `${MONTH[cursor.getMonth()]} '${String(cursor.getFullYear()).slice(2)}`, x, top - 6 / scale,
             Math.max(10 / scale, 2.5), theme.muted, scale, halo)
        cursor.setMonth(cursor.getMonth() + 1)
      }
      return
    }
    for (const net of networks.networks) {
      const pts = graph.nodes
        .filter((n) => net.nodeIds.has(String(n.id)) && n.x != null && n.y != null)
        .map((n) => [n.x!, n.y!] as [number, number])
      if (!pts.length || !hullPath(ctx, pts, HULL_PAD)) continue
      const dim = spotlight && spotlight.rank !== net.rank
      ctx.fillStyle = `${net.color}${dim ? '05' : '12'}`
      ctx.fill()
      ctx.lineWidth = 1.2 / scale
      ctx.setLineDash([4 / scale, 3 / scale])
      ctx.strokeStyle = `${net.color}${dim ? '22' : '70'}`
      ctx.stroke()
      ctx.setLineDash([])
      if (!compact) {
        const topY = Math.min(...pts.map((p) => p[1])) - HULL_PAD - 5 / scale
        const midX = pts.reduce((s, p) => s + p[0], 0) / pts.length
        ctx.textAlign = 'center'
        ctx.textBaseline = 'bottom'
        text(ctx, `NETWORK ${net.rank} · ${net.cases.length} cases${net.districts.length > 1 ? ` · ${net.districts.length} districts` : ''}`,
             midX, topY, Math.max(9.5 / scale, 2.4), dim ? `${net.color}55` : net.color, scale, halo)
      }
    }
  }

  return (
    <div
      ref={wrapRef}
      className="relative w-full"
      style={{
        height,
        backgroundImage: 'radial-gradient(rgba(139,148,158,0.13) 1px, transparent 1px), radial-gradient(ellipse at center, rgba(31,111,235,0.07), transparent 70%)',
        backgroundSize: '22px 22px, 100% 100%',
      }}
    >
      <ForceGraph2D<Node, Link>
        ref={ref}
        graphData={graph}
        width={width}
        height={height}
        backgroundColor="rgba(0,0,0,0)"
        autoPauseRedraw={false}
        warmupTicks={mode === 'timeline' ? 80 : 40}
        cooldownTicks={220}
        d3VelocityDecay={0.32}
        onEngineStop={() => {
          if (fitted.current) return
          fitted.current = true
          if (spotlight) ref.current?.zoomToFit(600, 90, (n: Node) => spotlight.nodeIds.has(String(n.id)))
          else ref.current?.zoomToFit(600, compact ? 45 : 60)
        }}
        onRenderFramePre={drawBackdrop}
        nodeRelSize={1}
        nodeVal={(n) => radius(n) ** 2}
        linkCurvature={mode === 'timeline' ? 0.25 : 0.12}
        linkColor={(l) => {
          const src = idOf(l.source)
          const tgt = idOf(l.target)
          const ident = kindOf.get(src) === 'crime' ? kindOf.get(tgt) : kindOf.get(src)
          const color = l.kind === 'member_of' ? NODE_COLORS.series : NODE_COLORS[ident ?? 'crime'] ?? '#8b949e'
          const lit = neighbours && neighbours.has(src) && neighbours.has(tgt)
          const dim = isDim(src) || isDim(tgt)
          return `${color}${lit ? 'e6' : dim ? '14' : '55'}`
        }}
        linkWidth={(l) => {
          const lit = neighbours && neighbours.has(idOf(l.source)) && neighbours.has(idOf(l.target))
          return lit ? 2 : l.kind === 'member_of' ? 0.8 : 1.1
        }}
        linkLineDash={(l) => (l.kind === 'member_of' ? [3, 3] : null)}
        linkDirectionalParticles={(l) => (neighbours && neighbours.has(idOf(l.source)) && neighbours.has(idOf(l.target)) ? 3 : 0)}
        linkDirectionalParticleWidth={2.4}
        linkDirectionalParticleSpeed={0.007}
        linkDirectionalParticleColor={(l) => {
          const src = idOf(l.source)
          return NODE_COLORS[kindOf.get(src) === 'crime' ? kindOf.get(idOf(l.target)) ?? 'crime' : kindOf.get(src) ?? 'crime'] ?? '#58a6ff'
        }}
        onNodeHover={(n) => setHovered(n ? String(n.id) : null)}
        onNodeClick={(n) => {
          const now = Date.now()
          if (lastClick.current && lastClick.current.id === n.id && now - lastClick.current.at < 350) onExpand?.(n)
          else onSelect?.(n)
          lastClick.current = { id: String(n.id), at: now }
        }}
        nodeCanvasObject={(n, ctx, scale) => {
          const r = radius(n)
          const x = n.x ?? 0
          const y = n.y ?? 0
          const id = String(n.id)
          const dimmed = isDim(id)
          const color = n.type === 'crime' ? crimeColor(n.crime_type ?? '') : NODE_COLORS[n.type] ?? '#8b949e'
          ctx.globalAlpha = dimmed ? 0.14 : 1

          if (n.type === 'series') {
            ctx.beginPath()
            ctx.arc(x, y, r, 0, 2 * Math.PI)
            ctx.fillStyle = theme.surface
            ctx.fill()
            ctx.lineWidth = 2
            ctx.strokeStyle = color
            ctx.stroke()
            ctx.beginPath()
            ctx.arc(x, y, r + 3, 0, 2 * Math.PI)
            ctx.setLineDash([2, 2])
            ctx.lineWidth = 1
            ctx.stroke()
            ctx.setLineDash([])
          } else {
            if (n.type !== 'crime' && !dimmed) {
              ctx.shadowColor = color
              ctx.shadowBlur = 8 + Math.min(n.case_count ?? 1, 8) * 2.5
            }
            shapePath(ctx, n.type, x, y, r)
            ctx.fillStyle = n.type === 'crime' ? color : `${color}`
            ctx.fill()
            ctx.shadowBlur = 0
            ctx.lineWidth = n.type === 'crime' ? 0.8 : 1.4
            ctx.strokeStyle = n.type === 'crime' ? theme.outline : theme.c('text-primary', 0.8)
            ctx.stroke()
            if (n.type !== 'crime' && (n.case_count ?? 0) > 1 && scale > 0.9) {
              ctx.font = `700 ${Math.max(r * 0.95, 3)}px Inter, system-ui, sans-serif`
              ctx.textAlign = 'center'
              ctx.textBaseline = 'middle'
              ctx.fillStyle = '#0a0c10'
              ctx.fillText(String(n.case_count), x, y + 0.3)
            }
          }

          if (id === selectedId) {
            const pulse = (Math.sin(performance.now() / 260) + 1) / 2
            ctx.beginPath()
            ctx.arc(x, y, r + 4 + pulse * 4, 0, 2 * Math.PI)
            ctx.lineWidth = 1.6
            ctx.strokeStyle = theme.c('text-primary', 0.9 - pulse * 0.6)
            ctx.stroke()
          }

          const showLabel = n.type !== 'crime' ? scale > 0.6 || id === hovered : scale > 1.8 || id === hovered || id === selectedId
          if (showLabel && !dimmed) {
            ctx.textAlign = 'center'
            ctx.textBaseline = 'top'
            text(ctx, n.label, x, y + r + 2.5, Math.max(10 / scale, 2.2), n.type === 'crime' ? theme.muted : theme.text, scale, halo)
          }
          ctx.globalAlpha = 1
        }}
        nodePointerAreaPaint={(n, color, ctx) => {
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(n.x ?? 0, n.y ?? 0, radius(n) + 3, 0, 2 * Math.PI)
          ctx.fill()
        }}
      />
    </div>
  )
}
