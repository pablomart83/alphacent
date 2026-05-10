import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { DataTable, EmptyState } from '@/components/primitives'
import { Layers } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { formatPercentage } from '@/lib/utils'
import type { RiskMetricsPayload } from '../useGuardData'

interface PerStrategyRow {
  strategy_id: string
  var_contribution_pct: number
}

interface PerStrategyRiskTableProps {
  metrics: RiskMetricsPayload | null | undefined
  loading?: boolean
}

/**
 * PerStrategyRiskTable — surface `risk_breakdown` (a {strategy_id: pct}
 * mapping) so the CIO can see which strategies drive portfolio VaR.
 */
export function PerStrategyRiskTable({ metrics, loading }: PerStrategyRiskTableProps) {
  const rows: PerStrategyRow[] = useMemo(() => {
    const bd = metrics?.risk_breakdown
    if (!bd) return []
    return Object.entries(bd).map(([strategy_id, var_contribution_pct]) => ({
      strategy_id,
      var_contribution_pct: Number(var_contribution_pct) || 0,
    }))
  }, [metrics])

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'var_contribution_pct', desc: true },
  ])

  const columns = useMemo<ColumnDef<PerStrategyRow>[]>(
    () => [
      {
        id: 'strategy_id',
        header: () => 'Strategy',
        accessorKey: 'strategy_id',
        size: 300,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-1)] truncate block max-w-[280px]"
            title={row.original.strategy_id}
          >
            {row.original.strategy_id}
          </span>
        ),
      },
      {
        id: 'var_contribution_pct',
        header: () => 'VaR contribution',
        accessorKey: 'var_contribution_pct',
        size: 180,
        cell: ({ row }) => {
          const pct = row.original.var_contribution_pct
          const color =
            pct >= 30
              ? 'var(--pnl-down)'
              : pct >= 15
                ? 'var(--status-warning)'
                : 'var(--text-1)'
          return (
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-[1px] bg-[var(--bg-0)] overflow-hidden">
                <div
                  className="h-full"
                  style={{
                    width: `${Math.max(0, Math.min(100, pct))}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
              <span className="mono tabular-nums text-[10px]" style={{ color }}>
                {formatPercentage(pct, { precision: 1 })}
              </span>
            </div>
          )
        },
      },
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <SectionLabel>Risk by strategy</SectionLabel>
      {rows.length === 0 && !loading ? (
        <EmptyState
          icon={Layers}
          title="No strategy-level VaR contributions"
          description="Appears once open positions are attributed to active strategies."
        />
      ) : (
        <DataTable
          data={rows}
          columns={columns}
          rowKey={(r) => r.strategy_id}
          loading={loading}
          sorting={{ state: sorting, onChange: setSorting }}
          density="compact"
        />
      )}
    </section>
  )
}
