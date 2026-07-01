import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface PanelProps {
  title: string
  /** Accent bar colour (lifecycle stage). */
  accent?: string
  /** Right-aligned chip (count, account tag, status). */
  badge?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}

/**
 * A board panel: fixed header + internally-scrolling body. This is what keeps
 * the Observatory a fitted single-pane (the PAGE doesn't scroll; PANELS do),
 * the way a trading-desk terminal tiles the screen.
 */
export function Panel({ title, accent, badge, children, className, bodyClassName }: PanelProps) {
  return (
    <section
      className={cn(
        'flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[4px] border border-[var(--border-subtle)] bg-[var(--bg-1)]',
        className,
      )}
    >
      <div
        className="flex h-[26px] shrink-0 items-center gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-2)] px-2"
        style={accent ? { borderLeft: `2px solid ${accent}` } : undefined}
      >
        <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-1)]">
          {title}
        </span>
        <div className="flex-1" />
        {badge}
      </div>
      <div className={cn('min-h-0 flex-1 overflow-y-auto p-2', bodyClassName)}>{children}</div>
    </section>
  )
}
