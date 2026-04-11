import { type FC, useState, useCallback, useEffect } from 'react';
import { useTradingMode } from '../contexts/TradingModeContext';
import { useWebSocketConnection } from '../hooks/useWebSocket';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { colors } from '../lib/design-tokens';

interface SummaryData {
  totalEquity: number;
  dailyPnl: number;
  dailyPnlPct: number;
  openPositions: number;
  activeStrategies: number;
  marketRegime: string;
  healthScore: number;
}

const REGIME_SHORT: Record<string, string> = {
  trending_up: 'Trending ↑',
  trending_down: 'Trending ↓',
  ranging_high_vol: 'Ranging HV',
  ranging_low_vol: 'Ranging LV',
  unknown: 'Unknown',
};

function getHealthColor(score: number): string {
  if (score >= 80) return colors.green;
  if (score >= 60) return '#84cc16';
  if (score >= 40) return colors.yellow;
  return colors.red;
}

export const GlobalSummaryBar: FC = () => {
  const { tradingMode } = useTradingMode();
  const wsConnected = useWebSocketConnection();
  const [data, setData] = useState<SummaryData>({
    totalEquity: 0,
    dailyPnl: 0,
    dailyPnlPct: 0,
    openPositions: 0,
    activeStrategies: 0,
    marketRegime: 'unknown',
    healthScore: 0,
  });

  const fetchSummary = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const [account, summary] = await Promise.all([
        apiClient.getAccountInfo(tradingMode),
        apiClient.getDashboardSummary(tradingMode),
      ]);

      const base = account.equity || account.balance || 1;
      setData({
        totalEquity: account.equity ?? 0,
        dailyPnl: account.daily_pnl ?? 0,
        dailyPnlPct: base !== 0 ? ((account.daily_pnl ?? 0) / base) * 100 : 0,
        openPositions: summary?.quick_stats?.open_positions ?? 0,
        activeStrategies: summary?.quick_stats?.active_strategies ?? 0,
        marketRegime: summary?.market_regime?.current_regime ?? 'unknown',
        healthScore: summary?.health_score?.score ?? 0,
      });
    } catch {
      // Non-critical — keep last known values
    }
  }, [tradingMode]);

  // Poll every 30s as fallback; skip polling when WS is connected (data arrives via WS events)
  usePolling({ fetchFn: fetchSummary, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  // Subscribe to WS position/account events for real-time updates
  useEffect(() => {
    if (!tradingMode) return;
    const unsubPosition = wsManager.onPositionUpdate(() => fetchSummary());
    const unsubOrder = wsManager.onOrderUpdate(() => fetchSummary());
    return () => { unsubPosition(); unsubOrder(); };
  }, [tradingMode, fetchSummary]);

  const pnlColor = data.dailyPnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]';
  const pnlSign = data.dailyPnl >= 0 ? '+' : '';

  return (
    <div
      className="flex items-center gap-4 px-4 md:px-8 h-12 min-h-[48px] max-h-[48px] border-b overflow-x-auto"
      style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-dark-surface)' }}
    >
      {/* Total Equity — always visible */}
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Equity</span>
        <span className="text-sm font-mono font-semibold text-gray-100">
          {formatCurrency(data.totalEquity)}
        </span>
      </div>

      <Separator />

      {/* Daily P&L — always visible */}
      <div className="flex items-center gap-1.5 shrink-0">
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Daily P&L</span>
        <span className={cn('text-sm font-mono font-semibold', pnlColor)}>
          {pnlSign}{formatCurrency(data.dailyPnl)}
        </span>
        <span className={cn('text-xs font-mono', pnlColor)}>
          ({pnlSign}{formatPercentage(data.dailyPnlPct)})
        </span>
      </div>

      {/* Below 768px: remaining metrics are hidden but accessible via horizontal scroll */}
      <Separator className="hidden md:block" />

      {/* Open Positions — hidden below 768px */}
      <div className="hidden md:flex items-center gap-1.5 shrink-0">
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Positions</span>
        <span className="text-sm font-mono font-semibold text-gray-100">
          {data.openPositions}
        </span>
      </div>

      <Separator className="hidden md:block" />

      {/* Active Strategies — hidden below 768px */}
      <div className="hidden md:flex items-center gap-1.5 shrink-0">
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Strategies</span>
        <span className="text-sm font-mono font-semibold text-gray-100">
          {data.activeStrategies}
        </span>
      </div>

      <Separator className="hidden md:block" />

      {/* Market Regime — hidden below 768px */}
      <div className="hidden md:flex items-center gap-1.5 shrink-0">
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Regime</span>
        <span className="text-xs font-mono font-medium px-1.5 py-0.5 rounded bg-gray-800 text-gray-300 border border-gray-700">
          {REGIME_SHORT[data.marketRegime] || data.marketRegime}
        </span>
      </div>

      <Separator className="hidden md:block" />

      {/* System Health — hidden below 768px */}
      <div className="hidden md:flex items-center gap-1.5 shrink-0">
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Health</span>
        <span
          className="text-sm font-mono font-semibold"
          style={{ color: getHealthColor(data.healthScore) }}
        >
          {data.healthScore}
        </span>
        {/* Yellow warning when WS disconnected */}
        {!wsConnected && (
          <span
            className="w-2 h-2 rounded-full animate-pulse"
            style={{ backgroundColor: colors.yellow }}
            title="WebSocket disconnected"
          />
        )}
      </div>

      {/* Condensed Multi-Timeframe placeholder at > 1440px */}
      <div className="hidden 2xl:flex items-center gap-1.5 ml-auto shrink-0">
        <Separator />
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Returns</span>
        {['1D', '1W', '1M', 'YTD'].map((period) => (
          <span
            key={period}
            className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-800 text-gray-500 border border-gray-700"
          >
            {period}: —
          </span>
        ))}
      </div>
    </div>
  );
};

const Separator: FC<{ className?: string }> = ({ className }) => (
  <div className={cn('w-px h-4 bg-gray-700 shrink-0', className)} />
);
