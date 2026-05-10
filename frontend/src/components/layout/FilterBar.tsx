import { cn } from '@/lib/utils'

interface FilterBarProps {
  children: React.ReactNode
  className?: string
}

export function FilterBar({ children, className }: FilterBarProps) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-1.5 py-1.5 px-2',
        'border-b border-[var(--border-subtle)]',
        className,
      )}
    >
      {children}
    </div>
  )
}
