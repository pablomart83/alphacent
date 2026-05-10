import { Button } from '@/components/primitives'
import { cn } from '@/lib/utils'

interface SaveBarProps {
  dirty: boolean
  changeCount?: number
  onSave: () => void
  onReset: () => void
  loading?: boolean
  saveLabel?: string
  resetLabel?: string
  className?: string
}

export function SaveBar({
  dirty,
  changeCount,
  onSave,
  onReset,
  loading = false,
  saveLabel = 'Save',
  resetLabel = 'Reset',
  className,
}: SaveBarProps) {
  if (!dirty) return null
  return (
    <div
      className={cn(
        'sticky bottom-0 left-0 right-0 z-10',
        'flex items-center justify-between gap-3 px-3 py-2',
        'bg-[var(--bg-2)] border-t border-[var(--border-default)] shadow-lg',
        className,
      )}
    >
      <div className="text-[12px] text-[var(--text-1)]">
        {changeCount != null && (
          <span className="mono font-medium">
            {changeCount} unsaved change{changeCount === 1 ? '' : 's'}
          </span>
        )}
      </div>
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={onReset} disabled={loading}>
          {resetLabel}
        </Button>
        <Button variant="primary" size="sm" onClick={onSave} loading={loading}>
          {saveLabel}
        </Button>
      </div>
    </div>
  )
}
