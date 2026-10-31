/**
 * Core Leaflet map component.
 * Handles: heatmap layer, crime markers, cluster polygons,
 * click-to-query-nearby, and marker popups.
 */
import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import { AutoResize } from '@/components/map/MapGuards'
import CaseFocusLayer from '@/components/map/CaseFocusLayer'
import type { HeatmapPoint, Crime, ClusterSummary, CaseMap } from '@/types'
import { severityColor, crimeTypeLabel, formatDate, escapeHtml } from '@/utils'
import 'leaflet/dist/leaflet.css'

// Fix Leaflet default icon path issue with Vite
delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

// Default center: New Delhi
const DEFAULT_CENTER: [number, number] = [28.6139, 77.2090]
const DEFAULT_ZOOM = 11

interface CrimeMapProps {
  heatmapPoints?: HeatmapPoint[]
  crimes?: Crime[]
  clusters?: ClusterSummary[]
  showHeatmap?: boolean
  showMarkers?: boolean
  showClusters?: boolean
  onMapClick?: (lat: number, lng: number) => void
  center?: [number, number]
  zoom?: number
  height?: string
  focus?: CaseMap | null
}

export default function CrimeMap({
  heatmapPoints = [],
  crimes = [],
  clusters = [],
  showHeatmap = true,
  showMarkers = true,
  showClusters = false,
  onMapClick,
  center = DEFAULT_CENTER,
  zoom = DEFAULT_ZOOM,
  height = '100%',
  focus = null,
}: CrimeMapProps) {
  return (
    <MapContainer
      center={center}
      zoom={zoom}
      style={{ height, width: '100%' }}
      className="rounded-lg overflow-hidden"
      zoomControl={true}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapController
        heatmapPoints={heatmapPoints}
        crimes={crimes}
        clusters={clusters}
        showHeatmap={showHeatmap}
        showMarkers={showMarkers}
        showClusters={showClusters}
        onMapClick={onMapClick}
      />
      {focus && <CaseFocusLayer focus={focus} />}
    </MapContainer>
  )
}
interface MapControllerProps {
  heatmapPoints: HeatmapPoint[]
  crimes: Crime[]
  clusters: ClusterSummary[]
  showHeatmap: boolean
  showMarkers: boolean
  showClusters: boolean
  onMapClick?: (lat: number, lng: number) => void
}

