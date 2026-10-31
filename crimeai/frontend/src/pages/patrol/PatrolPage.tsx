import { useEffect, useMemo, useState } from 'react'
import { Navigation, Target, Zap } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import L from 'leaflet'
import { MapContainer, TileLayer, Polyline, CircleMarker, Marker, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import toast from 'react-hot-toast'
import { getErrorMessage, mlApi } from '@/services'
import { useDistricts } from '@/hooks/useDistricts'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { AutoResize } from '@/components/map/MapGuards'
import { hasSize } from '@/components/map/mapSize'
import { useThemeColors } from '@/lib/theme'
import { cn, riskColor } from '@/utils'
import type { PatrolRoute } from '@/types'

function stopIcon(n: number, color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="width:22px;height:22px;border-radius:50%;background:${color};border:2px solid rgb(var(--bg-primary));
      box-shadow:0 1px 4px rgba(0,0,0,.6);color:#0a0c10;font:700 11px Inter,system-ui,sans-serif;
      display:flex;align-items:center;justify-content:center">${n}</div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  })
}

/** Keeps the whole route in view whenever a new one arrives. */
function FitToRoute({ points }: { points: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length > 1 && hasSize(map)) map.fitBounds(L.latLngBounds(points), { padding: [48, 48] })
  }, [map, points])
  return null
}

function FlyTo({ center }: { center: [number, number] }) {
  const map = useMap()
  useEffect(() => {
    if (!center.every(Number.isFinite)) return
    if (hasSize(map)) map.flyTo(center, Math.max(map.getZoom(), 13), { duration: 0.6 })
    else map.setView(center, Math.max(map.getZoom(), 13), { animate: false })
  }, [map, center])
  return null
}

const STRATEGIES = [
  { value: 'risk_weighted', label: 'Risk Weighted', desc: 'Prioritise high-crime areas' },
  { value: 'coverage',      label: 'Coverage',      desc: 'Maximise geographic spread' },
  { value: 'shortest',      label: 'Shortest',      desc: 'Minimum travel distance' },
]

