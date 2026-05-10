import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable, EmptyState } from '@/components/primitives'
import { Activity } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { formatAge, formatTimestamp } from '@/lib/utils'
import type { SystemHealthPayload } from '../useGuardData'

interface Row {
  name: string
  last_run?: string | null
  duration_s?: number | null
  symbols_updated?: number | null
  errors?: number
}

export function BackgroundThreadsTable({
  health,
  loading,
}: {
  health: SystemHealthPayload | null | undefined
  loading?: boolean
}) {
  const rows: Row[] = useMemo(() => {
    const bg = health?.background_threads ?? {}
    return Object.entries(bg).map(([name, v]) => {
      const rec = (v ?? {}) as {
        last_run?: string | null
        duration_s?: number | null
        symbols_updated?: number | null
        errors?: number
      }
      return {
        name,
        last_run: rec.last_run ?? null,
        duration_s: rec.duration_s ?? null,
        symbols_updated: rec.symbols_updated ?? null,
        errors: rec.errors ?? 0,
      }
    })
  }, [health])

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: 'name',
        header: () => 'Thread',
        accessorKey: 'name',
        size: 220,
        cell: ({ row }) => (
          <span className="mono text-[var(--text-0)] font-medium">{row.original.name}</span>
        ),
      },
      {
        id: 'last_run',
        header: () => 'Last run',
        accessorKey: 'last_run',
        size: 160,
        cell: ({ row }) => (
          <div className="flex items-baseline gap-2">
            <span className="mono tabular-nums text-[10px] text-[var(--text-1)]">
              {formatAge(row.original.last_run) || '—'}
            </span>
            <span className="text-[9px] text-[var(--text-3)] truncate">
              {formatTimestamp(row.original.last_run, 'short') || ''}
            </span>
          </div>
        ),
      },
      {
        id: 'duration_s',
        header: () => 'Duration',
        accessorKey: 'duration_s',
        size: 88,
        cell: ({ row }) => {
          const d = row.original.duration_s
          if (d == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-1)]">
              {d.toFixed(2)}s
            </span>
          )
        },
      },
      {
        id: 'symbols_updated',
        header: () => 'Symbols',
        accessorKey: 'symbols_updated',
        size: 88,
        cell: ({ row }) => {
          const n = row.original.symbols_updated
          if (n == null) return <span className="text-[var(--text-3)] text-[10px]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-0)]">{n}</span>
          )
        },
      },
      {
        id: 'errors',
        header: () => 'Errors',
        accessorKey: 'errors',
        size: 72,
        cell: ({ row }) => {
          const e = row.original.errors ?? 0
          return (
            <span
              className="mono tabular-nums"
              style={{ color: e > 0 ? 'var(--pnl-down)' : 'var(--text-1)' }}
            >
              {e}
            </span>
          )
        },
      },
    ],
    [],
  )

  return (
    <section className="space-y-1.5">
      <SectionLabel>Background threads</SectionLabel>
      {rows.length === 0 && !loading ? (
        <EmptyState
          icon={Activity}
          title="No background threads reported"
          description="Shows up once the monitoring service writes its first cycle summary."
        />
      ) : (
        <DataTable
          data={rows}
          columns={columns}
          rowKey={(r) => r.name}
          loading={loading}
          density="compact"
        />
      )}
    </section>
  )
}
