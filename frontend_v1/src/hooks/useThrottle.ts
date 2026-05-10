import { useRef, useEffect, useCallback } from 'react';

/**
 * Hook to throttle function calls
 * Ensures function is called at most once per delay period
 */
export function useThrottle<T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): T {
  const lastRan = useRef<number>(Date.now());
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return useCallback(
    ((...args: Parameters<T>) => {
      const now = Date.now();
      const timeSinceLastRan = now - lastRan.current;

      if (timeSinceLastRan >= delay) {
        // Enough time has passed, execute immediately
        callback(...args);
        lastRan.current = now;
      } else {
        // Schedule execution for later
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }

        timeoutRef.current = window.setTimeout(
          () => {
            callback(...args);
            lastRan.current = Date.now();
            timeoutRef.current = null;
          },
          delay - timeSinceLastRan
        );
      }
    }) as T,
    [callback, delay]
  );
}

/**
 * Hook to throttle state updates
 * Returns throttled value that updates at most once per delay period
 */
export function useThrottledValue<T>(value: T, delay: number): T {
  const [throttledValue, setThrottledValue] = React.useState<T>(value);
  const lastUpdated = useRef<number>(Date.now());
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const now = Date.now();
    const timeSinceLastUpdate = now - lastUpdated.current;

    if (timeSinceLastUpdate >= delay) {
      // Update immediately
      setThrottledValue(value);
      lastUpdated.current = now;
    } else {
      // Schedule update
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      timeoutRef.current = window.setTimeout(
        () => {
          setThrottledValue(value);
          lastUpdated.current = Date.now();
          timeoutRef.current = null;
        },
        delay - timeSinceLastUpdate
      );
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [value, delay]);

  return throttledValue;
}

// Need to import React for useState
import React from 'react';
