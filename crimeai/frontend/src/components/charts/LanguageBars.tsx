import type { LanguageMix } from '@/types'

/** FIR volume by language, each label shown in its own script. */
export default function LanguageBars({ data }: { data: LanguageMix }) {
  const max = Math.max(...data.counts.map((c) => c.count), 1)
  const total = data.counts.reduce((sum, c) => sum + c.count, 0)

  return (
    <div className="space-y-1.5">
      {data.counts.map((c) => (
        <div key={c.code} className="grid grid-cols-[96px_1fr_44px] items-center gap-3">
          <span className="truncate text-xs text-text-primary" title={c.name}>
            {c.native && c.native !== c.name ? c.native : c.name}
            {c.native && c.native !== c.name && <span className="ml-1 text-2xs text-text-muted">{c.name}</span>}
          </span>
          <span className="h-1.5 overflow-hidden rounded-full bg-bg-elevated">
            <span
              className="block h-full rounded-full bg-accent-blue transition-[width] duration-700 ease-out"
              style={{ width: `${(c.count / max) * 100}%` }}
            />
          </span>
          <span className="text-right text-2xs tabular-nums text-text-secondary">
            {total ? Math.round((c.count / total) * 100) : 0}%
          </span>
        </div>
      ))}
    </div>
  )
}
