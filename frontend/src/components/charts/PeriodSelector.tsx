import { type FC } from 'react';
import { cn } from '../../lib/utils';

const DEFAULT_PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

interface PeriodSelectorProps {
  periods?: string[];
  activePeriod: string;
  onPeriodChange: (period: string) => void;
}

export const PeriodSelector: FC<PeriodSelectorProps> = ({
  periods = DEFAULT_PERIODS,
  activePeriod,
  onPeriodChange,
}) => {
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Time period selector">
      {periods.map((period) => {
        const isActive = period === activePeriod;
        return (
          <button
            key={period}
            type="button"
            onClick={() => onPeriodChange(period)}
            aria-pressed={isActive}
            className={cn(
              'px-2 py-0.5 text-xs font-mono rounded transition-colors',
              isActive
                ? 'bg-accent-blue text-white'
                : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover',
            )}
          >
            {period}
          </button>
        );
      })}
    </div>
  );
};
