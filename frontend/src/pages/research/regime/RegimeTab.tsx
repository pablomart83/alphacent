import { Hammer } from 'lucide-react'
import { EmptyState } from '@/components/primitives'

export function RegimeTab() {
  return (
    <div className="flex h-full items-center justify-center px-6">
      <EmptyState
        icon={Hammer}
        title="Regime — coming in Sprint 11"
        description="Per-asset-class regime grid, strategy × regime heatmap, market context, crypto cycle, carry rates, MQS."
      />
    </div>
  )
}
