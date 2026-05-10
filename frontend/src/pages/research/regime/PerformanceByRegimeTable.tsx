import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { SectionLabel } from '@/components/layout'
import { Badge, DataTable, EmptyState } from '@/components/primitives'
import { Workflow } from 'lucide-react'
import { cn, formatNumber } from '@/lib/utils'
import type { RegimePerformanceRow } from '../useResearchData'

interface PerformanceByRegimeTableProps {
  rows: RegimePerformanceRow[] | undefined
  loading?: boolean
}

export function PerformanceByRegimeTable({
  rows,
  loading,
}: PerformanceByRegimeTableProps) {
  const data = rows ?? []

  const columns = useMemo<ColumnDef<RegimePerformanceRow>[]>(
    () => [
      {
        id: 'regime',
        accessorKey: 'regime',
        header: () => <span>Regime</span>,
        cell: ({ getValue }) => (
          <Badge variant={regimeToBadge(String(getValue()))}>{String(getValue())}</Badge>
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
        id: 'sharpe',
        accessorKey: 'sharpe',
        header: () => <span className="text-right block w-full">Sharpe</span>,
        size: 70,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatNumber(Number(getValue()), 2)}
          </span>
        ),
      },
      {
        id: 'trades',
        accessorKey: 'trades',
        header: () => <span className="text-right block w-full">Trades</span>,
        size: 60,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatNumber(Number(getValue()), 0)}
          </span>
        ),
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
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <SectionLabel>Performance by regime</SectionLabel>
      {data.length === 0 && !loading ? (
        <EmptyState
          icon={Workflow}
          title="No per-regime performance"
          description="Populates when strategies with macro_regime metadata have positions."
          className="py-6"
        />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
          <DataTable
            data={data}
            columns={columns}
            rowKey={(r) => r.regime}
            loading={loading}
          />
        </div>
      )}
    </section>
  )
}

function regimeToBadge(
  r: string,
):
  | 'regime-up'
  | 'regime-down'
  | 'regime-range'
  | 'regime-vol'
  | 'default' {
  const s = (r || '').toLowerCase()
  if (s.includes('trending up')) return 'regime-up'
  if (s.includes('trending down')) return 'regime-down'
  if (s.includes('ranging')) return 'regime-range'
  if (s.includes('volatile') || s.includes('high')) return 'regime-vol'
  return 'default'
}
