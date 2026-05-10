import { RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Spinner } from '@/components/primitives'

interface PanelHeaderProps {
  title: string
  actions?: React.ReactNode
  onRefresh?: () => void
  isRefreshing?: boolean
  children?: React.ReactNode
  className?: string
  bodyClassName?: string
}

export function PanelHeader({
  title,
  actions,
  onRefresh,
  isRefreshing = false,
  children,
  className,
  bodyClassName,
}: PanelHeaderProps) {
  return (
    <div className={cn('flex flex-col h-full min-h-0', className)}>
      <div
        className="flex items-center justify-between px-2 shrink-0 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]"
        style={{ height: 'var(--panel-header-h)' }}
      >
        <h3 className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-2)]">
          {title}
        </h3>
        <div className="flex items-center gap-1">
          {actions}
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              aria-label={`Refresh ${title}`}
              className="p-1 rounded-[2px] text-[var(--text-3)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)] transition-colors"
            >
              {isRefreshing ? (
                <Spinner size="xs" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
            </button>
          )}
        </div>
      </div>
      <div className={cn('flex-1 min-h-0 overflow-auto', bodyClassName)}>{children}</div>
    </div>
  )
}
