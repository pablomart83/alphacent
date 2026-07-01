import { ShieldAlert, ShieldCheck } from 'lucide-react'
import { StatTile } from '@/components/primitives'
import { AccountToggle } from '@/components/trading/AccountToggle'
import { RegimePill } from '@/components/trading/RegimePill'
import { WebSocketIndicator } from '@/components/trading/WebSocketIndicator'
import { cn, formatCurrency, formatNumber, formatPercentage } from '@/lib/utils'
import type { TradingMode } from '@/stores'
import { DataFreshnessIndicator } from './DataFreshnessIndicator'
import { Sparkline } from './Sparkline'
import type { AccountSplit, FundOverview } from './useObservatoryData'

interface FundHeaderProps {
  overview: FundOverview
  split: AccountSplit
  mode: TradingMode
  loading?: boolean
}

/**
 * Compact, fixed-height fund ribbon. Account context is explicit: a DEMO|LIVE
 * toggle, a "<mode> view" tag on the KPI row, and an always-visible DEMO vs LIVE
 * NAV split so a percentage is never ambiguous.
 */
export function FundHeader({ overview: o, split, mode, loading }: FundHeaderProps) {
  const healthy = o.systemState == null || o.systemState.toLowerCase().includes('run')
  const accountColor = mode === 'LIVE' ? 'var(--account-live)' : 'var(--account-demo)'

  return (
    <header className="shrink-0 border-b border-[var(--border-default)] bg-[var(--bg-0)]">
      {/* Status line */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1.5">
        <span className="text-[12px] font-semibold tracking-tight text-[var(--text-0)]">Observatory</span>
        <AccountToggle size="sm" liveEnabled={o.liveEnabled} />
        <div className="flex-1" />
        <RegimePill regime={o.regime} confidence={o.regimeConfidence ?? undefined} size="sm" showConfidence />
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
        </span>
        <DataFreshnessIndicator dataUpdatedAt={o.dataUpdatedAt} lastSyncAt={o.lastSyncAt} className="hidden sm:flex" />
        <WebSocketIndicator />
      </div>

      {/* Ribbon: account split · KPI chips · sparkline */}
      <div className="flex items-stretch gap-2 border-t border-[var(--border-subtle)] px-3 py-2">
        {/* DEMO vs LIVE split — always both, unambiguous */}
        <div className="hidden shrink-0 gap-1.5 md:flex">
          <SplitCard
            tag="DEMO"
            tagColor="var(--account-demo)"
            nav={split.demoEquity}
            subLabel={`${split.demoOpenPositions ?? 0} pos`}
            active={mode === 'DEMO'}
          />
          <SplitCard
            tag={`LIVE ${split.liveEnabled ? '●' : '○'}`}
            tagColor={split.liveEnabled ? 'var(--pnl-up)' : 'var(--text-3)'}
            nav={split.liveVirtualEquity}
            subLabel={split.liveRealEquity != null ? `real ${formatCurrency(split.liveRealEquity, { compact: true, precision: 0 })}` : '—'}
            active={mode === 'LIVE'}
          />
        </div>

        {/* KPI chips (active account) */}
        <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <span
            className="shrink-0 rounded-[2px] px-1.5 py-1 text-[9px] font-bold uppercase tracking-wider"
            style={{ color: accountColor, background: `color-mix(in oklab, ${accountColor} 14%, transparent)` }}
            title="KPIs below reflect this account"
          >
            {mode} view
          </span>
          <Chip label="NAV" value={formatCurrency(o.equity ?? 0, { precision: 0 })} loading={loading} />
          <Chip label="Today" pnl={{ v: o.todayPnl, fmt: 'currency' }} sub={o.todayPnlPct != null ? formatPercentage(o.todayPnlPct) : undefined} loading={loading} />
          <Chip label="Week" pnl={{ v: o.weekReturnPct, fmt: 'percentage' }} loading={loading} />
          <Chip label="Month" pnl={{ v: o.monthReturnPct, fmt: 'percentage' }} loading={loading} />
          <Chip label="All-time" pnl={{ v: o.allTimeReturnPct, fmt: 'percentage' }} loading={loading} />
          <Chip label="Alpha/SPY" pnl={{ v: o.alphaVsSpyPct, fmt: 'percentage' }} loading={loading} />
          <Chip label="Sharpe" value={o.sharpe == null ? '—' : formatNumber(o.sharpe, 2)} tone={o.sharpe != null && o.sharpe >= 1 ? 'up' : o.sharpe != null && o.sharpe < 0 ? 'down' : 'default'} loading={loading} />
          <Chip label="Sortino" value={o.sortino == null ? '—' : formatNumber(o.sortino, 2)} loading={loading} />
          <Chip label="Cur DD" value={o.currentDrawdownPct == null ? '—' : formatPercentage(o.currentDrawdownPct, { precision: 1 })} tone="down" loading={loading} />
          <Chip label="Max DD" value={o.maxDrawdownPct == null ? '—' : formatPercentage(o.maxDrawdownPct, { precision: 1 })} tone="down" loading={loading} />
          <Chip
            label="Gross exp"
            value={o.grossExposurePct == null ? '—' : formatPercentage(o.grossExposurePct, { precision: 0, signed: false })}
            sub={o.exposureLimitPct != null ? `/ ${o.exposureLimitPct.toFixed(0)}%` : undefined}
            loading={loading}
          />
          <Chip label="Win 30d" value={o.winRate30d == null ? '—' : formatPercentage(o.winRate30d, { precision: 0, signed: false })} loading={loading} />
        </div>

        {/* Equity trend */}
        <div className="hidden shrink-0 flex-col justify-center pl-1 xl:flex">
          <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">Equity trend</span>
          <Sparkline data={o.equitySeries} />
        </div>
      </div>
    </header>
  )
}

function SplitCard({
  tag,
  tagColor,
  nav,
  subLabel,
  active,
}: {
  tag: string
  tagColor: string
  nav: number | null
  subLabel: string
  active: boolean
}) {
  return (
    <div
      className={cn(
        'flex w-[104px] flex-col justify-center rounded-[3px] border px-2 py-1',
        active ? 'border-[var(--border-strong)] bg-[var(--bg-2)]' : 'border-[var(--border-subtle)] bg-[var(--bg-1)]',
      )}
    >
      <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: tagColor }}>{tag}</span>
      <span className="mono tabular-nums text-[13px] font-bold text-[var(--text-0)]">
        {nav == null ? '—' : formatCurrency(nav, { precision: 0 })}
      </span>
      <span className="text-[9px] text-[var(--text-3)] mono">{subLabel}</span>
    </div>
  )
}

function Chip(props: {
  label: string
  value?: React.ReactNode
  pnl?: { v: number | null; fmt: 'currency' | 'percentage' }
  sub?: React.ReactNode
  tone?: 'default' | 'up' | 'down'
  loading?: boolean
}) {
  return (
    <StatTile
      className="min-w-[84px] shrink-0 !p-1.5"
      size="sm"
      label={props.label}
      value={props.loading ? '…' : props.value}
      pnl={props.loading || !props.pnl ? undefined : { value: props.pnl.v ?? 0, format: props.pnl.fmt, precision: props.pnl.fmt === 'currency' ? 0 : 2 }}
      sublabel={props.sub}
      tone={props.loading ? 'muted' : props.tone}
    />
  )
}
