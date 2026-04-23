import { type FC, useState, useEffect, useMemo } from 'react';
import { apiClient } from '../../services/api';
import { cn, formatCurrency } from '../../lib/utils';
import { SVGBarChart } from '../../components/charts/SVGBarChart';
import { EquityCurveChart } from '../../components/charts/EquityCurveChart';
import { buildEquityCurveSeries } from '../../lib/chart-utils';
import { UnderwaterPlot } from '../../components/charts/UnderwaterPlot';

interface PerformanceTabProps {
  performanceMetrics: any;
  cioDashboard: any;
  perfStats: any;
  regimeAnalysis: any;
  period: string;
  setPeriod: (p: any) => void;
  equityInterval: string;
  setEquityInterval: (iv: any) => void;
}

const StatRow: FC<{ label: string; value: React.ReactNode; valueClass?: string }> = ({ label, value, valueClass }) => (
  <div className="flex justify-between items-center py-[3px]">
    <span className="text-gray-500 text-xs">{label}</span>
    <span className={cn('text-xs font-mono font-semibold', valueClass)}>{value}</span>
  </div>
);

const KpiTile: FC<{ label: string; value: string; sub?: string; color: string; border?: string }> = ({ label, value, sub, color, border }) => (
  <div className={cn('bg-[var(--color-dark-surface)] px-3 py-2.5 flex flex-col gap-0.5', border && `border-l-2 ${border}`)}>
    <span className="text-[10px] text-gray-500 tracking-widest uppercase">{label}</span>
    <span className={cn('text-sm font-mono font-bold leading-tight', color)}>{value}</span>
    {sub && <span className="text-[10px] text-gray-600 font-mono">{sub}</span>}
  </div>
);

