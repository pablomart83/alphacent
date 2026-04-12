import { type FC, memo } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '../../lib/utils';
import { AnimatedNumber } from '../ui/animated-number';

export interface CompactMetric {
  label: string;
  value: string | number;
  /** Optional trend: positive, negative, or neutral */
  trend?: 'up' | 'down' | 'neutral';
  /** Optional color override */
  color?: string;
}

interface CompactMetricRowProps {
  metrics: CompactMetric[];
  className?: string;
}

/** Try to extract a raw number from a formatted string like "$465,234" or "+12.5%" */
function parseNumericValue(val: string | number): { isNumeric: boolean; num: number; isCurrency: boolean; isPercentage: boolean; decimals: number } {
  if (typeof val === 'number') return { isNumeric: true, num: val, isCurrency: false, isPercentage: false, decimals: 2 };
  const s = String(val).trim();
  const isPercentage = s.endsWith('%');
  const isCurrency = s.startsWith('$') || s.startsWith('-$') || s.startsWith('+$');
  // Strip formatting chars
  const cleaned = s.replace(/[$,%+\s]/g, '').replace(/,/g, '');
  const num = parseFloat(cleaned);
  if (isNaN(num)) return { isNumeric: false, num: 0, isCurrency: false, isPercentage: false, decimals: 0 };
  // Detect decimals from original string
  const dotIdx = cleaned.indexOf('.');
  const decimals = dotIdx >= 0 ? cleaned.length - dotIdx - 1 : 0;
  return { isNumeric: true, num: s.startsWith('-') ? -Math.abs(num) : num, isCurrency, isPercentage, decimals };
}

export const CompactMetricRow: FC<CompactMetricRowProps> = memo(({ metrics, className }) => {
  return (
    <div
      className={cn(
        'flex items-center gap-3 px-3 h-10 max-h-[40px] min-h-[40px] overflow-x-auto scrollbar-hide',
        'bg-[var(--color-dark-surface)] border border-[var(--color-dark-border)] rounded-lg',
        className
      )}
    >
      {metrics.map((metric, idx) => {
        const parsed = parseNumericValue(metric.value);
        const valueClass = cn(
          'text-xs font-mono font-semibold whitespace-nowrap',
          metric.color
            ? undefined
            : metric.trend === 'up'
              ? 'text-[#22c55e]'
              : metric.trend === 'down'
                ? 'text-[#ef4444]'
                : 'text-gray-100'
        );
        const valueStyle = metric.color ? { color: metric.color } : undefined;

        return (
          <div key={idx} className="flex items-center gap-1.5 shrink-0">
            <span className="text-[10px] text-gray-500 uppercase tracking-wide whitespace-nowrap">
              {metric.label}
            </span>
            {parsed.isNumeric ? (
              <AnimatedNumber
                value={parsed.num}
                format={parsed.isCurrency ? 'currency' : parsed.isPercentage ? 'percentage' : parsed.decimals === 0 ? 'integer' : 'number'}
                decimals={parsed.decimals}
                showSign={String(metric.value).startsWith('+')}
                className={valueClass}
              />
            ) : (
              <span className={valueClass} style={valueStyle}>
                {metric.value}
              </span>
            )}
            {metric.trend && <TrendIcon trend={metric.trend} />}
            {idx < metrics.length - 1 && (
              <div className="w-px h-3 bg-gray-700/50 ml-1.5" />
            )}
          </div>
        );
      })}
    </div>
  );
});

const TrendIcon: FC<{ trend: 'up' | 'down' | 'neutral' }> = ({ trend }) => {
  if (trend === 'up') return <TrendingUp size={10} className="text-[#22c55e]" />;
  if (trend === 'down') return <TrendingDown size={10} className="text-[#ef4444]" />;
  return <Minus size={10} className="text-gray-500" />;
};
