import { PnLNumber } from '@/components/trading/PnLNumber'
import { AccountToggle } from '@/components/trading/AccountToggle'
import { LivePill } from '@/components/trading/LivePill'
import type { LivePillState } from '@/components/trading/LivePill'
import { cn, formatCurrency } from '@/lib/utils'

interface AccountHeroProps {
  equity: number | null | undefined
  equityLabel?: string
  todayPnl: number | null | undefined
  todayPnlPct: number | null | undefined
  availableCash: number | null | undefined
  liveEnabled: boolean
  liveAuthorisations: number
  className?: string
}

function deriveLiveState(liveEnabled: boolean, authCount: number): LivePillState {
  if (!liveEnabled) return 'off'
  if (authCount === 0) return 'on-no-authorisations'
  return 'on-active'
}

export function AccountHero({
  equity,
  equityLabel = 'Equity',
  todayPnl,
  todayPnlPct,
  availableCash,
  liveEnabled,
  liveAuthorisations,
  className,
}: AccountHeroProps) {
  const liveState = deriveLiveState(liveEnabled, liveAuthorisations)

  return (
    <div className={cn('flex flex-col gap-2 p-2 border-b border-[var(--border-subtle)]', className)}>
      <div className="flex items-center justify-between gap-2">
        <AccountToggle liveEnabled={liveEnabled} />
        <LivePill state={liveState} authorisationCount={liveAuthorisations} />
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium">
          {equityLabel}
        </div>
        <PnLNumber
          value={equity ?? 0}
          format="currency"
          precision={0}
          size="3xl"
          showSign={false}
          muted
        />
      </div>
      <div className="flex items-baseline gap-3">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium">
            Today
          </span>
          <div className="flex items-baseline gap-2">
            <PnLNumber value={todayPnl} size="lg" />
            {todayPnlPct != null && (
              <PnLNumber value={todayPnlPct} format="percentage" size="sm" />
            )}
          </div>
        </div>
        <div className="flex flex-col ml-auto">
          <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium">
            Available cash
          </span>
          <span className="mono text-[12px] text-[var(--text-1)]">
            {formatCurrency(availableCash ?? 0, { precision: 0 })}
          </span>
        </div>
      </div>
    </div>
  )
}
