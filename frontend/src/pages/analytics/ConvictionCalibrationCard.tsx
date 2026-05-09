/**
 * ConvictionCalibrationCard — Score vs P&L monitor.
 *
 * Shows whether higher conviction scores produce higher avg P&L (monotonicity).
 * A well-calibrated scorer has strictly increasing avg P&L as score rises.
 *
 * Key signals:
 *   - Red banner: a bucket above threshold is negative EV → raise threshold
 *   - Amber banner: monotonicity violated → scorer needs reweighting
 *   - Green banner: all good, scorer is working
 *   - ⚠ on any bucket with < 30 trades (statistically weak)
 */

import { type FC, useEffect, useState } from 'react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../services/api';

// ── Types ─────────────────────────────────────────────────────────────────────

interface ConvictionBucket {
  bucket: string;
  label: string;
  min_score: number;
  max_score: number;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_pnl: number;
  total_pnl: number;
  is_positive_ev: boolean;
  is_above_threshold: boolean;
  sample_size_warning: boolean;
}

interface CalibrationData {
  buckets: ConvictionBucket[];
  threshold: number;
  is_monotonic: boolean;
  monotonicity_violations: string[];
  negative_ev_above_threshold: string[];
  total_trades_with_score: number;
  coverage_pct: number;
  recommendation: string;
  data_window_days: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtPnl(n: number): string {
  const s = Math.abs(n) >= 1000
    ? `$${(Math.abs(n) / 1000).toFixed(1)}K`
    : `$${Math.abs(n).toFixed(0)}`;
  return n >= 0 ? `+${s}` : `-${s}`;
}

// ── Bar visualisation ─────────────────────────────────────────────────────────

const PnlBar: FC<{ value: number; maxAbs: number }> = ({ value, maxAbs }) => {
  if (maxAbs === 0) return <div className="h-2 w-full bg-gray-800 rounded" />;
  const pct = Math.min(Math.abs(value) / maxAbs * 100, 100);
  return (
    <div className="h-2 w-full bg-gray-800 rounded overflow-hidden">
      <div
        className={cn('h-full rounded', value >= 0 ? 'bg-accent-green' : 'bg-accent-red')}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
};

// ── Main Component ────────────────────────────────────────────────────────────

interface ConvictionCalibrationCardProps {
  days?: number;
}

export const ConvictionCalibrationCard: FC<ConvictionCalibrationCardProps> = ({ days = 30 }) => {
  const [data, setData] = useState<CalibrationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [window, setWindow] = useState(days);
  const [granularity, setGranularity] = useState(2);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiClient.getConvictionCalibration(window, granularity)
      .then(setData)
      .catch((e: any) => setError(e?.message || 'Failed to load calibration data'))
      .finally(() => setLoading(false));
  }, [window, granularity]);

  // ── Status banner ─────────────────────────────────────────────────────────
  const bannerConfig = data
    ? data.negative_ev_above_threshold.length > 0
      ? { color: 'border-accent-red bg-accent-red/10 text-accent-red', icon: '✗', label: 'Threshold too low — negative EV above threshold' }
      : !data.is_monotonic
      ? { color: 'border-amber-500 bg-amber-500/10 text-amber-400', icon: '⚠', label: 'Non-monotonic — scorer needs reweighting' }
      : { color: 'border-accent-green bg-accent-green/10 text-accent-green', icon: '✓', label: 'Well-calibrated — monotonic above threshold' }
    : null;

  const maxAbsPnl = data
    ? Math.max(...data.buckets.map((b) => Math.abs(b.avg_pnl)), 1)
    : 1;

