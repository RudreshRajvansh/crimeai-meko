import { cn } from '@/utils'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'blue' | 'green' | 'amber' | 'red' | 'purple' | 'gray'
  size?: 'sm' | 'md'
  className?: string
}

const variants = {
  default: 'bg-bg-elevated text-text-secondary border-border-default',
  blue:    'bg-accent-blue/10 text-accent-blue border-accent-blue/20',
  green:   'bg-severity-low-bg text-severity-low border-severity-low/20',
  amber:   'bg-severity-medium-bg text-severity-medium border-severity-medium/20',
  red:     'bg-severity-high-bg text-severity-high border-severity-high/20',
  purple:  'bg-accent-purple/10 text-accent-purple border-accent-purple/20',
  gray:    'bg-bg-hover text-text-muted border-border-subtle',
}

const sizes = {
  sm: 'text-2xs px-1.5 py-0.5',
  md: 'text-xs px-2 py-0.5',
}

export default function Badge({ children, variant = 'default', size = 'md', className }: BadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center rounded font-medium border',
      variants[variant], sizes[size], className
    )}>
      {children}
    </span>
  )
}
