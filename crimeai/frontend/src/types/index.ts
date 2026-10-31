export type UserRole = 'admin' | 'police' | 'analyst' | 'readonly'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  badge_number: string | null
  department: string | null
  designation?: string | null
  is_active?: boolean
  account_status?: 'pending' | 'approved' | 'rejected' | 'suspended'
  request_id?: string | null
  requested_role?: UserRole | null
  last_login_at?: string | null
  created_at?: string
  approved_at?: string | null
  rejection_reason?: string | null
}

/** Login/refresh response. The refresh token never reaches JavaScript: it lives in an HttpOnly cookie. */
export interface SessionResponse {
  access_token: string
  token_type: string
  expires_in: number
  user_id: string
  role: UserRole
  full_name: string
  email: string
}

export interface UserListResponse {
  items: User[]
  total: number
}

export interface AccessRequestResponse {
  message: string
  request_id: string
  status: string
}

export interface UserStatsResponse {
  total_users: number
  pending_requests: number
  approved_users: number
  rejected_users: number
  suspended_users: number
}

export * from './profile'

export interface AuditLogResponse {
  id: string
  user_id: string | null
  action: string
  resource_type: string
  resource_id: string | null
  method: string
  path: string
  ip_address: string | null
  extra_metadata: Record<string, unknown> | null
  created_at: string
}

export interface AuditLogListResponse {
  items: AuditLogResponse[]
  total: number
}
export type CrimeStatus = 'reported' | 'under_investigation' | 'resolved' | 'closed'
export type CrimeSeverity = 1 | 2 | 3 | 4 | 5

export interface Crime {
  id: string
  crime_type: string
  sub_type: string | null
  description: string | null
  severity: CrimeSeverity
  location_name: string | null
  address: string | null
  district: string | null
  city: string
  latitude: number
  longitude: number
  occurred_at: string
  reported_at: string
  status: CrimeStatus
  case_number: string | null
  assigned_officer_id: string | null
  cluster_id: number | null
  series_id?: string | null
  legal_sections?: string[] | null
  accused_arrested_at?: string | null
  chargesheet_filed_at?: string | null
  risk_score: number | null
  created_at: string
  updated_at: string
}

