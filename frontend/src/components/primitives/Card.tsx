import { forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const cardVariants = cva(
  'rounded-[4px] border border-[var(--border-subtle)] bg-[var(--bg-1)]',
  {
    variants: {
      variant: {
        default: '',
        elevated: 'bg-[var(--bg-2)] border-[var(--border-default)]',
        flush: 'border-none bg-transparent',
      },
      padding: {
        none: 'p-0',
        sm: 'p-2',
        md: 'p-3',
        lg: 'p-4',
      },
      interactive: {
        true: 'transition-colors hover:bg-[var(--bg-hover)] cursor-pointer',
      },
    },
    defaultVariants: {
      variant: 'default',
      padding: 'md',
    },
  },
)

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant, padding, interactive, ...props }, ref) => (
    <div ref={ref} className={cn(cardVariants({ variant, padding, interactive }), className)} {...props} />
  ),
)
Card.displayName = 'Card'
