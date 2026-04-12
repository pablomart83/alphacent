import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';
import { cn } from '../../lib/utils';

interface Signal {
  symbol: string;
  direction: string;
  conviction: number;
  timestamp: string;
}

export const RecentSignalsWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [signals, setSignals] = useState<Signal[]>([]);

  const fetchSignals = useCallback(async () => {
    if (!tradingMode) return;
    try {
      // Try dedicated dashboard endpoint first
      try {
        const data = await apiClient.getDashboardRecentSignals(tradingMode, 5);
        if (data?.signals && data.signals.length > 0) {
          setSignals(
            data.signals.slice(0, 5).map((s: any) => ({
              symbol: s.symbol || '?',
              direction: s.direction || s.signal_type || '?',
              conviction: s.conviction_score ?? 0,
              timestamp: s.timestamp || '',
            }))
          );
          return;
        }
      } catch { /* endpoint not available — fall back */ }

      // Fallback: use existing signals endpoint
      const data = await apiClient.getRecentSignals(tradingMode, 5);
      if (data?.signals) {
        setSignals(
          data.signals.slice(0, 5).map((s: any) => ({
            symbol: s.symbol || '?',
            direction: s.side || s.signal_type || '?',
            conviction: s.metadata?.conviction_score ?? s.metadata?.signal_strength ?? 0,
            timestamp: s.created_at || '',
          }))
        );
      }
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchSignals, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const unsub = wsManager.onSignalGenerated(() => fetchSignals());
    return unsub;
  }, [tradingMode, fetchSignals]);

  if (signals.length === 0) {
    return <div className="text-[10px] text-gray-600 font-mono">No recent signals</div>;
  }

  return (
    <div className="space-y-1 text-[10px] font-mono">
      {signals.map((sig, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <span
            className={cn(
              'w-4 text-center font-bold',
              sig.direction.toLowerCase().includes('buy') ? 'text-[#22c55e]' : 'text-[#ef4444]'
            )}
          >
            {sig.direction.toLowerCase().includes('buy') ? '↑' : '↓'}
          </span>
          <span className="text-gray-300 truncate flex-1">{sig.symbol}</span>
          <span className="text-gray-500 shrink-0">
            {(sig.conviction * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  );
};
