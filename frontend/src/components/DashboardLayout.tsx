import { type FC, type ReactNode, useEffect, useState, useCallback, useRef } from 'react';
import { TopNavBar } from './TopNavBar';
import { MetricsBar } from './MetricsBar';
import { PositionTickerStrip } from './PositionTickerStrip';
import { KeyboardShortcutsHelp } from './KeyboardShortcutsHelp';
import { useTradingMode } from '../contexts/TradingModeContext';
import { useLastSynced } from '../hooks/useLastSynced';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { toast } from 'sonner';

interface DashboardLayoutProps {
  children: ReactNode;
  onLogout: () => void;
}

export const DashboardLayout: FC<DashboardLayoutProps> = ({ children, onLogout }) => {
  const { tradingMode } = useTradingMode();
  const [pendingClosuresCount, setPendingClosuresCount] = useState(0);
  const [queuedOrdersCount, setQueuedOrdersCount] = useState(0);
  const [globalSyncing, setGlobalSyncing] = useState(false);
  const { touch: touchSync } = useLastSynced();

  // Keyboard shortcuts (R = sync, ? = help overlay, 1-8 = navigate)
  const { showHelp, setShowHelp } = useKeyboardShortcuts({
    onRefresh: () => handleGlobalSync(),
  });

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

  usePolling({ fetchFn: fetchBadgeCounts, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

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

  usePolling({ fetchFn: fetchRegime, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

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
    <div className="flex flex-col h-screen overflow-hidden bg-dark-bg">
      <TopNavBar
        onLogout={onLogout}
        onSync={handleGlobalSync}
        syncing={globalSyncing}
        pendingClosuresCount={pendingClosuresCount}
        queuedOrdersCount={queuedOrdersCount}
      />
      <MetricsBar />
      <PositionTickerStrip />

      <main className="flex-1 overflow-auto">
        {children}
      </main>

      {/* Keyboard shortcuts help overlay */}
      <KeyboardShortcutsHelp open={showHelp} onClose={() => setShowHelp(false)} />
    </div>
  );
};
