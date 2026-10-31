import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink, Link2, Loader2, ShieldCheck, ShieldAlert, Stamp } from 'lucide-react'
import toast from 'react-hot-toast'
import { getErrorMessage } from '@/services'
import { investigationApi } from '@/services/investigation'
import { cn, formatDate } from '@/utils'
import type { Seal, SealVerification } from '@/types/investigation'

const SEAL_STATUS: Record<Seal['status'], string> = {
  anchored: 'bg-severity-low/15 text-severity-low',
  submitted: 'bg-severity-medium/15 text-severity-medium',
  failed: 'bg-severity-high/15 text-severity-high',
}

const ITEM_STATE: Record<SealVerification['items'][number]['state'], string> = {
  unchanged: 'text-severity-low',
  changed: 'text-severity-high',
  added: 'text-severity-medium',
  removed: 'text-severity-high',
}

/**
 * Chain of custody: sealing hashes every document and officer review on the case and anchors their Merkle root on
 * Solana; verifying recomputes the hashes and reads the root back from the chain. Only hashes leave the deployment.
 */
export default function CustodyPanel({ crimeId, canAct }: { crimeId: string; canAct: boolean }) {
  const qc = useQueryClient()
  const seals = useQuery({ queryKey: ['seals', crimeId], queryFn: () => investigationApi.seals(crimeId) })
  const seal = useMutation({
    mutationFn: () => investigationApi.seal(crimeId),
    onSuccess: (s) => {
      if (s.status === 'failed') toast.error(`Seal not anchored: ${s.error ?? 'unknown error'}`)
      else toast.success(s.status === 'anchored' ? 'Case file sealed on Solana' : 'Seal sent; confirming on Solana')
      qc.invalidateQueries({ queryKey: ['seals', crimeId] })
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  })

  const data = seals.data
  return (
    <div className="rounded border border-accent-cyan/40 bg-accent-cyan/[0.04] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-xs font-semibold text-text-primary">
            <Link2 size={13} className="text-accent-cyan" /> Chain of custody · Solana {data?.cluster ?? ''}
          </h3>
          <p className="mt-0.5 text-2xs text-text-muted">
            Every document and officer review is hashed; the Merkle root goes on chain in one memo transaction. Only
            hashes leave the deployment.
            {data?.address && <> Sealing key <span className="font-mono">{data.address.slice(0, 6)}…{data.address.slice(-4)}</span>.</>}
          </p>
        </div>
        {canAct && data?.enabled && (
          <button type="button" className="btn-secondary py-1 text-2xs" disabled={seal.isPending} onClick={() => seal.mutate()}>
            {seal.isPending ? <Loader2 size={11} className="animate-spin" /> : <Stamp size={11} className="text-accent-cyan" />}
            Seal case file on Solana
          </button>
        )}
      </div>
      {seals.isLoading && <p className="mt-2 text-2xs text-text-muted"><Loader2 size={11} className="mr-1 inline animate-spin" />Loading seals…</p>}
      {data && !data.enabled && (
        <p className="mt-2 text-2xs text-text-muted">Sealing is off on this server: run <span className="font-mono">scripts/solana_setup.py</span>.</p>
      )}
      {data && data.seals.length === 0 && data.enabled && <p className="mt-2 text-2xs text-text-muted">Not sealed yet.</p>}
      <ul className="mt-2 space-y-1.5">
        {data?.seals.map((s) => <SealRow key={s.id} crimeId={crimeId} seal={s} />)}
      </ul>
    </div>
  )
}

function SealRow({ crimeId, seal }: { crimeId: string; seal: Seal }) {
  const [open, setOpen] = useState(false)
  const verify = useQuery({
    queryKey: ['seal-verify', crimeId, seal.id],
    queryFn: () => investigationApi.verifySeal(crimeId, seal.id),
    enabled: open,
  })
  const v = verify.data
  const changed = v?.items.filter((i) => i.state !== 'unchanged') ?? []
  return (
    <li className="rounded border border-border-subtle bg-bg-primary px-2.5 py-2 text-2xs">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn('rounded px-1.5 py-0.5 font-semibold', SEAL_STATUS[seal.status])}>{seal.status}</span>
        <span className="text-text-secondary">{seal.created_at ? formatDate(seal.created_at, 'dd MMM yyyy, HH:mm') : ''}</span>
        <span className="text-text-muted">{seal.leaves} item{seal.leaves === 1 ? '' : 's'} · root</span>
        <span className="font-mono text-text-primary" title={seal.merkle_root}>{seal.merkle_root.slice(0, 16)}…</span>
        {seal.explorer_url && (
          <a href={seal.explorer_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent-cyan hover:underline">
            Explorer <ExternalLink size={10} />
          </a>
        )}
        {seal.signature && (
          <button type="button" className="ml-auto text-accent-blue hover:underline" onClick={() => setOpen((x) => !x)}>
            {open ? 'Hide check' : 'Verify'}
          </button>
        )}
      </div>
      {seal.error && <p className="mt-1 text-severity-high">{seal.error}</p>}
      {open && verify.isLoading && <p className="mt-1 text-text-muted"><Loader2 size={11} className="mr-1 inline animate-spin" />Recomputing hashes and reading the chain…</p>}
      {open && verify.error && <p className="mt-1 text-severity-high">{getErrorMessage(verify.error)}</p>}
      {open && v && (
        <div className="mt-1.5 space-y-1">
          <p className={cn('flex items-center gap-1 font-semibold', v.intact ? 'text-severity-low' : 'text-severity-high')}>
            {v.intact ? <ShieldCheck size={12} /> : <ShieldAlert size={12} />}
            {v.intact ? 'Intact: every item matches the seal, and the root is on chain.'
              : changed.length ? `${changed.length} item${changed.length === 1 ? '' : 's'} differ from the seal.`
                : v.chain.matches ? 'Items match, but the stored seal record does not.' : 'The root could not be confirmed on chain.'}
          </p>
          <p className="text-text-muted">
            On chain: {v.chain.checked ? (v.chain.matches ? `root found in slot ${v.chain.slot ?? '?'}` : v.chain.found ? 'memo does not carry this root' : 'transaction not found yet')
              : v.chain.error ?? 'not checked'}
          </p>
          <ul className="space-y-0.5">
            {v.items.map((i) => (
              <li key={`${i.kind}-${i.id}`} className="flex gap-2">
                <span className={cn('w-16 shrink-0 font-semibold', ITEM_STATE[i.state])}>{i.state}</span>
                <span className="text-text-secondary">{i.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  )
}
