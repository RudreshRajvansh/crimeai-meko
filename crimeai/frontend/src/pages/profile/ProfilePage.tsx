import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, User as UserIcon, Upload, Info } from 'lucide-react'
import { useForm } from 'react-hook-form'
import toast from 'react-hot-toast'

import { useAuthStore } from '@/store/auth'
import { getErrorMessage, api } from '@/services'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import { roleLabel, cn, formatDate } from '@/utils'
import Badge from '@/components/ui/Badge'
import type { ProfileChangeRequestResponse } from '@/types'

const DEPARTMENTS = [
  'Cyber Crime Cell',
  'Criminal Investigation Department (CID)',
  'Anti-Terrorism Squad (ATS)',
  'Narcotics Control Bureau (NCB)',
  'Local Police Station',
  'Intelligence Bureau (IB)',
  'Forensics Department',
  'Other'
]

const DESIGNATIONS = [
  'Constable',
  'Head Constable',
  'Sub-Inspector',
  'Inspector',
  'Deputy Superintendent',
  'Superintendent',
  'Analyst',
  'Investigator',
  'Other'
]

export default function ProfilePage() {
  const user = useAuthStore(s => s.user)
  const qc = useQueryClient()
  const [isEditing, setIsEditing] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  
  const { register, handleSubmit, reset } = useForm({
    defaultValues: {
      department: user?.department || '',
      designation: user?.designation || '',
    }
  })

  const { data: fullProfile, isLoading: profileLoading } = useQuery({
    queryKey: ['profile', 'me'],
    queryFn: () => api.get<any>('/users/me').then(r => r.data),
  })

  const { data: requests, isLoading } = useQuery({
    queryKey: ['profile', 'requests'],
    queryFn: () => api.get<{items: ProfileChangeRequestResponse[]}>('/users/profile/change-requests').then(r => r.data),
  })

  // Use the full profile if available, otherwise fallback to the basic user info from the store
  const displayUser = fullProfile || user

  const submitChange = useMutation({
    mutationFn: async (data: any) => {
      if (!file) throw new Error("Proof document is required to make changes")
      const formData = new FormData()
      formData.append('proof', file)
      if (data.department && data.department !== user?.department) formData.append('department', data.department)
      if (data.designation && data.designation !== user?.designation) formData.append('designation', data.designation)
      
      let hasChanges = false
      for (const [key] of formData.entries()) {
        if (key !== 'proof') hasChanges = true
      }
      
      if (!hasChanges) throw new Error("No changes made")
      
      return api.post('/users/profile/change-request', formData).then(r => r.data)
    },
    onSuccess: () => {
      toast.success('Change request submitted for approval')
      setIsEditing(false)
      setFile(null)
      qc.invalidateQueries({ queryKey: ['profile', 'requests'] })
    },
    onError: (err) => toast.error(getErrorMessage(err))
  })

  if (!user || profileLoading) return <PageLoader />

  return (
    <div className="max-w-4xl mx-auto p-5 space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text-primary flex items-center gap-2">
          <UserIcon className="text-accent-blue" />
          My Profile
        </h1>
        {!isEditing && (
          <button onClick={() => setIsEditing(true)} className="btn-secondary">
            Edit Profile
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Profile Card */}
        <div className="md:col-span-1 card p-6 text-center space-y-4">
          <div className="w-24 h-24 mx-auto rounded-full bg-accent-blue/10 flex items-center justify-center border-2 border-accent-blue/20">
            <span className="text-3xl font-bold text-accent-blue">
              {displayUser.full_name.charAt(0).toUpperCase()}
            </span>
          </div>
          <div>
            <h2 className="text-lg font-medium text-text-primary">{displayUser.full_name}</h2>
            <p className="text-sm text-text-secondary">{displayUser.email}</p>
          </div>
          <Badge variant={displayUser.is_active ? 'green' : 'red'}>
            {displayUser.is_active ? 'Active' : 'Inactive'}
          </Badge>
        </div>

        {/* Details Form */}
        <div className="md:col-span-2 card p-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4 border-b border-border-subtle pb-2">
            Account Details
          </h3>
          
          <form onSubmit={handleSubmit(data => submitChange.mutate(data))} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">Full Name</label>
                <input type="text" className="input bg-bg-secondary cursor-not-allowed" value={displayUser.full_name} disabled />
                <p className="text-2xs text-text-muted mt-1 flex items-center gap-1"><Info size={10}/> Cannot be changed</p>
              </div>
              
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">Badge/Employee ID</label>
                <input type="text" className="input bg-bg-secondary cursor-not-allowed font-mono" value={displayUser.badge_number || ''} disabled />
                <p className="text-2xs text-text-muted mt-1 flex items-center gap-1"><Info size={10}/> Cannot be changed</p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">Role</label>
                <input type="text" className="input bg-bg-secondary cursor-not-allowed" value={roleLabel(displayUser.role)} disabled />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-2 border-t border-border-subtle">
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">Department</label>
                {isEditing ? (
                  <select {...register('department')} className="input py-2">
                    <option value="">Select Department...</option>
                    {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                ) : (
                  <input type="text" className="input bg-bg-secondary cursor-not-allowed" value={displayUser.department || 'Not set'} disabled />
                )}
              </div>
              
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">Designation</label>
                {isEditing ? (
                  <select {...register('designation')} className="input py-2">
                    <option value="">Select Designation...</option>
                    {DESIGNATIONS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                ) : (
                  <input type="text" className="input bg-bg-secondary cursor-not-allowed" value={displayUser.designation || 'Not set'} disabled />
                )}
              </div>
            </div>

            {isEditing && (
              <div className="pt-4 space-y-3">
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-md">
                  <p className="text-xs text-amber-500 flex items-start gap-1.5">
                    <Info size={14} className="mt-0.5 shrink-0" />
                    To change your Department or Designation, you must upload an official ID or transfer order as proof. An administrator will review your request.
                  </p>
                </div>
                
                <div>
                  <label className="block text-xs font-medium text-text-secondary mb-1">Proof of Change (Image or PDF)</label>
                  <label className="flex items-center justify-center w-full h-24 px-4 transition bg-bg-primary border-2 border-border-medium border-dashed rounded-md appearance-none cursor-pointer hover:border-accent-blue focus:outline-none">
                    <div className="flex flex-col items-center space-y-2">
                      <Upload size={20} className="text-text-muted" />
                      <span className="text-xs font-medium text-text-secondary">
                        {file ? file.name : "Click to select a file"}
                      </span>
                    </div>
                    <input type="file" className="hidden" accept="image/*,.pdf" onChange={(e) => e.target.files && setFile(e.target.files[0])} />
                  </label>
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button type="button" onClick={() => { setIsEditing(false); reset() }} className="btn-secondary">
                    Cancel
                  </button>
                  <button type="submit" disabled={submitChange.isPending || !file} className="btn-primary">
                    {submitChange.isPending ? 'Submitting...' : 'Submit Request'}
                  </button>
                </div>
              </div>
            )}
          </form>
        </div>
      </div>

      {/* Change Requests History */}
      {!isLoading && requests?.items && requests.items.length > 0 && (
        <div className="card p-6">
          <h3 className="text-sm font-semibold text-text-primary mb-4">Change Requests History</h3>
          <div className="table-wrapper">
            <table className="table-base">
              <thead className="table-head">
                <tr>
                  <th className="table-th">Date</th>
                  <th className="table-th">Requested Changes</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">Reason</th>
                </tr>
              </thead>
              <tbody>
                {requests.items.map((req) => (
                  <tr key={req.id} className="table-row">
                    <td className="table-td text-xs text-text-muted whitespace-nowrap">{formatDate(req.created_at)}</td>
                    <td className="table-td text-xs text-text-secondary font-mono">{JSON.stringify(req.requested_changes)}</td>
                    <td className="table-td">
                      <Badge variant={req.status === 'approved' ? 'green' : req.status === 'rejected' ? 'red' : 'amber'}>
                        {req.status}
                      </Badge>
                    </td>
                    <td className="table-td text-xs text-text-muted max-w-[200px] truncate">
                      {req.rejection_reason || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
