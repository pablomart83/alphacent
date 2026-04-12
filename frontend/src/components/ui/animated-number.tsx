import { useEffect, useRef, useState, useCallback, memo } from 'react';

interface AnimatedNumberProps {
  /** The numeric value to animate to */
  value: number;
  /** Format: 'number', 'currency', 'percentage', or 'integer' */
  format?: 'number' | 'currency' | 'percentage' | 'integer';
  /** Decimal places (ignored for 'integer') */
  decimals?: number;
  /** Animation duration in ms */
  duration?: number;
  /** CSS class */
  className?: string;
  /** Show sign (+/-) for non-zero values */
  showSign?: boolean;
}

function formatValue(
  num: number,
  format: string,
  decimals: number,
  showSign: boolean,
): string {
  const sign = showSign && num > 0 ? '+' : '';

  switch (format) {
    case 'currency':
      return (
        sign +
        new Intl.NumberFormat('en-US', {
          style: 'currency',
          currency: 'USD',
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }).format(num)
      );

    case 'percentage':
      return `${num >= 0 && showSign ? '+' : ''}${num.toFixed(decimals)}%`;

    case 'integer':
      return sign + Math.round(num).toLocaleString();

    default:
      return (
        sign +
        new Intl.NumberFormat('en-US', {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }).format(num)
      );
  }
}

export const AnimatedNumber = memo(function AnimatedNumber({
  value,
  format = 'number',
  decimals = 2,
  duration = 300,
  className = '',
  showSign = false,
}: AnimatedNumberProps) {
  const [display, setDisplay] = useState(() => formatValue(value, format, decimals, showSign));
  const prevRef = useRef(value);
  const rafRef = useRef<number>(0);

  const animate = useCallback(
    (from: number, to: number) => {
      const start = performance.now();
      const step = (now: number) => {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        // ease-out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = from + (to - from) * eased;
        setDisplay(formatValue(current, format, decimals, showSign));
        if (progress < 1) {
          rafRef.current = requestAnimationFrame(step);
        }
      };
      cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(step);
    },
    [duration, format, decimals, showSign],
  );

  useEffect(() => {
    const prev = prevRef.current;
    if (prev !== value) {
      animate(prev, value);
      prevRef.current = value;
    } else {
      // Initial render or format change — just set directly
      setDisplay(formatValue(value, format, decimals, showSign));
    }
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, animate, format, decimals, showSign]);

  return <span className={className}>{display}</span>;
});

/** Convenience wrapper for integer values */
export function AnimatedInteger({
  value,
  className = '',
  duration = 300,
}: {
  value: number;
  className?: string;
  duration?: number;
}) {
  return (
    <AnimatedNumber
      value={value}
      format="integer"
      className={className}
      duration={duration}
    />
  );
}
