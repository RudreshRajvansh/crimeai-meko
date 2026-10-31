import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Eye, EyeOff, ArrowRight, Shield, UserCircle, Building2, Lock, ChevronLeft } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { authApi, getErrorMessage } from '@/services'
import { cn } from '@/utils'
import AuthBackground from './AuthBackground'

const requestSchema = z.object({
  full_name: z.string().min(2, 'Name is required'),
  email: z.string().email('Valid official email required'),
  badge_number: z.string().min(1, 'Badge/Employee ID is required'),
  department: z.string().min(1, 'Department is required'),
  designation: z.string().min(1, 'Designation is required'),
  password: z.string().min(10, 'Password must be at least 10 characters')
    .regex(/[A-Z]/, 'Must contain an uppercase letter')
    .regex(/[a-z]/, 'Must contain a lowercase letter')
    .regex(/[0-9]/, 'Must contain a number'),
  confirm_password: z.string(),
}).refine((data) => data.password === data.confirm_password, {
  message: "Passwords don't match",
  path: ['confirm_password'],
})

type RequestForm = z.infer<typeof requestSchema>

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

const REQUESTED_ROLES = [
  {
    value: 'readonly',
    label: 'Read Only',
    description: 'Executive intelligence, regional risk summaries and operational briefings.',
  },
  {
    value: 'analyst',
    label: 'Crime Analyst',
    description: 'Crime trends, spatial analysis, clusters and pattern detection.',
  },
  {
    value: 'police',
    label: 'Police Officer',
    description: 'FIR submission, case management and custody tracking.',
  },
]

const STEPS = [
  { num: '01', label: 'Identity',     icon: UserCircle },
  { num: '02', label: 'Organization', icon: Building2 },
  { num: '03', label: 'Security',     icon: Lock },
]

