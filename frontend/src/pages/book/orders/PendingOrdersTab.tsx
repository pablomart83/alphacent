import { AllOrdersTab } from './AllOrdersTab'
import { MarketStatusHeader } from './MarketStatusHeader'
import type { OrderRow } from '../useBookData'

const isPending = (r: OrderRow) => r.status === 'PENDING' || r.status === 'SUBMITTED'

/**
 * Pending orders — PENDING or SUBMITTED. Uses a client predicate since
 * the backend status_filter param only accepts a single status. The
 * sparse extra requests are cheap because we already fetch the full
 * orders list for the main tab.
 */
export function PendingOrdersTab() {
  return (
    <AllOrdersTab
      clientFilter={isPending}
      banner={<MarketStatusHeader />}
    />
  )
}
