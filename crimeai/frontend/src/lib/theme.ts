import { useMemo } from 'react'
import { useUIStore } from '@/store/ui'

const TOKENS = [
  'bg-primary', 'bg-secondary', 'bg-tertiary', 'bg-elevated', 'border-subtle', 'border-default', 'border-strong',
  'text-primary', 'text-secondary', 'text-muted', 'severity-low', 'severity-low-bg', 'severity-high', 'severity-high-bg',
] as const
type Token = (typeof TOKENS)[number]

/** A theme token as a CSS colour, optionally translucent. Tokens are stored as "r g b" channels in index.css. */
export function tokenColor(channels: string, alpha = 1): string {
  return alpha >= 1 ? `rgb(${channels})` : `rgb(${channels} / ${alpha})`
}

function read(): Record<Token, string> {
  const style = getComputedStyle(document.documentElement)
  return Object.fromEntries(TOKENS.map((t) => [t, style.getPropertyValue(`--${t}`).trim()])) as Record<Token, string>
}

/**
 * Resolved colours for places CSS classes cannot reach: chart props, canvas drawing, toast styles.
 * Recomputed when the theme changes.
 */
export function useThemeColors() {
  const isDark = useUIStore((s) => s.isDark)
  return useMemo(() => {
    const t = read()
    const c = (name: Token, alpha?: number) => tokenColor(t[name], alpha)
    return {
      isDark,
      c,
      grid: c('border-subtle'),
      axis: c('text-secondary'),
      text: c('text-primary'),
      muted: c('text-secondary'),
      surface: c('bg-secondary'),
      /** Outline that separates a marker from whatever is under it. */
      outline: c('bg-primary'),
      tooltip: {
        background: c('bg-elevated'),
        border: `1px solid ${c('border-default')}`,
        borderRadius: '8px',
        fontSize: '12px',
        color: c('text-primary'),
      } as React.CSSProperties,
    }
  }, [isDark])
}
