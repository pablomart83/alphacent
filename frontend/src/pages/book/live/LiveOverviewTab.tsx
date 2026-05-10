import { useMemo } from 'react'
import { Receipt } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { cn, formatAge, formatCurrency, parseUtcIso } from '@/lib/utils'
import {
  useLiveConfig,
  useOrders,
  type OrderRow,
} from '../useBookData'

export function LiveOverviewTab() {
  const config = useLiveConfig()
  const ordersQuery = useOrders({ pinMode: 'LIVE', limit: 50 })

  const recentFills: OrderRow[] = useMemo(() => {
    const rows = ordersQuery.data?.orders ?? []
    return rows
      .filter((r) => r.status === 'FILLED')
      .sort((a, b) => {
        const ta = a.filled_at ? parseUtcIso(a.filled_at).getTime() : 0
        const tb = b.filled_at ? parseUtcIso(b.filled_at).getTime() : 0
        return tb - ta
      })
      .slice(0, 10)
  }, [ordersQuery.data?.orders])

  const mirror = config.data?.mirror_ratio ?? 0.1

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto p-3 gap-3">
      {/* Config reference card */}
      <section className="rounded-[4px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-3">
        <SectionLabel>Live trading config</SectionLabel>
        {config.isLoading ? (
          <Skeleton variant="block" className="h-20" />
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            <ConfigRow label="Virtual balance" value={formatCurrency(config.data?.virtual_balance ?? 0, { precision: 0 })} />
            <ConfigRow label="Real investment" value={formatCurrency(config.data?.real_investment ?? 0, { precision: 0 })} />
            <ConfigRow label="Mirror ratio" value={`${(mirror * 100).toFixed(0)}%`} />
            <ConfigRow
              label="Min / max order"
              value={`${formatCurrency(config.data?.min_order_size ?? 0, { precision: 0 })} – ${formatCurrency(config.data?.max_order_size ?? 0, { precision: 0 })}`}
            />
            <ConfigRow
              label="Per-order real exposure"
              value={`${formatCurrency(config.data?.real_per_virtual_order ?? 0, { precision: 0 })} – ${formatCurrency(config.data?.max_real_per_order ?? 0, { precision: 0 })}`}
            />
            <ConfigRow label="Base risk pct" value={`${(config.data?.base_risk_pct ?? 0).toFixed(2)}%`} />
            <ConfigRow
              label="Symbol cap"
              value={`${(config.data?.symbol_cap_pct ?? 0).toFixed(0)}% of virtual`}
            />
            <ConfigRow
              label="Portfolio heat cap"
              value={`${(config.data?.portfolio_heat_cap ?? 0).toFixed(0)}%`}
            />
            <ConfigRow
              label="Conviction threshold"
              value={`${config.data?.conviction_threshold ?? 74} (equities) · ${config.data?.conviction_threshold_crypto ?? 68} (crypto)`}
            />
          </div>
        )}
      </section>

      {/* Recent live fills */}
      <section className="rounded-[4px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-3">
        <SectionLabel>Recent live fills</SectionLabel>
        {ordersQuery.isLoading && recentFills.length === 0 ? (
          <div className="flex flex-col gap-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} variant="table-row" />
            ))}
          </div>
        ) : recentFills.length === 0 ? (
          <EmptyState
            icon={Receipt}
            title="No live fills yet"
            description="Real fills appear here as approved (template, symbol) pairs fire on live account."
            className="py-6"
          />
        ) : (
          <ul className="divide-y divide-[var(--border-subtle)]">
            {recentFills.map((r) => {
              const isSell = r.side === 'SELL'
              const realInvested = r.quantity * mirror
              return (
                <li key={r.id} className="flex items-center gap-3 py-1.5 text-[11px]">
                  <span
                    className="inline-block h-1.5 w-1.5 rounded-full shrink-0"
                    style={{
                      backgroundColor: isSell ? 'var(--pnl-down)' : 'var(--pnl-up)',
                    }}
                  />
                  <span className="mono font-semibold text-[var(--text-0)] w-[60px] truncate">
                    {r.symbol}
                  </span>
                  <span
                    className={cn(
                      'text-[10px] uppercase tracking-wide font-medium shrink-0',
                      isSell ? 'text-[var(--pnl-down)]' : 'text-[var(--pnl-up)]',
                    )}
                  >
                    {r.side}
                  </span>
                  <span className="text-[10px] text-[var(--text-3)] uppercase tracking-wide">
                    {r.order_action}
                  </span>
                  <span className="mono tabular-nums text-[var(--text-2)]">
                    {formatCurrency(r.quantity, { precision: 0 })}
                    <span className="ml-1 text-[var(--text-3)]">
                      ({formatCurrency(realInvested, { precision: 0 })} real)
                    </span>
                  </span>
                  {r.filled_price != null && (
                    <PnLNumber
                      value={r.filled_price}
                      format="decimal"
                      precision={2}
                      size="sm"
                      muted
                      showSign={false}
                    />
                  )}
                  <span className="ml-auto text-[10px] text-[var(--text-3)] mono">
                    {formatAge(r.filled_at)}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      <span className="mono tabular-nums text-[12px] text-[var(--text-0)]">{value}</span>
    </div>
  )
}
