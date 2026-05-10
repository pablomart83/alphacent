import { Hammer } from 'lucide-react'
import { EmptyState } from '@/components/primitives'

export function StressTab() {
  return (
    <div className="flex h-full items-center justify-center px-6">
      <EmptyState
        icon={Hammer}
        title="Stress — coming in Sprint 11"
        description="Scenario cards (COVID, Lehman, SVB, custom) with simulated portfolio impact vs SPY."
      />
    </div>
  )
}