export default function RequestAccessPage() {
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [selectedRole, setSelectedRole] = useState('')
  const [accessPurpose, setAccessPurpose] = useState('')
  const [activeStep, setActiveStep] = useState(0)
  const navigate = useNavigate()

  const { register, handleSubmit, formState: { errors } } = useForm<RequestForm>({
    resolver: zodResolver(requestSchema),
  })

  const onSubmit = async (data: RequestForm) => {
    setIsSubmitting(true)
    try {
      const payload = { ...data, requested_role: selectedRole || undefined }
      const response = await authApi.register(payload)
      navigate('/request-submitted', { state: { requestId: response.request_id } })
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center py-10 px-4 relative overflow-hidden font-sans text-slate-200">
      <AuthBackground />

      <div className="relative w-full max-w-lg z-10">

        {/* ── Branding ── */}
        <div className="text-center mb-6 opacity-0 animate-fade-up">
          <div className="relative inline-flex items-center justify-center w-14 h-14 mb-3">
            <div className="absolute inset-0 rounded-full bg-accent-blue/15 blur-xl" />
            <img
              src="/logo.png"
              alt="CrimeAI Logo"
              className="w-full h-full object-contain relative z-10 drop-shadow-[0_0_10px_rgba(31,111,235,0.3)]"
            />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">
            <span className="text-slate-100">Crime</span>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-400">AI</span>
          </h1>
        </div>

        {/* ── Card ── */}
        <div className="auth-card p-7 space-y-6 opacity-0 animate-fade-up-d1">

          {/* Card header */}
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Shield className="w-4 h-4 text-blue-400" />
              <h2 className="text-sm font-bold text-slate-200 uppercase tracking-[0.15em]">
                Request Platform Access
              </h2>
            </div>
            <p className="text-[11px] text-slate-500 ml-6">
              Submit your credentials for administrator authorization.
            </p>
            <div className="flex items-center gap-1.5 mt-2 ml-6">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-60" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-blue-500" />
              </span>
              <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">
                Access Request
              </span>
            </div>
          </div>

          {/* Step indicator */}
          <div className="flex items-center gap-0" role="list" aria-label="Form sections">
            {STEPS.map((step, i) => (
              <div key={step.num} className="flex items-center flex-1" role="listitem">
                <div className="flex items-center gap-1.5">
                  <span className={cn(
                    'text-[10px] font-bold font-mono rounded-full w-5 h-5 flex items-center justify-center transition-colors',
                    i === activeStep
                      ? 'bg-blue-500/20 text-blue-400 ring-1 ring-blue-500/30'
                      : 'bg-slate-800/50 text-slate-600'
                  )}>
                    {step.num}
                  </span>
                  <span className={cn(
                    'text-[10px] font-semibold uppercase tracking-wider hidden sm:inline',
                    i === activeStep ? 'text-slate-300' : 'text-slate-600'
                  )}>
                    {step.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div className="flex-1 h-px bg-gradient-to-r from-slate-700/50 to-slate-800/20 mx-2" />
                )}
              </div>
            ))}
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">

            {/* ── SECTION 01: IDENTITY ── */}
            <div className="space-y-3" onFocus={() => setActiveStep(0)}>
              <div className="flex items-center gap-2 pb-1">
                <UserCircle className="w-3.5 h-3.5 text-blue-400/70" />
                <span className="text-[10px] font-bold text-blue-400/70 uppercase tracking-[0.15em]">
                  Identity
                </span>
                <div className="flex-1 h-px bg-slate-800/50" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="ra-name" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                    Full Name
                  </label>
                  <input
                    {...register('full_name')}
                    id="ra-name"
                    className={cn('auth-input', errors.full_name && 'has-error')}
                    placeholder="Officer Name"
                  />
                  {errors.full_name && <p className="text-[11px] text-red-400 mt-1">{errors.full_name.message}</p>}
                </div>

                <div>
                  <label htmlFor="ra-email" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                    Official Email
                  </label>
                  <input
                    {...register('email')}
                    id="ra-email"
                    type="email"
                    className={cn('auth-input', errors.email && 'has-error')}
                    placeholder="name@police.gov.in"
                  />
                  {errors.email && <p className="text-[11px] text-red-400 mt-1">{errors.email.message}</p>}
                </div>
              </div>

              <div>
                <label htmlFor="ra-badge" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                  Badge / Employee ID
                </label>
                <input
                  {...register('badge_number')}
                  id="ra-badge"
                  className={cn('auth-input font-mono', errors.badge_number && 'has-error')}
                  placeholder="ID-12345"
                />
                {errors.badge_number && <p className="text-[11px] text-red-400 mt-1">{errors.badge_number.message}</p>}
              </div>
            </div>

            {/* ── SECTION 02: ORGANIZATION ── */}
            <div className="space-y-3" onFocus={() => setActiveStep(1)}>
              <div className="flex items-center gap-2 pb-1">
                <Building2 className="w-3.5 h-3.5 text-blue-400/70" />
                <span className="text-[10px] font-bold text-blue-400/70 uppercase tracking-[0.15em]">
                  Organization
                </span>
                <div className="flex-1 h-px bg-slate-800/50" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="ra-designation" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                    Designation
                  </label>
                  <select
                    {...register('designation')}
                    id="ra-designation"
                    className={cn('auth-select', errors.designation && 'has-error')}
                  >
                    <option value="">Select Designation...</option>
                    {DESIGNATIONS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                  {errors.designation && <p className="text-[11px] text-red-400 mt-1">{errors.designation.message}</p>}
                </div>

                <div>
                  <label htmlFor="ra-department" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                    Department
                  </label>
                  <select
                    {...register('department')}
                    id="ra-department"
                    className={cn('auth-select', errors.department && 'has-error')}
                  >
                    <option value="">Select Department...</option>
                    {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                  {errors.department && <p className="text-[11px] text-red-400 mt-1">{errors.department.message}</p>}
                </div>
              </div>
            </div>

            {/* ── REQUESTED ROLE ── */}
            <div className="space-y-3" onFocus={() => setActiveStep(1)}>
              <div className="flex items-center gap-2 pb-1">
                <Shield className="w-3.5 h-3.5 text-blue-400/70" />
                <span className="text-[10px] font-bold text-blue-400/70 uppercase tracking-[0.15em]">
                  Requested Access Role
                </span>
                <div className="flex-1 h-px bg-slate-800/50" />
              </div>
              <div className="grid grid-cols-1 gap-2">
                {REQUESTED_ROLES.map((role) => (
                  <button
                    key={role.value}
                    type="button"
                    onClick={() => {
                      setSelectedRole(role.value)
                      setActiveStep(1)
                    }}
                    className={cn(
                      'text-left rounded-lg p-3 border transition-all duration-200',
                      selectedRole === role.value
                        ? 'bg-blue-500/10 border-blue-500/30 shadow-[0_0_12px_rgba(31,111,235,0.1)]'
                        : 'bg-slate-900/30 border-slate-700/30 hover:border-slate-600/50 hover:bg-slate-900/50'
                    )}
                  >
                    <div className="flex items-start gap-2.5">
                      <div className={cn(
                        'mt-0.5 w-3.5 h-3.5 rounded-full border-2 flex-shrink-0 flex items-center justify-center transition-colors',
                        selectedRole === role.value ? 'border-blue-400' : 'border-slate-600'
                      )}>
                        {selectedRole === role.value && (
                          <div className="w-1.5 h-1.5 rounded-full bg-blue-400" />
                        )}
                      </div>
                      <div>
                        <p className={cn(
                          'text-xs font-semibold transition-colors',
                          selectedRole === role.value ? 'text-slate-200' : 'text-slate-400'
                        )}>
                          {role.label}
                        </p>
                        <p className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">
                          {role.description}
                        </p>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
              <p className="text-[9px] text-slate-600 ml-0.5">
                Final role is subject to administrator approval.
              </p>
            </div>

            {/* ── PURPOSE OF ACCESS ── */}
            <div onFocus={() => setActiveStep(1)}>
              <label htmlFor="ra-purpose" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                Purpose of Access <span className="text-slate-600 normal-case tracking-normal">(optional)</span>
              </label>
              <textarea
                id="ra-purpose"
                value={accessPurpose}
                onChange={(e) => setAccessPurpose(e.target.value)}
                rows={2}
                className="auth-input resize-none"
                placeholder="Briefly describe why you require access to the CrimeAI platform."
              />
            </div>

            {/* ── SECTION 03: SECURITY ── */}
            <div className="space-y-3" onFocus={() => setActiveStep(2)}>
              <div className="flex items-center gap-2 pb-1">
                <Lock className="w-3.5 h-3.5 text-blue-400/70" />
                <span className="text-[10px] font-bold text-blue-400/70 uppercase tracking-[0.15em]">
                  Security
                </span>
                <div className="flex-1 h-px bg-slate-800/50" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="ra-password" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                    Password
                  </label>
                  <div className="relative group">
                    <input
                      {...register('password')}
                      id="ra-password"
                      type={showPassword ? 'text' : 'password'}
                      className={cn('auth-input pr-9', errors.password && 'has-error')}
                      placeholder="••••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((p) => !p)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300 transition-colors focus:outline-none"
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                    </button>
                  </div>
                  {errors.password && <p className="text-[11px] text-red-400 mt-1">{errors.password.message}</p>}
                </div>

                <div>
                  <label htmlFor="ra-confirm" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                    Confirm Password
                  </label>
                  <input
                    {...register('confirm_password')}
                    id="ra-confirm"
                    type={showPassword ? 'text' : 'password'}
                    className={cn('auth-input', errors.confirm_password && 'has-error')}
                    placeholder="••••••••••"
                  />
                  {errors.confirm_password && <p className="text-[11px] text-red-400 mt-1">{errors.confirm_password.message}</p>}
                </div>
              </div>

              <p className="text-[9px] text-slate-600 ml-0.5">
                Min 10 characters • uppercase • lowercase • number
              </p>
            </div>

            {/* ── Submit ── */}
            <div className="pt-1">
              <button
                type="submit"
                disabled={isSubmitting}
                className="auth-btn"
              >
                {isSubmitting ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                    Submitting Request…
                  </>
                ) : (
                  <>
                    Request Authorization
                    <ArrowRight size={16} className="ml-0.5" />
                  </>
                )}
              </button>
            </div>
          </form>

          {/* ── Approval workflow visual ── */}
          <div className="flex items-center justify-center gap-1.5 text-[9px] font-mono text-slate-600 uppercase tracking-wider">
            <span>You</span>
            <span className="text-slate-700">→</span>
            <span>Request</span>
            <span className="text-slate-700">→</span>
            <span className="text-blue-500/70">Admin Review</span>
            <span className="text-slate-700">→</span>
            <span>Access</span>
          </div>

          {/* ── Back to Login ── */}
          <div className="relative pt-4">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-slate-700/60 to-transparent" />
            <div className="text-center">
              <p className="text-xs text-slate-500 mb-1.5">Already have an account?</p>
              <a
                href="/login"
                className="group inline-flex items-center gap-1 text-sm font-medium text-blue-400 hover:text-blue-300 transition-colors"
              >
                <ChevronLeft
                  size={14}
                  className="transform group-hover:-translate-x-1 transition-transform duration-300"
                />
                Back to Login
              </a>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 text-center opacity-0 animate-fade-up-d2">
          <p className="text-[10px] text-slate-600 tracking-widest uppercase">
            Administrator review required before access is granted
          </p>
        </div>
      </div>
    </div>
  )
}
