import { api } from './api'
import type { Connector, EvidenceLink, ImportReport } from '@/types'

const upload = (path: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<ImportReport>(path, form, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data)
}

export const integrationsApi = {
  connectors: () => api.get<Connector[]>('/integrations/').then((r) => r.data),
  importCctns: (file: File) => upload('/integrations/cctns/import', file),
  importNcrp: (file: File) => upload('/integrations/ncrp/import', file),
  cctnsEnrichment: (crimeId: string) => api.get(`/integrations/cctns/enrichment/${crimeId}`).then((r) => r.data),
  linkEvidence: (crimeId: string, body: { sid: string; provision: string; packet_hash?: string; note?: string }) =>
    api.post<EvidenceLink>(`/integrations/esakshya/${crimeId}/links`, body).then((r) => r.data),
}
