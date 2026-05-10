import { useEffect, useState } from 'react'
import {
  classifyAssetClassStatus,
  assetClassDisplay,
  marketStatusColour,
} from '@/lib/market-hours'
import { cn } from '@/lib/utils'

const CLASSES = ['Stocks', 'ETFs', 'Forex', 'Crypto', 'Indices', 'Commodities'] as const

/**
 * A strip at the top of the Pending Orders tab showing which market
 * sessions are open or closed right now. Client-side classifier only —
 * not a trading gate, see `lib/market-hours.ts` for the caveat.
 */
export function MarketStatusHeader({ className }: { className?: string }) {
  // Re-classify once per minute so the badges stay current as the session
  // rolls. (Rerender is trivial for 6 small divs.)
  const [, force] = useState(0)
  useEffect(() => {
    const t = setInterval(() => force((n) => n + 1), 60_000)
    return () => clearInterval(t)
  }, [])

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-2 py-1 border-b border-[var(--border-subtle)] bg-[var(--bg-2)] overflow-x-auto',
        className,
      )}
    >
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium shrink-0">
        Markets
      </span>
      {CLASSES.map((ac) => {
        const info = classifyAssetClassStatus(ac)
        const colour = marketStatusColour(info.status)
        return (
          <div
            key={ac}
            className="inline-flex items-center gap-1.5 text-[10px] shrink-0"
            title={`${assetClassDisplay(ac)} · ${info.sessionLabel}`}
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{
                backgroundColor: colour,
                boxShadow:
                  info.status === 'open'
                    ? '0 0 5px color-mix(in oklab, var(--pnl-up) 50%, transparent)'
                    : undefined,
              }}
            />
            <span className="text-[var(--text-2)]">{ac}</span>
            <span className="text-[var(--text-3)]">{info.label}</span>
          </div>
        )
      })}
    </div>
  )
}
