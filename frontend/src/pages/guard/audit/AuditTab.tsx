import { useMemo, useState } from 'react'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import {
  ChevronDown,
  ChevronRight,
  Download,
  FileSearch,
  Search,
} from 'lucide-react'
import {
  Badge,
  Button,
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
import { FilterBar } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { formatAge, formatTimestamp } from '@/lib/utils'
import {
  buildAuditExportUrl,
  useAuditLog,
  type AuditEventType,
  type AuditLogEntry,
} from '../useGuardData'
import { TradeLifecycleChain } from './TradeLifecycleChain'

type SeverityFilter = 'all' | 'info' | 'warning' | 'danger'

const SEVERITY_VARIANT: Record<string, 'info' | 'warning' | 'error'> = {
  info: 'info',
  warning: 'warning',
  danger: 'error',
  critical: 'error',
  error: 'error',
}

const EVENT_TYPE_OPTIONS: Array<{ value: AuditEventType | 'all'; label: string }> = [
  { value: 'all', label: 'All events' },
  { value: 'signal', label: 'Signal' },
  { value: 'order', label: 'Order' },
  { value: 'position', label: 'Position' },
  { value: 'strategy', label: 'Strategy' },
  { value: 'rejection', label: 'Rejection' },
]

/**
 * AuditTab — filterable audit log with expand-for-lifecycle drill-down.
 * CSV export is a direct link so the browser streams it.
 *
 * Only trade entries (orders / positions) render the TradeLifecycleChain
 * drawer — signal / strategy / rejection rows don't have a lifecycle endpoint
 * target so their expand row shows inline metadata instead.
 */
export function AuditTab() {
  const [eventType, setEventType] = useState<AuditEventType | 'all'>('all')
  const [severity, setSeverity] = useState<SeverityFilter>('all')
  const [search, setSearch] = useState('')
  const [symbol, setSymbol] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'timestamp', desc: true },
  ])

  const filters = useMemo(
    () => ({
      event_types: eventType === 'all' ? undefined : [eventType as AuditEventType],
      severity: severity === 'all' ? null : severity,
      symbol: symbol.trim() || null,
      search: search.trim() || null,
      limit: 200,
    }),
    [eventType, severity, symbol, search],
  )

  const log = useAuditLog(filters)
  const rows = log.data?.entries ?? []

  const columns = useMemo<ColumnDef<AuditLogEntry>[]>(
    () => [
      {
        id: 'expand',
        header: () => '',
        size: 26,
        enableSorting: false,
        cell: ({ row }) => {
          const canExpand = canDrillDown(row.original)
          return (
            <button
              type="button"
              className="inline-flex items-center justify-center h-5 w-5 text-[var(--text-3)] hover:text-[var(--text-0)] disabled:opacity-30"
              disabled={!canExpand}
              title={
                canExpand
                  ? expanded === row.original.id
                    ? 'Collapse'
                    : 'Expand lifecycle'
                  : 'No lifecycle for this event'
              }
              onClick={(e) => {
                e.stopPropagation()
                setExpanded((cur) => (cur === row.original.id ? null : row.original.id))
              }}
            >
              {expanded === row.original.id ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
            </button>
          )
        },
      },
      {
        id: 'event_type',
        header: () => 'Type',
        accessorKey: 'event_type',
        size: 110,
        cell: ({ row }) => (
          <Badge variant="muted" size="sm">
            {row.original.event_type}
          </Badge>
        ),
      },
      {
        id: 'severity',
        header: () => 'Severity',
        accessorKey: 'severity',
        size: 96,
        cell: ({ row }) => (
          <Badge
            variant={SEVERITY_VARIANT[row.original.severity] ?? 'muted'}
            size="sm"
          >
            {row.original.severity}
          </Badge>
        ),
      },
      {
        id: 'symbol',
        header: () => 'Symbol',
        accessorKey: 'symbol',
        size: 90,
        cell: ({ row }) =>
          row.original.symbol ? (
            <span className="mono text-[var(--text-0)] font-medium">
              {row.original.symbol}
            </span>
          ) : (
            <span className="text-[var(--text-3)] text-[10px]">—</span>
          ),
      },
      {
        id: 'strategy_name',
        header: () => 'Strategy',
        accessorKey: 'strategy_name',
        size: 220,
        cell: ({ row }) =>
          row.original.strategy_name ? (
            <span
              className="text-[10px] text-[var(--text-2)] truncate block max-w-[200px]"
              title={row.original.strategy_name}
            >
              {row.original.strategy_name}
            </span>
          ) : (
            <span className="text-[var(--text-3)] text-[10px]">—</span>
          ),
      },
      {
        id: 'description',
        header: () => 'Description',
        accessorKey: 'description',
        size: 420,
        cell: ({ row }) => (
          <span
            className="text-[10px] text-[var(--text-1)] truncate block max-w-[400px]"
            title={row.original.description}
          >
            {row.original.description}
          </span>
        ),
      },
      {
        id: 'timestamp',
        header: () => 'When',
        accessorKey: 'timestamp',
        size: 140,
        cell: ({ row }) => (
          <div className="flex items-baseline gap-1.5">
            <span className="mono tabular-nums text-[10px] text-[var(--text-1)]">
              {formatAge(row.original.timestamp) || '—'}
            </span>
            <span className="text-[9px] text-[var(--text-3)] truncate">
              {formatTimestamp(row.original.timestamp, 'short') || ''}
            </span>
          </div>
        ),
      },
    ],
    [expanded],
  )

  if (log.isError) {
    const info = classifyError(log.error, 'audit log')
    return (
      <ErrorState
        title="Couldn't load audit log"
        message={info.message}
        onRetry={() => log.refetch()}
      />
    )
  }

  const expandedRow = rows.find((r) => r.id === expanded) ?? null
  const exportUrl = buildAuditExportUrl(filters)

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      <FilterBar>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-3)] pointer-events-none" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search description…"
            className="h-7 pl-7 w-[260px] text-[11px]"
          />
        </div>
        <Input
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Symbol"
          className="h-7 w-[120px] mono text-[11px]"
        />
        <Select
          value={eventType as string}
          onValueChange={(v) => setEventType(v as AuditEventType | 'all')}
        >
          <SelectTrigger size="sm" className="w-[140px]">
            <SelectValue placeholder="Event type" />
          </SelectTrigger>
          <SelectContent>
            {EVENT_TYPE_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value as string}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={severity}
          onValueChange={(v) => setSeverity(v as SeverityFilter)}
        >
          <SelectTrigger size="sm" className="w-[130px]">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All severities</SelectItem>
            <SelectItem value="info">Info</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="danger">Danger</SelectItem>
          </SelectContent>
        </Select>

        <div className="ml-auto flex items-center gap-2">
          <div className="text-[10px] text-[var(--text-3)]">
            {rows.length} of {log.data?.total ?? 0}
          </div>
          <Button
            asChild
            size="sm"
            variant="secondary"
            className="gap-1.5"
          >
            <a
              href={exportUrl}
              target="_blank"
              rel="noreferrer"
              download="alphacent-audit.csv"
            >
              <Download className="h-3 w-3" />
              Export CSV
            </a>
          </Button>
        </div>
      </FilterBar>

      <div className="flex-1 min-h-0 overflow-auto px-3 py-3 space-y-2">
        {rows.length === 0 && !log.isLoading ? (
          <EmptyState
            icon={FileSearch}
            title="No audit entries match"
            description="Loosen filters to see recent signal, order, position, strategy and rejection events."
          />
        ) : (
          <>
            <DataTable
              data={rows}
              columns={columns}
              rowKey={(r) => r.id}
              loading={log.isLoading}
              density="compact"
              sorting={{ state: sorting, onChange: setSorting }}
              activeRowId={expanded}
              onRowClick={(r) => {
                if (!canDrillDown(r)) return
                setExpanded((cur) => (cur === r.id ? null : r.id))
              }}
            />

            {expandedRow && (
              <ExpandedDetail entry={expandedRow} />
            )}
          </>
        )}
      </div>
    </div>
  )
}

