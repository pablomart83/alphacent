import { CycleStatusCard, type AutonomousStatusShape } from '@/pages/command/CycleStatusCard'
import { StrategyPipelineCounts, type PipelineCounts } from '@/pages/command/StrategyPipelineCounts'
import { RegimeBlock } from '@/pages/command/RegimeBlock'

interface ResearchZoneProps {
  autonomousStatus: AutonomousStatusShape | null | undefined
  pipelineCounts: PipelineCounts
  pipelineLoading?: boolean
  regime: string | null
  regimeConfidence: number | null
  regimeDataQuality: string | null
  regimeDescription: string | null
}

/**
 * RESEARCH — idea generation: market regime, the autonomous proposal cycle, and
 * the strategy pipeline funnel. All three are prop-driven Command cards reused
 * verbatim (no fork).
 */
export function ResearchZone({
  autonomousStatus,
  pipelineCounts,
  pipelineLoading,
  regime,
  regimeConfidence,
  regimeDataQuality,
  regimeDescription,
}: ResearchZoneProps) {
  return (
    <div className="flex flex-col gap-2 [&>*]:rounded-[3px] [&>*]:border [&>*]:border-[var(--border-subtle)]">
      <RegimeBlock
        regime={regime}
        confidence={regimeConfidence}
        dataQuality={regimeDataQuality}
        description={regimeDescription}
      />
      <CycleStatusCard status={autonomousStatus} />
      <StrategyPipelineCounts counts={pipelineCounts} loading={pipelineLoading} />
    </div>
  )
}
