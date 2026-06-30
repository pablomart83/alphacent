import { Search, X, Zap, MoonStar, TrendingDown, TrendingUp, GraduationCap, Beaker, Sparkles, Star, Pause } from 'lucide-react'
import {
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { cn } from '@/lib/utils'
import type { StrategyStatus } from '../useStrategiesData'

export type QuickPillId =
  | 'signals-today'
  | 'idle-7d'
  | 'negative-live-pnl'
  | 'graduation-eligible'
  | 'paper-20-plus'
  | 'promoted-today'
  | 'activated-today'
  | 'live-today'
  | 'dormant'

export interface LibraryFilters {
  search: string
  status: StrategyStatus | 'all'
  template: string // '' = all
  regime: string // '' = all
  source: 'all' | 'TEMPLATE' | 'USER'
  category: string // '' = all
  type: string // '' = all
  quickPills: QuickPillId[]
}

export const DEFAULT_LIBRARY_FILTERS: LibraryFilters = {
  search: '',
  status: 'all',
  template: '',
  regime: '',
  source: 'all',
  category: '',
  type: '',
  quickPills: [],
}

const STATUS_OPTIONS: Array<{ value: StrategyStatus | 'all'; label: string }> = [
  { value: 'all', label: 'Any status' },
  { value: 'PROPOSED', label: 'Proposed' },
  { value: 'BACKTESTED', label: 'Backtested' },
  { value: 'PAPER', label: 'Paper' },
  { value: 'LIVE', label: 'Live' },
  { value: 'RETIRED', label: 'Retired' },
]

const QUICK_PILLS: Array<{
  id: QuickPillId
  label: string
  icon: React.ComponentType<{ className?: string }>
  description: string
}> = [
  {
    id: 'signals-today',
    label: 'Signals today',
    icon: Zap,
    description: 'Strategies that generated a signal in the last 24 hours',
  },
  {
    id: 'idle-7d',
    label: 'Idle 7d+',
    icon: MoonStar,
    description: 'No signal or fill in the last 7 days',
  },
  {
    id: 'negative-live-pnl',
    label: 'Negative live P&L',
    icon: TrendingDown,
    description: 'Live-authorised strategies with live_pnl < 0',
  },
  {
    id: 'graduation-eligible',
    label: 'Graduation eligible',
    icon: GraduationCap,
    description: 'PAPER with ≥20 trades and Sharpe ≥ 1.0',
  },
  {
    id: 'paper-20-plus',
    label: 'Paper ≥ 20 trades',
    icon: Beaker,
    description: 'PAPER strategies with at least 20 trades',
  },
  {
    id: 'promoted-today',
    label: 'Promoted today',
    icon: TrendingUp,
    description: 'Strategies promoted from BACKTESTED → PAPER today',
  },
  {
    id: 'activated-today',
    label: 'Activated today',
    icon: Sparkles,
    description: 'Brand-new strategies proposed and activated today',
  },
  {
    id: 'live-today',
    label: 'Live today',
    icon: Star,
    description: 'Strategies that graduated to live trading today',
  },
  {
    id: 'dormant',
    label: 'Dormant',
    icon: Pause,
    description: 'Validated but asleep — regime not current (kept warm, no signals until its regime returns)',
  },
]

interface LibraryFilterBarProps {
  filters: LibraryFilters
  onChange: (next: LibraryFilters) => void
  templateOptions: string[]
  regimeOptions: string[]
  categoryOptions: string[]
  typeOptions: string[]
  resultCount: number
  totalCount: number
  className?: string
}

export function LibraryFilterBar({
  filters,
  onChange,
  templateOptions,
  regimeOptions,
  categoryOptions,
  typeOptions,
  resultCount,
  totalCount,
  className,
}: LibraryFilterBarProps) {
  const set = <K extends keyof LibraryFilters>(k: K, v: LibraryFilters[K]) =>
    onChange({ ...filters, [k]: v })

  const togglePill = (id: QuickPillId) => {
    const has = filters.quickPills.includes(id)
    const next = has
      ? filters.quickPills.filter((p) => p !== id)
      : [...filters.quickPills, id]
    set('quickPills', next)
  }

  const hasActive =
    filters.search.trim().length > 0 ||
    filters.status !== 'all' ||
    filters.template !== '' ||
    filters.regime !== '' ||
    filters.source !== 'all' ||
    filters.category !== '' ||
    filters.type !== '' ||
    filters.quickPills.length > 0

  return (
    <div
      className={cn(
        'flex flex-col gap-1.5 py-1.5 px-2 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]',
        className,
      )}
    >
      {/* Row 1 — search + structured filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <Input
          size="sm"
          prefix={<Search className="h-3.5 w-3.5" />}
          placeholder="Name, template, symbol…"
          value={filters.search}
          onChange={(e) => set('search', e.target.value)}
          className="max-w-[240px]"
          data-library-search
        />

        <Select
          value={filters.status}
          onValueChange={(v) => set('status', v as LibraryFilters['status'])}
        >
          <SelectTrigger size="sm" className="h-7 min-w-[130px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.template || '__ALL__'}
          onValueChange={(v) => set('template', v === '__ALL__' ? '' : v)}
        >
          <SelectTrigger size="sm" className="h-7 min-w-[150px] text-[11px]">
            <SelectValue placeholder="Template" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__ALL__">All templates</SelectItem>
            {templateOptions.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.regime || '__ALL__'}
          onValueChange={(v) => set('regime', v === '__ALL__' ? '' : v)}
        >
          <SelectTrigger size="sm" className="h-7 min-w-[140px] text-[11px]">
            <SelectValue placeholder="Regime" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__ALL__">Any regime</SelectItem>
            {regimeOptions.map((r) => (
              <SelectItem key={r} value={r}>
                {r.replace(/_/g, ' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.source}
          onValueChange={(v) => set('source', v as LibraryFilters['source'])}
        >
          <SelectTrigger size="sm" className="h-7 min-w-[110px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any source</SelectItem>
            <SelectItem value="TEMPLATE">Template</SelectItem>
            <SelectItem value="USER">User</SelectItem>
          </SelectContent>
        </Select>

        <Select
          value={filters.category || '__ALL__'}
          onValueChange={(v) => set('category', v === '__ALL__' ? '' : v)}
        >
          <SelectTrigger size="sm" className="h-7 min-w-[130px] text-[11px]">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__ALL__">Any category</SelectItem>
            {categoryOptions.map((c) => (
              <SelectItem key={c} value={c}>
                {c.replace(/_/g, ' ')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {typeOptions.length > 0 && (
          <Select
            value={filters.type || '__ALL__'}
            onValueChange={(v) => set('type', v === '__ALL__' ? '' : v)}
          >
            <SelectTrigger size="sm" className="h-7 min-w-[130px] text-[11px]">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__ALL__">Any type</SelectItem>
              {typeOptions.map((t) => (
                <SelectItem key={t} value={t}>
                  {t.replace(/_/g, ' ')}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {hasActive && (
          <button
            type="button"
            onClick={() => onChange(DEFAULT_LIBRARY_FILTERS)}
            className="inline-flex items-center gap-1 text-[10px] text-[var(--text-3)] hover:text-[var(--text-0)]"
          >
            <X className="h-3 w-3" />
            Clear
          </button>
        )}

        <div className="ml-auto text-[10px] text-[var(--text-3)] mono">
          {resultCount} of {totalCount}
        </div>
      </div>

      {/* Row 2 — quick pills */}
      <div className="flex items-center gap-1 flex-wrap">
        <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
          Quick filters
        </span>
        {QUICK_PILLS.map((pill) => {
          const Icon = pill.icon
          const active = filters.quickPills.includes(pill.id)
          return (
            <button
              key={pill.id}
              type="button"
              onClick={() => togglePill(pill.id)}
              title={pill.description}
              className={cn(
                'inline-flex items-center gap-1 h-6 px-2 rounded-[2px] text-[10px] font-medium',
                'border transition-colors',
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
