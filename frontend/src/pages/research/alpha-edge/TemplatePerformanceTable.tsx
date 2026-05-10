import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { SectionLabel } from '@/components/layout'
import { DataTable, EmptyState } from '@/components/primitives'
import { Package } from 'lucide-react'
import { cn, formatNumber } from '@/lib/utils'
import type { TemplatePerformance } from '../useResearchData'

interface TemplatePerformanceTableProps {
  rows: TemplatePerformance[] | undefined
  loading?: boolean
}

export function TemplatePerformanceTable({
  rows,
  loading,
}: TemplatePerformanceTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'sharpe_ratio', desc: true },
  ])
  const data = rows ?? []

  const columns = useMemo<ColumnDef<TemplatePerformance>[]>(
    () => [
      {
        id: 'template',
        accessorKey: 'template',
        header: () => <span>Template</span>,
        cell: ({ getValue }) => (
          <span className="truncate" title={String(getValue())}>
            {String(getValue())}
          </span>
        ),
      },
      {
        id: 'trades',
        accessorKey: 'trades',
        header: () => <span className="text-right block w-full">Trades</span>,
        size: 70,
        cell: ({ getValue }) => {
          const v = Number(getValue())
          return (
            <span
              className={cn(
                'mono tabular-nums text-right block',
                v < 8 && 'text-[var(--text-3)]',
              )}
            >
              {formatNumber(v, 0)}
            </span>
          )
        },
      },
      {
        id: 'win_rate',
        accessorKey: 'win_rate',
        header: () => <span className="text-right block w-full">Win %</span>,
        size: 70,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatNumber(Number(getValue()), 1)}%
          </span>
        ),
      },
      {
        id: 'total_return',
        accessorKey: 'total_return',
        header: () => <span className="text-right block w-full">Return</span>,
        size: 90,
        cell: ({ getValue }) => {
          const v = Number(getValue())
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
        id: 'sharpe_ratio',
        accessorKey: 'sharpe_ratio',
        header: () => <span className="text-right block w-full">Sharpe</span>,
        size: 80,
        cell: ({ getValue }) => {
          const v = Number(getValue())
          return (
            <span
              className={cn(
                'mono tabular-nums text-right block',
                v >= 1 ? 'text-[var(--pnl-up)]' : v < 0 ? 'text-[var(--pnl-down)]' : '',
              )}
            >
              {formatNumber(v, 2)}
            </span>
          )
        },
      },
      {
        id: 'avg_hold_time_hours',
        accessorKey: 'avg_hold_time_hours',
        header: () => <span className="text-right block w-full">Avg hold</span>,
        size: 90,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatHold(Number(getValue()))}
          </span>
        ),
      },
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <SectionLabel>Per-template performance</SectionLabel>
      {data.length === 0 && !loading ? (
        <EmptyState
          icon={Package}
          title="No template performance"
          description="Each row needs at least one closed trade under its template."
          className="py-6"
        />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] max-h-[380px]">
          <DataTable
            data={data}
            columns={columns}
            rowKey={(r) => r.template}
            loading={loading}
            sorting={{ state: sorting, onChange: setSorting }}
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
