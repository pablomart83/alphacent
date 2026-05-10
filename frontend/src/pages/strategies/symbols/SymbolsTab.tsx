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
 * Current view  = active_strategies + usage_count (what's running right now)
 * Lifetime view = proposed / traded / win_rate / total_pnl / best_template
 *
 * Click a row → SymbolDetailDrawer in a right-side panel. Blacklists and idle
 * demotions live in their own `/strategies/blacklist` tab (spec §3B put them
 * in an accordion here; we split them per operator preference).
 */

type ViewMode = 'current' | 'lifetime'

export function SymbolsTab() {
  const query = useSymbolStats()
  const [search, setSearch] = useState('')
  const [assetClass, setAssetClass] = useState<string>('all')
  const [view, setView] = useState<ViewMode>('current')
  const [selected, setSelected] = useState<string | null>(null)
  const [sorting, setSorting] = useState<SortingState>([
    { id: view === 'current' ? 'active_strategies' : 'traded_count', desc: true },
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
      // For current view: only show rows with proposals, active, or traded activity.
      // For lifetime view: only show rows with any non-zero lifetime stats.
      if (view === 'current') {
        const hasActivity =
          r.active_strategies > 0 || r.usage_count > 0 || r.open_positions > 0
        if (!hasActivity && !q && assetClass === 'all') return false
      } else {
        const hasLifetime =
          r.proposed_count > 0 || r.traded_count > 0 || r.activated_count > 0
        if (!hasLifetime && !q && assetClass === 'all') return false
      }
      return true
    })
  }, [rows, search, assetClass, view])

  const selectedRow = useMemo(
    () => rows.find((r) => r.symbol === selected) ?? null,
    [rows, selected],
  )

  const columns = useMemo<ColumnDef<SymbolStatsRow>[]>(
    () =>
      view === 'current' ? buildCurrentColumns() : buildLifetimeColumns(),
    [view],
  )

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

        <div
          className="inline-flex items-center rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-default)] p-[2px]"
          role="tablist"
          aria-label="View mode"
        >
          {(['current', 'lifetime'] as ViewMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              role="tab"
              aria-selected={view === mode}
              onClick={() => {
                setView(mode)
                setSorting([
                  {
                    id: mode === 'current' ? 'active_strategies' : 'traded_count',
                    desc: true,
                  },
                ])
              }}
              className={`h-6 px-2 text-[10px] uppercase tracking-wider rounded-[2px] transition-colors ${
                view === mode
                  ? 'bg-[var(--accent-primary)] text-white'
                  : 'text-[var(--text-2)] hover:text-[var(--text-0)]'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>

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

/* ──────────────────────────── columns ──────────────────────────── */

function buildCurrentColumns(): ColumnDef<SymbolStatsRow>[] {
  return [
    {
      id: 'symbol',
      header: () => 'Symbol',
      accessorKey: 'symbol',
      size: 100,
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
      size: 90,
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
      size: 130,
      cell: ({ row }) => {
        const s = row.original.sector
        if (!s || s === 'unknown') {
          return <span className="text-[var(--text-3)] text-[10px]">—</span>
        }
        return (
          <span className="text-[var(--text-2)] text-[10px] truncate block max-w-[120px]" title={s}>
            {s}
          </span>
        )
      },
    },
    {
      id: 'active_strategies',
      header: () => 'Active',
      accessorKey: 'active_strategies',
      size: 80,
      cell: ({ row }) => {
        const n = row.original.active_strategies
        if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-0)] font-medium">{n}</span>
        )
      },
    },
    {
      id: 'usage_count',
      header: () => 'Usage',
      accessorKey: 'usage_count',
      size: 80,
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
      size: 72,
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
      id: 'last_signal',
      header: () => 'Last signal',
      accessorKey: 'last_signal',
      size: 140,
      cell: ({ row }) => (
        <span className="text-[10px] text-[var(--text-3)]">
          {fmtDate(row.original.last_signal)}
        </span>
      ),
    },
  ]
}

function buildLifetimeColumns(): ColumnDef<SymbolStatsRow>[] {
  return [
    {
      id: 'symbol',
      header: () => 'Symbol',
      accessorKey: 'symbol',
      size: 100,
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
      size: 90,
      cell: ({ row }) => (
        <Badge variant="muted" size="sm">
          {row.original.asset_class}
        </Badge>
      ),
    },
    {
      id: 'proposed_count',
      header: () => 'Proposed',
      accessorKey: 'proposed_count',
      size: 96,
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
      size: 84,
      cell: ({ row }) => {
        const n = row.original.traded_count
        if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span className="mono tabular-nums text-[var(--text-0)] font-medium">{n}</span>
        )
      },
    },
    {
      id: 'avg_sharpe',
      header: () => 'Sharpe',
      accessorFn: (r) => r.avg_sharpe ?? null,
      size: 88,
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
      size: 80,
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
      size: 104,
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
      size: 220,
      cell: ({ row }) => {
        const t = row.original.best_template
        if (!t) return <span className="text-[var(--text-3)] text-[10px]">—</span>
        return (
          <span
            className="text-[10px] text-[var(--text-2)] truncate block max-w-[210px]"
            title={t}
          >
            {t}
          </span>
        )
      },
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
