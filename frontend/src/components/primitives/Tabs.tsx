import { forwardRef } from 'react'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

export const Tabs = TabsPrimitive.Root

const tabsListVariants = cva('inline-flex items-center gap-1', {
  variants: {
    variant: {
      underline: 'border-b border-[var(--border-subtle)] gap-0.5 w-full',
      pills: 'bg-[var(--bg-2)] rounded-[3px] p-0.5 gap-0',
      sidebar: 'flex-col w-full gap-0.5',
      segmented: 'bg-[var(--bg-2)] rounded-[3px] p-0.5 gap-0 border border-[var(--border-subtle)]',
    },
  },
  defaultVariants: { variant: 'underline' },
})

type TabsListProps = React.ComponentPropsWithoutRef<typeof TabsPrimitive.List> &
  VariantProps<typeof tabsListVariants>

export const TabsList = forwardRef<React.ElementRef<typeof TabsPrimitive.List>, TabsListProps>(
  ({ className, variant, ...props }, ref) => (
    <TabsPrimitive.List ref={ref} className={cn(tabsListVariants({ variant }), className)} {...props} />
  ),
)
TabsList.displayName = 'TabsList'

const tabsTriggerVariants = cva(
  [
    'inline-flex items-center gap-1.5 whitespace-nowrap',
    'text-[12px] font-medium',
    'transition-colors outline-none',
    'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)] focus-visible:outline-offset-1',
    'disabled:opacity-50 disabled:pointer-events-none',
  ],
  {
    variants: {
      variant: {
        underline: [
          'px-3 py-1.5 text-[var(--text-2)] relative',
          'hover:text-[var(--text-0)]',
          'data-[state=active]:text-[var(--text-0)]',
          'data-[state=active]:after:absolute data-[state=active]:after:bottom-0 data-[state=active]:after:left-0 data-[state=active]:after:right-0 data-[state=active]:after:h-[2px] data-[state=active]:after:bg-[var(--accent-primary)]',
        ],
        pills: [
          'px-2.5 py-1 rounded-[2px] text-[var(--text-2)]',
          'hover:text-[var(--text-0)]',
          'data-[state=active]:bg-[var(--bg-active)] data-[state=active]:text-[var(--text-0)]',
        ],
        sidebar: [
          'justify-start w-full px-2.5 py-1.5 rounded-[2px] text-[var(--text-2)]',
          'hover:bg-[var(--bg-hover)] hover:text-[var(--text-0)]',
          'data-[state=active]:bg-[var(--bg-active)] data-[state=active]:text-[var(--text-0)]',
          'data-[state=active]:border-l-2 data-[state=active]:border-[var(--accent-primary)] data-[state=active]:pl-2',
        ],
        segmented: [
          'px-2.5 py-1 rounded-[2px] text-[var(--text-2)] flex-1 justify-center',
          'hover:text-[var(--text-0)]',
          'data-[state=active]:bg-[var(--bg-1)] data-[state=active]:text-[var(--text-0)] data-[state=active]:shadow-sm',
        ],
      },
    },
    defaultVariants: { variant: 'underline' },
  },
)

type TabsTriggerProps = React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger> &
  VariantProps<typeof tabsTriggerVariants>

export const TabsTrigger = forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  TabsTriggerProps
>(({ className, variant, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(tabsTriggerVariants({ variant }), className)}
    {...props}
  />
))
TabsTrigger.displayName = 'TabsTrigger'

export const TabsContent = forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn(
      'mt-2 outline-none',
      'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)] focus-visible:outline-offset-2',
      className,
    )}
    {...props}
  />
))
TabsContent.displayName = 'TabsContent'
