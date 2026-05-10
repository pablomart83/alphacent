import { PnLNumber } from '@/components/trading/PnLNumber'
import { Skeleton } from '@/components/primitives'
import { cn, formatCurrency, formatPercentage } from '@/lib/utils'
import type { LiveSummary } from '../useBookData'

interface AccountTilesProps {
  summary: LiveSummary | undefined
  loading?: boolean
  className?: string
}

export function AccountTiles({ summary, loading, className }: AccountTilesProps) {
  if (loading && !summary) {
    return (
      <div className={cn('grid grid-cols-2 md:grid-cols-4 gap-2', className)}>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} variant="metric-tile" />
        ))}
      </div>
    )
  }

  const virtualEquity = summary?.virtual_equity ?? 0
  const realEquity = summary?.real_equity ?? 0
  const todayVirtual = summary?.today_pnl_virtual ?? 0
  const todayReal = summary?.today_pnl_real ?? 0
  const positions = summary?.open_positions ?? 0
  const deployedVirtual = summary?.deployed_capital_virtual ?? 0
  const deployedPct = summary?.deployed_pct ?? 0
  const auth = summary?.active_live_authorizations ?? 0

  return (
    <div className={cn('grid grid-cols-2 md:grid-cols-4 gap-2', className)}>
      <Tile label="Virtual equity">
        <span className="mono tabular-nums text-[18px] font-semibold text-[var(--text-0)]">
          {formatCurrency(virtualEquity, { precision: 0 })}
        </span>
        <span className="mono text-[10px] text-[var(--text-3)]">
          {formatCurrency(realEquity, { precision: 0 })} real
        </span>
      </Tile>
      <Tile label="Today's P&L">
        <PnLNumber value={todayVirtual} format="currency" precision={0} size="lg" />
        <span className="mono text-[10px] text-[var(--text-3)]">
          {todayReal >= 0 ? '+' : ''}
          {formatCurrency(todayReal, { precision: 0 })} real
        </span>
      </Tile>
      <Tile label="Open positions">
        <span className="mono tabular-nums text-[18px] font-semibold text-[var(--text-0)]">
          {positions}
        </span>
        <span className="mono text-[10px] text-[var(--text-3)]">
          {formatCurrency(deployedVirtual, { precision: 0 })} · {formatPercentage(deployedPct, { precision: 1, signed: false })} deployed
        </span>
      </Tile>
      <Tile label="Live authorisations">
        <span className="mono tabular-nums text-[18px] font-semibold text-[var(--text-0)]">
          {auth}
        </span>
        <span className="mono text-[10px] text-[var(--text-3)]">
          approved (template, symbol) pair{auth === 1 ? '' : 's'}
        </span>
      </Tile>
    </div>
  )
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)] px-2.5 py-2">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      {children}
    </div>
  )
}
