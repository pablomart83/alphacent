import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber } from '@/lib/utils'
import type { MarketContext } from '../useResearchData'

interface MarketContextPanelProps {
  data: MarketContext | undefined
  loading?: boolean
}

export function MarketContextPanel({ data, loading }: MarketContextPanelProps) {
  const vix = num(data?.vix)
  const vixChange = num(data?.vix_change)
  const ten = num(data?.ten_year_yield)
  const two = num(data?.two_year_yield)
  const spread = num(data?.yield_curve_spread)
  const fed = num(data?.fed_funds_rate)
  const cpi = num(data?.cpi)
  const gdp = num(data?.gdp_nowcast)
  const pmi = num(data?.ism_pmi)

  return (
    <Card padding="sm" className="flex flex-col gap-2 min-h-[200px]">
      <SectionLabel className="mb-0">Market context</SectionLabel>
      {loading && !data ? (
        <div className="flex-1 animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : (
        <div className="grid grid-cols-3 gap-x-2 gap-y-2 text-[10px]">
          <Stat
            label="VIX"
            value={vix != null ? formatNumber(vix, 2) : '—'}
            sub={vixChange != null ? `${vixChange >= 0 ? '+' : ''}${formatNumber(vixChange, 2)}%` : undefined}
            tone={vix != null && vix > 25 ? 'down' : 'neutral'}
          />
          <Stat
            label="10Y"
            value={ten != null ? `${formatNumber(ten, 2)}%` : '—'}
          />
          <Stat
            label="2Y"
            value={two != null ? `${formatNumber(two, 2)}%` : '—'}
          />
          <Stat
            label="Curve"
            value={spread != null ? `${formatNumber(spread, 2)}bp` : '—'}
            tone={spread != null && spread < 0 ? 'down' : 'neutral'}
            sub={spread != null && spread < 0 ? 'Inverted' : undefined}
          />
          <Stat
            label="Fed funds"
            value={fed != null ? `${formatNumber(fed, 2)}%` : '—'}
          />
          <Stat
            label="ISM PMI"
            value={pmi != null ? formatNumber(pmi, 1) : '—'}
            tone={pmi != null && pmi < 50 ? 'down' : 'up'}
          />
          <Stat label="CPI" value={cpi != null ? `${formatNumber(cpi, 1)}%` : '—'} />
          <Stat
            label="GDP now"
            value={gdp != null ? `${formatNumber(gdp, 1)}%` : '—'}
          />
        </div>
      )}
    </Card>
  )
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub?: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[11px]',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
      {sub && <div className="text-[9px] text-[var(--text-3)]">{sub}</div>}
    </div>
  )
}

function num(v: unknown): number | null {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : null
  return n != null && Number.isFinite(n) ? n : null
}
