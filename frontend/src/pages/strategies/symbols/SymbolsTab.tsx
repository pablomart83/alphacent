import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { Search, Globe } from 'lucide-react'
import {
  Badge,
  DataTable,
  EmptyState,
  ErrorState,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { FilterBar, ResizablePanelLayout } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { classifyError } from '@/lib/errors'
import { useSymbolStats, type SymbolStatsRow } from '../useStrategiesData'
import { SymbolDetailDrawer } from './SymbolDetailDrawer'

/**
 * Symbols tab — /strategies/symbols.
 *
 * One table, every column the endpoint provides. Current-state columns
 * (Active, Usage, Open) sit alongside lifetime columns (Proposed, Traded,
 * Sharpe, Win%, P&L, Best template). Sorted by Active desc by default;
 * click any header to re-sort. Row click → detail drawer.
 */

export function SymbolsTab() {
  const query = useSymbolStats()
  const [search, setSearch] = useState('')
  const [assetClass, setAssetClass] = useState<string>('all')
  const [activityFilter, setActivityFilter] = useState<'any' | 'active' | 'traded' | 'all'>(
    'any',
  )
  const [selected, setSelected] = useState<string | null>(null)
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'active_strategies', desc: true },
  ])

  const rows = query.data?.symbols ?? []
  const assetClassOptions = useMemo(
    () =>
      Array.from(new Set(rows.map((r) => r.asset_class))).filter(
        (c) => c && c !== 'unknown',
      ).sort(),
    [rows],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toUpperCase()
    return rows.filter((r) => {
      if (q && !r.symbol.includes(q)) return false
      if (assetClass !== 'all' && r.asset_class !== assetClass) return false
      if (activityFilter === 'active') {
        if (r.active_strategies === 0 && r.open_positions === 0) return false
      } else if (activityFilter === 'traded') {
        if (r.traded_count === 0) return false
      } else if (activityFilter === 'any') {
        // Default — hide rows with zero everything (they clutter the view).
        const anyActivity =
          r.active_strategies > 0 ||
          r.usage_count > 0 ||
          r.open_positions > 0 ||
          r.proposed_count > 0 ||
          r.traded_count > 0
        if (!anyActivity) return false
      }
      // activityFilter === 'all' — no activity filtering.
      return true
    })
  }, [rows, search, assetClass, activityFilter])

  const selectedRow = useMemo(
    () => rows.find((r) => r.symbol === selected) ?? null,
    [rows, selected],
  )

  const columns = useMemo<ColumnDef<SymbolStatsRow>[]>(() => buildColumns(), [])

  if (query.isError) {
    const info = classifyError(query.error, 'symbol stats')
    return (
      <ErrorState
        title="Couldn't load symbols"
        message={info.message}
        onRetry={() => query.refetch()}
      />
    )
  }

  const tableContent = (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      <FilterBar>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-3)] pointer-events-none" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value.toUpperCase())}
            placeholder="Symbol…"
            className="h-7 pl-7 w-[140px] text-[11px] mono"
          />
        </div>
        <Select value={assetClass} onValueChange={setAssetClass}>
          <SelectTrigger size="sm" className="w-[130px]">
            <SelectValue placeholder="Asset class" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All classes</SelectItem>
            {assetClassOptions.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={activityFilter}
          onValueChange={(v) => setActivityFilter(v as typeof activityFilter)}
        >
          <SelectTrigger size="sm" className="w-[150px]">
            <SelectValue placeholder="Activity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="any">Any activity</SelectItem>
            <SelectItem value="active">Active now</SelectItem>
            <SelectItem value="traded">Ever traded</SelectItem>
            <SelectItem value="all">All (including idle)</SelectItem>
          </SelectContent>
        </Select>

        <div className="ml-auto flex items-center gap-2 text-[10px] text-[var(--text-3)]">
          {filtered.length} of {rows.length} symbols
        </div>
      </FilterBar>

      {filtered.length === 0 && !query.isLoading ? (
        <div className="flex-1 min-h-0 flex items-center justify-center">
          <EmptyState
            icon={Globe}
            title="No symbols match"
            description="Clear filters to see the full universe."
          />
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <DataTable
            data={filtered}
            columns={columns}
            rowKey={(r) => r.symbol}
            loading={query.isLoading}
            sorting={{ state: sorting, onChange: setSorting }}
            density="compact"
            onRowClick={(r) => setSelected(r.symbol)}
            activeRowId={selected}
          />
        </div>
      )}
    </div>
  )

  const detailPanel = (
    <SymbolDetailDrawer symbol={selectedRow} onClose={() => setSelected(null)} />
  )

  return selectedRow ? (
    <ResizablePanelLayout
      layoutId="strategies.symbols"
      panels={[
        {
          id: 'symbols-main',
          defaultSize: 62,
          minSize: 40,
          content: tableContent,
        },
        {
          id: 'symbols-detail',
          defaultSize: 38,
          minSize: 24,
          maxSize: 60,
          content: detailPanel,
        },
      ]}
    />
  ) : (
    tableContent
  )
}

