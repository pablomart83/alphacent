import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { useBreakpoint } from '@/hooks/useBreakpoint'
import type { EquityInterval, EquityPeriod } from '@/components/trading/EquityChart'
import { useObservatoryData } from './useObservatoryData'
import { FundHeader } from './FundHeader'
import { Panel } from './Panel'
import { AlertsPanel } from './AlertsPanel'
import { ResearchZone } from './zones/ResearchZone'
import { BacktestZone } from './zones/BacktestZone'
import { PaperZone } from './zones/PaperZone'
import { LiveZone } from './zones/LiveZone'

const PERIOD_SET: EquityPeriod[] = ['1W', '1M', '3M', '6M', '1Y', 'ALL']
const INTERVAL_SET: EquityInterval[] = ['1d', '4h', '1h']
const isPeriod = (v: string | null): v is EquityPeriod => !!v && (PERIOD_SET as string[]).includes(v)
const isInterval = (v: string | null): v is EquityInterval => !!v && (INTERVAL_SET as string[]).includes(v)

type MobileTab = 'live' | 'alerts' | 'paper' | 'research' | 'backtest'
const MOBILE_TABS: { id: MobileTab; label: string }[] = [
  { id: 'live', label: 'Live' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'paper', label: 'Paper' },
  { id: 'research', label: 'Research' },
  { id: 'backtest', label: 'Backtest' },
]

const ACCENT = {
  research: 'var(--accent-secondary)',
  backtest: 'var(--accent-primary)',
  paper: 'var(--account-demo)',
  live: 'var(--account-live)',
  alerts: 'var(--status-warning)',
} as const

export function Observatory() {
  const [searchParams] = useSearchParams()
  const { isDesktop } = useBreakpoint()
  const [mobileTab, setMobileTab] = useState<MobileTab>('live')

  // Period/interval only feed the analytics window (Sharpe/returns); no chart here.
  const period: EquityPeriod = isPeriod(searchParams.get('period')) ? (searchParams.get('period') as EquityPeriod) : '3M'
  const interval: EquityInterval = isInterval(searchParams.get('interval')) ? (searchParams.get('interval') as EquityInterval) : '1d'

  const { overview, split, mode, queries } = useObservatoryData(period, interval)
  const { dashboard, autonomous, pipeline } = queries

  useEffect(() => {
    document.title = 'Observatory · AlphaCent'
  }, [])

  const researchContent = (
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
  const alertsContent = (
    <AlertsPanel dataUpdatedAt={overview.dataUpdatedAt} lastSyncAt={overview.lastSyncAt} systemState={overview.systemState} />
  )

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--bg-0)]">
      <FundHeader overview={overview} split={split} mode={mode} loading={dashboard.isLoading} />

      {isDesktop ? (
        /* Fitted command board — the PAGE does not scroll; panels scroll internally. */
        <div className="grid min-h-0 flex-1 grid-cols-3 grid-rows-[minmax(0,3fr)_minmax(0,2fr)] gap-2 overflow-hidden p-2">
          <Panel title="Live · real capital" accent={ACCENT.live} className="col-span-2" badge={<AccountBadge mode="LIVE" />}>
            <LiveZone />
          </Panel>
          <Panel title="Alerts" accent={ACCENT.alerts}>
            {alertsContent}
          </Panel>
          <Panel title="Research · pipeline" accent={ACCENT.research}>
            {researchContent}
          </Panel>
          <Panel title="Backtest / walk-forward" accent={ACCENT.backtest}>
            <BacktestZone />
          </Panel>
          <Panel title="Paper · data collection" accent={ACCENT.paper} badge={<AccountBadge mode="DEMO" />}>
            <PaperZone />
          </Panel>
        </div>
      ) : (
        /* Mobile: sticky segmented tabs, attention-first (Live, Alerts first). */
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div className="flex shrink-0 gap-1 overflow-x-auto border-b border-[var(--border-default)] bg-[var(--bg-0)] px-2 py-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {MOBILE_TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setMobileTab(t.id)}
                className={cn(
                  'min-h-[38px] shrink-0 rounded-[3px] px-3 text-[11px] font-medium transition-colors',
                  mobileTab === t.id ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--bg-2)] text-[var(--text-2)]',
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {mobileTab === 'live' && <LiveZone />}
            {mobileTab === 'alerts' && alertsContent}
            {mobileTab === 'paper' && <PaperZone />}
            {mobileTab === 'research' && researchContent}
            {mobileTab === 'backtest' && <BacktestZone />}
          </div>
        </div>
      )}
    </div>
  )
}

function AccountBadge({ mode }: { mode: 'LIVE' | 'DEMO' }) {
  const color = mode === 'LIVE' ? 'var(--account-live)' : 'var(--account-demo)'
  return (
    <span
      className="rounded-[2px] px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
      style={{ color, background: `color-mix(in oklab, ${color} 14%, transparent)` }}
    >
      {mode}
    </span>
  )
}

export default Observatory
