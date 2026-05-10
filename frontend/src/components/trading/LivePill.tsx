import { cn } from '@/lib/utils'

export type LivePillState = 'off' | 'on-no-authorisations' | 'on-active'

interface LivePillProps {
  state: LivePillState
  authorisationCount?: number
  size?: 'sm' | 'md' | 'lg'
  className?: string
  onClick?: () => void
}

const SIZE_CLASS = {
  sm: 'h-[16px] px-1.5 text-[10px] gap-1',
  md: 'h-[20px] px-2 text-[11px] gap-1.5',
  lg: 'h-[24px] px-2.5 text-[12px] gap-1.5',
} as const

const STATE_STYLES: Record<
  LivePillState,
  { color: string; bg: string; border: string; dot: string; pulse: boolean; label: (n?: number) => string }
> = {
  off: {
    color: 'var(--text-3)',
    bg: 'transparent',
    border: 'var(--border-default)',
    dot: 'var(--text-3)',
    pulse: false,
    label: () => 'Live Off',
  },
  'on-no-authorisations': {
    color: 'var(--status-warning)',
    bg: 'var(--status-warning-bg)',
    border: 'color-mix(in oklab, var(--status-warning) 40%, transparent)',
    dot: 'var(--status-warning)',
    pulse: true,
    label: () => 'Live On · 0 auth',
  },
  'on-active': {
    color: 'var(--account-live)',
    bg: 'color-mix(in oklab, var(--account-live) 15%, transparent)',
    border: 'color-mix(in oklab, var(--account-live) 45%, transparent)',
    dot: 'var(--account-live)',
    pulse: false,
    label: (n) => `Live · ${n ?? 0}`,
  },
}

export function LivePill({
  state,
  authorisationCount,
  size = 'md',
  className,
  onClick,
}: LivePillProps) {
  const style = STATE_STYLES[state]
  const Component = onClick ? 'button' : 'span'

  return (
    <Component
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={cn(
        'inline-flex items-center rounded-[3px] border font-medium uppercase tracking-wide',
        SIZE_CLASS[size],
        onClick && 'hover:brightness-110 cursor-pointer focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]',
        className,
      )}
      style={{ color: style.color, backgroundColor: style.bg, borderColor: style.border }}
    >
      <span
        className={cn(
          'inline-block h-1.5 w-1.5 rounded-full',
          style.pulse && 'animate-pulse',
        )}
        style={{ backgroundColor: style.dot }}
        aria-hidden
      />
      {style.label(authorisationCount)}
    </Component>
  )
}
