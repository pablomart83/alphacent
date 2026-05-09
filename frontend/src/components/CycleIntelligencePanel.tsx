/**
 * CycleIntelligencePanel — Redesigned Cycle Intelligence right panel.
 *
 * The correct funnel (per actual cycle flow):
 *   200 Asked → 200 Generated (195 DSL + 5 AE) → N WF Backtested → N Passed WF
 *   → N Passed Activation → N Signals → N Trades
 *
 * Sections:
 *   1. Live Stage — current stage when running
 *   2. Funnel — the full 7-stage pipeline with correct counts
 *   3. Cycle History — last 8 cycles as a mini table
 *   4. Signal Quality — acceptance rate + rejection reasons
 *   5. Strategy Health — active/max, Sharpe, correlation, net flow
 *   6. Template Performance — top templates by success rate
 */
import { type FC, useMemo } from 'react';
import { cn } from '../lib/utils';
import { colors as designColors } from '../lib/design-tokens';
import type { AutonomousStatus } from '../types';

// ── Mini Sparkline (no axes, no labels — clean inline chart) ──────────────

const MiniSparkline: FC<{
  data: number[];
  color: string;
  label?: string;
  showZeroLine?: boolean;
}> = ({ data, color, showZeroLine }) => {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 100;
  const h = 36;
  const pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x},${y}`;
  }).join(' ');
  const zeroY = h - pad - ((0 - min) / range) * (h - pad * 2);

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-full" preserveAspectRatio="none">
      {showZeroLine && min < 0 && max > 0 && (
        <line x1={pad} y1={zeroY} x2={w - pad} y2={zeroY}
          stroke="#374151" strokeWidth="0.5" strokeDasharray="2,2" />
      )}
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      {/* Last value dot */}
      {data.length > 0 && (() => {
        const last = data[data.length - 1];
        const x = w - pad;
        const y = h - pad - ((last - min) / range) * (h - pad * 2);
        return <circle cx={x} cy={y} r="2" fill={color} />;
      })()}
    </svg>
  );
};

// ── Types ──────────────────────────────────────────────────────────────────

interface CycleRun {
  cycle_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  proposals_generated: number;
  proposals_alpha_edge: number;
  proposals_template: number;
  backtested: number;
  backtest_passed: number;
  backtest_failed: number;
  activated: number;          // passed activation criteria → BACKTESTED status
  promoted_to_demo: number;   // got first order executed → DEMO status
  total_active: number;
  total_backtested: number;
  signals_generated: number;
  signals_passed: number;
  orders_submitted: number;
  orders_filled: number;
  orders_rejected: number;
  avg_sharpe: number | null;
  avg_win_rate: number | null;
  strategies_retired: number;
}

interface SignalSummary {
  total: number;
  accepted: number;
  rejected: number;
  acceptance_rate: number;
  rejection_reasons: Array<{ reason: string; count: number; percentage: number }>;
}

interface WalkForwardData {
  pass_rate_history?: Array<{ date: string; pass_rate: number }>;
  similarity_rejections?: Array<{ rejected_name: string; existing_name: string; similarity: number }>;
}

interface CycleIntelligencePanelProps {
  autonomousStatus: AutonomousStatus | null;
  cycleHistory: CycleRun[];
  cycleProgress: number;
  cycleStage: string;
  lastCycleData: {
    duration_seconds: number | null;
    proposals_generated: number;
    backtest_passed: number;
    backtested: number;
    activated: number;
    strategies_retired: number;
  } | null;
  signalData: { signals: any[]; summary: SignalSummary } | null;
  walkForwardData: WalkForwardData | null;
  /** Configured proposal count from autonomous config (default 200) */
  proposalCount?: number;
}

// ── Helpers ────────────────────────────────────────────────────────────────

function fmtDuration(s: number | null): string {
  if (s == null) return '—';
  if (s < 60) return `${s.toFixed(0)}s`;
  return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`;
}

