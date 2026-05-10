import { Hammer } from 'lucide-react'
import { EmptyState } from '@/components/primitives'

export function JournalTab() {
  return (
    <div className="flex h-full items-center justify-center px-6">
      <EmptyState
        icon={Hammer}
        title="Journal — coming in Sprint 11"
        description="Per-trade journal with virtualised list, MAE/MFE scatter, patterns panel, CSV export."
      />
    </div>
  )
}
