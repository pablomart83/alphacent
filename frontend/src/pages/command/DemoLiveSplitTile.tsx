import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { SectionLabel } from '@/components/layout'
import { StatInline } from '@/components/primitives'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import { api } from '@/services/api'
import type { LiveSummary } from '@/pages/book/useBookData'

/**
 * DemoLiveSplitTile — side-by-side DEMO and LIVE account summary.
 *
 * Always shows both accounts regardless of the active mode toggle.
 * Uses its own independent DEMO query (never inherits the mode-reactive
 * dashboard from the parent) so switching DEMO ↔ LIVE in the top nav
 * does not mutate either card.
 */

interface DemoLiveSplitTileProps {
  /** liveSummary is passed in from the parent (already fetched there). */
  liveSummary: LiveSummary | undefined
  loading?: boolean
  className?: string
}

// Minimal shape we need from the dashboard response.
interface DashboardMini {
  account_equity: number
  total_unrealized_pnl: number
  quick_stats: { open_positions: number; win_rate_30d: number }
}

/** Always fetches DEMO — query key never includes the active mode. */
function useDemoDashboard() {
  return useQuery<DashboardMini>({
    queryKey: ['dashboard-mini', 'DEMO'],
    queryFn: () =>
      api.get<DashboardMini>('/account/dashboard/summary', { mode: 'DEMO', interval: '1d' }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export function DemoLiveSplitTile({
  liveSummary,
  loading,
  className,
}: DemoLiveSplitTileProps) {
  const navigate = useNavigate()
  const demoQuery = useDemoDashboard()
  const demo = demoQuery.data
  const isLoading = loading || demoQuery.isLoading

  const demoEquity = demo?.account_equity
  const demoPositions = demo?.quick_stats?.open_positions
  const demoWinRate = demo?.quick_stats?.win_rate_30d
  const demoUnrealized = demo?.total_unrealized_pnl

  const liveVirtual = liveSummary?.virtual_equity
  const liveReal = liveSummary?.real_equity
  const livePositions = liveSummary?.open_positions
  const liveTodayReal = liveSummary?.today_pnl_real
  const liveEnabled = liveSummary?.live_enabled ?? false

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Accounts</SectionLabel>
      <div className="grid grid-cols-2 gap-1.5">
        {/* DEMO — always shows DEMO data */}
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
              {isLoading ? '…' : `${demoPositions ?? 0} pos`}
            </span>
          </div>
          <div className="mono tabular-nums text-[13px] font-bold text-[var(--text-0)]">
            {isLoading ? '…' : formatCurrency(demoEquity ?? 0, { precision: 0 })}
          </div>
          <div className="grid grid-cols-2 gap-x-1 text-[9px]">
            <Stat
              label="WR 30d"
              value={demoWinRate != null ? `${formatNumber(demoWinRate, 1)}%` : '—'}
            />
            <Stat
              label="Unrealized"
              value={
                demoUnrealized != null
                  ? formatCurrency(demoUnrealized, { signed: true, precision: 0 })
                  : '—'
              }
              tone={
                demoUnrealized != null && demoUnrealized > 0
                  ? 'up'
                  : demoUnrealized != null && demoUnrealized < 0
                    ? 'down'
                    : 'neutral'
              }
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
              {`${livePositions ?? 0} pos`}
            </span>
          </div>
          <div className="mono tabular-nums text-[13px] font-bold text-[var(--text-0)]">
            {formatCurrency(liveVirtual ?? 0, { precision: 0 })}
          </div>
          <div className="grid grid-cols-2 gap-x-1 text-[9px]">
            <Stat
              label="Real"
              value={liveReal != null ? formatCurrency(liveReal, { precision: 0 }) : '—'}
            />
            <Stat
              label="Today"
              value={
                liveTodayReal != null
                  ? formatCurrency(liveTodayReal, { signed: true, precision: 0 })
                  : '—'
              }
              tone={
                liveTodayReal != null && liveTodayReal > 0
                  ? 'up'
                  : liveTodayReal != null && liveTodayReal < 0
                    ? 'down'
                    : 'neutral'
              }
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
    <StatInline
      label={label}
      value={value}
      size="xs"
      tone={tone === 'neutral' ? 'default' : tone}
    />
  )
}
