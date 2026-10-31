import { useQuery } from '@tanstack/react-query'
import { Moon, Sun, Sunrise, Sunset } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { mlApi } from '@/services/ml'
import { formatDate, timeAgo } from '@/utils'
import type { RiskLevel, ShiftForecastBlock } from '@/types'

const SHIFT_ICON = { night: Moon, morning: Sunrise, afternoon: Sun, evening: Sunset } as const
const LEVEL_VARIANT: Record<RiskLevel, 'green' | 'amber' | 'red' | 'purple'> = {
  low: 'green',
  medium: 'amber',
  high: 'red',
  critical: 'purple',
}

function ShiftColumn({ block }: { block: ShiftForecastBlock }) {
  const Icon = SHIFT_ICON[block.shift]
  return (
    <div className="bg-bg-elevated rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-text-primary capitalize flex items-center gap-1.5">
          <Icon size={13} /> {block.shift}
        </p>
        <span className="text-2xs text-text-muted">{formatDate(block.block_start, 'HH:mm')}</span>
      </div>
      {block.predictions.slice(0, 4).map((p) => (
        <div key={p.district} className="flex items-center justify-between gap-2">
          <span className="text-xs text-text-secondary truncate">{p.district}</span>
          <Badge size="sm" variant={LEVEL_VARIANT[p.risk_level]}>
            {Math.round(p.probability * 100)}%
          </Badge>
        </div>
      ))}
    </div>
  )
}

/** Next 24 hours by police shift: where to concentrate patrols, with the model version that said so. */
export default function ShiftForecastPanel() {
  const { data } = useQuery({ queryKey: ['ml', 'shift-forecast'], queryFn: mlApi.getShiftForecast, staleTime: 5 * 60_000 })
  const blocks = data?.data ?? []
  const beatsBaseline = data?.metadata?.beats_baseline

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Shift Forecast — Next 24 Hours</p>
        {data?.status === 'ok' && (
          <span className="text-2xs text-text-muted">
            model v{String(data.metadata?.model_version ?? '?')} · {data.generated_at ? timeAgo(data.generated_at) : ''}
          </span>
        )}
      </div>
      {blocks.length > 0 ? (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {blocks.map((block) => <ShiftColumn key={block.block_start} block={block} />)}
          </div>
          {beatsBaseline === false && (
            <p className="text-2xs text-severity-medium mt-3">
              The current model does not outperform the recent-average baseline on held-out data. Treat it as a
              second opinion, not a ranking.
            </p>
          )}
        </>
      ) : (
        <p className="text-xs text-text-muted py-6 text-center">{data?.message ?? 'No forecast yet.'}</p>
      )}
    </div>
  )
}
