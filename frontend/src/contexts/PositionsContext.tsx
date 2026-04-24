/**
 * PositionsContext — single source of truth for open positions.
 * One polling loop (30s, WS-aware) shared by PositionTickerStrip,
 * BookPulseWidget, RiskPulseWidget, and any page that needs positions.
 * Eliminates 3+ duplicate getPositions() calls on every page load.
 */
import { createContext, useContext, useState, useCallback, type FC, type ReactNode } from 'react';
import { useTradingMode } from './TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { useEffect } from 'react';
import type { Position } from '../types';

interface PositionsContextType {
  positions: Position[];
  isLoading: boolean;
  refresh: () => Promise<void>;
}

const PositionsContext = createContext<PositionsContextType>({
  positions: [],
  isLoading: false,
  refresh: async () => {},
});

export const PositionsProvider: FC<{ children: ReactNode }> = ({ children }) => {
  const { tradingMode } = useTradingMode();
  const [positions, setPositions] = useState<Position[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchPositions = useCallback(async () => {
    if (!tradingMode) return;
    setIsLoading(true);
    try {
      const data = await apiClient.getPositions(tradingMode);
      setPositions(data);
    } catch {
      // keep last known
    } finally {
      setIsLoading(false);
    }
  }, [tradingMode]);

  const { refresh } = usePolling({
    fetchFn: fetchPositions,
    intervalMs: 30000,
    enabled: !!tradingMode,
    skipWhenWsConnected: true,
  });

  // Live updates via WebSocket
  useEffect(() => {
    if (!tradingMode) return;
    return wsManager.onPositionUpdate(() => fetchPositions());
  }, [tradingMode, fetchPositions]);

  return (
    <PositionsContext.Provider value={{ positions, isLoading, refresh }}>
      {children}
    </PositionsContext.Provider>
  );
};

export const usePositions = () => useContext(PositionsContext);