  return (
    <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-mono font-semibold text-gray-300">Conviction Score Calibration</p>
          <p className="text-xs font-mono text-gray-500 mt-0.5">
            Does higher conviction → higher P&L? Threshold: {data?.threshold ?? 70}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* Granularity selector */}
          <div className="flex items-center gap-0.5">
            <span className="text-[10px] font-mono text-gray-600 mr-1">bucket</span>
            {[1, 2, 5].map((g) => (
              <button
                key={g}
                onClick={() => setGranularity(g)}
                className={cn(
                  'px-1.5 py-0.5 text-[10px] font-mono rounded transition-colors',
                  granularity === g
                    ? 'bg-blue-600/30 text-blue-300 font-semibold'
                    : 'text-gray-600 hover:text-gray-300',
                )}
              >
                {g}pt
              </button>
            ))}
          </div>
          {/* Window selector */}
          <div className="flex items-center gap-1">
            {[7, 14, 30, 0].map((d) => (
              <button
                key={d}
                onClick={() => setWindow(d)}
                className={cn(
                  'px-2 py-0.5 text-[10px] font-mono rounded transition-colors',
                  window === d
                    ? 'bg-gray-700 text-gray-200 font-semibold'
                    : 'text-gray-600 hover:text-gray-300',
                )}
              >
                {d === 0 ? 'ALL' : `${d}d`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center h-24 text-xs text-gray-500 font-mono">
          Computing…
        </div>
      )}

      {error && (
        <div className="text-xs text-accent-red font-mono p-2">{error}</div>
      )}

      {data && !loading && (
        <>
          {/* Status banner */}
          {bannerConfig && (
            <div className={cn('rounded border px-3 py-2 text-xs font-mono flex items-start gap-2', bannerConfig.color)}>
              <span className="font-bold shrink-0">{bannerConfig.icon}</span>
              <div className="space-y-0.5">
                <p className="font-semibold">{bannerConfig.label}</p>
                <p className="opacity-80">{data.recommendation}</p>
              </div>
            </div>
          )}

          {/* Bucket table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-[var(--color-dark-border)]">
                  <th className="text-left py-1.5 pr-3 text-gray-500 font-normal">Score</th>
                  <th className="text-right py-1.5 px-2 text-gray-500 font-normal">Trades</th>
                  <th className="text-right py-1.5 px-2 text-gray-500 font-normal">Win%</th>
                  <th className="text-right py-1.5 px-2 text-gray-500 font-normal">Avg P&L</th>
                  <th className="text-right py-1.5 px-2 text-gray-500 font-normal">Total P&L</th>
                  <th className="py-1.5 pl-3 text-gray-500 font-normal w-24">Distribution</th>
                </tr>
              </thead>
              <tbody>
                {data.buckets
                  .filter((b) => b.trades > 0 || b.is_above_threshold)
                  .map((b) => {
                  const isThresholdRow = b.min_score === data.threshold;
                  return (
                    <tr
                      key={b.bucket}
                      className={cn(
                        'border-b border-[var(--color-dark-border)]/40',
                        isThresholdRow && 'border-t-2 border-t-blue-500/50',
                        b.is_above_threshold && !b.is_positive_ev && b.trades > 0
                          ? 'bg-accent-red/5'
                          : b.is_above_threshold && b.is_positive_ev
                          ? 'bg-accent-green/5'
                          : '',
                      )}
                    >
                      <td className="py-1 pr-3">
                        <div className="flex items-center gap-1.5">
                          {isThresholdRow && (
                            <span className="text-[9px] text-blue-400 font-semibold">▶</span>
                          )}
                          <span className={cn(
                            'font-semibold',
                            b.is_above_threshold ? 'text-gray-200' : 'text-gray-500',
                          )}>
                            {b.label}
                          </span>
                          {b.sample_size_warning && b.trades > 0 && (
                            <span className="text-amber-400 text-[9px]" title="< 30 trades — statistically weak">⚠</span>
                          )}
                          {b.trades === 0 && (
                            <span className="text-gray-700 text-[9px]">—</span>
                          )}
                        </div>
                      </td>
                      <td className="py-1 px-2 text-right text-gray-400">
                        {b.trades > 0 ? b.trades : '—'}
                      </td>
                      <td className={cn(
                        'py-1 px-2 text-right',
                        b.trades > 0
                          ? b.win_rate >= 50 ? 'text-accent-green' : 'text-accent-red'
                          : 'text-gray-700',
                      )}>
                        {b.trades > 0 ? `${b.win_rate.toFixed(0)}%` : '—'}
                      </td>
                      <td className={cn(
                        'py-1 px-2 text-right font-semibold',
                        b.trades > 0
                          ? b.avg_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
                          : 'text-gray-700',
                      )}>
                        {b.trades > 0 ? fmtPnl(b.avg_pnl) : '—'}
                      </td>
                      <td className={cn(
                        'py-1 px-2 text-right',
                        b.trades > 0
                          ? b.total_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'
                          : 'text-gray-700',
                      )}>
                        {b.trades > 0 ? fmtPnl(b.total_pnl) : '—'}
                      </td>
                      <td className="py-1 pl-3">
                        {b.trades > 0
                          ? <PnlBar value={b.avg_pnl} maxAbs={maxAbsPnl} />
                          : <div className="h-2 w-full bg-gray-800/40 rounded" />
                        }
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Monotonicity violations */}
          {data.monotonicity_violations.length > 0 && (
            <div className="space-y-0.5">
              <p className="text-[10px] font-mono text-amber-400 font-semibold">Monotonicity violations:</p>
              {data.monotonicity_violations.map((v, i) => (
                <p key={i} className="text-[10px] font-mono text-amber-400/80 pl-2">• {v}</p>
              ))}
            </div>
          )}

          {/* Coverage + metadata */}
          <div className="flex items-center justify-between text-[10px] font-mono text-gray-600 pt-1 border-t border-[var(--color-dark-border)]">
            <span>
              {data.total_trades_with_score} scored trades
              {data.data_window_days > 0 ? ` (last ${data.data_window_days}d)` : ' (all-time)'}
            </span>
            <span className={cn(
              data.coverage_pct >= 50 ? 'text-gray-500' : 'text-amber-400',
            )}>
              {data.coverage_pct.toFixed(0)}% coverage
              {data.coverage_pct < 50 && ' ⚠ low'}
            </span>
          </div>
        </>
      )}
    </div>
  );
};
