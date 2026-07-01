import { FreshnessDot } from '@/components/primitives'
import { cn } from '@/lib/utils'

interface DataFreshnessIndicatorProps {
  /** Epoch ms of the last successful dashboard data touch. */
  dataUpdatedAt: number | null
  /** ISO of the last successful data-pipeline sync (reconciliation proxy). */
  lastSyncAt: string | null
  className?: string
}

/**
 * Surfaces the two things fund dashboards break on first: stale valuations and
 * failed reconciliation. Research (fundcount, family-office guidance) is
 * explicit that data completeness/freshness deserves a first-class, always-on
 * signal — so it lives in the sticky fund header, not buried in a tab.
 * Content rephrased for compliance with licensing restrictions.
 */
export function DataFreshnessIndicator({
  dataUpdatedAt,
  lastSyncAt,
  className,
}: DataFreshnessIndicatorProps) {
  return (
    <div className={cn('flex items-center gap-3', className)}>
      <FreshnessDot
        label="Data"
        since={dataUpdatedAt}
        showAge
        warnAfterSec={90}
        staleAfterSec={300}
      />
      <FreshnessDot
        label="Sync"
        since={lastSyncAt}
        showAge
        warnAfterSec={30 * 60}
        staleAfterSec={90 * 60}
      />
    </div>
  )
}
