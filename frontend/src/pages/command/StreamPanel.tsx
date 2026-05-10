import { PanelHeader } from '@/components/layout'
import { SignalFeed } from '@/components/trading/SignalFeed'
import { OrderFillsTicker } from '@/components/trading/OrderFillsTicker'
import { LifecycleFeed } from '@/components/trading/LifecycleFeed'
import { AlertsBadge } from '@/components/trading/AlertsBadge'

export function StreamPanel() {
  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      <div className="shrink-0 p-2 border-b border-[var(--border-subtle)]">
        <AlertsBadge className="w-full justify-center" />
      </div>
      <div className="grid grid-rows-[1fr_auto_auto] flex-1 min-h-0 overflow-hidden">
        <PanelHeader title="Signals" bodyClassName="overflow-hidden" className="min-h-0">
          <SignalFeed />
        </PanelHeader>
        <PanelHeader title="Fills" bodyClassName="overflow-hidden" className="min-h-[180px] max-h-[240px]">
          <OrderFillsTicker />
        </PanelHeader>
        <PanelHeader title="Lifecycle" bodyClassName="overflow-hidden" className="min-h-[160px] max-h-[220px]">
          <LifecycleFeed />
        </PanelHeader>
      </div>
    </div>
  )
}
