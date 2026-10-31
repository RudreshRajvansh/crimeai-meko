import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangle, ArrowUpRight, FileImage, Languages, Scale, ShieldCheck, X } from 'lucide-react'
import HighlightedText, { HighlightLegend } from '@/components/intel/HighlightedText'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { FirGeminiSection } from '@/components/fir/GeminiBrief'
import ContextPanel from '@/components/fir/ContextPanel'
import { firApi } from '@/services/fir'
import { brandSafe } from '@/services/api'
import { cn, crimeTypeLabel, formatDate } from '@/utils'

const RTL_LANGUAGES = new Set(['ur', 'ks', 'sd'])

/** Slide-over showing one FIR: the narrative in its own script with every recognised term marked, plus what NLP extracted. */
export default function FIRDetailPanel({ firId, onClose }: { firId: string; onClose: () => void }) {
  const { data: fir, isLoading, error } = useQuery({ queryKey: ['fir', firId], queryFn: () => firApi.get(firId) })
  const [docUrl, setDocUrl] = useState<string | null>(null)
  const [docType, setDocType] = useState<string | null>(null)
  const [docError, setDocError] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => () => { if (docUrl) URL.revokeObjectURL(docUrl) }, [docUrl])

  const showDocument = async () => {
    try {
      const blob = await firApi.document(firId)
      setDocType(blob.type)
      setDocUrl(URL.createObjectURL(blob))
    } catch {
      setDocError(true)
    }
  }

  const entities = fir?.extracted_entities
  const highlights = fir?.highlights ?? []
  const kinds = [...new Set(highlights.map((h) => h.kind))]
  const identifiers = entities?.identifiers

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="FIR details">
      <button type="button" aria-label="Close" onClick={onClose} className="absolute inset-0 bg-bg-primary/60" />
      <aside className="relative flex h-full w-full max-w-2xl flex-col border-l border-border-default bg-bg-secondary shadow-elevated animate-slide-up">
        <header className="flex items-start justify-between gap-4 border-b border-border-subtle px-6 py-4">
          <div className="min-w-0">
            <p className="text-2xs font-medium uppercase tracking-wider text-text-muted">FIR</p>
            <h2 className="truncate font-mono text-lg font-semibold text-text-primary">{fir?.fir_number ?? '…'}</h2>
            {fir && (
              <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-text-secondary">
                {entities?.language && (
                  <span className="inline-flex items-center gap-1"><Languages size={12} /> {entities.language.name} · {entities.language.script}</span>
                )}
                {entities?.crime_type && <span className="font-medium text-text-primary">{crimeTypeLabel(entities.crime_type)}</span>}
                {fir.incident_date && <span>Incident {formatDate(fir.incident_date, 'dd MMM yyyy')}</span>}
                <span>Filed {formatDate(fir.created_at, 'dd MMM yyyy, HH:mm')}</span>
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="btn-ghost p-1.5" aria-label="Close panel"><X size={16} /></button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {isLoading && <PageLoader label="Loading FIR…" />}
          {error && <p className="text-sm text-severity-high">This FIR could not be loaded.</p>}
          {fir && (
            <>
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">Narrative</h3>
                  {fir.text_redacted && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-severity-low-bg px-2 py-0.5 text-2xs text-severity-low">
                      <ShieldCheck size={11} /> Personal data redacted for your role
                    </span>
                  )}
                </div>
                <div className="rounded-md border border-border-subtle bg-bg-primary px-4 py-3">
                  {fir.text ? (
                    <HighlightedText
                      text={fir.text}
                      highlights={highlights}
                      dir={RTL_LANGUAGES.has(entities?.language?.code ?? fir.language ?? '') ? 'rtl' : 'ltr'}
                    />
                  ) : (
                    <p className="text-sm text-text-muted">
                      {fir.nlp_status === 'awaiting_ocr' ? 'The document has no readable text yet; it is waiting for OCR.' : 'Text will appear once the document has been read.'}
                    </p>
                  )}
                </div>
                {kinds.length > 0 && (
                  <div className="mt-2 flex items-center gap-2"><span className="text-2xs text-text-muted">Recognised:</span><HighlightLegend kinds={kinds} /></div>
                )}
              </section>

              {fir.crime_id && (
                <Link to={`/crimes?focus=${fir.crime_id}`} className="btn-secondary w-full justify-center text-xs">
                  Show case and its matches on the map
                </Link>
              )}

              {entities?.context && <ContextPanel context={entities.context} rulesCrimeType={entities.rules_crime_type} />}

              {fir.text && <FirGeminiSection firId={fir.id} cached={entities?.gemini} />}

              {fir.has_document && (
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">Original document</h3>
                  {docUrl ? (
                    docType?.startsWith('image/') ? (
                      <img src={docUrl} alt={`Scanned FIR ${fir.fir_number}`} className="w-full rounded-md border border-border-subtle bg-white" />
                    ) : (
                      <a href={docUrl} target="_blank" rel="noreferrer" className="btn-secondary text-xs">Open document</a>
                    )
                  ) : (
                    <button type="button" onClick={showDocument} className="btn-secondary text-xs" disabled={docError}>
                      <FileImage size={13} /> {docError ? 'Document unavailable' : 'Show scanned document'}
                    </button>
                  )}
                  {fir.file_sha256 && <p className="mt-1.5 font-mono text-2xs text-text-muted">SHA-256 {fir.file_sha256}</p>}
                </section>
              )}

              {entities?.legal && entities.legal.mapped.length > 0 && (
                <section>
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-secondary">
                    <Scale size={12} /> Sections · governed by {entities.legal.governing_code}
                  </h3>
                  <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
                    {entities.legal.mapped.map((m, i) => (
                      <li key={i} className="grid grid-cols-[90px_100px_1fr] gap-3 px-3 py-2 text-xs">
                        <span className="font-mono text-text-secondary">{m.ipc ? `IPC ${m.ipc}` : '—'}</span>
                        <span className="font-mono text-accent-purple">{m.bns ? `BNS ${m.bns}` : '—'}</span>
                        <span className="text-text-primary">{m.offence ?? m.note}</span>
                      </li>
                    ))}
                  </ul>
                  {entities.legal.warnings.map((w) => (
                    <p key={w} className="mt-2 flex items-start gap-1.5 text-xs text-severity-medium"><AlertTriangle size={12} className="mt-0.5 shrink-0" />{w}</p>
                  ))}
                </section>
              )}

              {identifiers && (
                <section>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-text-secondary">Extracted references</h3>
                  <dl className="grid grid-cols-[140px_1fr] gap-y-1.5 text-xs">
                    <Row label="Earlier FIRs cited" values={identifiers.fir_references?.map((r) => `FIR ${r}`)} />
                    <Row label="Dates" values={identifiers.dates?.map((d) => formatDate(d, 'dd MMM yyyy'))} />
                    <Row label="Vehicles" values={identifiers.vehicles} />
                    <Row label="Phones" values={identifiers.phones} />
                    <Row label="UPI IDs" values={identifiers.upi_ids} />
                    <Row label="Amounts" values={identifiers.amounts?.map((a) => `₹${a.toLocaleString('en-IN')}`)} />
                    <Row label="Weapons" values={entities?.weapons} />
                  </dl>
                </section>
              )}

              {entities?.language && entities.language.confidence < 0.5 && (
                <p className="flex items-start gap-1.5 text-xs text-severity-medium">
                  <AlertTriangle size={12} className="mt-0.5 shrink-0" />
                  Language detected with low confidence ({Math.round(entities.language.confidence * 100)}%). If this is a scan, the text may be misread; use Reprocess to read the original again.
                </p>
              )}
              {fir.nlp_error && <p className="text-xs text-severity-high">Processing note: {brandSafe(fir.nlp_error)}</p>}
            </>
          )}
        </div>

        {fir?.crime_id && (
          <footer className="border-t border-border-subtle px-6 py-3">
            <Link to={`/cases/${fir.crime_id}`} className="btn-primary text-xs">Open case dossier <ArrowUpRight size={13} /></Link>
          </footer>
        )}
      </aside>
    </div>
  )
}

function Row({ label, values }: { label: string; values?: string[] | null }) {
  return (
    <>
      <dt className="text-text-muted">{label}</dt>
      <dd className={cn('font-mono', values?.length ? 'text-text-primary' : 'text-text-muted')}>{values?.length ? values.join(', ') : '—'}</dd>
    </>
  )
}