function relDate(ts: string | null): string {
  if (!ts) return '—';
  const ms = Date.now() - new Date(ts.endsWith('Z') ? ts : ts + 'Z').getTime();
  const m = Math.floor(ms / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function convRate(num: number, den: number): string {
  if (!den || den === 0) return '';
  return `${((num / den) * 100).toFixed(0)}%`;
}

function truncateReason(r: string): string {
  const map: Record<string, string> = {
    'Max exposure reached': 'Max exposure',
    'Calculated position size is zero or negative': 'Zero size',
    'Strategy allocation exhausted': 'Alloc full',
    'Position already exists': 'Duplicate',
    'Market closed': 'Mkt closed',
    'Circuit breaker active': 'Circuit brk',
    'Daily loss limit reached': 'Loss limit',
    'Regime gate': 'Regime gate',
  };
  for (const [k, v] of Object.entries(map)) {
    if (r.toLowerCase().includes(k.toLowerCase())) return v;
  }
  return r.slice(0, 18);
}

// ── Stage label map ────────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  cache_warming: 'Warming cache',
  cleanup_retirement: 'Retiring strategies',
  performance_feedback: 'Updating feedback',
  strategy_proposals: 'Generating proposals',
  data_validation: 'Validating data',
  walk_forward_backtesting: 'Walk-forward backtesting',
  strategy_activation: 'Activating strategies',
  signal_generation: 'Generating signals',
  order_submission: 'Submitting orders',
  Idle: 'Idle',
  Running: 'Running',
  Completed: 'Completed',
  Error: 'Error',
};

// ── Sub-components ─────────────────────────────────────────────────────────

const SectionTitle: FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-widest mb-1.5 font-mono">
    {children}
  </div>
);

const Stat: FC<{ label: string; value: React.ReactNode; color?: string; sub?: string }> = ({ label, value, color, sub }) => (
  <div className="flex flex-col">
    <span className="text-[10px] text-gray-600 font-mono">{label}</span>
    <span className={cn('text-sm font-mono font-bold leading-tight', color || 'text-gray-200')}>{value}</span>
    {sub && <span className="text-[10px] text-gray-600 font-mono">{sub}</span>}
  </div>
);

// ── Funnel bar ─────────────────────────────────────────────────────────────

interface FunnelStage {
  label: string;
  value: number;
  color: string;
  sub?: string; // e.g. "195 DSL + 5 AE"
}

