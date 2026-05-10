import { cn } from '@/lib/utils'

interface PageTemplateProps {
  title: string
  description?: string
  actions?: React.ReactNode
  children: React.ReactNode
  compact?: boolean
  className?: string
}

export function PageTemplate({
  title,
  description,
  actions,
  children,
  compact = false,
  className,
}: PageTemplateProps) {
  return (
    <div className={cn('flex flex-col h-full min-h-0 bg-[var(--bg-0)]', className)}>
      <div
        className={cn(
          'flex items-center justify-between gap-4 shrink-0',
          'border-b border-[var(--border-subtle)] bg-[var(--bg-0)]',
          compact ? 'px-3 py-1' : 'px-4 py-2',
        )}
      >
        <div className="flex items-baseline gap-3 min-w-0">
          <h1
            className={cn(
              'font-semibold text-[var(--text-0)] truncate',
              compact ? 'text-[13px]' : 'text-[15px]',
            )}
          >
            {title}
          </h1>
          {description && (
            <span className={cn('text-[11px] text-[var(--text-2)] truncate')}>{description}</span>
          )}
        </div>
        {actions && <div className="flex items-center gap-1 shrink-0">{actions}</div>}
      </div>
      <div className="flex-1 min-h-0 overflow-hidden">{children}</div>
    </div>
  )
}
