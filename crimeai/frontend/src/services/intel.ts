import { api } from './api'
import type { Crime, CrimeSeries, CustodyDeadlineList, LegalAnalysis, RegistryOutput, SwarmResult, SwarmSeed } from '@/types'

export const intelApi = {
  swarmSeeds: () => api.get<SwarmSeed[]>('/intel/swarm/seeds').then((r) => r.data),

  swarm: (crimeId: string, body: { days: number; patrols: number; freeze: boolean; runs?: number }) =>
    api.post<SwarmResult>(`/intel/swarm/${crimeId}`, body).then((r) => r.data),

  series: (activeWithinDays = 30) =>
    api
      .get<RegistryOutput<CrimeSeries[]>>('/intel/series', { params: { active_within_days: activeWithinDays } })
      .then((r) => r.data),

  seriesIncidents: (seriesId: string) =>
    api.get<Crime[]>(`/intel/series/${encodeURIComponent(seriesId)}/incidents`).then((r) => r.data),

  detectSeries: () => api.post('/intel/series/detect').then((r) => r.data),

  custodyDeadlines: (params?: { district?: string; only_due_within_days?: number }) =>
    api.get<CustodyDeadlineList>('/intel/custody-deadlines', { params }).then((r) => r.data),

  legalSections: (text: string, incident_date?: string) =>
    api.post<LegalAnalysis>('/nlp/legal-sections', { text, incident_date }).then((r) => r.data),

  dailyBriefingUrl: () => `${api.defaults.baseURL}/reports/daily-briefing.pdf`,

  downloadBriefing: () =>
    api.get('/reports/daily-briefing.pdf', { responseType: 'blob' }).then((r) => r.data as Blob),
}
