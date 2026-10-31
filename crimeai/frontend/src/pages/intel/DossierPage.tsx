import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { Circle, CircleMarker, MapContainer, TileLayer } from 'react-leaflet'
import { AlertTriangle, ArrowLeft, Fingerprint, GitBranch, Languages, Network, Orbit, Scale, ShieldCheck } from 'lucide-react'
import HighlightedText, { HighlightLegend } from '@/components/intel/HighlightedText'
import LinkGraph from '@/components/intel/LinkGraph'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { crimeColor, NODE_COLORS, NODE_LABELS } from '@/lib/palette'
import { insightApi } from '@/services/insight'
import { useThemeColors } from '@/lib/theme'
import { cn, crimeTypeLabel, formatDate } from '@/utils'
import type { CustodyDeadline, Dossier } from '@/types'
import EvidencePanel from '@/components/intel/EvidencePanel'

const RTL_SCRIPTS = new Set(['Arabic'])

export default function DossierPage() {
  const theme = useThemeColors()
  const { id = '' } = useParams()
  const { data, isLoading, error } = useQuery({ queryKey: ['dossier', id], queryFn: () => insightApi.dossier(id) })
  const graph = useQuery({
    queryKey: ['graph', 'case', id],
    queryFn: () => insightApi.graphNeighbourhood(`crime:${id}`, 2),
    enabled: Boolean(data),
  })

  if (isLoading) return <PageLoader label="Assembling dossier…" />
  if (error || !data) return <p className="p-6 text-sm text-severity-high">This case could not be loaded.</p>

  const c = data.case
  const kinds = [...new Set(data.narrative.highlights.map((h) => h.kind))]

  return (
    <div className="space-y-4 p-5 animate-fade-in">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/crimes/list" className="inline-flex items-center gap-1 text-2xs text-text-muted hover:text-text-secondary">
            <ArrowLeft size={12} /> Cases
          </Link>
          <h1 className="mt-1 font-mono text-xl font-semibold text-text-primary">{c.case_number}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
            <span className="flex items-center gap-1.5 font-medium text-text-primary">
              <span className="h-2 w-2 rounded-full" style={{ background: crimeColor(c.crime_type) }} />
              {crimeTypeLabel(c.crime_type)}
            </span>
            <span>{c.district} · {c.city}</span>
            <span>{formatDate(c.occurred_at, 'EEE dd MMM yyyy, HH:mm')}</span>
            <span className="capitalize">{c.status.replace('_', ' ')}</span>
            <SeverityPips value={c.severity} />
            {data.fir && <span className="font-mono text-text-muted">{data.fir.fir_number}</span>}
          </p>
        </div>
        <div className="flex items-center gap-4">
          {data.custody && <CustodyRing custody={data.custody} />}
          <Link to="/graph" state={{ node: `crime:${c.id}` }} className="btn-secondary text-xs">
            <Network size={13} /> Link analysis
          </Link>
          <Link to={`/swarm/${c.id}`} className="btn-secondary text-xs">
            <Orbit size={13} /> Swarm
          </Link>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <NarrativeCard data={data} kinds={kinds} />
          {data.legal && data.legal.mapped.length > 0 && <LegalCard data={data} />}
          <EvidencePanel crimeId={c.id} evidence={data.evidence} />
          <SimilarCases data={data} />
        </div>

        <div className="space-y-4">
          <section className="card overflow-hidden">
            <div className="h-56">
              <MapContainer center={[c.latitude, c.longitude]} zoom={14} zoomControl={false} className="h-full w-full" attributionControl={false}>
                <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <Circle center={[c.latitude, c.longitude]} radius={1000} pathOptions={{ color: '#58a6ff', weight: 1, fillOpacity: 0.06, dashArray: '4 4' }} />
                <CircleMarker center={[c.latitude, c.longitude]} radius={7} pathOptions={{ color: theme.outline, weight: 2, fillColor: crimeColor(c.crime_type), fillOpacity: 1 }} />
              </MapContainer>
            </div>
            <dl className="grid grid-cols-2 gap-px bg-border-subtle text-xs">
              <Stat label="Incidents within 1 km, ±30 days" value={data.context.within_1km_30d} />
              <Stat label="Same offence nearby" value={data.context.same_type_within_1km_30d} />
              <Stat label="District rank for this offence" value={data.context.district_rank_for_type ? `#${data.context.district_rank_for_type}` : '—'} />
              <Stat label="Harm weight" value={data.context.harm_weight ?? '—'} />
            </dl>
          </section>

          {data.series && (
            <section className="card p-4">
              <h2 className="flex items-center gap-2 text-xs font-semibold text-text-primary">
                <GitBranch size={14} className="text-severity-high" /> Part of series {data.series.series_id}
              </h2>
              <p className="mt-2 text-xs leading-relaxed text-text-secondary">
                {data.series.size} incidents within {data.series.radius_km.toFixed(1)} km across {data.series.districts.join(', ')}
                {data.series.cross_language && <>, reported in {data.series.languages?.join(' and ')}</>}. MO cohesion{' '}
                <b className="text-text-primary">{data.series.cohesion.toFixed(2)}</b>.
              </p>
              {data.series.next_window && (
                <p className="mt-2 text-xs text-severity-medium">
                  Next incident expected {formatDate(data.series.next_window.from, 'dd MMM')}–{formatDate(data.series.next_window.to, 'dd MMM')}.
                </p>
              )}
            </section>
          )}

          <section className="card p-4">
            <h2 className="flex items-center gap-2 text-xs font-semibold text-text-primary">
              <Fingerprint size={14} /> Linked identifiers
            </h2>
            {data.linked_entities.length ? (
              <ul className="mt-2 space-y-1.5">
                {data.linked_entities.map((e) => (
                  <li key={e.id} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full" style={{ background: NODE_COLORS[e.type] }} />
                      <span className="font-mono text-text-primary">{e.label}</span>
                    </span>
                    <span className={cn('text-2xs', (e.case_count ?? 0) > 1 ? 'text-severity-high' : 'text-text-muted')}>
                      {NODE_LABELS[e.type]} · {e.case_count} case{e.case_count === 1 ? '' : 's'}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-text-muted">No vehicle, phone or UPI identifiers mentioned.</p>
            )}
            {graph.data && graph.data.nodes.length > 1 && (
              <div className="mt-3 rounded-md border border-border-subtle bg-bg-primary">
                <LinkGraph data={graph.data} height={220} selectedId={`crime:${c.id}`} compact />
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

function NarrativeCard({ data, kinds }: { data: Dossier; kinds: string[] }) {
  const lang = data.narrative.language
  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">FIR narrative</h2>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-border-default bg-bg-elevated px-2.5 py-1 text-2xs text-text-primary">
            <Languages size={12} /> {lang.name} · {lang.script}
            <span className="text-text-muted">{Math.round(lang.confidence * 100)}%</span>
          </span>
          {data.narrative.redacted && (
            <span className="inline-flex items-center gap-1 rounded-full bg-severity-low-bg px-2.5 py-1 text-2xs text-severity-low">
              <ShieldCheck size={12} /> Personal data redacted
            </span>
          )}
        </div>
      </div>
      <div className="mt-3 border-l border-border-default pl-4">
        {data.narrative.text ? (
          <HighlightedText
            text={data.narrative.text}
            highlights={data.narrative.highlights}
            dir={RTL_SCRIPTS.has(lang.script) ? 'rtl' : 'ltr'}
          />
        ) : (
          <p className="text-sm text-text-muted">No narrative recorded for this case.</p>
        )}
      </div>
      {kinds.length > 0 && (
        <div className="mt-4 flex items-center gap-3">
          <span className="text-2xs text-text-muted">Recognised:</span>
          <HighlightLegend kinds={kinds} />
        </div>
      )}
    </section>
  )
}

function LegalCard({ data }: { data: Dossier }) {
  const legal = data.legal!
  return (
    <section className="card p-5">
      <h2 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">
        <Scale size={13} /> Sections · governed by {legal.governing_code}
      </h2>
      <div className="mt-3 divide-y divide-border-subtle">
        {legal.mapped.map((m, i) => (
          <div key={i} className="grid grid-cols-[1fr_auto_1fr_2fr] items-center gap-3 py-2 text-xs">
            <span className="font-mono text-text-secondary">{m.ipc ? `IPC ${m.ipc}` : '—'}</span>
            <span className="text-text-muted">→</span>
            <span className="font-mono text-accent-purple">{m.bns ? `BNS ${m.bns}` : 'no equivalent'}</span>
            <span className="text-text-primary">{m.offence ?? m.note}</span>
          </div>
        ))}
      </div>
      {legal.warnings.map((w) => (
        <p key={w} className="mt-2 flex items-start gap-1.5 text-xs text-severity-medium">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {w}
        </p>
      ))}
    </section>
  )
}

function SimilarCases({ data }: { data: Dossier }) {
  return (
    <section className="card p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Similar modus operandi</h2>
      <p className="mt-1 text-2xs text-text-muted">Multilingual semantic match on redacted narratives; language of the report does not matter.</p>
      <ul className="mt-3 space-y-2">
        {data.similar_cases.map((s) => (
          <li key={s.id}>
            <Link to={`/cases/${s.id}`} className="grid grid-cols-[1fr_120px] items-center gap-4 rounded-md px-2 py-2 hover:bg-bg-hover">
              <span className="min-w-0">
                <span className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-text-primary">{s.case_number}</span>
                  <span className="text-text-muted">{crimeTypeLabel(s.crime_type)} · {s.district}</span>
                  {s.series_id && <span className="rounded bg-severity-high-bg px-1.5 text-2xs text-severity-high">series</span>}
                </span>
                <span className="mt-0.5 block truncate text-2xs text-text-secondary">{s.description}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-elevated">
                  <span className="block h-full rounded-full bg-accent-blue" style={{ width: `${Math.max(0, (s.similarity - 0.7) / 0.3) * 100}%` }} />
                </span>
                <span className="w-9 text-right text-2xs tabular-nums text-text-secondary">{s.similarity.toFixed(2)}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-bg-secondary p-3">
      <dd className="text-base font-semibold tabular-nums text-text-primary">{value}</dd>
      <dt className="mt-0.5 text-2xs text-text-muted">{label}</dt>
    </div>
  )
}

function SeverityPips({ value }: { value: number }) {
  return (
    <span className="flex items-center gap-0.5" aria-label={`Severity ${value} of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={cn('h-2.5 w-1 rounded-sm', i <= value ? 'bg-severity-high' : 'bg-bg-hover')} />
      ))}
    </span>
  )
}

function CustodyRing({ custody }: { custody: CustodyDeadline }) {
  const elapsed = custody.limit_days - custody.days_remaining
  const fraction = Math.min(Math.max(elapsed / custody.limit_days, 0), 1)
  const r = 22
  const circumference = 2 * Math.PI * r
  const color = custody.days_remaining <= 2 ? '#f85149' : custody.days_remaining <= 7 ? '#ffa657' : '#d29922'
  return (
    <div className="flex items-center gap-3" title={`Chargesheet due ${formatDate(custody.deadline, 'dd MMM yyyy')}`}>
      <svg width="56" height="56" viewBox="0 0 56 56" role="img" aria-label={`${custody.days_remaining} days left`}>
        <circle cx="28" cy="28" r={r} fill="none" className="stroke-border-subtle" strokeWidth="5" />
        <circle
          cx="28" cy="28" r={r} fill="none" stroke={color} strokeWidth="5" strokeLinecap="round"
          strokeDasharray={circumference} strokeDashoffset={circumference * (1 - fraction)}
          transform="rotate(-90 28 28)"
        />
        <text x="28" y="31" textAnchor="middle" className="fill-text-primary text-[13px] font-semibold tabular-nums">
          {Math.max(custody.days_remaining, 0)}
        </text>
      </svg>
      <div className="text-2xs leading-tight">
        <p className="font-semibold text-text-primary">days to chargesheet</p>
        <p className="text-text-muted">
          {custody.limit_days}-day limit · BNSS 187(3) · from {custody.clock_starts === 'remand' ? 'first remand' : 'arrest (approx.)'}
        </p>
        {custody.needs_verification && <p className="text-severity-medium">Verify track: {custody.track_note}</p>}
      </div>
    </div>
  )
}
