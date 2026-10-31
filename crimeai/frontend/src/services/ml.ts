import { api } from './api'
import type {
  ClusterResult,
  ModelCard,
  PatrolRoute,
  RegistryOutput,
  RiskScore,
  ShiftForecastBlock,
  SimulationResult,
  SimulationScenario,
} from '@/types'

interface QueuedJob {
  status: 'queued' | 'queue_unavailable'
  task_id?: string
  message?: string
}

export const mlApi = {
  getClusters: () => api.get<RegistryOutput<ClusterResult>>('/ml/clusters').then((r) => r.data),

  triggerClustering: (params?: { eps_km?: number; auto_eps?: boolean }) =>
    api.post<QueuedJob>('/ml/cluster', null, { params }).then((r) => r.data),

  getRiskMap: () => api.get<RegistryOutput<Record<string, RiskScore>>>('/ml/risk-map').then((r) => r.data),

  getShiftForecast: () =>
    api.get<RegistryOutput<ShiftForecastBlock[]>>('/ml/hotspot-predictions').then((r) => r.data),

  triggerHotspotPrediction: () => api.post<QueuedJob>('/ml/hotspot-prediction').then((r) => r.data),

  triggerEmbedding: (limit = 1000) =>
    api.post<QueuedJob>('/ml/embed-crimes', null, { params: { limit } }).then((r) => r.data),

  getAreaProfile: (district: string, lookback_days = 60) =>
    api.get(`/ml/profile/${encodeURIComponent(district)}`, { params: { lookback_days } }).then((r) => r.data),

  getModelCard: () => api.get<ModelCard>('/ml/model-card').then((r) => r.data),

  getTaskStatus: (taskId: string) => api.get(`/ml/tasks/${taskId}`).then((r) => r.data),

  runSimulation: (payload: {
    scenario: string
    district: string
    parameters: Record<string, unknown>
    num_simulations?: number
  }) => api.post<SimulationResult>('/simulation/run', payload).then((r) => r.data),

  getScenarios: () => api.get('/simulation/scenarios').then((r) => r.data as SimulationScenario[]),

  optimizePatrol: (payload: {
    start_lat: number
    start_lng: number
    district: string
    strategy?: string
    num_checkpoints?: number
    patrol_type?: string
  }) => api.post<PatrolRoute>('/patrol/optimize', payload).then((r) => r.data),
}
