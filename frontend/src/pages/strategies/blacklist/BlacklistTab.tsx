import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { Moon, ShieldOff } from 'lucide-react'
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
import { FilterBar, SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { formatTimestamp } from '@/lib/utils'
import {
  useBlacklistedCombos,
  useIdleDemotions,
  type BlacklistEntry,
  type IdleDemotionEntry,
} from '../useStrategiesData'

/**
 * Blacklist tab — /strategies/blacklist.
 *
 * Two read-only tables stacked vertically:
 *   · Rejection blacklist — (template × symbol) pairs under cooldown
 *   · Idle demotions      — strategies demoted for inactivity / flat P&L
 *
 * Spec §3B nested these under the Symbols tab as an accordion; they were
 * split into their own tab per operator preference. Investigation surface,
 * no actions — the proposer and autonomous cycle own the state here.
 */
export function BlacklistTab() {
  const [search, setSearch] = useState('')
  const [bType, setBType] = useState<string>('all')
  const blacklist = useBlacklistedCombos()
  const idle = useIdleDemotions()

  const blEntries = blacklist.data?.entries ?? []
  const idleEntries = idle.data?.entries ?? []

  const typeOptions = useMemo(
    () =>
      Array.from(new Set(blEntries.map((e) => e.type))).sort(),
    [blEntries],
  )

  const filteredBlacklist = useMemo(() => {
    const q = search.trim().toUpperCase()
    return blEntries.filter((e) => {
      if (bType !== 'all' && e.type !== bType) return false
      if (q) {
        const hay = `${e.template} ${e.symbol} ${e.type}`.toUpperCase()
        if (!hay.includes(q)) return false
      }
      return true
    })
  }, [blEntries, search, bType])

  const filteredIdle = useMemo(() => {
    const q = search.trim().toUpperCase()
    if (!q) return idleEntries
    return idleEntries.filter((e) =>
      `${e.name} ${e.reason}`.toUpperCase().includes(q),
    )
  }, [idleEntries, search])

  if (blacklist.isError) {
    const info = classifyError(blacklist.error, 'blacklist')
    return (
      <ErrorState
        title="Couldn't load blacklist"
        message={info.message}
        onRetry={() => blacklist.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      <FilterBar>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search template, symbol, strategy…"
          className="h-7 w-[260px] text-[11px]"
        />
        <Select value={bType} onValueChange={setBType}>
          <SelectTrigger size="sm" className="w-[170px]">
            <SelectValue placeholder="Rejection type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All rejection types</SelectItem>
            {typeOptions.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="ml-auto flex items-center gap-2 text-[10px] text-[var(--text-3)]">
          {filteredBlacklist.length} blacklisted · {filteredIdle.length} idle demoted
        </div>
      </FilterBar>

      <div className="flex-1 min-h-0 overflow-auto">
        <BlacklistSection
          entries={filteredBlacklist}
          totalUnfiltered={blEntries.length}
          loading={blacklist.isLoading}
        />
        <IdleSection
          entries={filteredIdle}
          totalUnfiltered={idleEntries.length}
          loading={idle.isLoading}
        />
      </div>
    </div>
  )
}

/* ──────────────────────────── Blacklist ──────────────────────────── */

function BlacklistSection({
  entries,
  totalUnfiltered,
  loading,
}: {
  entries: BlacklistEntry[]
  totalUnfiltered: number
  loading: boolean
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'timestamp', desc: true },
  ])

  const columns = useMemo<ColumnDef<BlacklistEntry>[]>(
    () => [
      {
        id: 'type',
        header: () => 'Type',
        accessorKey: 'type',
        size: 150,
        cell: ({ row }) => (
          <Badge variant="error" size="sm">
            {row.original.type}
          </Badge>
        ),
      },
      {
        id: 'template',
        header: () => 'Template',
        accessorKey: 'template',
        size: 280,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-1)] truncate block max-w-[260px]"
            title={row.original.template}
          >
            {row.original.template}
          </span>
        ),
      },
      {
        id: 'symbol',
        header: () => 'Symbol',
        accessorKey: 'symbol',
        size: 110,
        cell: ({ row }) => (
          <span className="mono text-[var(--text-0)] font-medium">
            {row.original.symbol}
          </span>
        ),
      },
      {
        id: 'count',
        header: () => 'Count',
        accessorKey: 'count',
        size: 80,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {row.original.count}
          </span>
        ),
      },
      {
        id: 'timestamp',
        header: () => 'Recorded',
        accessorKey: 'timestamp',
        size: 160,
        cell: ({ row }) => (
          <span className="text-[10px] text-[var(--text-3)]">
            {formatTimestamp(row.original.timestamp, 'short')}
          </span>
        ),
      },
    ],
    [],
  )

  return (
    <section className="flex flex-col gap-2 px-2 py-3">
      <header className="flex items-center gap-2">
        <ShieldOff className="h-3.5 w-3.5 text-[var(--text-3)]" />
        <SectionLabel className="mb-0">Rejection blacklist</SectionLabel>
        <span className="mono tabular-nums text-[10px] text-[var(--text-1)]">
          {totalUnfiltered}
        </span>
        <span className="text-[10px] text-[var(--text-3)]">
          · 14-day cooldown · regime-scoped early expiry
        </span>
      </header>

      {entries.length === 0 && !loading ? (
        <EmptyState
          icon={ShieldOff}
          title="No blacklisted combos"
          description="Proposer can see every (template, symbol) pair right now."
        />
      ) : (
        <DataTable
          data={entries}
          columns={columns}
          rowKey={(e) => `${e.template}::${e.symbol}::${e.timestamp}`}
          loading={loading}
          sorting={{ state: sorting, onChange: setSorting }}
          density="compact"
        />
      )}
    </section>
  )
}

