import { Search, X, Clock, Timer, CheckCircle2, XCircle, ArrowDownCircle, ArrowUpCircle } from 'lucide-react'
import {
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { cn } from '@/lib/utils'
import type { OrderStatus } from '../useBookData'

export type OrderQuickPillId =
  | 'today'
  | '48h'
  | 'filled'
  | 'failed'
  | 'entry'
  | 'close'

export interface OrderFilters {
  search: string
  strategy: string // '' = all
  side: 'all' | 'BUY' | 'SELL'
  status: 'all' | OrderStatus
  action: 'all' | 'entry' | 'close' | 'retirement'
  range: '1d' | '7d' | '30d' | 'all'
  quickPills: OrderQuickPillId[]
}

const ORDER_PILLS: Array<{
  id: OrderQuickPillId
  label: string
  icon: React.ComponentType<{ className?: string }>
  description: string
}> = [
  { id: 'today',  label: 'Today',       icon: Clock,          description: 'Orders created in the last 24 hours' },
  { id: '48h',    label: 'Last 48h',    icon: Timer,          description: 'Orders created in the last 48 hours' },
  { id: 'filled', label: 'Filled',      icon: CheckCircle2,   description: 'Orders with status FILLED' },
  { id: 'failed', label: 'Failed',      icon: XCircle,        description: 'Orders that were FAILED, REJECTED, or CANCELLED' },
  { id: 'entry',  label: 'Entry only',  icon: ArrowDownCircle,description: 'Entry orders only' },
  { id: 'close',  label: 'Close only',  icon: ArrowUpCircle,  description: 'Close orders only' },
]

interface OrdersFilterBarProps {
  filters: OrderFilters
  onChange: (next: OrderFilters) => void
  strategyOptions: string[]
  resultCount: number
  totalCount: number
  className?: string
  actions?: React.ReactNode
  /** When true, the parent tab pre-filters by status (Pending / Cancelled-Failed) — hide status select. */
  lockStatus?: boolean
}

export function OrdersFilterBar({
  filters,
  onChange,
  strategyOptions,
  resultCount,
  totalCount,
  className,
  actions,
  lockStatus,
}: OrdersFilterBarProps) {
  const set = <K extends keyof OrderFilters>(k: K, v: OrderFilters[K]) =>
    onChange({ ...filters, [k]: v })

  const togglePill = (id: OrderQuickPillId) => {
    const has = filters.quickPills.includes(id)
    set('quickPills', has ? filters.quickPills.filter((p) => p !== id) : [...filters.quickPills, id])
  }

  const hasActive =
    filters.search.trim().length > 0 ||
    filters.strategy !== '' ||
    filters.side !== 'all' ||
    (!lockStatus && filters.status !== 'all') ||
    filters.action !== 'all' ||
    filters.range !== '30d' ||
    filters.quickPills.length > 0

  return (
    <div
      className={cn(
        'flex flex-col gap-1.5 px-2 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]',
        className,
      )}
    >
      {/* Row 1 — structured filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <Input
          size="sm"
          prefix={<Search className="h-3.5 w-3.5" />}
          placeholder="Symbol or strategy…"
          value={filters.search}
          onChange={(e) => set('search', e.target.value)}
          className="max-w-[220px]"
        />
        <Select
          value={filters.strategy || '__ALL__'}
          onValueChange={(v) => set('strategy', v === '__ALL__' ? '' : v)}
        >
          <SelectTrigger size="sm" className="h-7 min-w-[150px] text-[11px]">
            <SelectValue placeholder="Strategy" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__ALL__">All strategies</SelectItem>
            {strategyOptions.map((s) => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.side} onValueChange={(v) => set('side', v as OrderFilters['side'])}>
          <SelectTrigger size="sm" className="h-7 min-w-[80px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any side</SelectItem>
            <SelectItem value="BUY">Buy</SelectItem>
            <SelectItem value="SELL">Sell</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filters.action} onValueChange={(v) => set('action', v as OrderFilters['action'])}>
          <SelectTrigger size="sm" className="h-7 min-w-[100px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any action</SelectItem>
            <SelectItem value="entry">Entry</SelectItem>
            <SelectItem value="close">Close</SelectItem>
            <SelectItem value="retirement">Retirement</SelectItem>
          </SelectContent>
        </Select>

        {!lockStatus && (
          <Select value={filters.status} onValueChange={(v) => set('status', v as OrderFilters['status'])}>
            <SelectTrigger size="sm" className="h-7 min-w-[110px] text-[11px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any status</SelectItem>
              <SelectItem value="FILLED">Filled</SelectItem>
              <SelectItem value="PARTIALLY_FILLED">Partially filled</SelectItem>
              <SelectItem value="PENDING">Pending</SelectItem>
              <SelectItem value="SUBMITTED">Submitted</SelectItem>
              <SelectItem value="CANCELLED">Cancelled</SelectItem>
              <SelectItem value="REJECTED">Rejected</SelectItem>
              <SelectItem value="FAILED">Failed</SelectItem>
            </SelectContent>
          </Select>
        )}

        <Select value={filters.range} onValueChange={(v) => set('range', v as OrderFilters['range'])}>
          <SelectTrigger size="sm" className="h-7 min-w-[110px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1d">Last 24h</SelectItem>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
            <SelectItem value="all">All time</SelectItem>
          </SelectContent>
        </Select>

        {hasActive && (
          <button
            type="button"
            onClick={() =>
              onChange({ search: '', strategy: '', side: 'all', status: 'all', action: 'all', range: '30d', quickPills: [] })
            }
            className="inline-flex items-center gap-1 text-[10px] text-[var(--text-3)] hover:text-[var(--text-0)]"
          >
            <X className="h-3 w-3" />
            Clear
          </button>
        )}

        <div className="ml-auto flex items-center gap-2">
          <span className="text-[10px] text-[var(--text-3)] mono">
            {resultCount} of {totalCount}
          </span>
          {actions}
        </div>
      </div>

      {/* Row 2 — quick pills */}
      <div className="flex items-center gap-1 flex-wrap">
        <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">Quick filters</span>
        {ORDER_PILLS.map((pill) => {
          const Icon = pill.icon
          const active = filters.quickPills.includes(pill.id)
          return (
            <button
              key={pill.id}
              type="button"
              onClick={() => togglePill(pill.id)}
              title={pill.description}
              className={cn(
                'inline-flex items-center gap-1 h-6 px-2 rounded-[2px] text-[10px] font-medium border transition-colors',
                active
                  ? 'bg-[color-mix(in_oklab,var(--accent-primary)_15%,transparent)] text-[var(--accent-primary)] border-[var(--accent-primary)]/30'
                  : 'bg-[var(--bg-2)] text-[var(--text-2)] border-transparent hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
              )}
            >
              <Icon className="h-3 w-3" />
              {pill.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
