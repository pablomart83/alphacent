import { cn } from '@/lib/utils'

interface MetricGridProps {
  cols?: 2 | 3 | 4 | 6 | 8
  gap?: 1 | 2 | 3
  className?: string
  children: React.ReactNode
}

export function MetricGrid({ cols = 4, gap = 2, className, children }: MetricGridProps) {
  const gridCols =
    cols === 2
      ? 'grid-cols-1 sm:grid-cols-2'
      : cols === 3
        ? 'grid-cols-2 sm:grid-cols-3'
        : cols === 4
          ? 'grid-cols-2 sm:grid-cols-4'
          : cols === 6
            ? 'grid-cols-3 sm:grid-cols-6'
            : 'grid-cols-4 sm:grid-cols-8'
  const gapClass = gap === 1 ? 'gap-1' : gap === 2 ? 'gap-2' : 'gap-3'
  return <div className={cn('grid', gridCols, gapClass, className)}>{children}</div>
}
