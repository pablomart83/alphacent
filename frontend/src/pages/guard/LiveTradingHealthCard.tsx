import { useNavigate } from 'react-router-dom'
import { Rocket } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { StatInline } from '@/components/primitives'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import { useLiveSummary } from '@/pages/book/useBookData'

/**
 * LiveTradingHealthCard — compact live account status in the Guard left panel.
 *
 * Shows: virtual equity, real equity, mirror ratio, live positions,
 * today's real P&L, and days since last live fill.
 * Clicking navigates to Book/Live.
 */
export function LiveTradingHealthCard() {
  const navigate = useNavigate()
  const summary = useLiveSummary()
  const d = summary.data

  const liveEnabled = d?.live_enabled ?? false
  const livePositions = d?.open_positions ?? 0
  const virtualEquity = d?.virtual_equity
  const realEquity = d?.real_equity
  const todayReal = d?.today_pnl_real
  const mirrorRatio = d?.mirror_ratio
  const liveAuths = d?.active_live_authorizations ?? 0

  return (
    <section className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Rocket
            className={cn(
              'h-3.5 w-3.5',
              liveEnabled ? 'text-[var(--pnl-up)]' : 'text-[var(--text-3)]',
            )}
          />
          <SectionLabel className="mb-0">Live account</SectionLabel>
        </div>
        <button
          type="button"
          onClick={() => navigate('/book/live')}
          className="text-[9px] text-[var(--accent-primary)] hover:underline"
        >
          Open →
        </button>
      </div>

      <div
        className={cn(
          'inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[2px] text-[10px] font-semibold',
          liveEnabled
            ? 'bg-[color-mix(in_oklab,var(--pnl-up)_15%,transparent)] text-[var(--pnl-up)]'
            : 'bg-[var(--bg-2)] text-[var(--text-3)]',
        )}
      >
        {liveEnabled ? '● LIVE ON' : '○ LIVE OFF'}
        {liveEnabled && liveAuths > 0 && (
          <span className="ml-1 text-[var(--text-2)]">· {liveAuths} auth{liveAuths === 1 ? '' : 's'}</span>
        )}
      </div>

      {summary.isLoading ? (
        <div className="h-[60px] animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : (
        <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
          <Stat label="Virtual equity" value={virtualEquity != null ? formatCurrency(virtualEquity, { precision: 0 }) : '—'} />
          <Stat label="Real equity" value={realEquity != null ? formatCurrency(realEquity, { precision: 0 }) : '—'} />
          <Stat label="Live positions" value={formatNumber(livePositions, 0)} />
          <Stat
            label="Today (real)"
            value={todayReal != null ? formatCurrency(todayReal, { signed: true, precision: 0 }) : '—'}
            tone={todayReal != null && todayReal > 0 ? 'up' : todayReal != null && todayReal < 0 ? 'down' : 'neutral'}
          />
          {mirrorRatio != null && (
            <Stat label="Mirror ratio" value={`${formatNumber(mirrorRatio * 100, 0)}%`} />
          )}
        </div>
      )}
    </section>
  )
}

function Stat({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <StatInline
      label={label}
      value={value}
      size="sm"
      tone={tone === 'neutral' ? 'default' : tone}
    />
  )
}
