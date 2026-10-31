import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn, formatNumber } from '@/utils'

interface StatCardProps {
  label: string
  value: number | string
  change?: number   // percentage change
  icon?: React.ReactNode
  color?: 'blue' | 'green' | 'amber' | 'red' | 'purple'
  loading?: boolean
  suffix?: string
}

const colorMap = {
  blue:   'text-accent-blue bg-accent-blue/10 border-accent-blue/20',
  green:  'text-severity-low bg-severity-low-bg border-severity-low/20',
  amber:  'text-severity-medium bg-severity-medium-bg border-severity-medium/20',
  red:    'text-severity-high bg-severity-high-bg border-severity-high/20',
  purple: 'text-accent-purple bg-accent-purple/10 border-accent-purple/20',
}

export default function StatCard({ label, value, change, icon, color = 'blue', loading, suffix }: StatCardProps) {
  const displayValue = typeof value === 'number' ? formatNumber(value) : value

  return (
    <div className={cn('card p-4 border', colorMap[color].split(' ').slice(2).join(' '))}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="stat-label">{label}</p>
          {loading ? (
            <div className="h-7 w-20 bg-bg-elevated rounded animate-pulse mt-1" />
          ) : (
            <p className="stat-value mt-1">
              {displayValue}{suffix && <span className="text-sm font-normal text-text-secondary ml-1">{suffix}</span>}
            </p>
          )}
          {change !== undefined && !loading && (
            <div className={cn('flex items-center gap-1 mt-1.5', 'stat-change',
              change > 0 ? 'text-severity-high' : change < 0 ? 'text-severity-low' : 'text-text-muted'
            )}>
              {change > 0 ? <TrendingUp size={12} /> : change < 0 ? <TrendingDown size={12} /> : <Minus size={12} />}
              <span>{Math.abs(change).toFixed(1)}% vs last period</span>
            </div>
          )}
        </div>
        {icon && (
          <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0', colorMap[color].split(' ').slice(0, 2).join(' '))}>
            {icon}
          </div>
        )}
      </div>
    </div>
  )
}
