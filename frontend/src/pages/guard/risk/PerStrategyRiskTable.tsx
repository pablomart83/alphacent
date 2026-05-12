import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { DataTable, EmptyState } from '@/components/primitives'
import { Layers } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { formatCurrency, formatPercentage } from '@/lib/utils'
import type { RiskMetricsPayload } from '../useGuardData'

interface PerStrategyRow {
  strategy_name: string
  value: number
  var_contribution_pct: number
}

interface PerStrategyRiskTableProps {
  metrics: RiskMetricsPayload | null | undefined
  loading?: boolean
}

/**
 * PerStrategyRiskTable — surface `risk_breakdown` (a {strategy_name: value}
 * mapping) so the CIO can see which strategies drive portfolio exposure.
 * Backend now resolves UUIDs to human-readable strategy names.
 */
export function PerStrategyRiskTable({ metrics, loading }: PerStrategyRiskTableProps) {
  const [showAll, setShowAll] = useState(false)
  const PAGE = 12

  const rows: PerStrategyRow[] = useMemo(() => {
    const bd = metrics?.risk_breakdown
    if (!bd) return []
    const total = Object.values(bd).reduce((s, v) => s + (Number(v) || 0), 0)
    return Object.entries(bd)
      .map(([strategy_name, value]) => ({
        strategy_name,
        value: Number(value) || 0,
        var_contribution_pct: total > 0 ? (Number(value) / total) * 100 : 0,
      }))
      .sort((a, b) => b.var_contribution_pct - a.var_contribution_pct)
  }, [metrics])

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'var_contribution_pct', desc: true },
  ])

  const visible = showAll ? rows : rows.slice(0, PAGE)

  const columns = useMemo<ColumnDef<PerStrategyRow>[]>(
    () => [
      {
        id: 'strategy_name',
        header: () => 'Strategy',
        accessorKey: 'strategy_name',
        cell: ({ row }) => (
          <span
            className="text-[var(--text-1)] truncate block max-w-[260px] text-[11px]"
            title={row.original.strategy_name}
          >
            {row.original.strategy_name}
          </span>
        ),
      },
      {
        id: 'value',
        header: () => <span className="text-right block w-full">Exposure</span>,
        accessorKey: 'value',
        size: 90,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[10px] text-[var(--text-2)] text-right block">
            {formatCurrency(row.original.value, { precision: 0 })}
          </span>
        ),
      },
      {
        id: 'var_contribution_pct',
        header: () => <span className="text-right block w-full">% of portfolio</span>,
        accessorKey: 'var_contribution_pct',
        size: 160,
        cell: ({ row }) => {
          const pct = row.original.var_contribution_pct
          const color =
            pct >= 15
              ? 'var(--pnl-down)'
              : pct >= 8
                ? 'var(--status-warning)'
                : 'var(--pnl-up)'
          return (
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-[1px] bg-[var(--bg-0)] overflow-hidden">
                <div
                  className="h-full rounded-[1px]"
                  style={{
                    width: `${Math.max(0, Math.min(100, pct))}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
              <span className="mono tabular-nums text-[10px] w-10 text-right" style={{ color }}>
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
      <SectionLabel
        actions={
          rows.length > PAGE ? (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="text-[10px] text-[var(--accent-primary)] hover:underline"
            >
              {showAll ? 'Show less' : `Show all ${rows.length}`}
            </button>
          ) : undefined
        }
      >
        Exposure by strategy
      </SectionLabel>
      {rows.length === 0 && !loading ? (
        <EmptyState
          icon={Layers}
          title="No strategy exposure data"
          description="Appears once open positions are attributed to active strategies."
        />
      ) : (
        <DataTable
          data={visible}
          columns={columns}
          rowKey={(r) => r.strategy_name}
          loading={loading}
          sorting={{ state: sorting, onChange: setSorting }}
          density="compact"
        />
      )}
    </section>
  )
}
