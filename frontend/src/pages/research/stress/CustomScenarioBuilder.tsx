import { useMemo, useState } from 'react'
import { Card, Input, Label } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatCurrency } from '@/lib/utils'
import { useOpenPositions } from '@/pages/book/useBookData'

/**
 * Client-side custom-scenario builder.
 *
 * Takes the current open-positions list (from /account/positions), applies a
 * symbol-specific shock percentage (or uniform fallback), widens vol-scaled
 * risk, and reports simulated P&L. No backend endpoint yet — kept honest by
 * rendering a banner that says so.
 */
export function CustomScenarioBuilder() {
  const positions = useOpenPositions()
  const [symbolShock, setSymbolShock] = useState<number>(-5)
  const [volMultiplier, setVolMultiplier] = useState<number>(2)
  const [correlationShift, setCorrelationShift] = useState<number>(0.3)
  const [horizonDays, setHorizonDays] = useState<number>(5)

  const result = useMemo(() => {
    const openPositions = (positions.data?.positions ?? []).filter(
      (p) => !p.closed_at && (p.invested_amount ?? 0) > 0,
    )
    if (!openPositions.length) {
      return {
        simulatedPnl: 0,
        worstSymbol: null as { symbol: string; pnl: number } | null,
        positionImpact: [] as Array<{ symbol: string; pnl: number; invested: number }>,
      }
    }

    // Each position's shock is the symbol shock scaled by vol multiplier and
    // correlation-shift amplification. Horizon-day scaling dampens per-day moves.
    const scaledShock =
      (symbolShock / 100) *
      volMultiplier *
      (1 + correlationShift) *
      Math.sqrt(Math.max(1, horizonDays) / 5)

    const impact = openPositions.map((p) => {
      const invested = Math.abs(p.invested_amount ?? 0)
      // Long exposure loses when shock is negative; short wins.
      const directional = p.side === 'SHORT' ? -scaledShock : scaledShock
      const pnl = invested * directional
      return { symbol: p.symbol, pnl, invested }
    })

    const simulated = impact.reduce((a, r) => a + r.pnl, 0)
    const worst = impact.reduce<null | { symbol: string; pnl: number }>((acc, r) => {
      if (!acc || r.pnl < acc.pnl) return { symbol: r.symbol, pnl: r.pnl }
      return acc
    }, null)
    return { simulatedPnl: simulated, worstSymbol: worst, positionImpact: impact }
  }, [positions.data, symbolShock, volMultiplier, correlationShift, horizonDays])

  return (
    <Card padding="md" className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <SectionLabel className="mb-0">Custom scenario builder</SectionLabel>
        <span className="text-[10px] text-[var(--text-3)]">
          Client-side estimate over {positions.data?.positions?.length ?? 0} open positions
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <FormField label="Symbol shock (%)" suffix="%">
          <Input
            type="number"
            value={symbolShock}
            onChange={(e) => setSymbolShock(Number(e.target.value))}
            step={0.5}
            className="h-7 mono tabular-nums"
          />
        </FormField>
        <FormField label="Vol multiplier" suffix="×">
          <Input
            type="number"
            value={volMultiplier}
            onChange={(e) => setVolMultiplier(Math.max(0.1, Number(e.target.value)))}
            step={0.1}
            min={0.1}
            max={10}
            className="h-7 mono tabular-nums"
          />
        </FormField>
        <FormField label="Correlation shift" suffix="Δρ">
          <Input
            type="number"
            value={correlationShift}
            onChange={(e) =>
              setCorrelationShift(Math.max(-1, Math.min(1, Number(e.target.value))))
            }
            step={0.05}
            min={-1}
            max={1}
            className="h-7 mono tabular-nums"
          />
        </FormField>
        <FormField label="Time horizon" suffix="d">
          <Input
            type="number"
            value={horizonDays}
            onChange={(e) => setHorizonDays(Math.max(1, Number(e.target.value)))}
            step={1}
            min={1}
            max={90}
            className="h-7 mono tabular-nums"
          />
        </FormField>
      </div>
      <div className="flex flex-wrap items-center gap-4 border-t border-[var(--border-subtle)] pt-2">
        <div>
          <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
            Simulated P&L
          </div>
          <div
            className={cn(
              'mono tabular-nums text-[22px] font-semibold',
              result.simulatedPnl >= 0 ? 'text-[var(--pnl-up)]' : 'text-[var(--pnl-down)]',
            )}
          >
            {formatCurrency(result.simulatedPnl, { signed: true, precision: 0 })}
          </div>
        </div>
        {result.worstSymbol && (
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
              Worst position
            </div>
            <div className="text-[12px] mono">
              <span className="text-[var(--text-1)]">{result.worstSymbol.symbol}</span>
              <span className="ml-2 text-[var(--pnl-down)]">
                {formatCurrency(result.worstSymbol.pnl, { signed: true })}
              </span>
            </div>
          </div>
        )}
        <div className="ml-auto text-[10px] text-[var(--text-3)] max-w-[420px]">
          Model applies `shock × vol × (1+Δρ) × √(H/5)` per position; short positions
          profit on negative shocks. Use as a what-if, not a VaR.
        </div>
      </div>
      {result.positionImpact.length > 0 && (
        <details className="text-[11px]">
          <summary className="cursor-pointer text-[var(--text-2)] hover:text-[var(--text-0)]">
            Per-position breakdown ({result.positionImpact.length})
          </summary>
          <div className="mt-2 max-h-[200px] overflow-auto space-y-0.5">
            {result.positionImpact
              .slice()
              .sort((a, b) => a.pnl - b.pnl)
              .map((r) => (
                <div
                  key={r.symbol}
                  className="grid grid-cols-[120px_1fr_120px] items-center gap-2"
                >
                  <span className="mono text-[var(--text-1)]">{r.symbol}</span>
                  <span className="mono tabular-nums text-[10px] text-[var(--text-3)]">
                    {formatCurrency(r.invested, { compact: true, precision: 0 })} invested
                  </span>
                  <span
                    className={cn(
                      'mono tabular-nums text-right',
                      r.pnl >= 0 ? 'text-[var(--pnl-up)]' : 'text-[var(--pnl-down)]',
                    )}
                  >
                    {formatCurrency(r.pnl, { signed: true, precision: 0 })}
                  </span>
                </div>
              ))}
          </div>
        </details>
      )}
    </Card>
  )
}

function FormField({
  label,
  suffix,
  children,
}: {
  label: string
  suffix?: string
  children: React.ReactNode
}) {
  return (
    <div className="space-y-1">
      <Label className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </Label>
      <div className="flex items-center gap-1">
        {children}
        {suffix && <span className="text-[10px] text-[var(--text-3)]">{suffix}</span>}
      </div>
    </div>
  )
}
