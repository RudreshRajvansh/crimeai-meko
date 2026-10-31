import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Shield, Eye, EyeOff, ArrowRight, Mail, Lock } from 'lucide-react'
import { useState } from 'react'
import { useLogin } from '@/hooks/useAuth'
import { cn } from '@/utils'
import AuthBackground from './AuthBackground'

const loginSchema = z.object({
  email: z.string().email('Valid email required'),
  password: z.string().min(8, 'Password must be at least 8 characters'),
})
type LoginForm = z.infer<typeof loginSchema>


const REMEMBER_KEY = 'crimeai-login-email'

function rememberedEmail(): string {
  try {
    return localStorage.getItem(REMEMBER_KEY) ?? ''
  } catch {
    return ''
  }
}

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false)
  const [showReset, setShowReset] = useState(false)
  const [remember, setRemember] = useState(() => rememberedEmail() !== '')
  const login = useLogin()

  const { register, handleSubmit, formState: { errors } } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: rememberedEmail() },
  })

  const onSubmit = (data: LoginForm) => {
    // Only the email is remembered, on this browser; sessions already persist through the refresh cookie.
    try {
      if (remember) localStorage.setItem(REMEMBER_KEY, data.email)
      else localStorage.removeItem(REMEMBER_KEY)
    } catch {
      // Storage blocked: nothing to remember.
    }
    login.mutate(data)
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-8 relative overflow-hidden font-sans text-slate-200">
      <AuthBackground />

      <div className="relative w-full max-w-[400px] z-10">

        {/* ── Branding ── */}
        <div className="text-center mb-8 opacity-0 animate-fade-up">
          {/* Logo with subtle glow */}
          <div className="relative inline-flex items-center justify-center w-[72px] h-[72px] mb-5">
            <div className="absolute inset-0 rounded-full bg-accent-blue/15 blur-xl" />
            <img
              src="/logo.png"
              alt="CrimeAI Logo"
              className="w-full h-full object-contain relative z-10 drop-shadow-[0_0_12px_rgba(31,111,235,0.4)]"
            />
          </div>

          <h1 className="text-3xl font-bold tracking-tight mb-1.5">
            <span className="text-slate-100">Crime</span>
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-400">AI</span>
          </h1>
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-[0.2em]">
            Intelligence &amp; Predictive Policing
          </p>

        </div>

        {/* ── Login Card ── */}
        <div className="auth-card p-7 space-y-6 opacity-0 animate-fade-up-d1">

          {/* Card header */}
          <div className="flex flex-col items-center text-center">
            <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-accent-blue/10 border border-accent-blue/20 mb-3">
              <Shield className="w-5 h-5 text-blue-400" />
            </div>
            <h2 className="text-sm font-bold text-slate-200 uppercase tracking-[0.15em]">
              Secure Access
            </h2>
            <p className="text-[11px] text-slate-500 mt-1">
              Authorized personnel only
            </p>
            <div className="flex items-center gap-1.5 mt-2.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
              </span>
              <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">
                Authentication Gateway
              </span>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">

            {/* Email */}
            <div>
              <label htmlFor="login-email" className="block text-[11px] font-medium text-slate-400 mb-1.5 uppercase tracking-wider">
                Official Email
              </label>
              <div className="relative group">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 group-focus-within:text-blue-400 transition-colors" />
                <input
                  {...register('email')}
                  id="login-email"
                  type="email"
                  className={cn('auth-input pl-9', errors.email && 'has-error')}
                  placeholder="officer@police.gov.in"
                  autoComplete="email"
                />
              </div>
              {errors.email && (
                <p className="text-[11px] text-red-400 mt-1.5 ml-0.5">{errors.email.message}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="login-password" className="block text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                  Password
                </label>
                <button
                  type="button"
                  onClick={() => setShowReset((v) => !v)}
                  aria-expanded={showReset}
                  className="text-[10px] text-blue-400 hover:text-blue-300 transition-colors"
                >
                  Forgot password?
                </button>
              </div>
              <div className="relative group">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 group-focus-within:text-blue-400 transition-colors" />
                <input
                  {...register('password')}
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  className={cn('auth-input pl-9 pr-10', errors.password && 'has-error')}
                  placeholder="••••••••••••"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((p) => !p)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300 transition-colors focus:outline-none"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              {errors.password && (
                <p className="text-[11px] text-red-400 mt-1.5 ml-0.5">{errors.password.message}</p>
              )}
              {showReset && (
                <p className="mt-2 rounded-lg border border-blue-500/20 bg-blue-500/10 px-3 py-2 text-[11px] leading-relaxed text-slate-300">
                  Passwords are reset by your unit administrator, not by email: contact them with your badge
                  number and they will set a temporary password from Admin &rarr; Users. Every reset is audited.
                </p>
              )}
            </div>

            {/* Remember device */}
            <div className="flex items-center gap-2.5 pt-0.5">
              <input
                type="checkbox"
                id="remember"
                className="auth-checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              <label htmlFor="remember" className="text-xs text-slate-400 cursor-pointer select-none hover:text-slate-300 transition-colors">
                Remember my email on this browser
              </label>
            </div>

            {/* Sign In button */}
            <button
              type="submit"
              disabled={login.isPending}
              className="auth-btn"
            >
              {login.isPending ? (
                <>
                  <span className="w-4 h-4 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                  Signing In…
                </>
              ) : (
                <>
                  Sign In
                  <ArrowRight size={16} className="ml-0.5" />
                </>
              )}
            </button>
          </form>

          {/* Divider + Request Access */}
          <div className="relative pt-4">
            <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-slate-700/60 to-transparent" />
            <div className="text-center">
              <p className="text-xs text-slate-500 mb-1.5">Don&apos;t have access?</p>
              <a
                href="/request-access"
                className="group inline-flex items-center gap-1 text-sm font-medium text-blue-400 hover:text-blue-300 transition-colors"
              >
                Request Platform Access
                <ArrowRight
                  size={14}
                  className="transform group-hover:translate-x-1 transition-transform duration-300"
                />
              </a>
            </div>
          </div>

          {/* System status */}
          <div className="flex justify-center items-center gap-1.5">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.7)]" />
            </span>
            <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest">
              System Operational
            </span>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center opacity-0 animate-fade-up-d2">
          <p className="text-[10px] text-slate-600 tracking-widest uppercase">
            Authorised personnel only
          </p>
          <p className="text-[10px] text-slate-600 tracking-widest uppercase mt-0.5">
            Access activity is logged
          </p>
        </div>
      </div>
    </div>
  )
}
