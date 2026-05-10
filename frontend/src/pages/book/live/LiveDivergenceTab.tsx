import { useMemo, useState } from 'react'
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Skeleton,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { classifyError } from '@/lib/errors'
import { cn, formatAge } from '@/lib/utils'
import { toast } from 'sonner'
import { AlertTriangle, GitCompare, ShieldAlert } from 'lucide-react'
import {
  useLiveDivergence,
  useRetireLiveStrategy,
  type LiveDivergenceRow,
} from '../useBookData'

/**
 * Divergence tab.
 *
 * Answers: "Is live underperforming paper on this authorised pair?"
 *
 * divergence_pct (from backend) = live_sharpe / paper_sharpe × 100.
 *   - 100+   live is matching or beating paper
 *   - 50–100 live is worse than paper but still positive
 *   - 0–50   divergence_flag = true (live <50% of paper Sharpe)
 *   - null   either not enough live trades, or paper_sharpe ≤ 0
 *
 * The intensity bar shows each row's divergence — green if ≥100%, amber 50–99, red <50.
 */
export function LiveDivergenceTab() {
  const query = useLiveDivergence()
  const retire = useRetireLiveStrategy()
  const [retireTarget, setRetireTarget] = useState<LiveDivergenceRow | null>(null)

  const rows = query.data?.divergence ?? []
  const flagged = useMemo(() => rows.filter((r) => r.divergence_flag).length, [rows])

  const handleRetire = async (row: LiveDivergenceRow) => {
    try {
      const res = await retire.mutateAsync(row.id)
      toast.success(res.message || `Retired live authorisation for ${row.symbol}`)
    } catch (e) {
      const info = classifyError(e, 'retire live')
      toast.error(info.title, { description: info.message })
    } finally {
      setRetireTarget(null)
    }
  }

  if (query.isError) {
    const info = classifyError(query.error, 'live divergence')
    return (
      <ErrorState
        title="Couldn't load divergence"
        message={info.message}
        onRetry={() => query.refetch()}
      />
    )
  }

  if (query.isLoading && rows.length === 0) {
    return (
      <div className="flex flex-col gap-2 p-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} variant="block" className="h-20" />
        ))}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <EmptyState
        icon={GitCompare}
        title="No live authorisations yet"
        description="Once a (template, symbol) pair is graduated to live trading and accumulates live trades, divergence vs paper performance appears here."
        className="py-10"
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Summary strip */}
      <div className="flex items-center gap-3 px-3 py-2 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
        <SectionLabel className="mb-0">Live authorisations</SectionLabel>
        <span className="text-[11px] text-[var(--text-2)] mono">
          {rows.length} total
        </span>
        {flagged > 0 && (
          <span className="text-[11px] inline-flex items-center gap-1 text-[var(--status-error)]">
            <ShieldAlert className="h-3 w-3" />
            {flagged} flagged · live &lt; 50% of paper Sharpe
          </span>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-auto p-3 flex flex-col gap-2">
        {rows.map((row) => (
          <DivergenceCard
            key={row.id}
            row={row}
            onRetire={() => setRetireTarget(row)}
            isRetiring={retire.isPending && retire.variables === row.id}
          />
        ))}
      </div>

      <ConfirmDialog
        open={!!retireTarget}
        onOpenChange={(o) => !o && setRetireTarget(null)}
        title="Retire live authorisation"
        description={
          retireTarget
            ? `Stop live fills for ${retireTarget.template_name} / ${retireTarget.symbol}? The strategy keeps paper-trading on DEMO; existing live positions stay open and continue to be monitored.`
            : ''
        }
        confirmLabel="Retire"
        confirmVariant="destructive"
        isLoading={retire.isPending}
        onConfirm={() => {
          if (retireTarget) void handleRetire(retireTarget)
        }}
      />
    </div>
  )
}

