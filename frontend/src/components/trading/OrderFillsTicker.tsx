import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Receipt } from 'lucide-react'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import { cn, formatAge, formatCurrency, parseUtcIso } from '@/lib/utils'
import { EmptyState, Skeleton } from '@/components/primitives'

interface OrderApiRow {
  id: string
  symbol: string
  side: string
  status: string
  price?: number | null
  filled_price?: number | null
  filled_at?: string | null
  expected_price?: number | null
  slippage?: number | null
  fill_time_seconds?: number | null
  order_action?: string | null
  quantity?: number | null
}

interface OrdersResponse {
  orders: OrderApiRow[]
  total_count: number
}

function slippageBps(row: OrderApiRow): number | null {
  if (
    row.slippage != null &&
    Number.isFinite(row.slippage) &&
    row.expected_price != null &&
    row.expected_price > 0
  ) {
    // slippage is in price units → convert to bps of expected price.
    return (row.slippage / row.expected_price) * 10_000
  }
  if (
    row.filled_price != null &&
    row.expected_price != null &&
    row.expected_price > 0
  ) {
    return ((row.filled_price - row.expected_price) / row.expected_price) * 10_000
  }
  return null
}

export function OrderFillsTicker() {
  const mode = useTradingMode((s) => s.mode)
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<OrdersResponse>({
    queryKey: ['orders', mode, { status: 'FILLED', limit: 20 }],
    queryFn: () =>
      api.get<OrdersResponse>('/orders', {
        mode,
        status_filter: 'FILLED',
        limit: 20,
      }),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })

  const fills = useMemo(() => {
    const rows = data?.orders ?? []
    return [...rows]
      .filter((r) => r.status === 'FILLED')
      .sort((a, b) => {
        const ta = a.filled_at ? parseUtcIso(a.filled_at).getTime() : 0
        const tb = b.filled_at ? parseUtcIso(b.filled_at).getTime() : 0
        return tb - ta
      })
      .slice(0, 10)
  }, [data])

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading && fills.length === 0 && (
          <div className="flex flex-col gap-1 p-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} variant="table-row" />
            ))}
          </div>
        )}
        {!isLoading && fills.length === 0 && (
          <EmptyState
            icon={Receipt}
            title="No recent fills"
            description="Filled orders will appear here as positions open and close."
            className="py-6"
          />
        )}
        <ul className="divide-y divide-[var(--border-subtle)]">
          {fills.map((row) => {
            const bps = slippageBps(row)
            const isSell = /SELL|SHORT/i.test(row.side)
            const sideColor = isSell ? 'var(--pnl-down)' : 'var(--pnl-up)'
            const bpsColor =
              bps == null
                ? 'var(--text-3)'
                : Math.abs(bps) < 5
                  ? 'var(--text-2)'
                  : bps > 0
                    ? 'var(--pnl-down)'
                    : 'var(--pnl-up)'

            return (
              <li key={row.id}>
                <button
                  type="button"
                  onClick={() => navigate(`/book?order=${encodeURIComponent(row.id)}`)}
                  className="w-full text-left flex items-center gap-2 px-2 py-1.5 hover:bg-[var(--bg-hover)]"
                >
                  <span
                    className="inline-block h-1 w-1 rounded-full shrink-0"
                    style={{ backgroundColor: sideColor }}
                    aria-hidden
                  />
                  <span className="mono text-[11px] font-semibold text-[var(--text-0)] w-[52px] shrink-0 truncate">
                    {row.symbol}
                  </span>
                  <span
                    className="text-[10px] font-medium uppercase tracking-wide shrink-0"
                    style={{ color: sideColor }}
                  >
                    {isSell ? 'SELL' : 'BUY'}
                  </span>
                  <span className="mono text-[10px] text-[var(--text-2)] shrink-0">
                    {formatCurrency(row.filled_price ?? row.price ?? 0, { precision: 2 })}
                  </span>
                  {bps != null && (
                    <span
                      className="mono text-[10px] shrink-0"
                      style={{ color: bpsColor }}
                      title={`Slippage: ${bps.toFixed(1)} bps`}
                    >
                      {bps >= 0 ? '+' : ''}
                      {bps.toFixed(0)}bp
                    </span>
                  )}
                  <span
                    className={cn(
                      'ml-auto text-[10px] mono text-[var(--text-3)] shrink-0',
                    )}
                  >
                    {formatAge(row.filled_at)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
