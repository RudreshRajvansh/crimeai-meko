import { useEffect, useMemo, useState } from 'react'
import { FlaskConical, Play, ShieldPlus, Users } from 'lucide-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import toast from 'react-hot-toast'
import { getErrorMessage, mlApi } from '@/services'
import { useDistricts } from '@/hooks/useDistricts'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import { cn } from '@/utils'
import { useThemeColors } from '@/lib/theme'
import type { PatrolCurvePoint, SimulationResult, SimulationScenario } from '@/types'

function defaults(scenario?: SimulationScenario): Record<string, unknown> {
  return Object.fromEntries(Object.entries(scenario?.parameters ?? {}).map(([k, spec]) => [k, spec.default]))
}

export default function SimulationPage() {
  const districts = useDistricts()
  const [scenario, setScenario] = useState('patrol_increase')
  const [district, setDistrict] = useState('')
  const [numSims, setNumSims] = useState(200)
  const [params, setParams] = useState<Record<string, unknown>>({ current_officers: 40, additional_officers: 10 })
  const [result, setResult] = useState<SimulationResult | null>(null)

  const { data: scenarios } = useQuery({ queryKey: ['simulation', 'scenarios'], queryFn: mlApi.getScenarios })
  const selectedScenario = scenarios?.find((s) => s.id === scenario)

  useEffect(() => {
    if (!district && districts.length) setDistrict(districts[0].name)
  }, [district, districts])

  const chooseScenario = (id: string) => {
    setScenario(id)
    setParams(defaults(scenarios?.find((s) => s.id === id)))
    setResult(null)
  }
  const setParam = (key: string, value: number) => setParams((p) => ({ ...p, [key]: value }))

  const runMutation = useMutation({
    mutationFn: () => mlApi.runSimulation({ scenario, district, parameters: params, num_simulations: numSims }),
    onSuccess: (data) => {
      if ('status' in data && data.status === 'insufficient_data') {
        toast.error('Not enough recent incidents in this district to simulate.')
        return
      }
      setResult(data)
      toast.success('Simulation complete')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const current = Number(params.current_officers ?? 40)
  const added = Number(params.additional_officers ?? 0)

  return (
    <div className="p-5 space-y-5 animate-fade-in">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="card p-5 space-y-4">
          <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <FlaskConical size={15} /> Scenario Configuration
          </h3>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Scenario</label>
            <select className="input" value={scenario} onChange={(e) => chooseScenario(e.target.value)}>
              {scenarios?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            {selectedScenario && (
              <p className="text-2xs text-text-muted mt-1.5 leading-relaxed">{selectedScenario.description}</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">District</label>
            <select className="input" value={district} onChange={(e) => setDistrict(e.target.value)}>
              {districts.map((d) => <option key={d.name} value={d.name}>{d.name} ({d.incidents})</option>)}
            </select>
          </div>

          {scenario === 'patrol_increase' && (
            <div className="space-y-3 rounded-lg border border-border-subtle bg-bg-primary p-3">
              <div>
                <label htmlFor="current-officers" className="flex items-center gap-1.5 text-xs font-medium text-text-secondary mb-1.5">
                  <Users size={12} /> Officers on patrol now
                </label>
                <input
                  id="current-officers"
                  type="number" min={1} max={500}
                  value={current}
                  onChange={(e) => setParam('current_officers', Math.max(1, Math.min(500, Number(e.target.value) || 1)))}
                  className="input tabular-nums"
                />
              </div>
              <div>
                <label htmlFor="added-officers" className="flex items-center justify-between text-xs font-medium text-text-secondary mb-1.5">
                  <span className="flex items-center gap-1.5"><ShieldPlus size={12} /> Officers to add</span>
                  <span className="tabular-nums text-text-primary">+{added}</span>
                </label>
                <input
                  id="added-officers"
                  type="range" min={0} max={Math.max(60, current)} step={1}
                  value={added}
                  onChange={(e) => setParam('additional_officers', Number(e.target.value))}
                  className="w-full accent-accent-blue"
                />
                <p className="mt-1 text-2xs text-text-muted tabular-nums">
                  {current} → <b className="text-text-primary">{current + added}</b> officers
                  {added > 0 && <> ({Math.round((added / current) * 100)}% more strength)</>}
                </p>
              </div>
            </div>
          )}

          {scenario === 'curfew' && (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">Curfew Duration (days)</label>
              <input
                type="number" min={1} max={30}
                value={Number(params.duration_days ?? 7)}
                onChange={(e) => setParam('duration_days', Number(e.target.value))}
                className="input"
              />
            </div>
          )}

          {scenario === 'tech_deployment' && (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                Coverage: {Number(params.coverage_pct ?? 60)}%
              </label>
              <input
                type="range" min={10} max={100} step={10}
                value={Number(params.coverage_pct ?? 60)}
                onChange={(e) => setParam('coverage_pct', Number(e.target.value))}
                className="w-full accent-accent-blue"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Monte Carlo Trials: {numSims}</label>
            <input
              type="range" min={50} max={500} step={50}
              value={numSims}
              onChange={(e) => setNumSims(Number(e.target.value))}
              className="w-full accent-accent-blue"
            />
            <p className="text-2xs text-text-muted mt-0.5">More trials = more accurate, slower</p>
          </div>

          <button
            onClick={() => runMutation.mutate()}
            disabled={runMutation.isPending || !district}
            className="btn-primary w-full justify-center"
          >
            {runMutation.isPending
              ? <><span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" /> Running…</>
              : <><Play size={13} /> Run Simulation</>}
          </button>
        </div>

        <div className="lg:col-span-2 space-y-4">
          {runMutation.isPending ? (
            <div className="card p-8 flex items-center justify-center">
              <PageLoader label={`Running ${numSims} Monte Carlo trials…`} />
            </div>
          ) : result ? (
            <SimulationResults result={result} />
          ) : (
            <div className="card">
              <EmptyState
                icon={<FlaskConical size={24} />}
                title="Configure and run a simulation"
                description="Pick a district and how many officers to add, then run the simulation."
                className="py-20"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** First staffing level at which one more officer buys less than half of what the first one did. */
function kneeOf(curve: PatrolCurvePoint[]): PatrolCurvePoint | null {
  if (curve.length < 3) return null
  const perOfficer = (a: PatrolCurvePoint, b: PatrolCurvePoint) => (b.reduction_pct - a.reduction_pct) / (b.officers_added - a.officers_added)
  const first = perOfficer(curve[0], curve[1])
  if (first <= 0) return null
  for (let i = 1; i < curve.length - 1; i++) {
    if (perOfficer(curve[i], curve[i + 1]) < first / 2) return curve[i]
  }
  return null
}

function SimulationResults({ result }: { result: SimulationResult }) {
  const theme = useThemeColors()
  const reduction = result.reduction
  const isPositive = reduction.p50_pct > 0
  const meta = result.metadata
  const curve = useMemo(() => meta?.response_curve ?? [], [meta])
  const knee = useMemo(() => kneeOf(curve), [curve])
  const chosen = meta?.officers ? curve.reduce<PatrolCurvePoint | null>(
    (best, p) => (!best || Math.abs(p.officers_added - meta.officers!.added) < Math.abs(best.officers_added - meta.officers!.added) ? p : best),
    null,
  ) : null

  const distributionData = [
    { label: 'Pessimistic (P5)', pct: reduction.p5_pct },
    { label: 'Median (P50)', pct: reduction.p50_pct },
    { label: 'Optimistic (P95)', pct: reduction.p95_pct },
  ]
  const typeData = Object.keys(result.baseline.by_type).slice(0, 8).map((type) => ({
    type: type.replace(/_/g, ' '),
    before: result.baseline.by_type[type] ?? 0,
    after: result.projected.by_type[type] ?? 0,
  }))

  const kpis = [
    { label: 'Median Reduction', value: `${reduction.p50_pct.toFixed(1)}%`, positive: isPositive },
    { label: 'Crimes/day now', value: result.baseline.crimes_per_day.toFixed(1), positive: null },
    { label: 'Crimes/day after', value: result.projected.crimes_per_day.toFixed(1), positive: isPositive },
    ...(meta?.prevented_per_month != null
      ? [
          { label: 'Prevented / month', value: meta.prevented_per_month.toFixed(0), positive: meta.prevented_per_month > 0 },
          { label: 'Per extra officer / month', value: (meta.prevented_per_officer_month ?? 0).toFixed(1), positive: null },
        ]
      : []),
  ]

  return (
    <div className="space-y-4">
      <div className={cn('grid gap-3', kpis.length > 3 ? 'grid-cols-2 sm:grid-cols-5' : 'grid-cols-3')}>
        {kpis.map(({ label, value, positive }) => (
          <div key={label} className="card p-3 text-center">
            <p className="text-2xs text-text-muted mb-1">{label}</p>
            <p className={cn('text-xl font-bold tabular-nums',
              positive === true ? 'text-severity-low' : positive === false ? 'text-severity-high' : 'text-text-primary')}>
              {value}
            </p>
          </div>
        ))}
      </div>

      {curve.length > 1 && meta?.officers && (
        <div className="card p-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Staffing curve · expected reduction by officers added</p>
            <p className="text-2xs text-text-muted tabular-nums">
              {meta.officers.current} on patrol now · plan +{meta.officers.added} ({meta.officers.increase_pct}%)
            </p>
          </div>
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={curve} margin={{ left: -12, right: 12, top: 8, bottom: 4 }}>
              <defs>
                <linearGradient id="curveFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3fb950" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="#3fb950" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
              <XAxis dataKey="officers_added" tick={{ fill: theme.axis, fontSize: 10 }} axisLine={false} tickLine={false}
                     tickFormatter={(v) => `+${v}`} />
              <YAxis tick={{ fill: theme.axis, fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={theme.tooltip}
                labelFormatter={(v) => `+${v} officers`}
                formatter={(v: number, name) => (name === 'reduction_pct' ? [`${v.toFixed(1)}%`, 'Reduction'] : [v.toFixed(2), 'Crimes/day'])}
              />
              {knee && (
                <ReferenceLine x={knee.officers_added} stroke="#d29922" strokeDasharray="4 4"
                               label={{ value: 'diminishing returns', fill: '#d29922', fontSize: 10, position: 'insideTopRight' }} />
              )}
              <Area type="monotone" dataKey="reduction_pct" stroke="#3fb950" strokeWidth={2} fill="url(#curveFill)" />
              {chosen && (
                <ReferenceDot x={chosen.officers_added} y={chosen.reduction_pct} r={5} fill="#58a6ff" stroke={theme.outline} strokeWidth={2} />
              )}
            </AreaChart>
          </ResponsiveContainer>
          <p className="mt-2 text-2xs text-text-muted leading-relaxed">
            Blue dot: your plan.{knee && <> Past about <b className="text-severity-medium">+{knee.officers_added} officers</b>, each extra officer adds less than half the effect of the first ones; spreading them to another district may do more.</>}
            {' '}Patrols mainly deter street crime; cyber fraud and domestic offences barely move.
          </p>
        </div>
      )}

      <div className="card p-4">
        <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">Expected Crime Reduction Distribution</p>
        <div className="flex items-end gap-4 h-28">
          {distributionData.map(({ label, pct }) => (
            <div key={label} className="flex-1 flex flex-col items-center gap-1">
              <span className="text-xs font-bold text-severity-low">{pct.toFixed(1)}%</span>
              <div className="w-full bg-severity-low/30 rounded-t" style={{ height: `${Math.max(8, (pct / 100) * 88)}px` }} />
              <span className="text-2xs text-text-muted text-center leading-tight">{label}</span>
            </div>
          ))}
        </div>
        <p className="text-2xs text-text-muted mt-3">
          95% CI: [{reduction.confidence_interval_95[0].toFixed(1)}, {reduction.confidence_interval_95[1].toFixed(1)}] crimes/day
        </p>
      </div>

      {typeData.length > 0 && (
        <div className="card p-4">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">Before vs After — By Crime Type (crimes/day)</p>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={typeData} margin={{ left: -10, right: 4, top: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} vertical={false} />
              <XAxis dataKey="type" tick={{ fill: theme.axis, fontSize: 9 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: theme.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={theme.tooltip} />
              <Bar dataKey="before" fill="#f85149" name="Before" radius={[2, 2, 0, 0]} />
              <Bar dataKey="after" fill="#3fb950" name="After" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <p className="rounded-md border border-severity-medium/30 bg-severity-medium/10 px-3 py-2 text-2xs leading-relaxed text-text-secondary">
        <b className="text-severity-medium">Scenario illustration, not a forecast.</b> Effect sizes are planning
        assumptions guided by published evaluations (hot-spots policing, CCTV), not estimates calibrated on this
        district. Use it to compare options, not to promise a reduction.
      </p>

      <div className="text-2xs text-text-muted px-1">
        Scenario: <strong>{result.scenario.replace(/_/g, ' ')}</strong> · District: <strong>{result.district}</strong> · {result.num_simulations} trials · Risk: {result.baseline.risk_level} → {result.projected.risk_level}
      </div>
    </div>
  )
}
