import { api } from './api'
import type {
  GeminiReview, InvestigationView, ReviewResult, ReviewStatus, Seal, SealList, SealVerification,
} from '@/types/investigation'

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

  approved: (crimeId: string) =>
    api.get<InvestigationView['meko']>(`/investigation/cases/${crimeId}/approved-context`, SLOW).then((r) => r.data),

  addDocument: (crimeId: string, body: { doc_type: string; title: string; text: string; recorded_at?: string; source_ref?: string }) =>
    api.post<{ id: string }>(`/investigation/cases/${crimeId}/documents`, body).then((r) => r.data),

  removeDocument: (crimeId: string, documentId: string) =>
    api.delete(`/investigation/cases/${crimeId}/documents/${documentId}`).then(() => undefined),

  review: (crimeId: string, fingerprint: string, decision: ReviewStatus, note: string) =>
    api.post<ReviewResult>(`/investigation/cases/${crimeId}/findings/${fingerprint}/review`, { decision, note }, SLOW).then((r) => r.data),

  gemini: (crimeId: string) =>
    api.post<GeminiReview>(`/investigation/cases/${crimeId}/gemini`, {}, SLOW).then((r) => r.data),

  seals: (crimeId: string) => api.get<SealList>(`/investigation/cases/${crimeId}/seals`).then((r) => r.data),

  seal: (crimeId: string) => api.post<Seal>(`/investigation/cases/${crimeId}/seals`, {}, SLOW).then((r) => r.data),

  verifySeal: (crimeId: string, sealId: string) =>
    api.get<SealVerification>(`/investigation/cases/${crimeId}/seals/${sealId}/verify`, SLOW).then((r) => r.data),
}
