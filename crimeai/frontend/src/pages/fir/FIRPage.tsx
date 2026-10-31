import { useState } from 'react'
import { FileText, Send, RefreshCw, CheckCircle, AlertCircle, Clock, Upload, Scale, ShieldCheck, ScanLine, Sparkles, PenLine, Camera, Mic, Square, Loader2 } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { firApi, getErrorMessage } from '@/services'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import FIRDetailPanel from '@/components/fir/FIRDetailPanel'
import { GeminiBriefCard, useGeminiStatus } from '@/components/fir/GeminiBrief'
import CameraScanDialog from '@/components/fir/CameraScanDialog'
import RecordMatchPanel from '@/components/fir/RecordMatchPanel'
import ContextPanel from '@/components/fir/ContextPanel'
import CasePlacedCard from '@/components/fir/CasePlacedCard'
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder'
import { useAuthStore } from '@/store/auth'
import { timeAgo, cn } from '@/utils'
import type { ExtractedEntities, GeminiBrief, LegalAnalysis, LinkCheck } from '@/types'

export default function FIRPage() {
  // Filing and uploading are police actions on the server; analysts get the read-only records view.
  const canSubmit = useAuthStore((s) => s.hasRole('police'))
  const [activeTab, setActiveTab] = useState<'submit' | 'list'>(canSubmit ? 'submit' : 'list')
  const [firNumber, setFirNumber] = useState('')
  const [rawText, setRawText] = useState('')
  const [incidentDate, setIncidentDate] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [openFir, setOpenFir] = useState<string | null>(null)
  const [analysisResult, setAnalysisResult] = useState<ExtractedEntities | null>(null)
  const [geminiResult, setGeminiResult] = useState<GeminiBrief | null>(null)
  const gemini = useGeminiStatus()
  const [scanUrl, setScanUrl] = useState<string | null>(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [tracked, setTracked] = useState<{ id: string; number: string } | null>(null)
  const [linkResult, setLinkResult] = useState<LinkCheck | null>(null)

  const linkMutation = useMutation({
    mutationFn: (text: string) => firApi.linkCheck(text),
    onSuccess: (data) => setLinkResult(data),
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const speechMutation = useMutation({
    mutationFn: (audio: File) => firApi.transcribe(audio),
    onSuccess: (data) => {
      const text = rawText.trim() ? `${rawText.trimEnd()}
${data.statement}` : data.statement
      setRawText(text)
      toast.success(`Complaint heard${data.languages.length ? ` (${data.languages.join(', ')})` : ''}`)
      analyseAll(text)
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const voice = useVoiceRecorder((audio) => speechMutation.mutate(audio))

  const ocrMutation = useMutation({
    mutationFn: (f: File) => firApi.handwritingOcr(f),
    onSuccess: (data) => {
      setRawText(data.text)
      setFile(null)
      const scanned = firNumberFrom(data.text)
      if (scanned) setFirNumber((current) => current || scanned)
      toast.success(`FIR read: ${data.chars} characters`)
      analyseAll(data.text)
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const scanHandwriting = (f: File | undefined) => {
    if (!f) return
    if (scanUrl) URL.revokeObjectURL(scanUrl)
    setScanUrl(f.type.startsWith('image/') ? URL.createObjectURL(f) : null)
    ocrMutation.mutate(f)
  }
  const qc = useQueryClient()

  const { data: firList, isLoading } = useQuery({
    queryKey: ['fir', 'list'],
    queryFn: () => firApi.list({ limit: 50 }),
    enabled: activeTab === 'list',
  })

  const submitMutation = useMutation({
    mutationFn: () => {
      const incident_date = incidentDate ? new Date(incidentDate).toISOString() : undefined
      return file
        ? firApi.upload(firNumber, file, incident_date)
        : firApi.submit({ fir_number: firNumber, raw_text: rawText, incident_date })
    },
    onSuccess: (saved) => {
      toast.success(`FIR ${saved.fir_number} received. Analysis queued.`)
      setTracked({ id: saved.id, number: saved.fir_number })
      qc.invalidateQueries({ queryKey: ['fir'] })
      setFirNumber('')
      setRawText('')
      setIncidentDate('')
      setFile(null)
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const analyzeMutation = useMutation({
    mutationFn: (text: string) => firApi.extract(text, incidentDate ? incidentDate.slice(0, 10) : undefined),
    onSuccess: (data) => setAnalysisResult(data),
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const geminiMutation = useMutation({
    mutationFn: (text: string) => firApi.geminiPreview(text, incidentDate ? incidentDate.slice(0, 10) : undefined),
    onSuccess: (data) => setGeminiResult(data),
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  // One scan, every engine: entities + law, the cross-station record check, and the English brief.
  function analyseAll(text: string) {
    if (text.trim().length < 20) return
    setAnalysisResult(null)
    setGeminiResult(null)
    setLinkResult(null)
    analyzeMutation.mutate(text)
    linkMutation.mutate(text)
    if (gemini.data?.enabled) geminiMutation.mutate(text)
  }

  const reprocessMutation = useMutation({
    mutationFn: (id: string) => firApi.reprocess(id),
    onSuccess: () => { toast.success('Reprocessing queued'); qc.invalidateQueries({ queryKey: ['fir'] }) },
  })

  return (
    <div className="p-3 sm:p-5 space-y-4 animate-fade-in">
      {/* Tabs */}
      <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit">
        {(canSubmit ? (['submit', 'list'] as const) : (['list'] as const)).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize',
              activeTab === tab
                ? 'bg-bg-elevated text-text-primary shadow-inner-sm'
                : 'text-text-muted hover:text-text-secondary'
            )}
          >
            {tab === 'submit' ? 'Submit FIR' : 'FIR Records'}
          </button>
        ))}
      </div>

      {activeTab === 'submit' && canSubmit && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Submit form */}
          <div className="card p-5 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                <FileText size={15} /> Submit FIR for NLP Analysis
              </h3>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                FIR Number *
              </label>
              <input
                className="input"
                placeholder="e.g. FIR-2024-DL-001"
                value={firNumber}
                onChange={(e) => setFirNumber(e.target.value.replace(/[^A-Za-z0-9/\-_.]+/g, '-'))}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                Incident date
              </label>
              <input
                type="datetime-local"
                className="input"
                value={incidentDate}
                onChange={(e) => setIncidentDate(e.target.value)}
              />
              <p className="text-2xs text-text-muted mt-1">
                Decides whether IPC (before 1 July 2024) or BNS governs, so mis-cited sections can be flagged.
              </p>
            </div>

            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1.5">
                Scanned FIR or PDF (optional)
              </label>
              <label className="input flex items-center gap-2 cursor-pointer text-xs">
                <Upload size={13} />
                <span className="truncate">{file ? file.name : 'Choose PDF, image (PNG, JPEG, WebP, TIFF) or text file (max 10 MB)'}</span>
                <input
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.txt"
                  className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              </label>
            </div>

            {gemini.data?.enabled && (
              <div className="rounded-lg border border-dashed border-accent-purple/50 bg-accent-purple/5 p-3">
                <label className={cn('flex cursor-pointer items-center justify-center gap-2 text-xs font-semibold text-accent-purple', ocrMutation.isPending && 'pointer-events-none opacity-70')}>
                  <PenLine size={14} className={cn(ocrMutation.isPending && 'animate-pulse')} />
                  {ocrMutation.isPending ? 'Reading handwriting…' : 'Scan handwritten FIR (photo or PDF)'}
                  <input type="file" accept="image/png,image/jpeg,image/webp,image/heic,application/pdf" className="hidden"
                         onChange={(e) => { scanHandwriting(e.target.files?.[0]); e.target.value = '' }} />
                </label>
                <button
                  type="button"
                  onClick={() => setCameraOpen(true)}
                  disabled={ocrMutation.isPending}
                  className="btn-primary mt-2 w-full justify-center text-xs"
                >
                  <Camera size={14} /> Scan live with camera
                </button>
                {scanUrl && (
                  <div className="relative mt-3 overflow-hidden rounded-md border border-border-subtle bg-white">
                    <img src={scanUrl} alt="Scanned FIR" className="max-h-64 w-full object-contain" />
                    {ocrMutation.isPending && (
                      <>
                        <div className="absolute inset-0 bg-accent-blue/10" />
                        <span className="absolute inset-x-0 top-0 h-0.5 animate-scan-line bg-accent-blue shadow-glow-blue" />
                        <span className="absolute bottom-2 left-2 rounded bg-black/70 px-2 py-0.5 text-2xs text-white">Reading the FIR…</span>
                      </>
                    )}
                  </div>
                )}
              </div>
            )}

            <div>
              <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                <label className="block text-xs font-medium text-text-secondary">
                  FIR Text {file ? '(ignored when a document is attached)' : '*'}
                </label>
                {voice.supported && gemini.data?.enabled && !voice.recording && (
                  <button
                    type="button"
                    onClick={() => void voice.start()}
                    disabled={speechMutation.isPending}
                    className="btn-secondary h-7 py-0 text-2xs"
                    title="Record the complainant in any language, or a mix of them"
                  >
                    {speechMutation.isPending
                      ? <><Loader2 size={12} className="animate-spin" /> Understanding speech…</>
                      : <><Mic size={12} /> Speak FIR</>}
                  </button>
                )}
              </div>
              {voice.recording && (
                <div className="mb-2 flex items-center gap-3 rounded-lg border border-severity-high/40 bg-severity-high-bg px-3 py-2">
                  <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
                    <span className="absolute inset-0 animate-ping rounded-full bg-severity-high opacity-75" />
                    <span className="relative h-2.5 w-2.5 rounded-full bg-severity-high" />
                  </span>
                  <span className="font-mono text-xs text-severity-high">
                    {String(Math.floor(voice.seconds / 60)).padStart(2, '0')}:{String(voice.seconds % 60).padStart(2, '0')}
                  </span>
                  <div className="flex h-6 flex-1 items-center gap-0.5" aria-hidden>
                    {voice.levels.map((l, i) => (
                      <span key={i} className="flex-1 rounded-full bg-severity-high transition-[height] duration-75" style={{ height: `${Math.max(12, l * 100)}%` }} />
                    ))}
                  </div>
                  <button type="button" onClick={voice.stop} className="btn-secondary h-7 py-0 text-2xs">
                    <Square size={11} /> Stop
                  </button>
                </div>
              )}
              {voice.error && <p className="mb-1.5 text-2xs text-severity-high">{voice.error}</p>}
              <textarea
                className="input min-h-48 resize-y font-mono text-xs leading-relaxed"
                placeholder="Paste FIR content here… (minimum 20 characters)&#10;&#10;e.g. On 15/06/2024 at approximately 14:30 hours, the complainant Rajesh Kumar reported to Police Station Connaught Place that his motorcycle bearing registration number DL-01-AB-1234 was stolen…"
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
              />
              <p className="text-2xs text-text-muted mt-1">{rawText.length} chars</p>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => submitMutation.mutate()}
                disabled={!firNumber || (!file && rawText.length < 20) || submitMutation.isPending}
                className="btn-primary flex-1 justify-center"
              >
                {submitMutation.isPending
                  ? <><span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" /> Submitting…</>
                  : <><Send size={13} /> Submit & Queue NLP</>
                }
              </button>
              <button
                onClick={() => { setLinkResult(null); analyzeMutation.mutate(rawText); linkMutation.mutate(rawText) }}
                disabled={rawText.length < 20 || analyzeMutation.isPending}
                className="btn-secondary justify-center"
                title="Analyse without saving"
              >
                {analyzeMutation.isPending
                  ? <span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                  : 'Preview NLP'
                }
              </button>
              {gemini.data?.enabled && (
                <button
                  onClick={() => geminiMutation.mutate(rawText)}
                  disabled={rawText.length < 20 || geminiMutation.isPending}
                  className="btn-secondary justify-center text-accent-purple"
                  title="English translation and case brief (personal identifiers masked first, nothing saved)"
                >
                  <Sparkles size={13} className={cn(geminiMutation.isPending && 'animate-pulse')} /> AI Brief
                </button>
              )}
            </div>
          </div>

          {/* NLP Results panel */}
          <div className="card p-5">
            <h3 className="text-sm font-semibold text-text-primary mb-3">NLP Extraction Results</h3>
            {tracked && <div className="mb-4"><CasePlacedCard key={tracked.id} firId={tracked.id} firNumber={tracked.number} /></div>}
            {analyzeMutation.isPending && !linkResult && !linkMutation.isPending ? (
              <PageLoader label="Analysing text…" />
            ) : analysisResult || geminiResult || linkResult || linkMutation.isPending || geminiMutation.isPending ? (
              <div className="space-y-4">
                <RecordMatchPanel result={linkResult} pending={linkMutation.isPending} />
                {geminiMutation.isPending && (
                  <p className="flex items-center gap-2 text-xs text-accent-purple"><Sparkles size={13} className="animate-pulse" /> Translating and writing the case brief…</p>
                )}
                {geminiResult && <GeminiBriefCard brief={geminiResult} />}
                {analyzeMutation.isPending && (
                  <p className="flex items-center gap-2 text-xs text-text-muted"><RefreshCw size={12} className="animate-spin" /> Extracting entities and legal sections…</p>
                )}
                {analysisResult && <EntityResultPanel entities={analysisResult} />}
              </div>
            ) : (
              <EmptyState
                title="No analysis yet"
                description="Scan a paper FIR, speak one, or paste text and click 'Preview NLP'."
              />
            )}
          </div>
        </div>
      )}

      {activeTab === 'list' && (
        isLoading ? <PageLoader /> : (
          <div className="table-wrapper">
            <table className="table-base">
              <thead className="table-head">
                <tr>
                  <th className="table-th">FIR Number</th>
                  <th className="table-th">Language</th>
                  <th className="table-th">NLP Status</th>
                  <th className="table-th">Crime Type</th>
                  <th className="table-th">Confidence</th>
                  <th className="table-th">Submitted</th>
                  <th className="table-th">Actions</th>
                </tr>
              </thead>
              <tbody>
                {firList?.items.map((fir) => (
                  <tr key={fir.id} className="table-row">
                    <td className="table-td">
                      <button
                        type="button"
                        onClick={() => setOpenFir(fir.id)}
                        className="font-mono text-xs text-accent-blue hover:underline underline-offset-2"
                      >
                        {fir.fir_number}
                      </button>
                    </td>
                    <td className="table-td text-xs text-text-secondary">{fir.extracted_entities?.language?.name ?? '—'}</td>
                    <td className="table-td"><NLPStatusBadge status={fir.nlp_status} /></td>
                    <td className="table-td text-xs">
                      {fir.extracted_entities?.crime_type ?? <span className="text-text-muted">—</span>}
                    </td>
                    <td className="table-td text-xs tabular-nums">
                      {fir.extraction_confidence != null
                        ? `${(fir.extraction_confidence * 100).toFixed(0)}%`
                        : '—'}
                    </td>
                    <td className="table-td text-xs text-text-muted">{timeAgo(fir.created_at)}</td>
                    <td className="table-td">
                      {fir.nlp_status !== 'processing' && (
                        <button
                          onClick={() => reprocessMutation.mutate(fir.id)}
                          className="text-2xs text-accent-blue hover:underline flex items-center gap-1"
                        >
                          <RefreshCw size={10} /> Reprocess
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {openFir && <FIRDetailPanel firId={openFir} onClose={() => setOpenFir(null)} />}
      {cameraOpen && (
        <CameraScanDialog
          onClose={() => setCameraOpen(false)}
          onCapture={(f) => { setCameraOpen(false); scanHandwriting(f) }}
        />
      )}
    </div>
  )
}

function NLPStatusBadge({ status }: { status: string }) {
  const config = {
    completed:  { icon: <CheckCircle size={10} />, class: 'bg-severity-low-bg text-severity-low' },
    processing: { icon: <RefreshCw size={10} className="animate-spin" />, class: 'bg-accent-blue/10 text-accent-blue' },
    pending:    { icon: <Clock size={10} />, class: 'bg-severity-medium-bg text-severity-medium' },
    failed:     { icon: <AlertCircle size={10} />, class: 'bg-severity-high-bg text-severity-high' },
    awaiting_ocr: { icon: <ScanLine size={10} />, class: 'bg-accent-purple/10 text-accent-purple' },
  }[status] ?? { icon: null, class: 'bg-bg-elevated text-text-muted' }

  return (
    <span className={cn('inline-flex items-center gap-1 text-2xs font-medium px-2 py-0.5 rounded', config.class)}>
      {config.icon}{status}
    </span>
  )
}

// "FIR No. 14/18" on a scanned form -> "FIR-14/18", the shape the FIR number field accepts.
function firNumberFrom(text: string): string | null {
  const m = text.match(/FIR\s*No\.?\s*[:-]?\s*([0-9]{1,6}\s*[/-]\s*[0-9]{2,4})/i)
  return m ? `FIR-${m[1].replace(/\s+/g, '')}` : null
}

function EntityResultPanel({ entities }: { entities: ExtractedEntities }) {
  const confidence = Math.round((entities.overall_confidence ?? 0) * 100)
  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-blue rounded-full transition-all"
            style={{ width: `${confidence}%` }}
          />
        </div>
        <span className="text-text-muted font-mono w-8 text-right">{confidence}%</span>
      </div>

      {entities.context && <ContextPanel context={entities.context} rulesCrimeType={entities.rules_crime_type} />}

      {[
        { label: 'Crime Type', value: entities.crime_type },
        { label: 'Primary Location', value: entities.primary_location },
        { label: 'Inferred Severity', value: entities.inferred_severity ? `${entities.inferred_severity}/5` : null },
        { label: 'Has Weapon', value: entities.has_weapon ? '⚠️ Yes' : 'No' },
        { label: 'Has Injury', value: entities.has_injury ? '🚑 Yes' : 'No' },
      ].map(({ label, value }) => (
        <div key={label} className="flex justify-between items-start gap-4">
          <span className="text-text-muted">{label}</span>
          <span className="text-text-primary font-medium text-right">{value ?? '—'}</span>
        </div>
      ))}

      {entities.locations?.length > 0 && (
        <div>
          <p className="text-text-muted mb-1">Locations ({entities.locations.length})</p>
          <div className="flex flex-wrap gap-1">
            {entities.locations.map((l: string, i: number) => (
              <span key={i} className="bg-bg-elevated text-text-secondary px-2 py-0.5 rounded text-2xs">{l}</span>
            ))}
          </div>
        </div>
      )}

      {entities.weapons?.length > 0 && (
        <div>
          <p className="text-text-muted mb-1">Weapons</p>
          <div className="flex flex-wrap gap-1">
            {entities.weapons.map((w: string, i: number) => (
              <span key={i} className="bg-severity-high-bg text-severity-high px-2 py-0.5 rounded text-2xs">{w}</span>
            ))}
          </div>
        </div>
      )}

      {entities.legal && entities.legal.mapped.length > 0 && <LegalPanel legal={entities.legal} />}

      {entities.privacy?.pii_found && Object.keys(entities.privacy.pii_found).length > 0 && (
        <div className="flex items-start gap-2 bg-bg-tertiary rounded p-2 text-2xs text-text-secondary">
          <ShieldCheck size={12} className="text-severity-low mt-0.5 flex-shrink-0" />
          <span>
            Personal data found and redacted from analyst views and embeddings:{' '}
            {Object.entries(entities.privacy.pii_found as Record<string, number>)
              .map(([kind, n]) => `${n} ${kind.toLowerCase().replace('_', ' ')}`)
              .join(', ')}
            .
          </span>
        </div>
      )}

      {entities.suspects?.length > 0 && (
        <div>
          <p className="text-text-muted mb-1">Suspects ({entities.suspects.length})</p>
          {entities.suspects.slice(0, 2).map((s, i) => (
            <div key={i} className="bg-bg-tertiary rounded p-2 text-2xs text-text-secondary mb-1">
              {[s.gender, s.age ? `Age ${s.age}` : null, s.build, s.complexion].filter(Boolean).join(' · ')}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function LegalPanel({ legal }: { legal: LegalAnalysis }) {
  return (
    <div className="space-y-1.5">
      <p className="text-text-muted flex items-center gap-1.5">
        <Scale size={12} /> Sections cited (incident governed by {legal.governing_code})
      </p>
      <div className="space-y-1">
        {legal.mapped.map((m, i) => (
          <div key={i} className="flex items-center justify-between gap-2 bg-bg-tertiary rounded px-2 py-1">
            <span className="font-mono text-2xs text-accent-purple">
              {m.ipc ? `IPC ${m.ipc}` : '—'} → {m.bns ? `BNS ${m.bns}` : 'no equivalent'}
            </span>
            <span className="text-2xs text-text-secondary truncate">{m.offence ?? m.note}</span>
          </div>
        ))}
      </div>
      {legal.warnings.map((w) => (
        <p key={w} className="text-2xs text-severity-medium flex items-start gap-1">
          <AlertCircle size={11} className="mt-0.5 flex-shrink-0" /> {w}
        </p>
      ))}
    </div>
  )
}
