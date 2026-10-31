import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { CalendarClock, Download, GitBranch, Radar } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { getErrorMessage } from '@/services/api'
import { intelApi } from '@/services/intel'
import { useAuthStore } from '@/store/auth'
import { cn, crimeTypeLabel, formatDate, timeAgo } from '@/utils'
import type { CrimeSeries, CustodyDeadline } from '@/types'

type Tab = 'series' | 'custody'

export default function IntelPage() {
  const isOfficer = useAuthStore((s) => s.hasRole('police'))
  const [tab, setTab] = useState<Tab>('series')

  const downloadBriefing = useMutation({
    mutationFn: intelApi.downloadBriefing,
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `daily-briefing-${new Date().toISOString().slice(0, 10)}.pdf`
      link.click()
      URL.revokeObjectURL(url)
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
          {(['series', ...(isOfficer ? ['custody'] : [])] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                'px-4 py-1.5 rounded-md text-sm font-medium transition-colors',
                tab === t ? 'bg-bg-elevated text-text-primary' : 'text-text-muted hover:text-text-secondary',
              )}
            >
              {t === 'series' ? 'Crime Series' : 'Custody Deadlines'}
            </button>
          ))}
        </div>
        {isOfficer && (
          <button
            onClick={() => downloadBriefing.mutate()}
            disabled={downloadBriefing.isPending}
            className="btn-secondary text-xs gap-1.5"
          >
            <Download size={13} /> Daily briefing (PDF)
          </button>
        )}
      </div>
      {tab === 'series' ? <SeriesTab /> : <CustodyTab />}
    </div>
  )
}

function SeriesTab() {
  const [windowDays, setWindowDays] = useState(30)
  const { data, isLoading } = useQuery({
    queryKey: ['intel', 'series', windowDays],
    queryFn: () => intelApi.series(windowDays),
  })
  const detect = useMutation({
    mutationFn: intelApi.detectSeries,
    onSuccess: () => toast.success('Series detection queued'),
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  if (isLoading) return <PageLoader />
  const series = data?.data ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-muted max-w-2xl">
          Incidents of the same type, close in space and time, with similar modus operandi, are linked into candidate
          series, including across police-station boundaries. Each one is a lead for an analyst to confirm, not a
          finding.
        </p>
        <div className="flex items-center gap-2">
          <select
            value={windowDays}
            onChange={(e) => setWindowDays(Number(e.target.value))}
            className="input text-xs py-1"
            aria-label="Active within"
          >
            {[7, 30, 90].map((d) => <option key={d} value={d}>Active in last {d} days</option>)}
          </select>
          <button onClick={() => detect.mutate()} className="btn-ghost text-xs gap-1.5">
            <Radar size={13} /> Re-run
          </button>
        </div>
      </div>
      {series.length === 0 ? (
        <div className="card p-10 text-center text-xs text-text-muted">{data?.message ?? 'No active series.'}</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {series.map((s) => <SeriesCard key={s.series_id} series={s} />)}
        </div>
      )}
    </div>
  )
}

function SeriesCard({ series }: { series: CrimeSeries }) {
  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <GitBranch size={14} /> {series.size} linked {crimeTypeLabel(series.crime_type).toLowerCase()} incidents
          </p>
          <p className="text-2xs text-text-muted font-mono mt-0.5">{series.series_id}</p>
        </div>
        {series.cross_jurisdiction && <Badge variant="red" size="sm">Cross-station</Badge>}
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <Metric label="Areas" value={series.districts.join(', ') || '—'} />
        <Metric label="Footprint" value={`${series.radius_km.toFixed(1)} km`} />
        <Metric label="MO cohesion" value={series.cohesion.toFixed(2)} />
        <Metric label="First seen" value={formatDate(series.first_seen, 'dd MMM')} />
        <Metric label="Last seen" value={timeAgo(series.last_seen)} />
        <Metric label="Cadence" value={series.median_gap_days ? `~${series.median_gap_days.toFixed(1)} days` : '—'} />
      </div>
      {series.next_window && (new Date(series.next_window.to) < new Date() ? (
        <p className="text-xs text-text-muted">
          Expected window {formatDate(series.next_window.from, 'dd MMM')} – {formatDate(series.next_window.to, 'dd MMM')} passed
          with no linked incident: the pattern may have stopped or moved.
        </p>
      ) : (
        <p className="text-xs text-severity-medium">
          If the pattern holds, next incident expected {formatDate(series.next_window.from, 'dd MMM')} –{' '}
          {formatDate(series.next_window.to, 'dd MMM')} near {series.centroid.lat.toFixed(4)},{' '}
          {series.centroid.lng.toFixed(4)}.
        </p>
      ))}
      {series.key_terms.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {series.key_terms.map((term) => <Badge key={term} size="sm" variant="gray">{term}</Badge>)}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-2xs text-text-muted">{label}</p>
      <p className="text-text-primary truncate" title={value}>{value}</p>
    </div>
  )
}

const STATUS_VARIANT: Record<CustodyDeadline['status'], 'red' | 'amber' | 'green'> = {
  overdue: 'red',
  due_soon: 'amber',
  on_track: 'green',
}

function CustodyTab() {
  const { data, isLoading } = useQuery({ queryKey: ['intel', 'custody'], queryFn: () => intelApi.custodyDeadlines() })
  if (isLoading) return <PageLoader />

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <div className="card p-3"><p className="text-2xs text-text-muted">Open custody cases</p><p className="text-lg font-bold">{data?.total ?? 0}</p></div>
        <div className="card p-3"><p className="text-2xs text-text-muted">Due within 15 days</p><p className="text-lg font-bold text-severity-medium">{data?.due_soon ?? 0}</p></div>
        <div className="card p-3"><p className="text-2xs text-text-muted">Overdue</p><p className="text-lg font-bold text-severity-high">{data?.overdue ?? 0}</p></div>
      </div>
      <p className="text-2xs text-text-muted flex items-center gap-1.5"><CalendarClock size={12} /> {data?.basis}</p>
      <div className="table-wrapper">
        <table className="table-base">
          <thead className="table-head">
            <tr>
              <th className="table-th">Case</th>
              <th className="table-th">Offence</th>
              <th className="table-th">District</th>
              <th className="table-th">In custody since</th>
              <th className="table-th">Limit</th>
              <th className="table-th">Deadline</th>
              <th className="table-th text-right">Days left</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.crime_id} className="table-row">
                <td className="table-td font-mono text-xs">{c.case_number ?? c.crime_id.slice(0, 8)}</td>
                <td className="table-td text-xs">{crimeTypeLabel(c.crime_type)}</td>
                <td className="table-td text-xs text-text-secondary">{c.district ?? '—'}</td>
                <td className="table-td text-xs">{formatDate(c.arrested_at, 'dd MMM yyyy')}</td>
                <td className="table-td text-xs">
                  {c.limit_days} days
                  {c.needs_verification && (
                    <span title={c.track_note ?? undefined} className="ml-1.5 rounded bg-severity-medium/15 px-1 py-0.5 text-2xs text-severity-medium">verify track</span>
                  )}
                  {c.approximate && (
                    <span title="No remand date recorded; counted from arrest" className="ml-1 rounded bg-bg-elevated px-1 py-0.5 text-2xs text-text-muted">approx.</span>
                  )}
                </td>
                <td className="table-td text-xs">{formatDate(c.deadline, 'dd MMM yyyy')}</td>
                <td className="table-td text-right">
                  <Badge size="sm" variant={STATUS_VARIANT[c.status]}>
                    {c.days_remaining < 0 ? `${-c.days_remaining} overdue` : c.days_remaining}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
