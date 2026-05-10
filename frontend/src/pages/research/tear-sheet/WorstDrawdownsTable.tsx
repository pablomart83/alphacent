import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { SectionLabel } from '@/components/layout'
import { DataTable, EmptyState } from '@/components/primitives'
import { Waves } from 'lucide-react'
import { cn, formatNumber, formatTimestamp } from '@/lib/utils'
import type { WorstDrawdown } from '../useResearchData'

interface WorstDrawdownsTableProps {
  rows: WorstDrawdown[] | undefined
  loading?: boolean
}

export function WorstDrawdownsTable({ rows, loading }: WorstDrawdownsTableProps) {
  const data = rows ?? []

  const columns = useMemo<ColumnDef<WorstDrawdown>[]>(
    () => [
      {
        id: 'rank',
        accessorKey: 'rank',
        header: () => <span className="text-right block w-full">#</span>,
        size: 40,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">{String(getValue())}</span>
        ),
      },
      {
        id: 'start_date',
        accessorKey: 'start_date',
        header: () => <span>Start</span>,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums">{formatTimestamp(String(getValue()), 'date')}</span>
        ),
      },
      {
        id: 'trough_date',
        accessorKey: 'trough_date',
        header: () => <span>Trough</span>,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums">{formatTimestamp(String(getValue()), 'date')}</span>
        ),
      },
      {
        id: 'recovery_date',
        accessorKey: 'recovery_date',
        header: () => <span>Recovered</span>,
        cell: ({ getValue }) => {
          const v = getValue()
          return v ? (
            <span className="mono tabular-nums">{formatTimestamp(String(v), 'date')}</span>
          ) : (
            <span className="text-[var(--status-warning)] text-[10px] mono">— in progress</span>
          )
        },
      },
      {
        id: 'depth_pct',
        accessorKey: 'depth_pct',
        header: () => <span className="text-right block w-full">Depth</span>,
        size: 80,
        cell: ({ getValue }) => {
          const v = Math.abs(Number(getValue()))
          return (
            <span
              className={cn(
                'mono tabular-nums text-right block',
                v > 15 ? 'text-[var(--pnl-down)]' : 'text-[var(--status-warning)]',
              )}
            >
              −{formatNumber(v, 2)}%
            </span>
          )
        },
      },
      {
        id: 'duration_days',
        accessorKey: 'duration_days',
        header: () => <span className="text-right block w-full">Duration</span>,
        size: 90,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">{formatNumber(Number(getValue()), 0)}d</span>
        ),
      },
      {
        id: 'recovery_days',
        accessorKey: 'recovery_days',
        header: () => <span className="text-right block w-full">Recovery</span>,
        size: 90,
        cell: ({ getValue }) => {
          const v = getValue()
          return v == null ? (
            <span className="text-[var(--text-3)] text-[10px]">—</span>
          ) : (
            <span className="mono tabular-nums text-right block">
              {formatNumber(Number(v), 0)}d
            </span>
          )
        },
      },
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <SectionLabel>Worst drawdowns</SectionLabel>
      {data.length === 0 && !loading ? (
        <EmptyState
          icon={Waves}
          title="No material drawdowns"
          description="Top-5 drawdowns populate once equity_snapshots covers enough history."
          className="py-6"
        />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
          <DataTable
            data={data}
            columns={columns}
            rowKey={(r) => String(r.rank)}
            loading={loading}
          />
        </div>
      )}
    </section>
  )
}
