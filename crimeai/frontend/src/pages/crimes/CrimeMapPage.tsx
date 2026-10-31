import { useState, useCallback } from 'react'
import { Layers, Filter, Download, Target, Link2, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import CrimeMap from '@/components/map/CrimeMap'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { useHeatmap, useCrimeList } from '@/hooks/useCrimes'
import { mlApi, crimesApi } from '@/services'
import { insightApi } from '@/services/insight'
import { MATCH_STYLE } from '@/components/map/CaseFocusLayer'
import { cn, crimeTypeLabel } from '@/utils'
import { CRIME_TYPES } from '@/lib/palette'


type MapLayer = 'heatmap' | 'markers' | 'clusters'

export default function CrimeMapPage() {
  const [activeLayers, setActiveLayers] = useState<Set<MapLayer>>(new Set(['heatmap', 'markers']))
  const [selectedType, setSelectedType] = useState<string>('')
  const [clickedLocation, setClickedLocation] = useState<{lat: number; lng: number} | null>(null)
  const [showFilters, setShowFilters] = useState(false)
  const [params, setParams] = useSearchParams()
  const focusId = params.get('focus')
  const { data: focus } = useQuery({
    queryKey: ['case-map', focusId],
    queryFn: () => insightApi.caseMap(focusId!),
    enabled: !!focusId,
  })

  const { data: heatmapData, isLoading: heatLoading } = useHeatmap(
    selectedType ? { crime_type: selectedType } : undefined
  )

  const { data: crimesData, isLoading: crimesLoading } = useCrimeList({
    limit: 500,
    ...(selectedType ? { crime_type: selectedType } : {}),
  })

  const { data: clusterData } = useQuery({
    queryKey: ['ml', 'clusters'],
    queryFn: mlApi.getClusters,
    staleTime: 1000 * 60 * 10,
  })

  const { data: nearbyData, isLoading: nearbyLoading } = useQuery({
    queryKey: ['crimes', 'nearby', clickedLocation],
    queryFn: () => clickedLocation
      ? crimesApi.nearby(clickedLocation.lat, clickedLocation.lng, 1.5, { limit: 20 })
      : Promise.resolve([]),
    enabled: !!clickedLocation,
  })

  const toggleLayer = (layer: MapLayer) => {
    setActiveLayers((prev) => {
      const next = new Set(prev)
      if (next.has(layer)) next.delete(layer)
      else next.add(layer)
      return next
    })
  }

  const handleMapClick = useCallback((lat: number, lng: number) => {
    setClickedLocation({ lat, lng })
  }, [])

  const handleExport = async () => {
    const data = await crimesApi.exportGeoJSON(
      selectedType ? { crime_type: selectedType } : undefined
    )
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/geo+json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'crimes.geojson'; a.click()
    URL.revokeObjectURL(url)
  }

  const isLoading = heatLoading || crimesLoading

  return (
    <div className="flex h-full flex-col md:flex-row">
      {/* Map container */}
      <div className="relative flex-1 min-h-[45vh]">
        {isLoading && (
          <div className="absolute inset-0 z-10 bg-bg-primary/60 flex items-center justify-center">
            <PageLoader label="Loading map data…" />
          </div>
        )}

        {/* Toolbar */}
        <div className="absolute top-3 left-3 z-20 flex flex-col gap-2">
          {/* Layer controls */}
          <div className="card-elevated p-2 flex flex-col gap-1">
            <p className="text-2xs text-text-muted px-1 mb-0.5 font-medium uppercase">Layers</p>
            {(['heatmap', 'markers', 'clusters'] as MapLayer[]).map((layer) => (
              <button
                key={layer}
                onClick={() => toggleLayer(layer)}
                className={cn(
                  'flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors',
                  activeLayers.has(layer)
                    ? 'bg-accent-blue/20 text-accent-blue'
                    : 'text-text-muted hover:text-text-secondary hover:bg-bg-hover'
                )}
              >
                <Layers size={12} />
                <span className="capitalize">{layer}</span>
              </button>
            ))}
          </div>

          {/* Actions */}
          <div className="card-elevated p-2 flex flex-col gap-1">
            <button
              onClick={() => setShowFilters((v) => !v)}
              className={cn('btn-ghost text-xs gap-1', showFilters && 'text-accent-blue')}
            >
              <Filter size={12} /> Filter
            </button>
            <button onClick={handleExport} className="btn-ghost text-xs gap-1">
              <Download size={12} /> GeoJSON
            </button>
          </div>

          {/* Filter panel */}
          {showFilters && (
            <div className="card-elevated p-3 w-44">
              <p className="text-2xs text-text-muted mb-2 font-medium uppercase">Crime Type</p>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="input text-xs"
              >
                <option value="">All types</option>
                {CRIME_TYPES.map((t) => (
                  <option key={t} value={t}>{crimeTypeLabel(t)}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Stats overlay */}
        <div className="absolute top-3 right-3 z-20 card-elevated p-3 text-right">
          <p className="text-2xs text-text-muted">Crimes shown</p>
          <p className="text-lg font-bold text-text-primary">
            {crimesData?.total?.toLocaleString() ?? '—'}
          </p>
          {(clusterData?.data?.num_clusters ?? 0) > 0 && (
            <p className="text-2xs text-accent-blue">{clusterData?.data?.num_clusters} clusters</p>
          )}
        </div>

        <CrimeMap
          heatmapPoints={heatmapData ?? []}
          crimes={crimesData?.items ?? []}
          clusters={activeLayers.has('clusters') ? clusterData?.data?.clusters ?? [] : []}
          showHeatmap={activeLayers.has('heatmap')}
          showMarkers={activeLayers.has('markers')}
          showClusters={activeLayers.has('clusters')}
          onMapClick={handleMapClick}
          height="100%"
          focus={focusId ? focus ?? null : null}
        />
      </div>

      {/* Side panel: one case and what it matches */}
      {focusId && focus && (
        <div className="w-full md:w-80 max-h-[50vh] md:max-h-none border-t md:border-t-0 md:border-l border-border-default bg-bg-secondary flex flex-col flex-shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
            <div className="flex items-center gap-2">
              <Link2 size={14} className="text-accent-purple" />
              <span className="text-sm font-medium">Case matches</span>
            </div>
            <button onClick={() => setParams({})} className="text-text-muted hover:text-text-primary" aria-label="Close"><X size={14} /></button>
          </div>
          <div className="px-4 py-3 border-b border-border-subtle">
            <p className="text-xs font-semibold text-text-primary">{crimeTypeLabel(focus.case.crime_type)} · {focus.case.label}</p>
            <p className="text-2xs text-text-muted">{focus.case.location_name ?? focus.case.district ?? 'Unknown place'}</p>
            <div className="mt-2 grid grid-cols-3 gap-1 text-center">
              {(['identifier', 'series', 'modus_operandi'] as const).map((k) => (
                <div key={k} className="rounded bg-bg-tertiary px-1 py-1.5">
                  <p className="text-base font-bold" style={{ color: MATCH_STYLE[k].color }}>{focus.counts[k]}</p>
                  <p className="text-2xs leading-tight text-text-muted">{MATCH_STYLE[k].label}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto divide-y divide-border-subtle">
            {focus.matches.length === 0 && <p className="p-4 text-xs text-text-muted">No matching cases on record yet.</p>}
            {focus.matches.map((m) => (
              <Link key={m.id} to={`/cases/${m.id}`} className="block px-4 py-3 hover:bg-bg-hover">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-text-primary">{crimeTypeLabel(m.crime_type)}</p>
                  <span className="h-2 w-2 flex-shrink-0 rounded-full" style={{ background: MATCH_STYLE[m.reason].color }} />
                </div>
                <p className="text-2xs text-text-muted mt-0.5">{m.district ?? '—'} · {m.label}</p>
                {m.shared.map((s) => <p key={s} className="text-2xs font-mono text-severity-high">{s}</p>)}
                {m.similarity != null && <p className="text-2xs text-accent-blue">{Math.round(m.similarity * 100)}% alike</p>}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Side panel: nearby crimes on click */}
      {clickedLocation && !focusId && (
        <div className="w-72 border-l border-border-default bg-bg-secondary flex flex-col flex-shrink-0">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
            <div className="flex items-center gap-2">
              <Target size={14} className="text-accent-blue" />
              <span className="text-sm font-medium">Nearby Crimes</span>
            </div>
            <button onClick={() => setClickedLocation(null)} className="text-text-muted hover:text-text-primary text-xs">✕</button>
          </div>
          <div className="flex-1 overflow-y-auto">
            {nearbyLoading ? (
              <div className="flex items-center justify-center h-20"><PageLoader /></div>
            ) : nearbyData && nearbyData.length > 0 ? (
              <div className="divide-y divide-border-subtle">
                {nearbyData.map((crime) => (
                  <div key={crime.id} className="px-4 py-3 hover:bg-bg-hover">
                    <p className="text-xs font-medium text-text-primary">{crimeTypeLabel(crime.crime_type)}</p>
                    <p className="text-2xs text-text-muted mt-0.5">{crime.district} · Sev {crime.severity}</p>
                    <p className="text-2xs text-text-muted">{crime.case_number ?? 'No case #'}</p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex items-center justify-center h-20 text-text-muted text-xs">
                No crimes within 1.5 km
              </div>
            )}
          </div>
          <div className="px-4 py-3 border-t border-border-subtle">
            <p className="text-2xs text-text-muted">
              📍 {clickedLocation.lat.toFixed(4)}, {clickedLocation.lng.toFixed(4)}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
