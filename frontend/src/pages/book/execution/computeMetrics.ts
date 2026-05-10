import { parseUtcIso } from '@/lib/utils'
import { slippageBps } from '../orders/orderColumns'
import type { OrderRow } from '../useBookData'

/** Period → number of days (ALL → null). */
export const EXECUTION_PERIODS = ['1D', '1W', '1M', '3M'] as const
export type ExecutionPeriod = (typeof EXECUTION_PERIODS)[number]

const PERIOD_DAYS: Record<ExecutionPeriod, number> = {
  '1D': 1,
  '1W': 7,
  '1M': 30,
  '3M': 90,
}

/* ───── Percentile helper (NaN-safe). ───── */
function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const rank = (p / 100) * (sorted.length - 1)
  const lo = Math.floor(rank)
  const hi = Math.ceil(rank)
  if (lo === hi) return sorted[lo]
  const frac = rank - lo
  return sorted[lo] * (1 - frac) + sorted[hi] * frac
}

export interface ExecutionTiles {
  filledCount: number
  avgSlippageBps: number | null
  fillRatePct: number // 0-100 of (filled / attempted-excluding-retirement)
  avgFillTimeSec: number | null
  rejectionRatePct: number // 0-100 of (rejected+failed / attempted-excluding-retirement)
  implementationShortfallBps: number | null
  sampleCoveragePct: number // proportion of FILLED entries with slippage data
}

export interface SlippageTrendPoint {
  date: string // YYYY-MM-DD
  p50: number | null
  p75: number | null
  p95: number | null
  count: number
}

export interface SlippageByStrategy {
  strategy: string
  avgBps: number
  count: number
}

export interface SlippageHeatmapCell {
  dow: number // 0 Sun … 6 Sat
  hour: number // 0 … 23 (UTC)
  avgBps: number | null
  count: number
}

export interface RejectionReason {
  reason: string
  count: number
}

export interface WorstExecution {
  row: OrderRow
  shortfallBps: number
}

export interface FillRateBucket {
  label: string // "<5s", "5–30s", "30–60s", ">60s"
  count: number
  pct: number
}

export interface AssetClassStat {
  assetClass: string
  avgBps: number | null
  fillRatePct: number
  filledCount: number
  totalCount: number
}

export interface ExecutionAnalytics {
  tiles: ExecutionTiles
  trend: SlippageTrendPoint[]
  byStrategy: SlippageByStrategy[]
  heatmap: SlippageHeatmapCell[]
  rejections: RejectionReason[]
  fillBuckets: FillRateBucket[]
  worst: WorstExecution[]
  byAssetClass: AssetClassStat[]
}

/** Normalise a raw rejection reason string to a category for bar chart. */
function categorizeRejection(raw: string): string {
  const r = raw.toLowerCase()
  if (r.includes('circuit')) return 'Circuit breaker'
  if (r.includes('market') && (r.includes('closed') || r.includes('hours'))) return 'Market closed'
  if (r.includes('risk') || r.includes('cap') || r.includes('limit')) return 'Risk limit'
  if (r.includes('margin') || r.includes('cash')) return 'Insufficient margin'
  if (r.includes('symbol') || r.includes('instrument') || r.includes('unknown'))
    return 'Unknown instrument'
  if (r.includes('spread') || r.includes('price')) return 'Spread / price'
  if (r.includes('duplicate') || r.includes('cooldown')) return 'Deduplication'
  return 'Other'
}

function assetClassFor(symbol: string, provided: string | null | undefined): string {
  if (provided) return provided
  const up = symbol.toUpperCase()
  if (/^[A-Z]{6}$/.test(up)) return 'Forex'
  if (/^(BTC|ETH|XRP|ADA|SOL|DOT|LTC|MATIC|AVAX|LINK)/.test(up)) return 'Crypto'
  return 'Stocks'
}

/** Shortfall bps for a filled order with expected_price. */
function shortfallBps(row: OrderRow): number | null {
  const v = slippageBps(row)
  return v == null ? null : v
}