function MapController({
  heatmapPoints, crimes, clusters,
  showHeatmap, showMarkers, showClusters, onMapClick,
}: MapControllerProps) {
  const map = useMap()
  const heatLayerRef = useRef<L.Layer | null>(null)
  const markersLayerRef = useRef<L.LayerGroup | null>(null)
  const clustersLayerRef = useRef<L.LayerGroup | null>(null)
  useEffect(() => {
    if (!onMapClick) return
    const handler = (e: L.LeafletMouseEvent) => onMapClick(e.latlng.lat, e.latlng.lng)
    map.on('click', handler)
    return () => { map.off('click', handler) }
  }, [map, onMapClick])
  useEffect(() => {
    if (!showHeatmap || heatmapPoints.length === 0) {
      heatLayerRef.current?.remove()
      return
    }

    let cancelled = false
    const draw = async () => {
      // leaflet.heat is a classic plugin that extends the global L; expose it, then load the bundled copy.
      // Bundling (not a CDN script) keeps it working under the production Content-Security-Policy.
      ;(window as unknown as { L: typeof L }).L = L
      await import('leaflet.heat')
      if (cancelled) return
      const size = map.getSize()
      if (size.x === 0 || size.y === 0) return  // canvas would be 0px wide and the plugin throws
      heatLayerRef.current?.remove()
      const points = heatmapPoints.map((p) => [p.lat, p.lng, p.weight] as [number, number, number])
      heatLayerRef.current = (L as unknown as { heatLayer: (p: unknown, o: unknown) => L.Layer }).heatLayer(points, {
        radius: 25,
        blur: 20,
        maxZoom: 17,
        gradient: { 0.2: '#3fb950', 0.5: '#d29922', 0.8: '#f85149', 1.0: '#ff7b72' },
      }).addTo(map)
    }
    map.whenReady(() => { void draw() })

    return () => {
      cancelled = true
      heatLayerRef.current?.remove()
      heatLayerRef.current = null
    }
  }, [map, heatmapPoints, showHeatmap])
  useEffect(() => {
    markersLayerRef.current?.clearLayers()
    if (!showMarkers || crimes.length === 0) return

    if (!markersLayerRef.current) {
      markersLayerRef.current = L.layerGroup().addTo(map)
    }

    crimes.slice(0, 500).forEach((crime) => {
      const color = severityColor(crime.severity)
      const icon = L.divIcon({
        className: '',
        html: `<div style="
          width:10px;height:10px;border-radius:50%;
          background:${color};border:2px solid rgba(255,255,255,0.6);
          box-shadow:0 0 6px ${color}88;
        "></div>`,
        iconSize: [10, 10],
        iconAnchor: [5, 5],
      })

      const marker = L.marker([crime.latitude, crime.longitude], { icon })
      marker.bindPopup(`
        <div style="min-width:180px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">
            ${escapeHtml(crimeTypeLabel(crime.crime_type))}
          </div>
          <div style="font-size:11px;color:rgb(var(--text-secondary));margin-bottom:2px">
            ${escapeHtml(crime.district ?? 'Unknown')} · ${escapeHtml(crime.city)}
          </div>
          <div style="font-size:11px;margin-bottom:4px">
            Severity: <strong style="color:${color}">${crime.severity}/5</strong>
          </div>
          <div style="font-size:11px;color:rgb(var(--text-secondary))">
            ${formatDate(crime.occurred_at, 'dd MMM yyyy HH:mm')}
          </div>
          <div style="font-size:11px;margin-top:4px;color:rgb(var(--text-secondary))">
            ${crime.case_number ? `Case: ${escapeHtml(crime.case_number)}` : ''}
          </div>
          <a href="/cases/${encodeURIComponent(crime.id)}" style="display:inline-block;margin-top:6px;font-size:11px;color:#58a6ff">Open dossier →</a>
        </div>
      `, { maxWidth: 220 })

      markersLayerRef.current!.addLayer(marker)
    })
  }, [map, crimes, showMarkers])
  useEffect(() => {
    clustersLayerRef.current?.clearLayers()
    if (!showClusters || clusters.length === 0) return

    if (!clustersLayerRef.current) {
      clustersLayerRef.current = L.layerGroup().addTo(map)
    }

    clusters.forEach((cluster) => {
      // Draw a circle at centroid sized by cluster count
      const radius = Math.max(500, cluster.size * 150)
      const circle = L.circle(
        [cluster.centroid_lat, cluster.centroid_lng],
        {
          radius,
          color: '#1f6feb',
          fillColor: '#1f6feb',
          fillOpacity: 0.12,
          weight: 1.5,
          dashArray: '4 4',
        }
      )

      // Centroid label
      const label = L.divIcon({
        className: '',
        html: `<div style="
          background:rgba(31,111,235,0.85);color:white;
          border-radius:12px;padding:2px 8px;font-size:11px;
          font-weight:600;white-space:nowrap;border:1px solid rgba(255,255,255,0.3);
        ">Cluster ${cluster.cluster_id} · ${cluster.size}</div>`,
        iconAnchor: [0, 0],
      })
      const labelMarker = L.marker([cluster.centroid_lat, cluster.centroid_lng], { icon: label, zIndexOffset: 100 })

      circle.bindPopup(`
        <div style="min-width:160px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">
            Cluster ${cluster.cluster_id}
          </div>
          <div style="font-size:11px;color:rgb(var(--text-secondary));margin-bottom:2px">${cluster.size} crimes</div>
          <div style="font-size:11px">
            Type: <strong>${escapeHtml(crimeTypeLabel(cluster.dominant_crime_type))}</strong>
          </div>
          <div style="font-size:11px">Avg Severity: ${cluster.avg_severity}</div>
        </div>
      `)

      clustersLayerRef.current!.addLayer(circle)
      clustersLayerRef.current!.addLayer(labelMarker)
    })
  }, [map, clusters, showClusters])

  return <AutoResize />
}
