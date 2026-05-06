/**
 * AlphaTab — Alpha Generation section for the Analytics page.
 *
 * Displays hedge-fund-style alpha metrics:
 *   - Cumulative alpha chart (portfolio return minus SPY, rebased to 0)
 *   - Rolling 30d / 90d alpha chart
 *   - Metric tiles: IR, Beta, Total Alpha, Alpha (30d)
 *   - Alpha by period table (1W / 1M / 3M / 6M / inception)
 *   - Annotation markers for major system changes
 *
 * Uses TvChart (lightweight-charts v5 wrapper) for all charting — never
 * calls the chart API directly.
 */

import { type FC, useMemo } from 'react';
import { cn } from '../../lib/utils';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { TvChart, type TvSeriesConfig } from '../../components/charts/TvChart';

// ── Types ─────────────────────────────────────────────────────────────────────

interface AlphaDailyPoint {
  date: string;
  portfolio_return: number;
  spy_return: number;
  excess_return: number;
  cumulative_alpha: number;
  rolling_30d_alpha: number | null;
  rolling_90d_alpha: number | null;
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
}> = ({ label, value, sub, positive }) => (
  <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3 space-y-1">
    <p className="text-xs text-gray-500 font-mono tracking-wide">{label}</p>
    <p
      className={cn(
        'text-xl font-bold font-mono',
        positive === true && 'text-accent-green',
        positive === false && 'text-accent-red',
        positive === null && 'text-gray-200',
      )}
    >
      {value}
    </p>
    {sub && <p className="text-xs text-gray-500 font-mono">{sub}</p>}
  </div>
);

// ── Alpha by Period Table ─────────────────────────────────────────────────────

const PERIOD_LABELS: Record<string, string> = {
  '1W': '1 Week',
  '1M': '1 Month',
  '3M': '3 Months',
  '6M': '6 Months',
  inception: 'Since Inception',
};

