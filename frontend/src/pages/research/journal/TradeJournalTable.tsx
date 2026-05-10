import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { SectionLabel } from '@/components/layout'
import { Badge, DataTable, EmptyState } from '@/components/primitives'
import { BookOpen } from 'lucide-react'
import { cn, formatCurrency, formatNumber, formatTimestamp } from '@/lib/utils'
import type { TradeJournalEntry } from '../useResearchData'

interface TradeJournalTableProps {
  trades: TradeJournalEntry[] | undefined
  loading?: boolean
}

export function TradeJournalTable({ trades, loading }: TradeJournalTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'entry_time', desc: true },
  ])
  const data = trades ?? []

  const columns = useMemo<ColumnDef<TradeJournalEntry>[]>(
    () => [
      {
        id: 'entry_time',
        accessorKey: 'entry_time',
        header: () => <span>Entered</span>,
        size: 140,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-[10px]">
            {formatTimestamp(String(getValue()), 'short')}
          </span>
        ),
      },
      {
        id: 'symbol',
        accessorKey: 'symbol',
        header: () => <span>Symbol</span>,
        size: 80,
        cell: ({ getValue }) => (
          <span className="mono font-medium">{String(getValue())}</span>
        ),
      },
      {
        id: 'strategy_name',
        accessorKey: 'strategy_name',
        header: () => <span>Strategy</span>,
        size: 200,
        cell: ({ getValue }) => (
          <span className="truncate" title={String(getValue() ?? '')}>
            {String(getValue() ?? '—')}
          </span>
        ),
      },
      {
        id: 'pnl',
        accessorKey: 'pnl',
        header: () => <span className="text-right block w-full">P&L</span>,
        size: 90,
        cell: ({ getValue }) => {
          const v = Number(getValue() ?? 0)
          return (
            <span
              className={cn(
                'mono tabular-nums text-right block',
                v > 0 ? 'text-[var(--pnl-up)]' : v < 0 ? 'text-[var(--pnl-down)]' : '',
              )}
            >
              {formatCurrency(v, { signed: true, precision: 0 })}
            </span>
          )
        },
      },
      {
        id: 'pnl_percent',
        accessorKey: 'pnl_percent',
        header: () => <span className="text-right block w-full">Return</span>,
        size: 80,
        cell: ({ getValue }) => {
          const v = Number(getValue() ?? 0)
          return (
            <span
              className={cn(
                'mono tabular-nums text-right block',
                v > 0 ? 'text-[var(--pnl-up)]' : v < 0 ? 'text-[var(--pnl-down)]' : '',
              )}
            >
              {v > 0 ? '+' : ''}
              {formatNumber(v, 2)}%
            </span>
          )
        },
      },
      {
        id: 'hold_time_hours',
        accessorKey: 'hold_time_hours',
        header: () => <span className="text-right block w-full">Hold</span>,
        size: 70,
        cell: ({ getValue }) => {
          const v = Number(getValue() ?? 0)
          return (
            <span className="mono tabular-nums text-right block">
              {formatHold(v)}
            </span>
          )
        },
      },
      {
        id: 'max_adverse_excursion',
        accessorKey: 'max_adverse_excursion',
        header: () => <span className="text-right block w-full">MAE</span>,
        size: 70,
        cell: ({ getValue }) => {
          const v = getValue()
          return v == null ? (
            <span className="text-[var(--text-3)] text-[10px]">—</span>
          ) : (
            <span className="mono tabular-nums text-right block text-[var(--pnl-down)]">
              −{formatNumber(Math.abs(Number(v)), 2)}%
            </span>
          )
        },
      },
      {
        id: 'max_favorable_excursion',
        accessorKey: 'max_favorable_excursion',
        header: () => <span className="text-right block w-full">MFE</span>,
        size: 70,
        cell: ({ getValue }) => {
          const v = getValue()
          return v == null ? (
            <span className="text-[var(--text-3)] text-[10px]">—</span>
          ) : (
            <span className="mono tabular-nums text-right block text-[var(--pnl-up)]">
              +{formatNumber(Math.abs(Number(v)), 2)}%
            </span>
          )
        },
      },
      {
        id: 'conviction_score',
        accessorKey: 'conviction_score',
        header: () => <span className="text-right block w-full">Conv</span>,
        size: 60,
        cell: ({ getValue }) => {
          const v = getValue()
          return v == null ? (
            <span className="text-[var(--text-3)] text-[10px]">—</span>
          ) : (
            <span className="mono tabular-nums text-right block">
              {formatNumber(Number(v), 0)}
            </span>
          )
        },
      },
      {
        id: 'market_regime',
        accessorKey: 'market_regime',
        header: () => <span>Regime</span>,
        size: 110,
        cell: ({ getValue }) => {
          const v = String(getValue() ?? '')
          if (!v) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <Badge
              variant={
                /up/i.test(v)
                  ? 'regime-up'
                  : /down/i.test(v)
                    ? 'regime-down'
                    : /rang/i.test(v)
                      ? 'regime-range'
                      : 'default'
              }
              size="sm"
            >
              {v.replace(/_/g, ' ')}
            </Badge>
          )
        },
      },
      {
        id: 'exit_reason',
        accessorKey: 'exit_reason',
        header: () => <span>Exit</span>,
        size: 140,
        cell: ({ getValue }) => {
          const v = String(getValue() ?? '')
          return v ? (
            <span className="text-[var(--text-2)] text-[10px] truncate">
              {v.replace(/_/g, ' ')}
            </span>
          ) : (
            <span className="text-[var(--text-3)] text-[10px]">Open</span>
          )
        },
      },
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <SectionLabel>Trade journal · {data.length} shown</SectionLabel>
      {data.length === 0 && !loading ? (
        <EmptyState
          icon={BookOpen}
          title="No trades match filters"
          description="Adjust the filter bar above, or clear filters to see the full journal."
          className="py-8"
        />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] h-[480px]">
          <DataTable
            data={data}
            columns={columns}
            rowKey={(r) => String(r.id)}
            loading={loading}
            density="compact"
            sorting={{ state: sorting, onChange: setSorting }}
            virtualized
            estimatedRowHeight={24}
          />
        </div>
      )}
    </section>
  )
}

function formatHold(v: number): string {
  if (!Number.isFinite(v) || v <= 0) return '—'
  if (v < 1) return `${Math.round(v * 60)}m`
  if (v < 48) return `${v.toFixed(1)}h`
  return `${(v / 24).toFixed(1)}d`
}
