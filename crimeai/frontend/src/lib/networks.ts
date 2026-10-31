import type { GraphNode, GraphPayload } from '@/types'

/** Distinct hues for network hulls; kept apart from the node-type colours where possible. */
export const NETWORK_COLORS = ['#58a6ff', '#f778ba', '#3fb950', '#d29922', '#bc8cff', '#39c5cf', '#ff7b72', '#a5d6ff', '#ffa657', '#7ee787']

export interface Network {
  /** 1-based rank by threat score; also the display number. */
  rank: number
  color: string
  nodeIds: Set<string>
  cases: GraphNode[]
  identifiers: GraphNode[]
  series: GraphNode[]
  districts: string[]
  firstSeen: string | null
  lastSeen: string | null
  /** Wider reach and more shared identifiers suggest an organised group rather than coincidence. */
  score: number
}

export interface NetworkIndex {
  networks: Network[]
  networkOf: Map<string, Network>
}

/** Connected components of the link graph: each is a set of cases tied together by shared identifiers or a series. */
export function findNetworks(graph: GraphPayload): NetworkIndex {
  const parent = new Map<string, string>(graph.nodes.map((n) => [n.id, n.id]))
  const find = (id: string): string => {
    let root = id
    while (parent.get(root) !== root) root = parent.get(root)!
    let cur = id
    while (cur !== root) {
      const next = parent.get(cur)!
      parent.set(cur, root)
      cur = next
    }
    return root
  }
  for (const l of graph.links) {
    if (parent.has(l.source) && parent.has(l.target)) parent.set(find(l.source), find(l.target))
  }

  const groups = new Map<string, GraphNode[]>()
  for (const n of graph.nodes) {
    const root = find(n.id)
    groups.set(root, [...(groups.get(root) ?? []), n])
  }

  const networks = [...groups.values()]
    .map((nodes) => {
      const cases = nodes.filter((n) => n.type === 'crime')
      const identifiers = nodes.filter((n) => n.type !== 'crime' && n.type !== 'series')
      const series = nodes.filter((n) => n.type === 'series')
      const districts = [...new Set(cases.map((c) => c.district).filter((d): d is string => !!d))].sort()
      const dates = cases.map((c) => c.occurred_at).filter((d): d is string => !!d).sort()
      return {
        rank: 0,
        color: '',
        nodeIds: new Set(nodes.map((n) => n.id)),
        cases,
        identifiers,
        series,
        districts,
        firstSeen: dates[0] ?? null,
        lastSeen: dates[dates.length - 1] ?? null,
        score: cases.length + 2 * identifiers.length + 3 * Math.max(0, districts.length - 1) + 2 * series.length,
      }
    })
    .filter((n) => n.cases.length >= 2)
    .sort((a, b) => b.score - a.score)

  const networkOf = new Map<string, Network>()
  networks.forEach((net, i) => {
    net.rank = i + 1
    net.color = NETWORK_COLORS[i % NETWORK_COLORS.length]
    for (const id of net.nodeIds) networkOf.set(id, net)
  })
  return { networks, networkOf }
}

/** Monotone-chain convex hull of 2D points. */
export function convexHull(points: [number, number][]): [number, number][] {
  const pts = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1])
  if (pts.length < 3) return pts
  const cross = (o: number[], a: number[], b: number[]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
  const lower: [number, number][] = []
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop()
    lower.push(p)
  }
  const upper: [number, number][] = []
  for (const p of [...pts].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop()
    upper.push(p)
  }
  return [...lower.slice(0, -1), ...upper.slice(0, -1)]
}
