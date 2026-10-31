/** Investigation intelligence for one case: documents, agent findings with reviews, timeline, Meko context. */
import type { MekoCall, MekoRecalled } from './meko'

export type ReviewStatus = 'open' | 'accepted' | 'rejected' | 'needs_investigation'

export interface CaseDocument {
  id: string
  doc_type: string
  type_label: string
  title: string
  recorded_at: string | null
  language: string | null
  text: string
  source_ref: string | null
  removable: boolean
}

export interface FindingClaim {
  doc_id: string
  doc_title: string
  doc_type: string
  subject: string
  value: string
  display: string
  quote: string
}

export interface Finding {
  fingerprint: string
  agent: 'evidence' | 'timeline'
  kind: 'contradiction' | 'gap'
  subject: string
  title: string
  difference: string
  claims: FindingClaim[]
  suggested_action: string
  documents: string[]
  from?: string
  to?: string
  status: ReviewStatus
  review_note: string | null
  reviewed_at: string | null
}

export interface TimelineEvent {
  at: string
  date_only: boolean
  label: string
  kind: 'incident' | 'document' | 'mention' | 'evidence' | 'custody'
  source: string
  source_id: string | null
  quote: string | null
}

export interface InvestigationView {
  case_ref: string
  documents: CaseDocument[]
  agents: { name: string; summary: string }[]
  claims: FindingClaim[]
  findings: Finding[]
  timeline: TimelineEvent[]
  gap_days: number
  time_tolerance_min: number
  review_statuses: ReviewStatus[]
  meko: { status: 'ok' | 'off' | 'error'; error?: string; items: MekoRecalled[]; recalled?: number; calls: MekoCall[] }
}

export interface ReviewResult {
  fingerprint: string
  status: ReviewStatus
  review_note: string | null
  meko: { status: string; promoted?: boolean; error?: string | null }
}

export interface GeminiNote {
  explanation: string
  likely_cause: string
  verify_with: string
  next_step: string
}

export interface GeminiReview {
  model: string
  generated_at: string
  chars_sent: number
  redactions: Record<string, number>
  findings: Record<string, GeminiNote>
  plan: string[]
  missing_documents: string[]
}

export interface Seal {
  id: string
  created_at: string | null
  merkle_root: string
  leaves: number
  memo: string
  cluster: string
  signature: string | null
  slot: number | null
  status: 'anchored' | 'submitted' | 'failed'
  error: string | null
  explorer_url: string | null
}

export interface SealList {
  enabled: boolean
  cluster: string
  address: string | null
  seals: Seal[]
}

export interface SealVerification {
  seal: Seal
  items: { kind: 'document' | 'review'; id: string; label: string; state: 'unchanged' | 'changed' | 'added' | 'removed' }[]
  record_ok: boolean
  chain: { checked: boolean; found?: boolean; matches?: boolean; memo?: string | null; slot?: number | null; block_time?: number | null; error?: string }
  intact: boolean
}
