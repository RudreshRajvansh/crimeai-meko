import { AlertTriangle, Shield, Clock, Activity, MapPin, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import StatCard from '@/components/ui/StatCard'
import CrimeTypeChart from '@/components/charts/CrimeTypeChart'
import CrimeTrendChart from '@/components/charts/CrimeTrendChart'
import RiskBarChart from '@/components/charts/RiskBarChart'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { useCrimeStats } from '@/hooks/useCrimes'
import { useAlerts } from '@/hooks/useAlerts'
import { mlApi } from '@/services/ml'
import { formatNumber, timeAgo, severityBadgeClass } from '@/utils'
import ShiftForecastPanel from '@/components/intel/ShiftForecastPanel'
import TemporalHeatGrid from '@/components/charts/TemporalHeatGrid'
import LanguageBars from '@/components/charts/LanguageBars'
import { insightApi } from '@/services/insight'

export default function DashboardPage() {
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useCrimeStats()
  const { data: alertsData } = useAlerts({ limit: 5, is_resolved: false })
  const { data: riskMapData } = useQuery({
    queryKey: ['ml', 'risk-map'],
    queryFn: mlApi.getRiskMap,
    staleTime: 1000 * 60 * 5,
  })

  const { data: matrix } = useQuery({ queryKey: ['analytics', 'matrix'], queryFn: () => insightApi.temporalMatrix() })
  const { data: languages } = useQuery({ queryKey: ['analytics', 'languages'], queryFn: insightApi.languages })

  if (statsLoading) return <PageLoader label="Loading dashboard…" />

  return (
    <div className="p-5 space-y-5 animate-fade-in">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-text-primary">Operations Overview</h2>
          <p className="text-xs text-text-muted mt-0.5">Real-time crime intelligence dashboard</p>
        </div>
        <button
          onClick={() => refetchStats()}
          className="btn-ghost text-xs gap-1.5"
        >
          <RefreshCw size={12} />
          Refresh
        </button>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          label="Total Crimes"
          value={stats?.total_crimes ?? 0}
          icon={<AlertTriangle size={16} />}
          color="red"
          loading={statsLoading}
        />
        <StatCard
          label="Avg Daily Rate"
          value={stats?.avg_daily_crimes ?? 0}
          suffix="/ day"
          icon={<Activity size={16} />}
          color="amber"
          loading={statsLoading}
        />
        <StatCard
          label="Unread Alerts"
          value={alertsData?.unread_count ?? 0}
          icon={<Shield size={16} />}
          color="blue"
          loading={!alertsData}
        />
        <StatCard
          label="Peak Hour"
          value={stats?.most_active_hour !== undefined ? `${stats.most_active_hour}:00` : '—'}
          icon={<Clock size={16} />}
          color="purple"
          loading={statsLoading}
        />
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Crime trend */}
        <div className="card p-4 lg:col-span-2">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">
            Crime Trend — Last 12 Months
          </p>
          {stats?.by_month ? (
            <CrimeTrendChart data={stats.by_month} />
          ) : (
            <div className="h-44 flex items-center justify-center text-text-muted text-xs">No trend data</div>
          )}
        </div>

        {/* Crime types donut */}
        <div className="card p-4">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">
            By Crime Type
          </p>
          {stats?.by_type ? (
            <CrimeTypeChart data={stats.by_type} />
          ) : (
            <div className="h-44 flex items-center justify-center text-text-muted text-xs">No data</div>
          )}
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Risk map */}
        <div className="card p-4 lg:col-span-2">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">
            District Risk Index (0-100, absolute)
          </p>
          {riskMapData?.data && Object.keys(riskMapData.data).length > 0 ? (
            <RiskBarChart data={riskMapData.data} />
          ) : (
            <div className="h-44 flex flex-col items-center justify-center text-text-muted text-xs gap-2">
              <MapPin size={20} className="opacity-30" />
              <span>No risk data — run hotspot prediction first</span>
            </div>
          )}
        </div>

        {/* Recent alerts */}
        <div className="card p-4">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">
            Recent Alerts
          </p>
          {alertsData?.items && alertsData.items.length > 0 ? (
            <div className="space-y-2">
              {alertsData.items.slice(0, 5).map((alert) => (
                <div key={alert.id} className="flex items-start gap-2 py-1.5 border-b border-border-subtle last:border-0">
                  <span className={severityBadgeClass(alert.severity)}>{alert.severity}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-text-primary truncate">{alert.title}</p>
                    <p className="text-2xs text-text-muted">{timeAgo(alert.created_at)}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-32 text-text-muted text-xs">
              No active alerts
            </div>
          )}
        </div>
      </div>

      <ShiftForecastPanel />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-text-secondary">When incidents happen (last 12 months)</p>
          {matrix ? <TemporalHeatGrid data={matrix} /> : <div className="h-40" />}
        </div>
        <div className="card p-4">
          <p className="mb-1 text-xs font-medium uppercase tracking-wider text-text-secondary">FIR languages</p>
          <p className="mb-3 text-2xs text-text-muted">{languages ? `${languages.supported.length - 1} Indian languages supported · ${languages.embedding_model}` : ''}</p>
          {languages ? <LanguageBars data={languages} /> : <div className="h-40" />}
        </div>
      </div>

      {/* Crime breakdown table */}
      <div className="card p-4">
        <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">
          Crime Breakdown by District
        </p>
        <div className="table-wrapper">
          <table className="table-base">
            <thead className="table-head">
              <tr>
                <th className="table-th">District</th>
                <th className="table-th text-right">Crimes</th>
                <th className="table-th text-right">Share</th>
              </tr>
            </thead>
            <tbody>
              {stats && Object.entries(stats.by_district)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 8)
                .map(([district, count]) => (
                  <tr key={district} className="table-row">
                    <td className="table-td font-medium">{district}</td>
                    <td className="table-td text-right tabular-nums">{formatNumber(count)}</td>
                    <td className="table-td text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                          <div
                            className="h-full bg-accent-blue rounded-full"
                            style={{ width: `${(count / stats.total_crimes) * 100}%` }}
                          />
                        </div>
                        <span className="text-2xs text-text-muted tabular-nums w-8 text-right">
                          {((count / stats.total_crimes) * 100).toFixed(1)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
