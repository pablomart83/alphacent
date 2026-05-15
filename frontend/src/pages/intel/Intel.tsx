import { PageTemplate } from '@/components/layout'
import { IntelPage } from './IntelPage'

/**
 * Intel page — /intel
 *
 * Manually-triggered analyst that reads all system data and surfaces
 * structured findings with evidence and recommended actions.
 */
export function Intel() {
  return (
    <PageTemplate title="Intel" description="System analyst · findings · recommendations">
      <IntelPage />
    </PageTemplate>
  )
}
