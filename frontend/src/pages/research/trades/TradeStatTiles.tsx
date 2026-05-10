import { MetricGrid, SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import type { TradeAnalyticsPayload } from '../useResearchData'

interface TradeStatTilesProps {
  data: TradeAnalyticsPayload | undefined
  loading: boolean
}

type Tone = 'up' | 'down' | 'neutral' | 'warn'

function toneColor(tone: Tone): string {
  return tone === 'up'
    ? 'var(--pnl-up)'
    : tone === 'down'
      ? 'var(--pnl-down)'
      : tone === 'warn'
        ? 'var(--status-warning)'
        : 'var(--text-0)'
}

export function TradeStatTiles({ data, loading }: TradeStatTilesProps) {
  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Trade summary</SectionLabel>
        <MetricGrid cols={8}>
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} variant="metric-tile" />
          ))}
        </MetricGrid>
      </section>
    )
  }

  const tiles: Array<{ label: string; value: string; tone: Tone; hint?: string }> = [
    {
      label: 'Total trades',
      value: formatNumber(data?.total_trades ?? 0, 0),
      tone: 'neutral',
    },
    {
      label: 'Winning',
      value: formatNumber(data?.winning_trades ?? 0, 0),
      tone: 'up',
    },
    {
      label: 'Losing',
      value: formatNumber(data?.losing_trades ?? 0, 0),
      tone: 'down',
    },
    {
      label: 'Win rate',
      value: `${formatNumber(data?.win_rate ?? 0, 1)}%`,
      tone:
        (data?.win_rate ?? 0) >= 55 ? 'up' : (data?.win_rate ?? 0) >= 45 ? 'neutral' : 'down',
    },
    {
      label: 'Avg holding',
      value: formatHoldingHours(data?.avg_holding_time_hours),
      tone: 'neutral',
    },
    {
      label: 'Best trade',
      value: formatCurrency(data?.largest_win, { signed: true, precision: 0 }),
      tone: 'up',
    },
    {
      label: 'Worst trade',
      value: formatCurrency(-(data?.largest_loss ?? 0), { signed: true, precision: 0 }),
      tone: 'down',
    },
    {
      label: 'Profit factor',
      value: formatNumber(data?.profit_factor ?? 0, 2),
      tone:
        (data?.profit_factor ?? 0) >= 1.5
          ? 'up'
          : (data?.profit_factor ?? 0) >= 1
            ? 'neutral'
            : 'down',
    },
  ]

  return (
    <section className="space-y-1.5">
      <SectionLabel>Trade summary</SectionLabel>
      <MetricGrid cols={8}>
        {tiles.map((t) => (
          <Tile key={t.label} {...t} />
        ))}
      </MetricGrid>
    </section>
  )
}

function Tile({ label, value, tone, hint }: { label: string; value: string; tone: Tone; hint?: string }) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2.5 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn('mt-0.5 text-[14px] font-semibold mono tabular-nums leading-none')}
        style={{ color: toneColor(tone) }}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-[9px] text-[var(--text-3)] truncate">{hint}</div>}
    </div>
  )
}

function formatHoldingHours(v: number | undefined | null): string {
  if (v == null || !Number.isFinite(v)) return '—'
  if (v < 1) return `${Math.round(v * 60)}m`
  if (v < 48) return `${v.toFixed(1)}h`
  return `${(v / 24).toFixed(1)}d`
}
