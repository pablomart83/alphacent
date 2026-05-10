import { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { ChevronDown, ChevronRight, ShieldOff, Moon } from 'lucide-react'
import {
  Badge,
  DataTable,
  EmptyState,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatTimestamp } from '@/lib/utils'
import {
  useBlacklistedCombos,
  useIdleDemotions,
  type BlacklistEntry,
  type IdleDemotionEntry,
} from '../useStrategiesData'

/**
 * BlacklistAccordion — collapsible panels surfacing the
 * rejection_blacklist and idle-demotions tables. Both read-only:
 * investigation surfaces, not action surfaces.
 */
export function BlacklistAccordion() {
  const blacklist = useBlacklistedCombos()
  const idleDemotions = useIdleDemotions()

  const [blOpen, setBlOpen] = useState(true)
  const [idleOpen, setIdleOpen] = useState(false)

  const blEntries = blacklist.data?.entries ?? []
  const idleEntries = idleDemotions.data?.entries ?? []

  return (
    <div className="flex flex-col gap-2 p-2 border-t border-[var(--border-subtle)]">
      <AccordionPanel
        icon={<ShieldOff className="h-3.5 w-3.5 text-[var(--text-3)]" />}
        title="Blacklisted combos"
        count={blEntries.length}
        open={blOpen}
        onToggle={() => setBlOpen((v) => !v)}
        subtitle="Rejection blacklist · 14-day cooldown, regime-scoped early expiry"
      >
        {blacklist.isLoading ? (
          <div className="text-[10px] text-[var(--text-3)] py-2 px-1">Loading…</div>
        ) : blEntries.length === 0 ? (
          <EmptyState
            icon={ShieldOff}
            title="No blacklisted combos"
            description="Proposer can see every (template, symbol) pair."
          />
        ) : (
          <BlacklistTable entries={blEntries} />
        )}
      </AccordionPanel>

      <AccordionPanel
        icon={<Moon className="h-3.5 w-3.5 text-[var(--text-3)]" />}
        title="Idle demotions"
        count={idleEntries.length}
        open={idleOpen}
        onToggle={() => setIdleOpen((v) => !v)}
        subtitle="Strategies demoted for inactivity or persistent flat P&L"
      >
        {idleDemotions.isLoading ? (
          <div className="text-[10px] text-[var(--text-3)] py-2 px-1">Loading…</div>
        ) : idleEntries.length === 0 ? (
          <EmptyState
            icon={Moon}
            title="No idle demotions"
            description="All active strategies are producing signals."
          />
        ) : (
          <IdleTable entries={idleEntries} />
        )}
      </AccordionPanel>
    </div>
  )
}

interface AccordionPanelProps {
  icon: React.ReactNode
  title: string
  subtitle?: string
  count: number
  open: boolean
  onToggle: () => void
  children: React.ReactNode
}

function AccordionPanel({
  icon,
  title,
  subtitle,
  count,
  open,
  onToggle,
  children,
}: AccordionPanelProps) {
  return (
    <section className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
      <button
        type="button"
        onClick={onToggle}
        className={cn(
          'w-full flex items-center gap-2 px-2 py-1.5 text-left',
          'hover:bg-[var(--bg-hover)]',
        )}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="h-3 w-3 text-[var(--text-3)]" />
        ) : (
          <ChevronRight className="h-3 w-3 text-[var(--text-3)]" />
        )}
        {icon}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <SectionLabel className="mb-0">{title}</SectionLabel>
            <span className="mono tabular-nums text-[10px] text-[var(--text-1)]">
              {count}
            </span>
          </div>
          {subtitle && (
            <p className="text-[10px] text-[var(--text-3)] mt-0.5 truncate" title={subtitle}>
              {subtitle}
            </p>
          )}
        </div>
      </button>
      {open && <div className="border-t border-[var(--border-subtle)]">{children}</div>}
    </section>
  )
}

function BlacklistTable({ entries }: { entries: BlacklistEntry[] }) {
  const columns = useMemo<ColumnDef<BlacklistEntry>[]>(
    () => [
      {
        id: 'type',
        header: () => 'Type',
        size: 110,
        cell: ({ row }) => (
          <Badge variant="error" size="sm">
            {row.original.type}
          </Badge>
        ),
      },
      {
        id: 'template',
        header: () => 'Template',
        accessorKey: 'template' as const,
        size: 260,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-1)] truncate block max-w-[240px]"
            title={row.original.template}
          >
            {row.original.template}
          </span>
        ),
      },
      {
        id: 'symbol',
        header: () => 'Symbol',
        accessorKey: 'symbol' as const,
        size: 100,
        cell: ({ row }) => (
          <span className="mono text-[var(--text-0)] font-medium">
            {row.original.symbol}
          </span>
        ),
      },
      {
        id: 'count',
        header: () => 'Count',
        accessorKey: 'count' as const,
        size: 72,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-1)]">
            {row.original.count}
          </span>
        ),
      },
      {
        id: 'timestamp',
        header: () => 'Recorded',
        accessorKey: 'timestamp' as const,
        size: 148,
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
    <DataTable
      data={entries}
      columns={columns}
      rowKey={(e) => `${e.template}::${e.symbol}::${e.timestamp}`}
      density="compact"
    />
  )
}

function IdleTable({ entries }: { entries: IdleDemotionEntry[] }) {
  const columns = useMemo<ColumnDef<IdleDemotionEntry>[]>(
    () => [
      {
        id: 'name',
        header: () => 'Strategy',
        accessorKey: 'name' as const,
        size: 300,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-1)] truncate block max-w-[280px]"
            title={row.original.name}
          >
            {row.original.name}
          </span>
        ),
      },
      {
        id: 'reason',
        header: () => 'Reason',
        accessorKey: 'reason' as const,
        size: 260,
        cell: ({ row }) => (
          <span
            className="text-[10px] text-[var(--text-2)] truncate block max-w-[250px]"
            title={row.original.reason}
          >
            {row.original.reason}
          </span>
        ),
      },
      {
        id: 'timestamp',
        header: () => 'Demoted',
        accessorKey: 'timestamp' as const,
        size: 148,
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
    <DataTable
      data={entries}
      columns={columns}
      rowKey={(e) => `${e.strategy_id}::${e.timestamp}`}
      density="compact"
    />
  )
}
