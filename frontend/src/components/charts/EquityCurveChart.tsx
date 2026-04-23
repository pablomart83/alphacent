/**
 * EquityCurveChart — Professional equity curve for AlphaCent.
 *
 * Design principles:
 * - Absolute equity value on Y-axis (not normalized) — traders care about dollars
 * - Single synchronized multi-pane chart via TvMultiPane — equity + drawdown share time axis
 * - Clean: blue area for equity, gray dashed for SPY (normalized to same start), green dashed for realized
 * - Drawdown shown as red area in a compact sub-pane
 * - Period selector filters data client-side; interval selector triggers parent re-fetch
 */
import { type FC, useMemo } from 'react';
import { TvMultiPane } from './TvMultiPane';
import type { TvSeriesConfig } from './TvChart';
import { TvPeriodSelector } from './TvPeriodSelector';
import { cn } from '../../lib/utils';
import { filterDataByPeriod } from '../../lib/chart-utils';

export interface EquityPoint {
  date: string;
  equity: number;
  realized?: number | null;
}

export interface SpyPoint {
  date: string;
  close: number;
}

export interface EquityCurveChartProps {
  equityData: EquityPoint[];
  spyData?: SpyPoint[];
  period: string;
  onPeriodChange: (p: string) => void;
  interval?: string;
  onIntervalChange?: (iv: string) => void;
  height?: number;
  /** Optional: total return % to show in header */
  totalReturnPct?: number | null;
  /** Optional: max drawdown % to show in header */
  maxDrawdownPct?: number | null;
}

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