export interface CrimeListResponse {
  items: Crime[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export interface CrimeStats {
  total_crimes: number
  by_type: Record<string, number>
  by_district: Record<string, number>
  by_status: Record<string, number>
  by_severity: Record<string, number>
  by_month: Array<{ year: number; month: number; count: number }>
  avg_daily_crimes: number
  most_active_hour: number
}

export interface CrimeCreatePayload {
  crime_type: string
  sub_type?: string
  description?: string
  severity: number
  latitude: number
  longitude: number
  location_name?: string
  address?: string
  district?: string
  city: string
  occurred_at: string
  status?: CrimeStatus
  case_number?: string
}

export interface HeatmapPoint {
  lat: number
  lng: number
  weight: number
}

export interface HotspotData {
  district: string
  crime_type: string
  count: number
  lat: number
  lng: number
  max_severity: number
}
export interface GeoJSONFeatureCollection {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    geometry: { type: 'Point'; coordinates: [number, number] }
    properties: {
      id: string
      crime_type: string
      severity: number
      district: string | null
      status: string
      occurred_at: string
      risk_score: number | null
    }
  }>
  metadata: Record<string, unknown>
}
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type AlertType = 'hotspot' | 'cluster' | 'high_risk' | 'pattern' | 'system' | 'manual'

export interface Alert {
  id: string
  title: string
  message: string
  alert_type: AlertType
  severity: AlertSeverity
  is_read: boolean
  is_resolved: boolean
  latitude: number | null
  longitude: number | null
  district: string | null
  related_crime_id: string | null
  target_role: string | null
  created_at: string
  updated_at: string
  cases?: LinkedCase[]
  graph_node?: string | null
  entity_kind?: string | null
}

export interface LinkedCase {
  id: string
  case_number: string | null
  crime_type: string
  district: string | null
  occurred_at: string | null
}

export interface AlertListResponse {
  items: Alert[]
  total: number
  unread_count: number
}
export type NLPStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'awaiting_ocr'

export interface FIRReport {
  id: string
  fir_number: string
  crime_id: string | null
  submitted_by: string
  incident_date: string | null
  /** Original narrative for police and above; PII-redacted copy for analysts. */
  text: string
  text_redacted: boolean
  file_type: string | null
  file_sha256: string | null
  extracted_entities: ExtractedEntities | null
  extraction_confidence: number | null
  nlp_status: NLPStatus
  nlp_error: string | null
  language?: string | null
  highlights?: TextHighlight[] | null
  has_document?: boolean
  created_at: string
  updated_at: string
}

export interface LegalAnalysis {
  governing_code: 'IPC' | 'BNS'
  citations: { section: string; code: 'IPC' | 'BNS' | null }[]
  mapped: { ipc: string | null; bns: string | null; offence: string | null; crime_type: string | null; note: string | null }[]
  suggested_crime_type: string | null
  warnings: string[]
  disclaimer: string
}

export interface CaseMapPoint {
  id: string
  label: string
  crime_type: string
  district: string | null
  severity: number
  occurred_at: string | null
  series_id: string | null
  lat: number
  lng: number
}

export interface CaseMatch extends CaseMapPoint {
  shared: string[]
  same_series: boolean
  similarity: number | null
  reason: 'identifier' | 'series' | 'modus_operandi'
}

export interface CaseMap {
  case: CaseMapPoint & { location_name: string | null }
  matches: CaseMatch[]
  counts: { identifier: number; series: number; modus_operandi: number }
}

export interface FirContext {
  crime_type: string
  confidence: number
  severity: number
  reasoning: string
  people: { name: string; role: string; detail: string }[]
  timeline: string[]
  motive: string
  relationship: string
  premeditated: boolean
  violence: boolean
  injury: boolean
  weapons: string[]
  red_flags: string[]
}

export interface ExtractedEntities {
  gemini?: GeminiBrief
  context?: FirContext
  rules_crime_type?: string | null
  locations: string[]
  primary_location: string | null
  crime_type: string | null
  crime_type_confidence: number
  weapons: string[]
  suspects: SuspectDescription[]
  time_references: string[]
  legal?: LegalAnalysis
  language?: { code: string; name: string; script: string; confidence: number; mixed_script: boolean }
  identifiers?: { vehicles: string[]; phones: string[]; upi_ids: string[]; amounts: number[]; fir_references?: string[]; dates?: string[] }
  privacy?: { pii_found: Record<string, number> }
  overall_confidence: number
  inferred_severity: number
  has_weapon: boolean
  has_injury: boolean
}

export interface SuspectDescription {
  raw_description: string
  age?: string
  gender?: 'male' | 'female'
  build?: string
  complexion?: string
  clothing?: string[]
}
export interface ClusterSummary {
  cluster_id: number
  size: number
  centroid_lat: number
  centroid_lng: number
  dominant_crime_type: string
  crime_type_breakdown: Record<string, number>
  avg_severity: number
  bbox: { min_lat: number; max_lat: number; min_lng: number; max_lng: number }
}

export interface ClusterResult {
  status: string
  num_clusters: number
  noise_points: number
  total_points: number
  coverage_pct: number
  parameters: { eps_km: number; min_samples: number }
  clusters: ClusterSummary[]
  from_cache?: boolean
}

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface RiskScore {
  score: number
  level: RiskLevel
  trend: 'rising' | 'stable' | 'falling'
  components: {
    total_crimes: number
    recent_7d: number
    recent_30d: number
    harm_per_day: number
    trend_ratio: number
    avg_severity: number
    top_types: Record<string, number>
  }
}

/** Every ML output is a versioned artifact from the model registry. */
export interface RegistryOutput<T> {
  status: 'ok' | 'not_ready'
  message?: string
  version?: number
  generated_at?: string
  metadata?: Record<string, unknown>
  data: T | null
}

export interface ShiftPrediction {
  district: string
  probability: number
  risk_level: RiskLevel
  expected_baseline: number
}

export interface ShiftForecastBlock {
  block_start: string
  block_end: string
  shift: 'night' | 'morning' | 'afternoon' | 'evening'
  predictions: ShiftPrediction[]
}

export interface CrimeSeries {
  series_id: string
  crime_type: string
  size: number
  incident_ids: string[]
  districts: string[]
  cross_jurisdiction: boolean
  first_seen: string
  last_seen: string
  centroid: { lat: number; lng: number }
  radius_km: number
  cohesion: number
  median_gap_days: number | null
  next_window: { from: string; to: string } | null
  key_terms: string[]
  languages?: string[]
  cross_language?: boolean
}

export interface CustodyDeadline {
  crime_id: string
  case_number: string | null
  crime_type: string
  district: string | null
  assigned_officer_id: string | null
  arrested_at: string
  limit_days: 60 | 90
  deadline: string
  days_remaining: number
  status: 'on_track' | 'due_soon' | 'overdue'
  escalation: RiskLevel | null
  /** The clock runs from the first remand; "arrest" means no remand date was recorded. */
  clock_starts: 'remand' | 'arrest'
  approximate: boolean
  track_basis: 'section' | 'default'
  needs_verification: boolean
  track_note: string | null
}

export interface CustodyDeadlineList {
  total: number
  overdue: number
  due_soon: number
  items: CustodyDeadline[]
  basis: string
}

export interface ModelCard {
  hotspot_model: {
    version: number | null
    trained_at: string | null
    evaluation: {
      threshold: number
      roc_auc: number | null
      pr_auc: number | null
      brier: number | null
      baseline_roc_auc: number | null
      beats_baseline: boolean
      positive_rate: number
      n_train: number
      n_test: number
      feature_importance: Record<string, number>
    } | null
    intended_use: string
    limitations: string[]
  }
  embedding_model: string
  risk_index: string
}
export interface PatrolStop {
  stop_number: number
  node_id: string
  label: string
  lat: number
  lng: number
  risk_score: number
  crime_count: number
  node_type: string
  distance_from_prev_km: number
  cumulative_distance_km: number
}

export interface RoadPath {
  provider: string
  profile: 'car' | 'foot'
  geometry: [number, number][]
  distance_km: number
  duration_min: number
  legs: { distance_km: number; duration_min: number }[]
}

export interface PatrolRoute {
  route_id: string
  strategy: string
  district: string
  checkpoints: PatrolStop[]
  total_distance_km: number
  estimated_duration_minutes: number
  total_risk_covered: number
  coverage_radius_km: number
  generated_at: string
  from_cache?: boolean
  road?: RoadPath | null
  straight_line_km?: number
}
export interface SimulationScenario {
  id: string
  name: string
  description: string
  parameters: Record<string, { type: string; range?: [number, number]; default?: number }>
}

export interface SimulationResult {
  simulation_id: string
  scenario: string
  district: string
  parameters: Record<string, unknown>
  num_simulations: number
  baseline: {
    crimes_per_day: number
    by_type: Record<string, number>
    risk_level: string
  }
  projected: {
    crimes_per_day: number
    by_type: Record<string, number>
    risk_level: string
  }
  reduction: {
    mean_pct: number
    std_pct: number
    p5_pct: number
    p50_pct: number
    p95_pct: number
    confidence_interval_95: [number, number]
  }
  simulated_at: string
  metadata?: SimulationMetadata
}

export interface PatrolCurvePoint {
  officers_added: number
  crimes_per_day: number
  reduction_pct: number
}

export interface SimulationMetadata {
  intervention_strength: number
  lookback_days: number
  n_crimes_in_baseline: number
  officers?: { current: number; added: number; total: number; increase_pct: number }
  prevented_per_month?: number
  prevented_per_officer_month?: number
  response_curve?: PatrolCurvePoint[]
}
export interface PaginationParams {
  limit?: number
  offset?: number
}
export interface APIError {
  error: string
  message: string
  path: string
  detail?: unknown
}
export type WSMessage =
  | { type: 'connected'; role: string }
  | { type: 'new_alert'; alert_id: string; severity: AlertSeverity; title: string; alert_type: string; district: string | null }
  | { type: 'ping' }
  | { type: 'pong' }

export interface GraphNode {
  id: string
  type: 'crime' | 'vehicle' | 'phone' | 'upi' | 'account' | 'series'
  label: string
  crime_type?: string
  district?: string | null
  severity?: number
  occurred_at?: string | null
  series_id?: string | null
  case_count?: number
  size?: number
  lat?: number
  lng?: number
  first_seen?: string
  last_seen?: string
}

export interface GraphPayload {
  nodes: GraphNode[]
  links: { source: string; target: string; kind: string }[]
  stats: { cases: number; entities: number; series: number; districts: number; entities_by_kind?: Record<string, number>; linking_entities?: number }
}

export interface TextHighlight {
  start: number
  end: number
  text: string
  kind: string
  gloss: string
  language: string
}

export interface LanguageInfo {
  code: string
  name: string
  script: string
  confidence: number
}

export interface Dossier {
  case: Crime
  fir: { id: string; fir_number: string; nlp_status: string; file_sha256: string | null; entities: ExtractedEntities | null } | null
  narrative: { text: string; redacted: boolean; language: LanguageInfo; highlights: TextHighlight[] }
  legal: LegalAnalysis | null
  linked_entities: GraphNode[]
  similar_cases: { id: string; crime_type: string; district: string | null; occurred_at: string | null; case_number: string | null; description: string; similarity: number; series_id: string | null }[]
  series: CrimeSeries | null
  custody: CustodyDeadline | null
  evidence?: { links: EvidenceLink[]; s105_gap: string | null }
  context: { within_1km_30d: number; same_type_within_1km_30d: number; district_rank_for_type: number | null; harm_weight: number | null }
}

export interface TemporalMatrix {
  days: string[]
  matrix: number[][]
  max: number
  peak: { day: number; hour: number; count: number }
  timezone: string
}

export interface LanguageMix {
  counts: { code: string; name: string; native: string | null; count: number }[]
  supported: { code: string; name: string; native: string; script: string }[]
  embedding_model: string
}

export interface TimelinePayload {
  since: string
  until: string
  points: [number, number, number, string, number, string | null][]
}

export interface SearchResults {
  query: string
  language: string
  cases: { id: string; case_number: string | null; crime_type: string; district: string | null; occurred_at: string; snippet: string }[]
  semantic: { id: string; case_number: string | null; crime_type: string; district: string | null; occurred_at: string; snippet: string; similarity: number }[]
  firs: { id: string; fir_number: string; language: string | null; crime_id: string | null }[]
  entities: GraphNode[]
}

export interface SystemStatus {
  uptime_seconds: number
  version: string
  data: Record<string, number>
  queues: Record<string, number | null>
  workers: string[]
  websocket_clients: number
  artifacts: { name: string; version: number; updated_at: string }[]
  hotspot_model: { version: number; roc_auc: number | null; baseline_roc_auc: number | null; beats_baseline: boolean | null } | null
  nlp: { embedding_model: string; languages_supported: number; zero_shot_enabled: boolean }
  schedule: { name: string; task: string; schedule: string }[]
}

export interface FreezePacket {
  entity: { id: string; kind: 'upi' | 'account' | 'phone'; label: string; identifier: string | null }
  complaints: {
    crime_id: string
    case_number: string | null
    fir_numbers: string[]
    occurred_at: string
    district: string | null
    crime_type: string
    amount: number | null
  }[]
  totals: { complaints: number; districts: string[]; amount: number | null; first: string; latest: string; hours_since_latest: number }
  draft: string
  legal_basis: string
}

export interface Connector {
  id: string
  name: string
  owner: string
  status: 'file' | 'manual' | 'planned' | 'excluded'
  receives: string[]
  sends: string[]
  onboarding: string
  guardrail: string | null
}

export interface ImportReport {
  received: number
  created: number
  skipped: number
  error_count: number
  errors: { row: number; error: string }[]
  link_alerts?: number
}

export interface EvidenceLink {
  id: string
  sid: string
  packet_hash: string | null
  provision: string
  provision_label: string
  captured_at: string | null
  note: string | null
  linked_at: string | null
}

export interface SwarmSeed {
  crime_id: string
  case_number: string
  crime_type: string
  district: string | null
  identifier: string
  kind: string
  cases: number
}

export interface SwarmAgent {
  id: string
  kind: string
  label: string
  anchor: [number, number]
  frozen: boolean
  cases: number
  case_ids: string[]
  share: number
}

export interface SwarmEvent {
  t: number
  lat: number
  lng: number
  agent: string
  stopped: 'patrol' | 'freeze' | null
}

export interface SwarmResult {
  seed_case: { id: string; case_number: string | null }
  basis: 'linked' | 'near-repeat'
  params: { days: number; runs: number; patrols: number; freeze: boolean; rate_per_day: number; acceleration: number; spread_km: number; street_pattern: boolean }
  cases: Array<{ id: string; lat: number; lng: number; type: string; district: string | null; occurred_at: string; case_number: string }>
  agents: SwarmAgent[]
  patrol_posts: Array<{ lat: number; lng: number }>
  outlook: {
    p_hit_baseline: number
    p_hit_intervention: number
    expected_hits_baseline: number
    expected_hits_intervention: number
    prevented_pct: number
    prevented_by: Record<string, number>
    median_hours_to_next: number | null
    peak_hour_ist: number
    likely_district: string | null
  }
  curve: { baseline: number[]; intervention: number[] }
  daily: { baseline: number[]; intervention: number[] }
  hours: number[]
  districts: Array<{ district: string; share: number }>
  heat: Array<{ lat: number; lng: number; w: number }>
  samples: SwarmEvent[][]
  note: string
}

export interface GeminiSection {
  code: string
  section: string
  reason: string
  official_title?: string | null
  status: 'cited_in_fir' | 'new' | 'wrong_code' | 'title_differs'
}

export interface GeminiBrief {
  model: string
  generated_at: string
  governing_code: string
  redactions: Record<string, number>
  chars_sent: number
  english: string
  summary: string
  offence: string
  modus_operandi: string[]
  facts: { when: string; where: string; property: string; weapon: string }
  suggested_sections: GeminiSection[]
  missing: string[]
}

export interface LinkCheckCase {
  id: string
  case_number: string | null
  crime_type: string
  district: string | null
  occurred_at: string | null
  language: string | null
}

export interface LinkCheckMatch {
  kind: 'vehicle' | 'phone' | 'upi' | 'account'
  label: string
  entity_id: string | null
  case_count: number
  districts: string[]
  cases: LinkCheckCase[]
}

export interface LinkCheck {
  language: string
  language_name: string
  identifiers: number
  known: number
  matches: LinkCheckMatch[]
}
