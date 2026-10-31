import { useState } from 'react'
import { Users, Activity, Cpu, UserPlus, ClipboardList, ShieldAlert, Check, X, RefreshCw } from 'lucide-react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { api, getErrorMessage, mlApi, adminApi } from '@/services'
import { PageLoader } from '@/components/ui/LoadingSpinner'
import Badge from '@/components/ui/Badge'
import { roleLabel, timeAgo, cn, formatDate } from '@/utils'
import type { User, UserListResponse, UserRole } from '@/types'

type AdminTab = 'requests' | 'profile_edits' | 'users' | 'audit' | 'ml' | 'system'

function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>('requests')
  const qc = useQueryClient()
  const { data: stats, isLoading: statsLoading } = useQuery({ queryKey: ['admin', 'stats'], queryFn: adminApi.getStats })

  const refreshGlobal = () => {
    qc.invalidateQueries({ queryKey: ['admin'] })
  }

  return (
    <div className="p-5 space-y-4 animate-fade-in">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <StatCard title="Total Users" value={stats?.total_users ?? 0} loading={statsLoading} />
        <StatCard title="Pending Requests" value={stats?.pending_requests ?? 0} loading={statsLoading} 
          className={stats?.pending_requests ? 'border-amber-500/50 bg-amber-500/5' : ''} />
        <StatCard title="Approved" value={stats?.approved_users ?? 0} loading={statsLoading} />
        <StatCard title="Rejected" value={stats?.rejected_users ?? 0} loading={statsLoading} />
        <StatCard title="Suspended" value={stats?.suspended_users ?? 0} loading={statsLoading} />
      </div>

      <div className="flex justify-between items-center mb-4">
        <div className="flex gap-1 bg-bg-secondary rounded-lg p-1 w-fit overflow-x-auto max-w-full">
          {(['requests', 'profile_edits', 'users', 'audit', 'ml', 'system'] as AdminTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={cn(
                'px-4 py-1.5 rounded-md text-sm font-medium transition-colors capitalize whitespace-nowrap',
                activeTab === tab
                  ? 'bg-bg-elevated text-text-primary shadow-inner-sm'
                  : 'text-text-muted hover:text-text-secondary'
              )}
            >
              {tab === 'ml' ? 'ML Models' : tab === 'requests' ? 'Access Requests' : tab === 'profile_edits' ? 'Profile Edits' : tab === 'audit' ? 'Audit Logs' : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
        <button onClick={refreshGlobal} className="btn-ghost text-xs px-3 py-1.5" title="Refresh Admin Panel">
          <RefreshCw size={14} className={statsLoading ? "animate-spin text-accent-blue" : ""} />
          Refresh
        </button>
      </div>

      {activeTab === 'requests' && <AccessRequestsTab />}
      {activeTab === 'profile_edits' && <ProfileEditsTab />}
      {activeTab === 'users' && <UsersTab />}
      {activeTab === 'audit' && <AuditLogsTab />}
      {activeTab === 'ml' && <MLTab />}
      {activeTab === 'system' && <SystemTab />}
    </div>
  )
}

function UsersTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => api.get<UserListResponse>('/users/').then((r) => r.data),
  })
  const refresh = () => qc.invalidateQueries({ queryKey: ['admin', 'users'] })

  const update = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Partial<Pick<User, 'role' | 'is_active'>> }) =>
      api.patch(`/users/${id}`, changes),
    onSuccess: () => {
      refresh()
      toast.success('User updated. Their open sessions were revoked.')
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  if (isLoading) return <PageLoader />

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <Users size={15} /> User Management
        </h3>
        <span className="text-xs text-text-muted">{data?.total ?? 0} users</span>
      </div>

      <CreateUserForm onCreated={refresh} />

      <div className="table-wrapper">
        <table className="table-base">
          <thead className="table-head">
            <tr>
              <th className="table-th">Name</th>
              <th className="table-th">Email</th>
              <th className="table-th">Role</th>
              <th className="table-th">Badge/Emp ID</th>
              <th className="table-th">Designation</th>
              <th className="table-th">Last sign-in</th>
              <th className="table-th">Status</th>
              <th className="table-th">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((user) => (
              <tr key={user.id} className="table-row">
                <td className="table-td font-medium">{user.full_name}</td>
                <td className="table-td text-text-secondary text-xs">{user.email}</td>
                <td className="table-td">
                  <select
                    value={user.role}
                    onChange={(e) => update.mutate({ id: user.id, changes: { role: e.target.value as UserRole } })}
                    className="input text-xs py-0.5"
                    aria-label={`Role for ${user.full_name}`}
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>{roleLabel(role)}</option>
                    ))}
                  </select>
                </td>
                <td className="table-td font-mono text-xs text-text-muted">{user.badge_number ?? '—'}</td>
                <td className="table-td font-mono text-xs text-text-muted">{user.designation ?? '—'}</td>
                <td className="table-td text-xs text-text-muted">
                  {user.last_login_at ? timeAgo(user.last_login_at) : 'Never'}
                </td>
                <td className="table-td">
                  <Badge size="sm" variant={user.is_active ? 'green' : 'gray'}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </td>
                <td className="table-td">
                  {user.account_status === 'suspended' ? (
                    <button
                      onClick={() => {
                        if (confirm(`Reactivate ${user.full_name}?`)) {
                          update.mutate({ id: user.id, changes: { is_active: true } })
                          adminApi.reactivateUser(user.id).then(refresh)
                        }
                      }}
                      className="text-2xs text-severity-low hover:underline"
                    >
                      Reactivate
                    </button>
                  ) : user.account_status === 'approved' ? (
                    <button
                      onClick={() => {
                        if (confirm(`Suspend ${user.full_name}?`)) {
                          adminApi.suspendUser(user.id).then(refresh)
                        }
                      }}
                      className="text-2xs text-severity-high hover:underline"
                    >
                      Suspend
                    </button>
                  ) : null}
                  <button onClick={() => resetPassword(user)} className="ml-3 text-2xs text-accent-blue hover:underline">
                    Reset password
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const ROLES: UserRole[] = ['readonly', 'analyst', 'police', 'admin']
/** A temporary password that meets the policy: 14 characters with upper, lower and digits, no look-alikes. */
function temporaryPassword(): string {
  const sets = ['ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnpqrstuvwxyz', '23456789']
  const all = sets.join('')
  const bytes = crypto.getRandomValues(new Uint32Array(14))
  const chars = Array.from(bytes, (b, i) => (i < 3 ? sets[i] : all)[b % (i < 3 ? sets[i].length : all.length)])
  return chars.sort(() => (crypto.getRandomValues(new Uint8Array(1))[0] > 127 ? 1 : -1)).join('')
}

