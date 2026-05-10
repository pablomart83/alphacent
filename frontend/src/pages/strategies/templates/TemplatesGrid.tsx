import { useMemo, useState } from 'react'
import { ChevronDown, ChevronRight, Zap } from 'lucide-react'
import {
  Badge,
  Card,
  EmptyState,
  Switch,
} from '@/components/primitives'
import { Skeleton } from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { cn, formatCurrency, formatTimestamp } from '@/lib/utils'
import type { TemplateRow } from '../useStrategiesData'

interface TemplatesGridProps {
  templates: TemplateRow[]
  loading?: boolean
  selected: Set<string>
  onToggleSelection: (name: string, checked: boolean) => void
  onToggleEnabled: (name: string, enabled: boolean) => void
  pendingToggleName: string | null
  className?: string
}

export function TemplatesGrid({
  templates,
  loading,
  selected,
  onToggleSelection,
  onToggleEnabled,
  pendingToggleName,
  className,
}: TemplatesGridProps) {
  if (loading) {
    return (
      <div className={cn('grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 p-2', className)}>
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[260px] w-full rounded-[3px]" />
        ))}
      </div>
    )
  }

  if (!templates.length) {
    return (
      <EmptyState
        icon={Zap}
        title="No templates match these filters"
        description="Clear filters to see the full library."
      />
    )
  }

  return (
    <div className={cn('grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 p-2', className)}>
      {templates.map((t) => (
        <TemplateCard
          key={t.name}
          template={t}
          selected={selected.has(t.name)}
          onToggleSelection={(checked) => onToggleSelection(t.name, checked)}
          onToggleEnabled={(enabled) => onToggleEnabled(t.name, enabled)}
          isPendingToggle={pendingToggleName === t.name}
        />
      ))}
    </div>
  )
}

interface TemplateCardProps {
  template: TemplateRow
  selected: boolean
  onToggleSelection: (checked: boolean) => void
  onToggleEnabled: (enabled: boolean) => void
  isPendingToggle: boolean
}

