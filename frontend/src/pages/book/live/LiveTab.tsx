import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/primitives'
import { AllOrdersTab } from '../orders/AllOrdersTab'
import { MasterSwitchBlock } from './MasterSwitchBlock'
import { AccountTiles } from './AccountTiles'
import { MirrorRatioStrip } from './MirrorRatioStrip'
import { LiveOverviewTab } from './LiveOverviewTab'
import { LivePositionsTab } from './LivePositionsTab'
import { LiveDivergenceTab } from './LiveDivergenceTab'
import { useLiveConfig, useLiveDivergence, useLiveSummary } from '../useBookData'

type Sub = 'overview' | 'positions' | 'orders' | 'divergence'

function isSub(v: string | null): v is Sub {
  return v === 'overview' || v === 'positions' || v === 'orders' || v === 'divergence'
}

export function LiveTab() {
  const [params, setParams] = useSearchParams()
  const sub = isSub(params.get('sub')) ? (params.get('sub') as Sub) : 'overview'

  const setSub = (next: Sub) => {
    const p = new URLSearchParams(params)
    p.set('sub', next)
    setParams(p, { replace: true })
  }

  const summaryQuery = useLiveSummary()
  const config = useLiveConfig()
  const divergence = useLiveDivergence()

  const openPositions = summaryQuery.data?.open_positions ?? 0
  const flagged = useMemo(
    () => divergence.data?.divergence.filter((d) => d.divergence_flag).length ?? 0,
    [divergence.data?.divergence],
  )

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)]">
      {/* Header block — master switch, tiles, mirror strip */}
      <div className="flex flex-col gap-3 p-3 shrink-0 border-b border-[var(--border-subtle)]">
        <MasterSwitchBlock />
        <AccountTiles summary={summaryQuery.data} loading={summaryQuery.isLoading} />
        <MirrorRatioStrip config={config.data} />
      </div>

      {/* Sub-tabs */}
      <Tabs value={sub} onValueChange={(v) => setSub(v as Sub)} className="flex flex-col flex-1 min-h-0">
        <TabsList className="shrink-0 px-2 pt-1 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="positions">
            Positions
            {openPositions > 0 && (
              <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-[2px] bg-[var(--account-live)]/25 text-[var(--account-live)] text-[9px] font-semibold">
                {openPositions}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="orders">Orders</TabsTrigger>
          <TabsTrigger value="divergence">
            Divergence
            {flagged > 0 && (
              <span className="ml-1.5 inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-[2px] bg-[var(--status-error)]/25 text-[var(--status-error)] text-[9px] font-semibold">
                {flagged}
              </span>
            )}
          </TabsTrigger>
        </TabsList>
        <TabsContent
          value="overview"
          className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden"
        >
          <LiveOverviewTab />
        </TabsContent>
        <TabsContent
          value="positions"
          className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden"
        >
          <LivePositionsTab />
        </TabsContent>
        <TabsContent
          value="orders"
          className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden"
        >
          <AllOrdersTab pinMode="LIVE" />
        </TabsContent>
        <TabsContent
          value="divergence"
          className="flex-1 min-h-0 m-0 data-[state=inactive]:hidden"
        >
          <LiveDivergenceTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