async function resetPassword(user: User) {
  const password = prompt(
    `Temporary password for ${user.full_name}. Share it through an official channel. They are signed out everywhere until they sign in with it.`,
    temporaryPassword(),
  )
  if (!password) return
  try {
    await adminApi.resetPassword(user.id, password)
    toast.success(`Password reset for ${user.full_name}`)
  } catch (err) {
    toast.error(getErrorMessage(err))
  }
}

const EMPTY_FORM = { email: '', full_name: '', password: '', role: 'readonly' as UserRole, badge_number: '' }

function CreateUserForm({ onCreated }: { onCreated: () => void }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const create = useMutation({
    mutationFn: () => api.post('/users/', { ...form, badge_number: form.badge_number || undefined }),
    onSuccess: () => {
      toast.success('User created')
      setForm(EMPTY_FORM)
      onCreated()
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  return (
    <form
      className="card p-3 grid grid-cols-2 lg:grid-cols-6 gap-2 items-end"
      onSubmit={(e) => {
        e.preventDefault()
        create.mutate()
      }}
    >
      <input className="input text-xs" placeholder="Full name" value={form.full_name} onChange={set('full_name')} required />
      <input className="input text-xs" type="email" placeholder="Email" value={form.email} onChange={set('email')} required />
      <input
        className="input text-xs"
        type="password"
        placeholder="Temporary password (10+)"
        value={form.password}
        onChange={set('password')}
        minLength={10}
        required
        autoComplete="new-password"
      />
      <input className="input text-xs" placeholder="Badge no." value={form.badge_number} onChange={set('badge_number')} />
      <select className="input text-xs" value={form.role} onChange={set('role')} aria-label="Role">
        {ROLES.map((role) => (
          <option key={role} value={role}>{roleLabel(role)}</option>
        ))}
      </select>
      <button type="submit" disabled={create.isPending} className="btn-primary text-xs justify-center">
        <UserPlus size={13} /> Add user
      </button>
    </form>
  )
}

function MLTab() {
  const qc = useQueryClient()
  const { data: card, isLoading } = useQuery({ queryKey: ['admin', 'ml', 'model-card'], queryFn: mlApi.getModelCard })

  const queued = (what: string) => () => {
    toast.success(`${what} queued`)
    setTimeout(() => qc.invalidateQueries({ queryKey: ['admin', 'ml'] }), 5000)
  }
  const onError = (err: unknown) => toast.error(getErrorMessage(err))
  const train = useMutation({ mutationFn: mlApi.triggerHotspotPrediction, onSuccess: queued('Training'), onError })
  const cluster = useMutation({ mutationFn: () => mlApi.triggerClustering({ auto_eps: true }), onSuccess: queued('Clustering'), onError })
  const embed = useMutation({ mutationFn: () => mlApi.triggerEmbedding(1000), onSuccess: queued('Embedding'), onError })

  if (isLoading) return <PageLoader />
  const model = card?.hotspot_model
  const evaluation = model?.evaluation
  const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
        <Cpu size={15} /> Model Card
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-medium text-text-primary">Shift hotspot model</p>
            <Badge variant={model?.version ? 'green' : 'amber'}>{model?.version ? `v${model.version}` : 'Not trained'}</Badge>
          </div>
          {evaluation && (
            <div className="space-y-1 text-xs text-text-secondary">
              <Row label="ROC-AUC (held-out)" value={pct(evaluation.roc_auc)} />
              <Row label="Baseline ROC-AUC" value={pct(evaluation.baseline_roc_auc)} />
              <Row label="PR-AUC" value={pct(evaluation.pr_auc)} />
              <Row label="Brier score" value={evaluation.brier?.toFixed(3) ?? '—'} />
              <Row label="Positive rate" value={pct(evaluation.positive_rate)} />
              <Row label="Train / test rows" value={`${evaluation.n_train.toLocaleString()} / ${evaluation.n_test.toLocaleString()}`} />
              {model?.trained_at && <Row label="Trained" value={timeAgo(model.trained_at)} />}
              <p className={cn('pt-1 text-2xs', evaluation.beats_baseline ? 'text-severity-low' : 'text-severity-medium')}>
                {evaluation.beats_baseline
                  ? 'Beats the naive baseline on held-out weeks.'
                  : 'Does not beat the naive baseline. Use with caution.'}
              </p>
            </div>
          )}
          <button onClick={() => train.mutate()} disabled={train.isPending} className="btn-primary text-xs w-full justify-center">
            {model?.version ? 'Retrain & forecast' : 'Train now'}
          </button>
        </div>

        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-primary">DBSCAN clustering</p>
          <p className="text-xs text-text-muted">Spatial clusters with haversine distance and automatic eps selection.</p>
          <button onClick={() => cluster.mutate()} disabled={cluster.isPending} className="btn-secondary text-xs w-full justify-center">
            Run clustering
          </button>
        </div>

        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-primary">Narrative embeddings</p>
          <p className="text-2xs text-text-muted font-mono">{card?.embedding_model}</p>
          <button onClick={() => embed.mutate()} disabled={embed.isPending} className="btn-secondary text-xs w-full justify-center">
            Embed backlog (1000)
          </button>
        </div>
      </div>

      {model && (
        <div className="card p-4 space-y-2">
          <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Intended use and limitations</p>
          <p className="text-xs text-text-primary">{model.intended_use}</p>
          <ul className="list-disc pl-5 space-y-1 text-xs text-text-secondary">
            {model.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </div>
      )}

      {evaluation?.feature_importance && (
        <div className="card p-4">
          <p className="text-xs font-medium text-text-secondary mb-3 uppercase tracking-wider">Feature sensitivity</p>
          <div className="space-y-2">
            {Object.entries(evaluation.feature_importance).map(([feature, weight]) => (
              <div key={feature} className="flex items-center gap-3">
                <span className="text-xs text-text-secondary w-40 font-mono">{feature}</span>
                <div className="flex-1 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                  <div className="h-full bg-accent-blue rounded-full" style={{ width: `${(weight * 100).toFixed(1)}%` }} />
                </div>
                <span className="text-2xs text-text-muted font-mono w-12 text-right">{(weight * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span>{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  )
}

function SystemTab() {
  const { data: health } = useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => fetch(`${import.meta.env.VITE_API_URL ?? ''}/health`).then((r) => r.json()),
    refetchInterval: 30_000,
  })

  const { data: ready } = useQuery({
    queryKey: ['system', 'ready'],
    queryFn: () => fetch(`${import.meta.env.VITE_API_URL ?? ''}/ready`).then((r) => r.json()),
    refetchInterval: 30_000,
  })

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
        <Activity size={15} /> System Health
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Application</p>
          {health ? (
            <div className="space-y-2 text-xs">
              <StatusRow label="Status" value={health.status} ok={health.status === 'ok'} />
              <StatusRow label="Version" value={health.version} />
            </div>
          ) : <div className="h-16 flex items-center justify-center text-text-muted text-xs">Loading…</div>}
        </div>

        <div className="card p-4 space-y-3">
          <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">Infrastructure</p>
          {ready ? (
            <div className="space-y-2 text-xs">
              <StatusRow label="Database" value={ready.checks?.database} ok={ready.checks?.database === 'ok'} />
              <StatusRow label="Redis Cache" value={ready.checks?.redis} ok={ready.checks?.redis === 'ok'} />
              <StatusRow label="Overall" value={ready.status} ok={ready.status === 'ready'} />
            </div>
          ) : <div className="h-16 flex items-center justify-center text-text-muted text-xs">Loading…</div>}
        </div>
      </div>
    </div>
  )
}

function StatusRow({ label, value, ok }: { label: string; value?: string; ok?: boolean }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-text-muted">{label}</span>
      <span className={cn('flex items-center gap-1.5 font-medium capitalize',
        ok === true ? 'text-severity-low' : ok === false ? 'text-severity-high' : 'text-text-primary'
      )}>
        {ok !== undefined && (
          <span className={cn('w-1.5 h-1.5 rounded-full', ok ? 'bg-status-online' : 'bg-status-offline')} />
        )}
        {value ?? '—'}
      </span>
    </div>
  )
}

function StatCard({ title, value, loading, className }: { title: string; value: number; loading?: boolean; className?: string }) {
  return (
    <div className={cn("card p-4 space-y-1", className)}>
      <p className="text-xs font-medium text-text-secondary uppercase tracking-wider">{title}</p>
      {loading ? (
        <div className="h-7 w-12 bg-bg-elevated animate-pulse rounded" />
      ) : (
        <p className="text-2xl font-bold text-text-primary">{value.toLocaleString()}</p>
      )}
    </div>
  )
}

function AccessRequestsTab() {
  const qc = useQueryClient()
  const [filter, setFilter] = useState('pending')
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'requests', filter],
    queryFn: () => adminApi.getAccessRequests({ account_status: filter }),
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'requests'] })
    qc.invalidateQueries({ queryKey: ['admin', 'stats'] })
  }

  const approve = useMutation({
    mutationFn: adminApi.approveAccessRequest,
    onSuccess: () => { toast.success('Request approved'); refresh() },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const reject = useMutation({
    mutationFn: (id: string) => adminApi.rejectAccessRequest(id),
    onSuccess: () => { toast.success('Request rejected'); refresh() },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <ClipboardList size={15} /> Access Requests
        </h3>
        <div className="flex items-center gap-2">
          <select 
            value={filter} 
            onChange={(e) => setFilter(e.target.value)}
            className="input text-xs py-1 px-2 w-auto"
          >
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select>
        </div>
      </div>

      {isLoading ? <PageLoader /> : (
        <div className="table-wrapper">
          <table className="table-base">
            <thead className="table-head">
              <tr>
                <th className="table-th">Req ID</th>
                <th className="table-th">Name</th>
                <th className="table-th">Email</th>
                <th className="table-th">Badge/Emp ID</th>
                <th className="table-th">Department</th>
                <th className="table-th">Designation</th>
                <th className="table-th">Requested Role</th>
                <th className="table-th">Requested At</th>
                {filter === 'pending' && <th className="table-th">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={9} className="table-td text-center text-text-muted py-8">
                    No {filter} requests found.
                  </td>
                </tr>
              )}
              {data?.items.map((user) => (
                <tr key={user.id} className="table-row">
                  <td className="table-td font-mono text-xs text-accent-blue">{user.request_id}</td>
                  <td className="table-td font-medium">{user.full_name}</td>
                  <td className="table-td text-text-secondary text-xs">{user.email}</td>
                  <td className="table-td font-mono text-xs text-text-muted">{user.badge_number ?? '—'}</td>
                  <td className="table-td text-xs text-text-secondary">{user.department ?? '—'}</td>
                  <td className="table-td text-xs text-text-secondary">{user.designation ?? '—'}</td>
                  <td className="table-td text-xs text-text-secondary">
                    {user.requested_role ? (
                      <Badge variant="gray">{roleLabel(user.requested_role)}</Badge>
                    ) : '—'}
                  </td>
                  <td className="table-td text-xs text-text-muted">{formatDate(user.created_at ?? '')}</td>
                  {filter === 'pending' && (
                    <td className="table-td">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => approve.mutate(user.id)}
                          disabled={approve.isPending || reject.isPending}
                          className="flex items-center gap-1 px-2 py-1 bg-severity-low-bg text-severity-low rounded-md hover:bg-severity-low/20 transition-colors text-2xs font-medium"
                        >
                          <Check size={12} /> Approve
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Reject request from ${user.full_name}?`)) reject.mutate(user.id)
                          }}
                          disabled={approve.isPending || reject.isPending}
                          className="flex items-center gap-1 px-2 py-1 bg-severity-high-bg text-severity-high rounded-md hover:bg-severity-high/20 transition-colors text-2xs font-medium"
                        >
                          <X size={12} /> Reject
                        </button>
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function AuditLogsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'audit'],
    queryFn: () => adminApi.getAuditLogs({ limit: 100 }),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <ShieldAlert size={15} /> Audit Logs
        </h3>
        <span className="text-xs text-text-muted">Last 100 events</span>
      </div>

      {isLoading ? <PageLoader /> : (
        <div className="table-wrapper">
          <table className="table-base">
            <thead className="table-head">
              <tr>
                <th className="table-th">Timestamp</th>
                <th className="table-th">Action</th>
                <th className="table-th">Resource</th>
                <th className="table-th">User ID</th>
                <th className="table-th">IP Address</th>
                <th className="table-th">Metadata</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((log) => (
                <tr key={log.id} className="table-row">
                  <td className="table-td text-xs text-text-muted whitespace-nowrap">{formatDate(log.created_at)}</td>
                  <td className="table-td text-xs font-mono font-medium text-text-primary">{log.action}</td>
                  <td className="table-td text-xs text-text-secondary">{log.resource_type} {log.resource_id ? <span className="font-mono text-2xs text-text-muted ml-1">({log.resource_id.substring(0, 8)})</span> : ''}</td>
                  <td className="table-td text-xs font-mono text-text-muted">{log.user_id ? log.user_id.substring(0, 8) + '...' : 'System'}</td>
                  <td className="table-td text-xs font-mono text-text-muted">{log.ip_address ?? '—'}</td>
                  <td className="table-td text-2xs font-mono text-text-muted max-w-[200px] truncate" title={JSON.stringify(log.extra_metadata)}>
                    {log.extra_metadata ? JSON.stringify(log.extra_metadata) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function ProfileEditsTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'profile_requests'],
    queryFn: () => api.get<any>('/users/profile-requests?status=pending').then(r => r.data),
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['admin', 'profile_requests'] })

  const approve = useMutation({
    mutationFn: (id: string) => api.patch(`/users/profile-requests/${id}/approve`),
    onSuccess: () => { toast.success('Profile edit approved'); refresh() },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const reject = useMutation({
    mutationFn: (id: string) => api.patch(`/users/profile-requests/${id}/reject`, { reason: 'Rejected by admin' }),
    onSuccess: () => { toast.success('Profile edit rejected'); refresh() },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
          <UserPlus size={15} /> Pending Profile Edits
        </h3>
        <span className="text-xs text-text-muted">{data?.total ?? 0} pending</span>
      </div>

      {isLoading ? <PageLoader /> : (
        <div className="table-wrapper">
          <table className="table-base">
            <thead className="table-head">
              <tr>
                <th className="table-th">User ID</th>
                <th className="table-th">Requested Changes</th>
                <th className="table-th">Proof</th>
                <th className="table-th">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={4} className="table-td text-center text-text-muted py-8">
                    No pending profile edits.
                  </td>
                </tr>
              )}
              {data?.items.map((req: any) => (
                <tr key={req.id} className="table-row">
                  <td className="table-td font-mono text-xs text-text-muted">{req.user_id.substring(0,8)}</td>
                  <td className="table-td text-xs text-text-secondary font-mono">{JSON.stringify(req.requested_changes)}</td>
                  <td className="table-td">
                    <button
                      type="button"
                      onClick={() => adminApi.openProof(req.proof_url).catch((err) => toast.error(getErrorMessage(err)))}
                      className="text-accent-blue text-xs hover:underline"
                    >
                      View Proof
                    </button>
                  </td>
                  <td className="table-td">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => approve.mutate(req.id)}
                        disabled={approve.isPending || reject.isPending}
                        className="flex items-center gap-1 px-2 py-1 bg-severity-low-bg text-severity-low rounded-md hover:bg-severity-low/20 transition-colors text-2xs font-medium"
                      >
                        <Check size={12} /> Approve
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Reject profile edit?`)) reject.mutate(req.id)
                        }}
                        disabled={approve.isPending || reject.isPending}
                        className="flex items-center gap-1 px-2 py-1 bg-severity-high-bg text-severity-high rounded-md hover:bg-severity-high/20 transition-colors text-2xs font-medium"
                      >
                        <X size={12} /> Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default AdminPage

