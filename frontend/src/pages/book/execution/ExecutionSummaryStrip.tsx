import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useTradingMode } from '@/stores'
import { useOrders } from '../useBookData'
import { computeExecutionAnalytics } from './computeMetrics'

/**
 * ExecutionSummaryStrip — 6 key execution metrics above the sub-tabs.
 *
 * Computed client-side from the orders list (same source as SlippageTab)
 * so no extra network request. Uses the 1M window as the default.
 */
export function ExecutionSummaryStrip() {
  const mode = useTradingMode((s) => s.mode)
  const ordersQuery = useOrders({ limit: 2000 })
  const orders = ordersQuery.data?.orders ?? []

  const analytics = useMemo(
    () => computeExecutionAnalytics(orders, '1M'),
    [orders],
  )

  const { tiles } = analytics
  const loading = ordersQuery.isLoading

  const metrics: Array<{ label: string; value: string; tone?: 'up' | 'down' | 'warn' | 'neutral' }> = [
    {
      label: 'Filled (30d)',
      value: loading ? '…' : tiles.filledCount.toLocaleString('en-US'),
      tone: 'neutral',
    },
    {
      label: 'Fill rate',
      value: loading ? '…' : `${tiles.fillRatePct.toFixed(1)}%`,
      tone: tiles.fillRatePct >= 95 ? 'up' : tiles.fillRatePct >= 85 ? 'warn' : 'down',
    },
    {
      label: 'Avg slippage',
      value:
        loading || tiles.avgSlippageBps == null
          ? '—'
          : `${tiles.avgSlippageBps >= 0 ? '+' : ''}${tiles.avgSlippageBps.toFixed(1)} bps`,
      tone:
        tiles.avgSlippageBps == null
          ? 'neutral'
          : Math.abs(tiles.avgSlippageBps) < 3
            ? 'up'
            : Math.abs(tiles.avgSlippageBps) < 8
              ? 'warn'
              : 'down',
    },
    {
      label: 'Rejection rate',
      value: loading ? '…' : `${tiles.rejectionRatePct.toFixed(1)}%`,
      tone: tiles.rejectionRatePct <= 5 ? 'up' : tiles.rejectionRatePct <= 15 ? 'warn' : 'down',
    },
    {
      label: 'Avg fill time',
      value:
        loading || tiles.avgFillTimeSec == null
          ? '—'
          : tiles.avgFillTimeSec < 60
            ? `${tiles.avgFillTimeSec.toFixed(1)}s`
            : `${(tiles.avgFillTimeSec / 60).toFixed(1)}m`,
      tone: 'neutral',
    },
    {
      label: 'Shortfall',
      value:
        loading || tiles.implementationShortfallBps == null
          ? '—'
          : `${tiles.implementationShortfallBps.toFixed(1)} bps`,
      tone:
        tiles.implementationShortfallBps == null
          ? 'neutral'
          : Math.abs(tiles.implementationShortfallBps) < 5
            ? 'up'
            : 'warn',
    },
  ]

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)] shrink-0 overflow-x-auto">
      <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] shrink-0">
        {mode} · 30d
      </span>
      {metrics.map((m) => (
        <div key={m.label} className="flex items-center gap-1.5 shrink-0">
          <span className="text-[9px] text-[var(--text-3)] uppercase tracking-wider">{m.label}</span>
          <span
            className={cn(
              'mono tabular-nums text-[11px] font-semibold',
              m.tone === 'up'
                ? 'text-[var(--pnl-up)]'
                : m.tone === 'down'
                  ? 'text-[var(--pnl-down)]'
                  : m.tone === 'warn'
                    ? 'text-[var(--status-warning)]'
                    : 'text-[var(--text-0)]',
            )}
          >
            {m.value}
          </span>
          <span className="text-[var(--text-3)] text-[9px]">·</span>
        </div>
      ))}
    </div>
  )
}
