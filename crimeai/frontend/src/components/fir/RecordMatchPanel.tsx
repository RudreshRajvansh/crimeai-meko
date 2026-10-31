import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, Car, CheckCircle2, CreditCard, Landmark, Phone, Radar } from 'lucide-react'
import { cn, crimeTypeLabel, formatDate } from '@/utils'
import type { LinkCheck, LinkCheckMatch } from '@/types'

const LANGUAGE_NAMES: Record<string, string> = {
  en: 'English', hi: 'Hindi', bn: 'Bengali', mr: 'Marathi', ta: 'Tamil', te: 'Telugu', gu: 'Gujarati',
  kn: 'Kannada', ml: 'Malayalam', pa: 'Punjabi', or: 'Odia', ur: 'Urdu', as: 'Assamese', ne: 'Nepali',
  'hi-Latn': 'Hinglish',
}

const KIND = {
  phone: { icon: Phone, noun: 'Phone' },
  upi: { icon: CreditCard, noun: 'UPI ID' },
  account: { icon: Landmark, noun: 'Bank account' },
  vehicle: { icon: Car, noun: 'Vehicle' },
} as const

const languageName =(code: string | null | undefined) => (code ? LANGUAGE_NAMES[code] ?? code : null)

/** "Have we seen this number before?" — every identifier in the scanned text, checked against every station's records. */
export default function RecordMatchPanel({ result, pending }: { result: LinkCheck | null; pending: boolean }) {
  if (pending) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-accent-blue/40 bg-accent-blue/5 p-3 text-xs text-accent-blue">
        <Radar size={14} className="animate-spin" /> Checking every station's records for these numbers…
      </div>
    )
  }
  if (!result) return null
  if (result.identifiers === 0) {
    return (
      <div className="rounded-md border border-border-subtle bg-bg-tertiary p-3 text-xs text-text-muted">
        No phone number, UPI ID, bank account or vehicle number found in this FIR to cross-check.
      </div>
    )
  }
  const known = result.matches.filter((m) => m.case_count > 0)
  const fresh = result.matches.filter((m) => m.case_count === 0)
  const sourceLang = result.language_name || languageName(result.language)

  return (
    <div className="space-y-2">
      {known.length > 0 ? (
        <div className="rounded-md border border-severity-high/50 bg-severity-high/[0.06] p-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-severity-high">
            <Radar size={15} className="animate-pulse" />
            Already on record: {known.length} of {result.identifiers} identifier{result.identifiers > 1 ? 's' : ''} in this {sourceLang} FIR
          </p>
          <div className="mt-2 space-y-2">
            {known.map((m) => <KnownMatch key={`${m.kind}-${m.label}`} match={m} sourceLang={result.language} />)}
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-md border border-severity-low/40 bg-severity-low/[0.06] p-3 text-xs text-severity-low">
          <CheckCircle2 size={14} /> {result.identifiers} identifier{result.identifiers > 1 ? 's' : ''} checked: none seen in any other case yet.
        </div>
      )}
      {known.length > 0 && fresh.length > 0 && (
        <p className="text-2xs text-text-muted">
          New, not seen before: {fresh.map((m) => `${KIND[m.kind].noun} ${m.label}`).join(' · ')}
        </p>
      )}
    </div>
  )
}

function KnownMatch({ match, sourceLang }: { match: LinkCheckMatch; sourceLang: string }) {
  const navigate = useNavigate()
  const { icon: Icon, noun } = KIND[match.kind]
  const otherLangs = [...new Set(match.cases.map((c) => c.language).filter((l): l is string => !!l && l !== sourceLang))]
  return (
    <div className="rounded border border-border-subtle bg-bg-primary p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Icon size={13} className="text-severity-high" />
        <span className="font-mono text-xs text-text-primary">{noun} {match.label}</span>
        <span className="rounded bg-severity-high/15 px-1.5 py-0.5 text-2xs font-semibold text-severity-high">
          {match.case_count} earlier case{match.case_count > 1 ? 's' : ''}
        </span>
        {match.districts.length > 0 && (
          <span className="text-2xs text-text-secondary">{match.districts.join(', ')}</span>
        )}
        {match.entity_id && (
          <button
            type="button"
            onClick={() => navigate('/graph', { state: { node: `entity:${match.entity_id}` } })}
            className="ml-auto inline-flex items-center gap-1 text-2xs font-medium text-accent-blue hover:underline"
          >
            Open network <ArrowUpRight size={11} />
          </button>
        )}
      </div>
      {otherLangs.length > 0 && (
        <p className="mt-1 text-2xs text-accent-purple">
          Linked across languages: also written in {otherLangs.map(languageName).join(', ')}
        </p>
      )}
      <ul className="mt-1.5 grid gap-1 sm:grid-cols-2">
        {match.cases.slice(0, 6).map((c) => (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => navigate(`/cases/${c.id}`)}
              className={cn('w-full truncate rounded bg-bg-tertiary px-2 py-1 text-left text-2xs text-text-secondary hover:text-text-primary')}
              title="Open the case dossier"
            >
              <span className="font-mono text-text-primary">{c.case_number ?? c.id.slice(0, 8)}</span>
              {' · '}{crimeTypeLabel(c.crime_type)}{c.district ? ` · ${c.district}` : ''}
              {c.occurred_at ? ` · ${formatDate(c.occurred_at, 'dd MMM yyyy')}` : ''}
              {c.language ? ` · ${languageName(c.language)}` : ''}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
