import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from './Button'
import { cn } from '@/lib/utils'

interface ErrorStateProps {
  title?: string
  message?: string
  onRetry?: () => void
  lastGoodAt?: Date | null
  className?: string
}

export function ErrorState({
  title = 'Something went wrong',
  message = 'Request failed. Try again.',
  onRetry,
  lastGoodAt,
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 p-6 text-center',
        className,
      )}
    >
      <AlertTriangle className="h-6 w-6 text-[var(--status-error)]" />
      <div className="text-[13px] font-medium text-[var(--text-0)]">{title}</div>
      <div className="text-[11px] text-[var(--text-2)] max-w-[420px]">{message}</div>
      {lastGoodAt && (
        <div className="text-[10px] text-[var(--text-3)]">
          Last fresh: {lastGoodAt.toLocaleTimeString()}
        </div>
      )}
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-1">
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </Button>
      )}
    </div>
  )
}