function TemplateCard({
  template,
  selected,
  onToggleSelection,
  onToggleEnabled,
  isPendingToggle,
}: TemplateCardProps) {
  const [expanded, setExpanded] = useState(false)

  const {
    name,
    description,
    active_strategies,
    traded_count,
    activated_count,
    avg_sharpe,
    avg_win_rate,
    avg_return,
    total_pnl,
    best_symbol,
    worst_symbol,
    asset_classes,
    interval,
    direction,
    last_proposed,
    last_activated,
    enabled,
    entry_rules,
    exit_rules,
    indicators,
  } = template

  const directionVariant = useMemo<
    'success' | 'error' | 'info' | 'muted'
  >(() => {
    const d = (direction ?? '').toLowerCase()
    if (d === 'long') return 'success'
    if (d === 'short') return 'error'
    if (d === 'any' || d === 'both') return 'info'
    return 'muted'
  }, [direction])

  return (
    <Card
      className={cn(
        'flex flex-col gap-2 p-3 transition-colors',
        selected
          ? 'border-[var(--accent-primary)] bg-[color-mix(in_oklab,var(--accent-primary)_4%,var(--bg-1))]'
          : 'hover:bg-[var(--bg-1)]',
        !enabled && 'opacity-70',
      )}
    >
      <header className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={(e) => onToggleSelection(e.target.checked)}
          className="mt-0.5 h-3.5 w-3.5 accent-[var(--accent-primary)] cursor-pointer"
          aria-label={`Select ${name}`}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h3
              className="text-[12px] font-semibold text-[var(--text-0)] truncate"
              title={name}
            >
              {name}
            </h3>
            <Switch
              checked={enabled}
              onCheckedChange={onToggleEnabled}
              disabled={isPendingToggle}
              aria-label={enabled ? `Disable ${name}` : `Enable ${name}`}
            />
          </div>
          <p
            className="text-[10px] text-[var(--text-3)] line-clamp-2 mt-0.5"
            title={description}
          >
            {description}
          </p>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-1">
        {direction && (
          <Badge variant={directionVariant} size="sm">
            {direction}
          </Badge>
        )}
        <Badge variant="muted" size="sm">
          {interval}
        </Badge>
        {asset_classes.slice(0, 4).map((cls) => (
          <Badge key={cls} variant="muted" size="sm">
            {cls}
          </Badge>
        ))}
        {asset_classes.length > 4 && (
          <span className="text-[9px] text-[var(--text-3)]">
            +{asset_classes.length - 4}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
        <Stat label="Active" value={active_strategies} />
        <Stat label="Activated" value={activated_count} />
        <Stat label="Traded" value={traded_count} />
        <Stat
          label="Avg Sharpe"
          value={avg_sharpe != null ? avg_sharpe.toFixed(2) : '—'}
        />
        <Stat
          label="Avg WR"
          value={avg_win_rate != null ? `${(avg_win_rate * 100).toFixed(0)}%` : '—'}
        />
        <Stat
          label="Avg return"
          value={avg_return != null ? `${(avg_return * 100).toFixed(1)}%` : '—'}
        />
        <div className="col-span-2 flex items-baseline justify-between pt-1 border-t border-[var(--border-subtle)]">
          <span className="text-[var(--text-3)] uppercase tracking-wider text-[9px]">
            Total P&L
          </span>
          {total_pnl != null ? (
            <PnLNumber value={total_pnl} format="currency" precision={0} size="sm" showSign />
          ) : (
            <span className="text-[var(--text-3)]">—</span>
          )}
        </div>
      </div>

      {(best_symbol || worst_symbol) && (
        <div className="flex items-center justify-between text-[10px]">
          {best_symbol ? (
            <span className="inline-flex items-center gap-1 text-[var(--pnl-up)] font-mono">
              Best: {best_symbol}
            </span>
          ) : (
            <span />
          )}
          {worst_symbol && worst_symbol !== best_symbol && (
            <span className="inline-flex items-center gap-1 text-[var(--pnl-down)] font-mono">
              Worst: {worst_symbol}
            </span>
          )}
        </div>
      )}

      <div className="flex items-center justify-between text-[9px] text-[var(--text-3)] uppercase tracking-wider">
        <span title={last_proposed ?? '—'}>
          Proposed {formatTimestamp(last_proposed, 'short') || '—'}
        </span>
        <span title={last_activated ?? '—'}>
          Activated {formatTimestamp(last_activated, 'short') || '—'}
        </span>
      </div>

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="inline-flex items-center gap-1 text-[10px] text-[var(--text-2)] hover:text-[var(--accent-primary)] self-start"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        {expanded ? 'Hide rules' : 'Show rules'}
      </button>

      {expanded && (
        <div className="text-[10px] space-y-2 pt-1 border-t border-[var(--border-subtle)]">
          {indicators.length > 0 && (
            <RuleBlock label="Indicators" items={indicators} mono />
          )}
          {entry_rules.length > 0 && <RuleBlock label="Entry" items={entry_rules} />}
          {exit_rules.length > 0 && <RuleBlock label="Exit" items={exit_rules} />}
        </div>
      )}
    </Card>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-1">
      <span className="text-[var(--text-3)] uppercase tracking-wider text-[9px]">
        {label}
      </span>
      <span className="mono tabular-nums text-[var(--text-1)]">{value}</span>
    </div>
  )
}

function RuleBlock({
  label,
  items,
  mono,
}: {
  label: string
  items: string[]
  mono?: boolean
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-0.5">
        {label}
      </div>
      <ul className="space-y-0.5 pl-1">
        {items.map((item, i) => (
          <li
            key={`${label}-${i}`}
            className={cn(
              'text-[var(--text-2)] break-words',
              mono && 'mono text-[var(--text-1)]',
            )}
          >
            · {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

/* Silence unused imports. */
export const __fmt = formatCurrency
