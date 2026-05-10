import { Search, X } from 'lucide-react'
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

export interface OrderFilters {
  search: string
  strategy: string // '' = all
  side: 'all' | 'BUY' | 'SELL'
  status: 'all' | OrderStatus
  action: 'all' | 'entry' | 'close' | 'retirement'
  range: '1d' | '7d' | '30d' | 'all'
}

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

  const hasActive =
    filters.search.trim().length > 0 ||
    filters.strategy !== '' ||
    filters.side !== 'all' ||
    (!lockStatus && filters.status !== 'all') ||
    filters.action !== 'all' ||
    filters.range !== '30d'

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-2 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]',
        className,
      )}
    >
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
            <SelectItem key={s} value={s}>
              {s}
            </SelectItem>
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
            onChange({
              search: '',
              strategy: '',
              side: 'all',
              status: 'all',
              action: 'all',
              range: '30d',
            })
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
  )
}
