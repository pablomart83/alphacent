import { forwardRef } from 'react'
import * as SwitchPrimitive from '@radix-ui/react-switch'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const switchVariants = cva(
  [
    'peer inline-flex shrink-0 items-center rounded-full',
    'border-2 border-transparent',
    'transition-colors',
    'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)] focus-visible:outline-offset-2',
    'disabled:cursor-not-allowed disabled:opacity-50',
    'data-[state=checked]:bg-[var(--accent-primary)]',
    'data-[state=unchecked]:bg-[var(--bg-active)]',
  ],
  {
    variants: {
      size: {
        sm: 'h-4 w-7',
        md: 'h-5 w-9',
        lg: 'h-6 w-11',
      },
      variant: {
        default: '',
        live:
          'data-[state=checked]:bg-[var(--account-live)] data-[state=unchecked]:bg-[var(--bg-active)]',
      },
    },
    defaultVariants: { size: 'md', variant: 'default' },
  },
)

const thumbVariants = cva(
  [
    'block rounded-full bg-white shadow-sm ring-0',
    'transition-transform',
  ],
  {
    variants: {
      size: {
        sm: 'h-3 w-3 data-[state=checked]:translate-x-3 data-[state=unchecked]:translate-x-0',
        md: 'h-4 w-4 data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0',
        lg: 'h-5 w-5 data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0',
      },
    },
    defaultVariants: { size: 'md' },
  },
)

type SwitchProps = React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root> &
  VariantProps<typeof switchVariants>

export const Switch = forwardRef<React.ElementRef<typeof SwitchPrimitive.Root>, SwitchProps>(
  ({ className, size, variant, ...props }, ref) => (
    <SwitchPrimitive.Root
      ref={ref}
      className={cn(switchVariants({ size, variant }), className)}
      {...props}
    >
      <SwitchPrimitive.Thumb className={thumbVariants({ size })} />
    </SwitchPrimitive.Root>
  ),
)

Switch.displayName = 'Switch'
