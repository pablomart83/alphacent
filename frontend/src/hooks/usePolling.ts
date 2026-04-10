import { useCallback, useEffect, useRef, useState } from 'react';
import { wsManager } from '../services/websocket';

export interface UsePollingOptions {
  /** Fetch function to call on each interval */
  fetchFn: () => Promise<void>;
  /** Polling interval in milliseconds */
  intervalMs: number;
  /** Whether polling is enabled (default: true) */
  enabled?: boolean;
  /** Whether to fetch immediately on mount (default: true) */
  fetchOnMount?: boolean;
}

export interface UsePollingReturn {
  /** Manually trigger an immediate fetch */
  refresh: () => Promise<void>;
  /** Whether a fetch is currently in progress */
  isRefreshing: boolean;
}

/**
 * Reusable polling hook with visibility-aware pausing and WebSocket reconnection triggers.
 * Pauses when the browser tab is hidden, resumes with an immediate fetch when visible.
 * Also fetches immediately on WebSocket reconnection.
 */
export function usePolling(options: UsePollingOptions): UsePollingReturn {
  const { fetchFn, intervalMs, enabled = true, fetchOnMount = true } = options;

  const [isRefreshing, setIsRefreshing] = useState(false);
  const isFetchingRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fetchFnRef = useRef(fetchFn);
  const wasConnectedRef = useRef<boolean | null>(null);

  // Keep fetchFn ref current to avoid stale closures
  fetchFnRef.current = fetchFn;

  const doFetch = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    setIsRefreshing(true);
    try {
      await fetchFnRef.current();
    } catch (err) {
      // Errors are handled by the caller's fetchFn; we just guard concurrency
      console.error('[usePolling] fetch error:', err);
    } finally {
      isFetchingRef.current = false;
      setIsRefreshing(false);
    }
  }, []);

  const startInterval = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(doFetch, intervalMs);
  }, [doFetch, intervalMs]);

  const stopInterval = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // Core polling lifecycle
  useEffect(() => {
    if (!enabled) {
      stopInterval();
      return;
    }

    if (fetchOnMount) {
      doFetch();
    }
    startInterval();

    return () => stopInterval();
  }, [enabled, fetchOnMount, doFetch, startInterval, stopInterval]);

  // Visibility-aware pausing
  useEffect(() => {
    if (!enabled) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopInterval();
      } else {
        doFetch();
        startInterval();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, doFetch, startInterval, stopInterval]);

  // WebSocket reconnection trigger
  useEffect(() => {
    if (!enabled) return;

    const unsubscribe = wsManager.onConnectionStateChange((connected: boolean) => {
      const wasConnected = wasConnectedRef.current;
      wasConnectedRef.current = connected;

      // Fetch immediately on reconnection (false → true), skip initial notification
      if (wasConnected === false && connected) {
        doFetch();
      }
    });

    return unsubscribe;
  }, [enabled, doFetch]);

  const refresh = useCallback(async () => {
    await doFetch();
  }, [doFetch]);

  return { refresh, isRefreshing };
}
