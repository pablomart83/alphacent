import { useState, useEffect, useCallback } from 'react';
import { useDataCache, CACHE_DURATIONS } from '../stores/dataCache';
import { apiClient } from '../services/api';
import type { AccountInfo, Position, Order } from '../types';

/**
 * Custom hook for fetching account info with caching
 * Uses stale-while-revalidate pattern
 */
export function useCachedAccountInfo(tradingMode: 'DEMO' | 'LIVE') {
  const { getAccountInfo, setAccountInfo, isStale } = useDataCache();
  const [data, setData] = useState<AccountInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async (force = false) => {
    try {
      // Check cache first
      if (!force) {
        const cached = getAccountInfo(CACHE_DURATIONS.ACCOUNT_INFO);
        if (cached) {
          setData(cached);
          setLoading(false);
          
          // Revalidate in background if stale
          if (isStale('accountInfo', CACHE_DURATIONS.ACCOUNT_INFO / 2)) {
            const fresh = await apiClient.getAccountInfo(tradingMode);
            setAccountInfo(fresh);
            setData(fresh);
          }
          return;
        }
      }

      // Fetch fresh data
      setLoading(true);
      const fresh = await apiClient.getAccountInfo(tradingMode);
      setAccountInfo(fresh);
      setData(fresh);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [tradingMode, getAccountInfo, setAccountInfo, isStale]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: () => fetchData(true) };
}

/**
 * Custom hook for fetching positions with caching
 */
export function useCachedPositions(tradingMode: 'DEMO' | 'LIVE') {
  const { getPositions, setPositions, isStale } = useDataCache();
  const [data, setData] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async (force = false) => {
    try {
      // Check cache first
      if (!force) {
        const cached = getPositions(CACHE_DURATIONS.POSITIONS);
        if (cached) {
          setData(cached);
          setLoading(false);
          
          // Revalidate in background if stale
          if (isStale('positions', CACHE_DURATIONS.POSITIONS / 2)) {
            const fresh = await apiClient.getPositions(tradingMode);
            setPositions(fresh);
            setData(fresh);
          }
          return;
        }
      }

      // Fetch fresh data
      setLoading(true);
      const fresh = await apiClient.getPositions(tradingMode);
      setPositions(fresh);
      setData(fresh);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [tradingMode, getPositions, setPositions, isStale]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: () => fetchData(true) };
}

/**
 * Custom hook for fetching orders with caching
 */
export function useCachedOrders(tradingMode: 'DEMO' | 'LIVE') {
  const { getOrders, setOrders, isStale } = useDataCache();
  const [data, setData] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const fetchData = useCallback(async (force = false) => {
    try {
      // Check cache first
      if (!force) {
        const cached = getOrders(CACHE_DURATIONS.ORDERS);
        if (cached) {
          setData(cached);
          setLoading(false);
          
          // Revalidate in background if stale
          if (isStale('orders', CACHE_DURATIONS.ORDERS / 2)) {
            const fresh = await apiClient.getOrders(tradingMode);
            setOrders(fresh);
            setData(fresh);
          }
          return;
        }
      }

      // Fetch fresh data
      setLoading(true);
      const fresh = await apiClient.getOrders(tradingMode);
      setOrders(fresh);
      setData(fresh);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setLoading(false);
    }
  }, [tradingMode, getOrders, setOrders, isStale]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refetch: () => fetchData(true) };
}

/**
 * Hook to invalidate all caches (useful after mutations)
 */
export function useInvalidateCache() {
  const { clearAll } = useDataCache();
  
  return useCallback(() => {
    clearAll();
  }, [clearAll]);
}
