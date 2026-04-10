import { type FC } from 'react';
import { cn } from '../../lib/utils';

/**
 * Base Skeleton primitive — a shimmering placeholder block.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-muted', className)}
      {...props}
    />
  );
}

export { Skeleton };

// Re-export higher-level skeleton components for convenience
export {
  MetricCardSkeleton,
  TableSkeleton,
  ChartSkeleton,
  PageSkeleton,
  DashboardSkeleton,
} from './loading-skeletons';

/**
 * Subtle refresh indicator shown during background polling refreshes.
 * Renders a thin animated bar at the top of its container.
 */
export const RefreshIndicator: FC<{ visible: boolean }> = ({ visible }) => {
  if (!visible) return null;
  return (
    <div
      className="absolute top-0 left-0 right-0 h-0.5 bg-primary/30 overflow-hidden z-10"
      role="status"
      aria-label="Refreshing data"
    >
      <div className="h-full w-1/3 bg-primary animate-[shimmer_1.5s_ease-in-out_infinite]" />
    </div>
  );
};
