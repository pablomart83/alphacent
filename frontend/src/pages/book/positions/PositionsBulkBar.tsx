import { Download, RefreshCw, XCircle } from 'lucide-react'
import { Button } from '@/components/primitives'
import { cn } from '@/lib/utils'

interface PositionsBulkBarProps {
  selectedCount: number
  totalCount: number
  onCloseSelected: () => void
  onCloseAll: () => void
  onSync: () => void
  onExportCsv: () => void
  isSyncing?: boolean
  isClosing?: boolean
  className?: string
}

export function PositionsBulkBar({
  selectedCount,
  totalCount,
  onCloseSelected,
  onCloseAll,
  onSync,
  onExportCsv,
  isSyncing,
  isClosing,
  className,
}: PositionsBulkBarProps) {
  const hasSelection = selectedCount > 0

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-2 py-1 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]',
        hasSelection && 'bg-[color-mix(in_oklab,var(--accent-primary)_8%,var(--bg-1))]',
        className,
      )}
    >
      {hasSelection ? (
        <>
          <span className="text-[11px] text-[var(--text-1)] font-medium">
            {selectedCount} selected
          </span>
          <Button
            variant="destructive"
            size="sm"
            onClick={onCloseSelected}
            loading={isClosing}
          >
            Close selected
          </Button>
        </>
      ) : (
        <span className="text-[11px] text-[var(--text-3)]">
          {totalCount.toLocaleString('en-US')} positions
        </span>
      )}
      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={onSync}
          loading={isSyncing}
          title="Re-sync positions from eToro"
          className="gap-1"
        >
          <RefreshCw className="h-3 w-3" />
          Sync
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onExportCsv}
          className="gap-1"
          title="Export filtered rows as CSV"
        >
          <Download className="h-3 w-3" />
          CSV
        </Button>
        <Button
          variant="destructive"
          size="sm"
          onClick={onCloseAll}
          className="gap-1"
          title="Close every open position"
        >
          <XCircle className="h-3 w-3" />
          Close all
        </Button>
      </div>
    </div>
  )
}
