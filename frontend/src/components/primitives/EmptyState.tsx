import type { LucideIcon } from 'lucide-react'
import { Inbox } from 'lucide-react'
import { cn } from '@/lib/utils'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 p-8 text-center',
        className,
      )}
    >
      <Icon className="h-8 w-8 text-[var(--text-3)]" />
      <div className="flex flex-col gap-0.5">
        <div className="text-[13px] font-medium text-[var(--text-1)]">{title}</div>
        {description && (
          <div className="text-[11px] text-[var(--text-2)] max-w-[360px]">{description}</div>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  )
}
