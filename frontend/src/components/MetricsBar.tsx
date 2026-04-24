import { type FC, useState, useCallback, useEffect, useRef, memo } from 'react';
import { useTradingMode } from '../contexts/TradingModeContext';
import { useWebSocketConnection } from '../hooks/useWebSocket';
import { usePolling } from '../hooks/usePolling';
import { useLastSynced } from '../hooks/useLastSynced';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn } from '../lib/utils';
import { colors } from '../lib/design-tokens';
import { AnimatedNumber } from './ui/animated-number';
import { FlashWrapper } from './ui/flash-wrapper';

interface MetricsData {
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

export const MetricsBar: FC = memo(() => {
  const { tradingMode } = useTradingMode();
  const wsConnected = useWebSocketConnection();
  const { label: lastSyncedLabel, touch: touchLastSynced } = useLastSynced();
  const [data, setData] = useState<MetricsData>({
    totalEquity: 0,
    dailyPnl: 0,
    dailyPnlPct: 0,
    openPositions: 0,
    activeStrategies: 0,
    marketRegime: 'unknown',
    healthScore: 0,
  });

  // Signal chip state
  const [signalChip, setSignalChip] = useState<{ ago: string; total: number; executed: number } | null>(null);

  function relAge(ts: string): string {
    if (!ts) return '—';
    const ms = Date.now() - new Date(ts.endsWith('Z') ? ts : ts + 'Z').getTime();
    const m = Math.floor(ms / 60000);
    if (m < 60) return `${m}m`;
    return `${Math.floor(m / 60)}h`;
  }

  const fetchMetrics = useCallback(async () => {
    if (!tradingMode) return;
    try {
      // Use lightweight metrics-bar endpoint instead of full dashboard/summary
      const [metricsBar, signals] = await Promise.all([
        apiClient.get(`/account/metrics-bar?mode=${tradingMode}`),
        apiClient.getRecentSignals(tradingMode, 20).catch(() => null),
      ]);
      setData({
        totalEquity: metricsBar.equity ?? 0,
        dailyPnl: metricsBar.daily_pnl ?? 0,
        dailyPnlPct: metricsBar.daily_pnl_pct ?? 0,
        openPositions: metricsBar.open_positions ?? 0,
        activeStrategies: metricsBar.active_strategies ?? 0,
        marketRegime: metricsBar.market_regime ?? 'unknown',
        healthScore: metricsBar.health_score ?? 0,
      });
      touchLastSynced();

      if (signals?.signals?.length) {
        setSignalChip({
          ago: relAge(signals.signals[0]?.created_at || ''),
          total: signals.summary.total,
          executed: signals.summary.accepted,
        });
      }
    } catch {
      // Non-critical — keep last known values
    }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchMetrics, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const unsubPosition = wsManager.onPositionUpdate(() => fetchMetrics());
    const unsubOrder = wsManager.onOrderUpdate(() => fetchMetrics());
    return () => { unsubPosition(); unsubOrder(); };
  }, [tradingMode, fetchMetrics]);

  const pnlColor = data.dailyPnl >= 0 ? 'text-[#22c55e]' : 'text-[#ef4444]';

  // Track previous values for flash direction
  const prevDataRef = useRef(data);
  useEffect(() => {
    prevDataRef.current = data;
  });

  return (
    <div
      className="flex items-center gap-3 px-4 h-10 min-h-[40px] max-h-[40px] border-b overflow-x-auto scrollbar-hide"
      style={{ borderColor: 'var(--color-dark-border)', backgroundColor: '#0a0e17' }}
    >
      {/* Connection dot */}
      <div className="flex items-center gap-1.5 shrink-0">
        <div
          className={cn('w-2 h-2 rounded-full', wsConnected ? 'bg-accent-green' : 'bg-accent-red')}
          style={!wsConnected ? { backgroundColor: colors.yellow, animation: 'pulse 2s infinite' } : undefined}
        />
      </div>

      <Sep />

      {/* Equity */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-xs text-gray-500 tracking-wide">Equity</span>
        <FlashWrapper value={data.totalEquity} previousValue={prevDataRef.current.totalEquity}>
          <AnimatedNumber value={data.totalEquity} format="currency" className="text-xs font-mono font-semibold text-gray-100" />
        </FlashWrapper>
      </div>

      <Sep />

      {/* Daily P&L */}
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-xs text-gray-500 tracking-wide">P&L</span>
        <FlashWrapper value={data.dailyPnl} previousValue={prevDataRef.current.dailyPnl}>
          <AnimatedNumber value={data.dailyPnl} format="currency" showSign className={cn('text-xs font-mono font-semibold', pnlColor)} />
        </FlashWrapper>
        <span className={cn('text-xs font-mono', pnlColor)}>
          (<AnimatedNumber value={data.dailyPnlPct} format="percentage" showSign className={cn('text-xs font-mono', pnlColor)} />)
        </span>
      </div>

      <Sep className="hidden md:block" />

      {/* Positions */}
      <div className="hidden md:flex items-center gap-1 shrink-0">
        <span className="text-xs text-gray-500 tracking-wide">Pos</span>
        <AnimatedNumber value={data.openPositions} format="integer" className="text-xs font-mono font-semibold text-gray-100" />
      </div>

      <Sep className="hidden md:block" />

      {/* Strategies */}
      <div className="hidden md:flex items-center gap-1 shrink-0">
        <span className="text-xs text-gray-500 tracking-wide">Strats</span>
        <AnimatedNumber value={data.activeStrategies} format="integer" className="text-xs font-mono font-semibold text-gray-100" />
      </div>

      <Sep className="hidden md:block" />

      {/* Regime */}
      <div className="hidden md:flex items-center gap-1 shrink-0">
        <span className="text-xs text-gray-500 tracking-wide">Regime</span>
        <span className="text-xs font-mono font-medium px-1.5 py-0.5 rounded bg-gray-800 text-gray-300 border border-gray-700">
          {REGIME_SHORT[data.marketRegime] || data.marketRegime}
        </span>
      </div>

      <Sep className="hidden md:block" />

      {/* Health */}
      <div className="hidden md:flex items-center gap-1 shrink-0">
        <span className="text-xs text-gray-500 tracking-wide">Health</span>
        <span className="text-xs font-mono font-semibold" style={{ color: getHealthColor(data.healthScore) }}>
          {data.healthScore}
        </span>
      </div>

      <Sep className="hidden lg:block" />

      {/* Last Synced */}
      <div className="hidden lg:flex items-center gap-1 shrink-0">
        <span className="text-xs text-gray-500 tracking-wide">Synced</span>
        <span className="text-xs font-mono text-gray-400">{lastSyncedLabel}</span>
      </div>

      {/* Signal chip */}
      {signalChip && (
        <>
          <Sep className="hidden lg:block" />
          <div className="hidden lg:flex items-center gap-1 shrink-0">
            <span className="text-xs text-gray-500 tracking-wide">Signal</span>
            <span className="text-xs font-mono text-gray-400">{signalChip.ago} ago</span>
            <span className="text-xs font-mono text-gray-500">·</span>
            <span className="text-xs font-mono text-gray-300">{signalChip.total}</span>
            <span className="text-xs font-mono text-gray-500">→</span>
            <span className={cn(
              'text-xs font-mono font-semibold',
              signalChip.executed > 0 ? 'text-[#22c55e]' : 'text-[#ef4444]'
            )}>
              {signalChip.executed} exec
            </span>
          </div>
        </>
      )}

      {/* Condensed Multi-Timeframe at > 1440px */}
      <div className="hidden 2xl:flex items-center gap-1 ml-auto shrink-0">
        <Sep />
        <span className="text-xs text-gray-500 tracking-wide">Returns</span>
        {['1D', '1W', '1M', 'YTD'].map(period => (
          <span
            key={period}
            className="text-xs font-mono px-1 py-0.5 rounded bg-gray-800 text-gray-500 border border-gray-700"
          >
            {period}: —
          </span>
        ))}
      </div>
    </div>
  );
});

const Sep: FC<{ className?: string }> = ({ className }) => (
  <div className={cn('w-px h-3 bg-gray-700/60 shrink-0', className)} />
);
