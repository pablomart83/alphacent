import { useNavigate } from 'react-router-dom'
import { SectionLabel } from '@/components/layout'
import { StatInline } from '@/components/primitives'
import { cn, formatPercentage } from '@/lib/utils'
import { useAlphaGeneration } from './useCommandData'

/**
 * AlphaGenTile — 7d and 30d total return + win rate.
 *
 * Uses the analytics/performance endpoint for 1W and 1M periods.
 * Clicking navigates to Research/Performance.
 */
export function AlphaGenTile({ className }: { className?: string }) {
  const navigate = useNavigate()
  const { q7d, q30d } = useAlphaGeneration()

  const ret7d = q7d.data?.total_return
  const ret30d = q30d.data?.total_return
  const wr30d = q30d.data?.win_rate
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
        <div className="grid grid-cols-3 gap-2">
          <ReturnCell label="7d return" value={ret7d} loading={loading} />
          <ReturnCell label="30d return" value={ret30d} loading={loading} />
          <ReturnCell label="30d win rate" value={wr30d != null ? wr30d / 100 : null} loading={loading} isPercent />
        </div>
      </button>
    </div>
  )
}

function ReturnCell({
  label,
  value,
  loading,
  isPercent = false,
}: {
  label: string
  value: number | null | undefined
  loading: boolean
  isPercent?: boolean
}) {
  const tone =
    loading || value == null ? 'strong' : value > 0 ? 'up' : value < 0 ? 'down' : 'strong'

  const display = loading
    ? '…'
    : value != null
      ? isPercent
        ? `${(value * 100).toFixed(1)}%`
        : formatPercentage(value)
      : '—'

  return (
    <StatInline
      label={label}
      value={display}
      size="md"
      tone={tone}
      valueColor={loading ? 'var(--text-3)' : undefined}
    />
  )
}
