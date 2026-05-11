import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, FileText } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { cn, formatAge, formatCurrency, formatNumber } from '@/lib/utils'
import type { DashboardSummaryPayload, PerformanceAnalyticsPayload } from './useCommandData'
import type { AutonomousStatusShape } from './CycleStatusCard'
import type { PipelineCounts } from './StrategyPipelineCounts'
import type { LiveSummary } from '@/pages/book/useBookData'

/**
 * DailyBriefingCard — auto-generated text summary of the fund's current state.
 *
 * Collapsible. Generates a 3-4 sentence briefing from existing data:
 *   1. Today's P&L + open positions + win rate.
 *   2. Strategy library state + approaching graduation.
 *   3. Regime + cycle status.
 *   4. Live account status (if enabled).
 *
 * Pure frontend computation — no new endpoints.
 */

interface DailyBriefingCardProps {
  dashboard: DashboardSummaryPayload | undefined
  performance: PerformanceAnalyticsPayload | undefined
  autonomousStatus: AutonomousStatusShape | null | undefined
  pipelineCounts: PipelineCounts
  liveSummary: LiveSummary | undefined
  className?: string
}

export function DailyBriefingCard({
  dashboard,
  performance,
  autonomousStatus,
  pipelineCounts,
  liveSummary,
  className,
}: DailyBriefingCardProps) {
  const [open, setOpen] = useState(false)

  const lines = useMemo(
    () => generateBriefing({ dashboard, performance, autonomousStatus, pipelineCounts, liveSummary }),
    [dashboard, performance, autonomousStatus, pipelineCounts, liveSummary],
  )

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 w-full text-left"
        aria-expanded={open}
      >
        <FileText className="h-3 w-3 text-[var(--text-3)]" />
        <SectionLabel className="mb-0 flex-1">Daily briefing</SectionLabel>
        {open ? (
          <ChevronDown className="h-3 w-3 text-[var(--text-3)]" />
        ) : (
          <ChevronRight className="h-3 w-3 text-[var(--text-3)]" />
        )}
      </button>
      {open && (
        <div className="mt-2 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-1.5">
          {lines.length === 0 ? (
            <p className="text-[11px] text-[var(--text-3)]">
              No data yet — briefing populates once the first cycle runs.
            </p>
          ) : (
            lines.map((line, i) => (
              <p key={i} className="text-[11px] text-[var(--text-1)] leading-[16px]">
                {line}
              </p>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function generateBriefing({
  dashboard,
  performance,
  autonomousStatus,
  pipelineCounts,
  liveSummary,
}: Omit<DailyBriefingCardProps, 'className'>): string[] {
  const lines: string[] = []

  // Line 1 — P&L + positions
  const todayPnl = dashboard?.pnl_periods?.find((p) => p.label === 'Today')
  const openPos = dashboard?.quick_stats?.open_positions
  const winRate = dashboard?.quick_stats?.win_rate_30d
  const sharpe = dashboard?.quick_stats?.sharpe_30d

  if (todayPnl != null || openPos != null) {
    const parts: string[] = []
    if (todayPnl != null) {
      const sign = todayPnl.pnl_absolute >= 0 ? '+' : ''
      parts.push(
        `Today: ${sign}${formatCurrency(todayPnl.pnl_absolute, { precision: 0 })} (${sign}${formatNumber(todayPnl.pnl_percent, 2)}%)`,
      )
    }
    if (openPos != null) parts.push(`${openPos} open positions`)
    if (winRate != null) parts.push(`${formatNumber(winRate, 1)}% win rate (30d)`)
    if (sharpe != null) parts.push(`Sharpe ${formatNumber(sharpe, 2)}`)
    lines.push(parts.join(' · ') + '.')
  }

  // Line 2 — Strategy library
  const { paper, backtested, live } = pipelineCounts
  if (paper + backtested + live > 0) {
    const parts: string[] = []
    if (paper > 0) parts.push(`${paper} PAPER`)
    if (backtested > 0) parts.push(`${backtested} BACKTESTED`)
    if (live > 0) parts.push(`${live} LIVE`)
    lines.push(`Strategy library: ${parts.join(', ')}.`)
  }

  // Line 3 — Regime + cycle
  const regime = autonomousStatus?.market_regime
  const confidence = autonomousStatus?.market_confidence
  const lastCycle = autonomousStatus?.last_cycle_time
  const cycleStats = autonomousStatus?.cycle_stats

  if (regime || lastCycle) {
    const parts: string[] = []
    if (regime) {
      const regimeLabel = regime.replace(/_/g, ' ')
      parts.push(
        `Regime: ${regimeLabel}${confidence != null ? ` (${formatNumber(confidence * 100, 0)}% confidence)` : ''}`,
      )
    }
    if (lastCycle) {
      parts.push(`Last cycle ${formatAge(lastCycle)}`)
      if (cycleStats?.proposals_generated) {
        parts.push(
          `${cycleStats.proposals_generated} proposed → ${cycleStats.activated ?? 0} activated`,
        )
      }
    }
    lines.push(parts.join(' · ') + '.')
  }

  // Line 4 — Live account (only if enabled)
  if (liveSummary?.live_enabled) {
    const livePos = liveSummary.open_positions
    const liveReal = liveSummary.real_equity
    const liveTodayReal = liveSummary.today_pnl_real
    const parts: string[] = [`Live account ON`]
    if (liveReal != null) parts.push(`real equity ${formatCurrency(liveReal, { precision: 0 })}`)
    if (livePos != null) parts.push(`${livePos} live positions`)
    if (liveTodayReal != null) {
      const sign = liveTodayReal >= 0 ? '+' : ''
      parts.push(`today ${sign}${formatCurrency(liveTodayReal, { precision: 0 })} real`)
    }
    lines.push(parts.join(' · ') + '.')
  } else if (liveSummary?.live_enabled === false) {
    lines.push('Live trading is OFF — all fills are paper only.')
  }

  // Line 5 — Performance summary (30d)
  if (performance) {
    const ret = performance.total_return
    const maxDD = performance.max_drawdown
    const pf = performance.profit_factor
    if (ret != null || maxDD != null) {
      const parts: string[] = []
      if (ret != null) parts.push(`${ret >= 0 ? '+' : ''}${formatNumber(ret, 2)}% total return`)
      if (maxDD != null) parts.push(`max DD −${formatNumber(maxDD, 1)}%`)
      if (pf != null) parts.push(`profit factor ${formatNumber(pf, 2)}`)
      lines.push(`Period: ${parts.join(' · ')}.`)
    }
  }

  return lines
}
