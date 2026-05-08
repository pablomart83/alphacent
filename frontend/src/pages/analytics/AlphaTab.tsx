/**
 * AlphaTab — Alpha Generation section for the Analytics page.
 *
 * Layout (top to bottom):
 *   1. Data confidence banner — obs count, IR reliability, time-to-reliable
 *   2. Context cards — annualized alpha, beta-adjusted benchmark, industry comparison
 *   3. Core metric tiles — IR, Beta, Total Alpha, Alpha (30d)
 *   4. Cumulative alpha chart
 *   5. Rolling alpha chart
 *   6. Alpha by period table
 *   7. Methodology note
 */

import { type FC, useMemo } from 'react';
import { cn } from '../../lib/utils';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { TvChart, type TvSeriesConfig } from '../../components/charts/TvChart';
import { ConvictionCalibrationCard } from './ConvictionCalibrationCard';

// ── Types ─────────────────────────────────────────────────────────────────────

interface AlphaDailyPoint {
  date: string;
  portfolio_return: number;
  spy_return: number;
  excess_return: number;
  cumulative_alpha: number;
  rolling_30d_alpha: number | null;
  rolling_90d_alpha: number | null;
  // realized series
  realized_return_pct: number | null;
  spy_return_cumulative: number | null;
  cumulative_realized_alpha: number | null;
}

interface AlphaPeriodRow {
  period: string;
  portfolio_return: number;
  spy_return: number;
  alpha: number;
  capm_alpha: number;
  beta: number;
}

interface AlphaAnnotation {
  date: string;
  label: string;
  description: string;
}

interface AlphaData {
  daily_series: AlphaDailyPoint[];
  information_ratio: number;
  beta: number;
  total_alpha: number;
  alpha_30d: number;
  alpha_by_period: AlphaPeriodRow[];
  annotations: AlphaAnnotation[];
  data_start: string;
  data_points: number;
  // context fields
  annualized_alpha: number;
  annualized_alpha_1w: number;
  ir_confidence: 'low' | 'building' | 'reliable';
  obs_needed: number;
  beta_equivalent_return: number;
  beta_gap: number;
  spy_inception_return: number;
  portfolio_inception_return: number;
  // realized alpha
  realized_alpha_inception: number;
  realized_alpha_30d: number | null;
}

interface AlphaTabProps {
  data: AlphaData | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number, decimals = 2, sign = false): string {
  const s = n.toFixed(decimals);
  return sign && n > 0 ? `+${s}` : s;
}
function fmtPct(n: number, sign = false): string {
  return fmt(n, 2, sign) + '%';
}

// ── Metric Tile ───────────────────────────────────────────────────────────────

const MetricTile: FC<{
  label: string;
  value: string;
  sub?: string;
  positive?: boolean | null;
  warn?: boolean;
}> = ({ label, value, sub, positive, warn }) => (
  <div className={cn(
    'rounded-md border bg-[var(--color-dark-bg)] p-3 space-y-1',
    warn ? 'border-amber-500/40' : 'border-[var(--color-dark-border)]',
  )}>
    <p className="text-xs text-gray-500 font-mono tracking-wide">{label}</p>
    <p className={cn(
      'text-xl font-bold font-mono',
      positive === true && 'text-accent-green',
      positive === false && 'text-accent-red',
      positive === null && 'text-gray-200',
      warn && positive === null && 'text-amber-400',
    )}>
      {value}
    </p>
    {sub && <p className="text-xs text-gray-500 font-mono leading-tight">{sub}</p>}
  </div>
);

// ── Data Confidence Banner ────────────────────────────────────────────────────

const IR_CONFIDENCE_CONFIG = {
  low:      { color: 'text-amber-400', bar: 'bg-amber-500', label: 'Low confidence', desc: 'IR is unreliable below 30 obs. A single bad week dominates the signal.' },
  building: { color: 'text-blue-400',  bar: 'bg-blue-500',  label: 'Building',       desc: 'IR is stabilising. Meaningful at 90+ obs; reliable at 252 (1 year).' },
  reliable: { color: 'text-accent-green', bar: 'bg-accent-green', label: 'Reliable', desc: 'Sufficient observations for statistically meaningful IR.' },
};

