import { cn } from '@/utils'

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
  label?: string
}

const sizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-10 h-10' }

export default function LoadingSpinner({ size = 'md', className, label }: LoadingSpinnerProps) {
  return (
    <div className={cn('flex flex-col items-center gap-2', className)}>
      <div className={cn(
        'rounded-full border-2 border-border-default border-t-accent-blue animate-spin',
        sizes[size]
      )} />
      {label && <p className="text-xs text-text-muted">{label}</p>}
    </div>
  )
}

export function PageLoader({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="flex h-full items-center justify-center">
      <LoadingSpinner size="lg" label={label} />
    </div>
  )
}
