import { useEffect, useRef, memo, type ReactNode } from 'react';
import { cn } from '../../lib/utils';

interface FlashWrapperProps {
  /** The value to watch for changes */
  value: number | string;
  /** Previous value — used to determine flash color. If omitted, any change flashes blue. */
  previousValue?: number | string;
  children: ReactNode;
  className?: string;
  /** Flash duration in ms */
  duration?: number;
}

/**
 * Wraps children and flashes green (positive change) or red (negative change)
 * at 20% opacity, fading over `duration` ms when `value` changes.
 */
export const FlashWrapper = memo(function FlashWrapper({
  value,
  previousValue,
  children,
  className = '',
  duration = 500,
}: FlashWrapperProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const prevValueRef = useRef(value);
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      prevValueRef.current = value;
      return;
    }

    const prev = previousValue !== undefined ? previousValue : prevValueRef.current;
    if (value === prev) return;

    const el = ref.current;
    if (!el) return;

    // Determine direction
    const numCurrent = typeof value === 'number' ? value : parseFloat(String(value)) || 0;
    const numPrev = typeof prev === 'number' ? prev : parseFloat(String(prev)) || 0;
    const isPositive = numCurrent >= numPrev;

    // Remove any existing animation
    el.classList.remove('flash-green', 'flash-red');
    // Force reflow to restart animation
    void el.offsetWidth;
    el.classList.add(isPositive ? 'flash-green' : 'flash-red');

    const timer = setTimeout(() => {
      el.classList.remove('flash-green', 'flash-red');
    }, duration);

    prevValueRef.current = value;
    return () => clearTimeout(timer);
  }, [value, previousValue, duration]);

  return (
    <span
      ref={ref}
      className={cn('inline-flex transition-colors', className)}
      style={{ '--flash-duration': `${duration}ms` } as React.CSSProperties}
    >
      {children}
    </span>
  );
});
