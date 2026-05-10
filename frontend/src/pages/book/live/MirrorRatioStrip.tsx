import { Info } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'
import type { LiveConfig } from '../useBookData'

interface MirrorRatioStripProps {
  config: LiveConfig | undefined
}

export function MirrorRatioStrip({ config }: MirrorRatioStripProps) {
  if (!config) return null
  const mirror = (config.mirror_ratio * 100).toFixed(0)
  return (
    <div className="flex items-start gap-2 px-3 py-2 rounded-[3px] bg-[var(--bg-2)] border border-[var(--border-subtle)] text-[11px] leading-[16px]">
      <Info className="h-3.5 w-3.5 mt-[1px] shrink-0 text-[var(--accent-primary)]" />
      <p className="text-[var(--text-1)]">
        Mirror ratio <span className="mono font-semibold">{mirror}%</span> — each live order
        deploys {' '}
        <span className="mono text-[var(--text-0)]">
          {formatCurrency(config.min_order_size, { precision: 0 })}
        </span>
        –
        <span className="mono text-[var(--text-0)]">
          {formatCurrency(config.max_order_size, { precision: 0 })}
        </span>{' '}
        virtual, placing{' '}
        <span className="mono text-[var(--text-0)]">
          {formatCurrency(config.real_per_virtual_order, { precision: 0 })}
        </span>
        –
        <span className="mono text-[var(--text-0)]">
          {formatCurrency(config.max_real_per_order, { precision: 0 })}
        </span>{' '}
        of real capital per order. Conviction threshold{' '}
        <span className="mono font-semibold">{config.conviction_threshold}</span> for equities,{' '}
        <span className="mono font-semibold">{config.conviction_threshold_crypto}</span> for
        crypto. Symbol cap{' '}
        <span className="mono">{config.symbol_cap_pct.toFixed(0)}%</span> of virtual balance.
      </p>
    </div>
  )
}
