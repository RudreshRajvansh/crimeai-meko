/** Meko shared memory: what the backend recalled, stored and decided, exactly as Meko returned it. */

export type MekoCategory = 'write' | 'recall' | 'promote' | 'delete' | 'session' | 'admin'
export type MekoDatapack = 'agency' | 'grid'

export interface MekoCall {
  id: string
  ts?: string
  run_id: string
  agent: string
  tool: string
  category: MekoCategory
  datapack: string | null
  transport: string
  ok: boolean
  latency_ms: number
  summary: string
  args?: Record<string, unknown>
  result?: unknown
}

export interface MekoParsed {
  kind: 'sighting' | 'series' | 'exclusion' | 'case' | 'other'
  tokens: string[]
  refs: string[]
  series_ids: string[]
  tags: string[]
  lead: string
  note: string
}

export interface MekoRecalled {
  ref: string
  id: string | null
  text: string
  score: number | null
  datapack: string
  source: string
  agent: string
  call_id: string | null
  parsed: MekoParsed
}

export interface MekoKbPassage {
  ref: string
  id: string | null
  text: string
  score: number | null
  source: string
  call_id: string | null
}

export interface MekoIdentifier {
  kind: 'phone' | 'upi' | 'account' | 'vehicle'
  noun: string
  token: string
  label: string
}

export interface MekoLink {
  ref: string
  agency: string
  agency_name: string
  tokens: string[]
  evidence: string[]
}

export interface MekoSeriesMatch {
  series_id: string
  tokens: string[]
  mo_tags: string[]
  refs: string[]
  basis: string[]
  evidence: string[]
  lead: string
  note: string
  member: boolean
  confidence: string
}

export interface MekoSimilar {
  ref: string
  agency: string
  agency_name: string
  mo_tags: string[]
  evidence: string[]
}

export interface MekoAnalysis {
  links: MekoLink[]
  series: MekoSeriesMatch[]
  similar: MekoSimilar[]
  excluded: { token: string; ref: string; memory_id: string | null }[]
}

export interface MekoStep {
  agent: string
  label: string
  calls: string[]
  errors: string[]
}

export interface MekoRecall {
  status: 'ok' | 'off' | 'error'
  error?: string
  agency: string
  agency_name: string
  identifiers: MekoIdentifier[]
  mo_tags: string[]
  run_id?: string
  steps?: MekoStep[]
  recalled?: MekoRecalled[]
  kb?: MekoKbPassage[]
  analysis?: MekoAnalysis
  calls: MekoCall[]
}

export interface MekoDecision {
  series_id?: string
  token?: string
  text: string
  memory_add: { ok: boolean; error: string | null; ids: string[] }
  promote: { ok: boolean; error: string | null }
  calls: MekoCall[]
}

export interface MekoMemoryItem {
  id: string | null
  text: string
  score: number | null
  source: string
  metadata: Record<string, unknown>
  parsed: MekoParsed
  writer: string | null
  local_status: string | null
}

export interface MekoMemoryList {
  datapack: MekoDatapack
  ok: boolean
  error: string | null
  total: number | null
  items: MekoMemoryItem[]
  calls: MekoCall[]
}

export interface MekoStatus {
  enabled: boolean
  ready: boolean
  agency: string
  agency_name: string
  mcp_url: string
  datapacks: Record<string, { name: string; id: string }>
  agents: Record<string, string>
  stats: Record<MekoCategory | 'errors' | 'total', number>
}
