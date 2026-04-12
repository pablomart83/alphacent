import { type FC, useState, useCallback } from 'react';
import { useTradingMode } from '../../contexts/TradingModeContext';
import { usePolling } from '../../hooks/usePolling';
import { apiClient } from '../../services/api';
import { cn } from '../../lib/utils';

interface MacroIndicator {
  label: string;
  value: string;
  color?: string;
}

export const MacroPulseWidget: FC = () => {
  const { tradingMode } = useTradingMode();
  const [indicators, setIndicators] = useState<MacroIndicator[]>([]);

  const fetchMacro = useCallback(async () => {
    if (!tradingMode) return;
    try {
      // Try to get macro data from dashboard summary or regime endpoint
      const summary = await apiClient.getDashboardSummary(tradingMode);
      const regime = summary?.market_regime;
      const items: MacroIndicator[] = [];

      // Extract macro indicators if available
      if (regime?.macro_indicators) {
        const macro = regime.macro_indicators;
        if (macro.vix !== undefined) items.push({ label: 'VIX', value: macro.vix.toFixed(1), color: macro.vix > 25 ? '#ef4444' : macro.vix > 18 ? '#eab308' : '#22c55e' });
        if (macro.fed_funds !== undefined) items.push({ label: 'Fed Funds', value: `${macro.fed_funds.toFixed(2)}%` });
        if (macro.treasury_10y !== undefined) items.push({ label: '10Y', value: `${macro.treasury_10y.toFixed(2)}%` });
        if (macro.yield_curve !== undefined) items.push({ label: 'Yield Curve', value: `${macro.yield_curve.toFixed(0)}bps`, color: macro.yield_curve < 0 ? '#ef4444' : '#22c55e' });
        if (macro.inflation !== undefined) items.push({ label: 'CPI', value: `${macro.inflation.toFixed(1)}%` });
      }

      // Fallback: show placeholder indicators
      if (items.length === 0) {
        items.push(
          { label: 'VIX', value: '—' },
          { label: 'Fed Funds', value: '—' },
          { label: '10Y', value: '—' },
          { label: 'Yield Curve', value: '—' },
          { label: 'CPI', value: '—' },
        );
      }

      setIndicators(items);
    } catch {
      setIndicators([
        { label: 'VIX', value: '—' },
        { label: 'Fed Funds', value: '—' },
        { label: '10Y', value: '—' },
        { label: 'Yield Curve', value: '—' },
        { label: 'CPI', value: '—' },
      ]);
    }
  }, [tradingMode]);

  usePolling({ fetchFn: fetchMacro, intervalMs: 60000, enabled: !!tradingMode });

  return (
    <div className="space-y-1 text-[10px] font-mono">
      {indicators.map((ind, idx) => (
        <div key={idx} className="flex items-center justify-between">
          <span className="text-gray-500">{ind.label}</span>
          <span
            className={cn('font-semibold', !ind.color && 'text-gray-300')}
            style={ind.color ? { color: ind.color } : undefined}
          >
            {ind.value}
          </span>
        </div>
      ))}
    </div>
  );
};
