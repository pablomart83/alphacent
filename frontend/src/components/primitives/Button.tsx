import { forwardRef } from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center gap-1.5',
    'font-medium whitespace-nowrap select-none',
    'border border-transparent rounded-[3px]',
    'transition-colors outline-none',
    'disabled:pointer-events-none disabled:opacity-50',
    'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)] focus-visible:outline-offset-2',
  ],
  {
    variants: {
      variant: {
        primary:
          'bg-[var(--accent-primary)] text-white hover:brightness-110 active:brightness-90',
        secondary:
          'bg-[var(--bg-2)] text-[var(--text-0)] border-[var(--border-default)] hover:bg-[var(--bg-hover)] active:bg-[var(--bg-active)]',
        ghost:
          'bg-transparent text-[var(--text-1)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-0)]',
        destructive:
          'bg-[var(--status-error)] text-white hover:brightness-110 active:brightness-90',
        live:
          'bg-[var(--account-live)] text-white hover:brightness-110 active:brightness-90',
        outline:
          'bg-transparent text-[var(--text-1)] border-[var(--border-strong)] hover:bg-[var(--bg-hover)] hover:text-[var(--text-0)]',
        link:
          'bg-transparent text-[var(--accent-primary)] hover:underline p-0 h-auto',
      },
      size: {
        sm: 'h-7 px-2 text-[11px] gap-1',
        md: 'h-8 px-3 text-[12px]',
        lg: 'h-9 px-4 text-[13px]',
        icon: 'h-7 w-7 p-0',
        'icon-sm': 'h-6 w-6 p-0',
      },
    },
    defaultVariants: {
      variant: 'secondary',
      size: 'md',
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    // `Slot` requires exactly one child. When asChild=true we must NOT emit
    // the loading spinner as a sibling — it falls through to the caller.
    const content = asChild ? (
      children
    ) : (
      <>
        {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
        {children}
      </>
    )
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        {...props}
      >
        {content}
      </Comp>
    )
  },
)

Button.displayName = 'Button'

export { buttonVariants }
