import { useState } from 'react'
import type { TemporalMatrix } from '@/types'

const SHIFT_BREAKS = [6, 12, 18]

function cellColor(value: number, max: number): string {
  if (!value || !max) return 'rgba(48,54,61,0.35)'
  const t = Math.sqrt(value / max)
  return `rgba(88,166,255,${0.12 + t * 0.88})`
}

/** Weekday x hour grid in local time, with police-shift boundaries marked, so peak patrol windows read at a glance. */
export default function TemporalHeatGrid({ data }: { data: TemporalMatrix }) {
  const [hover, setHover] = useState<{ d: number; h: number } | null>(null)
  const value = hover ? data.matrix[hover.d][hover.h] : null

  return (
    <div className="space-y-2">
      <div className="grid gap-[3px]" style={{ gridTemplateColumns: '32px repeat(24, minmax(0, 1fr))' }}>
        <span />
        {Array.from({ length: 24 }, (_, h) => (
          <span key={h} className="text-center text-2xs tabular-nums text-text-muted">
            {h % 3 === 0 ? String(h).padStart(2, '0') : ''}
          </span>
        ))}
        {data.matrix.map((row, d) => (
          <div key={d} className="contents">
            <span className="self-center text-2xs text-text-secondary">{data.days[d]}</span>
            {row.map((n, h) => {
              const isPeak = d === data.peak.day && h === data.peak.hour
              return (
                <button
                  key={h}
                  type="button"
                  aria-label={`${data.days[d]} ${String(h).padStart(2, '0')}:00, ${n} incidents`}
                  onMouseEnter={() => setHover({ d, h })}
                  onMouseLeave={() => setHover(null)}
                  onFocus={() => setHover({ d, h })}
                  className="aspect-square rounded-[3px] outline-none transition-transform hover:scale-125 focus-visible:ring-1 focus-visible:ring-text-primary"
                  style={{
                    background: cellColor(n, data.max),
                    boxShadow: isPeak ? '0 0 0 1.5px #f85149' : undefined,
                    marginLeft: SHIFT_BREAKS.includes(h) ? 3 : undefined,
                  }}
                />
              )
            })}
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between text-2xs text-text-muted">
        <span className="tabular-nums">
          {hover && value !== null
            ? `${data.days[hover.d]} ${String(hover.h).padStart(2, '0')}:00–${String((hover.h + 1) % 24).padStart(2, '0')}:00 · ${value} incidents`
            : `Peak: ${data.days[data.peak.day]} ${String(data.peak.hour).padStart(2, '0')}:00 (${data.peak.count})`}
        </span>
        <span className="flex items-center gap-1.5">
          Fewer
          {[0.1, 0.35, 0.6, 1].map((t) => (
            <span key={t} className="h-2.5 w-2.5 rounded-[2px]" style={{ background: cellColor(t * data.max, data.max) }} />
          ))}
          More · {data.timezone}
        </span>
      </div>
    </div>
  )
}
