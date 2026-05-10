import { forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  [
    'inline-flex items-center gap-1 rounded-[3px] whitespace-nowrap',
    'font-medium uppercase tracking-wide',
    'border',
  ],
  {
    variants: {
      variant: {
        default: 'bg-[var(--bg-2)] text-[var(--text-1)] border-[var(--border-default)]',
        muted: 'bg-[var(--bg-2)] text-[var(--text-2)] border-transparent',
        success: 'bg-[var(--pnl-up-bg)] text-[var(--pnl-up)] border-[var(--pnl-up)]/30',
        warning: 'bg-[var(--status-warning-bg)] text-[var(--status-warning)] border-[var(--status-warning)]/30',
        error: 'bg-[var(--status-error-bg)] text-[var(--status-error)] border-[var(--status-error)]/40',
        info: 'bg-[color-mix(in_oklab,var(--status-info)_15%,transparent)] text-[var(--status-info)] border-[var(--status-info)]/30',
        demo: 'bg-[color-mix(in_oklab,var(--account-demo)_15%,transparent)] text-[var(--account-demo)] border-[var(--account-demo)]/40',
        live: 'bg-[color-mix(in_oklab,var(--account-live)_15%,transparent)] text-[var(--account-live)] border-[var(--account-live)]/40',
        paper: 'bg-[color-mix(in_oklab,var(--accent-secondary)_12%,transparent)] text-[var(--accent-secondary)] border-[var(--accent-secondary)]/30',
        backtested: 'bg-[color-mix(in_oklab,var(--status-warning)_12%,transparent)] text-[var(--status-warning)] border-[var(--status-warning)]/30',
        retired: 'bg-[var(--bg-2)] text-[var(--text-3)] border-[var(--border-subtle)]',
        'regime-up': 'bg-[color-mix(in_oklab,var(--regime-up)_15%,transparent)] text-[var(--regime-up)] border-[var(--regime-up)]/30',
        'regime-up-strong': 'bg-[color-mix(in_oklab,var(--regime-up-strong)_15%,transparent)] text-[var(--regime-up-strong)] border-[var(--regime-up-strong)]/30',
        'regime-down': 'bg-[color-mix(in_oklab,var(--regime-down)_15%,transparent)] text-[var(--regime-down)] border-[var(--regime-down)]/30',
        'regime-range': 'bg-[color-mix(in_oklab,var(--regime-range)_15%,transparent)] text-[var(--regime-range)] border-[var(--regime-range)]/30',
        'regime-vol': 'bg-[color-mix(in_oklab,var(--regime-vol)_15%,transparent)] text-[var(--regime-vol)] border-[var(--regime-vol)]/30',
      },
      size: {
        sm: 'h-[14px] px-1 text-[9px]',
        md: 'h-[16px] px-1.5 text-[10px]',
        lg: 'h-[20px] px-2 text-[11px]',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'md',
    },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, size, ...props }, ref) => (
    <span ref={ref} className={cn(badgeVariants({ variant, size }), className)} {...props} />
  ),
)

Badge.displayName = 'Badge'

export { badgeVariants }
