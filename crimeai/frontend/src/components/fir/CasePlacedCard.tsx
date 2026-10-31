import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Loader2, MapPin } from 'lucide-react'
import { firApi } from '@/services/fir'
import { insightApi } from '@/services/insight'

// Follows a just-filed FIR through the worker until its case is on the map, then shows what it matched.
export default function CasePlacedCard({ firId, firNumber }: { firId: string; firNumber: string }) {
  const navigate = useNavigate()
  const fir = useQuery({
    queryKey: ['fir', 'track', firId],
    queryFn: () => firApi.get(firId),
    refetchInterval: (q) => (['completed', 'failed'].includes(q.state.data?.nlp_status ?? '') ? false : 2000),
  })
  const crimeId = fir.data?.crime_id
  const done = fir.data?.nlp_status === 'completed'
  const matches = useQuery({
    queryKey: ['case-map', crimeId],
    queryFn: () => insightApi.caseMap(crimeId!),
    enabled: !!crimeId && done,
    // The narrative embedding lands a moment after the case; look once more for similar cases.
    refetchInterval: (q) => ((q.state.dataUpdateCount ?? 0) < 3 ? 3000 : false),
  })

  if (fir.data?.nlp_status === 'failed') {
    return <p className="rounded-lg bg-severity-high-bg p-3 text-xs text-severity-high">FIR {firNumber} could not be analysed.</p>
  }
  if (!done || !crimeId) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-border-subtle bg-bg-tertiary p-3 text-xs text-text-secondary">
        <Loader2 size={13} className="animate-spin text-accent-blue" />
        {done ? `FIR ${firNumber} analysed; no place could be read for the map.` : `Analysing FIR ${firNumber}, linking it and placing it on the map…`}
      </div>
    )
  }
  const counts = matches.data?.counts
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-accent-purple/40 bg-accent-purple/10 p-3">
      <div className="text-xs">
        <p className="flex items-center gap-1.5 font-semibold text-accent-purple"><MapPin size={13} /> Case {firNumber} is on the map</p>
        <p className="mt-0.5 text-text-secondary">
          {counts
            ? `${counts.identifier} linked by phone/UPI/vehicle · ${counts.series} in series · ${counts.modus_operandi} with similar MO`
            : 'Finding matching cases…'}
        </p>
      </div>
      <button onClick={() => navigate(`/crimes?focus=${crimeId}`)} className="btn-primary flex-shrink-0 text-xs">
        Show on map
      </button>
    </div>
  )
}
