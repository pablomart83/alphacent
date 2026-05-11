import { useNavigate } from 'react-router-dom'
import { SectionLabel } from '@/components/layout'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import type { DashboardSummaryPayload } from './useCommandData'
import type { LiveSummary } from '@/pages/book/useBookData'

/**
 * DemoLiveSplitTile — side-by-side DEMO and LIVE account summary.
 *
 * DEMO: equity, open positions, win rate 30d, unrealized P&L.
 * LIVE: virtual equity, real equity, live positions, today's real P&L.
 *
 * Clicking DEMO navigates to Book/Positions (DEMO).
 * Clicking LIVE navigates to Book/Live.
 */

interface DemoLiveSplitTileProps {
  dashboard: DashboardSummaryPayload | undefined
  liveSummary: LiveSummary | undefined
  loading?: boolean
  className?: string
}

export function DemoLiveSplitTile({
  dashboard,
  liveSummary,
  loading,
  className,
}: DemoLiveSplitTileProps) {
  const navigate = useNavigate()

  const demoEquity = dashboard?.account_equity
  const demoPositions = dashboard?.quick_stats?.open_positions
  const demoWinRate = dashboard?.quick_stats?.win_rate_30d
  const demoUnrealized = dashboard?.total_unrealized_pnl

  const liveVirtual = liveSummary?.virtual_equity
  const liveReal = liveSummary?.real_equity
  const livePositions = liveSummary?.open_positions
  const liveTodayReal = liveSummary?.today_pnl_real
  const liveEnabled = liveSummary?.live_enabled ?? false

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Accounts</SectionLabel>
      <div className="grid grid-cols-2 gap-1.5">
        {/* DEMO */}
        <button
          type="button"
          onClick={() => navigate('/book/positions')}
          className="text-left rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 hover:bg-[var(--bg-hover)] transition-colors space-y-1.5"
        >
          <div className="flex items-center justify-between">
            <span className="text-[9px] uppercase tracking-wider font-semibold text-[var(--accent-secondary)]">
              DEMO
            </span>
            <span className="text-[9px] text-[var(--text-3)] mono">
              {loading ? '…' : `${demoPositions ?? 0} pos`}
            </span>
          </div>
          <div className="mono tabular-nums text-[13px] font-bold text-[var(--text-0)]">
            {loading ? '…' : formatCurrency(demoEquity ?? 0, { precision: 0 })}
          </div>
          <div className="grid grid-cols-2 gap-x-1 text-[9px]">
            <Stat label="WR 30d" value={demoWinRate != null ? `${formatNumber(demoWinRate, 1)}%` : '—'} />
            <Stat
              label="Unrealized"
              value={demoUnrealized != null ? formatCurrency(demoUnrealized, { signed: true, precision: 0 }) : '—'}
              tone={demoUnrealized != null && demoUnrealized > 0 ? 'up' : demoUnrealized != null && demoUnrealized < 0 ? 'down' : 'neutral'}
            />
          </div>
        </button>

        {/* LIVE */}
        <button
          type="button"
          onClick={() => navigate('/book/live')}
          className={cn(
            'text-left rounded-[3px] border p-2 hover:bg-[var(--bg-hover)] transition-colors space-y-1.5',
            liveEnabled
              ? 'border-[color-mix(in_oklab,var(--pnl-up)_30%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--pnl-up)_4%,var(--bg-1))]'
              : 'border-[var(--border-subtle)] bg-[var(--bg-1)]',
          )}
        >
          <div className="flex items-center justify-between">
            <span
              className={cn(
                'text-[9px] uppercase tracking-wider font-semibold',
                liveEnabled ? 'text-[var(--pnl-up)]' : 'text-[var(--text-3)]',
              )}
            >
              LIVE {liveEnabled ? '●' : '○'}
            </span>
            <span className="text-[9px] text-[var(--text-3)] mono">
              {loading ? '…' : `${livePositions ?? 0} pos`}
            </span>
          </div>
          <div className="mono tabular-nums text-[13px] font-bold text-[var(--text-0)]">
            {loading ? '…' : formatCurrency(liveVirtual ?? 0, { precision: 0 })}
          </div>
          <div className="grid grid-cols-2 gap-x-1 text-[9px]">
            <Stat
              label="Real"
              value={liveReal != null ? formatCurrency(liveReal, { precision: 0 }) : '—'}
            />
            <Stat
              label="Today"
              value={liveTodayReal != null ? formatCurrency(liveTodayReal, { signed: true, precision: 0 }) : '—'}
              tone={liveTodayReal != null && liveTodayReal > 0 ? 'up' : liveTodayReal != null && liveTodayReal < 0 ? 'down' : 'neutral'}
            />
          </div>
        </button>
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div>
      <div className="text-[var(--text-3)] uppercase tracking-wider">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[10px] font-medium',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-1)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}
