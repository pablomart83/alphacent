import { Hammer } from 'lucide-react'
import { EmptyState } from '@/components/primitives'

export function AlphaEdgeTab() {
  return (
    <div className="flex h-full items-center justify-center px-6">
      <EmptyState
        icon={Hammer}
        title="Alpha Edge — coming in Sprint 11"
        description="Fundamental + ML filter stats, conviction distribution with 65/74 thresholds, per-template performance, TCA."
      />
    </div>
  )
}
