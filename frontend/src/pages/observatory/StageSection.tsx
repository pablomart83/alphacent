import { useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StageSectionProps {
  /** Lifecycle stage label, e.g. "RESEARCH". */
  title: string
  /** Short qualifier shown next to the title. */
  hint?: string
  /** Right-aligned status chip (e.g. count / regime). */
  badge?: ReactNode
  /** Accent bar colour for the stage (uses a token). */
  accent?: string
  defaultOpen?: boolean
  /** When false, hides the collapse control (used inside mobile segmented view). */
  collapsible?: boolean
  children: ReactNode
  className?: string
}

/**
 * A titled, collapsible lifecycle zone. Uses the shared SectionLabel visual
 * language (10px uppercase) with a left accent bar so the four stages
 * (RESEARCH → BACKTEST → PAPER → LIVE) read as a progression.
 */
export function StageSection({
  title,
  hint,
  badge,
  accent = 'var(--border-strong)',
  defaultOpen = true,
  collapsible = true,
  children,
  className,
}: StageSectionProps) {
  const [open, setOpen] = useState(defaultOpen)
  const showBody = !collapsible || open

  return (
    <section className={cn('border-b border-[var(--border-subtle)]', className)}>
      <div
        className="flex items-center gap-2 px-3 py-1.5"
        style={{ borderLeft: `2px solid ${accent}` }}
      >
        {collapsible ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1.5 text-[var(--text-1)] hover:text-[var(--text-0)]"
            aria-expanded={open}
          >
            <ChevronDown
              className={cn('h-3 w-3 transition-transform', !open && '-rotate-90')}
            />
            <span className="text-[10px] font-semibold uppercase tracking-[0.14em]">{title}</span>
          </button>
        ) : (
          <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-1)]">
            {title}
          </span>
        )}
        {hint && <span className="text-[10px] text-[var(--text-3)] truncate">{hint}</span>}
        <div className="flex-1" />
        {badge}
      </div>
      {showBody && <div className="p-2 pt-0">{children}</div>}
    </section>
  )
}
