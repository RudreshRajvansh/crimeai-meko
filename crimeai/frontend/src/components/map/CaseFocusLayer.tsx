/**
 * One case and everything it matches, drawn over the crime map: the case pulses, and a line runs to each
 * match — red for a shared phone, UPI ID, account or vehicle, amber for the same series, dashed blue for a
 * narrative that reads alike.
 */
import { useEffect } from 'react'
import { useMap } from 'react-leaflet'
import L from 'leaflet'
import type { CaseMap, CaseMatch } from '@/types'
import { crimeTypeLabel, escapeHtml, formatDate } from '@/utils'

export const MATCH_STYLE: Record<CaseMatch['reason'], { color: string; dash?: string; label: string }> = {
  identifier: { color: '#f85149', label: 'Shared identifier' },
  series: { color: '#d29922', label: 'Same series' },
  modus_operandi: { color: '#58a6ff', dash: '6 6', label: 'Similar modus operandi' },
}

function popup(title: string, lines: string[], id: string): string {
  return `
    <div style="min-width:190px">
      <div style="font-weight:600;font-size:13px;margin-bottom:4px">${escapeHtml(title)}</div>
      ${lines.map((l) => `<div style="font-size:11px;color:rgb(var(--text-secondary));margin-bottom:2px">${escapeHtml(l)}</div>`).join('')}
      <a href="/cases/${encodeURIComponent(id)}" style="display:inline-block;margin-top:6px;font-size:11px;color:#58a6ff">Open dossier →</a>
    </div>`
}

export default function CaseFocusLayer({ focus }: { focus: CaseMap }) {
  const map = useMap()

  useEffect(() => {
    const group = L.layerGroup().addTo(map)
    const origin = L.latLng(focus.case.lat, focus.case.lng)

    // Lines first so the markers sit on top of them.
    focus.matches.forEach((m) => {
      const style = MATCH_STYLE[m.reason]
      L.polyline([origin, [m.lat, m.lng]], {
        color: style.color, weight: m.reason === 'identifier' ? 3 : 2, opacity: 0.85, dashArray: style.dash,
      }).addTo(group)
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:14px;height:14px;border-radius:50%;background:${style.color};border:2px solid #fff;box-shadow:0 0 10px ${style.color}"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      })
      const lines = [
        `${m.district ?? 'Unknown district'} · ${m.occurred_at ? formatDate(m.occurred_at, 'dd MMM yyyy') : ''}`,
        style.label + (m.similarity != null ? ` · ${Math.round(m.similarity * 100)}% alike` : ''),
        ...m.shared,
      ]
      L.marker([m.lat, m.lng], { icon }).bindPopup(popup(`${crimeTypeLabel(m.crime_type)} · ${m.label}`, lines, m.id))
        .addTo(group)
    })

    const focusIcon = L.divIcon({
      className: '',
      html: `<div style="position:relative;width:22px;height:22px">
        <span class="animate-ping" style="position:absolute;inset:0;border-radius:50%;background:#a371f7;opacity:.6"></span>
        <span style="position:absolute;inset:3px;border-radius:50%;background:#a371f7;border:3px solid #fff;box-shadow:0 0 14px #a371f7"></span>
      </div>`,
      iconSize: [22, 22],
      iconAnchor: [11, 11],
    })
    const c = focus.case
    L.marker(origin, { icon: focusIcon, zIndexOffset: 1000 })
      .bindPopup(popup(`New case · ${crimeTypeLabel(c.crime_type)}`, [
        c.label, c.location_name ?? c.district ?? '', `${focus.matches.length} matching cases`,
      ], c.id))
      .addTo(group)
      .openPopup()

    const bounds = L.latLngBounds([origin, ...focus.matches.map((m) => L.latLng(m.lat, m.lng))])
    // The matches panel opens beside the map in the same render; measure the narrower map before fitting.
    const fit = window.setTimeout(() => {
      map.invalidateSize()
      map.flyToBounds(bounds.pad(0.2), { maxZoom: 14, duration: 1.2 })
    }, 250)

    return () => { window.clearTimeout(fit); group.remove() }
  }, [map, focus])

  return null
}
