import { AccountHero } from './AccountHero'
import { MetricsStrip } from './MetricsStrip'
import { MultiTimeframeReturns } from './MultiTimeframeReturns'
import type { PnLPeriodEntry } from './MultiTimeframeReturns'
import { RegimeBlock } from './RegimeBlock'
import { FundScorecardCard } from './FundScorecardCard'
import { DemoLiveSplitTile } from './DemoLiveSplitTile'
import { AlphaGenTile } from './AlphaGenTile'
import { DailyBriefingCard } from './DailyBriefingCard'
import { CycleStatusCard, type AutonomousStatusShape } from './CycleStatusCard'
import { StrategyPipelineCounts, type PipelineCounts } from './StrategyPipelineCounts'
import type { EquityPeriod } from '@/components/trading/EquityChart'
import type { DashboardSummaryPayload, PerformanceAnalyticsPayload } from './useCommandData'
import type { LiveSummary } from '@/pages/book/useBookData'

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
  autonomousStatus: AutonomousStatusShape | null | undefined
  pipelineCounts: PipelineCounts
  pipelineLoading?: boolean
  // New props for enhanced panels
  dashboard?: DashboardSummaryPayload | undefined
  performance?: PerformanceAnalyticsPayload | undefined
  liveSummary?: LiveSummary | undefined
  dashboardLoading?: boolean
  performanceLoading?: boolean
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

      {/* DEMO vs LIVE split — Item 1 */}
      <DemoLiveSplitTile
        liveSummary={props.liveSummary}
        loading={props.dashboardLoading}
      />

      {/* Alpha generation 7d / 30d — Item 2 */}
      <AlphaGenTile />

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

      {/* Fund Scorecard — Item 5 (replaces HealthScoreCard) */}
      <FundScorecardCard
        performance={props.performance}
        loading={props.performanceLoading}
      />

      <CycleStatusCard status={props.autonomousStatus} />

      <StrategyPipelineCounts
        counts={props.pipelineCounts}
        loading={props.pipelineLoading}
      />

      {/* Daily Briefing — Item 8 */}
      <DailyBriefingCard
        dashboard={props.dashboard}
        performance={props.performance}
        autonomousStatus={props.autonomousStatus}
        pipelineCounts={props.pipelineCounts}
        liveSummary={props.liveSummary}
      />
    </div>
  )
}
