import { api } from './api'
import type { InvestigationView, ReviewResult, ReviewStatus } from '@/types/investigation'

export const DOCUMENT_TYPES: Record<string, string> = {
  witness_statement: 'Witness statement',
  investigation_report: 'Investigation report',
  forensic_report: 'Forensic report',
  cctv_note: 'CCTV description',
  seizure_memo: 'Seizure memo',
  bank_statement: 'Bank or UPI statement',
  chargesheet: 'Charge sheet',
  court_document: 'Court document',
}

const SLOW = { timeout: 120_000 }

export const investigationApi = {
  view: (crimeId: string, meko = true) =>
    api.get<InvestigationView>(`/investigation/cases/${crimeId}`, { ...SLOW, params: { meko } }).then((r) => r.data),

  addDocument: (crimeId: string, body: { doc_type: string; title: string; text: string; recorded_at?: string; source_ref?: string }) =>
    api.post<{ id: string }>(`/investigation/cases/${crimeId}/documents`, body).then((r) => r.data),

  removeDocument: (crimeId: string, documentId: string) =>
    api.delete(`/investigation/cases/${crimeId}/documents/${documentId}`).then(() => undefined),

  review: (crimeId: string, fingerprint: string, decision: ReviewStatus, note: string) =>
    api.post<ReviewResult>(`/investigation/cases/${crimeId}/findings/${fingerprint}/review`, { decision, note }, SLOW).then((r) => r.data),
}
