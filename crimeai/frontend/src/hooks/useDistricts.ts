import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { crimesApi } from '@/services'

export interface District {
  name: string
  /** Incident-weighted centre, a better start point than the administrative centroid. */
  center: [number, number]
  incidents: number
}

/** Districts that actually have incidents, from the hotspot grid, sorted by name. */
export function useDistricts(): District[] {
  const { data: hotspots } = useQuery({ queryKey: ['hotspots', 'districts'], queryFn: () => crimesApi.hotspots() })
  return useMemo(() => {
    const acc = new Map<string, { lat: number; lng: number; n: number }>()
    for (const h of hotspots ?? []) {
      if (!h.district || h.district === 'Unknown') continue
      const cur = acc.get(h.district) ?? { lat: 0, lng: 0, n: 0 }
      acc.set(h.district, { lat: cur.lat + h.lat * h.count, lng: cur.lng + h.lng * h.count, n: cur.n + h.count })
    }
    return [...acc.entries()]
      .map(([name, v]) => ({ name, center: [v.lat / v.n, v.lng / v.n] as [number, number], incidents: v.n }))
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [hotspots])
}
