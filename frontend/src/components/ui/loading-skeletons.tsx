import { type ReactNode, useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Skeleton } from './skeleton';
import { Card, CardContent, CardHeader } from './Card';
import { ErrorState } from './error-state';

// ---------------------------------------------------------------------------
// Fade-in transition variant (200ms as per Req 7.3)
// ---------------------------------------------------------------------------
const fadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: 0.2 },
};

// ---------------------------------------------------------------------------
// MetricCardSkeleton — single metric card placeholder
// ---------------------------------------------------------------------------
export function MetricCardSkeleton() {
  return (
    <Card>
      <CardContent className="pt-6">
        <Skeleton className="h-3 w-20 mb-2" />
        <Skeleton className="h-8 w-24 mb-1" />
        <Skeleton className="h-3 w-16" />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// MetricGridSkeleton — 4-column grid of metric card placeholders (Req 7.1)
// ---------------------------------------------------------------------------
export function MetricGridSkeleton({ columns = 4 }: { columns?: number }) {
  return (
    <div className={`grid grid-cols-2 md:grid-cols-${columns} gap-4`}>
      {Array.from({ length: columns }).map((_, i) => (
        <MetricCardSkeleton key={i} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChartSkeleton — period selector row + chart area rectangle (Req 7.1)
// ---------------------------------------------------------------------------
export function ChartSkeleton({ height = 300 }: { height?: number }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <Skeleton className="h-5 w-32 mb-2" />
            <Skeleton className="h-3 w-48" />
          </div>
          {/* Period selector row */}
          <div className="flex gap-1.5">
            {['1W', '1M', '3M', '6M', '1Y', 'ALL'].map((p) => (
              <Skeleton key={p} className="h-7 w-10 rounded" />
            ))}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <Skeleton className="w-full rounded-lg" style={{ height: `${height}px` }} />
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// TableSkeleton — table header + N rows of cell placeholders (Req 7.1)
// ---------------------------------------------------------------------------
export function TableSkeleton({
  rows = 5,
  columns = 5,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex gap-4 pb-2 border-b border-border">
        {Array.from({ length: columns }).map((_, i) => (
          <Skeleton
            key={i}
            className="h-4"
            style={{ width: i === columns - 1 ? undefined : `${60 + (i % 3) * 20}px`, flex: i === columns - 1 ? 1 : undefined }}
          />
        ))}
      </div>

      {/* Rows */}
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 py-3">
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton
              key={c}
              className="h-4"
              style={{ width: c === columns - 1 ? undefined : `${60 + (c % 3) * 20}px`, flex: c === columns - 1 ? 1 : undefined }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HeatmapSkeleton — grid of small rectangles (monthly returns / correlation)
// ---------------------------------------------------------------------------
export function HeatmapSkeleton({
  rows = 5,
  columns = 12,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-5 w-40 mb-2" />
        <Skeleton className="h-3 w-56" />
      </CardHeader>
      <CardContent>
        {/* Column headers */}
        <div className="flex gap-1 mb-2 pl-12">
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton key={c} className="h-3 w-8 rounded-sm" />
          ))}
        </div>
        {/* Grid rows */}
        <div className="space-y-1">
          {Array.from({ length: rows }).map((_, r) => (
            <div key={r} className="flex gap-1 items-center">
              <Skeleton className="h-3 w-10 shrink-0 rounded-sm" />
              {Array.from({ length: columns }).map((_, c) => (
                <Skeleton key={c} className="h-8 w-8 rounded-sm" />
              ))}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// SummaryBarSkeleton — matches GlobalSummaryBar shape (48px horizontal row)
// ---------------------------------------------------------------------------
export function SummaryBarSkeleton() {
  return (
    <div
      className="flex items-center gap-4 px-8 h-12 min-h-[48px] max-h-[48px] border-b overflow-hidden"
      style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-dark-surface)' }}
    >
      {/* Equity */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-4 w-20" />
      </div>
      <div className="w-px h-4 bg-gray-700 shrink-0" />

      {/* Daily P&L */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Skeleton className="h-3 w-14" />
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-3 w-12" />
      </div>
      <div className="w-px h-4 bg-gray-700 shrink-0" />

      {/* Positions */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-4 w-8" />
      </div>
      <div className="w-px h-4 bg-gray-700 shrink-0" />

      {/* Strategies */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-4 w-8" />
      </div>
      <div className="w-px h-4 bg-gray-700 shrink-0" />

      {/* Regime */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-5 w-20 rounded" />
      </div>
      <div className="w-px h-4 bg-gray-700 shrink-0" />

      {/* Health */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Skeleton className="h-3 w-12" />
        <Skeleton className="h-4 w-8" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PageSkeleton — full page: chart + metric grid + table (Req 7.1)
// ---------------------------------------------------------------------------
export function PageSkeleton() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto space-y-6">
      {/* Header */}
      <div className="mb-6 lg:mb-8">
        <Skeleton className="h-8 w-48 mb-2" />
        <Skeleton className="h-4 w-64" />
      </div>

      {/* Chart */}
      <ChartSkeleton />

      {/* Metrics Row */}
      <MetricGridSkeleton columns={4} />

      {/* Table */}
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-40 mb-2" />
          <Skeleton className="h-4 w-56" />
        </CardHeader>
        <CardContent>
          <TableSkeleton rows={8} />
        </CardContent>
      </Card>
    </div>
  );
}


// ---------------------------------------------------------------------------
// DashboardSkeleton — complex dashboard layout placeholder
// ---------------------------------------------------------------------------
export function DashboardSkeleton() {
  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto space-y-6">
      {/* Header */}
      <div className="mb-6 lg:mb-8 flex items-center justify-between">
        <div>
          <Skeleton className="h-8 w-48 mb-2" />
          <Skeleton className="h-4 w-64" />
        </div>
        <Skeleton className="h-9 w-24" />
      </div>

      {/* Tabs */}
      <div className="space-y-6">
        <Skeleton className="h-10 w-full max-w-md" />

        {/* Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column */}
          <div className="lg:col-span-2 space-y-6">
            <Card>
              <CardHeader>
                <Skeleton className="h-6 w-40 mb-2" />
                <Skeleton className="h-4 w-32" />
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <div key={i}>
                      <Skeleton className="h-3 w-20 mb-1" />
                      <Skeleton className="h-6 w-24" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <MetricCardSkeleton key={i} />
              ))}
            </div>
          </div>

          {/* Right Column */}
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <Skeleton className="h-6 w-32" />
              </CardHeader>
              <CardContent className="space-y-4">
                <Skeleton className="h-20 w-full" />
                <div className="space-y-2">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="flex justify-between">
                      <Skeleton className="h-4 w-24" />
                      <Skeleton className="h-4 w-16" />
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// DataSection — wrapper handling loading → skeleton, loaded → content,
// error → error state with retry, timeout (10s) → error (Req 7.3, 7.5)
// ---------------------------------------------------------------------------

type DataSectionState = 'loading' | 'loaded' | 'error' | 'timeout';

interface DataSectionProps {
  /** Whether data is currently being fetched */
  isLoading: boolean;
  /** Error object or message — triggers error state */
  error?: Error | string | null;
  /** Skeleton placeholder to show while loading */
  skeleton: ReactNode;
  /** Content to render once loaded */
  children: ReactNode;
  /** Retry callback for error / timeout states */
  onRetry?: () => void;
  /** Timeout in ms before showing error state (default 10 000) */
  timeoutMs?: number;
  /** Custom error title */
  errorTitle?: string;
  /** Custom error message */
  errorMessage?: string;
}

export function DataSection({
  isLoading,
  error,
  skeleton,
  children,
  onRetry,
  timeoutMs = 10_000,
  errorTitle,
  errorMessage,
}: DataSectionProps) {
  const [state, setState] = useState<DataSectionState>(
    error ? 'error' : isLoading ? 'loading' : 'loaded',
  );
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clear timeout helper
  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (error) {
      clearTimer();
      setState('error');
      return;
    }

    if (isLoading) {
      setState('loading');
      // Start timeout countdown
      clearTimer();
      timerRef.current = setTimeout(() => {
        setState('timeout');
      }, timeoutMs);
      return;
    }

    // Data loaded
    clearTimer();
    setState('loaded');
  }, [isLoading, error, timeoutMs, clearTimer]);

  // Cleanup on unmount
  useEffect(() => clearTimer, [clearTimer]);

  return (
    <AnimatePresence mode="wait">
      {(state === 'loading') && (
        <motion.div key="skeleton" {...fadeIn}>
          {skeleton}
        </motion.div>
      )}

      {state === 'loaded' && (
        <motion.div key="content" {...fadeIn}>
          {children}
        </motion.div>
      )}

      {(state === 'error' || state === 'timeout') && (
        <motion.div key="error" {...fadeIn}>
          <ErrorState
            title={errorTitle ?? (state === 'timeout' ? 'Request Timed Out' : 'Error Loading Data')}
            message={
              errorMessage ??
              (state === 'timeout'
                ? 'The data request took too long. Please try again.'
                : typeof error === 'string'
                  ? error
                  : error?.message ?? 'Something went wrong while loading the data.')
            }
            onRetry={onRetry}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
