import { useEffect, useMemo } from 'react'
import L from 'leaflet'
import { CircleMarker, MapContainer, Marker, Polygon, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { AutoResize } from '@/components/map/MapGuards'
import { hasSize } from '@/components/map/mapSize'
import { crimeColor, NODE_COLORS, NODE_LABELS } from '@/lib/palette'
import { convexHull, type NetworkIndex } from '@/lib/networks'
import { useThemeColors } from '@/lib/theme'
import { crimeTypeLabel, escapeHtml, formatDate } from '@/utils'
import type { GraphNode, GraphPayload } from '@/types'

interface LinkMapProps {
  data: GraphPayload
  networks: NetworkIndex
  selectedId?: string | null
  focusNetwork?: number | null
  onSelect: (node: GraphNode) => void
}

type LatLng = [number, number]

const GLYPH_SHAPE: Record<string, string> = {
  vehicle: 'border-radius:5px',
  phone: 'transform:rotate(45deg);border-radius:3px',
  upi: 'clip-path:polygon(25% 4%,75% 4%,100% 50%,75% 96%,25% 96%,0 50%)',
  account: 'clip-path:polygon(50% 0,100% 100%,0 100%)',
}

function glyph(node: GraphNode, selected: boolean, dim: boolean): L.DivIcon {
  const color = NODE_COLORS[node.type] ?? '#8b949e'
  if (node.type === 'series') {
    // A series is context, not a lead: a quiet ring at the centre of its incidents, named in the tooltip.
    return L.divIcon({
      className: '',
      iconSize: [22, 22],
      iconAnchor: [11, 11],
      html: `<div style="width:22px;height:22px;border-radius:50%;border:2px dashed ${color};opacity:${dim ? 0.15 : 0.85};
        box-shadow:0 0 ${selected ? 16 : 8}px ${color}66"></div>`,
    })
  }
  const size = 16 + Math.min(node.case_count ?? 1, 8) * 2
  const n = node.case_count ?? node.size ?? ''
  const count = node.type === 'phone' ? `<span style="transform:rotate(-45deg)">${n}</span>` : `${n}`
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div style="position:relative;width:${size}px;height:${size}px;opacity:${dim ? 0.18 : 1}">
      <div class="link-glyph" style="width:100%;height:100%;background:${color};${GLYPH_SHAPE[node.type] ?? 'border-radius:50%'};
        box-shadow:0 0 ${selected ? 22 : 14}px ${color}${selected ? '' : 'aa'};outline:${selected ? '2px solid rgb(var(--text-primary))' : 'none'};outline-offset:3px">${count}</div>
      <div class="link-glyph-label">${escapeHtml(node.label)}</div></div>`,
  })
}

/** Quadratic arc between two points, bowed to one side so parallel links stay readable. */
function arc(from: LatLng, to: LatLng, bend = 0.22): LatLng[] {
  const [lat1, lng1] = from
  const [lat2, lng2] = to
  const ctrl: LatLng = [(lat1 + lat2) / 2 - (lng2 - lng1) * bend, (lng1 + lng2) / 2 + (lat2 - lat1) * bend]
  return Array.from({ length: 25 }, (_, i) => {
    const t = i / 24
    const a = (1 - t) ** 2
    const b = 2 * (1 - t) * t
    const c = t ** 2
    return [a * lat1 + b * ctrl[0] + c * lat2, a * lng1 + b * ctrl[1] + c * lng2] as LatLng
  })
}

function FitTo({ points }: { points: LatLng[] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length && hasSize(map)) map.fitBounds(L.latLngBounds(points), { padding: [50, 50], maxZoom: 14 })
  }, [map, points])
  return null
}

/** The link graph on real geography: where linked cases happened and which identifiers tie them together. */
export default function LinkMap({ data, networks, selectedId, focusNetwork = null, onSelect }: LinkMapProps) {
  const theme = useThemeColors()
  const layout = useMemo(() => {
    const cases = data.nodes.filter((n) => n.type === 'crime' && n.lat != null && n.lng != null)
    const at = new Map<string, LatLng>(cases.map((c) => [c.id, [c.lat!, c.lng!]]))
    const members = new Map<string, string[]>()
    for (const l of data.links) {
      const [hub, leaf] = at.has(l.target) ? [l.source, l.target] : [l.target, l.source]
      if (at.has(leaf)) members.set(hub, [...(members.get(hub) ?? []), leaf])
    }
    const hubs = data.nodes
      .filter((n) => n.type !== 'crime' && members.has(n.id))
      .map((n) => {
        const pts = members.get(n.id)!.map((id) => at.get(id)!)
        const center: LatLng = [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length]
        return { node: n, center, leaves: members.get(n.id)! }
      })
    return { cases, at, hubs }
  }, [data])

  const spotlight = focusNetwork != null ? networks.networks.find((n) => n.rank === focusNetwork) ?? null : null
  const neighbours = useMemo(() => {
    if (!selectedId) return null
    const set = new Set([selectedId])
    for (const l of data.links) {
      if (l.source === selectedId) set.add(l.target)
      if (l.target === selectedId) set.add(l.source)
    }
    return set
  }, [selectedId, data.links])
  const dim = (id: string) => (spotlight ? !spotlight.nodeIds.has(id) : false) || (neighbours ? !neighbours.has(id) : false)

  const fitPoints = useMemo(() => {
    const ids = spotlight ? [...spotlight.nodeIds] : [...layout.at.keys()]
    return ids.map((id) => layout.at.get(id)).filter((p): p is LatLng => !!p)
  }, [spotlight, layout])

  return (
    <MapContainer center={[28.61, 77.21]} zoom={11} className="h-full w-full" zoomControl preferCanvas={false}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <AutoResize />
      <FitTo points={fitPoints} />

      {networks.networks.map((net) => {
        const pts = net.cases.map((c) => layout.at.get(c.id)).filter((p): p is LatLng => !!p)
        const hull = convexHull(pts)
        if (hull.length < 3) return null
        const faded = spotlight && spotlight.rank !== net.rank
        return (
          <Polygon
            key={`hull-${net.rank}`}
            positions={hull}
            pathOptions={{ color: net.color, weight: 1.2, dashArray: '5 5', fillColor: net.color, fillOpacity: faded ? 0.02 : 0.08, opacity: faded ? 0.15 : 0.6 }}
          >
            <Tooltip sticky>Network {net.rank} · {net.cases.length} cases · {net.districts.join(', ')}</Tooltip>
          </Polygon>
        )
      })}

      {layout.hubs.flatMap(({ node, center, leaves }) =>
        leaves.flatMap((leaf) => {
          const faded = dim(node.id) || dim(leaf)
          const lit = !!neighbours && neighbours.has(node.id) && neighbours.has(leaf)
          const color = NODE_COLORS[node.type] ?? '#8b949e'
          const path = arc(center, layout.at.get(leaf)!)
          return [
            <Polyline
              key={`${node.id}-${leaf}-glow`}
              positions={path}
              interactive={false}
              pathOptions={{ color, weight: lit ? 9 : 6, opacity: faded ? 0 : lit ? 0.3 : 0.14, lineCap: 'round' }}
            />,
            <Polyline
              key={`${node.id}-${leaf}`}
              positions={path}
              interactive={false}
              pathOptions={{
                color,
                weight: lit ? 3.2 : 2.2,
                opacity: faded ? 0.08 : lit ? 1 : 0.85,
                className: faded ? undefined : 'link-flow',
              }}
            />,
          ]
        }),
      )}

      {layout.cases.map((c) => (
        <CircleMarker
          key={c.id}
          center={layout.at.get(c.id)!}
          radius={c.id === selectedId ? 8 : 4 + (c.severity ?? 1) * 0.6}
          pathOptions={{
            color: c.id === selectedId ? theme.text : theme.outline,
            weight: c.id === selectedId ? 2.5 : 1,
            fillColor: crimeColor(c.crime_type ?? ''),
            fillOpacity: dim(c.id) ? 0.15 : 0.95,
            opacity: dim(c.id) ? 0.2 : 1,
          }}
          eventHandlers={{ click: () => onSelect(c) }}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <span className="font-mono">{c.label}</span> · {crimeTypeLabel(c.crime_type ?? '')} · {c.district}
            {c.occurred_at && <> · {formatDate(c.occurred_at, 'dd MMM yyyy')}</>}
          </Tooltip>
        </CircleMarker>
      ))}

      {layout.hubs.map(({ node, center }) => (
        <Marker
          key={node.id}
          position={center}
          icon={glyph(node, node.id === selectedId, dim(node.id))}
          zIndexOffset={node.type === 'series' ? 0 : 500}
          eventHandlers={{ click: () => onSelect(node) }}
        >
          <Tooltip direction="top" offset={[0, -12]}>
            {node.type === 'series' ? <span className="font-mono">{node.label}</span> : NODE_LABELS[node.type]} · links {node.case_count ?? node.size} cases
          </Tooltip>
        </Marker>
      ))}
    </MapContainer>
  )
}
