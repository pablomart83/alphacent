import { type FC } from 'react';
import { cn } from '../../lib/utils';

export interface MetricGridItem {
  label: string;
  value: string | number;
  /** Tailwind text color class, e.g. 'text-[#22c55e]' */
  color?: string;
  /** Optional sub-value (e.g. percentage below dollar amount) */
  sub?: string;
}

interface MetricGridProps {
  items: MetricGridItem[];
  /** Number of columns (default: items.length, max 8) */
  cols?: number;
  className?: string;
}

/**
 * Dense inline metric grid — replaces MetricCard grids and bg-muted boxes.
 * Each cell is a compact box with label + value, no icons, no padding waste.
 *
 * Usage:
 * ```tsx
 * <MetricGrid items={[
 *   { label: 'VaR 95%', value: '$12,340', color: 'text-[#ef4444]' },
 *   { label: 'Max DD', value: '-4.2%', color: 'text-[#ef4444]' },
 * ]} />
 * ```
 */
export const MetricGrid: FC<MetricGridProps> = ({ items, cols, className }) => {
  const colCount = cols ?? Math.min(items.length, 8);
  return (
    <div
      className={cn('grid gap-2', className)}
      style={{ gridTemplateColumns: `repeat(${colCount}, minmax(0, 1fr))` }}
    >
      {items.map((item, i) => (
        <div
          key={i}
          className="rounded-md p-2 bg-[var(--color-dark-bg)] border border-[var(--color-dark-border)]"
        >
          <div className="text-xs text-gray-500 tracking-wide">{item.label}</div>
          <div className={cn('text-base font-mono font-bold mt-0.5', item.color || 'text-gray-200')}>
            {item.value}
          </div>
          {item.sub && (
            <div className="text-xs font-mono text-gray-500 mt-0.5">{item.sub}</div>
          )}
        </div>
      ))}
    </div>
  );
};
