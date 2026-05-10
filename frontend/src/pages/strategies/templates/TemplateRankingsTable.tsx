import { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { Trophy } from 'lucide-react'
import {
  Badge,
  DataTable,
  EmptyState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { formatTimestamp } from '@/lib/utils'
import type { TemplateRankingRow, TemplateRow } from '../useStrategiesData'

interface TemplateRankingsTableProps {
  rankings: TemplateRankingRow[]
  templates: TemplateRow[]
  loading?: boolean
}

/**
 * TemplateRankingsTable — leaderboard with family + timeframe filters.
 * Cross-references the template metadata from useTemplates() so users can
 * scope by asset class / direction even though the rankings endpoint itself
 * only returns aggregate stats.
 */
export function TemplateRankingsTable({
  rankings,
  templates,
  loading,
}: TemplateRankingsTableProps) {
  const [family, setFamily] = useState<string>('all')
  const [timeframe, setTimeframe] = useState<string>('all')
  const [direction, setDirection] = useState<string>('all')

  const metadataByName = useMemo(() => {
    const m = new Map<string, TemplateRow>()
    for (const t of templates) m.set(t.name, t)
    return m
  }, [templates])

  const rowsWithMeta = useMemo(
    () =>
      rankings.map((r) => ({
        ...r,
        meta: metadataByName.get(r.name) ?? null,
      })),
    [rankings, metadataByName],
  )

  const familyOptions = useMemo(() => {
    const families = new Set<string>()
    templates.forEach((t) => {
      if (t.strategy_type) families.add(t.strategy_type)
      ;(t.asset_classes ?? []).forEach((c) => families.add(c))
    })
    return Array.from(families).sort()
  }, [templates])

  const filtered = useMemo(() => {
    return rowsWithMeta.filter((r) => {
      if (family !== 'all') {
        const strategyType = r.meta?.strategy_type
        const classes = r.meta?.asset_classes ?? []
        if (strategyType !== family && !classes.includes(family)) return false
      }
      if (timeframe !== 'all') {
        if ((r.meta?.interval ?? '1d') !== timeframe) return false
      }
      if (direction !== 'all') {
        if ((r.meta?.direction ?? '').toLowerCase() !== direction) return false
      }
      return true
    })
  }, [rowsWithMeta, family, timeframe, direction])

  const columns = useMemo<ColumnDef<(typeof filtered)[number]>[]>(
    () => [
      {
        id: 'rank',
        header: () => '#',
        size: 40,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-3)] text-[10px]">
            {row.index + 1}
          </span>
        ),
      },
      {
        id: 'name',
        header: () => 'Template',
        accessorKey: 'name',
        size: 280,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-0)] font-medium truncate block max-w-[260px]"
            title={row.original.name}
          >
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'direction',
        header: () => 'Dir',
        size: 72,
        enableSorting: false,
        cell: ({ row }) => {
          const d = (row.original.meta?.direction ?? '').toLowerCase()
          if (!d) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          const variant: 'success' | 'error' | 'info' =
            d === 'long' ? 'success' : d === 'short' ? 'error' : 'info'
          return (
            <Badge variant={variant} size="sm">
              {d}
            </Badge>
          )
        },
      },
      {
        id: 'interval',
        header: () => 'TF',
        size: 60,
        enableSorting: false,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-1)] text-[10px]">
            {row.original.meta?.interval ?? '1d'}
          </span>
        ),
      },
      {
        id: 'total_trades',
        header: () => 'Trades',
        accessorKey: 'total_trades',
        size: 84,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {row.original.total_trades}
          </span>
        ),
      },
      {
        id: 'win_rate',
        header: () => 'Win %',
        accessorFn: (r) => r.win_rate ?? null,
        size: 88,
        cell: ({ row }) => {
          const wr = row.original.win_rate
          if (wr == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-1)]">
              {wr.toFixed(1)}%
            </span>
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
        id: 'active_count',
        header: () => 'Open',
        accessorKey: 'active_count',
        size: 70,
        cell: ({ row }) => {
          const n = row.original.active_count
          if (n === 0) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-0)] font-medium">
              {n}
            </span>
          )
        },
      },
      {
        id: 'last_proposal_date',
        header: () => 'Last proposed',
        accessorKey: 'last_proposal_date',
        size: 132,
        cell: ({ row }) => (
          <span className="text-[10px] text-[var(--text-3)]">
            {formatTimestamp(row.original.last_proposal_date, 'short') || '—'}
          </span>
        ),
      },
    ],
    [],
  )

  return (
    <section className="flex flex-col gap-2 p-2 border-t border-[var(--border-subtle)]">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Trophy className="h-3.5 w-3.5 text-[var(--text-3)]" />
          <SectionLabel className="mb-0">Template rankings</SectionLabel>
          <span className="text-[10px] text-[var(--text-3)]">
            ({filtered.length} of {rankings.length})
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Select value={family} onValueChange={setFamily}>
            <SelectTrigger size="sm" className="w-[120px]">
              <SelectValue placeholder="Family" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All families</SelectItem>
              {familyOptions.map((f) => (
                <SelectItem key={f} value={f}>
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={timeframe} onValueChange={setTimeframe}>
            <SelectTrigger size="sm" className="w-[96px]">
              <SelectValue placeholder="TF" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All TFs</SelectItem>
              <SelectItem value="1d">1D</SelectItem>
              <SelectItem value="4h">4H</SelectItem>
              <SelectItem value="1h">1H</SelectItem>
            </SelectContent>
          </Select>
          <Select value={direction} onValueChange={setDirection}>
            <SelectTrigger size="sm" className="w-[110px]">
              <SelectValue placeholder="Direction" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any</SelectItem>
              <SelectItem value="long">Long</SelectItem>
              <SelectItem value="short">Short</SelectItem>
              <SelectItem value="both">Both</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      {filtered.length === 0 && !loading ? (
        <EmptyState
          icon={Trophy}
          title="No ranked templates match these filters"
          description="Clear filters to see the full leaderboard."
        />
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          rowKey={(r) => r.name}
          loading={loading}
          density="compact"
          sorting={{ state: [{ id: 'avg_sharpe', desc: true }], onChange: () => {} }}
        />
      )}
    </section>
  )
}