const FunnelBar: FC<{ stages: FunnelStage[] }> = ({ stages }) => {
  const maxVal = stages[0]?.value || 1;
  return (
    <div className="space-y-1.5">
      {stages.map((s, i) => {
        const barW = maxVal > 0 ? (s.value / maxVal) * 100 : 0;
        const prev = i > 0 ? stages[i - 1].value : null;
        const rate = prev !== null && prev > 0 ? convRate(s.value, prev) : null;
        // Derive text color from bg color class
        const textColor = s.color
          .replace('bg-[', 'text-[')
          .replace(']/60', ']')
          .replace(']/40', ']')
          .replace('bg-gray-500/60', 'text-gray-400');
        return (
          <div key={s.label} className="flex items-center gap-2">
            {/* Label — fixed width, right-aligned */}
            <div className="w-20 shrink-0 text-right">
              <span className="text-[10px] text-gray-500 font-mono">{s.label}</span>
            </div>
            {/* Bar track */}
            <div className="flex-1 h-4 bg-gray-800/60 rounded overflow-hidden min-w-0">
              {barW > 0 && (
                <div
                  className={cn('h-full rounded transition-all', s.color)}
                  style={{ width: `${barW}%` }}
                />
              )}
            </div>
            {/* Value — outside the track, fixed width */}
            <span className={cn('text-xs font-mono font-bold w-8 text-right shrink-0', textColor)}>
              {s.value}
            </span>
            {/* Conversion rate — fixed width */}
            <span className="text-[10px] text-gray-600 font-mono w-8 shrink-0 text-right">
              {rate || ''}
            </span>
          </div>
        );
      })}
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────

export const CycleIntelligencePanel: FC<CycleIntelligencePanelProps> = ({
  autonomousStatus,
  cycleHistory,
  cycleProgress,
  cycleStage,
  lastCycleData,
  signalData,
  walkForwardData,
  proposalCount = 200,
}) => {
  const isRunning = cycleProgress > 0 && cycleProgress < 100;
  const isComplete = cycleProgress === 100;

  // Last completed cycle from history
  const lastCycle = useMemo(() =>
    cycleHistory.find(c => c.status === 'COMPLETED' || c.status === 'completed') || null,
    [cycleHistory]
  );

  // Last 20 completed cycles for history table
  const recentCycles = useMemo(() =>
    cycleHistory.filter(c => c.status === 'COMPLETED' || c.status === 'completed').slice(0, 20),
    [cycleHistory]
  );

  // Pass rate trend for sparkline — from WF data or built from cycle history
  const passRateHistory = useMemo(() => {
    if (walkForwardData?.pass_rate_history?.length) {
      return walkForwardData.pass_rate_history.slice(-15);
    }
    return recentCycles
      .filter(c => c.backtested > 0)
      .map(c => ({
        date: (c.started_at || '').slice(0, 10),
        pass_rate: (c.backtest_passed / c.backtested) * 100,
      }))
      .reverse();
  }, [walkForwardData, recentCycles]);

  // Net flow per cycle (activated - retired) for sparkline
  const netFlowTrend = useMemo(() =>
    recentCycles.map(c => ({
      date: (c.started_at || '').slice(0, 10),
      net: c.activated - c.strategies_retired,
    })).reverse(),
    [recentCycles]
  );

  // Build funnel stages from last cycle data
  // The correct funnel:
  //   Asked → Generated (proposals_generated) → WF Backtested → WF Passed
  //   → Activation Passed → Signals → Trades
  const funnelStages = useMemo((): FunnelStage[] => {
    const c = lastCycle;
    if (!c) return [];

    // proposals_generated in DB = strategies that survived initial screening
    // The "asked" is the configured proposal_count (200)
    // DSL/AE split from proposals_alpha_edge + proposals_template
    const dsl = c.proposals_template || 0;
    const ae = c.proposals_alpha_edge || 0;

    // signals and trades
    const signalsGen = c.signals_generated || 0;
    const trades = c.orders_filled || c.orders_submitted || 0;

    return [
      { label: 'Proposed',   value: proposalCount,       color: 'bg-[#3b82f6]/60', sub: dsl > 0 || ae > 0 ? `${dsl} DSL · ${ae} AE` : `195 DSL · 5 AE` },
      { label: 'Validated',  value: proposalCount,       color: 'bg-[#6366f1]/60', sub: `DSL→WF · AE→Fundamental` },
      { label: 'Passed WF',  value: c.backtest_passed,   color: 'bg-[#a855f7]/60' },
      { label: 'Backtested', value: c.activated,         color: 'bg-[#22c55e]/60' },
      { label: 'Activated',  value: c.promoted_to_demo ?? 0, color: 'bg-[#f97316]/60' },
      { label: 'Signals',    value: signalsGen,           color: 'bg-[#eab308]/60' },
      { label: 'Trades',     value: trades,               color: 'bg-[#f97316]/60' },
    ];
  }, [lastCycle, proposalCount]);

  const health = autonomousStatus?.portfolio_health;
  const topTemplates = useMemo(() =>
    (autonomousStatus?.template_stats || [])
      .filter(t => t.usage_count > 0)
      .sort((a, b) => b.success_rate - a.success_rate)
      .slice(0, 5),
    [autonomousStatus]
  );

  return (
    <div className="flex flex-col gap-3 p-1.5 font-mono overflow-y-auto h-full text-xs">

      {/* ── 1. Live Stage ── */}
      {(isRunning || isComplete) && (
        <div className={cn(
          'rounded-lg p-2.5 border',
          isRunning ? 'bg-blue-500/5 border-blue-500/20' : 'bg-[#22c55e]/5 border-[#22c55e]/20'
        )}>
          <div className="flex items-center justify-between mb-1.5">
            <span className={cn('font-semibold text-[11px]', isRunning ? 'text-blue-400' : 'text-[#22c55e]')}>
              {isRunning ? '⟳ ' : '✓ '}{STAGE_LABELS[cycleStage] || cycleStage}
            </span>
            <span className={cn('font-bold text-sm', isRunning ? 'text-blue-400' : 'text-[#22c55e]')}>
              {cycleProgress}%
            </span>
          </div>
          <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all duration-500',
                isRunning ? 'bg-blue-500' : 'bg-[#22c55e]'
              )}
              style={{ width: `${cycleProgress}%` }}
            />
          </div>
          {lastCycleData && isComplete && (
            <div className="grid grid-cols-4 gap-1.5 mt-2">
              <Stat label="Duration" value={fmtDuration(lastCycleData.duration_seconds)} />
              <Stat label="Generated" value={lastCycleData.proposals_generated} color="text-[#3b82f6]" />
              <Stat label="WF Pass" value={lastCycleData.backtest_passed} color="text-[#a855f7]" />
              <Stat label="Activated" value={lastCycleData.activated} color="text-[#22c55e]" />
            </div>
          )}
        </div>
      )}

      {/* ── 2. Funnel ── */}
      {funnelStages.length > 0 && (
        <div>
          <SectionTitle>
            Last Cycle Funnel
            {lastCycle && (
              <span className="text-gray-700 ml-2 normal-case font-normal">
                {relDate(lastCycle.started_at)} · {fmtDuration(lastCycle.duration_seconds)}
              </span>
            )}
          </SectionTitle>
          <FunnelBar stages={funnelStages} />
          {/* DSL vs AE breakdown */}
          {lastCycle && (lastCycle.proposals_template > 0 || lastCycle.proposals_alpha_edge > 0) && (
            <div className="flex gap-3 mt-1.5 text-[10px] text-gray-600">
              <span className="text-[#3b82f6]">■ {lastCycle.proposals_template || 195} DSL → Walk-Forward</span>
              <span className="text-[#22c55e]">■ {lastCycle.proposals_alpha_edge || 5} AE → Fundamental+BT</span>
              {lastCycle.avg_sharpe != null && (
                <span className="ml-auto">Avg Sharpe: <span className="text-gray-400">{lastCycle.avg_sharpe.toFixed(2)}</span></span>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── 3. Cycle History ── */}
      {recentCycles.length > 0 && (
        <div>
          <SectionTitle>Cycle History ({recentCycles.length})</SectionTitle>
          {/* Pass rate sparkline */}
          {passRateHistory.length > 2 && (
            <div className="mb-1.5 h-10 w-full">
              <MiniSparkline
                data={passRateHistory.map(d => d.pass_rate)}
                color={designColors.green}
                label="WF Pass Rate"
              />
            </div>
          )}
          <div className="overflow-y-auto max-h-[220px] rounded border border-gray-800">
            <table className="w-full text-[10px] font-mono" style={{ tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: '34%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '13%' }} />
                <col style={{ width: '14%' }} />
              </colgroup>
              <thead className="sticky top-0 bg-[#0a0e1a]">
                <tr className="border-b border-gray-800">
                  <th className="py-1 px-1.5 text-left text-[9px] text-gray-600 uppercase tracking-wide font-medium">When</th>
                  <th className="py-1 px-1 text-right text-[9px] text-gray-600 uppercase tracking-wide font-medium">Gen</th>
                  <th className="py-1 px-1 text-right text-[9px] text-gray-600 uppercase tracking-wide font-medium">WF%</th>
                  <th className="py-1 px-1 text-right text-[9px] text-gray-600 uppercase tracking-wide font-medium">Act</th>
                  <th className="py-1 px-1 text-right text-[9px] text-gray-600 uppercase tracking-wide font-medium">Ret</th>
                  <th className="py-1 px-1 text-right text-[9px] text-gray-600 uppercase tracking-wide font-medium">Dur</th>
                </tr>
              </thead>
              <tbody>
                {recentCycles.map((c, i) => {
                  const passRate = c.backtested > 0 ? (c.backtest_passed / c.backtested) * 100 : 0;
                  const net = c.activated - c.strategies_retired;
                  return (
                    <tr
                      key={c.cycle_id}
                      className="border-b border-gray-800/50 hover:bg-gray-800/40 transition-colors"
                      style={{ background: i % 2 === 1 ? 'rgba(31,41,55,0.3)' : undefined }}
                    >
                      <td className="py-1 px-1.5 text-gray-500 truncate">{relDate(c.started_at)}</td>
                      <td className="py-1 px-1 text-right text-[#3b82f6]">{c.proposals_generated}</td>
                      <td className={cn('py-1 px-1 text-right font-semibold',
                        c.backtested === 0 ? 'text-gray-600' :
                        passRate >= 70 ? 'text-[#22c55e]' : passRate >= 40 ? 'text-[#eab308]' : 'text-[#ef4444]'
                      )}>
                        {c.backtested > 0 ? `${passRate.toFixed(0)}%` : '—'}
                      </td>
                      <td className={cn('py-1 px-1 text-right font-semibold',
                        net > 0 ? 'text-[#22c55e]' : net < 0 ? 'text-[#ef4444]' : 'text-gray-600'
                      )}>
                        {net > 0 ? `+${net}` : net !== 0 ? net : '—'}
                      </td>
                      <td className={cn('py-1 px-1 text-right',
                        c.strategies_retired > 0 ? 'text-[#ef4444]' : 'text-gray-600'
                      )}>
                        {c.strategies_retired > 0 ? c.strategies_retired : '—'}
                      </td>
                      <td className="py-1 px-1 text-right text-gray-500">{fmtDuration(c.duration_seconds)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── 4. Signal Quality ── */}
      {signalData?.summary && (
        <div>
          <SectionTitle>Signal Quality</SectionTitle>
          <div className="grid grid-cols-3 gap-1.5 mb-1.5">
            <Stat label="Total" value={signalData.summary.total} />
            <Stat label="Executed"
              value={signalData.summary.accepted}
              color={signalData.summary.accepted > 0 ? 'text-[#22c55e]' : 'text-gray-500'}
            />
            <Stat label="Accept %"
              value={`${signalData.summary.acceptance_rate.toFixed(0)}%`}
              color={
                signalData.summary.acceptance_rate >= 30 ? 'text-[#22c55e]' :
                signalData.summary.acceptance_rate >= 10 ? 'text-[#eab308]' : 'text-[#ef4444]'
              }
            />
          </div>
          <div className="h-1 bg-gray-800 rounded overflow-hidden mb-1.5">
            <div
              className={cn('h-full rounded',
                signalData.summary.acceptance_rate >= 30 ? 'bg-[#22c55e]' :
                signalData.summary.acceptance_rate >= 10 ? 'bg-[#eab308]' : 'bg-[#ef4444]'
              )}
              style={{ width: `${Math.min(100, signalData.summary.acceptance_rate)}%` }}
            />
          </div>
          {signalData.summary.rejection_reasons?.slice(0, 3).map((r, i) => (
            <div key={i} className="flex items-center justify-between py-0.5">
              <span className="text-gray-500 truncate flex-1">{truncateReason(r.reason)}</span>
              <div className="flex items-center gap-1.5 shrink-0 ml-2">
                <div className="w-12 h-1 bg-gray-800 rounded overflow-hidden">
                  <div className="h-full bg-[#ef4444]/60 rounded" style={{ width: `${r.percentage}%` }} />
                </div>
                <span className="text-[#ef4444]/80 w-6 text-right">{r.count}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── 5. Strategy Health ── */}
      {health && (
        <div>
          <SectionTitle>Strategy Health</SectionTitle>
          <div className="grid grid-cols-2 gap-1.5 mb-1.5">
            <Stat label="Active"
              value={`${health.active_strategies} / ${health.max_strategies}`}
              color={health.active_strategies >= health.max_strategies * 0.9 ? 'text-[#eab308]' : 'text-gray-200'}
            />
            <Stat label="Portfolio Sharpe"
              value={health.portfolio_sharpe != null ? health.portfolio_sharpe.toFixed(2) : '—'}
              color={health.portfolio_sharpe >= 1 ? 'text-[#22c55e]' : health.portfolio_sharpe >= 0.5 ? 'text-[#eab308]' : health.portfolio_sharpe > 0 ? 'text-[#ef4444]' : 'text-gray-500'}
            />
            <Stat label="Avg Correlation"
              value={health.avg_correlation != null ? health.avg_correlation.toFixed(2) : '—'}
              color={health.avg_correlation > 0.7 ? 'text-[#ef4444]' : health.avg_correlation > 0.5 ? 'text-[#eab308]' : health.avg_correlation > 0 ? 'text-[#22c55e]' : 'text-gray-500'}
            />
            <Stat label="Allocation"
              value={`${health.total_allocation > 10
                ? health.total_allocation.toFixed(0)   // already a percentage (e.g. 147)
                : (health.total_allocation * 100).toFixed(0)  // ratio (e.g. 0.97)
              }%`}
              color={health.total_allocation > 100 || health.total_allocation > 1.0
                ? 'text-[#ef4444]'
                : health.total_allocation > 90 || health.total_allocation > 0.9
                ? 'text-[#eab308]'
                : 'text-gray-200'}
            />
          </div>
          {netFlowTrend.length > 2 && (
            <div className="h-10">
              <MiniSparkline
                data={netFlowTrend.map(d => d.net)}
                color={designColors.blue}
                label="Net Flow"
                showZeroLine
              />
            </div>
          )}
        </div>
      )}

      {/* ── 6. Template Performance ── */}
      {topTemplates.length > 0 && (
        <div>
          <SectionTitle>Top Templates</SectionTitle>
          <div className="space-y-0.5">
            {topTemplates.map(t => (
              <div key={t.name} className="flex items-center gap-1.5 py-0.5">
                <span className="text-gray-300 truncate flex-1 text-[10px]">
                  {t.name.replace(/ Multi$/, '').replace(/ Long$/, '').slice(0, 22)}
                </span>
                <div className="w-16 h-1.5 bg-gray-800 rounded overflow-hidden shrink-0">
                  <div
                    className={cn('h-full rounded',
                      t.success_rate >= 0.7 ? 'bg-[#22c55e]' :
                      t.success_rate >= 0.4 ? 'bg-[#eab308]' : 'bg-[#ef4444]'
                    )}
                    style={{ width: `${t.success_rate * 100}%` }}
                  />
                </div>
                <span className={cn('text-[10px] font-semibold w-8 text-right shrink-0',
                  t.success_rate >= 0.7 ? 'text-[#22c55e]' :
                  t.success_rate >= 0.4 ? 'text-[#eab308]' : 'text-[#ef4444]'
                )}>
                  {(t.success_rate * 100).toFixed(0)}%
                </span>
                <span className="text-gray-600 text-[9px] w-6 text-right shrink-0">{t.usage_count}x</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Empty state ── */}
      {funnelStages.length === 0 && !isRunning && recentCycles.length === 0 && (
        <div className="flex flex-col items-center justify-center h-32 text-gray-600">
          <span className="text-2xl mb-2">⟳</span>
          <span className="text-xs font-mono">No cycle data yet</span>
          <span className="text-[10px] mt-1 font-mono">Run a cycle to see intelligence</span>
        </div>
      )}

    </div>
  );
};
