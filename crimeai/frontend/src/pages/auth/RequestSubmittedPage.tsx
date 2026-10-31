import { useLocation, Link, Navigate } from 'react-router-dom'
import { CheckCircle2, Copy, Clock, ShieldCheck, ArrowLeft } from 'lucide-react'
import toast from 'react-hot-toast'
import AuthBackground from './AuthBackground'

export default function RequestSubmittedPage() {
  const location = useLocation()
  const requestId = location.state?.requestId

  if (!requestId) {
    return <Navigate to="/login" replace />
  }

  const copyId = () => {
    navigator.clipboard.writeText(requestId)
    toast.success('Request ID copied to clipboard')
  }

  const now = new Date()
  const formattedDate = now.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
  })
  const formattedTime = now.toLocaleTimeString('en-IN', {
    hour: '2-digit', minute: '2-digit', hour12: false,
  }) + ' IST'

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-8 relative overflow-hidden font-sans text-slate-200">
      <AuthBackground />

      <div className="relative w-full max-w-[420px] z-10">
        <div className="auth-card p-8 space-y-6 opacity-0 animate-fade-up">

          {/* Success icon */}
          <div className="flex justify-center">
            <div className="relative">
              <div className="absolute inset-0 rounded-full bg-emerald-400/20 blur-xl" />
              <div className="relative w-16 h-16 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                <CheckCircle2 className="w-8 h-8 text-emerald-400" />
              </div>
            </div>
          </div>

          {/* Title */}
          <div className="text-center">
            <h2 className="text-lg font-bold text-slate-100 uppercase tracking-wider mb-1.5">
              Request Under Review
            </h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              Your access request has been securely submitted<br />
              for administrator review.
            </p>
          </div>

          {/* Request ID */}
          <div className="rounded-xl p-4 border border-slate-700/40 bg-slate-900/40">
            <p className="text-[10px] text-slate-500 mb-1.5 uppercase tracking-[0.15em] font-semibold text-center">
              Request ID
            </p>
            <div className="flex items-center justify-center gap-2">
              <span className="font-mono text-lg text-blue-400 font-bold tracking-wide">
                {requestId}
              </span>
              <button
                onClick={copyId}
                className="text-slate-500 hover:text-slate-300 transition-colors p-1 rounded hover:bg-slate-800/50"
                title="Copy Request ID"
                aria-label="Copy Request ID"
              >
                <Copy size={15} />
              </button>
            </div>
          </div>

          {/* Status details */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg p-3 border border-slate-700/30 bg-slate-900/30 text-center">
              <p className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold mb-1">
                Current Status
              </p>
              <div className="flex items-center justify-center gap-1.5">
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-60" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-amber-500" />
                </span>
                <span className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
                  Pending Review
                </span>
              </div>
            </div>
            <div className="rounded-lg p-3 border border-slate-700/30 bg-slate-900/30 text-center">
              <p className="text-[9px] text-slate-500 uppercase tracking-wider font-semibold mb-1">
                Submitted
              </p>
              <p className="text-xs font-medium text-slate-300">
                {formattedDate}
              </p>
              <p className="text-[10px] text-slate-500">{formattedTime}</p>
            </div>
          </div>

          {/* Status timeline */}
          <div className="rounded-xl p-4 border border-slate-700/30 bg-slate-900/20">
            <div className="space-y-0">
              {/* Step 1: Submitted ✓ */}
              <div className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <div className="w-5 h-5 rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center">
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                  </div>
                  <div className="w-px h-5 bg-slate-700/50" />
                </div>
                <p className="text-xs text-slate-300 font-medium pt-0.5">Request Submitted</p>
              </div>

              {/* Step 2: Admin Review (active) */}
              <div className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <div className="w-5 h-5 rounded-full bg-amber-500/15 border border-amber-500/30 flex items-center justify-center">
                    <Clock className="w-3 h-3 text-amber-400" />
                  </div>
                  <div className="w-px h-5 bg-slate-800/40" />
                </div>
                <p className="text-xs text-amber-400 font-medium pt-0.5">Administrator Review</p>
              </div>

              {/* Step 3: Approved (pending) */}
              <div className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <div className="w-5 h-5 rounded-full border border-slate-700/50 flex items-center justify-center">
                    <ShieldCheck className="w-3 h-3 text-slate-600" />
                  </div>
                  <div className="w-px h-5 bg-slate-800/30" />
                </div>
                <p className="text-xs text-slate-600 font-medium pt-0.5">Approved</p>
              </div>

              {/* Step 4: Access Enabled (pending) */}
              <div className="flex items-start gap-3">
                <div className="flex flex-col items-center">
                  <div className="w-5 h-5 rounded-full border border-slate-800/40 flex items-center justify-center" />
                </div>
                <p className="text-xs text-slate-600 font-medium pt-0.5">Access Enabled</p>
              </div>
            </div>
          </div>

          {/* Info text */}
          <p className="text-[11px] text-slate-500 text-center leading-relaxed">
            Administrator review is required before your account can access CrimeAI.
            You will be able to log in once your request is approved.
          </p>

          {/* CTA */}
          <div className="relative pt-4">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-slate-700/60 to-transparent" />
            <Link
              to="/login"
              className="auth-btn"
            >
              <ArrowLeft size={16} />
              Return to Login
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
