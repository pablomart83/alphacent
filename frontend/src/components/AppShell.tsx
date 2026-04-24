/**
 * AppShell — single persistent layout that survives page navigation.
 *
 * Renders once when the user logs in and stays mounted for the entire session.
 * TopNavBar, MetricsBar, PositionTickerStrip, BottomWidgetZone and all their
 * polling loops live here — they never remount on route changes.
 *
 * Pages still use <DashboardLayout> in their JSX, but DashboardLayout now
 * detects it is inside AppShell and becomes a transparent passthrough,
 * so no page files need to change.
 */
import { type FC, type ReactNode, useEffect, useState, useCallback, useRef, createContext, useContext } from 'react';
import { Outlet } from 'react-router-dom';
import { TopNavBar } from './TopNavBar';
import { MetricsBar } from './MetricsBar';
import { PositionTickerStrip } from './PositionTickerStrip';
import { BottomWidgetZone } from './BottomWidgetZone';
import { KeyboardShortcutsHelp } from './KeyboardShortcutsHelp';
import { useTradingMode } from '../contexts/TradingModeContext';
import { useLastSynced } from '../hooks/useLastSynced';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { toast } from 'sonner';

// ── Shell context — lets DashboardLayout know it's inside AppShell ────────────
interface ShellContextType {
  onLogout: () => void;
  onSync: () => void;
  syncing: boolean;
  pendingClosuresCount: number;
  queuedOrdersCount: number;
}

export const ShellContext = createContext<ShellContextType | null>(null);
export const useShell = () => useContext(ShellContext);

interface AppShellProps {
  onLogout: () => void;
  children?: ReactNode;
}

export const AppShell: FC<AppShellProps> = ({ onLogout }) => {
  const { tradingMode } = useTradingMode();
  const [pendingClosuresCount, setPendingClosuresCount] = useState(0);
  const [queuedOrdersCount, setQueuedOrdersCount] = useState(0);
  const [globalSyncing, setGlobalSyncing] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const { touch: touchSync } = useLastSynced();

  // Badge counts
  const fetchBadgeCounts = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const [positions, orders] = await Promise.all([
        apiClient.getPendingClosures(tradingMode),
        apiClient.getOrders(tradingMode),
      ]);
      setPendingClosuresCount(positions.length);
      setQueuedOrdersCount(orders.filter(o => o.status === 'PENDING' || o.status === 'SUBMITTED').length);
    } catch {}
  }, [tradingMode]);

  usePolling({ fetchFn: fetchBadgeCounts, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const u1 = wsManager.onPositionUpdate(() => fetchBadgeCounts());
    const u2 = wsManager.on('pending_closure', () => fetchBadgeCounts());
    const u3 = wsManager.onOrderUpdate(() => fetchBadgeCounts());
    return () => { u1(); u2(); u3(); };
  }, [tradingMode, fetchBadgeCounts]);

  // Regime change detection
  const lastRegimeRef = useRef<string | null>(null);
  const fetchRegime = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const data = await apiClient.getDashboardSummary(tradingMode);
      const currentRegime = data?.market_regime?.current_regime;
      if (!currentRegime) return;
      const storedRegime = localStorage.getItem('alphacent_last_regime');
      if (lastRegimeRef.current === null) lastRegimeRef.current = storedRegime;
      const previousRegime = lastRegimeRef.current;
      if (previousRegime && previousRegime !== currentRegime) {
        toast.info(`Market regime changed: ${previousRegime} → ${currentRegime}`, {
          duration: 8000,
          action: { label: 'View Dashboard', onClick: () => { window.location.href = '/'; } },
        });
      }
      lastRegimeRef.current = currentRegime;
      localStorage.setItem('alphacent_last_regime', currentRegime);
    } catch {}
  }, [tradingMode]);

  usePolling({ fetchFn: fetchRegime, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  const handleGlobalSync = useCallback(async () => {
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
  }, [tradingMode, globalSyncing, touchSync]);

  // Keyboard shortcuts
  useKeyboardShortcuts({ onRefresh: handleGlobalSync });

  const shellValue: ShellContextType = {
    onLogout,
    onSync: handleGlobalSync,
    syncing: globalSyncing,
    pendingClosuresCount,
    queuedOrdersCount,
  };

  return (
    <ShellContext.Provider value={shellValue}>
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

        <main className="flex-1 overflow-auto min-h-0">
          {/* Outlet renders the current page — only this part changes on navigation */}
          <Outlet />
        </main>

        {/* BottomWidgetZone is persistent — never remounts on navigation */}
        <BottomWidgetZone />

        <KeyboardShortcutsHelp open={showHelp} onClose={() => setShowHelp(false)} />
      </div>
    </ShellContext.Provider>
  );
};
