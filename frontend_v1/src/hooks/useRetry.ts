import { useState, useCallback } from 'react';

interface RetryOptions {
  maxAttempts?: number;
  initialDelay?: number;
  maxDelay?: number;
  backoffMultiplier?: number;
}

interface RetryState {
  isRetrying: boolean;
  attemptCount: number;
  lastError: Error | null;
}

export const useRetry = (options: RetryOptions = {}) => {
  const {
    maxAttempts = 3,
    initialDelay = 1000,
    maxDelay = 10000,
    backoffMultiplier = 2,
  } = options;

  const [state, setState] = useState<RetryState>({
    isRetrying: false,
    attemptCount: 0,
    lastError: null,
  });

  const calculateDelay = useCallback(
    (attempt: number): number => {
      const delay = initialDelay * Math.pow(backoffMultiplier, attempt);
      return Math.min(delay, maxDelay);
    },
    [initialDelay, backoffMultiplier, maxDelay]
  );

  const retry = useCallback(
    async <T>(fn: () => Promise<T>): Promise<T> => {
      setState((prev) => ({
        ...prev,
        isRetrying: true,
        attemptCount: 0,
        lastError: null,
      }));

      let lastError: Error | null = null;

      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
          const result = await fn();
          setState({
            isRetrying: false,
            attemptCount: attempt + 1,
            lastError: null,
          });
          return result;
        } catch (error) {
          lastError = error instanceof Error ? error : new Error('Unknown error');
          
          setState((prev) => ({
            ...prev,
            attemptCount: attempt + 1,
            lastError,
          }));

          // Don't wait after the last attempt
          if (attempt < maxAttempts - 1) {
            const delay = calculateDelay(attempt);
            console.log(`Retry attempt ${attempt + 1}/${maxAttempts} failed. Retrying in ${delay}ms...`);
            await new Promise((resolve) => setTimeout(resolve, delay));
          }
        }
      }

      setState((prev) => ({
        ...prev,
        isRetrying: false,
      }));

      throw lastError || new Error('All retry attempts failed');
    },
    [maxAttempts, calculateDelay]
  );

  const reset = useCallback(() => {
    setState({
      isRetrying: false,
      attemptCount: 0,
      lastError: null,
    });
  }, []);

  return {
    retry,
    reset,
    ...state,
  };
};

// Utility function for automatic retry with exponential backoff
export const retryWithBackoff = async <T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> => {
  const {
    maxAttempts = 3,
    initialDelay = 1000,
    maxDelay = 10000,
    backoffMultiplier = 2,
  } = options;

  let lastError: Error | null = null;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Unknown error');

      if (attempt < maxAttempts - 1) {
        const delay = Math.min(
          initialDelay * Math.pow(backoffMultiplier, attempt),
          maxDelay
        );
        console.log(`Retry attempt ${attempt + 1}/${maxAttempts} failed. Retrying in ${delay}ms...`);
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError || new Error('All retry attempts failed');
};
