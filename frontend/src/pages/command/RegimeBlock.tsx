import { useNavigate } from 'react-router-dom'
import { RegimePill } from '@/components/trading/RegimePill'
import { SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'

interface RegimeBlockProps {
  regime: string | null | undefined
  confidence?: number | null
  dataQuality?: string | null
  description?: string | null
  className?: string
}

export function RegimeBlock({
  regime,
  confidence,
  dataQuality,
  description,
  className,
}: RegimeBlockProps) {
  const navigate = useNavigate()
  const quality =
    dataQuality === 'high' || dataQuality === 'medium' || dataQuality === 'low'
      ? dataQuality
      : undefined

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Regime</SectionLabel>
      <button
        type="button"
        onClick={() => navigate('/research')}
        className="w-full text-left rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 hover:bg-[var(--bg-hover)] transition-colors"
        aria-label="Regime detail"
      >
        <div className="flex items-center gap-2">
          <RegimePill
            regime={regime || 'unknown'}
            confidence={confidence ?? undefined}
            dataQuality={quality}
            size="md"
          />
        </div>
        {description && (
          <p className="mt-1.5 text-[10px] text-[var(--text-2)] leading-[14px]">
            {description}
          </p>
        )}
      </button>
    </div>
  )
}
