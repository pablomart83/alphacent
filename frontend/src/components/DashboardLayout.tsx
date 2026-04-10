import { type FC, type ReactNode, useEffect, useState, useCallback, useRef } from 'react';
import { Sidebar } from './Sidebar';
import { Notifications } from './Notifications';
import { KeyboardShortcutsHelp } from './KeyboardShortcutsHelp';
import { RefreshButton } from './ui/RefreshButton';
import { useTradingMode } from '../contexts/TradingModeContext';
import { useTheme } from '../contexts/ThemeContext';
import { useLastSynced } from '../hooks/useLastSynced';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { useWebSocketConnection } from '../hooks/useWebSocket';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { toast } from 'sonner';

interface DashboardLayoutProps {
  children: ReactNode;
  onLogout: () => void;
}

export const DashboardLayout: FC<DashboardLayoutProps> = ({ children, onLogout }) => {
  const { tradingMode } = useTradingMode();
  const { theme, toggleTheme } = useTheme();
  const [pendingClosuresCount, setPendingClosuresCount] = useState(0);
  const [queuedOrdersCount, setQueuedOrdersCount] = useState(0);
  const [globalSyncing, setGlobalSyncing] = useState(false);
  const [dailyPnl, setDailyPnl] = useState<number>(0);
  const [dailyPnlPct, setDailyPnlPct] = useState<number>(0);
  const { label: lastSyncedLabel, touch: touchSync } = useLastSynced();
  const wsConnected = useWebSocketConnection();

  // Keyboard shortcuts (R = sync, ? = help overlay, 1-8 = navigate)
  const { showHelp, setShowHelp } = useKeyboardShortcuts({
    onRefresh: () => handleGlobalSync(),
  });

  // --- P&L ticker: fetch daily P&L from account info ---
  const fetchPnl = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const account = await apiClient.getAccountInfo(tradingMode);
      setDailyPnl(account.daily_pnl ?? 0);
      // Calculate percentage from daily_pnl / equity (or balance as fallback)
      const base = account.equity || account.balance || 1;
      setDailyPnlPct(base !== 0 ? (account.daily_pnl / base) * 100 : 0);
    } catch {
      // Non-critical — keep last known values
    }
  }, [tradingMode]);

  // Poll P&L every 30s
  usePolling({ fetchFn: fetchPnl, intervalMs: 30000, enabled: !!tradingMode });

  // Update P&L on WS position events
  useEffect(() => {
    if (!tradingMode) return;
    const unsub = wsManager.onPositionUpdate(() => { fetchPnl(); });
    return unsub;
  }, [tradingMode, fetchPnl]);

  // --- Badge counts: use usePolling (30s) ---
  const fetchBadgeCounts = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const [positions, orders] = await Promise.all([
        apiClient.getPendingClosures(tradingMode),
        apiClient.getOrders(tradingMode),
      ]);
      setPendingClosuresCount(positions.length);
      setQueuedOrdersCount(orders.filter(o => o.status === 'PENDING' || o.status === 'SUBMITTED').length);
    } catch {
      // Silently fail — badges are non-critical
    }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchBadgeCounts, intervalMs: 30000, enabled: !!tradingMode });

  // WS events for immediate badge updates
  useEffect(() => {
    if (!tradingMode) return;
    const unsubPosition = wsManager.onPositionUpdate(() => fetchBadgeCounts());
    const unsubPending = wsManager.on('pending_closure', () => fetchBadgeCounts());
    const unsubOrder = wsManager.onOrderUpdate(() => fetchBadgeCounts());
    return () => { unsubPosition(); unsubPending(); unsubOrder(); };
  }, [tradingMode, fetchBadgeCounts]);

  // --- Regime change detection ---
  const lastRegimeRef = useRef<string | null>(null);

  const fetchRegime = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const data = await apiClient.getDashboardSummary(tradingMode);
      const currentRegime = data?.market_regime?.current_regime;
      if (!currentRegime) return;

      const storedRegime = localStorage.getItem('alphacent_last_regime');
      // Initialize ref from localStorage on first run
      if (lastRegimeRef.current === null) {
        lastRegimeRef.current = storedRegime;
      }

      const previousRegime = lastRegimeRef.current;

      if (previousRegime && previousRegime !== currentRegime) {
        toast.info(`Market regime changed: ${previousRegime} → ${currentRegime}`, {
          duration: 8000,
          action: {
            label: 'View Dashboard',
            onClick: () => { window.location.href = '/'; },
          },
        });
      }

      lastRegimeRef.current = currentRegime;
      localStorage.setItem('alphacent_last_regime', currentRegime);
    } catch {
      // Non-critical
    }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchRegime, intervalMs: 30000, enabled: !!tradingMode });

  const handleGlobalSync = async () => {
    if (!tradingMode || globalSyncing) return;
    setGlobalSyncing(true);
    try {
      await apiClient.syncPositions(tradingMode);
      touchSync();
      toast.success('eToro sync complete');
    } catch {
      toast.error('eToro sync failed');
    } finally {
      setGlobalSyncing(false);
    }
  };

  return (
    <div className="flex h-screen bg-dark-bg">
      <Sidebar onLogout={onLogout} pendingClosuresCount={pendingClosuresCount} queuedOrdersCount={queuedOrdersCount} />

      <div className="flex-1 flex flex-col overflow-hidden">
        <header
          className="flex items-center justify-between px-8 py-4 border-b"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div
                className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-accent-green' : 'bg-accent-red'}`}
              />
              <span className="text-xs text-gray-500">
                {wsConnected ? 'Live' : 'Disconnected'}
              </span>
            </div>
            <span className="text-xs text-gray-600">·</span>
            <span className="text-xs text-gray-500">
              Last synced: {lastSyncedLabel}
            </span>
            <span className="text-xs text-gray-600">·</span>
            {/* Daily P&L Ticker */}
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-gray-500">Daily P&L</span>
              <span className={cn('text-sm font-mono font-semibold', dailyPnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                {dailyPnl >= 0 ? '+' : ''}{formatCurrency(dailyPnl)}
              </span>
              <span className={cn('text-xs font-mono', dailyPnlPct >= 0 ? 'text-accent-green/80' : 'text-accent-red/80')}>
                ({dailyPnlPct >= 0 ? '+' : ''}{formatPercentage(dailyPnlPct)})
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleTheme}
              className="p-2 rounded-md transition-colors"
              style={{
                color: 'var(--color-text-secondary)',
                backgroundColor: 'transparent',
                border: '1px solid var(--color-dark-border)',
              }}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              {theme === 'dark' ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="5" />
                  <line x1="12" y1="1" x2="12" y2="3" />
                  <line x1="12" y1="21" x2="12" y2="23" />
                  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                  <line x1="1" y1="12" x2="3" y2="12" />
                  <line x1="21" y1="12" x2="23" y2="12" />
                  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
                </svg>
              )}
            </button>
            <RefreshButton
              loading={globalSyncing}
              label="Sync eToro"
              onClick={handleGlobalSync}
              variant="outline"
              size="sm"
              title="Sync eToro (R)"
            />
            <Notifications />
          </div>
        </header>

        <main className="flex-1 overflow-auto">
          {children}
        </main>
      </div>

      {/* Keyboard shortcuts help overlay */}
      <KeyboardShortcutsHelp open={showHelp} onClose={() => setShowHelp(false)} />
    </div>
  );
};
