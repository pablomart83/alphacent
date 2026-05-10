import { Hammer } from 'lucide-react'
import { PageTemplate } from '@/components/layout'
import { EmptyState } from '@/components/primitives'

interface ComingSoonProps {
  surface: string
  sprint: number
  description?: string
}

export function ComingSoon({ surface, sprint, description }: ComingSoonProps) {
  return (
    <PageTemplate title={surface} description={`Sprint ${sprint}`}>
      <div className="flex h-full items-center justify-center">
        <EmptyState
          icon={Hammer}
          title={`${surface} — coming soon`}
          description={
            description ??
            `Scaffold in place. Full implementation lands in Sprint ${sprint}. The shell, design system, WebSocket layer and API client are live and can be verified from this view.`
          }
        />
      </div>
    </PageTemplate>
  )
}
