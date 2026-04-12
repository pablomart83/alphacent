import { type FC, memo } from 'react';
import { cn } from '../../lib/utils';

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'] as const;
export type TvPeriod = (typeof PERIODS)[number];

interface TvPeriodSelectorProps {
  activePeriod: string;
  onPeriodChange: (period: string) => void;
  periods?: string[];
  className?: string;
}

export const TvPeriodSelector: FC<TvPeriodSelectorProps> = memo(({
  activePeriod,
  onPeriodChange,
  periods,
  className,
}) => {
  const items = periods || [...PERIODS];
  return (
    <div className={cn('flex items-center gap-0.5', className)}>
      {items.map((p) => (
        <button
          key={p}
          onClick={() => onPeriodChange(p)}
          className={cn(
            'px-2 py-0.5 text-[11px] font-mono font-medium rounded transition-colors',
            activePeriod === p
              ? 'bg-gray-700 text-gray-100'
              : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
          )}
        >
          {p}
        </button>
      ))}
    </div>
  );
});

TvPeriodSelector.displayName = 'TvPeriodSelector';
