import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives'
import { AllOrdersTab } from './AllOrdersTab'
import { PendingOrdersTab } from './PendingOrdersTab'
import { CancelledFailedTab } from './CancelledFailedTab'
import { useOrders } from '../useBookData'

type Sub = 'all' | 'pending' | 'cancelled'

function isSub(v: string | null): v is Sub {
  return v === 'all' || v === 'pending' || v === 'cancelled'
}

export function OrdersTab() {
  const [params, setParams] = useSearchParams()
  const sub = isSub(params.get('sub')) ? (params.get('sub') as Sub) : 'all'

  const setSub = (next: Sub) => {
    const p = new URLSearchParams(params)
    p.set('sub', next)
    setParams(p, { replace: true })
  }

  const ordersQuery = useOrders({ limit: 2000 })
  const rows = ordersQuery.data?.orders ?? []

  const counts = useMemo(() => {
    let pending = 0
    let cancelled = 0
    for (const r of rows) {
      if (r.status === 'PENDING' || r.status === 'SUBMITTED') pending++
      else if (r.status === 'CANCELLED' || r.status === 'REJECTED' || r.status === 'FAILED') cancelled++
    }
    return { pending, cancelled }
  }, [rows])

  return (
    <Tabs value={sub} onValueChange={(v) => setSub(v as Sub)} className="flex flex-col h-full min-h-0">
      <TabsList className="shrink-0 px-2 pt-1 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
        <TabsTrigger value="all">All orders</TabsTrigger>
        <TabsTrigger value="pending">
          Pending
          {counts.pending > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-[2px] bg-[var(--status-warning)]/25 text-[var(--status-warning)] text-[9px] font-semibold">
              {counts.pending}
            </span>
          )}
        </TabsTrigger>
        <TabsTrigger value="cancelled">
          Cancelled / Failed
          {counts.cancelled > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-[2px] bg-[var(--status-error)]/25 text-[var(--status-error)] text-[9px] font-semibold">
              {counts.cancelled}
            </span>
          )}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="all" className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden">
        <AllOrdersTab />
      </TabsContent>
      <TabsContent value="pending" className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden">
        <PendingOrdersTab />
      </TabsContent>
      <TabsContent value="cancelled" className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden">
        <CancelledFailedTab />
      </TabsContent>
    </Tabs>
  )
}
