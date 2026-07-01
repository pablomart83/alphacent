import { useNavigate } from 'react-router-dom'
import { StatTile } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber, formatPercentage } from '@/lib/utils'
import { useAutonomousCycles, useGraduationFunnel } from '@/pages/strategies/useStrategiesData'
import { useLiveDivergence } from '@/pages/book/useBookData'

/**
 * BACKTEST / WALK-FORWARD — statistical validation. Reuses the cycle-run stats
 * (avg Sharpe, WF pass rate), the graduation funnel, and the live-vs-WF
 * divergence feed. Metric logic stays server-side; this only presents it.
 */
export function BacktestZone() {
  const navigate = useNavigate()
  const cycles = useAutonomousCycles(1)
  const funnel = useGraduationFunnel(30)
  const divergence = useLiveDivergence()

  const latest = cycles.data?.data?.[0]
  const wfPassRate =
    latest && latest.backtested > 0 ? (latest.backtest_passed / latest.backtested) * 100 : null
  const symbolPassRate =
    latest && latest.symbols_checked > 0
      ? (latest.symbols_passed / latest.symbols_checked) * 100
      : null

  const flagged = divergence.data?.divergence?.filter((d) => d.divergence_flag) ?? []

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <StatTile
          label="WF pass rate"
          value={wfPassRate == null ? '—' : formatPercentage(wfPassRate, { precision: 0, signed: false })}
          sublabel={latest ? `${latest.backtest_passed}/${latest.backtested}` : undefined}
          tone={wfPassRate != null && wfPassRate >= 5 ? 'up' : 'default'}
        />
        <StatTile
          label="Avg test Sharpe"
          value={latest?.avg_sharpe == null ? '—' : formatNumber(latest.avg_sharpe, 2)}
          tone={latest?.avg_sharpe != null && latest.avg_sharpe >= 1 ? 'up' : 'default'}
        />
        <StatTile
          label="Avg win rate"
          value={latest?.avg_win_rate == null ? '—' : formatPercentage(latest.avg_win_rate, { precision: 0, signed: false })}
        />
        <StatTile
          label="Symbol pass"
          value={symbolPassRate == null ? '—' : formatPercentage(symbolPassRate, { precision: 0, signed: false })}
          sublabel={latest ? `${latest.symbols_passed}/${latest.symbols_checked}` : undefined}
        />
        <StatTile
          label="Proposals"
          value={latest?.proposals_generated ?? '—'}
        />
        <StatTile
          label="WF→live divergence"
          value={divergence.isLoading ? '…' : flagged.length}
          tone={flagged.length > 0 ? 'warn' : 'up'}
          pulseValue={flagged.length > 0}
          onClick={() => navigate('/book/live')}
        />
      </div>

      {/* Graduation funnel */}
      <div>
        <SectionLabel>Graduation funnel (30d)</SectionLabel>
        {funnel.isLoading ? (
          <div className="h-14 animate-pulse rounded-[3px] bg-[var(--bg-1)]" />
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-1">
            {(funnel.data?.funnel ?? []).map((stage, i) => (
              <div key={stage.stage} className="flex items-center gap-2 shrink-0">
                <div className="min-w-[92px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
                  <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] truncate" title={stage.stage}>
                    {stage.stage}
                  </div>
                  <div className="mono tabular-nums text-[16px] font-bold text-[var(--text-0)]">
                    {stage.count}
                  </div>
                  {stage.drop_from_prev != null && i > 0 && (
                    <div className="text-[9px] text-[var(--text-3)] mono">
                      −{stage.drop_from_prev}
                    </div>
                  )}
                </div>
                {i < (funnel.data?.funnel?.length ?? 0) - 1 && (
                  <span className="text-[var(--text-3)]">→</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {flagged.length > 0 && (
        <div className={cn('rounded-[3px] border border-[var(--status-warning)]/40 bg-[var(--status-warning-bg)] p-2')}>
          <div className="text-[10px] uppercase tracking-wider text-[var(--status-warning)] mb-1">
            Live diverging from walk-forward
          </div>
          <div className="flex flex-wrap gap-1.5">
            {flagged.slice(0, 8).map((d) => (
              <span
                key={d.id}
                className="rounded-[2px] bg-[var(--bg-2)] px-1.5 py-0.5 text-[10px] mono text-[var(--text-1)]"
                title={`${d.template_name} · paper Sharpe ${d.paper_sharpe ?? '—'} vs live ${d.live_sharpe ?? '—'}`}
              >
                {d.symbol}
                {d.divergence_pct != null && (
                  <span className="ml-1 text-[var(--pnl-down)]">
                    {formatPercentage(d.divergence_pct, { precision: 0 })}
                  </span>
                )}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
