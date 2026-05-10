import { Download, GitCompareArrows, PlayCircle, RefreshCw, XCircle } from 'lucide-react'
import { Button } from '@/components/primitives'
import { cn } from '@/lib/utils'

interface LibraryBulkBarProps {
  selectedCount: number
  totalCount: number
  /** True when exactly 2 rows are selected — enables Compare button. */
  canCompare: boolean
  onCompare: () => void
  onActivateSelected: () => void
  onRetireSelected: () => void
  onRefresh: () => void
  onExportCsv: () => void
  isActivating?: boolean
  isRetiring?: boolean
  isRefreshing?: boolean
  className?: string
}

export function LibraryBulkBar({
  selectedCount,
  totalCount,
  canCompare,
  onCompare,
  onActivateSelected,
  onRetireSelected,
  onRefresh,
  onExportCsv,
  isActivating,
  isRetiring,
  isRefreshing,
  className,
}: LibraryBulkBarProps) {
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
            variant="secondary"
            size="sm"
            onClick={onCompare}
            disabled={!canCompare}
            title={canCompare ? 'Compare selected strategies' : 'Select exactly 2 strategies to compare'}
            className="gap-1"
          >
            <GitCompareArrows className="h-3 w-3" />
            Compare {selectedCount > 0 ? `(${selectedCount})` : ''}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={onActivateSelected}
            loading={isActivating}
            className="gap-1"
          >
            <PlayCircle className="h-3 w-3" />
            Activate
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={onRetireSelected}
            loading={isRetiring}
            className="gap-1"
          >
            <XCircle className="h-3 w-3" />
            Retire
          </Button>
        </>
      ) : (
        <span className="text-[11px] text-[var(--text-3)]">
          {totalCount.toLocaleString('en-US')} strategies
        </span>
      )}
      <div className="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          loading={isRefreshing}
          title="Refresh library"
          className="gap-1"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onExportCsv}
          title="Export filtered rows as CSV"
          className="gap-1"
        >
          <Download className="h-3 w-3" />
          CSV
        </Button>
      </div>
    </div>
  )
}
