import { forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const inputVariants = cva(
  [
    'w-full rounded-[3px] bg-[var(--bg-1)] text-[var(--text-0)]',
    'border border-[var(--border-default)]',
    'placeholder:text-[var(--text-3)]',
    'transition-colors',
    'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)] focus-visible:outline-offset-0 focus-visible:border-[var(--border-focus)]',
    'disabled:opacity-50 disabled:cursor-not-allowed',
  ],
  {
    variants: {
      size: {
        sm: 'h-7 px-2 text-[11px]',
        md: 'h-8 px-2.5 text-[12px]',
        lg: 'h-9 px-3 text-[13px]',
      },
      variant: {
        default: '',
        filled: 'bg-[var(--bg-2)] border-transparent',
      },
      invalid: {
        true: 'border-[var(--status-error)] focus-visible:outline-[var(--status-error)]',
      },
    },
    defaultVariants: {
      size: 'md',
      variant: 'default',
    },
  },
)

export interface InputProps
  extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size' | 'prefix'>,
    VariantProps<typeof inputVariants> {
  prefix?: React.ReactNode
  suffix?: React.ReactNode
  error?: boolean
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, size, variant, error, prefix, suffix, ...props }, ref) => {
    if (prefix || suffix) {
      return (
        <div className="relative w-full">
          {prefix && (
            <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-[var(--text-2)]">
              {prefix}
            </span>
          )}
          <input
            ref={ref}
            className={cn(
              inputVariants({ size, variant, invalid: error }),
              prefix && 'pl-7',
              suffix && 'pr-7',
              className,
            )}
            {...props}
          />
          {suffix && (
            <span className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-2)]">
              {suffix}
            </span>
          )}
        </div>
      )
    }
    return (
      <input
        ref={ref}
        className={cn(inputVariants({ size, variant, invalid: error }), className)}
        {...props}
      />
    )
  },
)

Input.displayName = 'Input'
