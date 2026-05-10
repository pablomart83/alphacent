import { Hammer } from 'lucide-react'
import { EmptyState } from '@/components/primitives'

export function TearSheetTab() {
  return (
    <div className="flex h-full items-center justify-center px-6">
      <EmptyState
        icon={Hammer}
        title="Tear Sheet — coming in Sprint 11"
        description="Underwater plot, worst drawdowns, return distribution with skew/kurtosis, annual + monthly heatmaps."
      />
    </div>
  )
}
