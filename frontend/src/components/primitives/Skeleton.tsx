import { cn } from '@/lib/utils'

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'text' | 'block' | 'circle' | 'metric-tile' | 'table-row' | 'chart'
  count?: number
}

export function Skeleton({ variant = 'block', count = 1, className, style, ...props }: SkeletonProps) {
  const base = 'skeleton-shimmer rounded-[3px]'
  const variants = {
    text: 'h-3 w-3/4',
    block: 'h-4 w-full',
    circle: 'rounded-full',
    'metric-tile': 'h-16 w-full',
    'table-row': 'h-7 w-full',
    chart: 'h-full w-full min-h-[240px]',
  } as const

  if (count === 1) {
    return <div className={cn(base, variants[variant], className)} style={style} {...props} />
  }
  return (
    <div className={cn('flex flex-col gap-1.5', className)} {...props}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className={cn(base, variants[variant])} style={style} />
      ))}
    </div>
  )
}

export function SkeletonTable({ rows = 8, columns = 6 }: { rows?: number; columns?: number }) {
  return (
    <div className="flex flex-col gap-1">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-2 items-center py-1">
          {Array.from({ length: columns }).map((_, j) => (
            <Skeleton key={j} variant="block" className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonChart({ height = 320 }: { height?: number }) {
  return <Skeleton variant="chart" style={{ height }} />
}
