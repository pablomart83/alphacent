import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';

interface StrategyAlert {
  type: 'activation' | 'retirement' | 'pending_closure' | 'other';
  name: string;
  timestamp: string;
}

const TYPE_ICONS: Record<string, string> = {
  activation: '🟢',
  retirement: '🔴',
  pending_closure: '🟡',
  other: '⚪',
};

export const StrategyAlertsWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [alerts, setAlerts] = useState<StrategyAlert[]>([]);

  const fetchAlerts = useCallback(async () => {
    if (!tradingMode) return;
    try {
      // Try dedicated endpoint first
      try {
        const data = await apiClient.getStrategyAlerts(tradingMode);
        if (data?.alerts) {
          setAlerts(data.alerts.slice(0, 8).map((a: any) => ({
            type: a.event_type || a.type || 'other',
            name: a.strategy_name || a.symbol || a.name || '?',
            timestamp: a.timestamp || a.created_at || '',
          })));
          return;
        }
      } catch { /* endpoint not available */ }

      // Fallback: get pending closures as alerts
      const pending = await apiClient.getPendingClosures(tradingMode);
      setAlerts(
        pending.slice(0, 5).map(p => ({
          type: 'pending_closure' as const,
          name: p.symbol || '?',
          timestamp: '',
        }))
      );
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchAlerts, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const unsub1 = wsManager.onStrategyUpdate(() => fetchAlerts());
    const unsub2 = wsManager.on('pending_closure', () => fetchAlerts());
    return () => { unsub1(); unsub2(); };
  }, [tradingMode, fetchAlerts]);

  if (alerts.length === 0) {
    return <div className="text-xs text-gray-600 font-mono">No recent alerts</div>;
  }

  return (
    <div className="space-y-1 text-xs font-mono">
      {alerts.map((alert, idx) => (
        <div key={idx} className="flex items-center gap-1.5">
          <span className="shrink-0">{TYPE_ICONS[alert.type] || '⚪'}</span>
          <span className="text-gray-300 truncate flex-1">{alert.name}</span>
          <span className="text-gray-600 shrink-0 capitalize">{alert.type.replace('_', ' ')}</span>
        </div>
      ))}
    </div>
  );
};
