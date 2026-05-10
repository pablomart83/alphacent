import { useMemo } from 'react'
import { PanelHeader, SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { Skeleton } from '@/components/primitives'
import { cn, formatCurrency, formatPercentage } from '@/lib/utils'
import type { PositionRow } from '../useBookData'

interface AllocationPanelProps {
  positions: PositionRow[]
  loading?: boolean
  className?: string
}

interface SymbolAgg {
  symbol: string
  invested: number
  pnl: number
}

interface SectorAgg {
  sector: string
  invested: number
  pnl: number
  count: number
}

interface AssetClassAgg {
  assetClass: string
  invested: number
  pnl: number
  count: number
}

const SYMBOL_COLORS = [
  'var(--accent-primary)',
  'var(--accent-secondary)',
  'var(--accent-ticker)',
  'var(--pnl-up)',
  'var(--status-warning)',
  'var(--regime-vol)',
  'var(--regime-up-strong)',
  'var(--status-error)',
  'var(--pnl-up-flash)',
  'var(--regime-range)',
]

export function AllocationPanel({ positions, loading, className }: AllocationPanelProps) {
  const { symbolAgg, sectorAgg, assetClassAgg, directional, totalInvested } = useMemo(() => {
    const bySymbol = new Map<string, SymbolAgg>()
    const bySector = new Map<string, SectorAgg>()
    const byClass = new Map<string, AssetClassAgg>()
    let longInvested = 0
    let shortInvested = 0
    let totalInvested = 0

    for (const p of positions) {
      const invested = Math.abs(p.invested_amount ?? p.quantity ?? 0)
      const pnl = p.unrealized_pnl ?? 0
      totalInvested += invested

      const sym = bySymbol.get(p.symbol) ?? { symbol: p.symbol, invested: 0, pnl: 0 }
      sym.invested += invested
      sym.pnl += pnl
      bySymbol.set(p.symbol, sym)

      const sector = p.sector || 'Other'
      const sec = bySector.get(sector) ?? { sector, invested: 0, pnl: 0, count: 0 }
      sec.invested += invested
      sec.pnl += pnl
      sec.count++
      bySector.set(sector, sec)

      const ac = p.asset_class || 'Stocks'
      const clz = byClass.get(ac) ?? { assetClass: ac, invested: 0, pnl: 0, count: 0 }
      clz.invested += invested
      clz.pnl += pnl
      clz.count++
      byClass.set(ac, clz)

      const up = (p.side || '').toUpperCase()
      if (up.includes('SHORT') || up.includes('SELL')) shortInvested += invested
      else longInvested += invested
    }

    return {
      symbolAgg: [...bySymbol.values()].sort((a, b) => b.invested - a.invested),
      sectorAgg: [...bySector.values()].sort((a, b) => b.invested - a.invested),
      assetClassAgg: [...byClass.values()].sort((a, b) => b.invested - a.invested),
      directional: {
        long: longInvested,
        short: shortInvested,
        net: longInvested - shortInvested,
      },
      totalInvested,
    }
  }, [positions])

  if (loading && positions.length === 0) {
    return (
      <div className={cn('flex flex-col h-full overflow-auto', className)}>
        <div className="p-3 flex flex-col gap-3">
          <Skeleton variant="block" className="h-40" />
          <Skeleton variant="block" className="h-40" />
          <Skeleton variant="block" className="h-20" />
        </div>
      </div>
    )
  }

  if (positions.length === 0) {
    return (
      <div className={cn('flex items-center justify-center h-full text-[11px] text-[var(--text-3)]', className)}>
        No open positions to allocate.
      </div>
    )
  }

  return (
    <div className={cn('flex flex-col h-full overflow-auto bg-[var(--bg-0)]', className)}>
      <PanelHeader title="Allocation" className="min-h-0">
        <div className="flex flex-col gap-3 p-3">
          <SymbolAllocation symbols={symbolAgg} total={totalInvested} />
          <SectorBars sectors={sectorAgg} total={totalInvested} />
          <DirectionalBar
            long={directional.long}
            short={directional.short}
            net={directional.net}
            total={totalInvested}
          />
          <AssetClassTiles classes={assetClassAgg} />
        </div>
      </PanelHeader>
    </div>
  )
}

function SymbolAllocation({ symbols, total }: { symbols: SymbolAgg[]; total: number }) {
  const top = symbols.slice(0, 9)
  const rest = symbols.slice(9)
  const restInvested = rest.reduce((acc, r) => acc + r.invested, 0)
  const restPnl = rest.reduce((acc, r) => acc + r.pnl, 0)
  const rows = [
    ...top.map((s, i) => ({ ...s, color: SYMBOL_COLORS[i % SYMBOL_COLORS.length] })),
    ...(rest.length > 0
      ? [{ symbol: `Other (${rest.length})`, invested: restInvested, pnl: restPnl, color: 'var(--text-3)' }]
      : []),
  ]

  return (
    <div>
      <SectionLabel>By symbol</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        {/* Horizontal bar composed of segments */}
        <div className="flex h-2.5 rounded-[2px] overflow-hidden bg-[var(--bg-2)] mb-2">
          {rows.map((r) => {
            const pct = total > 0 ? (r.invested / total) * 100 : 0
            if (pct <= 0) return null
            return (
              <div
                key={r.symbol}
                className="h-full transition-colors hover:brightness-125"
                style={{ width: `${pct}%`, backgroundColor: r.color }}
                title={`${r.symbol}: ${formatCurrency(r.invested, { precision: 0 })} (${pct.toFixed(1)}%)`}
              />
            )
          })}
        </div>
        {/* Legend */}
        <ul className="flex flex-col gap-0.5">
          {rows.map((r) => {
            const pct = total > 0 ? (r.invested / total) * 100 : 0
            return (
              <li key={r.symbol} className="flex items-center gap-1.5 text-[10px]">
                <span
                  className="h-1.5 w-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: r.color }}
                />
                <span className="text-[var(--text-1)] truncate mono">{r.symbol}</span>
                <span className="text-[var(--text-3)] mono tabular-nums ml-auto">
                  {pct.toFixed(1)}%
                </span>
                <PnLNumber value={r.pnl} format="currency" precision={0} size="sm" />
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

function SectorBars({ sectors, total }: { sectors: SectorAgg[]; total: number }) {
  const SECTOR_CAP = 30 // soft cap from steering file
  return (
    <div>
      <SectionLabel>By sector</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 flex flex-col gap-1">
        {sectors.map((s) => {
          const pct = total > 0 ? (s.invested / total) * 100 : 0
          const breach = pct > SECTOR_CAP
          return (
            <div key={s.sector} className="flex flex-col gap-0.5">
              <div className="flex items-center text-[10px]">
                <span className="text-[var(--text-1)] truncate">{s.sector}</span>
                <span className="ml-auto mono tabular-nums text-[var(--text-2)]">
                  {pct.toFixed(1)}%
                </span>
              </div>
              <div className="relative h-1.5 rounded-[1px] overflow-hidden bg-[var(--bg-2)]">
                <div
                  className="absolute inset-y-0 left-0"
                  style={{
                    width: `${Math.min(100, pct)}%`,
                    backgroundColor: breach ? 'var(--pnl-down)' : 'var(--accent-primary)',
                  }}
                />
                {/* Cap line */}
                <div
                  className="absolute inset-y-0 w-[1px] bg-[var(--text-3)]"
                  style={{ left: `${SECTOR_CAP}%` }}
                  title={`Soft cap ${SECTOR_CAP}%`}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function DirectionalBar({
  long,
  short,
  net,
  total,
}: {
  long: number
  short: number
  net: number
  total: number
}) {
  const longPct = total > 0 ? (long / total) * 100 : 0
  const shortPct = total > 0 ? (short / total) * 100 : 0

  return (
    <div>
      <SectionLabel>Directional</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <div className="flex h-2 rounded-[2px] overflow-hidden bg-[var(--bg-2)] mb-2">
          <div
            className="h-full"
            style={{ width: `${longPct}%`, backgroundColor: 'var(--pnl-up)' }}
            title={`Long ${formatCurrency(long, { precision: 0 })}`}
          />
          <div
            className="h-full"
            style={{ width: `${shortPct}%`, backgroundColor: 'var(--pnl-down)' }}
            title={`Short ${formatCurrency(short, { precision: 0 })}`}
          />
        </div>
        <div className="grid grid-cols-3 gap-2 text-[10px]">
          <div className="flex flex-col">
            <span className="text-[var(--text-3)] uppercase tracking-wide">Long</span>
            <span className="mono text-[var(--pnl-up)] font-semibold">
              {formatCurrency(long, { precision: 0 })}
            </span>
            <span className="mono text-[var(--text-3)]">{formatPercentage(longPct, { precision: 1, signed: false })}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[var(--text-3)] uppercase tracking-wide">Short</span>
            <span className="mono text-[var(--pnl-down)] font-semibold">
              {formatCurrency(short, { precision: 0 })}
            </span>
            <span className="mono text-[var(--text-3)]">{formatPercentage(shortPct, { precision: 1, signed: false })}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[var(--text-3)] uppercase tracking-wide">Net</span>
            <PnLNumber value={net} format="currency" precision={0} size="sm" muted={net === 0} />
          </div>
        </div>
      </div>
    </div>
  )
}

function AssetClassTiles({ classes }: { classes: AssetClassAgg[] }) {
  return (
    <div>
      <SectionLabel>By asset class</SectionLabel>
      <div className="grid grid-cols-2 gap-1.5">
        {classes.map((c) => (
          <div
            key={c.assetClass}
            className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-[var(--text-3)] uppercase tracking-wider">
                {c.assetClass}
              </span>
              <span className="text-[10px] mono text-[var(--text-2)]">{c.count}</span>
            </div>
            <div className="mt-0.5 mono tabular-nums text-[12px] text-[var(--text-0)]">
              {formatCurrency(c.invested, { precision: 0, compact: true })}
            </div>
            <PnLNumber value={c.pnl} format="currency" precision={0} size="sm" />
          </div>
        ))}
      </div>
    </div>
  )
}
