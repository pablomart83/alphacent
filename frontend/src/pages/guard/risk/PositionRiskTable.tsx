import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import {
  Badge,
  DataTable,
  EmptyState,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { Search, ShieldAlert } from 'lucide-react'
import { FilterBar, SectionLabel } from '@/components/layout'
import { formatCurrency, formatPercentage } from '@/lib/utils'
import type { PositionRiskRow } from '../useGuardData'

interface PositionRiskTableProps {
  rows: PositionRiskRow[] | null | undefined
  loading?: boolean
}

type LevelFilter = 'all' | 'high' | 'medium' | 'low'

const LEVEL_VARIANT: Record<string, 'error' | 'warning' | 'success' | 'muted'> = {
  high: 'error',
  medium: 'warning',
  low: 'success',
}

export function PositionRiskTable({ rows, loading }: PositionRiskTableProps) {
  const [search, setSearch] = useState('')
  const [level, setLevel] = useState<LevelFilter>('all')
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'risk_percent', desc: true },
  ])

  const filtered = useMemo(() => {
    const source = rows ?? []
    const q = search.trim().toUpperCase()
    return source.filter((r) => {
      if (level !== 'all' && r.risk_level !== level) return false
      if (q) {
        const hay = `${r.symbol} ${r.strategy_id}`.toUpperCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [rows, search, level])

  const columns = useMemo<ColumnDef<PositionRiskRow>[]>(
    () => [
      {
        id: 'risk_level',
        header: () => 'Level',
        accessorKey: 'risk_level',
        size: 86,
        cell: ({ row }) => (
          <Badge
            variant={LEVEL_VARIANT[row.original.risk_level] ?? 'muted'}
            size="sm"
          >
            {row.original.risk_level}
          </Badge>
        ),
      },
      {
        id: 'symbol',
        header: () => 'Symbol',
        accessorKey: 'symbol',
        size: 96,
        cell: ({ row }) => (
          <span className="mono text-[var(--text-0)] font-medium">
            {row.original.symbol}
          </span>
        ),
      },
      {
        id: 'strategy_id',
        header: () => 'Strategy',
        accessorKey: 'strategy_id',
        size: 260,
        cell: ({ row }) => (
          <span
            className="text-[10px] text-[var(--text-2)] truncate block max-w-[240px]"
            title={row.original.strategy_id}
          >
            {row.original.strategy_id}
          </span>
        ),
      },
      {
        id: 'risk_amount',
        header: () => 'Risk $',
        accessorKey: 'risk_amount',
        size: 100,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {formatCurrency(row.original.risk_amount, { precision: 0 })}
          </span>
        ),
      },
      {
        id: 'risk_percent',
        header: () => 'Risk %',
        accessorKey: 'risk_percent',
        size: 88,
        cell: ({ row }) => {
          const p = row.original.risk_percent
          const color =
            p > 10
              ? 'var(--pnl-down)'
              : p > 5
                ? 'var(--status-warning)'
                : 'var(--text-1)'
          return (
            <span className="mono tabular-nums" style={{ color }}>
              {formatPercentage(p, { precision: 2 })}
            </span>
          )
        },
      },
      {
        id: 'stop_loss',
        header: () => 'SL',
        accessorFn: (r) => r.stop_loss ?? null,
        size: 90,
        cell: ({ row }) => {
          const sl = row.original.stop_loss
          if (sl == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-1)]">
              {sl.toFixed(2)}
            </span>
          )
        },
      },
      {
        id: 'take_profit',
        header: () => 'TP',
        accessorFn: (r) => r.take_profit ?? null,
        size: 90,
        cell: ({ row }) => {
          const tp = row.original.take_profit
          if (tp == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-1)]">
              {tp.toFixed(2)}
            </span>
          )
        },
      },
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <div className="flex items-center justify-between">
        <SectionLabel className="mb-0">Position risk</SectionLabel>
        <span className="text-[10px] text-[var(--text-3)]">
          {filtered.length} of {rows?.length ?? 0}
        </span>
      </div>
      <FilterBar className="px-0">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-3)] pointer-events-none" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value.toUpperCase())}
            placeholder="Symbol / strategy…"
            className="h-7 pl-7 w-[220px] text-[11px] mono"
          />
        </div>
        <Select value={level} onValueChange={(v) => setLevel(v as LevelFilter)}>
          <SelectTrigger size="sm" className="w-[120px]">
            <SelectValue placeholder="Level" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All levels</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>
      </FilterBar>

      {filtered.length === 0 && !loading ? (
        <EmptyState
          icon={ShieldAlert}
          title="No positions matched"
          description="Clear filters to see all open positions."
        />
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          rowKey={(r) => r.position_id}
          loading={loading}
          sorting={{ state: sorting, onChange: setSorting }}
          density="compact"
        />
      )}
    </section>
  )
}
