import { MetricGrid, SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { formatNumber, formatPercentage, formatCurrency, cn } from '@/lib/utils'
import type { PerformanceAnalyticsPayload, SpyBenchmarkPoint } from '../useResearchData'

interface PerformanceTilesProps {
  data: PerformanceAnalyticsPayload | undefined
  loading: boolean
  spyData?: SpyBenchmarkPoint[]
}

interface Tile {
  label: string
  value: string
  tone: 'up' | 'down' | 'neutral' | 'warn'
  hint?: string
}

function toneColor(tone: Tile['tone']): string {
  switch (tone) {
    case 'up':
      return 'var(--pnl-up)'
    case 'down':
      return 'var(--pnl-down)'
    case 'warn':
      return 'var(--status-warning)'
    default:
      return 'var(--text-0)'
  }
}

export function PerformanceTiles({ data, loading, spyData }: PerformanceTilesProps) {
  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Headline metrics</SectionLabel>
        <MetricGrid cols={8}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} variant="metric-tile" />
          ))}
        </MetricGrid>
      </section>
    )
  }

  const totalReturn = data?.total_return ?? 0
  const totalReturnDollars = data?.total_return_dollars ?? null
  const realizedReturn = data?.realized_return ?? null
  const realizedDollars = data?.realized_return_dollars ?? null
  const sharpe = data?.sharpe_ratio ?? 0
  const sortino = data?.sortino_ratio ?? 0
  const maxDD = data?.max_drawdown ?? 0
  const winRate = data?.win_rate ?? 0
  const pf = data?.profit_factor ?? 0
  const drc = data?.daily_returns_count ?? 0
  const totalTrades = data?.total_trades ?? 0

  // Alpha vs SPY: prefer server-computed value, fall back to client-side from spyData
  let spyReturn: number | null = data?.spy_return ?? null
  let alpha: number | null = data?.alpha_vs_spy ?? null
  if ((spyReturn == null || alpha == null) && spyData && spyData.length >= 2) {
    const first = spyData[0].close
    const last = spyData[spyData.length - 1].close
    if (first > 0) {
      spyReturn = ((last - first) / first) * 100
      alpha = totalReturn - spyReturn
    }
  }

  const fmtDollar = (v: number | null) =>
    v != null ? `${v >= 0 ? '+' : ''}${formatCurrency(v, { precision: 0 })}` : undefined

  const tiles: Tile[] = [
    {
      label: 'Total return',
      value: formatPercentage(totalReturn),
      tone: totalReturn > 0 ? 'up' : totalReturn < 0 ? 'down' : 'neutral',
      hint: fmtDollar(totalReturnDollars),
    },
    {
      label: 'Realised P&L',
      value: realizedReturn != null ? formatPercentage(realizedReturn) : '—',
      tone: realizedReturn == null ? 'neutral' : realizedReturn > 0 ? 'up' : realizedReturn < 0 ? 'down' : 'neutral',
      hint: fmtDollar(realizedDollars) ?? 'Closed-trade P&L only',
    },
    {
      label: 'Alpha vs SPY',
      value: alpha != null ? `${alpha >= 0 ? '+' : ''}${formatNumber(alpha, 2)}%` : '—',
      tone: alpha == null ? 'neutral' : alpha > 0 ? 'up' : alpha < 0 ? 'down' : 'neutral',
      hint: spyReturn != null ? `SPY ${spyReturn >= 0 ? '+' : ''}${formatNumber(spyReturn, 2)}%` : undefined,
    },
    {
      label: 'Sharpe (ann.)',
      value: formatNumber(sharpe, 2),
      tone: sharpe >= 1 ? 'up' : sharpe >= 0 ? 'neutral' : 'down',
      hint: drc < 30 ? 'Sample < 30d — provisional' : undefined,
    },
    {
      label: 'Sortino (ann.)',
      value: formatNumber(sortino, 2),
      tone: sortino >= 1 ? 'up' : sortino >= 0 ? 'neutral' : 'down',
    },
    {
      label: 'Max drawdown',
      value: `−${formatNumber(maxDD, 2)}%`,
      tone: maxDD > 15 ? 'down' : maxDD > 8 ? 'warn' : 'neutral',
    },
    {
      label: 'Win rate',
      value: `${formatNumber(winRate, 1)}%`,
      tone: winRate >= 55 ? 'up' : winRate >= 45 ? 'neutral' : 'down',
    },
    {
      label: 'Profit factor',
      value: formatNumber(pf, 2),
      tone: pf >= 1.5 ? 'up' : pf >= 1 ? 'neutral' : 'down',
    },
    {
      label: 'Daily returns',
      value: formatNumber(drc, 0),
      tone: 'neutral',
      hint: `${formatNumber(totalTrades, 0)} trades`,
    },
  ]

  return (
    <section className="space-y-1.5">
      <SectionLabel>Headline metrics</SectionLabel>
      <MetricGrid cols={8}>
        {tiles.map((t) => (
          <Tile key={t.label} {...t} />
        ))}
      </MetricGrid>
    </section>
  )
}

function Tile({ label, value, tone, hint }: Tile) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2.5 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </div>
      <div
        className={cn('mt-0.5 text-[15px] font-semibold mono tabular-nums leading-none')}
        style={{ color: toneColor(tone) }}
      >
        {value}
      </div>
      {hint && (
        <div className="mt-1 text-[9px] text-[var(--text-3)] truncate">{hint}</div>
      )}
    </div>
  )
}
