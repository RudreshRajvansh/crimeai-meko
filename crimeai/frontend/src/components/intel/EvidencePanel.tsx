import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Download, Film, Link2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { getErrorMessage } from '@/services/api'
import { integrationsApi } from '@/services/integrations'
import { useAuthStore } from '@/store/auth'
import { formatDate } from '@/utils'
import type { EvidenceLink } from '@/types'

const PROVISIONS: [string, string][] = [
  ['105', 's.105 Search and seizure'],
  ['176', 's.176 Crime scene'],
  ['185', 's.185 Search during investigation'],
  ['180', 's.180 Examination of witnesses'],
  ['173', 's.173 Information / e-FIR'],
  ['497', 's.497 Property custody'],
]

/** e-Sakshya recordings linked to the case, the BNSS s.105 check, and the CCTNS write-back export. */
export default function EvidencePanel({ crimeId, evidence }: { crimeId: string; evidence?: { links: EvidenceLink[]; s105_gap: string | null } }) {
  const isPolice = useAuthStore((s) => s.hasRole('police'))
  const qc = useQueryClient()
  const [sid, setSid] = useState('')
  const [provision, setProvision] = useState('105')
  const [hash, setHash] = useState('')

  const link = useMutation({
    mutationFn: () => integrationsApi.linkEvidence(crimeId, { sid, provision, packet_hash: hash || undefined }),
    onSuccess: () => {
      toast.success('Recording linked')
      setSid('')
      setHash('')
      qc.invalidateQueries({ queryKey: ['dossier', crimeId] })
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const exportForCctns = async () => {
    try {
      const data = await integrationsApi.cctnsEnrichment(crimeId)
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const a = Object.assign(document.createElement('a'), { href: url, download: `cctns-enrichment-${crimeId.slice(0, 8)}.json` })
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      toast.error(getErrorMessage(err))
    }
  }

  const links = evidence?.links ?? []
  return (
    <section className="card p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary">
          <Film size={13} /> Evidence recordings (e-Sakshya)
        </h3>
        {isPolice && (
          <button type="button" onClick={exportForCctns} className="btn-ghost py-1 text-2xs">
            <Download size={12} /> Export for CCTNS
          </button>
        )}
      </div>

      {evidence?.s105_gap && (
        <p className="mb-3 flex items-start gap-1.5 rounded-md border border-severity-high/30 bg-severity-high/10 px-3 py-2 text-xs text-severity-high">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {evidence.s105_gap}
        </p>
      )}

      {links.length > 0 ? (
        <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
          {links.map((l) => (
            <li key={l.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2 text-xs">
              <span className="font-mono text-text-primary">SID {l.sid}</span>
              <span className="rounded bg-accent-purple/15 px-1.5 py-0.5 text-2xs text-accent-purple">BNSS s.{l.provision}</span>
              <span className="text-text-muted">{l.provision_label}</span>
              {l.packet_hash && <span className="font-mono text-2xs text-text-muted" title={l.packet_hash}>hash {l.packet_hash.slice(0, 12)}…</span>}
              {l.linked_at && <span className="ml-auto text-2xs text-text-muted">linked {formatDate(l.linked_at, 'dd MMM yyyy')}</span>}
            </li>
          ))}
        </ul>
      ) : (
        !evidence?.s105_gap && <p className="text-xs text-text-muted">No recordings linked.</p>
      )}

      {isPolice && (
        <form
          className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_auto_1fr_auto]"
          onSubmit={(e) => { e.preventDefault(); if (sid.trim()) link.mutate() }}
        >
          <input value={sid} onChange={(e) => setSid(e.target.value)} placeholder="16-digit SID from the app"
                 aria-label="e-Sakshya session id" className="input py-1.5 text-xs font-mono" inputMode="numeric" />
          <select value={provision} onChange={(e) => setProvision(e.target.value)} aria-label="BNSS provision" className="input py-1.5 text-xs">
            {PROVISIONS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
          <input value={hash} onChange={(e) => setHash(e.target.value)} placeholder="Packet hash (optional)"
                 aria-label="Packet hash" className="input py-1.5 text-xs font-mono" />
          <button type="submit" disabled={link.isPending || !sid.trim()} className="btn-primary py-1.5 text-xs">
            <Link2 size={12} /> Link
          </button>
        </form>
      )}
    </section>
  )
}
