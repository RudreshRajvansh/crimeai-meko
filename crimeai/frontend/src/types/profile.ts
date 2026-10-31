export interface ProfileChangeRequestResponse {
  id: string
  user_id: string
  requested_changes: Record<string, string>
  /** API path that streams the proof to its owner or an administrator. */
  proof_url: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
  resolved_at?: string | null
  resolved_by?: string | null
  rejection_reason?: string | null
}

export interface ProfileChangeRequestListResponse {
  items: ProfileChangeRequestResponse[]
  total: number
}
