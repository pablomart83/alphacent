/**
 * Client-side market-hours classifier.
 *
 * Backend has a full MarketHoursManager that knows about holidays, early
 * closes, DST drifts, per-symbol overrides from symbols.yaml, etc. We
 * don't try to recreate that here — this is a UX hint, not a trading
 * gate. It answers: "right now, is the primary session for this asset
 * class open, closed, or in a pre/post window?"
 *
 * Returns: 'open' | 'closed' | 'pre' | 'post' | 'holiday' | 'unknown'.
 *
 * If the user needs the authoritative answer they should look at
 * /positions response where `market_open` is set by the backend.
 */

export type MarketStatus = 'open' | 'closed' | 'pre' | 'post' | 'weekend' | 'unknown'

export interface MarketStatusInfo {
  status: MarketStatus
  label: string
  nextChangeLabel?: string
  /** Subtitle — e.g. "24/7", "Mon–Fri 24h", "NYSE 14:30–21:00 UTC". */
  sessionLabel: string
}

const ASSET_CLASS_LABEL: Record<string, string> = {
  Stocks: 'US equities',
  ETFs: 'US ETFs',
  Indices: 'Global indices',
  Commodities: 'Commodities',
  Crypto: 'Crypto',
  Forex: 'FX',
}

/** Returns UTC minute-of-day for the current Date. */
function utcMinuteOfDay(now: Date): number {
  return now.getUTCHours() * 60 + now.getUTCMinutes()
}

function formatHours(openMin: number, closeMin: number): string {
  const fmt = (m: number) =>
    `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
  return `${fmt(openMin)}–${fmt(closeMin)} UTC`
}

/**
 * US regular session: 09:30–16:00 America/New_York.
 * EDT (Mar–Nov): UTC-4 → 13:30–20:00 UTC
 * EST (Nov–Mar): UTC-5 → 14:30–21:00 UTC
 *
 * We detect DST by checking whether the current UTC offset for New York
 * is -4 (EDT) or -5 (EST) using the Intl API. Falls back to EDT (wider
 * window) if detection fails — better to show "Open" when borderline
 * than to show "Pre-market" when the market is actually open.
 */
function getUsSessionUTC(): { open: number; close: number; pre: number } {
  try {
    // Detect current NY offset by formatting a known time and parsing the offset
    const now = new Date()
    const nyStr = now.toLocaleString('en-US', { timeZone: 'America/New_York', timeZoneName: 'short' })
    const isEDT = nyStr.includes('EDT') || nyStr.includes('GMT-4')
    if (isEDT) {
      return { open: 13 * 60 + 30, close: 20 * 60, pre: 8 * 60 } // EDT: UTC-4
    }
    return { open: 14 * 60 + 30, close: 21 * 60, pre: 9 * 60 } // EST: UTC-5
  } catch {
    return { open: 13 * 60 + 30, close: 20 * 60, pre: 8 * 60 } // fallback: EDT
  }
}

function classifyUsEquities(now: Date): MarketStatusInfo {
  const day = now.getUTCDay() // 0 Sun … 6 Sat
  const { open: US_OPEN_UTC, close: US_CLOSE_UTC, pre: US_PRE_UTC } = getUsSessionUTC()
  const sessionLabel = `NYSE/NASDAQ ${formatHours(US_OPEN_UTC, US_CLOSE_UTC)}`
  if (day === 0 || day === 6) {
    return {
      status: 'weekend',
      label: 'Weekend · closed',
      sessionLabel,
    }
  }
  const m = utcMinuteOfDay(now)
  if (m >= US_OPEN_UTC && m < US_CLOSE_UTC) {
    return { status: 'open', label: 'Regular session', sessionLabel }
  }
  if (m >= US_PRE_UTC && m < US_OPEN_UTC) {
    return { status: 'pre', label: 'Pre-market', sessionLabel }
  }
  if (m >= US_CLOSE_UTC) {
    return { status: 'post', label: 'After-hours', sessionLabel }
  }
  return { status: 'closed', label: 'Closed', sessionLabel }
}

/** Forex: Sun 22:00 UTC → Fri 22:00 UTC, roughly Sydney open → NY close. */
function classifyForex(now: Date): MarketStatusInfo {
  const day = now.getUTCDay()
  const mins = utcMinuteOfDay(now)
  const sessionLabel = '24/5 · Sun 22:00 → Fri 22:00 UTC'

  // Weekend window: Fri after 22:00 UTC through Sun before 22:00 UTC.
  const friClosed = day === 5 && mins >= 22 * 60
  const saturday = day === 6
  const sunBeforeOpen = day === 0 && mins < 22 * 60
  if (friClosed || saturday || sunBeforeOpen) {
    return { status: 'weekend', label: 'Weekend · closed', sessionLabel }
  }
  return { status: 'open', label: 'Open', sessionLabel }
}

function classifyCrypto(): MarketStatusInfo {
  return { status: 'open', label: 'Open · 24/7', sessionLabel: '24/7' }
}

// Commodities & indices: we approximate with US equities hours for the UI.
// (CME futures have their own schedule; we surface it as "similar to US
// equities" since the positions we take are via eToro CFDs that track US
// trading hours.)
function classifyIndicesOrCommodities(now: Date, label: string): MarketStatusInfo {
  const base = classifyUsEquities(now)
  return { ...base, sessionLabel: `${label} · ${base.sessionLabel}` }
}

export function classifyAssetClassStatus(
  assetClass: string | null | undefined,
  now: Date = new Date(),
): MarketStatusInfo {
  const ac = (assetClass || '').toLowerCase()
  if (ac === 'crypto') return classifyCrypto()
  if (ac === 'forex') return classifyForex(now)
  if (ac === 'indices') return classifyIndicesOrCommodities(now, 'Indices CFD')
  if (ac === 'commodities') return classifyIndicesOrCommodities(now, 'Commodities CFD')
  if (ac === 'stocks' || ac === 'etfs' || ac === '')
    return classifyUsEquities(now)
  return {
    status: 'unknown',
    label: 'Unknown',
    sessionLabel: '—',
  }
}

export function assetClassDisplay(assetClass: string | null | undefined): string {
  if (!assetClass) return 'Stocks'
  return ASSET_CLASS_LABEL[assetClass] ?? assetClass
}

/** Map a MarketStatus to a semantic colour token. */
export function marketStatusColour(status: MarketStatus): string {
  switch (status) {
    case 'open':
      return 'var(--pnl-up)'
    case 'pre':
    case 'post':
      return 'var(--status-warning)'
    case 'weekend':
    case 'closed':
      return 'var(--text-3)'
    case 'unknown':
      return 'var(--text-3)'
  }
}
