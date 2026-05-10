import { Search, X } from 'lucide-react'
import { Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives'
import { cn } from '@/lib/utils'

export interface PositionFilters {
  search: string
  strategy: string // '' = all
  side: 'all' | 'long' | 'short'
  status: 'all' | 'open' | 'pending'
}

interface PositionsFilterBarProps {
  filters: PositionFilters
  onChange: (next: PositionFilters) => void
  strategyOptions: string[]
  resultCount: number
  totalCount: number
  className?: string
  /** Optional actions rendered on the right (e.g. sync button, density toggle). */
  actions?: React.ReactNode
}

export function PositionsFilterBar({
  filters,
  onChange,
  strategyOptions,
  resultCount,
  totalCount,
  className,
  actions,
}: PositionsFilterBarProps) {
  const set = <K extends keyof PositionFilters>(k: K, v: PositionFilters[K]) =>
    onChange({ ...filters, [k]: v })

  const hasActive =
    filters.search.trim().length > 0 ||
    filters.strategy !== '' ||
    filters.side !== 'all' ||
    filters.status !== 'all'

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

      <Select value={filters.strategy || '__ALL__'} onValueChange={(v) => set('strategy', v === '__ALL__' ? '' : v)}>
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

      <Select value={filters.side} onValueChange={(v) => set('side', v as PositionFilters['side'])}>
        <SelectTrigger size="sm" className="h-7 min-w-[90px] text-[11px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Any side</SelectItem>
          <SelectItem value="long">Long</SelectItem>
          <SelectItem value="short">Short</SelectItem>
        </SelectContent>
      </Select>

      <Select value={filters.status} onValueChange={(v) => set('status', v as PositionFilters['status'])}>
        <SelectTrigger size="sm" className="h-7 min-w-[110px] text-[11px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">Any status</SelectItem>
          <SelectItem value="open">Open only</SelectItem>
          <SelectItem value="pending">Pending close</SelectItem>
        </SelectContent>
      </Select>

      {hasActive && (
        <button
          type="button"
          onClick={() =>
            onChange({ search: '', strategy: '', side: 'all', status: 'all' })
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
