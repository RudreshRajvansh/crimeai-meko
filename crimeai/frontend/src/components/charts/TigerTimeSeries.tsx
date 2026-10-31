import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Clock3, Loader2, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'
import CrimeTrendChart from '@/components/charts/CrimeTrendChart'
import { getErrorMessage } from '@/services'
import { insightApi } from '@/services/insight'
import { useThemeColors } from '@/lib/theme'
import { useAuthStore } from '@/store/auth'
import { formatNumber, timeAgo } from '@/utils'

/**
 * The crime time series from Tiger Cloud: every crime mirrored into a TimescaleDB hypertable, with hourly and daily
 * continuous aggregates in Indian time. YugabyteDB stays the record; this card reads only the aggregates.
 */
export default function TigerTimeSeries() {
  const theme = useThemeColors()
  const qc = useQueryClient()
  const canSync = useAuthStore((s) => s.hasRole('analyst'))
  const tiger = useQuery({ queryKey: ['analytics', 'tiger'], queryFn: () => insightApi.tiger() })
  const sync = useMutation({
    mutationFn: insightApi.tigerSync,
    onSuccess: (r) => {
      toast.success(`${r.synced ?? 0} crime(s) mirrored to Tiger Cloud`)
      qc.invalidateQueries({ queryKey: ['analytics', 'tiger'] })
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const data = tiger.data
  const peak = data?.hours?.reduce((best, h) => (h.count > best.count ? h : best), { hour: 0, count: -1 })
  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-text-secondary">
          Time series · Tiger Cloud
        </p>
        {data?.enabled && canSync && (
          <button type="button" className="btn-secondary py-1 text-2xs" disabled={sync.isPending} onClick={() => sync.mutate()}>
            {sync.isPending ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />} Sync now
          </button>
        )}
      </div>
      {tiger.isLoading && <div className="flex h-44 items-center justify-center text-xs text-text-muted"><Loader2 size={14} className="mr-1 animate-spin" />Reading the continuous aggregates…</div>}
      {tiger.error && <p className="text-xs text-severity-high">{getErrorMessage(tiger.error)}</p>}
      {data && !data.enabled && (
        <p className="text-xs text-text-muted">Tiger Cloud is off: set TIGER_DATABASE_URL and run <span className="font-mono">scripts/tiger_setup.py</span>.</p>
      )}
      {data?.enabled && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <p className="mb-1 text-2xs text-text-muted">Crimes per month (crime_daily, last {data.months} months)</p>
            <CrimeTrendChart data={data.monthly ?? []} />
          </div>
          <div>
            <p className="mb-1 flex items-center gap-1 text-2xs text-text-muted">
              <Clock3 size={11} /> Hour of day, IST (crime_hourly, last {data.days} days)
              {peak && peak.count > 0 && <span className="ml-auto text-text-primary">peak {String(peak.hour).padStart(2, '0')}:00</span>}
            </p>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={data.hours} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: theme.axis }} interval={2} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: theme.axis }} allowDecimals={false} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={theme.tooltip} itemStyle={{ color: theme.text }}
                  labelFormatter={(h) => `${String(h).padStart(2, '0')}:00 IST`} />
                <Bar dataKey="count" name="Crimes" fill="#1f6feb" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="text-2xs text-text-muted lg:col-span-2">
            {formatNumber(data.rows ?? 0)} rows in the crime_events hypertable · {data.chunks} chunk{data.chunks === 1 ? '' : 's'}
            {' '}({data.compressed_chunks} compressed) · aggregates {data.aggregates?.join(', ')} · TimescaleDB {data.timescaledb}
            {data.synced_at && <> · synced {timeAgo(data.synced_at)}</>}
          </p>
        </div>
      )}
    </div>
  )
}
