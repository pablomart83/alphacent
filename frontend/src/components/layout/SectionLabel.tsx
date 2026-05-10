import { cn } from '@/lib/utils'

interface SectionLabelProps {
  children: React.ReactNode
  actions?: React.ReactNode
  className?: string
}

export function SectionLabel({ children, actions, className }: SectionLabelProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-between',
        'text-[10px] font-medium uppercase tracking-wider text-[var(--text-3)]',
        'mb-1.5',
        className,
      )}
    >
      <div>{children}</div>
      {actions && <div className="flex items-center gap-1">{actions}</div>}
    </div>
  )
}
