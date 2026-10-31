import { Fragment } from 'react'
import { HIGHLIGHT_STYLES } from '@/lib/palette'
import { cn } from '@/utils'
import type { TextHighlight } from '@/types'

const KIND_LABEL: Record<string, string> = {
  crime: 'Offence',
  weapon: 'Weapon',
  legal: 'Legal',
  place: 'Place',
  vehicle: 'Vehicle',
  phone: 'Phone',
  upi: 'UPI',
  amount: 'Amount',
}

/**
 * Renders an FIR narrative in its own script with every recognised term marked and glossed in English.
 * Offsets come from the server and index the original string, so highlights stay exact in any language.
 */
export default function HighlightedText({ text, highlights, dir }: { text: string; highlights: TextHighlight[]; dir?: 'rtl' | 'ltr' }) {
  const parts: JSX.Element[] = []
  let cursor = 0
  const sorted = [...highlights].sort((a, b) => a.start - b.start)
  sorted.forEach((h, i) => {
    if (h.start < cursor || text.slice(h.start, h.end) !== h.text) return
    if (h.start > cursor) parts.push(<Fragment key={`t${i}`}>{text.slice(cursor, h.start)}</Fragment>)
    parts.push(
      <mark
        key={`h${i}`}
        title={`${KIND_LABEL[h.kind] ?? h.kind}: ${h.gloss}`}
        className={cn(
          'group relative rounded-sm px-0.5 underline decoration-dotted decoration-1 underline-offset-4 cursor-help',
          HIGHLIGHT_STYLES[h.kind] ?? 'bg-bg-hover text-text-primary',
        )}
      >
        {h.text}
        <span
          role="tooltip"
          className="pointer-events-none absolute left-1/2 top-full z-20 mt-1.5 -translate-x-1/2 whitespace-nowrap rounded-md border border-border-default bg-bg-elevated px-2 py-1 text-2xs font-medium text-text-primary opacity-0 shadow-elevated transition-opacity duration-150 group-hover:opacity-100"
          dir="ltr"
        >
          <span className="text-text-muted">{KIND_LABEL[h.kind] ?? h.kind} · </span>
          {h.gloss}
        </span>
      </mark>,
    )
    cursor = h.end
  })
  if (cursor < text.length) parts.push(<Fragment key="tail">{text.slice(cursor)}</Fragment>)

  return (
    <p dir={dir} className="text-sm leading-8 text-text-primary whitespace-pre-wrap break-words">
      {parts}
    </p>
  )
}

export function HighlightLegend({ kinds }: { kinds: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {kinds.map((k) => (
        <span key={k} className={cn('rounded px-1.5 py-0.5 text-2xs font-medium', HIGHLIGHT_STYLES[k])}>
          {KIND_LABEL[k] ?? k}
        </span>
      ))}
    </div>
  )
}
