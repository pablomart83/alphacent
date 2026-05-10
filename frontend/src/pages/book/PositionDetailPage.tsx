import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { PageTemplate } from '@/components/layout'
import {
  Button,
  ErrorState,
  Skeleton,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { PriceChart, type PriceChartSignal } from '@/components/trading/PriceChart'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import { classifyError } from '@/lib/errors'
import { cn, formatCurrency, formatTimestamp } from '@/lib/utils'
import { useOpenPositions } from './useBookData'
import type { PositionRow } from './useBookData'

interface OHLCVApiPoint {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface OrderAnnotationApi {
  date: string
  side: string
  price: number
  order_id?: string | null
}

interface PnLPointApi {
  date: string
  pnl: number
}

interface PositionDetailResponse {
  symbol: string
  entry_price: number
  current_price: number
  side: string
  opened_at?: string | null
  price_history: OHLCVApiPoint[]
  order_annotations: OrderAnnotationApi[]
  pnl_series: PnLPointApi[]
}

type Interval = '1d' | '4h' | '1h'

export function PositionDetailPage() {
  const { symbol: rawSymbol } = useParams<{ symbol: string }>()
  const symbol = decodeURIComponent(rawSymbol || '')
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)
  const [interval, setInterval] = useState<Interval>('1d')

  const openQuery = useOpenPositions()
  const detailQuery = useQuery<PositionDetailResponse>({
    queryKey: ['position-detail', symbol, mode, interval],
    queryFn: () =>
      api.get<PositionDetailResponse>(`/account/positions/${encodeURIComponent(symbol)}/detail`, {
        mode,
        interval,
      }),
    staleTime: 60_000,
    enabled: Boolean(symbol),
  })

  const openMatches: PositionRow[] = useMemo(
    () => (openQuery.data?.positions ?? []).filter((p) => p.symbol === symbol),
    [openQuery.data?.positions, symbol],
  )

  const totals = useMemo(() => {
    let invested = 0
    let unrealized = 0
    for (const p of openMatches) {
      invested += Math.abs(p.invested_amount ?? p.quantity ?? 0)
      unrealized += p.unrealized_pnl ?? 0
    }
    return { invested, unrealized }
  }, [openMatches])

  const signals: PriceChartSignal[] = useMemo(() => {
    const list: PriceChartSignal[] = []
    for (const a of detailQuery.data?.order_annotations ?? []) {
      list.push({
        timestamp: a.date,
        type: 'entry', // backend returns entry/exit order prints — the shape only
        side: a.side,
        price: a.price,
      })
    }
    return list
  }, [detailQuery.data?.order_annotations])

  const detail = detailQuery.data

  return (
    <PageTemplate
      title={symbol || 'Position'}
      description={`${mode} · ${openMatches.length} open`}
      actions={
        <Button variant="ghost" size="sm" onClick={() => navigate('/book/positions')} className="gap-1.5">
          <ArrowLeft className="h-3 w-3" />
          Back
        </Button>
      }
    >
      <div className="flex flex-col h-full min-h-0">
        {/* Summary strip */}
        <div className="grid grid-cols-4 gap-2 p-3 border-b border-[var(--border-subtle)] bg-[var(--bg-1)] shrink-0">
          <SummaryTile label="Invested" value={formatCurrency(totals.invested, { precision: 0 })} mono />
          <PnlTile label="Unrealised" value={totals.unrealized} />
          <SummaryTile
            label="Entry"
            value={
              detail
                ? formatCurrency(detail.entry_price, { precision: 4 })
                : openMatches[0]
                  ? formatCurrency(openMatches[0].entry_price, { precision: 4 })
                  : '—'
            }
            mono
          />
          <SummaryTile
            label="Current"
            value={
              detail
                ? formatCurrency(detail.current_price, { precision: 4 })
                : openMatches[0]
                  ? formatCurrency(openMatches[0].current_price, { precision: 4 })
                  : '—'
            }
            mono
          />
        </div>

        {/* Chart toolbar */}
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)] shrink-0">
          <span className="text-[11px] text-[var(--text-2)]">Interval</span>
          <Select value={interval} onValueChange={(v) => setInterval(v as Interval)}>
            <SelectTrigger size="sm" className="h-7 min-w-[80px] text-[11px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1d">1d</SelectItem>
              <SelectItem value="4h">4h</SelectItem>
              <SelectItem value="1h">1h</SelectItem>
            </SelectContent>
          </Select>
          {detail?.opened_at && (
            <span className="ml-auto text-[10px] text-[var(--text-3)]">
              Opened {formatTimestamp(detail.opened_at, 'short')}
            </span>
          )}
        </div>

        {/* Chart */}
        <div className="flex-1 min-h-0 min-h-[320px]">
          {detailQuery.isError ? (
            <ErrorState
              title="Couldn't load position detail"
              message={classifyError(detailQuery.error, 'position detail').message}
              onRetry={() => detailQuery.refetch()}
            />
          ) : detailQuery.isLoading ? (
            <div className="p-3 h-full">
              <Skeleton variant="chart" className="h-full" />
            </div>
          ) : (
            <PriceChart
              symbol={symbol}
              bars={detail?.price_history ?? []}
              signals={signals}
              interval={interval}
            />
          )}
        </div>

        {/* Positions for this symbol — brief list */}
        {openMatches.length > 0 && (
          <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-0)] p-3 shrink-0 max-h-[200px] overflow-auto">
            <div className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium mb-1.5">
              Open positions for {symbol}
            </div>
            <ul className="flex flex-col gap-1">
              {openMatches.map((p) => (
                <li
                  key={p.id}
                  className="flex items-center gap-2 text-[11px] p-1.5 rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)]"
                >
                  <span className="text-[var(--text-2)] truncate max-w-[220px]">
                    {p.strategy_name || '—'}
                  </span>
                  <span className="mono tabular-nums text-[var(--text-2)]">
                    {p.side.toUpperCase()}
                  </span>
                  <span className="mono tabular-nums text-[var(--text-2)]">
                    {formatCurrency(p.invested_amount ?? p.quantity ?? 0, { precision: 0 })}
                  </span>
                  <PnLNumber value={p.unrealized_pnl} format="currency" precision={0} size="sm" />
                  <PnLNumber
                    value={p.unrealized_pnl_percent}
                    format="percentage"
                    precision={2}
                    size="sm"
                  />
                  <span className="ml-auto text-[10px] text-[var(--text-3)]">
                    opened {formatTimestamp(p.opened_at, 'short')}
                  </span>
                  <Link
                    to="/book/positions"
                    className="text-[10px] text-[var(--accent-primary)] hover:underline"
                  >
                    Back to table
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </PageTemplate>
  )
}

function SummaryTile({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[3px] bg-[var(--bg-2)] border border-[var(--border-subtle)] px-2.5 py-1.5">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      <span className={cn('text-[14px] font-semibold text-[var(--text-0)]', mono && 'mono tabular-nums')}>
        {value}
      </span>
    </div>
  )
}

function PnlTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[3px] bg-[var(--bg-2)] border border-[var(--border-subtle)] px-2.5 py-1.5">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      <PnLNumber value={value} format="currency" precision={0} size="lg" />
    </div>
  )
}
