import { useNavigate } from 'react-router-dom'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber, formatPercentage } from '@/lib/utils'
import type { PerformanceAnalyticsPayload } from './useCommandData'

/**
 * FundScorecardCard — six key fund metrics in a 2×3 grid.
 *
 * Replaces the old HealthScoreCard (which was a single 0-100 composite
 * score that obscured the underlying numbers). A CIO wants to see the
 * actual Sharpe, Sortino, max DD, win rate, profit factor, and alpha vs
 * SPY — not a single opaque score.
 *
 * Clicking any metric navigates to Research/Performance for the full
 * analytics view.
 */

interface FundScorecardCardProps {
  performance: PerformanceAnalyticsPayload | undefined
  loading?: boolean
  className?: string
}

interface Metric {
  label: string
  value: string
  tone: 'up' | 'down' | 'warn' | 'neutral'
  hint?: string
}

function tone(
  v: number | null | undefined,
  goodAbove?: number,
  badBelow?: number,
): 'up' | 'down' | 'warn' | 'neutral' {
  if (v == null) return 'neutral'
  if (goodAbove != null && v >= goodAbove) return 'up'
  if (badBelow != null && v < badBelow) return 'down'
  return 'warn'
}

export function FundScorecardCard({ performance, loading, className }: FundScorecardCardProps) {
  const navigate = useNavigate()

  const sharpe = performance?.sharpe_ratio
  const sortino = performance?.sortino_ratio
  const maxDD = performance?.max_drawdown
  const winRate = performance?.win_rate
  const pf = performance?.profit_factor
  const totalReturn = performance?.total_return

  const metrics: Metric[] = [
    {
      label: 'Sharpe (ann.)',
      value: sharpe != null ? formatNumber(sharpe, 2) : '—',
      tone: tone(sharpe, 1.0, 0),
      hint: 'Risk-adjusted return (annualised)',
    },
    {
      label: 'Sortino',
      value: sortino != null ? formatNumber(sortino, 2) : '—',
      tone: tone(sortino, 1.0, 0),
      hint: 'Downside-only risk-adjusted return',
    },
    {
      label: 'Max DD',
      value: maxDD != null ? `−${formatNumber(maxDD, 1)}%` : '—',
      tone: maxDD != null && maxDD > 15 ? 'down' : maxDD != null && maxDD > 8 ? 'warn' : 'neutral',
      hint: 'Peak-to-trough drawdown in selected period',
    },
    {
      label: 'Win rate',
      value: winRate != null ? `${formatNumber(winRate, 1)}%` : '—',
      tone: tone(winRate, 55, 45),
      hint: '% of closed trades that were profitable',
    },
    {
      label: 'Profit factor',
      value: pf != null ? formatNumber(pf, 2) : '—',
      tone: tone(pf, 1.5, 1.0),
      hint: 'Gross profit / gross loss',
    },
    {
      label: 'Total return',
      value: totalReturn != null ? formatPercentage(totalReturn) : '—',
      tone: totalReturn != null && totalReturn > 0 ? 'up' : totalReturn != null && totalReturn < 0 ? 'down' : 'neutral',
      hint: 'Cumulative return in selected period',
    },
  ]

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Fund scorecard</SectionLabel>
      <button
        type="button"
        onClick={() => navigate('/research/performance')}
        className="w-full text-left rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 hover:bg-[var(--bg-hover)] transition-colors"
        title="Open Research / Performance"
      >
        <div className="grid grid-cols-3 gap-1.5">
          {metrics.map((m) => (
            <MetricCell key={m.label} metric={m} loading={loading} />
          ))}
        </div>
      </button>
    </div>
  )
}

function MetricCell({ metric, loading }: { metric: Metric; loading?: boolean }) {
  const color =
    metric.tone === 'up'
      ? 'var(--pnl-up)'
      : metric.tone === 'down'
        ? 'var(--pnl-down)'
        : metric.tone === 'warn'
          ? 'var(--status-warning)'
          : 'var(--text-0)'

  return (
    <div className="flex flex-col gap-0.5" title={metric.hint}>
      <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] truncate">
        {metric.label}
      </span>
      <span
        className="mono tabular-nums text-[12px] font-semibold"
        style={{ color: loading ? 'var(--text-3)' : color }}
      >
        {loading ? '…' : metric.value}
      </span>
    </div>
  )
}