/* ──────────────────────────── Idle demotions ──────────────────────────── */

function IdleSection({
  entries,
  totalUnfiltered,
  loading,
}: {
  entries: IdleDemotionEntry[]
  totalUnfiltered: number
  loading: boolean
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'timestamp', desc: true },
  ])

  const columns = useMemo<ColumnDef<IdleDemotionEntry>[]>(
    () => [
      {
        id: 'name',
        header: () => 'Strategy',
        accessorKey: 'name',
        size: 320,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-1)] truncate block max-w-[300px]"
            title={row.original.name}
          >
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'reason',
        header: () => 'Reason',
        accessorKey: 'reason',
        size: 340,
        cell: ({ row }) => (
          <span
            className="text-[10px] text-[var(--text-2)] truncate block max-w-[320px]"
            title={row.original.reason}
          >
            {row.original.reason}
          </span>
        ),
      },
      {
        id: 'timestamp',
        header: () => 'Demoted',
        accessorKey: 'timestamp',
        size: 160,
        cell: ({ row }) => (
          <span className="text-[10px] text-[var(--text-3)]">
            {formatTimestamp(row.original.timestamp, 'short')}
          </span>
        ),
      },
    ],
    [],
  )

  return (
    <section className="flex flex-col gap-2 px-2 py-3 border-t border-[var(--border-subtle)]">
      <header className="flex items-center gap-2">
        <Moon className="h-3.5 w-3.5 text-[var(--text-3)]" />
        <SectionLabel className="mb-0">Idle demotions</SectionLabel>
        <span className="mono tabular-nums text-[10px] text-[var(--text-1)]">
          {totalUnfiltered}
        </span>
        <span className="text-[10px] text-[var(--text-3)]">
          · strategies demoted for inactivity or persistent flat P&amp;L
        </span>
      </header>

      {entries.length === 0 && !loading ? (
        <EmptyState
          icon={Moon}
          title="No idle demotions"
          description="All active strategies are producing signals."
        />
      ) : (
        <DataTable
          data={entries}
          columns={columns}
          rowKey={(e) => `${e.strategy_id}::${e.timestamp}`}
          loading={loading}
          sorting={{ state: sorting, onChange: setSorting }}
          density="compact"
        />
      )}
    </section>
  )
}
