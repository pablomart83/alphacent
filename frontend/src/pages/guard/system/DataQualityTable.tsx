import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { Search, Shield } from 'lucide-react'
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
import { FilterBar, SectionLabel } from '@/components/layout'
import type { DataQualityEntry } from '../useGuardData'

interface DataQualityTableProps {
  entries: DataQualityEntry[] | null | undefined
  loading?: boolean
}

type Bucket = 'all' | 'excellent' | 'good' | 'fair' | 'poor'

const BUCKET_RANGE: Record<Bucket, [number, number]> = {
  all: [0, 101],
  excellent: [90, 101],
  good: [75, 90],
  fair: [50, 75],
  poor: [0, 50],
}

export function DataQualityTable({ entries, loading }: DataQualityTableProps) {
  const [search, setSearch] = useState('')
  const [assetClass, setAssetClass] = useState<string>('all')
  const [bucket, setBucket] = useState<Bucket>('all')
  const [sorting, setSorting] = useState<SortingState>([{ id: 'score', desc: true }])

  const classOptions = useMemo(() => {
    const set = new Set<string>()
    ;(entries ?? []).forEach((e) => {
      if (e.asset_class && e.asset_class !== 'unknown') set.add(e.asset_class)
    })
    return Array.from(set).sort()
  }, [entries])

  const filtered = useMemo(() => {
    const q = search.trim().toUpperCase()
    const range = BUCKET_RANGE[bucket]
    return (entries ?? []).filter((e) => {
      if (q && !e.symbol.toUpperCase().includes(q)) return false
      if (assetClass !== 'all' && e.asset_class !== assetClass) return false
      // When bucket is 'all', include entries with null/missing scores too.
      // Only apply the score range filter when a specific bucket is selected.
      if (bucket !== 'all') {
        const score = typeof e.score === 'number' ? e.score : -1
        if (score < range[0] || score >= range[1]) return false
      }
      return true
    })
  }, [entries, search, assetClass, bucket])

  const columns = useMemo<ColumnDef<DataQualityEntry>[]>(
    () => [
      {
        id: 'symbol',
        header: () => 'Symbol',
        accessorKey: 'symbol',
        size: 100,
        cell: ({ row }) => (
          <span className="mono text-[var(--text-0)] font-medium">{row.original.symbol}</span>
        ),
      },
      {
        id: 'asset_class',
        header: () => 'Class',
        accessorKey: 'asset_class',
        size: 80,
        cell: ({ row }) => (
          <Badge variant="muted" size="sm">
            {row.original.asset_class ?? 'unknown'}
          </Badge>
        ),
      },
      {
        id: 'score',
        header: () => 'Score',
        accessorFn: (r) => (typeof r.score === 'number' ? r.score : null),
        size: 200,
        cell: ({ row }) => {
          const s = row.original.score
          if (typeof s !== 'number') {
            return <span className="text-[var(--text-3)] text-[10px]">—</span>
          }
          const color =
            s >= 90
              ? 'var(--pnl-up)'
              : s >= 75
                ? 'var(--text-0)'
                : s >= 50
                  ? 'var(--status-warning)'
                  : 'var(--pnl-down)'
          return (
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1.5 rounded-[1px] bg-[var(--bg-0)] overflow-hidden">
                <div
                  className="h-full"
                  style={{
                    width: `${Math.max(0, Math.min(100, s))}%`,
                    backgroundColor: color,
                  }}
                />
              </div>
              <span className="mono tabular-nums text-[10px]" style={{ color }}>
                {s.toFixed(0)}
              </span>
            </div>
          )
        },
      },
      {
        id: 'issues',
        header: () => 'Issues',
        accessorFn: (r) => (r.issues ?? []).length,
        size: 260,
        cell: ({ row }) => {
          const issues = row.original.issues ?? []
          if (!issues.length) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <div className="flex flex-wrap gap-1">
              {issues.slice(0, 3).map((issue, i) => (
                <Badge key={`${issue}-${i}`} variant="warning" size="sm" title={issue}>
                  {issue}
                </Badge>
              ))}
              {issues.length > 3 && (
                <span className="text-[9px] text-[var(--text-3)]">+{issues.length - 3}</span>
              )}
            </div>
          )
        },
      },
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel className="mb-0">Data quality</SectionLabel>
        <span className="text-[10px] text-[var(--text-3)]">
          {filtered.length} of {entries?.length ?? 0}
        </span>
      </div>
      <FilterBar className="px-0">
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
            <SelectValue placeholder="Class" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All classes</SelectItem>
            {classOptions.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={bucket} onValueChange={(v) => setBucket(v as Bucket)}>
          <SelectTrigger size="sm" className="w-[140px]">
            <SelectValue placeholder="Bucket" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All scores</SelectItem>
            <SelectItem value="excellent">Excellent ≥ 90</SelectItem>
            <SelectItem value="good">Good 75-90</SelectItem>
            <SelectItem value="fair">Fair 50-75</SelectItem>
            <SelectItem value="poor">Poor &lt; 50</SelectItem>
          </SelectContent>
        </Select>
      </FilterBar>
      {filtered.length === 0 && !loading ? (
        <EmptyState
          icon={Shield}
          title="No rows match"
          description="Clear filters to see the full list of symbols."
        />
      ) : (
        <DataTable
          data={filtered}
          columns={columns}
          rowKey={(r) => r.symbol}
          loading={loading}
          density="compact"
          sorting={{ state: sorting, onChange: setSorting }}
        />
      )}
    </section>
  )
}
