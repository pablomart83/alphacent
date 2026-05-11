import { cn } from '@/lib/utils'
import type { PipelineCounts } from '@/pages/command/StrategyPipelineCounts'

/**
 * LibraryStatusBar — compact status summary above the strategy table.
 *
 * Shows BACKTESTED · PAPER · LIVE · RETIRED counts as clickable badges
 * that filter the table. One glance tells the CIO the library state.
 */

interface LibraryStatusBarProps {
  counts: PipelineCounts
  liveAuthorizedCount?: number
  loading?: boolean
  onStatusFilter: (status: string) => void
  activeStatus: string
}

const STATUSES: Array<{
  key: keyof PipelineCounts
  label: string
  color: string
  filter: string
}> = [
  { key: 'backtested', label: 'Backtested', color: 'var(--status-warning)', filter: 'BACKTESTED' },
  { key: 'paper', label: 'Paper', color: 'var(--accent-secondary)', filter: 'PAPER' },
  { key: 'live', label: 'Live', color: 'var(--pnl-up)', filter: 'LIVE' },
  { key: 'retired', label: 'Retired', color: 'var(--text-3)', filter: 'RETIRED' },
]

export function LibraryStatusBar({
  counts,
  liveAuthorizedCount,
  loading,
  onStatusFilter,
  activeStatus,
}: LibraryStatusBarProps) {
  // Override the 'live' count with the live_authorized count from actual strategy rows
  // (strategies.status is never set to LIVE — live_strategies is the gate).
  const displayCounts: PipelineCounts = {
    ...counts,
    live: liveAuthorizedCount ?? counts.live,
  }
  return (
    <div className="flex items-center gap-1.5 px-2 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)] shrink-0 overflow-x-auto">
      <span className="text-[10px] text-[var(--text-3)] uppercase tracking-wider shrink-0">
        Library
      </span>
      <div className="flex items-center gap-1 flex-wrap">
        {STATUSES.map((s) => {
          const count = displayCounts[s.key]
          const isActive = activeStatus === s.filter
          return (
            <button
              key={s.key}
              type="button"
              onClick={() => onStatusFilter(isActive ? 'all' : s.filter)}
              className={cn(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-[2px] text-[10px] font-medium transition-colors',
                isActive
                  ? 'text-[var(--text-0)]'
                  : 'text-[var(--text-2)] hover:text-[var(--text-0)]',
              )}
              style={{
                backgroundColor: isActive
                  ? `color-mix(in oklab, ${s.color} 18%, transparent)`
                  : `color-mix(in oklab, ${s.color} 8%, transparent)`,
                border: `1px solid color-mix(in oklab, ${s.color} ${isActive ? '40%' : '20%'}, transparent)`,
              }}
            >
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: s.color }}
              />
              {s.label}
              <span
                className="mono tabular-nums"
                style={{ color: loading ? 'var(--text-3)' : s.color }}
              >
                {loading ? '…' : count}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
