import { useCallback, useEffect, useRef, useState } from 'react';
import { wsManager } from '../services/websocket';

/** Default fallback polling interval when WS disconnects (30s) */
const WS_FALLBACK_INTERVAL_MS = 30000;

export interface UsePollingOptions {
  /** Fetch function to call on each interval */
  fetchFn: () => Promise<void>;
  /** Polling interval in milliseconds */
  intervalMs: number;
  /** Whether polling is enabled (default: true) */
  enabled?: boolean;
  /** Whether to fetch immediately on mount (default: true) */
  fetchOnMount?: boolean;
  /**
   * When true, skip REST polling while WebSocket is connected.
   * On WS disconnect, fall back to 30s REST polling.
   * On WS reconnect, trigger a full data refresh.
   */
  skipWhenWsConnected?: boolean;
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
 *
 * When `skipWhenWsConnected` is true:
 * - Polling is suppressed while WebSocket is connected (data arrives via WS events)
 * - On WS disconnect, falls back to 30s REST polling
 * - On WS reconnect, performs a full data refresh then suppresses polling again
 */
export function usePolling(options: UsePollingOptions): UsePollingReturn {
  const {
    fetchFn,
    intervalMs,
    enabled = true,
    fetchOnMount = true,
    skipWhenWsConnected = false,
  } = options;

  const [isRefreshing, setIsRefreshing] = useState(false);
  const isFetchingRef = useRef(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const fetchFnRef = useRef(fetchFn);
  const wasConnectedRef = useRef<boolean | null>(null);
  const skipWhenWsConnectedRef = useRef(skipWhenWsConnected);

  // Keep refs current to avoid stale closures
  fetchFnRef.current = fetchFn;
  skipWhenWsConnectedRef.current = skipWhenWsConnected;

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

  const startInterval = useCallback((overrideMs?: number) => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(doFetch, overrideMs ?? intervalMs);
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

    // If skipWhenWsConnected and WS is currently connected, don't start polling
    if (skipWhenWsConnected && wsManager.isConnected()) {
      // No interval — data comes via WS events
      return () => stopInterval();
    }

    // Start polling (use fallback interval if skipWhenWsConnected and WS is disconnected)
    const effectiveInterval = skipWhenWsConnected ? WS_FALLBACK_INTERVAL_MS : intervalMs;
    startInterval(effectiveInterval);

    return () => stopInterval();
  }, [enabled, fetchOnMount, doFetch, startInterval, stopInterval, intervalMs, skipWhenWsConnected]);

  // Visibility-aware pausing
  useEffect(() => {
    if (!enabled) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopInterval();
      } else {
        doFetch();
        // Respect skipWhenWsConnected when resuming
        if (skipWhenWsConnectedRef.current && wsManager.isConnected()) {
          // WS is connected — don't restart polling
          return;
        }
        const effectiveInterval = skipWhenWsConnectedRef.current ? WS_FALLBACK_INTERVAL_MS : intervalMs;
        startInterval(effectiveInterval);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [enabled, doFetch, startInterval, stopInterval, intervalMs]);

  // WebSocket connection state change handler
  useEffect(() => {
    if (!enabled) return;

    const unsubscribe = wsManager.onConnectionStateChange((connected: boolean) => {
      const wasConnected = wasConnectedRef.current;
      wasConnectedRef.current = connected;

      if (skipWhenWsConnectedRef.current) {
        if (wasConnected === false && connected) {
          // Reconnected: full data refresh, then stop polling (WS takes over)
          doFetch();
          stopInterval();
        } else if (wasConnected !== null && !connected) {
          // Disconnected: start fallback 30s polling
          doFetch();
          startInterval(WS_FALLBACK_INTERVAL_MS);
        }
      } else {
        // Original behavior: fetch on reconnection only
        if (wasConnected === false && connected) {
          doFetch();
        }
      }
    });

    return unsubscribe;
  }, [enabled, doFetch, startInterval, stopInterval]);

  const refresh = useCallback(async () => {
    await doFetch();
  }, [doFetch]);

  return { refresh, isRefreshing };
}
