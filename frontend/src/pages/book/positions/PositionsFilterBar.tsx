import { Search, X, Clock, TrendingDown, AlertTriangle, Timer, XCircle } from 'lucide-react'
import { Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives'
import { cn } from '@/lib/utils'

export type PositionQuickPillId =
  | 'today'
  | '48h'
  | 'losing'
  | 'big-loss'
  | 'long-held'
  | 'pending-close'

export interface PositionFilters {
  search: string
  strategy: string // '' = all
  side: 'all' | 'long' | 'short'
  status: 'all' | 'open' | 'pending'
  quickPills: PositionQuickPillId[]
}

const POSITION_PILLS: Array<{
  id: PositionQuickPillId
  label: string
  icon: React.ComponentType<{ className?: string }>
  description: string
}> = [
  { id: 'today',        label: 'Opened today',   icon: Clock,          description: 'Positions opened in the last 24 hours' },
  { id: '48h',          label: 'Last 48h',        icon: Timer,          description: 'Positions opened in the last 48 hours' },
  { id: 'losing',       label: 'Losing',          icon: TrendingDown,   description: 'Unrealized P&L is negative' },
  { id: 'big-loss',     label: 'Loss > 5%',       icon: AlertTriangle,  description: 'Unrealized P&L below −5%' },
  { id: 'long-held',    label: 'Held 14d+',       icon: Timer,          description: 'Position open for 14 or more days' },
  { id: 'pending-close',label: 'Pending close',   icon: XCircle,        description: 'Flagged for closure, awaiting approval' },
]

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

  const togglePill = (id: PositionQuickPillId) => {
    const has = filters.quickPills.includes(id)
    set('quickPills', has ? filters.quickPills.filter((p) => p !== id) : [...filters.quickPills, id])
  }

  const hasActive =
    filters.search.trim().length > 0 ||
    filters.strategy !== '' ||
    filters.side !== 'all' ||
    filters.status !== 'all' ||
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

        <Select value={filters.strategy || '__ALL__'} onValueChange={(v) => set('strategy', v === '__ALL__' ? '' : v)}>
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
            onClick={() => onChange({ search: '', strategy: '', side: 'all', status: 'all', quickPills: [] })}
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
        {POSITION_PILLS.map((pill) => {
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
