import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { wsManager } from '../../services/websocket';
import { formatPercentage } from '../../lib/utils';

interface Mover {
  symbol: string;
  pnlPct: number;
}

export const TopMoversWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [gainers, setGainers] = useState<Mover[]>([]);
  const [losers, setLosers] = useState<Mover[]>([]);

  const fetchMovers = useCallback(async () => {
    if (!tradingMode) return;
    try {
      // Try dedicated endpoint first, fall back to positions
      try {
        const data = await apiClient.getTopMovers(tradingMode);
        if (data?.gainers && data?.losers) {
          setGainers(data.gainers.slice(0, 5).map((g: any) => ({ symbol: g.symbol, pnlPct: g.daily_pnl_pct ?? g.pnl_pct ?? 0 })));
          setLosers(data.losers.slice(0, 5).map((l: any) => ({ symbol: l.symbol, pnlPct: l.daily_pnl_pct ?? l.pnl_pct ?? 0 })));
          return;
        }
      } catch {
        // Endpoint not available yet — fall back
      }

      const positions = await apiClient.getPositions(tradingMode);
      const sorted = positions
        .map(p => ({ symbol: p.symbol || '?', pnlPct: p.unrealized_pnl_percent ?? 0 }))
        .sort((a, b) => b.pnlPct - a.pnlPct);
      setGainers(sorted.filter(p => p.pnlPct > 0).slice(0, 5));
      setLosers(sorted.filter(p => p.pnlPct < 0).slice(-5).reverse());
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchMovers, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const unsub = wsManager.onPositionUpdate(() => fetchMovers());
    return unsub;
  }, [tradingMode, fetchMovers]);

  return (
    <div className="flex gap-3 text-[10px] font-mono">
      <div className="flex-1 min-w-0">
        <div className="text-gray-500 mb-1">▲ Gainers</div>
        {gainers.length === 0 ? (
          <div className="text-gray-600">—</div>
        ) : (
          gainers.map(g => (
            <div key={g.symbol} className="flex justify-between py-0.5">
              <span className="text-gray-300 truncate">{g.symbol}</span>
              <span className="text-[#22c55e] shrink-0 ml-2">{formatPercentage(g.pnlPct)}</span>
            </div>
          ))
        )}
      </div>
      <div className="w-px bg-gray-800" />
      <div className="flex-1 min-w-0">
        <div className="text-gray-500 mb-1">▼ Losers</div>
        {losers.length === 0 ? (
          <div className="text-gray-600">—</div>
        ) : (
          losers.map(l => (
            <div key={l.symbol} className="flex justify-between py-0.5">
              <span className="text-gray-300 truncate">{l.symbol}</span>
              <span className="text-[#ef4444] shrink-0 ml-2">{formatPercentage(l.pnlPct)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