function canDrillDown(entry: AuditLogEntry): boolean {
  // Trade lifecycle is only meaningful for order/position rows (ids prefixed
  // ord-/pos-). Signal and strategy rows show inline metadata instead.
  return entry.id.startsWith('ord-') || entry.id.startsWith('pos-')
}

function ExpandedDetail({ entry }: { entry: AuditLogEntry }) {
  if (canDrillDown(entry)) {
    // Peel off prefix so the lifecycle endpoint sees the raw underlying id.
    // The audit endpoint composes ids like ord-<uuid> / pos-<uuid>; the
    // lifecycle endpoint expects a trade_id that resolves via orders or
    // positions tables — pass the stripped id.
    const rawId = entry.id.replace(/^(ord|pos)-/, '')
    return <TradeLifecycleChain tradeId={rawId} />
  }

  const md = entry.metadata ?? null
  const entries = md ? Object.entries(md).slice(0, 12) : []
  if (!entries.length) {
    return (
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 text-[10px] text-[var(--text-3)]">
        No metadata.
      </div>
    )
  }

  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
      <dl className="grid grid-cols-2 md:grid-cols-3 gap-x-4 gap-y-1">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-baseline gap-1.5 min-w-0">
            <dt className="text-[9px] uppercase tracking-wider text-[var(--text-3)] shrink-0">
              {k}
            </dt>
            <dd
              className="mono tabular-nums text-[10px] text-[var(--text-1)] truncate"
              title={JSON.stringify(v)}
            >
              {renderMetaValue(v)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function renderMetaValue(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'number' && Number.isFinite(v)) return v.toString()
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'string') return v
  try {
    return JSON.stringify(v)
  } catch {
    return String(v)
  }
}
