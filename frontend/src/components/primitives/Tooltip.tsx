import { forwardRef } from 'react'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { cn } from '@/lib/utils'

export const TooltipProvider = TooltipPrimitive.Provider
export const Tooltip = TooltipPrimitive.Root
export const TooltipTrigger = TooltipPrimitive.Trigger

export const TooltipContent = forwardRef<
  React.ElementRef<typeof TooltipPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 4, ...props }, ref) => (
  <TooltipPrimitive.Content
    ref={ref}
    sideOffset={sideOffset}
    className={cn(
      'z-50 overflow-hidden rounded-[3px]',
      'bg-[var(--bg-3)] text-[var(--text-0)]',
      'border border-[var(--border-default)]',
      'px-2 py-1 text-[11px] shadow-lg',
      'data-[state=delayed-open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=delayed-open]:fade-in-0',
      'data-[side=bottom]:slide-in-from-top-1 data-[side=top]:slide-in-from-bottom-1',
      className,
    )}
    {...props}
  />
))

TooltipContent.displayName = 'TooltipContent'
