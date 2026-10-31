import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import L from 'leaflet'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { Area, AreaChart, ResponsiveContainer, Tooltip as ChartTip, XAxis, YAxis } from 'recharts'
import { Pause, Play, RotateCcw, Shield, ShieldOff, Siren, Snowflake } from 'lucide-react'
import { AutoResize } from '@/components/map/MapGuards'
import { hasSize } from '@/components/map/mapSize'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { NODE_COLORS } from '@/lib/palette'
import { intelApi } from '@/services/intel'
import { cn, crimeTypeLabel } from '@/utils'
import type { SwarmEvent, SwarmResult } from '@/types'

const HIT = '#f85149'
const STOP_PATROL = '#58a6ff'
const STOP_FREEZE = '#a371f7'
const SPEEDS = [3, 8, 20]

/** MiroFish-style swarm: hundreds of simulated futures for one case's linked pattern, replayed as agents on a map. */
export default function SwarmPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const seeds = useQuery({ queryKey: ['swarm', 'seeds'], queryFn: intelApi.swarmSeeds })
  const crimeId = id ?? seeds.data?.[0]?.crime_id
  const [days, setDays] = useState(14)
  const [patrols, setPatrols] = useState(4)
  const [freeze, setFreeze] = useState(true)

  const sim = useQuery({
    queryKey: ['swarm', crimeId, days, patrols, freeze],
    queryFn: () => intelApi.swarm(crimeId!, { days, patrols, freeze }),
    enabled: !!crimeId,
    placeholderData: (prev) => prev,
  })

  return (
    <div className="flex h-full flex-col gap-3 p-4 animate-fade-in">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {seeds.data?.map((s) => (
          <button key={s.crime_id} type="button" onClick={() => navigate(`/swarm/${s.crime_id}`)}
                  className={cn('flex shrink-0 items-center gap-2 rounded-lg border px-3 py-1.5 text-xs transition-colors',
                    s.crime_id === crimeId ? 'border-accent-blue bg-accent-blue/10 text-text-primary' : 'border-border-subtle bg-bg-secondary text-text-secondary hover:border-border-default')}>
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: NODE_COLORS[s.kind] ?? '#8b949e' }} />
            <span className="font-mono">{s.identifier}</span>
            <span className="rounded bg-bg-elevated px-1 tabular-nums text-text-muted">{s.cases}</span>
          </button>
        ))}
      </div>

      {!sim.data ? <PageLoader label="Spawning agents…" /> : (
        <div className="grid min-h-0 flex-1 gap-3 lg:grid-cols-[1fr_340px]">
          <Theatre key={`${sim.data.seed_case.id}-${days}-${patrols}-${freeze}`} result={sim.data} busy={sim.isFetching} />
          <div className="flex min-h-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
            <Controls days={days} setDays={setDays} patrols={patrols} setPatrols={setPatrols} freeze={freeze} setFreeze={setFreeze}
                      street={sim.data.params.street_pattern} money={sim.data.agents.some((a) => a.kind === 'upi' || a.kind === 'account')} />
            <Outlook r={sim.data} />
            <Curve r={sim.data} />
            <div className="grid grid-cols-2 gap-3">
              <Clock hours={sim.data.hours} />
              <Districts r={sim.data} />
            </div>
            <Agents r={sim.data} />
          </div>
        </div>
      )}
    </div>
  )
}

