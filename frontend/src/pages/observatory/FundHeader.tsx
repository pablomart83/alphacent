import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { StatTile } from '@/components/primitives'
import { AccountToggle } from '@/components/trading/AccountToggle'
import { RegimePill, type Regime } from '@/components/trading/RegimePill'
import { WebSocketIndicator } from '@/components/trading/WebSocketIndicator'
import { cn, formatCurrency, formatNumber, formatPercentage } from '@/lib/utils'
import { DataFreshnessIndicator } from './DataFreshnessIndicator'
import type { FundOverview } from './useObservatoryData'

interface FundHeaderProps {
  overview: FundOverview
  loading?: boolean
}

/**
 * Sticky, always-visible fund-level strip — the "attention-first" summary a CIO
 * scans on a wall monitor or a phone. Desktop: a dense wrapping KPI grid.
 * Mobile: the same tiles become a horizontally swipeable chip row (no clipping,
 * touch targets ≥44px). Colour semantics come from the P&L/regime tokens.
 */
export function FundHeader({ overview: o, loading }: FundHeaderProps) {
  const systemHealthy = o.systemState == null || o.systemState.toLowerCase().includes('run')

  return (
    <header className="sticky top-0 z-20 border-b border-[var(--border-default)] bg-[var(--bg-0)]">
      {/* Status bar */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-1.5 border-b border-[var(--border-subtle)]">
        <span className="text-[12px] font-semibold text-[var(--text-0)] tracking-tight">
          Observatory
        </span>
        <span className="text-[10px] text-[var(--text-3)] uppercase tracking-wider hidden sm:inline">
          Fund command center
        </span>
        <div className="flex-1" />
        <RegimePill
          regime={(o.regime ?? 'ranging') as Regime}
          confidence={o.regimeConfidence ?? undefined}
          dataQuality={(o.regimeDataQuality as 'high' | 'medium' | 'low' | undefined) ?? undefined}
          size="sm"
          showConfidence
        />
        <StatusPill healthy={systemHealthy} liveEnabled={o.liveEnabled} />
        <DataFreshnessIndicator
          dataUpdatedAt={o.dataUpdatedAt}
          lastSyncAt={o.lastSyncAt}
          className="hidden md:flex"
        />
        <WebSocketIndicator />
        <AccountToggle size="sm" liveEnabled={o.liveEnabled} />
      </div>

      {/* Freshness on mobile (its own row so the status bar doesn't wrap awkwardly) */}
      <div className="md:hidden px-3 py-1 border-b border-[var(--border-subtle)]">
        <DataFreshnessIndicator dataUpdatedAt={o.dataUpdatedAt} lastSyncAt={o.lastSyncAt} />
      </div>

      {/* KPI tiles: swipeable row on mobile, wrapping grid on desktop */}
      <div
        className={cn(
          'flex gap-2 overflow-x-auto px-3 py-2 snap-x',
          '[scrollbar-width:none] [&::-webkit-scrollbar]:hidden',
          'lg:grid lg:grid-cols-6 lg:overflow-visible xl:grid-cols-12',
        )}
      >
        <Kpi label="NAV (equity)" value={formatCurrency(o.equity ?? 0, { precision: 0 })} loading={loading} />
        <Kpi
          label="Today P&L"
          pnl={{ value: o.todayPnl ?? 0, format: 'currency', precision: 0 }}
          sublabel={o.todayPnlPct != null ? formatPercentage(o.todayPnlPct) : undefined}
          loading={loading}
        />
        <Kpi label="Week" pnl={{ value: o.weekReturnPct ?? 0, format: 'percentage', precision: 2 }} loading={loading} />
        <Kpi label="Month" pnl={{ value: o.monthReturnPct ?? 0, format: 'percentage', precision: 2 }} loading={loading} />
        <Kpi
          label="Alpha vs SPY"
          pnl={{ value: o.alphaVsSpyPct ?? 0, format: 'percentage', precision: 2 }}
          loading={loading}
        />
        <Kpi
          label="Sharpe"
          value={o.sharpe == null ? '—' : formatNumber(o.sharpe, 2)}
          tone={o.sharpe != null && o.sharpe >= 1 ? 'up' : o.sharpe != null && o.sharpe < 0 ? 'down' : 'default'}
          loading={loading}
        />
        <Kpi
          label="Sortino"
          value={o.sortino == null ? '—' : formatNumber(o.sortino, 2)}
          tone={o.sortino != null && o.sortino >= 1 ? 'up' : o.sortino != null && o.sortino < 0 ? 'down' : 'default'}
          loading={loading}
        />
        <Kpi
          label="Cur DD"
          value={o.currentDrawdownPct == null ? '—' : formatPercentage(o.currentDrawdownPct, { precision: 2 })}
          tone="down"
          loading={loading}
        />
        <Kpi
          label="Max DD"
          value={o.maxDrawdownPct == null ? '—' : formatPercentage(o.maxDrawdownPct, { precision: 2 })}
          tone="down"
          loading={loading}
        />
        <Kpi
          label="Gross exp"
          value={o.grossExposurePct == null ? '—' : formatPercentage(o.grossExposurePct, { precision: 0, signed: false })}
          sublabel={o.exposureLimitPct != null ? `of ${o.exposureLimitPct.toFixed(0)}%` : undefined}
          progress={
            o.grossExposurePct != null && o.exposureLimitPct
              ? (o.grossExposurePct / o.exposureLimitPct) * 100
              : undefined
          }
          loading={loading}
        />
        <Kpi
          label="Net exp"
          value={o.netExposurePct == null ? '—' : formatPercentage(o.netExposurePct, { precision: 0 })}
          loading={loading}
        />
        <Kpi
          label="Win rate 30d"
          value={o.winRate30d == null ? '—' : formatPercentage(o.winRate30d, { precision: 1, signed: false })}
          loading={loading}
        />
      </div>
    </header>
  )
}

function Kpi(props: {
  label: string
  value?: React.ReactNode
  pnl?: { value: number; format: 'currency' | 'percentage' | 'decimal'; precision?: number }
  sublabel?: React.ReactNode
  tone?: 'default' | 'up' | 'down' | 'warn' | 'info' | 'muted'
  progress?: number
  loading?: boolean
}) {
  return (
    <StatTile
      className="min-w-[116px] shrink-0 snap-start lg:min-w-0"
      label={props.label}
      value={props.loading ? '…' : props.value}
      pnl={props.loading ? undefined : props.pnl}
      sublabel={props.sublabel}
      tone={props.loading ? 'muted' : props.tone}
      progress={props.progress}
    />
  )
}

function StatusPill({ healthy, liveEnabled }: { healthy: boolean; liveEnabled: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-[2px] px-1.5 py-0.5 text-[10px] font-semibold',
        healthy
          ? 'bg-[color-mix(in_oklab,var(--pnl-up)_14%,transparent)] text-[var(--pnl-up)]'
          : 'bg-[var(--status-error-bg)] text-[var(--status-error)]',
      )}
      title={healthy ? 'System healthy' : 'System attention required'}
    >
      {healthy ? <ShieldCheck className="h-3 w-3" /> : <ShieldAlert className="h-3 w-3" />}
      {healthy ? 'Healthy' : 'Check'}
      <span className="text-[var(--text-3)]">·</span>
      <span className={liveEnabled ? 'text-[var(--pnl-up)]' : 'text-[var(--text-3)]'}>
        {liveEnabled ? 'LIVE on' : 'LIVE off'}
      </span>
    </span>
  )
}
