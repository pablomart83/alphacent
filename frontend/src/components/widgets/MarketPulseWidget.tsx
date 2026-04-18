/**
 * MarketPulseWidget — 4 asset class regimes at a glance.
 * Equity / Crypto / Forex / Commodity — each with color + short label.
 * Compact, always useful, no navigation needed.
 */
import { type FC, useState, useCallback } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { cn } from '../../lib/utils';

interface RegimeRow {
  label: string;
  regime: string;
  confidence: number;
}

const REGIME_MAP: Record<string, { short: string; color: string; dot: string }> = {
  trending_up:          { short: '↑ Trend',   color: 'text-[#22c55e]', dot: 'bg-[#22c55e]' },
  trending_up_strong:   { short: '↑↑ Strong',  color: 'text-[#22c55e]', dot: 'bg-[#22c55e]' },
  trending_up_weak:     { short: '↑ Weak',     color: 'text-[#86efac]', dot: 'bg-[#86efac]' },
  trending_down:        { short: '↓ Trend',    color: 'text-[#ef4444]', dot: 'bg-[#ef4444]' },
  trending_down_strong: { short: '↓↓ Strong',  color: 'text-[#ef4444]', dot: 'bg-[#ef4444]' },
  trending_down_weak:   { short: '↓ Weak',     color: 'text-[#fca5a5]', dot: 'bg-[#fca5a5]' },
  ranging_high_vol:     { short: '↔ Hi Vol',   color: 'text-[#eab308]', dot: 'bg-[#eab308]' },
  ranging_low_vol:      { short: '↔ Lo Vol',   color: 'text-[#3b82f6]', dot: 'bg-[#3b82f6]' },
  high_volatility:      { short: '⚡ Hi Vol',  color: 'text-[#eab308]', dot: 'bg-[#eab308]' },
  unknown:              { short: '? Unknown',  color: 'text-gray-500',  dot: 'bg-gray-600'  },
};

function fmt(regime: string) {
  return REGIME_MAP[regime] ?? { short: regime.replace(/_/g, ' '), color: 'text-gray-400', dot: 'bg-gray-600' };
}

export const MarketPulseWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [rows, setRows] = useState<RegimeRow[]>([]);

  const fetch = useCallback(async () => {
    if (!tradingMode) return;
    try {
      // Try comprehensive regime endpoint first
      try {
        const data = await apiClient.getComprehensiveRegimeAnalysis();
        // Response shape: { current_regimes: { equity: {regime, confidence}, crypto: {...}, forex: {...}, commodity: {...} } }
        const cr = data?.current_regimes;
        if (cr && (cr.equity || cr.crypto || cr.forex || cr.commodity)) {
          setRows([
            { label: 'Equity',    regime: cr.equity?.regime    || 'unknown', confidence: cr.equity?.confidence    || 0 },
            { label: 'Crypto',    regime: cr.crypto?.regime    || 'unknown', confidence: cr.crypto?.confidence    || 0 },
            { label: 'Forex',     regime: cr.forex?.regime     || 'unknown', confidence: cr.forex?.confidence     || 0 },
            { label: 'Commodity', regime: cr.commodity?.regime || 'unknown', confidence: cr.commodity?.confidence || 0 },
          ]);
          return;
        }
      } catch { /* fall through */ }

      // Fallback: dashboard summary
      const summary = await apiClient.getDashboardSummary(tradingMode);
      const regime = summary?.market_regime?.current_regime || 'unknown';
      setRows([
        { label: 'Equity',    regime, confidence: summary?.market_regime?.confidence || 0 },
        { label: 'Crypto',    regime: 'unknown', confidence: 0 },
        { label: 'Forex',     regime: 'unknown', confidence: 0 },
        { label: 'Commodity', regime: 'unknown', confidence: 0 },
      ]);
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetch, intervalMs: 60000, enabled: !!tradingMode });

  if (rows.length === 0) {
    return <div className="text-xs text-gray-600 font-mono py-1">Loading...</div>;
  }

  return (
    <div className="flex flex-col gap-1 text-xs font-mono h-full justify-center">
      {rows.map(r => {
        const cfg = fmt(r.regime);
        return (
          <div key={r.label} className="flex items-center gap-2">
            {/* Dot */}
            <div className={cn('w-1.5 h-1.5 rounded-full shrink-0', cfg.dot)} />
            {/* Asset class */}
            <span className="text-gray-500 w-14 shrink-0">{r.label}</span>
            {/* Regime */}
            <span className={cn('font-semibold flex-1 truncate', cfg.color)}>{cfg.short}</span>
            {/* Confidence */}
            {r.confidence > 0 && (
              <span className="text-gray-700 text-[10px] shrink-0">{(r.confidence * 100).toFixed(0)}%</span>
            )}
          </div>
        );
      })}
    </div>
  );
};
