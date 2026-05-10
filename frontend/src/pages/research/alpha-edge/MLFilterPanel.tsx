import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber, formatTimestamp } from '@/lib/utils'
import type { MLStats } from '../useResearchData'

interface MLFilterPanelProps {
  data: MLStats | undefined
  loading?: boolean
}

export function MLFilterPanel({ data, loading }: MLFilterPanelProps) {
  const inCount = Number(data?.signals_filtered ?? 0)
  const passCount = Number(data?.signals_passed ?? 0)
  const avgConf = Number(data?.avg_confidence ?? 0)
  const acc = num(data?.model_accuracy)
  const prec = num(data?.model_precision)
  const rec = num(data?.model_recall)
  const f1 = num(data?.model_f1_score)
  const trained = data?.last_trained

  return (
    <Card padding="sm" className="flex flex-col gap-2 min-h-[260px]">
      <SectionLabel className="mb-0">ML filter</SectionLabel>
      {loading && !data ? (
        <div className="flex-1 animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <Stat label="In" value={formatNumber(inCount, 0)} />
            <Stat label="Passed" value={formatNumber(passCount, 0)} tone="up" />
            <Stat label="Avg conf" value={formatNumber(avgConf, 2)} />
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <Stat label="Accuracy" value={acc != null ? `${formatNumber(acc * 100, 1)}%` : '—'} />
            <Stat label="Precision" value={prec != null ? `${formatNumber(prec * 100, 1)}%` : '—'} />
            <Stat label="Recall" value={rec != null ? `${formatNumber(rec * 100, 1)}%` : '—'} />
            <Stat label="F1" value={f1 != null ? formatNumber(f1, 3) : '—'} />
          </div>
          <div className="mt-auto pt-1.5 border-t border-[var(--border-subtle)] text-[10px] flex items-center justify-between">
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
              Last trained
            </span>
            <span className="mono tabular-nums text-[var(--text-1)]">
              {trained ? formatTimestamp(trained, 'short') : '—'}
            </span>
          </div>
        </>
      )}
    </Card>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[13px]',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}

function num(v: number | null | undefined): number | null {
  return v != null && Number.isFinite(v) ? v : null
}
