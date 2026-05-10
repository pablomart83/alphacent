import { forwardRef } from 'react'
import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

type CheckboxProps = React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>

export const Checkbox = forwardRef<React.ElementRef<typeof CheckboxPrimitive.Root>, CheckboxProps>(
  ({ className, ...props }, ref) => (
    <CheckboxPrimitive.Root
      ref={ref}
      className={cn(
        'peer h-3.5 w-3.5 shrink-0 rounded-[2px]',
        'border border-[var(--border-strong)] bg-[var(--bg-1)]',
        'transition-colors',
        'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)] focus-visible:outline-offset-1',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'data-[state=checked]:bg-[var(--accent-primary)] data-[state=checked]:border-[var(--accent-primary)]',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center text-white">
        <Check className="h-3 w-3" strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  ),
)

Checkbox.displayName = 'Checkbox'