function DivergenceCard({
  row,
  onRetire,
  isRetiring,
}: {
  row: LiveDivergenceRow
  onRetire: () => void
  isRetiring?: boolean
}) {
  const divergence = row.divergence_pct
  const flagged = row.divergence_flag

  const colour =
    divergence == null
      ? 'var(--text-3)'
      : divergence >= 100
        ? 'var(--pnl-up)'
        : divergence >= 50
          ? 'var(--status-warning)'
          : 'var(--pnl-down)'

  return (
    <div
      className={cn(
        'rounded-[4px] border bg-[var(--bg-1)] p-3',
        flagged
          ? 'border-[var(--status-error)]/40'
          : divergence != null && divergence >= 100
            ? 'border-[var(--pnl-up)]/30'
            : 'border-[var(--border-subtle)]',
      )}
    >
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="mono font-semibold text-[13px] text-[var(--text-0)]">
              {row.symbol}
            </span>
            <span className="text-[11px] text-[var(--text-2)] truncate max-w-[240px]">
              {row.template_name}
            </span>
            {flagged && (
              <Badge variant="error" size="sm">
                <AlertTriangle className="h-2.5 w-2.5" />
                Divergent
              </Badge>
            )}
          </div>
          <div className="text-[10px] text-[var(--text-3)] mono mt-0.5">
            activated {formatAge(row.activated_at)} · size $
            {row.position_size?.toFixed(0) ?? '—'} · conviction ≥{' '}
            {row.conviction_min ?? '—'}
          </div>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRetire}
          loading={isRetiring}
          className="text-[var(--pnl-down)] hover:bg-[var(--pnl-down)]/10"
        >
          Retire
        </Button>
      </div>

      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-2">
        <StatBlock label="Paper" variant="paper">
          <StatRow label="trades" value={`${row.paper_trades}`} />
          <StatRow label="Sharpe" value={row.paper_sharpe?.toFixed(2) ?? '—'} />
          <StatRow
            label="win %"
            value={row.paper_win_rate != null ? `${row.paper_win_rate.toFixed(1)}%` : '—'}
          />
          <StatRow label="P&L" valueNode={<PnLNumber value={row.paper_pnl ?? 0} format="currency" precision={0} size="sm" />} />
        </StatBlock>
        <StatBlock label="Live" variant="live">
          <StatRow label="trades" value={`${row.live_trades}`} />
          <StatRow label="Sharpe" value={row.live_sharpe?.toFixed(2) ?? '—'} />
          <StatRow
            label="win %"
            value={row.live_win_rate != null ? `${row.live_win_rate.toFixed(1)}%` : '—'}
          />
          <StatRow label="P&L" valueNode={<PnLNumber value={row.live_pnl ?? 0} format="currency" precision={0} size="sm" />} />
        </StatBlock>
        <StatBlock label="Divergence" variant="neutral">
          <div className="flex flex-col gap-1">
            <span
              className="mono tabular-nums text-[20px] font-bold"
              style={{ color: colour }}
            >
              {divergence == null ? '—' : `${divergence.toFixed(0)}%`}
            </span>
            <span className="text-[10px] text-[var(--text-3)]">
              live Sharpe ÷ paper Sharpe
            </span>
            <DivergenceBar pct={divergence} />
          </div>
        </StatBlock>
      </div>
    </div>
  )
}

/**
 * Intensity bar — shows where this row's divergence falls on a 0-150% scale.
 * Red zone <50, amber 50-99, green 100+. Fills proportionally, capped at 150%.
 */
function DivergenceBar({ pct }: { pct: number | null }) {
  if (pct == null) {
    return (
      <div className="h-1.5 rounded-[1px] overflow-hidden bg-[var(--bg-2)]">
        <div className="h-full w-full bg-[var(--bg-2)]" />
      </div>
    )
  }

  const clamped = Math.max(0, Math.min(150, pct))
  const colour = clamped >= 100 ? 'var(--pnl-up)' : clamped >= 50 ? 'var(--status-warning)' : 'var(--pnl-down)'

  return (
    <div className="relative h-1.5 rounded-[1px] overflow-hidden bg-[var(--bg-2)]">
      <div
        className="absolute inset-y-0 left-0"
        style={{
          width: `${(clamped / 150) * 100}%`,
          backgroundColor: colour,
        }}
      />
      {/* 50% threshold marker */}
      <div
        className="absolute inset-y-0 w-[1px] bg-[var(--text-3)]"
        style={{ left: `${(50 / 150) * 100}%` }}
        title="50% — divergent threshold"
      />
      {/* 100% marker */}
      <div
        className="absolute inset-y-0 w-[1px] bg-[var(--text-0)]"
        style={{ left: `${(100 / 150) * 100}%` }}
        title="100% — paper parity"
      />
    </div>
  )
}

function StatBlock({
  label,
  variant,
  children,
}: {
  label: string
  variant: 'paper' | 'live' | 'neutral'
  children: React.ReactNode
}) {
  const border =
    variant === 'paper'
      ? 'border-[var(--accent-secondary)]/30'
      : variant === 'live'
        ? 'border-[var(--account-live)]/40'
        : 'border-[var(--border-subtle)]'
  const titleColour =
    variant === 'paper'
      ? 'text-[var(--accent-secondary)]'
      : variant === 'live'
        ? 'text-[var(--account-live)]'
        : 'text-[var(--text-3)]'
  return (
    <div className={cn('rounded-[3px] border bg-[var(--bg-2)] px-2.5 py-2', border)}>
      <div className={cn('text-[10px] uppercase tracking-wider font-medium mb-1', titleColour)}>
        {label}
      </div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  )
}

function StatRow({
  label,
  value,
  valueNode,
}: {
  label: string
  value?: string
  valueNode?: React.ReactNode
}) {
  return (
    <div className="flex items-baseline justify-between text-[11px]">
      <span className="text-[var(--text-3)]">{label}</span>
      {valueNode ?? (
        <span className="mono tabular-nums text-[var(--text-1)]">{value}</span>
      )}
    </div>
  )
}
