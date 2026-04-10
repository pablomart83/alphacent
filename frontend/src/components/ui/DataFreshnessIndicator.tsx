import { type FC, useEffect, useState } from 'react';
import { formatTimestamp } from '../../lib/utils';
import { cn } from '../../lib/utils';

interface DataFreshnessIndicatorProps {
  lastFetchedAt: Date | null;
}

const TWO_MINUTES = 2 * 60 * 1000;
const FIVE_MINUTES = 5 * 60 * 1000;
const RE_EVAL_INTERVAL = 10_000; // 10 seconds

function getStalenessLevel(ageMs: number): 'fresh' | 'warning' | 'stale' {
  if (ageMs < TWO_MINUTES) return 'fresh';
  if (ageMs < FIVE_MINUTES) return 'warning';
  return 'stale';
}

const levelStyles = {
  fresh: 'text-accent-green',
  warning: 'text-yellow-400',
  stale: 'text-accent-red',
} as const;

/**
 * Shows "Data as of: [timestamp]" with color-coded staleness.
 * Green (<2min), amber (2–5min), red (>5min + "Stale data").
 * Re-evaluates every 10 seconds.
 */
export const DataFreshnessIndicator: FC<DataFreshnessIndicatorProps> = ({ lastFetchedAt }) => {
  const [, setTick] = useState(0);

  // Force re-render every 10s to re-evaluate staleness
  useEffect(() => {
    const timer = setInterval(() => setTick((t) => t + 1), RE_EVAL_INTERVAL);
    return () => clearInterval(timer);
  }, []);

  if (!lastFetchedAt) return null;

  const ageMs = Date.now() - lastFetchedAt.getTime();
  const level = getStalenessLevel(ageMs);

  return (
    <span className={cn('text-xs font-mono', levelStyles[level])}>
      {level === 'stale' && 'Stale data · '}
      Data as of: {formatTimestamp(lastFetchedAt)}
    </span>
  );
};