export const PerformanceTab: FC<PerformanceTabProps> = ({
  performanceMetrics, cioDashboard, perfStats, regimeAnalysis,
  period, setPeriod, equityInterval, setEquityInterval,
}) => {
  const [showDailyPnl, setShowDailyPnl] = useState(false);
  const [spyData, setSpyData] = useState<Array<{ date: string; close: number }> | undefined>(undefined);
  const pm = performanceMetrics;

  useEffect(() => {
    apiClient.getSpyBenchmark(period).then((spy) => {
      setSpyData(spy && spy.length > 0 ? spy : undefined);
    }).catch(() => setSpyData(undefined));
  }, [period]);

  // Pre-build equity curve series — pure data transform, no rendering
  const equityCurveSeries = useMemo(() => {
    const rawCurve = pm?.equity_curve || perfStats?.equity_curve || [];
    if (!rawCurve.length) return null;
    const equityData = rawCurve.map((d: any) => ({
      date: typeof d.date === 'string' ? d.date : (d.timestamp ?? ''),
      equity: d.portfolio ?? d.value ?? 0,
    }));
    return buildEquityCurveSeries(equityData, spyData, period);
  }, [pm?.equity_curve, perfStats?.equity_curve, spyData, period, equityInterval]);
  const cio = cioDashboard;

  const kpiRow1 = [
    { label: 'Total Return', value: pm ? `${(pm.total_return ?? 0) >= 0 ? '+' : ''}${(pm.total_return ?? 0).toFixed(2)}%` : '—', color: (pm?.total_return ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red', border: (pm?.total_return ?? 0) >= 0 ? 'border-accent-green' : 'border-accent-red' },
    { label: 'CAGR', value: cio ? `${cio.cagr >= 0 ? '+' : ''}${cio.cagr.toFixed(1)}%` : '—', color: (cio?.cagr ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red', border: (cio?.cagr ?? 0) >= 0 ? 'border-accent-green' : 'border-accent-red' },
    {
      label: 'Sharpe Ratio',
      value: pm ? (pm.daily_returns_count ?? 0) < 30 ? `${(pm.sharpe_ratio ?? 0).toFixed(2)}*` : (pm.sharpe_ratio ?? 0).toFixed(2) : '—',
      sub: (pm?.daily_returns_count ?? 0) < 30 ? `*${pm?.daily_returns_count ?? 0}d data — needs 30+` : (pm?.sharpe_ratio ?? 0) >= 2 ? 'Excellent' : (pm?.sharpe_ratio ?? 0) >= 1 ? 'Good' : (pm?.sharpe_ratio ?? 0) >= 0.5 ? 'Acceptable' : 'Weak',
      color: (pm?.daily_returns_count ?? 0) < 30 ? 'text-yellow-400' : (pm?.sharpe_ratio ?? 0) >= 1 ? 'text-accent-green' : (pm?.sharpe_ratio ?? 0) >= 0.5 ? 'text-yellow-400' : 'text-accent-red',
      border: 'border-blue-500',
    },
    { label: 'Calmar', value: cio ? cio.calmar_ratio.toFixed(2) : '—', sub: 'Return / Max DD', color: (cio?.calmar_ratio ?? 0) >= 1 ? 'text-accent-green' : (cio?.calmar_ratio ?? 0) >= 0.5 ? 'text-yellow-400' : 'text-accent-red', border: 'border-blue-500' },
    { label: 'Info Ratio', value: cio ? cio.information_ratio.toFixed(2) : '—', sub: 'vs benchmark', color: (cio?.information_ratio ?? 0) >= 0.5 ? 'text-accent-green' : (cio?.information_ratio ?? 0) >= 0 ? 'text-yellow-400' : 'text-accent-red', border: 'border-purple-500' },
    { label: 'Max Drawdown', value: pm ? `${(pm.max_drawdown ?? 0).toFixed(2)}%` : '—', sub: cio ? `${cio.drawdown_duration_days}d duration` : undefined, color: 'text-accent-red', border: 'border-accent-red' },
    { label: 'Win Rate', value: pm ? `${(pm.win_rate ?? 0).toFixed(1)}%` : '—', sub: cio ? `${cio.winning_trades}W / ${cio.losing_trades}L` : undefined, color: (pm?.win_rate ?? 0) >= 50 ? 'text-accent-green' : 'text-yellow-400', border: (pm?.win_rate ?? 0) >= 50 ? 'border-accent-green' : 'border-yellow-500' },
    { label: 'Profit Factor', value: pm ? (pm.profit_factor ?? 0).toFixed(2) : '—', sub: (pm?.profit_factor ?? 0) >= 1.5 ? '✓ Target met' : 'Target: >1.5', color: (pm?.profit_factor ?? 0) >= 1.5 ? 'text-accent-green' : (pm?.profit_factor ?? 0) >= 1 ? 'text-yellow-400' : 'text-accent-red', border: (pm?.profit_factor ?? 0) >= 1.5 ? 'border-accent-green' : 'border-yellow-500' },
  ];

  return (
    <div className="space-y-2">
      {/* ROW 1: 8 KPI tiles */}
      <div className="grid grid-cols-8 gap-px bg-[var(--color-dark-border)] border border-[var(--color-dark-border)] rounded overflow-hidden">
        {kpiRow1.map((k) => (
          <KpiTile key={k.label} label={k.label} value={k.value} sub={k.sub} color={k.color} border={k.border} />
        ))}
      </div>

      {/* ROW 2: Equity Curve */}
      <div className="border border-[var(--color-dark-border)] rounded overflow-hidden bg-[var(--color-dark-surface)]">
        <div className="px-3 pt-2 pb-1 flex items-center justify-between border-b border-[var(--color-dark-border)]">
          <span className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold">Equity Curve</span>
          {cio && (
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className={cn(cio.total_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>Total P&L {cio.total_pnl >= 0 ? '+' : ''}{formatCurrency(cio.total_pnl)}</span>
              <span className="text-gray-600">|</span>
              <span className="text-gray-400">Realized <span className={cn(cio.total_realized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cio.total_realized_pnl)}</span></span>
              <span className="text-gray-400">Unrealized <span className={cn(cio.total_unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(cio.total_unrealized_pnl)}</span></span>
            </div>
          )}
        </div>
        <EquityCurveChart
          mainSeries={equityCurveSeries?.mainSeries ?? []}
          drawdownSeries={equityCurveSeries?.drawdownSeries ?? []}
          hasSpy={equityCurveSeries?.hasSpy ?? false}
          hasRealized={equityCurveSeries?.hasRealized ?? false}
          period={period} onPeriodChange={(p) => { setPeriod(p as any); }}
          interval={equityInterval} onIntervalChange={(iv: string) => setEquityInterval(iv as any)}
          height={280}
        />
      </div>

      {/* ROW 3: 3-column detail panels */}
      {cio && (
        <div className="grid grid-cols-3 gap-2">
          {/* COL 1: P&L + Drawdown + Streaks/Execution */}
          <div className="space-y-2">
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">P&L Breakdown</div>
              <StatRow label="Realized" value={formatCurrency(cio.total_realized_pnl)} valueClass={cio.total_realized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'} />
              <StatRow label="Unrealized" value={formatCurrency(cio.total_unrealized_pnl)} valueClass={cio.total_unrealized_pnl >= 0 ? 'text-accent-green' : 'text-accent-red'} />
              <div className="border-t border-[var(--color-dark-border)] mt-1 pt-1">
                <StatRow label="Total" value={formatCurrency(cio.total_pnl)} valueClass={cn('font-bold', cio.total_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')} />
              </div>
            </div>
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Drawdown</div>
              <StatRow label="Current DD" value={`${(cio.current_drawdown_pct ?? 0).toFixed(2)}%`} valueClass="text-accent-red" />
              <StatRow label="Max DD" value={`${(cio.max_drawdown_pct ?? pm?.max_drawdown ?? 0).toFixed(2)}%`} valueClass="text-accent-red" />
              <StatRow label="Duration" value={`${cio.drawdown_duration_days}d`} valueClass={cio.drawdown_duration_days <= 7 ? 'text-accent-green' : cio.drawdown_duration_days <= 30 ? 'text-yellow-400' : 'text-accent-red'} />
              {cio.last_equity_high_date && <StatRow label="Last high" value={cio.last_equity_high_date.slice(0, 10)} valueClass="text-gray-400" />}
            </div>
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Streaks & Execution</div>
              <StatRow label="Current streak" value={cio.current_streak > 0 ? `+${cio.current_streak}W` : cio.current_streak < 0 ? `${cio.current_streak}L` : '—'} valueClass={cio.current_streak >= 0 ? 'text-accent-green' : 'text-accent-red'} />
              <StatRow label="Best win streak" value={`${cio.longest_win_streak}W`} valueClass="text-accent-green" />
              <StatRow label="Worst loss streak" value={`${cio.longest_loss_streak}L`} valueClass="text-accent-red" />
              <div className="border-t border-[var(--color-dark-border)] mt-1 pt-1">
                <StatRow label="Entry slippage" value={`${cio.avg_entry_slippage_pct.toFixed(3)}%`} />
                <StatRow label="Exit slippage" value={`${cio.avg_exit_slippage_pct.toFixed(3)}%`} />
                <StatRow label="Total slip cost" value={formatCurrency(cio.total_slippage_cost)} valueClass="text-accent-red" />
              </div>
            </div>
          </div>

          {/* COL 2: Trade Quality */}
          <div className="space-y-2">
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Closed Trades</div>
              <StatRow label="Total closed" value={cio.total_trades_closed ?? 0} />
              <StatRow label="Win / Loss" value={<><span className="text-accent-green">{cio.winning_trades}</span><span className="text-gray-600"> / </span><span className="text-accent-red">{cio.losing_trades}</span></>} />
              <StatRow label="Win rate" value={`${(cio.win_rate ?? 0).toFixed(1)}%`} valueClass={(cio.win_rate ?? 0) >= 50 ? 'text-accent-green' : 'text-yellow-400'} />
              <StatRow label="Avg win" value={formatCurrency(cio.avg_win ?? 0)} valueClass="text-accent-green" />
              <StatRow label="Avg loss" value={formatCurrency(cio.avg_loss ?? 0)} valueClass="text-accent-red" />
              <StatRow label="Profit factor" value={(cio.profit_factor ?? 0).toFixed(2)} valueClass={(cio.profit_factor ?? 0) >= 1.5 ? 'text-accent-green' : (cio.profit_factor ?? 0) >= 1 ? 'text-yellow-400' : 'text-accent-red'} />
              <StatRow label="Avg hold time" value={`${(cio.avg_hold_time_hours ?? 0).toFixed(1)}h`} />
            </div>
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Open Positions</div>
              <StatRow label="Total open" value={cio.total_open_positions ?? 0} />
              <StatRow label="Win / Loss" value={<><span className="text-accent-green">{cio.open_winning}</span><span className="text-gray-600"> / </span><span className="text-accent-red">{cio.open_losing}</span></>} />
              <StatRow label="Open win rate" value={`${(cio.open_win_rate ?? 0).toFixed(1)}%`} valueClass={(cio.open_win_rate ?? 0) >= 50 ? 'text-accent-green' : 'text-yellow-400'} />
              <div className="border-t border-[var(--color-dark-border)] mt-1 pt-1">
                <StatRow label="Combined WR" value={`${(cio.combined_win_rate ?? 0).toFixed(1)}%`} valueClass={cn('font-bold', (cio.combined_win_rate ?? 0) >= 50 ? 'text-accent-green' : 'text-yellow-400')} />
              </div>
            </div>
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Expectancy</div>
              {perfStats && (
                <>
                  <StatRow label="Per trade (closed)" value={formatCurrency(perfStats.expectancy ?? 0)} valueClass={(perfStats.expectancy ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'} />
                  <StatRow label="All positions" value={formatCurrency(perfStats.total_expectancy ?? 0)} valueClass={(perfStats.total_expectancy ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'} />
                  <div className="border-t border-[var(--color-dark-border)] mt-1 pt-1">
                    <StatRow label="Gross profit" value={formatCurrency(perfStats.gross_profit ?? 0)} valueClass="text-accent-green" />
                    <StatRow label="Gross loss" value={formatCurrency(perfStats.gross_loss ?? 0)} valueClass="text-accent-red" />
                  </div>
                </>
              )}
            </div>
          </div>

          {/* COL 3: Strategy Pipeline + Closures */}
          <div className="space-y-2">
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Strategy Pipeline (30d)</div>
              <div className="grid grid-cols-3 gap-1 mb-2">
                {[
                  { label: 'Proposed', value: cio.strategies_proposed_30d, color: 'text-blue-400' },
                  { label: 'Activated', value: cio.strategies_activated_30d, color: 'text-accent-green' },
                  { label: 'Retired', value: cio.strategies_retired_30d, color: 'text-accent-red' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="text-center rounded bg-[var(--color-dark-bg)] py-1.5">
                    <div className={cn('text-sm font-mono font-bold', color)}>{value}</div>
                    <div className="text-[10px] text-gray-600">{label}</div>
                  </div>
                ))}
              </div>
              <StatRow label="Conversion rate" value={`${(cio.proposal_to_activation_rate ?? 0).toFixed(0)}%`} />
              <StatRow label="Active now" value={cio.active_strategy_count} />
              <StatRow label="Avg lifespan" value={`${(cio.avg_strategy_lifespan_days ?? 0).toFixed(0)}d`} />
            </div>
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Active Strategies</div>
              <StatRow label="Profitable" value={cio.active_profitable ?? 0} valueClass="text-accent-green" />
              <StatRow label="Unprofitable" value={cio.active_unprofitable ?? 0} valueClass="text-accent-red" />
              <div className="border-t border-[var(--color-dark-border)] mt-1 pt-1">
                <StatRow label="Unrealized P&L" value={formatCurrency(cio.active_total_unrealized ?? 0)} valueClass={(cio.active_total_unrealized ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'} />
                <StatRow label="Avg P&L / strategy" value={formatCurrency(cio.avg_active_strategy_pnl ?? 0)} valueClass={(cio.avg_active_strategy_pnl ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'} />
              </div>
            </div>
            <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
              <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Retired (30d) & Closures</div>
              <StatRow label="Profitable" value={cio.retired_profitable ?? 0} valueClass="text-accent-green" />
              <StatRow label="Unprofitable" value={cio.retired_unprofitable ?? 0} valueClass="text-accent-red" />
              <StatRow label="Retired P&L" value={formatCurrency(cio.retired_total_pnl ?? 0)} valueClass={(cio.retired_total_pnl ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'} />
              {cio.retirement_reasons && Object.keys(cio.retirement_reasons).length > 0 && (
                <div className="border-t border-[var(--color-dark-border)] mt-1 pt-1 space-y-0.5">
                  <div className="text-[10px] text-gray-600 mb-0.5">Retirement reasons</div>
                  {Object.entries(cio.retirement_reasons).sort(([,a],[,b]) => (b as number)-(a as number)).map(([r,c]) => (
                    <div key={r} className="flex justify-between"><span className="text-[10px] text-gray-600 capitalize">{r.replace(/_/g,' ')}</span><span className="text-[10px] font-mono text-gray-400">{c as number}</span></div>
                  ))}
                </div>
              )}
              {cio.closure_reasons && Object.keys(cio.closure_reasons).length > 0 && (
                <div className="border-t border-[var(--color-dark-border)] mt-1 pt-1">
                  <div className="text-[10px] text-gray-600 mb-0.5">Position closures</div>
                  {Object.entries(cio.closure_reasons).sort(([,a],[,b]) => (b as number)-(a as number)).map(([r,c]) => (
                    <div key={r} className="flex justify-between"><span className="text-[10px] text-gray-600 capitalize">{r.replace(/_/g,' ')}</span><span className="text-[10px] font-mono text-gray-400">{c as number}</span></div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ROW 4: Underwater + Regime side by side */}
      <div className="grid grid-cols-2 gap-2">
        {pm && pm.drawdown_curve && pm.drawdown_curve.length > 1 && (
          <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
            <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Underwater (Drawdown Duration)</div>
            <UnderwaterPlot data={pm.drawdown_curve.map((d: any) => ({ date: d.date, drawdown_pct: d.drawdown }))} height={140} />
          </div>
        )}
        {regimeAnalysis && regimeAnalysis.performance_by_regime.length > 0 && (
          <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
            <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">P&L by Market Regime</div>
            <div className="space-y-1.5 mt-1">
              {(() => {
                const maxAbs = Math.max(...regimeAnalysis.performance_by_regime.map((r: any) => Math.abs(r.return)), 0.01);
                return regimeAnalysis.performance_by_regime.map((r: any) => (
                  <div key={r.regime} className="flex items-center gap-2">
                    <span className="text-[10px] font-mono text-gray-500 w-32 truncate">{r.regime.replace(/_/g, ' ')}</span>
                    <div className="flex-1 h-3.5 bg-gray-800 rounded-sm overflow-hidden relative">
                      <div className="h-full rounded-sm absolute top-0" style={{ width: `${(Math.abs(r.return)/maxAbs)*100}%`, left: r.return >= 0 ? '50%' : `calc(50% - ${(Math.abs(r.return)/maxAbs)*50}%)`, backgroundColor: r.return >= 0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)' }} />
                      <div className="absolute top-0 bottom-0 w-px bg-gray-600" style={{ left: '50%' }} />
                    </div>
                    <span className={cn('text-[10px] font-mono w-12 text-right font-semibold', r.return >= 0 ? 'text-accent-green' : 'text-accent-red')}>{r.return >= 0 ? '+' : ''}{r.return.toFixed(1)}%</span>
                    <span className="text-[10px] font-mono text-gray-600 w-8 text-right">{r.trades}t</span>
                  </div>
                ));
              })()}
            </div>
          </div>
        )}
      </div>

      {/* ROW 5: Monthly Returns Heatmap */}
      {perfStats?.monthly_returns && perfStats.monthly_returns.length > 0 && (
        <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] overflow-hidden">
          <div className="px-3 py-2 border-b border-[var(--color-dark-border)]">
            <span className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold">Monthly Returns</span>
          </div>
          <div className="overflow-x-auto">
            {(() => {
              const years = [...new Set(perfStats.monthly_returns.map((r: any) => r.year))].sort();
              const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
              return (
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b border-[var(--color-dark-border)]">
                      <th className="text-left px-3 py-1.5 text-gray-500 font-normal w-12">Year</th>
                      {months.map(m => <th key={m} className="px-1 py-1.5 text-center text-gray-500 font-normal w-14">{m}</th>)}
                      <th className="px-3 py-1.5 text-center text-gray-500 font-semibold w-14">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {years.map((year: any) => {
                      const yd = perfStats.monthly_returns.filter((r: any) => r.year === year);
                      const yt = yd.reduce((s: number, r: any) => s + r.return_pct, 0);
                      return (
                        <tr key={year} className="border-b border-[var(--color-dark-border)]/30">
                          <td className="px-3 py-1 font-semibold text-gray-300">{year}</td>
                          {months.map((_, idx) => {
                            const md = yd.find((r: any) => r.month === idx + 1);
                            const val = md?.return_pct || 0;
                            const intensity = Math.min(Math.abs(val) / 8, 1);
                            const bg = val > 0.1 ? `rgba(16,185,129,${0.12+intensity*0.55})` : val < -0.1 ? `rgba(239,68,68,${0.12+intensity*0.55})` : 'transparent';
                            return (
                              <td key={idx} className="px-1 py-1 text-center text-[11px]" style={{ backgroundColor: bg }}>
                                {md ? <span className={val >= 0 ? 'text-accent-green' : 'text-accent-red'}>{val >= 0 ? '+' : ''}{val.toFixed(1)}%</span> : <span className="text-gray-700">—</span>}
                              </td>
                            );
                          })}
                          <td className={cn('px-3 py-1 text-center font-bold', yt >= 0 ? 'text-accent-green' : 'text-accent-red')}>{yt >= 0 ? '+' : ''}{yt.toFixed(1)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              );
            })()}
          </div>
        </div>
      )}

      {/* ROW 6: Win Rate by Day + Hour */}
      {perfStats && (
        <div className="grid grid-cols-2 gap-2">
          <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
            <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Win Rate by Day of Week</div>
            <SVGBarChart data={Object.entries(perfStats.win_rate_by_day || {}).map(([day, rate]: [string, any]) => ({ label: day.slice(0,3), value: rate, color: rate >= 50 ? '#10b981' : '#ef4444' }))} height={160} formatValue={(v) => `${v.toFixed(1)}%`} />
          </div>
          <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
            <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Win Rate by Hour of Day</div>
            <SVGBarChart data={Object.entries(perfStats.win_rate_by_hour || {}).map(([hour, rate]: [string, any]) => ({ label: `${hour}h`, value: rate, color: rate >= 50 ? '#10b981' : '#ef4444' }))} height={160} formatValue={(v) => `${v.toFixed(1)}%`} />
          </div>
        </div>
      )}

      {/* ROW 7: Winners vs Losers + Returns Distribution */}
      <div className="grid grid-cols-2 gap-2">
        {perfStats?.winners_vs_losers?.winners && (
          <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
            <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Winners vs Losers</div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="flex items-center gap-1.5 mb-1.5"><div className="w-2 h-2 rounded-full bg-accent-green" /><span className="text-xs font-semibold text-accent-green">Winners ({perfStats.winners_vs_losers.winners.count})</span></div>
                <StatRow label="Avg hold" value={`${perfStats.winners_vs_losers.winners.avg_hold_hours?.toFixed(1)}h`} />
                <StatRow label="Avg size" value={formatCurrency(perfStats.winners_vs_losers.winners.avg_size || 0)} />
                <StatRow label="Top strategy" value={<span className="truncate max-w-[100px] block">{perfStats.winners_vs_losers.winners.common_strategy}</span>} />
                <StatRow label="Top sector" value={perfStats.winners_vs_losers.winners.common_sector} />
              </div>
              <div>
                <div className="flex items-center gap-1.5 mb-1.5"><div className="w-2 h-2 rounded-full bg-accent-red" /><span className="text-xs font-semibold text-accent-red">Losers ({perfStats.winners_vs_losers.losers.count})</span></div>
                <StatRow label="Avg hold" value={`${perfStats.winners_vs_losers.losers.avg_hold_hours?.toFixed(1)}h`} />
                <StatRow label="Avg size" value={formatCurrency(perfStats.winners_vs_losers.losers.avg_size || 0)} />
                <StatRow label="Top strategy" value={<span className="truncate max-w-[100px] block">{perfStats.winners_vs_losers.losers.common_strategy}</span>} />
                <StatRow label="Top sector" value={perfStats.winners_vs_losers.losers.common_sector} />
              </div>
            </div>
          </div>
        )}
        {pm?.returns_distribution && pm.returns_distribution.length > 0 && (
          <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] p-3">
            <div className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold mb-2">Returns Distribution</div>
            <SVGBarChart data={pm.returns_distribution.map((d: any) => ({ label: d.range, value: d.count }))} height={160} color="#3b82f6" formatValue={(v) => String(Math.round(v))} />
          </div>
        )}
      </div>

      {/* ROW 8: Daily P&L table (collapsible) */}
      {cio && cio.daily_pnl_table && cio.daily_pnl_table.length > 0 && (
        <div className="border border-[var(--color-dark-border)] rounded bg-[var(--color-dark-surface)] overflow-hidden">
          <button onClick={() => setShowDailyPnl(v => !v)} className="w-full px-3 py-2 flex items-center justify-between hover:bg-[var(--color-dark-bg)] transition-colors">
            <span className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold">Daily P&L Log ({cio.daily_pnl_table.length} days)</span>
            <span className="text-xs text-gray-600">{showDailyPnl ? '▲ collapse' : '▼ expand'}</span>
          </button>
          {showDailyPnl && (
            <div className="overflow-x-auto max-h-[360px] overflow-y-auto border-t border-[var(--color-dark-border)]">
              <table className="w-full text-xs font-mono">
                <thead className="sticky top-0 bg-[var(--color-dark-surface)]">
                  <tr className="border-b border-[var(--color-dark-border)]">
                    {['Date','Start Equity','End Equity','Daily P&L','Daily %','Cumulative','Realized','Unrealized','Trades'].map(h => (
                      <th key={h} className={cn('p-2 text-gray-500 font-normal', h === 'Date' ? 'text-left' : 'text-right')}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...cio.daily_pnl_table].reverse().map((row: any) => (
                    <tr key={row.date} className="border-b border-[var(--color-dark-border)]/40 hover:bg-[var(--color-dark-bg)]">
                      <td className="p-2 text-gray-400">{row.date}</td>
                      <td className="p-2 text-right">{formatCurrency(row.starting_equity)}</td>
                      <td className="p-2 text-right">{formatCurrency(row.ending_equity)}</td>
                      <td className={cn('p-2 text-right font-semibold', row.daily_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{row.daily_pnl >= 0 ? '+' : ''}{formatCurrency(row.daily_pnl)}</td>
                      <td className={cn('p-2 text-right', row.daily_pnl_pct >= 0 ? 'text-accent-green' : 'text-accent-red')}>{row.daily_pnl_pct >= 0 ? '+' : ''}{row.daily_pnl_pct.toFixed(2)}%</td>
                      <td className={cn('p-2 text-right', row.cumulative_pnl >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatCurrency(row.cumulative_pnl)}</td>
                      <td className="p-2 text-right text-gray-400">{formatCurrency(row.realized_pnl)}</td>
                      <td className="p-2 text-right text-gray-400">{formatCurrency(row.unrealized_pnl)}</td>
                      <td className="p-2 text-right text-gray-400">{row.trades_closed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

    </div>
  );
};
