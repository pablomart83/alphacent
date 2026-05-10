import { Card, EmptyState } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { TradeJournalPatternsPayload } from '../useResearchData'

interface PatternsPanelProps {
  data: TradeJournalPatternsPayload | undefined
  loading?: boolean
}

export function PatternsPanel({ data, loading }: PatternsPanelProps) {
  const best = data?.best_patterns ?? []
  const worst = data?.worst_patterns ?? []
  const recs = data?.recommendations ?? []

  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Patterns & recommendations</SectionLabel>
        <div className="h-[320px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (!best.length && !worst.length && !recs.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Patterns & recommendations</SectionLabel>
        <EmptyState
          icon={Sparkles}
          title="No patterns surfaced yet"
          description="The patterns endpoint surfaces best and worst setups once there's enough closed-trade coverage."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Patterns & recommendations</SectionLabel>
      <div className="grid grid-cols-1 gap-2">
        <PatternList title="Best patterns" items={best} tone="up" />
        <PatternList title="Worst patterns" items={worst} tone="down" />
        <PatternList title="Recommendations" items={recs} tone="neutral" />
      </div>
    </section>
  )
}

function PatternList({
  title,
  items,
  tone,
}: {
  title: string
  items: Array<Record<string, unknown>>
  tone: 'up' | 'down' | 'neutral'
}) {
  if (!items.length) return null
  return (
    <Card padding="sm" className="space-y-1">
      <div
        className={cn(
          'text-[10px] uppercase tracking-wider',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-2)]',
        )}
      >
        {title}
      </div>
      <ul className="space-y-1 text-[11px]">
        {items.slice(0, 6).map((it, i) => (
          <li key={i} className="text-[var(--text-1)] leading-[15px]">
            {renderPattern(it)}
          </li>
        ))}
      </ul>
    </Card>
  )
}

function renderPattern(item: Record<string, unknown>): React.ReactNode {
  const description = item.description ?? item.message ?? item.name ?? item.pattern ?? ''
  const win = item.win_rate
  const pnl = item.avg_pnl ?? item.total_pnl
  const count = item.count ?? item.trades
  const pieces: string[] = []
  if (typeof count === 'number') pieces.push(`${count} trades`)
  if (typeof win === 'number') pieces.push(`${win.toFixed(1)}% win`)
  if (typeof pnl === 'number')
    pieces.push(`${pnl > 0 ? '+' : ''}${pnl.toFixed(2)} avg P&L`)
  return (
    <div>
      <div>{String(description)}</div>
      {pieces.length > 0 && (
        <div className="text-[10px] text-[var(--text-3)] mono">{pieces.join(' · ')}</div>
      )}
    </div>
  )
}
