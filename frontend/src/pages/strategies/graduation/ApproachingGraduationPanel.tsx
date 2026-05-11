import { useMemo } from 'react'
import { TrendingUp } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { Badge, EmptyState, Skeleton } from '@/components/primitives'
import { cn, formatNumber } from '@/lib/utils'
import { useStrategies, type StrategyRow } from '../useStrategiesData'

/**
 * ApproachingGraduationPanel — top 10 PAPER strategies that are on track
 * toward graduation but haven't crossed the threshold yet.
 *
 * Graduation criteria (from useStrategiesData.isGraduationEligible):
 *   - status === PAPER
 *   - trades >= 20
 *   - Sharpe >= 1.0
 *
 * "Approaching" = PAPER + trades >= 10 + Sharpe >= 0.5 (below threshold).
 * Sorted by a composite graduation score so the closest candidates surface
 * at the top.
 */

interface ApproachingRow {
  id: string
  name: string
  symbol: string
  trades: number
  sharpe: number
  winRate: number
  totalPnl: number
  score: number // 0-100 composite progress toward graduation
}

function graduationScore(s: StrategyRow): number {
  const trades = s.performance_metrics?.total_trades ?? 0
  const sharpe = s.performance_metrics?.sharpe_ratio ?? 0
  const winRate = s.performance_metrics?.win_rate ?? 0
  // Weighted progress toward each threshold:
  //   trades: 20 needed → 40% weight
  //   sharpe: 1.0 needed → 40% weight
  //   win_rate: 45% needed → 20% weight
  const tradesPct = Math.min(1, trades / 20)
  const sharpePct = Math.min(1, Math.max(0, sharpe) / 1.0)
  const wrPct = Math.min(1, winRate / 45)
  return (tradesPct * 40 + sharpePct * 40 + wrPct * 20)
}

export function ApproachingGraduationPanel() {
  const strategies = useStrategies({ slim: true, include_retired: false })

  const rows = useMemo<ApproachingRow[]>(() => {
    const all = strategies.data?.strategies ?? []
    return all
      .filter((s) => {
        if (s.status !== 'PAPER') return false
        const trades = s.performance_metrics?.total_trades ?? 0
        const sharpe = s.performance_metrics?.sharpe_ratio ?? 0
        // Approaching but not yet graduated: trades 10-19 OR sharpe 0.5-0.99
        const approaching =
          (trades >= 10 && trades < 20) ||
          (sharpe >= 0.5 && sharpe < 1.0) ||
          (trades >= 20 && sharpe < 1.0)
        return approaching
      })
      .map((s) => ({
        id: s.id,
        name: s.name,
        symbol: (s.symbols ?? [])[0] ?? '—',
        trades: s.performance_metrics?.total_trades ?? 0,
        sharpe: s.performance_metrics?.sharpe_ratio ?? 0,
        winRate: s.performance_metrics?.win_rate ?? 0,
        totalPnl: s.performance_metrics?.total_pnl ?? 0,
        score: graduationScore(s),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 10)
  }, [strategies.data?.strategies])

  if (strategies.isLoading && !strategies.data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Approaching graduation</SectionLabel>
        <Skeleton className="h-[280px] w-full" />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Approaching graduation</SectionLabel>
        <EmptyState
          icon={TrendingUp}
          title="No strategies approaching graduation"
          description="Strategies appear here once they have ≥ 10 trades or Sharpe ≥ 0.5 but haven't yet crossed the graduation threshold."
          className="py-6"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel
        actions={
          <span className="text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            {rows.length} candidates · threshold: 20 trades + Sharpe ≥ 1.0
          </span>
        }
      >
        Approaching graduation
      </SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] divide-y divide-[var(--border-subtle)]">
        {rows.map((r) => (
          <ApproachingRow key={r.id} row={r} />
        ))}
      </div>
    </section>
  )
}

function ApproachingRow({ row }: { row: ApproachingRow }) {
  const tradesPct = Math.min(100, (row.trades / 20) * 100)
  const sharpePct = Math.min(100, (Math.max(0, row.sharpe) / 1.0) * 100)

  return (
    <div className="px-3 py-2 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[11px] font-medium text-[var(--text-0)] truncate" title={row.name}>
            {row.name}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <Badge variant="paper" size="sm">PAPER</Badge>
            <span className="mono text-[10px] text-[var(--text-2)]">{row.symbol}</span>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 text-[10px]">
          <Stat
            label="Trades"
            value={`${row.trades}/20`}
            tone={row.trades >= 20 ? 'up' : 'neutral'}
          />
          <Stat
            label="Sharpe"
            value={formatNumber(row.sharpe, 2)}
            tone={row.sharpe >= 1.0 ? 'up' : row.sharpe >= 0.5 ? 'neutral' : 'down'}
          />
          <Stat
            label="Win %"
            value={`${formatNumber(row.winRate, 1)}%`}
            tone={row.winRate >= 45 ? 'up' : 'neutral'}
          />
          <Stat
            label="P&L"
            value={`${row.totalPnl >= 0 ? '+' : ''}${formatNumber(row.totalPnl, 0)}`}
            tone={row.totalPnl > 0 ? 'up' : row.totalPnl < 0 ? 'down' : 'neutral'}
          />
        </div>
      </div>
      {/* Dual progress bars: trades + sharpe */}
      <div className="grid grid-cols-2 gap-2">
        <ProgressBar label="Trades" pct={tradesPct} met={row.trades >= 20} />
        <ProgressBar label="Sharpe" pct={sharpePct} met={row.sharpe >= 1.0} />
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'up' | 'down' | 'neutral'
}) {
  return (
    <div className="text-right">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[11px]',
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

function ProgressBar({
  label,
  pct,
  met,
}: {
  label: string
  pct: number
  met: boolean
}) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between text-[9px] text-[var(--text-3)]">
        <span>{label}</span>
        <span className={met ? 'text-[var(--pnl-up)]' : ''}>{Math.round(pct)}%</span>
      </div>
      <div className="h-1 bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
        <div
          className="h-full rounded-[1px] transition-all"
          style={{
            width: `${pct}%`,
            backgroundColor: met ? 'var(--pnl-up)' : pct >= 75 ? 'var(--status-warning)' : 'var(--accent-primary)',
          }}
        />
      </div>
    </div>
  )
}
