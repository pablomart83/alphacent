import { type FC } from 'react';
import { cn } from '../../lib/utils';

/**
 * Base Skeleton primitive — a shimmering placeholder block.
 *
 * Uses a CSS shimmer animation (gradient sweep) layered on top of the
 * standard pulse for a polished loading indicator.
 */
function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-md bg-muted animate-pulse',
        // shimmer sweep overlay
        'before:absolute before:inset-0 before:-translate-x-full',
        'before:bg-gradient-to-r before:from-transparent before:via-white/5 before:to-transparent',
        'before:animate-[shimmer_2s_ease-in-out_infinite]',
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };

// Re-export higher-level skeleton components for convenience
export {
  MetricCardSkeleton,
  MetricGridSkeleton,
  TableSkeleton,
  ChartSkeleton,
  HeatmapSkeleton,
  SummaryBarSkeleton,
  PageSkeleton,
  DashboardSkeleton,
  DataSection,
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
