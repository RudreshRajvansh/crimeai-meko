import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { format, formatDistanceToNow, parseISO } from 'date-fns'
import type { CrimeSeverity, AlertSeverity, UserRole } from '@/types'

/** Merge Tailwind classes safely */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format ISO date string to human-readable */
export function formatDate(iso: string, fmt = 'dd MMM yyyy, HH:mm') {
  try { return format(parseISO(iso), fmt) } catch { return iso }
}

/** "3 hours ago" style */
export function timeAgo(iso: string) {
  try { return formatDistanceToNow(parseISO(iso), { addSuffix: true }) } catch { return iso }
}

/** Severity → Tailwind badge class */
export function severityBadgeClass(severity: AlertSeverity | string): string {
  const map: Record<string, string> = {
    low: 'badge-low', medium: 'badge-medium',
    high: 'badge-high', critical: 'badge-critical',
  }
  return map[severity] ?? 'badge-medium'
}

/** Numeric severity (1-5) → label */
export function severityLabel(s: CrimeSeverity | number): string {
  const labels = ['', 'Very Low', 'Low', 'Medium', 'High', 'Critical']
  return labels[s] ?? 'Unknown'
}

/** Numeric severity → colour */
export function severityColor(s: number): string {
  if (s <= 1) return '#3fb950'
  if (s <= 2) return '#88c0d0'
  if (s <= 3) return '#d29922'
  if (s <= 4) return '#f85149'
  return '#ff7b72'
}

/** Risk score (0-100) → colour */
export function riskColor(score: number): string {
  if (score < 20) return '#3fb950'
  if (score < 45) return '#d29922'
  if (score < 70) return '#f85149'
  return '#ff7b72'
}

/** Crime status → badge variant */
export function statusBadge(status: string): string {
  const map: Record<string, string> = {
    reported: 'bg-accent-blue/10 text-accent-blue',
    under_investigation: 'bg-severity-medium-bg text-severity-medium',
    resolved: 'bg-severity-low-bg text-severity-low',
    closed: 'bg-bg-elevated text-text-secondary',
  }
  return map[status] ?? 'bg-bg-elevated text-text-secondary'
}

/** Role → display label */
export function roleLabel(role: UserRole | string): string {
  const map: Record<string, string> = {
    admin: 'Administrator', police: 'Police Officer',
    analyst: 'Crime Analyst', readonly: 'Read Only',
  }
  return map[role] ?? role
}

/** Format large numbers with commas */
export function formatNumber(n: number): string {
  return new Intl.NumberFormat('en-IN').format(n)
}

/** Truncate long strings */
export function truncate(str: string, maxLen = 60): string {
  if (str.length <= maxLen) return str
  return str.slice(0, maxLen - 1) + '…'
}

/** Crime type → display label */
export function crimeTypeLabel(type: string): string {
  return type.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Month number → short name */
export function monthName(m: number): string {
  return ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m - 1] ?? ''
}

/** Leaflet popups and icons are HTML strings; every value that came from user input must be escaped first. */
export function escapeHtml(value: string | number | null | undefined): string {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]!)
}
