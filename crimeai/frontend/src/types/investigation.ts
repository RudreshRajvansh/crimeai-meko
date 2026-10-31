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