export const EquityCurveChart: FC<EquityCurveChartProps> = ({
  equityData,
  spyData,
  period,
  onPeriodChange,
  interval = '1d',
  onIntervalChange,
  height = 380,
  totalReturnPct,
  maxDrawdownPct,
}) => {
  const mainHeight = Math.round(height * 0.70);
  const ddHeight   = Math.round(height * 0.30);

  const panes = useMemo(() => {
    if (!equityData?.length) return [];

    // ── Filter by period ──────────────────────────────────────────────
    const filtered = filterDataByPeriod(
      equityData.map(d => ({ ...d })),
      'date',
      period,
    ) as EquityPoint[];

    if (filtered.length < 2) return [];

    // ── SPY: scale to same starting equity so it's visually comparable ─
    const hasSpy = !!spyData?.length;
    let spyScaled: Array<{ date: string; value: number }> = [];
    if (hasSpy) {
      const spyMap = new Map(spyData!.map(s => [s.date, s.close]));
      // Find SPY value at the start of the filtered period
      const startDate = filtered[0].date;
      const startSpy = spyMap.get(startDate) ?? [...spyMap.entries()].find(([d]) => d >= startDate)?.[1];
      const startEquity = filtered[0].equity;
      if (startSpy && startEquity) {
        spyScaled = filtered
          .map(d => {
            const spyVal = spyMap.get(d.date);
            if (spyVal == null) return null;
            return { date: d.date, value: (spyVal / startSpy) * startEquity };
          })
          .filter(Boolean) as Array<{ date: string; value: number }>;
      }
    }

    // ── Realized line: scale same way ─────────────────────────────────
    const hasRealized = filtered.some(d => d.realized != null);
    let realizedScaled: Array<{ date: string; value: number }> = [];
    if (hasRealized) {
      const startEquity = filtered[0].equity;
      const startRealized = filtered[0].realized ?? 0;
      realizedScaled = filtered
        .filter(d => d.realized != null)
        .map(d => ({
          date: d.date,
          // Realized line = starting equity + cumulative realized PnL
          value: startEquity + ((d.realized ?? 0) - startRealized),
        }));
    }

    // ── Drawdown ──────────────────────────────────────────────────────
    let peak = filtered[0].equity;
    const ddData = filtered.map(d => {
      if (d.equity > peak) peak = d.equity;
      const dd = peak > 0 ? ((d.equity - peak) / peak) * 100 : 0;
      return { date: d.date, value: dd };
    });

    // ── Build series ──────────────────────────────────────────────────
    const mainSeries: TvSeriesConfig[] = [];

    // SPY first (behind portfolio)
    if (spyScaled.length > 1) {
      mainSeries.push({
        id: 'spy',
        type: 'line',
        data: spyScaled.map(d => ({ time: d.date, value: d.value })),
        color: '#6b7280',
        lineWidth: 1,
        dashed: true,
        lastValueVisible: false,
        priceLineVisible: false,
      });
    }

    // Realized (behind portfolio)
    if (realizedScaled.length > 1) {
      mainSeries.push({
        id: 'realized',
        type: 'line',
        data: realizedScaled.map(d => ({ time: d.date, value: d.value })),
        color: '#22c55e',
        lineWidth: 1,
        dashed: true,
        lastValueVisible: false,
        priceLineVisible: false,
      });
    }

    // Portfolio area (on top)
    mainSeries.push({
      id: 'portfolio',
      type: 'area',
      data: filtered.map(d => ({ time: d.date, value: d.equity })),
      lineColor: '#3b82f6',
      topColor: 'rgba(59,130,246,0.12)',
      bottomColor: 'transparent',
      lineWidth: 2,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    const ddSeries: TvSeriesConfig[] = [{
      id: 'drawdown',
      type: 'area',
      data: ddData.map(d => ({ time: d.date, value: d.value })),
      lineColor: 'rgba(239,68,68,0.7)',
      topColor: 'rgba(239,68,68,0.3)',
      bottomColor: 'rgba(239,68,68,0.02)',
      lineWidth: 1,
      lastValueVisible: false,
      priceLineVisible: false,
    }];

    return [
      {
        id: 'equity',
        series: mainSeries,
        height: mainHeight,
        showTimeScale: false,
        showPriceScale: true,
      },
      {
        id: 'drawdown',
        series: ddSeries,
        height: ddHeight,
        showTimeScale: true,
        showPriceScale: true,
        label: 'Drawdown %',
      },
    ];
  }, [equityData, spyData, period, mainHeight, ddHeight]);

  const hasSpy = !!spyData?.length;
  const hasRealized = equityData?.some(d => d.realized != null) ?? false;

  return (
    <div className="w-full flex flex-col gap-1">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TvPeriodSelector periods={PERIODS} activePeriod={period} onPeriodChange={onPeriodChange} />
          {onIntervalChange && (
            <div className="flex items-center border border-gray-800 rounded overflow-hidden">
              {(['1d', '4h', '1h'] as const).map((iv) => (
                <button
                  key={iv}
                  onClick={() => onIntervalChange(iv)}
                  className={cn(
                    'px-2 py-0.5 text-[10px] font-mono font-medium transition-colors',
                    interval === iv
                      ? 'bg-gray-700 text-gray-100'
                      : 'text-gray-600 hover:text-gray-300 hover:bg-gray-800/60',
                  )}
                >
                  {iv.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Stats + Legend */}
        <div className="flex items-center gap-4 text-[10px] font-mono">
          {totalReturnPct != null && (
            <span className={cn('font-semibold', totalReturnPct >= 0 ? 'text-green-400' : 'text-red-400')}>
              {totalReturnPct >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}%
            </span>
          )}
          {maxDrawdownPct != null && (
            <span className="text-red-400/70">DD {maxDrawdownPct.toFixed(2)}%</span>
          )}
          <span className="flex items-center gap-1 text-gray-500">
            <span className="w-4 h-[2px] bg-[#3b82f6] inline-block rounded" />
            Total
          </span>
          {hasRealized && (
            <span className="flex items-center gap-1 text-gray-500">
              <span className="w-4 inline-block" style={{ borderTop: '1.5px dashed #22c55e' }} />
              Realised
            </span>
          )}
          {hasSpy && (
            <span className="flex items-center gap-1 text-gray-500">
              <span className="w-4 inline-block" style={{ borderTop: '1.5px dashed #6b7280' }} />
              SPY
            </span>
          )}
        </div>
      </div>

      {/* Chart */}
      {panes.length > 0 ? (
        <TvMultiPane panes={panes} />
      ) : (
        <div
          className="flex items-center justify-center text-gray-600 text-xs font-mono"
          style={{ height }}
        >
          No equity data
        </div>
      )}
    </div>
  );
};
