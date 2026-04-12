import { type FC, useState, useCallback, useEffect, memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTradingMode } from '../contexts/TradingModeContext';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { cn } from '../lib/utils';
import { AnimatedNumber } from './ui/animated-number';
import { FlashWrapper } from './ui/flash-wrapper';

interface TickerPosition {
  symbol: string;
  currentPrice: number;
  pnlPct: number;
  value: number;
}

export const PositionTickerStrip: FC = memo(() => {
  const { tradingMode } = useTradingMode();
  const navigate = useNavigate();
  const isMobile = useMediaQuery('(max-width: 767px)');
  const [positions, setPositions] = useState<TickerPosition[]>([]);

  const fetchPositions = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const raw = await apiClient.getPositions(tradingMode);
      const sorted = raw
        .map(p => ({
          symbol: p.symbol || '',
          currentPrice: p.current_price ?? 0,
          pnlPct: p.unrealized_pnl_percent ?? 0,
          value: Math.abs(p.invested_amount ?? (p.quantity * p.entry_price)),
        }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 15);
      setPositions(sorted);
    } catch {
      // Non-critical
    }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchPositions, intervalMs: 30000, enabled: !!tradingMode, skipWhenWsConnected: true });

  useEffect(() => {
    if (!tradingMode) return;
    const unsub = wsManager.onPositionUpdate(() => {
      fetchPositions();
    });
    return unsub;
  }, [tradingMode, fetchPositions]);

  // Hidden below 768px
  if (isMobile) return null;

  if (positions.length === 0) return null;

  return (
    <div
      className="flex items-center h-9 max-h-[36px] min-h-[36px] border-b overflow-x-auto scrollbar-hide gap-1 px-3"
      style={{ borderColor: 'var(--color-dark-border)', backgroundColor: '#080c14' }}
    >
      {positions.map(pos => {
        const isPositive = pos.pnlPct >= 0;
        return (
          <FlashWrapper
            key={pos.symbol}
            value={pos.currentPrice}
          >
            <button
              onClick={() => navigate(`/portfolio/${encodeURIComponent(pos.symbol)}`)}
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-mono shrink-0 transition-all duration-150',
                'hover:bg-gray-800 hover:scale-[1.02] cursor-pointer border border-transparent',
              )}
            >
              <span className="text-gray-300 font-semibold">{pos.symbol}</span>
              <span className="text-gray-500">$<AnimatedNumber value={pos.currentPrice} format="number" decimals={2} className="text-gray-500" /></span>
              <AnimatedNumber
                value={pos.pnlPct}
                format="percentage"
                showSign
                className={cn('font-semibold', isPositive ? 'text-[#22c55e]' : 'text-[#ef4444]')}
              />
            </button>
          </FlashWrapper>
        );
      })}
    </div>
  );
});
