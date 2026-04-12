import { type FC, useEffect, useState } from 'react';
import { cn } from '../../lib/utils';

interface DataFreshnessIndicatorProps {
  lastFetchedAt: Date | null;
}

const TWO_MINUTES = 2 * 60 * 1000;
const FIVE_MINUTES = 5 * 60 * 1000;
const RE_EVAL_INTERVAL = 10_000;

function getStalenessLevel(ageMs: number): 'fresh' | 'warning' | 'stale' {
  if (ageMs < TWO_MINUTES) return 'fresh';
  if (ageMs < FIVE_MINUTES) return 'warning';
  return 'stale';
}

function getRelativeAge(ageMs: number): string {
  const secs = Math.floor(ageMs / 1000);
  if (secs < 10) return 'now';
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h`;
}

const dotColor = {
  fresh: 'bg-green-400',
  warning: 'bg-yellow-400',
  stale: 'bg-red-400',
} as const;

/**
 * Compact freshness dot with relative age tooltip.
 * Shows a colored dot (green/amber/red) + relative time like "2m ago".
 */
export const DataFreshnessIndicator: FC<DataFreshnessIndicatorProps> = ({ lastFetchedAt }) => {
  const [, setTick] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), RE_EVAL_INTERVAL);
    return () => clearInterval(timer);
  }, []);

  if (!lastFetchedAt) return null;

  const ageMs = Date.now() - lastFetchedAt.getTime();
  const level = getStalenessLevel(ageMs);
  const age = getRelativeAge(ageMs);

  return (
    <span className="inline-flex items-center gap-1" title={`Last updated: ${lastFetchedAt.toLocaleTimeString()}`}>
      <span className={cn('w-1.5 h-1.5 rounded-full shrink-0', dotColor[level])} />
      <span className="text-[10px] font-mono text-gray-500">{age}</span>
    </span>
  );
};
