import { createContext, useContext, useState, useEffect, type ReactNode, type FC } from 'react';
import { apiClient } from '../services/api';
import { TradingMode } from '../types';

interface TradingModeContextType {
  tradingMode: TradingMode;
  setTradingMode: (mode: TradingMode) => void;
  isLoading: boolean;
}

const TradingModeContext = createContext<TradingModeContextType | undefined>(undefined);

const TRADING_MODE_KEY = 'alphacent_trading_mode';

function getCachedMode(): TradingMode {
  const cached = localStorage.getItem(TRADING_MODE_KEY);
  if (cached === 'LIVE' || cached === 'DEMO') return cached as TradingMode;
  return 'DEMO' as TradingMode;
}

interface TradingModeProviderProps {
  children: ReactNode;
}

export const TradingModeProvider: FC<TradingModeProviderProps> = ({ children }) => {
  // Use cached value immediately — no loading state blocks the UI
  const [tradingMode, setTradingModeState] = useState<TradingMode>(getCachedMode());
  const isLoading = false;

  // Sync with backend in background (non-blocking)
  useEffect(() => {
    const syncWithBackend = async () => {
      try {
        const config = await apiClient.getAppConfig();
        const mode = config.trading_mode || 'DEMO';
        setTradingModeState(mode as TradingMode);
        localStorage.setItem(TRADING_MODE_KEY, mode);
      } catch {
        // Backend not available — use cached/default value silently
      }
    };

    syncWithBackend();
  }, []);

  const setTradingMode = (mode: TradingMode) => {
    setTradingModeState(mode);
    localStorage.setItem(TRADING_MODE_KEY, mode);
  };

  return (
    <TradingModeContext.Provider value={{ tradingMode, setTradingMode, isLoading }}>
      {children}
    </TradingModeContext.Provider>
  );
};

export const useTradingMode = (): TradingModeContextType => {
  const context = useContext(TradingModeContext);
  if (context === undefined) {
    throw new Error('useTradingMode must be used within a TradingModeProvider');
  }
  return context;
};
