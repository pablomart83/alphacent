import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { Activity, AlertCircle } from 'lucide-react'
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { classifyError } from '@/lib/errors'
import { formatTimestamp } from '@/lib/utils'
import {
  useLiveStrategies,
  useRetireLiveStrategy,
  type LiveStrategyRow,
} from '../useStrategiesData'

/**
 * ActiveLiveTable — currently authorised (template × symbol) pairs with
 * paper vs live Sharpe side by side, divergence %, retire action.
 */
export function ActiveLiveTable() {
  const query = useLiveStrategies()
  const retire = useRetireLiveStrategy()

  const [confirmRetire, setConfirmRetire] = useState<LiveStrategyRow | null>(null)
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'activated_at', desc: true },
  ])

  const rows = query.data?.live_strategies ?? []

  const handleRetire = async () => {
    if (!confirmRetire) return
    try {
      await retire.mutateAsync({ liveId: confirmRetire.id })
      toast.success(
        `Retired ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}`,
      )
      setConfirmRetire(null)
    } catch (err) {
      const info = classifyError(err, 'retire live')
      toast.error(info.title, { description: info.message })
    }
  }

  const columns = useMemo<ColumnDef<LiveStrategyRow>[]>(
    () => [
      {
        id: 'template',
        header: () => 'Template',
        accessorFn: (r) => r.template_name ?? r.strategy_id,
        size: 240,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-0)] font-medium truncate block max-w-[220px]"
            title={row.original.template_name ?? row.original.strategy_id}
          >
            {row.original.template_name ?? row.original.strategy_id}
          </span>
        ),
      },
      {
        id: 'symbol',
        header: () => 'Symbol',
        accessorKey: 'symbol',
        size: 80,
        cell: ({ row }) => (
          <span className="mono text-[var(--text-0)] font-medium">
            {row.original.symbol}
          </span>
        ),
      },
      {
        id: 'activated_at',
        header: () => 'Activated',
        accessorKey: 'activated_at',
        size: 124,
        cell: ({ row }) => (
          <span className="text-[10px] text-[var(--text-3)]">
            {formatTimestamp(row.original.activated_at, 'short')}
          </span>
        ),
      },
      {
        id: 'live_trades',
        header: () => 'Live trades',
        accessorFn: (r) => r.live_trades ?? 0,
        size: 92,
        cell: ({ row }) => {
          const n = row.original.live_trades ?? 0
          if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-1)]">{n}</span>
          )
        },
      },
      {
        id: 'live_pnl',
        header: () => 'Live P&L',
        accessorFn: (r) => r.live_pnl ?? null,
        size: 104,
        cell: ({ row }) => {
          const p = row.original.live_pnl
          if (p == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <PnLNumber value={p} format="currency" precision={0} size="sm" showSign />
          )
        },
      },
      {
        id: 'paper_vs_live',
        header: () => 'Paper / Live Sharpe',
        accessorFn: (r) => r.divergence_pct ?? null,
        size: 156,
        cell: ({ row }) => {
          const paper = row.original.current_paper_sharpe
          const live = row.original.live_sharpe
          return (
            <span className="mono tabular-nums text-[10px]">
              <span className="text-[var(--text-2)]">
                {paper != null ? paper.toFixed(2) : '—'}
              </span>
              <span className="text-[var(--text-3)]"> / </span>
              <span className="text-[var(--text-0)]">
                {live != null ? live.toFixed(2) : '—'}
              </span>
            </span>
          )
        },
      },
      {
        id: 'divergence',
        header: () => 'Divergence',
        accessorFn: (r) => r.divergence_pct ?? null,
        size: 118,
        cell: ({ row }) => {
          const d = row.original.divergence_pct
          if (d == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          const critical = d < 50
          const warning = d < 80
          const color = critical
            ? 'var(--pnl-down)'
            : warning
              ? 'var(--status-warning)'
              : 'var(--pnl-up)'
          return (
            <span className="inline-flex items-center gap-1">
              {critical && <AlertCircle className="h-3 w-3 text-[var(--pnl-down)]" />}
              <span className="mono tabular-nums" style={{ color }}>
                {d.toFixed(0)}%
              </span>
            </span>
          )
        },
      },
      {
        id: 'config',
        header: () => 'Config',
        size: 170,
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original
          return (
            <div className="text-[10px] space-x-1 mono text-[var(--text-2)]">
              <span title="Virtual position size">${r.position_size?.toFixed(0) ?? '—'}</span>
              <span className="text-[var(--text-3)]">·</span>
              <span title="Stop-loss %">
                SL{r.sl_pct != null ? `${(r.sl_pct * 100).toFixed(1)}%` : '—'}
              </span>
              <span className="text-[var(--text-3)]">·</span>
              <span title="Take-profit %">
                TP{r.tp_pct != null ? `${(r.tp_pct * 100).toFixed(1)}%` : '—'}
              </span>
              <span className="text-[var(--text-3)]">·</span>
              <span title="Minimum conviction score">
                C≥{r.conviction_min ?? '—'}
              </span>
            </div>
          )
        },
      },
      {
        id: 'actions',
        header: () => '',
        size: 96,
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex items-center justify-end">
            <Button
              size="sm"
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                setConfirmRetire(row.original)
              }}
            >
              Retire
            </Button>
          </div>
        ),
      },
    ],
    [],
  )

  return (
    <section className="flex flex-col gap-2 p-2 border-t border-[var(--border-subtle)]">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-[var(--account-live)]" />
          <SectionLabel className="mb-0">Active live authorisations</SectionLabel>
          <Badge variant="live" size="sm">
            {rows.length}
          </Badge>
        </div>
        <a
          href="/book/live?sub=divergence"
          className="text-[10px] text-[var(--accent-primary)] hover:underline"
        >
          Divergence heatmap →
        </a>
      </div>

      {rows.length === 0 && !query.isLoading ? (
        <EmptyState
          icon={Activity}
          title="No live authorisations"
          description="Approve a candidate from the queue above to authorise the first (template, symbol) pair."
        />
      ) : (
        <DataTable
          data={rows}
          columns={columns}
          rowKey={(r) => String(r.id)}
          loading={query.isLoading}
          sorting={{ state: sorting, onChange: setSorting }}
          density="compact"
        />
      )}

      <ConfirmDialog
        open={!!confirmRetire}
        onOpenChange={(o) => !o && setConfirmRetire(null)}
        title="Retire live authorisation"
        description={
          confirmRetire
            ? `Retire ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}? Future signals stop firing live orders. Open live positions are NOT closed automatically — use Book → Live to close them.`
            : ''
        }
        confirmLabel="Retire"
        confirmVariant="destructive"
        isLoading={retire.isPending}
        onConfirm={handleRetire}
      />
    </section>
  )
}
