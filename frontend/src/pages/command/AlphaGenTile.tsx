import { useNavigate } from 'react-router-dom'
import { SectionLabel } from '@/components/layout'
import { cn, formatPercentage } from '@/lib/utils'
import { useAlphaGeneration } from './useCommandData'

/**
 * AlphaGenTile — 7d and 30d total return (alpha generation proxy).
 *
 * Uses the analytics/performance endpoint for 1W and 1M periods.
 * Clicking navigates to Research/Performance.
 *
 * Note: this is total return, not alpha vs SPY. True alpha requires
 * aligning the equity curve with SPY returns over the same period —
 * that computation lives in Research/Performance where the full chart
 * context is available.
 */
export function AlphaGenTile({ className }: { className?: string }) {
  const navigate = useNavigate()
  const { q7d, q30d } = useAlphaGeneration()

  const ret7d = q7d.data?.total_return
  const ret30d = q30d.data?.total_return
  const loading = q7d.isLoading || q30d.isLoading

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Alpha generation</SectionLabel>
      <button
        type="button"
        onClick={() => navigate('/research/performance')}
        className="w-full text-left rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 hover:bg-[var(--bg-hover)] transition-colors"
        title="Open Research / Performance"
      >
        <div className="grid grid-cols-2 gap-2">
          <ReturnCell label="7d return" value={ret7d} loading={loading} />
          <ReturnCell label="30d return" value={ret30d} loading={loading} />
        </div>
      </button>
    </div>
  )
}

function ReturnCell({
  label,
  value,
  loading,
}: {
  label: string
  value: number | null | undefined
  loading: boolean
}) {
  const tone =
    value == null ? 'neutral' : value > 0 ? 'up' : value < 0 ? 'down' : 'neutral'
  const color =
    tone === 'up'
      ? 'var(--pnl-up)'
      : tone === 'down'
        ? 'var(--pnl-down)'
        : 'var(--text-0)'

  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      <span
        className="mono tabular-nums text-[15px] font-bold"
        style={{ color: loading ? 'var(--text-3)' : color }}
      >
        {loading ? '…' : value != null ? formatPercentage(value) : '—'}
      </span>
    </div>
  )
}
