import { SectionLabel } from '@/components/layout'
import { Badge, Card, EmptyState, Skeleton } from '@/components/primitives'
import { Globe } from 'lucide-react'
import { cn, formatNumber } from '@/lib/utils'
import type { RegimeSnapshot } from '../useResearchData'

interface CurrentRegimesGridProps {
  data: Record<string, RegimeSnapshot> | undefined
  loading?: boolean
}

const ASSET_CLASSES: Array<{ key: string; label: string }> = [
  { key: 'equity', label: 'Equity' },
  { key: 'crypto', label: 'Crypto' },
  { key: 'forex', label: 'Forex' },
  { key: 'commodity', label: 'Commodity' },
]

export function CurrentRegimesGrid({ data, loading }: CurrentRegimesGridProps) {
  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Current regime per asset class</SectionLabel>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          {ASSET_CLASSES.map((a) => (
            <Skeleton key={a.key} variant="block" className="h-[140px]" />
          ))}
        </div>
      </section>
    )
  }

  if (!data || Object.keys(data).length === 0) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Current regime per asset class</SectionLabel>
        <EmptyState
          icon={Globe}
          title="Regime detection unavailable"
          description="Per-asset-class regime detection relies on SPY/QQQ/DIA/BTC/ETH/FX price history. Runs once price data is cached."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Current regime per asset class</SectionLabel>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        {ASSET_CLASSES.map((a) => (
          <RegimeCard key={a.key} label={a.label} snapshot={data[a.key]} />
        ))}
      </div>
    </section>
  )
}

function RegimeCard({
  label,
  snapshot,
}: {
  label: string
  snapshot: RegimeSnapshot | undefined
}) {
  if (!snapshot) {
    return (
      <Card padding="sm" className="flex flex-col gap-1">
        <div className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
        <div className="text-[12px] text-[var(--text-2)]">No data</div>
      </Card>
    )
  }

  const confidence = snapshot.confidence ?? 0

  return (
    <Card padding="sm" className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
          {label}
        </span>
        <Badge variant={regimeToBadge(snapshot.regime)}>
          {formatRegime(snapshot.regime)}
        </Badge>
      </div>
      {snapshot.error ? (
        <div className="text-[11px] text-[var(--pnl-down)]">{snapshot.error}</div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-x-2 gap-y-1 text-[10px]">
            <Stat label="Conf" value={`${formatNumber(confidence * 100, 0)}%`} />
            <Stat
              label="20d"
              value={`${formatNumber(snapshot.change_20d ?? 0, 2)}%`}
              tone={(snapshot.change_20d ?? 0) >= 0 ? 'up' : 'down'}
            />
            <Stat
              label="50d"
              value={`${formatNumber(snapshot.change_50d ?? 0, 2)}%`}
              tone={(snapshot.change_50d ?? 0) >= 0 ? 'up' : 'down'}
            />
            <Stat label="ATR" value={`${formatNumber(snapshot.atr_ratio ?? 0, 2)}%`} />
            <Stat
              label="Quality"
              value={snapshot.data_quality ?? '—'}
            />
          </div>
          {snapshot.symbols && snapshot.symbols.length > 0 && (
            <div className="mt-auto pt-1 border-t border-[var(--border-subtle)] text-[9px] text-[var(--text-3)] truncate">
              {snapshot.symbols.join(' · ')}
            </div>
          )}
        </>
      )}
    </Card>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div>
      <div className="text-[9px] text-[var(--text-3)] uppercase tracking-wider">{label}</div>
      <div
        className={cn(
          'text-[11px] mono tabular-nums',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}

function formatRegime(r: string): string {
  if (!r) return '—'
  return r.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function regimeToBadge(
  r: string,
):
  | 'regime-up'
  | 'regime-down'
  | 'regime-range'
  | 'regime-vol'
  | 'default' {
  const s = (r || '').toLowerCase()
  if (s.includes('trending_up') || s.includes('trending up')) return 'regime-up'
  if (s.includes('trending_down') || s.includes('trending down')) return 'regime-down'
  if (s.includes('ranging')) return 'regime-range'
  if (s.includes('volatile') || s.includes('high_vol')) return 'regime-vol'
  return 'default'
}