export function computeExecutionAnalytics(
  orders: OrderRow[],
  period: ExecutionPeriod,
): ExecutionAnalytics {
  const cutoff = Date.now() - PERIOD_DAYS[period] * 86_400_000

  // Scope to orders with a timestamp inside the period (by created_at or filled_at).
  const scoped = orders.filter((o) => {
    const ref = o.filled_at ? parseUtcIso(o.filled_at).getTime() : o.created_at ? parseUtcIso(o.created_at).getTime() : 0
    return Number.isFinite(ref) && ref >= cutoff
  })

  // Exclude retirement orders from fill-rate / rejection-rate denominators —
  // they represent system-initiated closes, not trading decisions.
  const tradedScope = scoped.filter((o) => o.order_action !== 'retirement')
  const filled = tradedScope.filter((o) => o.status === 'FILLED')
  const rejected = tradedScope.filter(
    (o) => o.status === 'REJECTED' || o.status === 'FAILED',
  )
  const pending = tradedScope.filter(
    (o) => o.status === 'PENDING' || o.status === 'SUBMITTED',
  )

  /* ── Tiles ── */
  const filledSlippages: number[] = []
  const filledTimes: number[] = []
  let filledWithSlippage = 0
  for (const o of filled) {
    const bps = shortfallBps(o)
    if (bps != null) {
      filledSlippages.push(bps)
      filledWithSlippage++
    }
    if (o.fill_time_seconds != null && o.fill_time_seconds >= 0) {
      filledTimes.push(o.fill_time_seconds)
    }
  }
  const tradedCount = tradedScope.length || 0
  const fillRatePct = tradedCount > 0 ? (filled.length / tradedCount) * 100 : 0
  const rejectionRatePct = tradedCount > 0 ? (rejected.length / tradedCount) * 100 : 0
  const avgSlippage =
    filledSlippages.length > 0
      ? filledSlippages.reduce((a, b) => a + b, 0) / filledSlippages.length
      : null
  const avgFillTime =
    filledTimes.length > 0
      ? filledTimes.reduce((a, b) => a + b, 0) / filledTimes.length
      : null
  // Implementation shortfall approximated as average absolute slippage.
  const shortfall =
    filledSlippages.length > 0
      ? filledSlippages.map((v) => Math.abs(v)).reduce((a, b) => a + b, 0) / filledSlippages.length
      : null

  const tiles: ExecutionTiles = {
    filledCount: filled.length,
    avgSlippageBps: avgSlippage,
    fillRatePct,
    avgFillTimeSec: avgFillTime,
    rejectionRatePct,
    implementationShortfallBps: shortfall,
    sampleCoveragePct:
      filled.length > 0 ? (filledWithSlippage / filled.length) * 100 : 0,
  }

  // Add pending count onto nothing — consumers already have `pending.length` via scoped filters.
  void pending

  /* ── Slippage trend (daily P50/P75/P95 from filled with slippage) ── */
  const byDay = new Map<string, number[]>()
  for (const o of filled) {
    const bps = shortfallBps(o)
    if (bps == null || !o.filled_at) continue
    const day = parseUtcIso(o.filled_at).toISOString().slice(0, 10)
    const arr = byDay.get(day) ?? []
    arr.push(bps)
    byDay.set(day, arr)
  }
  const trend: SlippageTrendPoint[] = [...byDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, values]) => ({
      date,
      p50: percentile(values, 50),
      p75: percentile(values, 75),
      p95: percentile(values, 95),
      count: values.length,
    }))

  /* ── By strategy (top 10 avg slippage) ── */
  const byStrat = new Map<string, { sum: number; n: number }>()
  for (const o of filled) {
    const bps = shortfallBps(o)
    if (bps == null) continue
    const key = o.strategy_name || o.strategy_id || 'Unknown'
    const cur = byStrat.get(key) ?? { sum: 0, n: 0 }
    cur.sum += bps
    cur.n++
    byStrat.set(key, cur)
  }
  const byStrategy: SlippageByStrategy[] = [...byStrat.entries()]
    .map(([strategy, { sum, n }]) => ({
      strategy,
      avgBps: sum / n,
      count: n,
    }))
    .filter((r) => r.count >= 3)
    .sort((a, b) => Math.abs(b.avgBps) - Math.abs(a.avgBps))
    .slice(0, 15)

  /* ── Heatmap (day-of-week × hour of day) ── */
  const cellMap = new Map<string, { sum: number; n: number }>()
  for (const o of filled) {
    const bps = shortfallBps(o)
    if (bps == null || !o.filled_at) continue
    const d = parseUtcIso(o.filled_at)
    const dow = d.getUTCDay()
    const hour = d.getUTCHours()
    const key = `${dow}-${hour}`
    const cur = cellMap.get(key) ?? { sum: 0, n: 0 }
    cur.sum += bps
    cur.n++
    cellMap.set(key, cur)
  }
  const heatmap: SlippageHeatmapCell[] = []
  for (let dow = 0; dow < 7; dow++) {
    for (let hour = 0; hour < 24; hour++) {
      const cur = cellMap.get(`${dow}-${hour}`)
      heatmap.push({
        dow,
        hour,
        avgBps: cur ? cur.sum / cur.n : null,
        count: cur ? cur.n : 0,
      })
    }
  }

  /* ── Rejection reasons ── */
  // We don't have a structured reason column — use closure_reason fallback via status-only heuristics.
  const rejectionCounts = new Map<string, number>()
  for (const o of rejected) {
    // No explicit reason field on OrderORM — classify FAILED vs REJECTED vs
    // market-closed via status only. When more data lands we swap in here.
    let cat = 'Other'
    if (o.status === 'FAILED') cat = 'Market closed (cosmetic)'
    else if (o.status === 'REJECTED') cat = categorizeRejection('')
    rejectionCounts.set(cat, (rejectionCounts.get(cat) ?? 0) + 1)
  }
  const rejections: RejectionReason[] = [...rejectionCounts.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count)

  /* ── Fill-time buckets ── */
  const buckets = { lt5: 0, lt30: 0, lt60: 0, gte60: 0 }
  for (const t of filledTimes) {
    if (t < 5) buckets.lt5++
    else if (t < 30) buckets.lt30++
    else if (t < 60) buckets.lt60++
    else buckets.gte60++
  }
  const total = filledTimes.length || 1
  const fillBuckets: FillRateBucket[] = [
    { label: '< 5s', count: buckets.lt5, pct: (buckets.lt5 / total) * 100 },
    { label: '5–30s', count: buckets.lt30, pct: (buckets.lt30 / total) * 100 },
    { label: '30–60s', count: buckets.lt60, pct: (buckets.lt60 / total) * 100 },
    { label: '> 60s', count: buckets.gte60, pct: (buckets.gte60 / total) * 100 },
  ]

  /* ── Worst 20 executions by absolute slippage ── */
  const worstScratch: WorstExecution[] = []
  for (const o of filled) {
    const bps = shortfallBps(o)
    if (bps == null) continue
    worstScratch.push({ row: o, shortfallBps: bps })
  }
  worstScratch.sort((a, b) => Math.abs(b.shortfallBps) - Math.abs(a.shortfallBps))
  const worst = worstScratch.slice(0, 20)

  /* ── Per-asset-class stats ── */
  const acMap = new Map<string, { slip: number[]; filled: number; total: number }>()
  for (const o of tradedScope) {
    const ac = assetClassFor(o.symbol, null)
    const entry = acMap.get(ac) ?? { slip: [], filled: 0, total: 0 }
    entry.total++
    if (o.status === 'FILLED') {
      entry.filled++
      const bps = shortfallBps(o)
      if (bps != null) entry.slip.push(bps)
    }
    acMap.set(ac, entry)
  }
  const byAssetClass: AssetClassStat[] = [...acMap.entries()]
    .map(([assetClass, v]) => ({
      assetClass,
      avgBps: v.slip.length > 0 ? v.slip.reduce((a, b) => a + b, 0) / v.slip.length : null,
      fillRatePct: v.total > 0 ? (v.filled / v.total) * 100 : 0,
      filledCount: v.filled,
      totalCount: v.total,
    }))
    .sort((a, b) => b.totalCount - a.totalCount)

  return {
    tiles,
    trend,
    byStrategy,
    heatmap,
    rejections,
    fillBuckets,
    worst,
    byAssetClass,
  }
}
