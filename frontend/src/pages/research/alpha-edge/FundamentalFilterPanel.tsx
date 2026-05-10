import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber } from '@/lib/utils'
import type { FundamentalStats } from '../useResearchData'

interface FundamentalFilterPanelProps {
  data: FundamentalStats | undefined
  loading?: boolean
}

export function FundamentalFilterPanel({
  data,
  loading,
}: FundamentalFilterPanelProps) {
  const passRate = Number(data?.pass_rate ?? 0)
  const filtered = Number(data?.symbols_filtered ?? 0)
  const passed = Number(data?.symbols_passed ?? 0)
  const summary = data?.checks_summary ?? {}
  const reasons = data?.failure_reasons ?? {}

  return (
    <Card padding="sm" className="flex flex-col gap-2 min-h-[260px]">
      <SectionLabel className="mb-0">Fundamental filter</SectionLabel>
      {loading && !data ? (
        <div className="flex-1 animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <Stat label="Pass rate" value={`${formatNumber(passRate, 1)}%`} tone={passRate >= 50 ? 'up' : 'down'} />
            <Stat label="Filtered" value={formatNumber(filtered, 0)} />
            <Stat label="Passed" value={formatNumber(passed, 0)} tone="up" />
          </div>
          {Object.keys(summary).length > 0 && (
            <div className="space-y-1">
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                Per-check pass rate
              </div>
              {Object.entries(summary).map(([check, stats]) => {
                const pass = Number(stats?.passed ?? 0)
                const fail = Number(stats?.failed ?? 0)
                const total = pass + fail || 1
                const pct = (pass / total) * 100
                return (
                  <div key={check} className="grid grid-cols-[110px_1fr_40px] items-center gap-2">
                    <span className="text-[10px] text-[var(--text-1)] truncate" title={check}>
                      {check.replace(/_/g, ' ')}
                    </span>
                    <div className="h-1.5 bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
                      <div
                        className="h-full"
                        style={{
                          width: `${pct}%`,
                          backgroundColor:
                            pct >= 60
                              ? 'var(--pnl-up)'
                              : pct >= 30
                                ? 'var(--status-warning)'
                                : 'var(--pnl-down)',
                        }}
                      />
                    </div>
                    <span className="mono tabular-nums text-[10px] text-right text-[var(--text-2)]">
                      {formatNumber(pct, 0)}%
                    </span>
                  </div>
                )
              })}
            </div>
          )}
          {Object.keys(reasons).length > 0 && (
            <div className="mt-auto pt-1.5 border-t border-[var(--border-subtle)] text-[10px] space-y-0.5">
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                Top failure reasons
              </div>
              {Object.entries(reasons)
                .sort(([, a], [, b]) => Number(b) - Number(a))
                .slice(0, 4)
                .map(([reason, count]) => (
                  <div key={reason} className="flex items-center justify-between">
                    <span className="text-[var(--text-2)] truncate">
                      {reason.replace(/_/g, ' ')}
                    </span>
                    <span className="mono tabular-nums text-[var(--pnl-down)]">
                      {formatNumber(Number(count), 0)}
                    </span>
                  </div>
                ))}
            </div>
          )}
        </>
      )}
    </Card>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[13px]',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}
