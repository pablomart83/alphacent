import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import type { EquityInterval, EquityPeriod } from '@/components/trading/EquityChart'
import { EquityPanel } from '@/pages/command/EquityPanel'
import { useObservatoryData } from './useObservatoryData'
import { FundHeader } from './FundHeader'
import { AttentionRail } from './AttentionRail'
import { StageSection } from './StageSection'
import { SignalFeed } from '@/components/trading/SignalFeed'
import { OrderFillsTicker } from '@/components/trading/OrderFillsTicker'
import { PanelHeader } from '@/components/layout'
import { ResearchZone } from './zones/ResearchZone'
import { BacktestZone } from './zones/BacktestZone'
import { PaperZone } from './zones/PaperZone'
import { LiveZone } from './zones/LiveZone'

const PERIOD_SET: EquityPeriod[] = ['1W', '1M', '3M', '6M', '1Y', 'ALL']
const INTERVAL_SET: EquityInterval[] = ['1d', '4h', '1h']

function isPeriod(v: string | null): v is EquityPeriod {
  return !!v && (PERIOD_SET as string[]).includes(v)
}
function isInterval(v: string | null): v is EquityInterval {
  return !!v && (INTERVAL_SET as string[]).includes(v)
}

type MobileTab = 'overview' | 'research' | 'backtest' | 'paper' | 'live' | 'activity'
const MOBILE_TABS: { id: MobileTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'research', label: 'Research' },
  { id: 'backtest', label: 'Backtest' },
  { id: 'paper', label: 'Paper' },
  { id: 'live', label: 'Live' },
  { id: 'activity', label: 'Activity' },
]

const STAGE_ACCENT = {
  research: 'var(--accent-secondary)',
  backtest: 'var(--accent-primary)',
  paper: 'var(--account-demo)',
  live: 'var(--account-live)',
} as const

export function Observatory() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { isDesktop } = useBreakpoint()

  const [period, setPeriod] = useState<EquityPeriod>(
    isPeriod(searchParams.get('period')) ? (searchParams.get('period') as EquityPeriod) : '3M',
  )
  const [interval, setInterval] = useState<EquityInterval>(
    isInterval(searchParams.get('interval')) ? (searchParams.get('interval') as EquityInterval) : '1d',
  )
  const [showBenchmark, setShowBenchmark] = useState(true)
  const [showRealized, setShowRealized] = useState(true)
  const [showDrawdown, setShowDrawdown] = useState(true)
  const [percentMode, setPercentMode] = useState(true)
  const [mobileTab, setMobileTab] = useState<MobileTab>('overview')

  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    next.set('period', period)
    next.set('interval', interval)
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, interval])

  const { overview, queries } = useObservatoryData(period, interval)
  const { dashboard, performance, spy, spyAll, autonomous, pipeline } = queries

  const hero = (
    <EquityPanel
      dashboard={dashboard.data}
      analytics={performance.data}
      spy={spy.data}
      isLoadingDashboard={dashboard.isLoading || dashboard.isFetching}
      isLoadingAnalytics={performance.isLoading || performance.isFetching}
      error={dashboard.error ?? performance.error}
      onRetry={() => {
        dashboard.refetch()
        performance.refetch()
      }}
      period={period}
      onPeriodChange={setPeriod}
      interval={interval}
      onIntervalChange={setInterval}
      showBenchmark={showBenchmark}
      onShowBenchmarkChange={setShowBenchmark}
      showRealized={showRealized}
      onShowRealizedChange={setShowRealized}
      showDrawdown={showDrawdown}
      onShowDrawdownChange={setShowDrawdown}
      percentMode={percentMode}
      onPercentModeChange={setPercentMode}
      fullscreen={false}
      onFullscreenToggle={() => {}}
      inceptionSpyBase={spyAll.data?.data?.[0]?.close}
      inceptionEquityBase={spyAll.data?.inception_equity_base ?? undefined}
    />
  )

  const researchZone = (
    <ResearchZone
      autonomousStatus={autonomous.data}
      pipelineCounts={pipeline.counts}
      pipelineLoading={pipeline.isLoading}
      regime={overview.regime}
      regimeConfidence={overview.regimeConfidence}
      regimeDataQuality={overview.regimeDataQuality}
      regimeDescription={overview.regimeDescription}
    />
  )

  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--bg-0)]">
      <FundHeader overview={overview} loading={dashboard.isLoading} />

      {isDesktop ? (
        /* ── Desktop / wall-monitor: main lifecycle column + sticky attention rail ── */
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_360px]">
          <main className="min-h-0 overflow-y-auto">
            <div className="h-[380px] border-b border-[var(--border-subtle)]">{hero}</div>
            <StageSection title="Research" hint="idea generation" accent={STAGE_ACCENT.research}>
              {researchZone}
            </StageSection>
            <StageSection title="Backtest / Walk-forward" hint="statistical validation" accent={STAGE_ACCENT.backtest}>
              <BacktestZone />
            </StageSection>
            <StageSection title="Paper" hint="DEMO · data collection" accent={STAGE_ACCENT.paper}>
              <PaperZone />
            </StageSection>
            <StageSection title="Live" hint="real capital · alpha" accent={STAGE_ACCENT.live}>
              <LiveZone />
            </StageSection>
          </main>
          <aside className="min-h-0 border-l border-[var(--border-default)]">
            <AttentionRail />
          </aside>
        </div>
      ) : (
        /* ── Mobile / tablet: attention-first, then segmented stage nav ── */
        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="border-b border-[var(--border-default)]">
            <AttentionRail showFeeds={false} />
          </div>

          {/* Sticky segmented stage nav */}
          <div className="sticky top-0 z-10 flex gap-1 overflow-x-auto border-b border-[var(--border-default)] bg-[var(--bg-0)] px-2 py-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {MOBILE_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setMobileTab(t.id)}
                className={cn(
                  'shrink-0 rounded-[3px] px-3 py-1.5 text-[11px] font-medium min-h-[36px] transition-colors',
                  mobileTab === t.id
                    ? 'bg-[var(--accent-primary)] text-white'
                    : 'bg-[var(--bg-2)] text-[var(--text-2)] hover:bg-[var(--bg-hover)]',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="p-2">
            {mobileTab === 'overview' && <div className="h-[420px]">{hero}</div>}
            {mobileTab === 'research' && researchZone}
            {mobileTab === 'backtest' && <BacktestZone />}
            {mobileTab === 'paper' && <PaperZone />}
            {mobileTab === 'live' && <LiveZone />}
            {mobileTab === 'activity' && (
              <div className="space-y-2">
                <div className="h-[340px] rounded-[3px] border border-[var(--border-subtle)] overflow-hidden">
                  <PanelHeader title="Signals">
                    <SignalFeed />
                  </PanelHeader>
                </div>
                <div className="h-[340px] rounded-[3px] border border-[var(--border-subtle)] overflow-hidden">
                  <PanelHeader title="Fills · slippage">
                    <OrderFillsTicker />
                  </PanelHeader>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default Observatory