/* ──────────────────────────── columns ────────────────────────────
 * One column set covering every field the /strategies/symbols endpoint
 * returns. Grouped mentally as: identity → current → lifetime counts →
 * lifetime perf → context. All sortable; click any header to pivot.
 */

function buildColumns(): ColumnDef<SymbolStatsRow>[] {
  return [
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
      id: 'asset_class',
      header: () => 'Class',
      accessorKey: 'asset_class',
      size: 80,
      cell: ({ row }) => (
        <Badge variant="muted" size="sm">
          {row.original.asset_class}
        </Badge>
      ),
    },
    {
      id: 'sector',
      header: () => 'Sector',
      accessorKey: 'sector',
      size: 120,
      cell: ({ row }) => {
        const s = row.original.sector
        if (!s || s === 'unknown')
          return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span
            className="text-[var(--text-2)] text-[10px] truncate block max-w-[110px]"
            title={s}
          >
            {s}
          </span>
        )
      },
    },
    {
      id: 'active_strategies',
      header: () => 'Active',
      accessorKey: 'active_strategies',
      size: 68,
      cell: ({ row }) => {
        const n = row.original.active_strategies
        if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-0)] font-medium">
            {n}
          </span>
        )
      },
    },
    {
      id: 'usage_count',
      header: () => 'Usage',
      accessorKey: 'usage_count',
      size: 68,
      cell: ({ row }) => (
        <span className="mono tabular-nums text-[var(--text-1)]">
          {row.original.usage_count}
        </span>
      ),
    },
    {
      id: 'open_positions',
      header: () => 'Open',
      accessorKey: 'open_positions',
      size: 64,
      cell: ({ row }) => {
        const n = row.original.open_positions
        if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--accent-primary)] font-medium">
            {n}
          </span>
        )
      },
    },
    {
      id: 'proposed_count',
      header: () => 'Proposed',
      accessorKey: 'proposed_count',
      size: 80,
      cell: ({ row }) => (
        <span className="mono tabular-nums text-[var(--text-1)]">
          {row.original.proposed_count}
        </span>
      ),
    },
    {
      id: 'traded_count',
      header: () => 'Traded',
      accessorKey: 'traded_count',
      size: 76,
      cell: ({ row }) => {
        const n = row.original.traded_count
        if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-0)] font-medium">
            {n}
          </span>
        )
      },
    },
    {
      id: 'avg_sharpe',
      header: () => 'Sharpe',
      accessorFn: (r) => r.avg_sharpe ?? null,
      size: 80,
      cell: ({ row }) => {
        const s = row.original.avg_sharpe
        if (s == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        const color =
          s >= 1.5
            ? 'var(--pnl-up)'
            : s >= 1.0
              ? 'var(--text-0)'
              : s >= 0.5
                ? 'var(--status-warning)'
                : 'var(--pnl-down)'
        return (
          <span className="mono tabular-nums" style={{ color }}>
            {s.toFixed(2)}
          </span>
        )
      },
    },
    {
      id: 'avg_win_rate',
      header: () => 'Win %',
      accessorFn: (r) => r.avg_win_rate ?? null,
      size: 72,
      cell: ({ row }) => {
        const wr = row.original.avg_win_rate
        if (wr == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {(wr * 100).toFixed(0)}%
          </span>
        )
      },
    },
    {
      id: 'total_pnl',
      header: () => 'P&L',
      accessorFn: (r) => r.total_pnl ?? null,
      size: 96,
      cell: ({ row }) => {
        const p = row.original.total_pnl
        if (p == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <PnLNumber value={p} format="currency" precision={0} size="sm" showSign />
        )
      },
    },
    {
      id: 'best_template',
      header: () => 'Best template',
      accessorKey: 'best_template',
      size: 200,
      cell: ({ row }) => {
        const t = row.original.best_template
        if (!t) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span
            className="text-[10px] text-[var(--text-2)] truncate block max-w-[190px]"
            title={t}
          >
            {t}
          </span>
        )
      },
    },
    {
      id: 'last_signal',
      header: () => 'Last signal',
      accessorKey: 'last_signal',
      size: 124,
      cell: ({ row }) => (
        <span className="text-[10px] text-[var(--text-3)]">
          {fmtDate(row.original.last_signal)}
        </span>
      ),
    },
  ]
}

function fmtDate(iso?: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso.endsWith('Z') ? iso : `${iso}Z`)
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return '—'
  }
}
