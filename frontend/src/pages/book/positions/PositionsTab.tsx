import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives'
import { ResizablePanelLayout } from '@/components/layout'
import { OpenPositionsTab } from './OpenPositionsTab'
import { PendingClosuresTab } from './PendingClosuresTab'
import { FundamentalAlertsTab } from './FundamentalAlertsTab'
import { ClosedPositionsTab } from './ClosedPositionsTab'
import { AllocationPanel } from './AllocationPanel'
import {
  useFundamentalAlerts,
  useOpenPositions,
  usePendingClosures,
} from '../useBookData'

type SubTab = 'open' | 'pending' | 'fundamental' | 'closed'

function isSubTab(v: string | null): v is SubTab {
  return v === 'open' || v === 'pending' || v === 'fundamental' || v === 'closed'
}

export function PositionsTab() {
  const [params, setParams] = useSearchParams()
  const sub = isSubTab(params.get('sub')) ? (params.get('sub') as SubTab) : 'open'

  const setSub = (next: SubTab) => {
    const p = new URLSearchParams(params)
    p.set('sub', next)
    setParams(p, { replace: true })
  }

  const openQuery = useOpenPositions()
  const pendingQuery = usePendingClosures()
  const alertsQuery = useFundamentalAlerts()

  const pendingCount = pendingQuery.data?.positions?.length ?? 0
  const alertCount = alertsQuery.data?.alerts?.length ?? 0

  const allocationPositions = useMemo(
    () => openQuery.data?.positions ?? [],
    [openQuery.data?.positions],
  )

  return (
    <ResizablePanelLayout
      layoutId="book.positions"
      panels={[
        {
          id: 'positions-main',
          defaultSize: 70,
          minSize: 50,
          content: (
            <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
              <Tabs value={sub} onValueChange={(v) => setSub(v as SubTab)} className="flex flex-col h-full min-h-0">
                <TabsList className="shrink-0 px-2 pt-1 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
                  <TabsTrigger value="open">Open</TabsTrigger>
                  <TabsTrigger value="pending">
                    Pending closures
                    {pendingCount > 0 && (
                      <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-[2px] bg-[var(--status-warning)]/25 text-[var(--status-warning)] text-[9px] font-semibold">
                        {pendingCount}
                      </span>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="fundamental">
                    Fundamental alerts
                    {alertCount > 0 && (
                      <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-[2px] bg-[var(--status-error)]/25 text-[var(--status-error)] text-[9px] font-semibold">
                        {alertCount}
                      </span>
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="closed">Closed</TabsTrigger>
                </TabsList>
                <TabsContent value="open" className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden">
                  <OpenPositionsTab />
                </TabsContent>
                <TabsContent value="pending" className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden">
                  <PendingClosuresTab />
                </TabsContent>
                <TabsContent value="fundamental" className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden">
                  <FundamentalAlertsTab />
                </TabsContent>
                <TabsContent value="closed" className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden">
                  <ClosedPositionsTab />
                </TabsContent>
              </Tabs>
            </div>
          ),
        },
        {
          id: 'positions-side',
          defaultSize: 30,
          minSize: 20,
          maxSize: 45,
          content: (
            <AllocationPanel
              positions={allocationPositions}
              loading={openQuery.isLoading}
            />
          ),
        },
      ]}
    />
  )
}
