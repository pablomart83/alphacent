import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Play, RefreshCw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { PageTemplate, ResizablePanelLayout } from '@/components/layout'
import { Button, EmptyState } from '@/components/primitives'
import { PulsePanel } from './PulsePanel'
import { EquityPanel } from './EquityPanel'
import { StreamPanel } from './StreamPanel'
import {
  useAutonomousStatus,
  useDashboardSummary,
  useLiveSummary,
  usePerformanceAnalytics,
  usePipelineCounts,
  useSpyBenchmark,
} from './useCommandData'
import type {
  EquityInterval,
  EquityPeriod,
} from '@/components/trading/EquityChart'
import { useTradingMode } from '@/stores'

const PERIOD_SET: EquityPeriod[] = ['1W', '1M', '3M', '6M', '1Y', 'ALL']
const INTERVAL_SET: EquityInterval[] = ['1d', '4h', '1h']

function isPeriod(v: string | null): v is EquityPeriod {
  return !!v && (PERIOD_SET as string[]).includes(v)
}

function isInterval(v: string | null): v is EquityInterval {
  return !!v && (INTERVAL_SET as string[]).includes(v)
}

export function Command() {
  const [searchParams, setSearchParams] = useSearchParams()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)

  const periodFromUrl = searchParams.get('period')
  const intervalFromUrl = searchParams.get('interval')
  const [period, setPeriod] = useState<EquityPeriod>(
    isPeriod(periodFromUrl) ? periodFromUrl : '3M',
  )
  const [interval, setInterval] = useState<EquityInterval>(
    isInterval(intervalFromUrl) ? intervalFromUrl : '1d',
  )

  const [showBenchmark, setShowBenchmark] = useState(true)
  const [showRealized, setShowRealized] = useState(true)
  const [showDrawdown, setShowDrawdown] = useState(true)
  const [percentMode, setPercentMode] = useState(true)
  const [fullscreen, setFullscreen] = useState(false)

  // Persist period/interval in URL so deep-linking + refresh preserve view.
  useEffect(() => {
    const next = new URLSearchParams(searchParams)
    next.set('period', period)
    next.set('interval', interval)
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [period, interval])

  /* ── Data ── */
  const dashboardQuery = useDashboardSummary(interval)
  const performanceQuery = usePerformanceAnalytics(period, interval)
  const spyQuery = useSpyBenchmark(period, showBenchmark)
  // ALL-period spy fetch for inception-based alpha calculation in the hover legend.
  // Always enabled (not gated on showBenchmark) so the inception base is available
  // even when the benchmark line is hidden. Stale time is long — this rarely changes.
  const spyAllQuery = useSpyBenchmark('ALL', true)
  const autonomousQuery = useAutonomousStatus()
  const liveSummaryQuery = useLiveSummary()

  const latestProposals =
    autonomousQuery.data?.cycle_stats?.proposals_generated ?? undefined
  const pipelineQuery = usePipelineCounts(latestProposals)

  const dashboard = dashboardQuery.data
  const performance = performanceQuery.data

  const quickStats = dashboard?.quick_stats
  const liveEnabled = Boolean(liveSummaryQuery.data?.live_enabled)
  const liveAuths = liveSummaryQuery.data?.active_live_authorizations ?? 0

  const todayPeriod = useMemo(
    () => dashboard?.pnl_periods?.find((p) => p.label === 'Today'),
    [dashboard?.pnl_periods],
  )

  const isEmptyState =
    !dashboardQuery.isLoading &&
    !performanceQuery.isLoading &&
    (quickStats?.active_strategies ?? 0) === 0 &&
    (quickStats?.open_positions ?? 0) === 0 &&
    pipelineQuery.counts.paper === 0 &&
    pipelineQuery.counts.live === 0

  const handleRefresh = useCallback(() => {
    qc.invalidateQueries({ queryKey: ['dashboard'] })
    qc.invalidateQueries({ queryKey: ['analytics-performance'] })
    qc.invalidateQueries({ queryKey: ['spy-benchmark'] })
    qc.invalidateQueries({ queryKey: ['autonomous-status'] })
    qc.invalidateQueries({ queryKey: ['live-summary'] })
    qc.invalidateQueries({ queryKey: ['strategies'] })
    qc.invalidateQueries({ queryKey: ['recent-signals'] })
    qc.invalidateQueries({ queryKey: ['orders'] })
    qc.invalidateQueries({ queryKey: ['dashboard-strategy-alerts'] })
  }, [qc])

  /* ── Page-local shortcuts ── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const inField =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      if (inField || e.metaKey || e.ctrlKey || e.altKey) return
      const key = e.key.toLowerCase()
      switch (key) {
        case 'f':
          e.preventDefault()
          setFullscreen((v) => !v)
          return
        case 'b':
          e.preventDefault()
          setShowBenchmark((v) => !v)
          return
        case '1':
          e.preventDefault()
          setPeriod('1W')
          return
        case '2':
          e.preventDefault()
          setPeriod('1M')
          return
        case '3':
          e.preventDefault()
          setPeriod('3M')
          return
        case '4':
          e.preventDefault()
          setPeriod('6M')
          return
        case '5':
          e.preventDefault()
          setPeriod('1Y')
          return
        case '6':
          e.preventDefault()
          setPeriod('ALL')
          return
        case 'd':
          e.preventDefault()
          setInterval('1d')
          return
        case 'h':
          e.preventDefault()
          setInterval('1h')
          return
        case 'q':
          e.preventDefault()
          setInterval('4h')
          return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  /* ── Render ── */
  const modeLabel = `${mode} · ${liveEnabled ? 'Live on' : 'Live off'}`

  const equityPanel = (
    <EquityPanel
      dashboard={dashboard}
      analytics={performance}
      spy={spyQuery.data}
      isLoadingDashboard={dashboardQuery.isLoading || dashboardQuery.isFetching}
      isLoadingAnalytics={performanceQuery.isLoading || performanceQuery.isFetching}
      error={dashboardQuery.error ?? performanceQuery.error}
      onRetry={() => {
        dashboardQuery.refetch()
        performanceQuery.refetch()
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
      fullscreen={fullscreen}
      onFullscreenToggle={() => setFullscreen((v) => !v)}
      inceptionSpyBase={spyAllQuery.data?.data?.[0]?.close}
      inceptionEquityBase={spyAllQuery.data?.inception_equity_base ?? undefined}
    />
  )

  return (
    <PageTemplate
      title="Command"
      description={modeLabel}
      actions={
        <Button
          variant="ghost"
          size="sm"
          onClick={handleRefresh}
          aria-label="Refresh all data"
          className="gap-1.5"
          title="Refresh"
        >
          <RefreshCw className="h-3 w-3" />
          Refresh
        </Button>
      }
    >
      {fullscreen ? (
        <div className="h-full">{equityPanel}</div>
      ) : (
        <ResizablePanelLayout
          layoutId="command"
          panels={[
            {
              id: 'pulse',
              defaultSize: 25,
              minSize: 18,
              maxSize: 35,
              content: (
                <PulsePanel
                  equity={dashboard?.account_equity}
                  todayPnl={todayPeriod?.pnl_absolute}
                  todayPnlPct={todayPeriod?.pnl_percent}
                  unrealizedPnl={dashboard?.total_unrealized_pnl}
                  availableCash={dashboard?.available_cash}
                  winRate30d={quickStats?.win_rate_30d}
                  sharpe30d={quickStats?.sharpe_30d}
                  maxDrawdown={
                    performance?.max_drawdown != null
                      ? -Math.abs(performance.max_drawdown)
                      : undefined
                  }
                  liveEnabled={liveEnabled}
                  liveAuthorisations={liveAuths}
                  pnlPeriods={dashboard?.pnl_periods}
                  chartPeriod={period}
                  onChartPeriodChange={setPeriod}
                  regime={dashboard?.market_regime?.current_regime}
                  regimeConfidence={autonomousQuery.data?.market_confidence}
                  regimeDataQuality={autonomousQuery.data?.data_quality}
                  regimeDescription={dashboard?.market_regime?.regime_description}
                  autonomousStatus={autonomousQuery.data}
                  pipelineCounts={pipelineQuery.counts}
                  pipelineLoading={pipelineQuery.isLoading}
                  dashboard={dashboard}
                  performance={performance}
                  liveSummary={liveSummaryQuery.data}
                  dashboardLoading={dashboardQuery.isLoading || dashboardQuery.isFetching}
                  performanceLoading={performanceQuery.isLoading || performanceQuery.isFetching}
                />
              ),
            },
            {
              id: 'equity',
              defaultSize: 50,
              minSize: 30,
              content: isEmptyState ? (
                <div className="h-full flex items-center justify-center">
                  <EmptyState
                    icon={Play}
                    title="No active strategies yet"
                    description="The library is empty and no positions are open. Kick off the first autonomous cycle to seed proposals."
                    action={
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => navigate('/strategies/cycle')}
                      >
                        Go to Cycle
                      </Button>
                    }
                  />
                </div>
              ) : (
                equityPanel
              ),
            },
            {
              id: 'stream',
              defaultSize: 25,
              minSize: 18,
              maxSize: 35,
              content: <StreamPanel />,
            },
          ]}
        />
      )}
    </PageTemplate>
  )
}
