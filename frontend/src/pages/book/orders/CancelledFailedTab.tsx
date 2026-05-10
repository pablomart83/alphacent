import { AlertTriangle } from 'lucide-react'
import { AllOrdersTab } from './AllOrdersTab'
import type { OrderRow } from '../useBookData'

const isCancelledOrFailed = (r: OrderRow) =>
  r.status === 'CANCELLED' || r.status === 'REJECTED' || r.status === 'FAILED'

/**
 * Cancelled / Failed orders tab.
 *
 * Surfaces the known cosmetic artefact from the backend: entry orders
 * that land during market-closed windows are written as FAILED and
 * re-fired the next cycle. The banner makes that visible rather than
 * leaving users to puzzle at a high FAILED count.
 */
export function CancelledFailedTab() {
  return (
    <AllOrdersTab
      clientFilter={isCancelledOrFailed}
      banner={
        <div className="flex items-start gap-2 px-3 py-2 text-[11px] leading-[16px] bg-[var(--status-warning-bg)] border-b border-[var(--status-warning)]/30 text-[var(--status-warning)]">
          <AlertTriangle className="h-3.5 w-3.5 mt-[1px] shrink-0" />
          <span>
            Entry orders submitted while the market is closed are logged as{' '}
            <span className="font-semibold">FAILED</span> and retried each cycle once the session opens.
            That inflates the FAILED count here without signalling real execution problems.
          </span>
        </div>
      }
    />
  )
}
