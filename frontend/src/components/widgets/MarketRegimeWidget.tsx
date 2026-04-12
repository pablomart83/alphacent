import { type FC, useState, useCallback } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { cn } from '../../lib/utils';

interface RegimeInfo {
  assetClass: string;
  regime: string;
  confidence: number;
}

const REGIME_COLORS: Record<string, string> = {
  trending_up: 'text-[#22c55e]',
  trending_down: 'text-[#ef4444]',
  ranging_high_vol: 'text-[#eab308]',
  ranging_low_vol: 'text-[#3b82f6]',
  unknown: 'text-gray-500',
};

const REGIME_SHORT: Record<string, string> = {
  trending_up: '↑ Trend',
  trending_down: '↓ Trend',
  ranging_high_vol: '↔ HV',
  ranging_low_vol: '↔ LV',
  unknown: '?',
};

export const MarketRegimeWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [regimes, setRegimes] = useState<RegimeInfo[]>([]);

  const fetchRegimes = useCallback(async () => {
    if (!tradingMode) return;
    try {
      const summary = await apiClient.getDashboardSummary(tradingMode);
      const regime = summary?.market_regime;
      if (regime) {
        // Build per-asset-class regimes from available data
        const items: RegimeInfo[] = [];
        if (regime.current_regime) {
          items.push({ assetClass: 'Overall', regime: regime.current_regime, confidence: regime.confidence ?? 0 });
        }
        // If per-asset-class data is available
        if (regime.per_asset_class) {
          for (const [ac, info] of Object.entries(regime.per_asset_class as Record<string, any>)) {
            items.push({ assetClass: ac, regime: info.regime || 'unknown', confidence: info.confidence ?? 0 });
          }
        }
        // Pad to 4 if needed
        const assetClasses = ['Equities', 'Crypto', 'Forex', 'Commodities'];
        if (items.length <= 1) {
          for (const ac of assetClasses) {
            if (!items.find(i => i.assetClass.toLowerCase() === ac.toLowerCase())) {
              items.push({ assetClass: ac, regime: regime.current_regime || 'unknown', confidence: regime.confidence ?? 0 });
            }
            if (items.length >= 4) break;
          }
        }
        setRegimes(items.slice(0, 4));
      }
    } catch { /* ignore */ }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchRegimes, intervalMs: 30000, enabled: !!tradingMode });

  if (regimes.length === 0) {
    return <div className="text-xs text-gray-600 font-mono">Loading regime data...</div>;
  }

  return (
    <div className="grid grid-cols-2 gap-1.5 text-xs font-mono">
      {regimes.map(r => (
        <div key={r.assetClass} className="flex flex-col px-1.5 py-1 rounded bg-gray-900/50 border border-gray-800">
          <span className="text-gray-500 truncate">{r.assetClass}</span>
          <span className={cn('font-semibold', REGIME_COLORS[r.regime] || 'text-gray-400')}>
            {REGIME_SHORT[r.regime] || r.regime}
          </span>
          {r.confidence > 0 && (
            <span className="text-gray-600">{(r.confidence * 100).toFixed(0)}%</span>
          )}
        </div>
      ))}
    </div>
  );
};
