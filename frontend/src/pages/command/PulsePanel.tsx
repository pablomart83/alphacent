import { AccountHero } from './AccountHero'
import { MetricsStrip } from './MetricsStrip'
import { MultiTimeframeReturns } from './MultiTimeframeReturns'
import type { PnLPeriodEntry } from './MultiTimeframeReturns'
import { RegimeBlock } from './RegimeBlock'
import { HealthScoreCard, type HealthScore } from './HealthScoreCard'
import { CycleStatusCard, type AutonomousStatusShape } from './CycleStatusCard'
import { StrategyPipelineCounts, type PipelineCounts } from './StrategyPipelineCounts'
import type { EquityPeriod } from '@/components/trading/EquityChart'

interface PulsePanelProps {
  equity: number | null | undefined
  todayPnl: number | null | undefined
  todayPnlPct: number | null | undefined
  unrealizedPnl: number | null | undefined
  availableCash: number | null | undefined
  winRate30d: number | null | undefined
  sharpe30d: number | null | undefined
  maxDrawdown: number | null | undefined
  liveEnabled: boolean
  liveAuthorisations: number
  pnlPeriods: PnLPeriodEntry[] | undefined
  chartPeriod: EquityPeriod
  onChartPeriodChange: (p: EquityPeriod) => void
  regime: string | null | undefined
  regimeConfidence?: number | null
  regimeDataQuality?: string | null
  regimeDescription?: string | null
  health: HealthScore | null | undefined
  autonomousStatus: AutonomousStatusShape | null | undefined
  pipelineCounts: PipelineCounts
  pipelineLoading?: boolean
}

export function PulsePanel(props: PulsePanelProps) {
  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)]">
      <AccountHero
        equity={props.equity}
        todayPnl={props.todayPnl}
        todayPnlPct={props.todayPnlPct}
        availableCash={props.availableCash}
        liveEnabled={props.liveEnabled}
        liveAuthorisations={props.liveAuthorisations}
      />
      <MetricsStrip
        equity={props.equity}
        dailyPnl={props.todayPnl}
        dailyPnlPct={props.todayPnlPct}
        unrealizedPnl={props.unrealizedPnl}
        winRate30d={props.winRate30d}
        sharpe30d={props.sharpe30d}
        maxDrawdown={props.maxDrawdown}
        cash={props.availableCash}
      />
      <MultiTimeframeReturns
        periods={props.pnlPeriods}
        selectedChartPeriod={props.chartPeriod}
        onChartPeriodChange={props.onChartPeriodChange}
      />
      <RegimeBlock
        regime={props.regime}
        confidence={props.regimeConfidence}
        dataQuality={props.regimeDataQuality}
        description={props.regimeDescription}
      />
      <HealthScoreCard health={props.health} />
      <CycleStatusCard status={props.autonomousStatus} />
      <StrategyPipelineCounts
        counts={props.pipelineCounts}
        loading={props.pipelineLoading}
      />
    </div>
  )
}