function Theatre({ result: r, busy }: { result: SwarmResult; busy: boolean }) {
  const [sample, setSample] = useState(0)
  const [playing, setPlaying] = useState(true)
  const [speed, setSpeed] = useState(1)
  const [t, setT] = useState(0)
  const horizon = r.params.days * 24
  const events = r.samples[sample] ?? []
  const fired = events.filter((e) => e.t <= t)

  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      setT((prev) => (prev + dt * SPEEDS[speed] >= horizon ? 0 : prev + dt * SPEEDS[speed]))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed, horizon])

  const day = Math.floor(t / 24) + 1
  const hour = Math.floor(t % 24)

  return (
    <div className="card relative flex min-h-[460px] flex-col overflow-hidden p-0">
      <div className="relative min-h-0 flex-1">
        <MapContainer center={[28.61, 77.15]} zoom={11} className="h-full w-full" zoomControl={false}>
          <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                     url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <AutoResize />
          <Fit r={r} />
          {r.heat.map((h, i) => (
            <CircleMarker key={i} center={[h.lat, h.lng]} radius={4 + Math.sqrt(h.w) * 2.2} interactive={false}
                          pathOptions={{ stroke: false, fillColor: '#f0883e', fillOpacity: 0.07 + Math.min(h.w, 20) * 0.006 }} />
          ))}
          {r.agents.map((a) => a.case_ids.map((cid) => {
            const c = r.cases.find((x) => x.id === cid)
            return c && (
              <Polyline key={`${a.id}-${cid}`} positions={[a.anchor, [c.lat, c.lng]]} interactive={false}
                        pathOptions={{ color: NODE_COLORS[a.kind] ?? '#8b949e', weight: 1, opacity: 0.35, dashArray: '3 5' }} />
            )
          }))}
          {r.cases.map((c) => (
            <CircleMarker key={c.id} center={[c.lat, c.lng]} radius={c.id === r.seed_case.id ? 8 : 5}
                          pathOptions={{ color: '#fff', weight: c.id === r.seed_case.id ? 3 : 1.5, fillColor: '#0d1117', fillOpacity: 0.9 }}>
              <Tooltip>{c.case_number} · {crimeTypeLabel(c.type)} · {c.district}</Tooltip>
            </CircleMarker>
          ))}
          <Swarm r={r} events={events} t={t} />
        </MapContainer>

        <div className="pointer-events-none absolute left-3 top-3 z-[500] rounded-lg border border-border-subtle bg-bg-primary/80 px-3 py-2 backdrop-blur">
          <p className="font-mono text-2xl font-bold tabular-nums text-text-primary">D{day} · {String(hour).padStart(2, '0')}:00</p>
          <div className="mt-1 flex gap-3 text-2xs font-semibold tabular-nums">
            <span style={{ color: HIT }}>● {fired.filter((e) => !e.stopped).length} hits</span>
            <span style={{ color: STOP_PATROL }}>■ {fired.filter((e) => e.stopped === 'patrol').length}</span>
            <span style={{ color: STOP_FREEZE }}>◆ {fired.filter((e) => e.stopped === 'freeze').length}</span>
          </div>
        </div>
        <div className="absolute right-3 top-3 z-[500] flex max-h-[45%] w-48 flex-col-reverse gap-1 overflow-hidden">
          {fired.slice(-7).map((e, i) => <FeedItem key={`${e.t}-${i}`} e={e} r={r} />)}
        </div>
        {busy && <div className="absolute inset-x-0 top-0 z-[500] h-0.5 animate-pulse bg-accent-blue" />}
      </div>

      <div className="flex items-center gap-3 border-t border-border-subtle bg-bg-secondary px-3 py-2">
        <button type="button" onClick={() => setPlaying((p) => !p)} className="btn-ghost p-1.5" aria-label={playing ? 'Pause' : 'Play'}>
          {playing ? <Pause size={15} /> : <Play size={15} />}
        </button>
        <button type="button" onClick={() => setT(0)} className="btn-ghost p-1.5" aria-label="Restart"><RotateCcw size={14} /></button>
        <div className="relative flex-1">
          <input type="range" min={0} max={horizon} step={0.5} value={t} onChange={(e) => setT(Number(e.target.value))}
                 className="w-full accent-accent-blue" aria-label="Simulated time" />
          <div className="pointer-events-none absolute inset-x-0 -top-1 h-2">
            {events.map((e, i) => (
              <span key={i} className="absolute h-2 w-0.5" style={{ left: `${(e.t / horizon) * 100}%`, background: e.stopped ? (e.stopped === 'patrol' ? STOP_PATROL : STOP_FREEZE) : HIT }} />
            ))}
          </div>
        </div>
        <button type="button" onClick={() => setSpeed((s) => (s + 1) % SPEEDS.length)} className="btn-ghost px-2 py-1 font-mono text-xs">
          {SPEEDS[speed]}h/s
        </button>
        <div className="flex gap-1">
          {r.samples.map((_, i) => (
            <button key={i} type="button" onClick={() => { setSample(i); setT(0) }} title={`Future #${i + 1}`}
                    className={cn('h-6 w-6 rounded text-2xs font-bold', sample === i ? 'bg-accent-blue text-white' : 'bg-bg-elevated text-text-muted')}>
              {i + 1}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function FeedItem({ e, r }: { e: SwarmEvent; r: SwarmResult }) {
  const agent = r.agents.find((a) => a.id === e.agent)
  const color = e.stopped === 'patrol' ? STOP_PATROL : e.stopped === 'freeze' ? STOP_FREEZE : HIT
  const Icon = e.stopped === 'patrol' ? Shield : e.stopped === 'freeze' ? Snowflake : Siren
  return (
    <div className="flex items-center gap-1.5 rounded border-l-2 bg-bg-primary/85 px-2 py-1 text-2xs backdrop-blur animate-fade-in" style={{ borderColor: color }}>
      <Icon size={11} style={{ color }} />
      <span className="font-mono tabular-nums text-text-muted">D{Math.floor(e.t / 24) + 1} {String(Math.floor(e.t % 24)).padStart(2, '0')}h</span>
      <span className="truncate font-mono text-text-secondary">{agent?.label ?? '—'}</span>
    </div>
  )
}

function Fit({ r }: { r: SwarmResult }) {
  const map = useMap()
  useEffect(() => {
    const pts = r.cases.map((c) => [c.lat, c.lng] as [number, number])
    if (pts.length && hasSize(map)) map.fitBounds(L.latLngBounds(pts), { padding: [70, 70], maxZoom: 14 })
  }, [map, r])
  return null
}

interface Civ { lat: number; lng: number; vx: number; vy: number }

/** Canvas layer: civilians drift, offender agents travel to each simulated hit, police hold their posts. */
function Swarm({ r, events, t }: { r: SwarmResult; events: SwarmEvent[]; t: number }) {
  const map = useMap()
  const canvas = useRef<HTMLCanvasElement | null>(null)
  const tRef = useRef(t)
  tRef.current = t

  const civs = useMemo<Civ[]>(() => {
    const pool = r.heat.length ? r.heat : r.cases.map((c) => ({ lat: c.lat, lng: c.lng, w: 1 }))
    return Array.from({ length: 420 }, (_, i) => {
      const p = pool[i % pool.length]
      return { lat: p.lat + (Math.random() - 0.5) * 0.03, lng: p.lng + (Math.random() - 0.5) * 0.03,
               vx: (Math.random() - 0.5) * 2e-5, vy: (Math.random() - 0.5) * 2e-5 }
    })
  }, [r])

  const routes = useMemo(() => {
    const byAgent = new Map<string, SwarmEvent[]>()
    for (const e of events) byAgent.set(e.agent, [...(byAgent.get(e.agent) ?? []), e])
    return byAgent
  }, [events])

  useEffect(() => {
    const el = L.DomUtil.create('canvas', 'pointer-events-none') as HTMLCanvasElement
    Object.assign(el.style, { position: 'absolute', inset: '0', zIndex: '450' })
    map.getContainer().appendChild(el)
    canvas.current = el
    return () => { el.remove(); canvas.current = null }
  }, [map])

  useEffect(() => {
    let raf = 0
    const trails = new Map<string, Array<{ x: number; y: number }>>()
    const draw = () => {
      const el = canvas.current
      if (!el) return
      const size = map.getSize()
      const dpr = window.devicePixelRatio || 1
      if (el.width !== size.x * dpr) { el.width = size.x * dpr; el.height = size.y * dpr; el.style.width = `${size.x}px`; el.style.height = `${size.y}px` }
      const ctx = el.getContext('2d')!
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, size.x, size.y)
      const now = tRef.current
      const pt = (lat: number, lng: number) => map.latLngToContainerPoint([lat, lng])

      // Civilians
      ctx.fillStyle = "rgba(57,197,207,0.6)"
      for (const c of civs) {
        c.lat += c.vy; c.lng += c.vx
        if (Math.random() < 0.02) { c.vx = (Math.random() - 0.5) * 2e-5; c.vy = (Math.random() - 0.5) * 2e-5 }
        const p = pt(c.lat, c.lng)
        ctx.fillRect(p.x - 1, p.y - 1, 2.2, 2.2)
      }

      // Police posts with coverage
      const km = pt(r.cases[0]?.lat ?? 28.6, r.cases[0]?.lng ?? 77.2)
      const kmEdge = pt((r.cases[0]?.lat ?? 28.6) + 0.9 / 111, r.cases[0]?.lng ?? 77.2)
      const radius = Math.abs(km.y - kmEdge.y)
      const onShift = r.hours[Math.floor(now % 24)] >= [...r.hours].sort((a, b) => b - a)[7]
      for (const post of r.patrol_posts) {
        const p = pt(post.lat, post.lng)
        ctx.beginPath(); ctx.arc(p.x, p.y, radius, 0, Math.PI * 2)
        ctx.fillStyle = onShift ? 'rgba(88,166,255,0.12)' : 'rgba(88,166,255,0.04)'; ctx.fill()
        ctx.strokeStyle = onShift ? 'rgba(88,166,255,0.8)' : 'rgba(88,166,255,0.25)'; ctx.setLineDash([4, 4]); ctx.stroke(); ctx.setLineDash([])
        ctx.fillStyle = STOP_PATROL; ctx.fillRect(p.x - 4, p.y - 4, 8, 8)
      }

      // Offender agents travel from their last hit (or anchor) to the next one, arriving on time.
      for (const a of r.agents) {
        const route = routes.get(a.id) ?? []
        const next = route.find((e) => e.t > now)
        const prev = [...route].reverse().find((e) => e.t <= now)
        const from = prev ? { lat: prev.lat, lng: prev.lng, t: prev.t } : { lat: a.anchor[0], lng: a.anchor[1], t: 0 }
        const to = next ?? { lat: a.anchor[0], lng: a.anchor[1], t: from.t + 48 }
        const k = Math.min(Math.max((now - from.t) / Math.max(to.t - from.t, 0.01), 0), 1)
        const ease = k * k * (3 - 2 * k)
        const wob = Math.sin(now * 3 + a.id.length) * 0.0015
        const p = pt(from.lat + (to.lat - from.lat) * ease + wob, from.lng + (to.lng - from.lng) * ease - wob)
        const trail = trails.get(a.id) ?? []
        trail.push({ x: p.x, y: p.y }); if (trail.length > 18) trail.shift(); trails.set(a.id, trail)
        const color = a.frozen ? STOP_FREEZE : HIT
        ctx.strokeStyle = color; ctx.globalAlpha = 0.35; ctx.lineWidth = 2; ctx.beginPath()
        trail.forEach((q, i) => (i ? ctx.lineTo(q.x, q.y) : ctx.moveTo(q.x, q.y))); ctx.stroke(); ctx.globalAlpha = 1
        if (next) {
          const target = pt(next.lat, next.lng)
          ctx.strokeStyle = color; ctx.globalAlpha = 0.18; ctx.setLineDash([2, 5]); ctx.beginPath()
          ctx.moveTo(p.x, p.y); ctx.lineTo(target.x, target.y); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1
        }
        ctx.shadowColor = color; ctx.shadowBlur = 14
        ctx.beginPath(); ctx.arc(p.x, p.y, 5.5, 0, Math.PI * 2)
        if (a.frozen) { ctx.strokeStyle = color; ctx.lineWidth = 2.5; ctx.stroke() } else { ctx.fillStyle = color; ctx.fill() }
        ctx.shadowBlur = 0
      }

      // Hits and stops: a burst when they happen, then a lasting mark.
      for (const e of events) {
        if (e.t > now) continue
        const p = pt(e.lat, e.lng)
        const age = now - e.t
        const color = e.stopped === 'patrol' ? STOP_PATROL : e.stopped === 'freeze' ? STOP_FREEZE : HIT
        if (age < 6) {
          const k = age / 6
          ctx.beginPath(); ctx.arc(p.x, p.y, 6 + k * 34, 0, Math.PI * 2)
          ctx.strokeStyle = color; ctx.globalAlpha = 1 - k; ctx.lineWidth = 2.5; ctx.stroke(); ctx.globalAlpha = 1
        }
        ctx.fillStyle = color
        if (e.stopped) { ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(Math.PI / 4); ctx.fillRect(-3.5, -3.5, 7, 7); ctx.restore() }
        else { ctx.beginPath(); ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2); ctx.fill() }
      }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [map, r, civs, routes, events])

  return null
}

function Controls(props: {
  days: number; setDays: (n: number) => void; patrols: number; setPatrols: (n: number) => void
  freeze: boolean; setFreeze: (b: boolean) => void; street: boolean; money: boolean
}) {
  return (
    <div className="card space-y-3 p-3">
      <div className="flex gap-1 rounded-md bg-bg-primary p-0.5">
        {[7, 14, 30].map((d) => (
          <button key={d} type="button" onClick={() => props.setDays(d)}
                  className={cn('flex-1 rounded py-1 text-xs font-semibold', props.days === d ? 'bg-bg-elevated text-text-primary' : 'text-text-muted')}>
            {d}d
          </button>
        ))}
      </div>
      <label className={cn('block', !props.street && 'opacity-40')} title={props.street ? undefined : 'Online pattern: patrols do not reach it'}>
        <span className="flex items-center justify-between text-xs text-text-secondary">
          <span className="flex items-center gap-1.5"><Shield size={13} className="text-accent-blue" /> Patrol units</span>
          <span className="font-mono font-bold text-text-primary">{props.patrols}</span>
        </span>
        <input type="range" min={0} max={12} value={props.patrols} disabled={!props.street}
               onChange={(e) => props.setPatrols(Number(e.target.value))} className="mt-1 w-full accent-accent-blue" />
      </label>
      <button type="button" disabled={!props.money} onClick={() => props.setFreeze(!props.freeze)}
              className={cn('flex w-full items-center justify-between rounded-md border px-3 py-2 text-xs font-semibold transition-colors disabled:opacity-40',
                props.freeze && props.money ? 'border-accent-purple bg-accent-purple/15 text-accent-purple' : 'border-border-subtle text-text-muted')}>
        <span className="flex items-center gap-1.5">{props.freeze ? <Snowflake size={13} /> : <ShieldOff size={13} />} Freeze money trail</span>
        <span>{props.freeze && props.money ? 'ON' : 'OFF'}</span>
      </button>
    </div>
  )
}

function Outlook({ r }: { r: SwarmResult }) {
  const o = r.outlook
  return (
    <div className="card p-3">
      <div className="flex items-end justify-between">
        <Gauge value={o.p_hit_baseline} color={HIT} label="no action" />
        <div className="pb-6 text-center">
          <p className="text-lg font-bold tabular-nums text-severity-low">−{o.prevented_pct}%</p>
          <p className="text-2xs text-text-muted">hits</p>
        </div>
        <Gauge value={o.p_hit_intervention} color={STOP_PATROL} label="with action" />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 border-t border-border-subtle pt-2 text-center">
        <Stat v={o.median_hours_to_next != null ? `${Math.round(o.median_hours_to_next / 24 * 10) / 10}d` : '—'} l="next hit" />
        <Stat v={`${String(o.peak_hour_ist).padStart(2, '0')}:00`} l="peak" />
        <Stat v={o.likely_district ?? '—'} l="where" />
      </div>
    </div>
  )
}

function Gauge({ value, color, label }: { value: number; color: string; label: string }) {
  const R = 34
  const C = Math.PI * R
  return (
    <div className="text-center">
      <svg width="96" height="58" viewBox="0 0 96 58">
        <path d={`M10,52 A${R},${R} 0 0 1 82,52`} transform="translate(2,0)" fill="none" stroke="rgb(var(--bg-elevated))" strokeWidth="9" strokeLinecap="round" />
        <path d={`M10,52 A${R},${R} 0 0 1 82,52`} transform="translate(2,0)" fill="none" stroke={color} strokeWidth="9" strokeLinecap="round"
              strokeDasharray={`${C * value} ${C}`} style={{ filter: `drop-shadow(0 0 6px ${color})`, transition: 'stroke-dasharray .6s' }} />
        <text x="48" y="50" textAnchor="middle" fontSize="17" fontWeight="800" className="fill-text-primary">{Math.round(value * 100)}%</text>
      </svg>
      <p className="text-2xs text-text-muted">{label}</p>
    </div>
  )
}

function Stat({ v, l }: { v: string; l: string }) {
  return (
    <div className="min-w-0">
      <p className="truncate text-sm font-bold text-text-primary" title={v}>{v}</p>
      <p className="text-2xs uppercase tracking-wider text-text-muted">{l}</p>
    </div>
  )
}

function Curve({ r }: { r: SwarmResult }) {
  const data = r.curve.baseline.map((b, i) => ({ d: i + 1, base: Math.round(b * 100), act: Math.round(r.curve.intervention[i] * 100) }))
  return (
    <div className="card h-36 p-2">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: -22 }}>
          <defs>
            <linearGradient id="sw-b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={HIT} stopOpacity={0.45} /><stop offset="1" stopColor={HIT} stopOpacity={0} /></linearGradient>
            <linearGradient id="sw-a" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={STOP_PATROL} stopOpacity={0.45} /><stop offset="1" stopColor={STOP_PATROL} stopOpacity={0} /></linearGradient>
          </defs>
          <XAxis dataKey="d" tick={{ fontSize: 10 }} tickFormatter={(d) => `D${d}`} stroke="rgb(var(--text-muted))" />
          <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} unit="%" stroke="rgb(var(--text-muted))" />
          <ChartTip formatter={(v: number, k: string) => [`${v}%`, k === 'base' ? 'No action' : 'With action']} labelFormatter={(d) => `By day ${d}`}
                    contentStyle={{ background: 'rgb(var(--bg-elevated))', border: '1px solid rgb(var(--border-default))', fontSize: 11 }} />
          <Area dataKey="base" stroke={HIT} fill="url(#sw-b)" strokeWidth={2} />
          <Area dataKey="act" stroke={STOP_PATROL} fill="url(#sw-a)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function Clock({ hours }: { hours: number[] }) {
  const max = Math.max(...hours, 0.001)
  return (
    <div className="card flex items-center justify-center p-2">
      <svg viewBox="-60 -60 120 120" className="h-32 w-32" role="img" aria-label="Hour-of-day risk">
        <circle r="18" fill="none" stroke="rgb(var(--border-subtle))" />
        {hours.map((h, i) => {
          const a = (i / 24) * Math.PI * 2 - Math.PI / 2
          const len = 20 + (h / max) * 34
          return <line key={i} x1={Math.cos(a) * 20} y1={Math.sin(a) * 20} x2={Math.cos(a) * len} y2={Math.sin(a) * len}
                       stroke={HIT} strokeOpacity={0.3 + (h / max) * 0.7} strokeWidth="4" strokeLinecap="round" />
        })}
        {[0, 6, 12, 18].map((h) => {
          const a = (h / 24) * Math.PI * 2 - Math.PI / 2
          return <text key={h} x={Math.cos(a) * 9} y={Math.sin(a) * 9 + 3} fontSize="7" textAnchor="middle" className="fill-text-muted">{h}</text>
        })}
      </svg>
    </div>
  )
}

function Districts({ r }: { r: SwarmResult }) {
  return (
    <div className="card space-y-1.5 p-2.5">
      {r.districts.slice(0, 5).map((d) => (
        <div key={d.district} title={`${Math.round(d.share * 100)}%`}>
          <div className="flex justify-between text-2xs"><span className="truncate text-text-secondary">{d.district}</span><span className="tabular-nums text-text-muted">{Math.round(d.share * 100)}</span></div>
          <div className="h-1.5 rounded-full bg-bg-elevated"><div className="h-full rounded-full bg-gradient-to-r from-severity-medium to-severity-high" style={{ width: `${d.share * 100}%` }} /></div>
        </div>
      ))}
    </div>
  )
}

function Agents({ r }: { r: SwarmResult }) {
  return (
    <div className="card p-2.5">
      <div className="flex flex-wrap gap-1.5">
        {r.agents.map((a) => (
          <span key={a.id} className={cn('flex items-center gap-1.5 rounded-md border px-2 py-1 font-mono text-2xs', a.frozen ? 'border-accent-purple/50 text-accent-purple' : 'border-border-subtle text-text-secondary')}
                title={`${a.cases} linked cases · ${Math.round(a.share * 100)}% of simulated hits`}>
            <span className="h-2 w-2 rounded-full" style={{ background: a.frozen ? STOP_FREEZE : NODE_COLORS[a.kind] ?? HIT }} />
            {a.label}
            <span className="text-text-muted">{Math.round(a.share * 100)}%</span>
            {a.frozen && <Snowflake size={10} />}
          </span>
        ))}
      </div>
      <p className="mt-2 text-2xs text-text-muted" title={r.note}>
        {r.params.runs} futures · {r.cases.length} cases · {r.params.rate_per_day}/day · {r.basis}
      </p>
    </div>
  )
}
