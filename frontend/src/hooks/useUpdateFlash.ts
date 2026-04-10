import { useState, useEffect, useRef } from 'react';

/**
 * Hook to create a flash/pulse effect when data updates
 * Returns a boolean that's true briefly when data changes
 */
export function useUpdateFlash<T>(data: T, duration: number = 500): boolean {
  const [isFlashing, setIsFlashing] = useState(false);
  const previousDataRef = useRef<T>(data);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    // Check if data actually changed (deep comparison for objects)
    const dataChanged = JSON.stringify(data) !== JSON.stringify(previousDataRef.current);
    
    if (dataChanged) {
      // Clear any existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      // Trigger flash
      setIsFlashing(true);

      // Clear flash after duration
      timeoutRef.current = window.setTimeout(() => {
        setIsFlashing(false);
        timeoutRef.current = null;
      }, duration);

      // Update previous data
      previousDataRef.current = data;
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [data, duration]);

  return isFlashing;
}

/**
 * Hook to get CSS classes for flash animation
 */
export function useFlashClasses<T>(
  data: T,
  duration: number = 500,
  flashClass: string = 'bg-accent-green/20'
): string {
  const isFlashing = useUpdateFlash(data, duration);
  return isFlashing ? `${flashClass} transition-colors` : 'transition-colors';
}