const ConfidenceBanner: FC<{
  obs: number;
  needed: number;
  confidence: 'low' | 'building' | 'reliable';
  dataStart: string;
}> = ({ obs, needed, confidence, dataStart }) => {
  const cfg = IR_CONFIDENCE_CONFIG[confidence];
  const pct = Math.min(100, Math.round((obs / needed) * 100));
  const daysLeft = needed - obs;

  return (
    <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono font-semibold text-gray-300">Data Confidence</span>
          <span className={cn('text-xs font-mono font-semibold', cfg.color)}>{cfg.label}</span>
        </div>
        <span className="text-xs font-mono text-gray-500">{obs} / {needed} obs · since {dataStart}</span>
      </div>
      <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden mb-2">
        <div className={cn('h-full rounded-full transition-all', cfg.bar)} style={{ width: `${pct}%` }} />
      </div>
      <p className="text-xs font-mono text-gray-500">
        {cfg.desc}
        {confidence !== 'reliable' && daysLeft > 0 && (
          <span className="text-gray-400"> ~{daysLeft} more trading days to reliable IR.</span>
        )}
      </p>
    </div>
  );
};

// ── Context Cards ─────────────────────────────────────────────────────────────

const ContextCards: FC<{
  data: AlphaData;
}> = ({ data }) => {
  const {
    annualized_alpha,
    annualized_alpha_1w,
    ir_confidence,
    data_points,
    beta,
    beta_equivalent_return,
    beta_gap,
    spy_inception_return,
    portfolio_inception_return,
    information_ratio,
  } = data;

  // Industry IR benchmarks
  const irTier =
    information_ratio >= 1.0 ? { label: 'Top-quartile (IR > 1.0)', color: 'text-accent-green' } :
    information_ratio >= 0.5 ? { label: 'Good (IR > 0.5)', color: 'text-blue-400' } :
    information_ratio >= 0.0 ? { label: 'Marginal (IR 0–0.5)', color: 'text-amber-400' } :
    { label: 'Below benchmark', color: 'text-accent-red' };

  // Annualized alpha noise warning
  const annualNoisy = data_points < 60;
  const annualWarn = data_points < 30;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">

      {/* ── Card 1: Annualised alpha ── */}
      <div className={cn(
        'rounded-md border p-3 space-y-2',
        annualWarn ? 'border-amber-500/40 bg-[var(--color-dark-bg)]' : 'border-[var(--color-dark-border)] bg-[var(--color-dark-bg)]',
      )}>
        <p className="text-xs font-mono text-gray-500 tracking-wide">Annualised Alpha (est.)</p>
        <div className="flex items-baseline gap-2">
          <span className={cn(
            'text-2xl font-bold font-mono',
            annualized_alpha >= 0 ? 'text-accent-green' : 'text-accent-red',
          )}>
            {fmtPct(annualized_alpha, true)}
          </span>
          <span className="text-xs font-mono text-gray-500">/ year</span>
        </div>
        {annualNoisy && (
          <p className="text-xs font-mono text-amber-400">
            ⚠ Estimated from {data_points} obs. Needs 252 for reliability.
          </p>
        )}
        <div className="pt-1 border-t border-[var(--color-dark-border)] space-y-0.5">
          <p className="text-xs font-mono text-gray-500">1W annualised: <span className={cn('font-semibold', annualized_alpha_1w >= 0 ? 'text-accent-green' : 'text-accent-red')}>{fmtPct(annualized_alpha_1w, true)}</span> <span className="text-amber-400">(noise — 5d window)</span></p>
          <p className="text-xs font-mono text-gray-500">Industry top-quartile: 3–8% / year</p>
          <p className="text-xs font-mono text-gray-500">Renaissance Medallion: ~66% / year</p>
        </div>
      </div>

      {/* ── Card 2: Beta-adjusted benchmark ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3 space-y-2">
        <p className="text-xs font-mono text-gray-500 tracking-wide">Beta-Adjusted Benchmark</p>
        <div className="space-y-1.5 text-xs font-mono">
          <div className="flex justify-between">
            <span className="text-gray-400">SPY return (inception)</span>
            <span className={spy_inception_return >= 0 ? 'text-accent-green' : 'text-accent-red'}>
              {fmtPct(spy_inception_return, true)}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">β × SPY (passive equiv.)</span>
            <span className="text-gray-300">{fmt(beta, 3)} × {fmtPct(spy_inception_return, true)} = <span className={beta_equivalent_return >= 0 ? 'text-accent-green' : 'text-accent-red'}>{fmtPct(beta_equivalent_return, true)}</span></span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-400">Portfolio return</span>
            <span className={portfolio_inception_return >= 0 ? 'text-accent-green' : 'text-accent-red'}>
              {fmtPct(portfolio_inception_return, true)}
            </span>
          </div>
          <div className="flex justify-between pt-1 border-t border-[var(--color-dark-border)]">
            <span className="text-gray-300 font-semibold">Gap vs passive</span>
            <span className={cn('font-bold', beta_gap >= 0 ? 'text-accent-green' : 'text-accent-red')}>
              {fmtPct(beta_gap, true)}
            </span>
          </div>
        </div>
        <p className="text-xs font-mono text-gray-500 pt-1">
          {beta_gap >= 0
            ? '✓ Outperforming beta-equivalent passive portfolio'
            : `Underperforming beta-equivalent passive by ${fmtPct(Math.abs(beta_gap))}. This is the real gap to close.`}
        </p>
      </div>

      {/* ── Card 3: Industry comparison ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3 space-y-2">
        <p className="text-xs font-mono text-gray-500 tracking-wide">IR vs Industry (annualised)</p>
        <div className="space-y-1.5">
          {[
            { label: 'Renaissance Medallion', range: '> 2.0', threshold: 2.0, note: 'closed fund, outlier' },
            { label: 'Citadel / Millennium',  range: '0.8–1.5', threshold: 0.8 },
            { label: 'AQR / Man AHL',         range: '0.4–0.8', threshold: 0.4 },
            { label: 'Median hedge fund',     range: '~0.0',    threshold: 0.0 },
          ].map((tier) => {
            const isCurrentTier =
              tier.label === 'Renaissance Medallion' ? information_ratio >= 2.0 :
              tier.label === 'Citadel / Millennium'  ? information_ratio >= 0.8 && information_ratio < 2.0 :
              tier.label === 'AQR / Man AHL'         ? information_ratio >= 0.4 && information_ratio < 0.8 :
              information_ratio >= 0.0 && information_ratio < 0.4;
            return (
              <div key={tier.label} className={cn(
                'flex items-center justify-between text-xs font-mono px-1.5 py-1 rounded',
                isCurrentTier && ir_confidence !== 'low' ? 'bg-blue-500/10 border border-blue-500/30' : '',
              )}>
                <span className={cn('text-gray-400', isCurrentTier && ir_confidence !== 'low' && 'text-gray-200')}>
                  {tier.label}
                  {tier.note && <span className="text-gray-600 ml-1">({tier.note})</span>}
                </span>
                <span className="text-gray-300">IR {tier.range}</span>
              </div>
            );
          })}
        </div>
        <div className="pt-1 border-t border-[var(--color-dark-border)]">
          <p className="text-xs font-mono">
            <span className="text-gray-500">Your IR: </span>
            <span className={cn('font-bold', irTier.color)}>{fmt(information_ratio, 3)}</span>
            <span className="text-gray-500 ml-1">— {irTier.label}</span>
          </p>
          {ir_confidence === 'low' && (
            <p className="text-xs font-mono text-amber-400 mt-0.5">
              ⚠ IR unreliable at {data_points} obs. Industry comparison valid at 252+.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Alpha by Period Table ─────────────────────────────────────────────────────

const PERIOD_LABELS: Record<string, string> = {
  '1W': '1 Week',
  '1M': '1 Month',
  '3M': '3 Months',
  '6M': '6 Months',
  inception: 'Since Inception',
};

const AlphaPeriodTable: FC<{ rows: AlphaPeriodRow[]; obsCount: number }> = ({ rows, obsCount }) => {
  if (rows.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 text-xs font-mono">
        Insufficient data for period breakdown
      </div>
    );
  }

  // Annualise a period return given approximate trading days
  const PERIOD_TRADING_DAYS: Record<string, number> = {
    '1W': 5, '1M': 21, '3M': 63, '6M': 126, inception: obsCount,
  };

  return (
    <div className="overflow-x-auto rounded-md border border-[var(--color-dark-border)]">
      <table className="w-full text-xs font-mono">
        <thead className="bg-[var(--color-dark-surface)] border-b border-[var(--color-dark-border)]">
          <tr>
            <th className="text-left p-2 text-gray-500">Period</th>
            <th className="text-right p-2 text-gray-500">Portfolio</th>
            <th className="text-right p-2 text-gray-500">SPY</th>
            <th className="text-right p-2 text-gray-500">Alpha</th>
            <th className="text-right p-2 text-gray-500">CAPM Alpha</th>
            <th className="text-right p-2 text-gray-500">Ann. Alpha</th>
            <th className="text-right p-2 text-gray-500">Beta</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const td = PERIOD_TRADING_DAYS[row.period] ?? obsCount;
            const annAlpha = td > 0 ? row.alpha * (252 / td) : null;
            const noisy = td < 30;
            return (
              <tr
                key={row.period}
                className="border-b border-[var(--color-dark-border)]/50 hover:bg-[var(--color-dark-surface)]"
              >
                <td className="p-2 font-semibold text-gray-300">
                  {PERIOD_LABELS[row.period] ?? row.period}
                </td>
                <td className={cn('p-2 text-right', row.portfolio_return >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                  {fmtPct(row.portfolio_return, true)}
                </td>
                <td className={cn('p-2 text-right', row.spy_return >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                  {fmtPct(row.spy_return, true)}
                </td>
                <td className={cn('p-2 text-right font-semibold', row.alpha >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                  {fmtPct(row.alpha, true)}
                </td>
                <td className={cn('p-2 text-right', row.capm_alpha >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                  {fmtPct(row.capm_alpha, true)}
                </td>
                <td className={cn('p-2 text-right', annAlpha !== null && annAlpha >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                  {annAlpha !== null ? (
                    <span className={noisy ? 'opacity-60' : ''} title={noisy ? 'Noisy — short window' : ''}>
                      {fmtPct(annAlpha, true)}{noisy && ' ⚠'}
                    </span>
                  ) : '—'}
                </td>
                <td className="p-2 text-right text-gray-300">{fmt(row.beta, 3)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

// ── Annotations Legend ────────────────────────────────────────────────────────

const AnnotationsLegend: FC<{ annotations: AlphaAnnotation[] }> = ({ annotations }) => {
  if (annotations.length === 0) return null;
  return (
    <div className="space-y-1">
      {annotations.map((a) => (
        <div key={a.date} className="flex items-start gap-2 text-xs font-mono text-gray-400">
          <span className="text-amber-400 shrink-0">▼ {a.date}</span>
          <span className="font-semibold text-gray-300 shrink-0">{a.label}:</span>
          <span className="text-gray-500">{a.description}</span>
        </div>
      ))}
    </div>
  );
};

// ── Main Component ────────────────────────────────────────────────────────────

export const AlphaTab: FC<AlphaTabProps> = ({ data, loading, error, onRetry }) => {
  const cumulativeAlphaSeries = useMemo<TvSeriesConfig[]>(() => {
    if (!data?.daily_series?.length) return [];
    return [{
      id: 'cumulative_alpha',
      type: 'baseline' as const,
      data: data.daily_series.map((p) => ({ time: p.date, value: p.cumulative_alpha })),
      baseValue: 0,
      topFillColor1: 'rgba(16, 185, 129, 0.25)',
      topFillColor2: 'rgba(16, 185, 129, 0.05)',
      bottomFillColor1: 'rgba(239, 68, 68, 0.05)',
      bottomFillColor2: 'rgba(239, 68, 68, 0.20)',
      topLineColor: '#10b981',
      bottomLineColor: '#ef4444',
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: false,
    }];
  }, [data]);

  const rollingAlphaSeries = useMemo<TvSeriesConfig[]>(() => {
    if (!data?.daily_series?.length) return [];
    const series: TvSeriesConfig[] = [];
    const data30 = data.daily_series.filter((p) => p.rolling_30d_alpha !== null)
      .map((p) => ({ time: p.date, value: p.rolling_30d_alpha as number }));
    if (data30.length > 0) series.push({ id: 'rolling_30d', type: 'line' as const, data: data30, color: '#3b82f6', lineWidth: 2, lastValueVisible: true, priceLineVisible: false });
    const data90 = data.daily_series.filter((p) => p.rolling_90d_alpha !== null)
      .map((p) => ({ time: p.date, value: p.rolling_90d_alpha as number }));
    if (data90.length > 0) series.push({ id: 'rolling_90d', type: 'line' as const, data: data90, color: '#8b5cf6', lineWidth: 2, lastValueVisible: true, priceLineVisible: false });
    series.push({ id: 'zero_line', type: 'line' as const, data: data.daily_series.map((p) => ({ time: p.date, value: 0 })), color: '#374151', lineWidth: 1, dashed: true, lastValueVisible: false, priceLineVisible: false });
    return series;
  }, [data]);

  // Realized alpha chart: realized_return_pct vs spy_return_cumulative vs cumulative_realized_alpha
  const realizedAlphaSeries = useMemo<TvSeriesConfig[]>(() => {
    if (!data?.daily_series?.length) return [];
    const series: TvSeriesConfig[] = [];

    const realizedData = data.daily_series
      .filter((p) => p.realized_return_pct !== null)
      .map((p) => ({ time: p.date, value: p.realized_return_pct as number }));
    if (realizedData.length > 0) {
      series.push({
        id: 'realized_return',
        type: 'line' as const,
        data: realizedData,
        color: '#22c55e',
        lineWidth: 2,
        lastValueVisible: true,
        priceLineVisible: false,
      });
    }

    const spyCumData = data.daily_series
      .filter((p) => p.spy_return_cumulative !== null)
      .map((p) => ({ time: p.date, value: p.spy_return_cumulative as number }));
    if (spyCumData.length > 0) {
      series.push({
        id: 'spy_cumulative',
        type: 'line' as const,
        data: spyCumData,
        color: '#6b7280',
        lineWidth: 1,
        dashed: true,
        lastValueVisible: true,
        priceLineVisible: false,
      });
    }

    // Zero baseline
    series.push({
      id: 'zero_realized',
      type: 'line' as const,
      data: data.daily_series.map((p) => ({ time: p.date, value: 0 })),
      color: '#374151',
      lineWidth: 1,
      dashed: true,
      lastValueVisible: false,
      priceLineVisible: false,
    });

    return series;
  }, [data]);

  // Cumulative realized alpha (realized_return_pct - spy_return_cumulative)
  const cumulativeRealizedAlphaSeries = useMemo<TvSeriesConfig[]>(() => {
    if (!data?.daily_series?.length) return [];
    const pts = data.daily_series
      .filter((p) => p.cumulative_realized_alpha !== null)
      .map((p) => ({ time: p.date, value: p.cumulative_realized_alpha as number }));
    if (pts.length < 2) return [];
    return [{
      id: 'cumulative_realized_alpha',
      type: 'baseline' as const,
      data: pts,
      baseValue: 0,
      topFillColor1: 'rgba(34, 197, 94, 0.25)',
      topFillColor2: 'rgba(34, 197, 94, 0.05)',
      bottomFillColor1: 'rgba(239, 68, 68, 0.05)',
      bottomFillColor2: 'rgba(239, 68, 68, 0.20)',
      topLineColor: '#22c55e',
      bottomLineColor: '#ef4444',
      lineWidth: 2,
      lastValueVisible: true,
      priceLineVisible: false,
    }];
  }, [data]);

  if (loading) return <div className="flex items-center justify-center h-48 text-sm text-gray-500 font-mono">Computing alpha metrics…</div>;
  if (error) return (
    <div className="space-y-2 p-4">
      <p className="text-sm text-accent-red font-mono">{error}</p>
      <button onClick={onRetry} className="text-xs text-gray-400 hover:text-gray-200 underline font-mono">Retry</button>
    </div>
  );
  if (!data || data.data_points === 0) return (
    <div className="flex items-center justify-center h-48 text-sm text-gray-500 font-mono">
      No alpha data available yet — need at least 2 daily equity snapshots with SPY overlap.
    </div>
  );

  const { daily_series, information_ratio, beta, total_alpha, alpha_30d, alpha_by_period, annotations, data_start, data_points, ir_confidence, obs_needed } = data;
  const irLabel = information_ratio >= 1.0 ? 'excellent' : information_ratio >= 0.5 ? 'good' : information_ratio >= 0.0 ? 'marginal' : 'negative';
  const betaLabel = beta < 0.8 ? 'low market sensitivity' : beta < 1.2 ? 'market-like' : 'high market sensitivity';
  const has30d = daily_series.some((p) => p.rolling_30d_alpha !== null);

  return (
    <div className="space-y-4">

      {/* ── 1. Data confidence banner ── */}
      <ConfidenceBanner
        obs={data_points}
        needed={obs_needed}
        confidence={ir_confidence}
        dataStart={data_start}
      />

      {/* ── 2. Context cards ── */}
      <ContextCards data={data} />

      {/* ── 3. Core metric tiles ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricTile
          label="Information Ratio"
          value={fmt(information_ratio, 3, true)}
          sub={`${irLabel} · IR > 0.5 = good · IR > 1.0 = top-quartile`}
          positive={information_ratio >= 0.5 ? true : information_ratio >= 0 ? null : false}
          warn={ir_confidence === 'low'}
        />
        <MetricTile
          label="Beta (vs SPY)"
          value={fmt(beta, 3)}
          sub={betaLabel}
          positive={beta < 1.0 ? true : null}
        />
        <MetricTile
          label="Total Alpha (inception)"
          value={fmtPct(total_alpha, true)}
          sub={`${data_points} obs since ${data_start}`}
          positive={total_alpha >= 0 ? true : false}
        />
        <MetricTile
          label="Alpha (30d rolling)"
          value={fmtPct(alpha_30d, true)}
          sub="sum of last 30 daily excess returns"
          positive={alpha_30d >= 0 ? true : false}
        />
      </div>

      {/* ── 3b. Conviction calibration ── */}
      <ConvictionCalibrationCard />

      {/* ── 4. Cumulative alpha chart ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Cumulative Alpha</SectionLabel>
          <span className="text-xs text-gray-500 font-mono">portfolio − SPY − risk-free · rebased to 0 at inception</span>
        </div>
        <TvChart series={cumulativeAlphaSeries} height={260} showTimeScale showPriceScale autoResize />
        {annotations.length > 0 && (
          <div className="mt-3 pt-2 border-t border-[var(--color-dark-border)]">
            <p className="text-xs text-gray-500 font-mono mb-1">System changes</p>
            <AnnotationsLegend annotations={annotations} />
          </div>
        )}
      </div>

      {/* ── 5. Rolling alpha chart ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Rolling Alpha</SectionLabel>
          <div className="flex items-center gap-4 text-xs font-mono text-gray-500">
            <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-blue-500 inline-block rounded" />30d</span>
            <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-purple-500 inline-block rounded" />90d</span>
          </div>
        </div>
        {has30d ? (
          <TvChart series={rollingAlphaSeries} height={220} showTimeScale showPriceScale autoResize />
        ) : (
          <div className="flex items-center justify-center h-32 text-xs text-gray-500 font-mono">
            Need 30+ days of data for rolling alpha
          </div>
        )}
      </div>

      {/* ── 6. Alpha by period table ── */}
      <div>
        <SectionLabel>Alpha by Period</SectionLabel>
        <AlphaPeriodTable rows={alpha_by_period} obsCount={data_points} />
      </div>

      {/* ── 6b. Realized alpha section ── */}
      {cumulativeRealizedAlphaSeries.length > 0 && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <MetricTile
              label="Realized Alpha (inception)"
              value={fmtPct(data.realized_alpha_inception, true)}
              sub="locked-in P&L / initial equity − SPY return"
              positive={data.realized_alpha_inception >= 0 ? true : false}
            />
            <MetricTile
              label="Realized Alpha (30d)"
              value={data.realized_alpha_30d !== null ? fmtPct(data.realized_alpha_30d, true) : 'n/a'}
              sub="30d change in realized return vs SPY"
              positive={data.realized_alpha_30d !== null ? (data.realized_alpha_30d >= 0 ? true : false) : null}
            />
          </div>

          {/* Realized return vs SPY */}
          <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
            <div className="flex items-center justify-between mb-2">
              <SectionLabel>Realized Return vs SPY</SectionLabel>
              <div className="flex items-center gap-4 text-xs font-mono text-gray-500">
                <span className="flex items-center gap-1">
                  <span className="w-4 h-0.5 bg-accent-green inline-block rounded" />
                  Realized P&L %
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-4 inline-block" style={{ borderTop: '1.5px dashed #6b7280' }} />
                  SPY %
                </span>
              </div>
            </div>
            <TvChart series={realizedAlphaSeries} height={200} showTimeScale showPriceScale autoResize />
            <p className="text-[10px] font-mono text-gray-600 mt-1">
              Both as % of initial equity ({data.data_start}). Green above grey = positive realized alpha.
            </p>
          </div>

          {/* Cumulative realized alpha */}
          <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
            <div className="flex items-center justify-between mb-2">
              <SectionLabel>Cumulative Realized Alpha</SectionLabel>
              <span className="text-xs text-gray-500 font-mono">
                realized return − SPY · only moves when trades close
              </span>
            </div>
            <TvChart series={cumulativeRealizedAlphaSeries} height={200} showTimeScale showPriceScale autoResize />
            <p className="text-[10px] font-mono text-gray-600 mt-1">
              Isolates decision quality from mark-to-market noise. Unlike total equity alpha, this is unaffected by open position fluctuations.
            </p>
          </div>
        </div>
      )}

      {/* ── 7. Methodology note ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3 text-xs font-mono text-gray-500 space-y-1">
        <p className="text-gray-400 font-semibold">Methodology</p>
        <p><span className="text-gray-300">Simple alpha</span> = portfolio return − SPY return</p>
        <p><span className="text-gray-300">CAPM alpha</span> = portfolio return − risk-free − β × (SPY return − risk-free)</p>
        <p><span className="text-gray-300">Annualised alpha</span> = period alpha × (252 / trading days in period) — noisy below 60 obs</p>
        <p><span className="text-gray-300">IR</span> = mean(daily excess returns) / std(daily excess returns) × √252 — reliable at 252+ obs</p>
        <p><span className="text-gray-300">Beta-equivalent passive</span> = β × SPY return — the hurdle a passive β-matched portfolio clears</p>
        <p><span className="text-gray-300">Realized alpha</span> = cumulative realized P&L / initial equity − SPY return over same period</p>
        <p><span className="text-gray-300">Risk-free rate</span>: 4.5% annualised (Fed funds proxy) = 0.0179bp/day</p>
      </div>
    </div>
  );
};
