import { type FC, useMemo } from 'react';
import { cn } from '../../lib/utils';

const ALL_PERIODS = ['1D', '1W', '1M', '3M', '6M', 'YTD', '1Y', 'ALL'] as const;
const COMPACT_PERIODS = ['1D', '1W', '1M', 'YTD'] as const;

export interface MultiTimeframeViewProps {
  returns: Record<string, { absolute: number | null; alpha: number | null }>;
  onPeriodClick?: (period: string) => void;
  compact?: boolean;
}

function formatReturn(value: number | null): string {
  if (value === null) return 'N/A';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

export const MultiTimeframeView: FC<MultiTimeframeViewProps> = ({
  returns,
  onPeriodClick,
  compact = false,
}) => {
  const periods = useMemo(
    () => (compact ? COMPACT_PERIODS : ALL_PERIODS),
    [compact],
  );

  return (
    <div
      className="flex items-stretch gap-1.5 overflow-x-auto"
      role="group"
      aria-label="Multi-timeframe performance"
    >
      {periods.map((period) => {
        const data = returns[period];
        const absolute = data?.absolute ?? null;
        const alpha = data?.alpha ?? null;
        const isNull = absolute === null;

        const bgClass = isNull
          ? 'bg-dark-surface'
          : absolute > 0
            ? 'bg-positive/10'
            : absolute < 0
              ? 'bg-negative/10'
              : 'bg-dark-surface';

        const borderClass = isNull
          ? 'border-dark-border'
          : absolute > 0
            ? 'border-positive/20'
            : absolute < 0
              ? 'border-negative/20'
              : 'border-dark-border';

        return (
          <button
            key={period}
            type="button"
            onClick={() => onPeriodClick?.(period)}
            disabled={!onPeriodClick}
            aria-label={`${period} return: ${formatReturn(absolute)}, alpha: ${formatReturn(alpha)}`}
            className={cn(
              'flex flex-col items-center justify-center rounded-md border px-3 py-1.5 transition-colors min-w-[64px]',
              bgClass,
              borderClass,
              onPeriodClick && 'cursor-pointer hover:brightness-125',
              !onPeriodClick && 'cursor-default',
            )}
          >
            <span className="text-xs font-medium text-text-secondary mb-0.5">
              {period}
            </span>
            {isNull ? (
              <span className="text-xs font-mono text-text-disabled">N/A</span>
            ) : (
              <>
                <span
                  className={cn(
                    'text-xs font-mono font-semibold leading-tight',
                    absolute! > 0 && 'text-positive',
                    absolute! < 0 && 'text-negative',
                    absolute === 0 && 'text-text-secondary',
                  )}
                >
                  {formatReturn(absolute)}
                </span>
                <span
                  className={cn(
                    'text-xs font-mono leading-tight mt-0.5',
                    alpha !== null && alpha > 0 && 'text-positive/70',
                    alpha !== null && alpha < 0 && 'text-negative/70',
                    (alpha === null || alpha === 0) && 'text-text-tertiary',
                  )}
                >
                  α {formatReturn(alpha)}
                </span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
};
