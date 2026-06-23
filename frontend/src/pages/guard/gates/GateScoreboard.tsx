import { useMemo } from 'react'
import { RefreshCw } from 'lucide-react'
import { Button, Skeleton, EmptyState, ErrorState } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import {
  useGateScoreboard,
  useRecomputeGateScoreboard,
  type GateScoreboardRow,
} from '../useGuardData'

/**
 * GateScoreboard — Tier-1 observability. For every entry gate, shows the
 * forward-return of the signals it BLOCKED vs the signals that PASSED all
 * gates (a direction-aware N-bar counterfactual from price data). A gate that
 * "hurts" is blocking signals that would have done better than the ones we let
 * through — silent edge destruction. Read-only; precomputed off the hot path.
 */

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(2)}%`
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    helps: { label: 'helps', color: 'var(--pnl-up)', bg: 'color-mix(in srgb, var(--pnl-up) 14%, transparent)' },
    hurts: { label: 'hurts', color: 'var(--pnl-down)', bg: 'color-mix(in srgb, var(--pnl-down) 14%, transparent)' },
    neutral: { label: 'neutral', color: 'var(--text-3)', bg: 'var(--bg-2)' },
    capacity: { label: 'capacity', color: 'var(--text-3)', bg: 'var(--bg-2)' },
    insufficient_data: { label: 'low n', color: 'var(--text-3)', bg: 'var(--bg-2)' },
  }
  const m = map[verdict] ?? map.insufficient_data
  return (
    <span
      className="inline-flex items-center rounded-[3px] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide"
      style={{ color: m.color, backgroundColor: m.bg }}
    >
      {m.label}
    </span>
  )
}

function GateRow({ row }: { row: GateScoreboardRow }) {
  const sep = row.separation
  const sepColor =
    sep === null
      ? 'var(--text-3)'
      : sep > 0
        ? 'var(--pnl-up)'
        : sep < 0
          ? 'var(--pnl-down)'
          : 'var(--text-2)'
  return (
    <tr className="border-t border-[var(--border-subtle)]">
      <td className="py-1.5 pr-2">
        <div className="flex items-center gap-1.5">
          <span className="text-[12px] text-[var(--text-1)]">{row.label}</span>
          {row.edge_gate ? (
            <span className="text-[9px] uppercase text-[var(--text-3)] border border-[var(--border-subtle)] rounded px-1">
              edge
            </span>
          ) : (
            <span className="text-[9px] uppercase text-[var(--text-3)]">cap</span>
          )}
        </div>
      </td>
      <td className="py-1.5 px-2 text-right mono text-[11px] text-[var(--text-2)]">
        {row.blocked_n.toLocaleString('en-US')}
      </td>
      <td className="py-1.5 px-2 text-right mono text-[11px] text-[var(--text-1)]">
        {pct(row.blocked_mean_fwd)}
        <span className="text-[var(--text-3)]">
          {row.blocked_win_rate !== null ? ` (${(row.blocked_win_rate * 100).toFixed(0)}%)` : ''}
        </span>
      </td>
      <td className="py-1.5 px-2 text-right mono text-[11px] text-[var(--text-2)]">
        {pct(row.passed_mean_fwd)}
      </td>
      <td className="py-1.5 px-2 text-right mono text-[11px]" style={{ color: sepColor }}>
        {sep === null ? '—' : `${sep > 0 ? '+' : ''}${(sep * 100).toFixed(2)}%`}
      </td>
      <td className="py-1.5 pl-2 text-right">
        <VerdictBadge verdict={row.verdict} />
      </td>
    </tr>
  )
}

export function GateScoreboard({ className }: { className?: string }) {
  const query = useGateScoreboard()
  const recompute = useRecomputeGateScoreboard()

  const accounts = useMemo(() => {
    const acc = query.data?.accounts ?? {}
    return (['demo', 'live'] as const)
      .map((key) => ({ key, data: acc[key] }))
      .filter((a) => a.data && (a.data.gates.length > 0 || a.data.passed.n > 0))
  }, [query.data])

  const meta = query.data
  const computedAt = meta?.computed_at ? new Date(meta.computed_at).toLocaleString() : null

  return (
    <section className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-center gap-2">
        <SectionLabel>Gate scoreboard · blocked-vs-passed forward edge</SectionLabel>
        <div className="ml-auto flex items-center gap-2">
          {meta?.coverage && (
            <span className="text-[10px] mono text-[var(--text-3)]">
              {meta.coverage.with_forward_return.toLocaleString('en-US')} signals ·{' '}
              {meta.horizon_bars}-bar fwd · {meta.lookback_days}d
            </span>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => recompute.mutate()}
            disabled={recompute.isPending || meta?.computing}
          >
            <RefreshCw className={cn('h-3 w-3 mr-1', (recompute.isPending || meta?.computing) && 'animate-spin')} />
            Recompute
          </Button>
        </div>
      </div>

      {query.isError ? (
        <ErrorState
          title="Couldn't load gate scoreboard"
          message={classifyError(query.error, 'gate scoreboard').message}
          onRetry={() => query.refetch()}
        />
      ) : query.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : !meta?.available ? (
        <EmptyState
          title="No scoreboard computed yet"
          description={meta?.message || 'Trigger a recompute or wait for the daily job.'}
        />
      ) : (
        <div className="flex flex-col gap-3">
          {computedAt && (
            <div className="text-[10px] text-[var(--text-3)]">
              Computed {computedAt}. Forward return is gross, direction-aware, over{' '}
              {meta.horizon_bars} daily bars. <strong>separation = passed − blocked</strong>; positive ⇒ gate
              blocks worse signals (helps), negative ⇒ blocks better signals (hurts).
            </div>
          )}
          {accounts.map(({ key, data }) => (
            <div key={key} className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[11px] uppercase tracking-wider text-[var(--text-2)]">{key}</span>
                {data && (
                  <span className="text-[10px] mono text-[var(--text-3)]">
                    passed cohort: {data.passed.n.toLocaleString('en-US')} signals · fwd {pct(data.passed.mean_fwd)}
                    {data.passed.win_rate !== null ? ` · win ${(data.passed.win_rate * 100).toFixed(0)}%` : ''}
                  </span>
                )}
              </div>
              <table className="w-full">
                <thead>
                  <tr className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                    <th className="text-left font-normal pb-1">Gate</th>
                    <th className="text-right font-normal pb-1 px-2">Blocked</th>
                    <th className="text-right font-normal pb-1 px-2">Blocked fwd (win)</th>
                    <th className="text-right font-normal pb-1 px-2">Passed fwd</th>
                    <th className="text-right font-normal pb-1 px-2">Separation</th>
                    <th className="text-right font-normal pb-1 pl-2">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.gates.map((row) => (
                    <GateRow key={row.gate} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
