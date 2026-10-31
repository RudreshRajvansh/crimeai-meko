import { api } from './api'
import type { FIRReport, GeminiBrief, LinkCheck } from '@/types'

export const firApi = {
  list: (params?: Record<string, unknown>) =>
    api.get<{ items: FIRReport[]; total: number }>('/fir/', { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<FIRReport>(`/fir/${id}`).then((r) => r.data),

  submit: (payload: { fir_number: string; raw_text: string; crime_id?: string; incident_date?: string }) =>
    api.post<FIRReport>('/fir/', payload).then((r) => r.data),

  upload: (fir_number: string, file: File, incident_date?: string) => {
    const form = new FormData()
    form.append('fir_number', fir_number)
    form.append('file', file)
    if (incident_date) form.append('incident_date', incident_date)
    return api
      .post<FIRReport>('/fir/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data)
  },

  document: (id: string) => api.get(`/fir/${id}/document`, { responseType: 'blob' }).then((r) => r.data as Blob),

  reprocess: (id: string) =>
    api.post(`/fir/${id}/reprocess`).then((r) => r.data),

  extract: (text: string, incident_date?: string) =>
    api.post('/nlp/extract', { text, incident_date: incident_date || undefined }).then((r) => r.data),

  geminiStatus: () =>
    api.get<{ enabled: boolean; model: string | null }>('/nlp/gemini').then((r) => r.data),

  geminiBrief: (id: string, refresh = false) =>
    api.post<GeminiBrief>(`/fir/${id}/gemini-brief`, null, { params: refresh ? { refresh: true } : undefined }).then((r) => r.data),

  handwritingOcr: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<{ text: string; chars: number }>('/nlp/handwriting-ocr', form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })
      .then((r) => r.data)
  },

  transcribe: (audio: File) => {
    const form = new FormData()
    form.append('file', audio)
    return api
      .post<{ transcript: string; statement: string; languages: string[] }>('/nlp/transcribe', form, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 })
      .then((r) => r.data)
  },

  geminiPreview: (text: string, incident_date?: string) =>
    api.post<GeminiBrief>('/nlp/gemini-brief', { text, incident_date: incident_date || undefined }).then((r) => r.data),

  linkCheck: (text: string) =>
    api.post<LinkCheck>('/graph/check', { text }).then((r) => r.data),

  classify: (text: string) =>
    api.post('/nlp/classify', { text }).then((r) => r.data),
}
