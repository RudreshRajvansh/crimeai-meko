import { useState } from 'react'
import { Search, ChevronLeft, ChevronRight } from 'lucide-react'
import { useCrimeList, useDeleteCrime } from '@/hooks/useCrimes'
import { useAuthStore } from '@/store/auth'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import EmptyState from '@/components/ui/EmptyState'
import {
  formatDate, crimeTypeLabel, severityLabel, statusBadge,
  formatNumber, cn,
} from '@/utils'
import type { Crime } from '@/types'
import { CRIME_TYPES } from '@/lib/palette'

const LIMIT = 50

export default function CrimeListPage() {
  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [selectedType, setSelectedType] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const isAdmin = useAuthStore((s) => s.user?.role === 'admin')
  const deleteCrime = useDeleteCrime()

  const { data, isLoading } = useCrimeList({
    limit: LIMIT,
    offset,
    ...(selectedType && { crime_type: selectedType }),
    ...(selectedStatus && { status: selectedStatus }),
  })

  const handleDelete = (crime: Crime) => {
    if (!confirm(`Delete case ${crime.case_number}? This cannot be undone.`)) return
    deleteCrime.mutate(crime.id)
  }

  const totalPages = data ? Math.ceil(data.total / LIMIT) : 0
  const currentPage = Math.floor(offset / LIMIT) + 1

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-48 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            className="input pl-9"
            placeholder="Search crimes…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <select
          className="input w-40"
          value={selectedType}
          onChange={(e) => { setSelectedType(e.target.value); setOffset(0) }}
        >
          <option value="">All types</option>
          {CRIME_TYPES.map((t) => (
            <option key={t} value={t}>{crimeTypeLabel(t)}</option>
          ))}
        </select>

        <select
          className="input w-44"
          value={selectedStatus}
          onChange={(e) => { setSelectedStatus(e.target.value); setOffset(0) }}
        >
          <option value="">All statuses</option>
          <option value="reported">Reported</option>
          <option value="under_investigation">Under Investigation</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>

        <div className="ml-auto flex items-center gap-2">
          {data && (
            <span className="text-xs text-text-muted">
              {formatNumber(data.total)} records
            </span>
          )}
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <PageLoader label="Loading crimes…" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No crimes found" description="Try adjusting your filters." />
      ) : (
        <>
          <div className="table-wrapper">
            <table className="table-base">
              <thead className="table-head">
                <tr>
                  <th className="table-th">Case #</th>
                  <th className="table-th">Type</th>
                  <th className="table-th">District</th>
                  <th className="table-th">Severity</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">Date</th>
                  <th className="table-th">Risk</th>
                  {isAdmin && <th className="table-th">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {data.items.map((crime) => (
                  <tr key={crime.id} className="table-row">
                    <td className="table-td font-mono text-xs text-accent-blue">
                      {crime.case_number ?? '—'}
                    </td>
                    <td className="table-td">{crimeTypeLabel(crime.crime_type)}</td>
                    <td className="table-td text-text-secondary">{crime.district ?? '—'}</td>
                    <td className="table-td">
                      <span className="text-xs">{severityLabel(crime.severity)}</span>
                    </td>
                    <td className="table-td">
                      <span className={cn('text-2xs px-2 py-0.5 rounded font-medium', statusBadge(crime.status))}>
                        {crime.status.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className="table-td text-text-secondary text-xs whitespace-nowrap">
                      {formatDate(crime.occurred_at, 'dd MMM yy')}
                    </td>
                    <td className="table-td">
                      {crime.risk_score != null ? (
                        <span className="font-mono text-xs">{crime.risk_score.toFixed(1)}</span>
                      ) : <span className="text-text-muted text-xs">—</span>}
                    </td>
                    {isAdmin && (
                      <td className="table-td">
                        <button
                          onClick={() => handleDelete(crime)}
                          className="text-2xs text-severity-high hover:underline"
                        >
                          Delete
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between text-xs text-text-secondary">
            <span>Page {currentPage} of {totalPages}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                disabled={offset === 0}
                className="btn-secondary text-xs px-3 py-1.5 disabled:opacity-40"
              >
                <ChevronLeft size={13} />
              </button>
              <button
                onClick={() => setOffset(offset + LIMIT)}
                disabled={!data.has_more}
                className="btn-secondary text-xs px-3 py-1.5 disabled:opacity-40"
              >
                <ChevronRight size={13} />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