const AlphaPeriodTable: FC<{ rows: AlphaPeriodRow[] }> = ({ rows }) => {
  if (rows.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 text-xs font-mono">
        Insufficient data for period breakdown
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border border-[var(--color-dark-border)]">
      <table className="w-full text-xs font-mono">
        <thead className="bg-[var(--color-dark-surface)] border-b border-[var(--color-dark-border)]">
          <tr>
            <th className="text-left p-2 text-gray-500">Period</th>
            <th className="text-right p-2 text-gray-500">Portfolio</th>
            <th className="text-right p-2 text-gray-500">SPY</th>
            <th className="text-right p-2 text-gray-500">Alpha (simple)</th>
            <th className="text-right p-2 text-gray-500">CAPM Alpha</th>
            <th className="text-right p-2 text-gray-500">Beta</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.period}
              className="border-b border-[var(--color-dark-border)]/50 hover:bg-[var(--color-dark-surface)]"
            >
              <td className="p-2 font-semibold text-gray-300">
                {PERIOD_LABELS[row.period] ?? row.period}
              </td>
              <td
                className={cn(
                  'p-2 text-right',
                  row.portfolio_return >= 0 ? 'text-accent-green' : 'text-accent-red',
                )}
              >
                {fmtPct(row.portfolio_return, true)}
              </td>
              <td
                className={cn(
                  'p-2 text-right',
                  row.spy_return >= 0 ? 'text-accent-green' : 'text-accent-red',
                )}
              >
                {fmtPct(row.spy_return, true)}
              </td>
              <td
                className={cn(
                  'p-2 text-right font-semibold',
                  row.alpha >= 0 ? 'text-accent-green' : 'text-accent-red',
                )}
              >
                {fmtPct(row.alpha, true)}
              </td>
              <td
                className={cn(
                  'p-2 text-right',
                  row.capm_alpha >= 0 ? 'text-accent-green' : 'text-accent-red',
                )}
              >
                {fmtPct(row.capm_alpha, true)}
              </td>
              <td className="p-2 text-right text-gray-300">{fmt(row.beta, 3)}</td>
            </tr>
          ))}
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
        <div
          key={a.date}
          className="flex items-start gap-2 text-xs font-mono text-gray-400"
        >
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
  // ── Build TvChart series configs from data ────────────────────────────────
  const cumulativeAlphaSeries = useMemo<TvSeriesConfig[]>(() => {
    if (!data?.daily_series?.length) return [];
    return [
      {
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
      },
    ];
  }, [data]);

  const rollingAlphaSeries = useMemo<TvSeriesConfig[]>(() => {
    if (!data?.daily_series?.length) return [];
    const series: TvSeriesConfig[] = [];

    const data30 = data.daily_series
      .filter((p) => p.rolling_30d_alpha !== null)
      .map((p) => ({ time: p.date, value: p.rolling_30d_alpha as number }));
    if (data30.length > 0) {
      series.push({
        id: 'rolling_30d',
        type: 'line' as const,
        data: data30,
        color: '#3b82f6',
        lineWidth: 2,
        lastValueVisible: true,
        priceLineVisible: false,
      });
    }

    const data90 = data.daily_series
      .filter((p) => p.rolling_90d_alpha !== null)
      .map((p) => ({ time: p.date, value: p.rolling_90d_alpha as number }));
    if (data90.length > 0) {
      series.push({
        id: 'rolling_90d',
        type: 'line' as const,
        data: data90,
        color: '#8b5cf6',
        lineWidth: 2,
        lastValueVisible: true,
        priceLineVisible: false,
      });
    }

    // Zero baseline
    series.push({
      id: 'zero_line',
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

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-gray-500 font-mono">
        Computing alpha metrics…
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-2 p-4">
        <p className="text-sm text-accent-red font-mono">{error}</p>
        <button
          onClick={onRetry}
          className="text-xs text-gray-400 hover:text-gray-200 underline font-mono"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || data.data_points === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-gray-500 font-mono">
        No alpha data available yet — need at least 2 daily equity snapshots with SPY overlap.
      </div>
    );
  }

  const {
    daily_series,
    information_ratio,
    beta,
    total_alpha,
    alpha_30d,
    alpha_by_period,
    annotations,
    data_start,
    data_points,
  } = data;

  const irLabel =
    information_ratio >= 1.0
      ? 'excellent'
      : information_ratio >= 0.5
      ? 'good'
      : information_ratio >= 0.0
      ? 'marginal'
      : 'negative';

  const betaLabel =
    beta < 0.8
      ? 'low market sensitivity'
      : beta < 1.2
      ? 'market-like'
      : 'high market sensitivity';

  const has30d = daily_series.some((p) => p.rolling_30d_alpha !== null);

  return (
    <div className="space-y-4">
      {/* ── Metric tiles ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricTile
          label="Information Ratio"
          value={fmt(information_ratio, 3, true)}
          sub={`${irLabel} · IR > 0.5 = good`}
          positive={information_ratio >= 0.5 ? true : information_ratio >= 0 ? null : false}
        />
        <MetricTile
          label="Beta (vs SPY)"
          value={fmt(beta, 3)}
          sub={betaLabel}
          positive={beta < 1.0 ? true : null}
        />
        <MetricTile
          label="Total Alpha"
          value={fmtPct(total_alpha, true)}
          sub={`since ${data_start} · ${data_points}d`}
          positive={total_alpha >= 0 ? true : false}
        />
        <MetricTile
          label="Alpha (30d)"
          value={fmtPct(alpha_30d, true)}
          sub="rolling 30-day excess return"
          positive={alpha_30d >= 0 ? true : false}
        />
      </div>

      {/* ── Cumulative alpha chart ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Cumulative Alpha</SectionLabel>
          <span className="text-xs text-gray-500 font-mono">
            portfolio − SPY − risk-free · rebased to 0 at inception
          </span>
        </div>
        <TvChart
          series={cumulativeAlphaSeries}
          height={260}
          showTimeScale
          showPriceScale
          autoResize
        />
        {annotations.length > 0 && (
          <div className="mt-3 pt-2 border-t border-[var(--color-dark-border)]">
            <p className="text-xs text-gray-500 font-mono mb-1">System changes</p>
            <AnnotationsLegend annotations={annotations} />
          </div>
        )}
      </div>

      {/* ── Rolling alpha chart ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3">
        <div className="flex items-center justify-between mb-2">
          <SectionLabel>Rolling Alpha</SectionLabel>
          <div className="flex items-center gap-4 text-xs font-mono text-gray-500">
            <span className="flex items-center gap-1">
              <span className="w-4 h-0.5 bg-blue-500 inline-block rounded" />
              30d
            </span>
            <span className="flex items-center gap-1">
              <span className="w-4 h-0.5 bg-purple-500 inline-block rounded" />
              90d
            </span>
          </div>
        </div>
        {has30d ? (
          <TvChart
            series={rollingAlphaSeries}
            height={220}
            showTimeScale
            showPriceScale
            autoResize
          />
        ) : (
          <div className="flex items-center justify-center h-32 text-xs text-gray-500 font-mono">
            Need 30+ days of data for rolling alpha
          </div>
        )}
      </div>

      {/* ── Alpha by period table ── */}
      <div>
        <SectionLabel>Alpha by Period</SectionLabel>
        <AlphaPeriodTable rows={alpha_by_period} />
      </div>

      {/* ── Methodology note ── */}
      <div className="rounded-md border border-[var(--color-dark-border)] bg-[var(--color-dark-bg)] p-3 text-xs font-mono text-gray-500 space-y-1">
        <p className="text-gray-400 font-semibold">Alpha decomposition</p>
        <p>
          <span className="text-gray-300">Simple alpha</span> = portfolio return − SPY return
        </p>
        <p>
          <span className="text-gray-300">CAPM alpha</span> = portfolio return − risk-free − β × (SPY return − risk-free)
        </p>
        <p>
          <span className="text-gray-300">Information Ratio</span> = mean(daily excess returns) / std(daily excess returns) × √252
        </p>
        <p>
          <span className="text-gray-300">Risk-free rate</span>: 4.5% annualized (Fed funds proxy) = 0.0179bp/day
        </p>
        <p>
          <span className="text-gray-300">Beta</span>: cov(portfolio, SPY) / var(SPY) over full period
        </p>
      </div>
    </div>
  );
};