export default function PatrolPage() {
  const theme = useThemeColors()
  const districts = useDistricts()
  const [district, setDistrict] = useState('Connaught Place')
  const [strategy, setStrategy] = useState('risk_weighted')
  const [numCheckpoints, setNumCheckpoints] = useState(5)
  const [patrolType, setPatrolType] = useState('vehicle')
  const [startPos, setStartPos] = useState<[number, number]>([28.6315, 77.2167])
  const [route, setRoute] = useState<PatrolRoute | null>(null)
  const [pickingStart, setPickingStart] = useState(false)

  const optimizeMutation = useMutation({
    mutationFn: () => mlApi.optimizePatrol({
      start_lat: startPos[0],
      start_lng: startPos[1],
      district,
      strategy,
      num_checkpoints: numCheckpoints,
      patrol_type: patrolType,
    }),
    onSuccess: (data) => {
      setRoute(data)
      toast.success(data.road ? 'Patrol route planned on the road network' : 'Route planned (road routing unavailable, showing straight lines)')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const selectDistrict = (name: string) => {
    setDistrict(name)
    setRoute(null)
    const match = districts.find((d) => d.name === name)
    if (match) setStartPos(match.center)
  }

  const straightPath = useMemo<[number, number][]>(
    () => (route ? [startPos, ...route.checkpoints.map((c) => [c.lat, c.lng] as [number, number])] : []),
    [route, startPos],
  )
  const roadPath = route?.road?.geometry ?? null

  return (
    <div className="flex h-full">
      {/* Config panel */}
      <div className="w-72 border-r border-border-default bg-bg-secondary flex flex-col flex-shrink-0">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Navigation size={15} /> Route Configuration
          </h3>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">District</label>
            <select className="input" value={district} onChange={(e) => selectDistrict(e.target.value)}>
              {districts.map((d) => <option key={d.name} value={d.name}>{d.name} ({d.incidents})</option>)}
            </select>
            <p className="mt-1 text-2xs text-text-muted">The start point moves to the district centre; pick on the map to change it.</p>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-2">Strategy</label>
            <div className="space-y-1.5">
              {STRATEGIES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => setStrategy(s.value)}
                  className={cn(
                    'w-full text-left px-3 py-2 rounded-md border transition-colors text-xs',
                    strategy === s.value
                      ? 'border-accent-blue bg-accent-blue/10 text-text-primary'
                      : 'border-border-subtle bg-bg-tertiary text-text-muted hover:bg-bg-hover'
                  )}
                >
                  <p className="font-medium">{s.label}</p>
                  <p className="text-2xs mt-0.5 opacity-70">{s.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">
              Checkpoints: {numCheckpoints}
            </label>
            <input
              type="range" min={2} max={15} value={numCheckpoints}
              onChange={(e) => setNumCheckpoints(Number(e.target.value))}
              className="w-full accent-accent-blue"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Patrol Type</label>
            <div className="flex gap-2">
              {['vehicle', 'foot'].map((t) => (
                <button
                  key={t}
                  onClick={() => setPatrolType(t)}
                  className={cn(
                    'flex-1 py-1.5 rounded-md text-xs font-medium border transition-colors capitalize',
                    patrolType === t
                      ? 'border-accent-blue bg-accent-blue/10 text-accent-blue'
                      : 'border-border-subtle text-text-muted hover:bg-bg-hover'
                  )}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Start Position</label>
            <p className="text-2xs text-text-muted mb-2">
              {startPos[0].toFixed(4)}, {startPos[1].toFixed(4)}
            </p>
            <button
              onClick={() => setPickingStart((v) => !v)}
              className={cn('btn-secondary text-xs w-full justify-center gap-1.5',
                pickingStart && 'border-accent-blue text-accent-blue')}
            >
              <Target size={12} />
              {pickingStart ? 'Click map to set start' : 'Pick on map'}
            </button>
          </div>
        </div>

        <div className="p-4 border-t border-border-subtle space-y-3">
          <button
            onClick={() => optimizeMutation.mutate()}
            disabled={optimizeMutation.isPending}
            className="btn-primary w-full justify-center"
          >
            {optimizeMutation.isPending
              ? <><span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" /> Optimising…</>
              : <><Zap size={13} /> Optimise Route</>
            }
          </button>

          {route && (
            <div className="card p-3 space-y-1 text-xs">
              <div className="flex justify-between">
                <span className="text-text-muted">{route.road ? 'Road distance' : 'Distance (straight line)'}</span>
                <span className="tabular-nums">{route.total_distance_km.toFixed(1)} km</span>
              </div>
              {route.road && route.straight_line_km != null && (
                <div className="flex justify-between"><span className="text-text-muted">Straight line</span><span className="tabular-nums text-text-muted">{route.straight_line_km.toFixed(1)} km</span></div>
              )}
              <div className="flex justify-between">
                <span className="text-text-muted">{route.road ? `Duration (${route.road.profile === 'foot' ? 'walking' : 'driving'} + stops)` : 'Est. duration'}</span>
                <span className="tabular-nums">{Math.round(route.estimated_duration_minutes)} min</span>
              </div>
              <div className="flex justify-between"><span className="text-text-muted">Stops</span><span className="tabular-nums">{route.checkpoints.length}</span></div>
              <div className="flex justify-between"><span className="text-text-muted">Coverage Radius</span><span className="tabular-nums">{route.coverage_radius_km.toFixed(1)} km</span></div>
            </div>
          )}
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        <MapContainer center={startPos} zoom={12} style={{ height: '100%', width: '100%' }}>
          <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <MapClickHandler pickingStart={pickingStart} onPick={(pos) => { setStartPos(pos); setPickingStart(false) }} />

          {/* Start marker */}
          <CircleMarker center={startPos} radius={8} pathOptions={{ color: '#1f6feb', fillColor: '#1f6feb', fillOpacity: 0.9 }}>
            <Popup>Start position</Popup>
          </CircleMarker>

          <AutoResize />
          <FlyTo center={startPos} />
          <FitToRoute points={roadPath ?? straightPath} />

          {roadPath ? (
            <>
              <Polyline positions={roadPath} pathOptions={{ color: theme.outline, weight: 9, opacity: 0.75, lineJoin: 'round' }} />
              <Polyline positions={roadPath} pathOptions={{ color: '#58a6ff', weight: 5, opacity: 0.95, lineJoin: 'round' }} />
            </>
          ) : (
            straightPath.length > 1 && (
              <Polyline positions={straightPath} pathOptions={{ color: '#1f6feb', weight: 3, dashArray: '8 6', opacity: 0.85 }} />
            )
          )}

          {route?.checkpoints.map((stop, i) => (
            <Marker key={stop.node_id} position={[stop.lat, stop.lng]} icon={stopIcon(i + 1, riskColor(stop.risk_score))}>
              <Tooltip direction="top" offset={[0, -12]}>Stop {i + 1} · risk {stop.risk_score.toFixed(0)}</Tooltip>
              <Popup>
                <div>
                  <p className="font-semibold">Stop {i + 1}: {stop.label}</p>
                  <p className="text-xs">Risk {stop.risk_score.toFixed(0)}/100 · {stop.crime_count} incidents</p>
                  <p className="text-xs">
                    {route.road && (stop as { road_km_from_prev?: number }).road_km_from_prev != null
                      ? `+${(stop as { road_km_from_prev?: number }).road_km_from_prev!.toFixed(2)} km by road, ${(stop as { road_min_from_prev?: number }).road_min_from_prev} min`
                      : `+${stop.distance_from_prev_km.toFixed(2)} km straight line`}
                  </p>
                </div>
              </Popup>
            </Marker>
          ))}
        </MapContainer>

        {optimizeMutation.isPending && (
          <div className="absolute inset-0 bg-bg-primary/60 flex items-center justify-center z-10">
            <PageLoader label="Optimising patrol route…" />
          </div>
        )}

        {route && (
          <div className="absolute bottom-4 left-4 z-[500] card-elevated px-3 py-2 text-2xs text-text-secondary">
            {route.road
              ? <>Route follows the road network ({route.road.profile === 'foot' ? 'walking' : 'driving'}) · OpenStreetMap / OSRM</>
              : <>Road routing unavailable: dashed straight lines show visit order only</>}
          </div>
        )}

        {pickingStart && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 z-10 card-elevated px-4 py-2 text-xs text-accent-blue font-medium">
            Click map to set patrol start position
          </div>
        )}
      </div>
    </div>
  )
}

function MapClickHandler({ pickingStart, onPick }: { pickingStart: boolean; onPick: (pos: [number, number]) => void }) {
  useMapEvents({
    click(e) {
      if (pickingStart) onPick([e.latlng.lat, e.latlng.lng])
    },
  })
  return null
}
