import React, { type FC, useEffect, useState, useRef, useCallback } from 'react';
import {
  CheckCircle2, XCircle, Loader2, Clock, Trash2, BarChart3,
  Lightbulb, Database, TrendingUp, Zap, Send, HardDrive,
} from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '../ui/Button';
import { SectionLabel } from '../ui/SectionLabel';
import { cn } from '../../lib/utils';
import { wsManager } from '../../services/websocket';
import { apiClient } from '../../services/api';

// Stage definitions matching backend CYCLE_STAGES
const STAGES = [
  { key: 'cache_warming', label: 'Cache', icon: HardDrive },
  { key: 'cleanup_retirement', label: 'Cleanup', icon: Trash2 },
  { key: 'performance_feedback', label: 'Feedback', icon: BarChart3 },
  { key: 'strategy_proposals', label: 'Proposals', icon: Lightbulb },
  { key: 'data_validation', label: 'Validate', icon: Database },
  { key: 'walk_forward_backtesting', label: 'Backtest', icon: TrendingUp },
  { key: 'strategy_activation', label: 'Activate', icon: Zap },
  { key: 'signal_generation', label: 'Signals', icon: TrendingUp },
  { key: 'order_submission', label: 'Orders', icon: Send },
] as const;

type StageStatus = 'pending' | 'running' | 'complete' | 'error';

interface StageState {
  status: StageStatus;
  progress_pct: number;
  metrics: Record<string, any>;
  error?: string;
}

interface CycleRun {
  cycle_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_seconds: number | null;
  proposals_generated: number;
  backtested: number;
  backtest_passed: number;
  activated: number;
  strategies_retired: number;
  strategies_cleaned: number;
  avg_sharpe: number | null;
  avg_win_rate: number | null;
  total_active: number;
  total_backtested: number;
}

interface TradingCyclePipelineProps {
  cycleRunning: boolean;
}

const LOCALSTORAGE_KEY = 'alphacent_last_cycle_stages';
const LIVE_STAGES_KEY = 'alphacent_live_cycle_stages';

const statusConfig = {
  pending: { color: 'text-gray-500', bg: 'bg-gray-500/10', border: 'border-gray-700' },
  running: { color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  complete: { color: 'text-accent-green', bg: 'bg-accent-green/10', border: 'border-accent-green/30' },
  error: { color: 'text-accent-red', bg: 'bg-accent-red/10', border: 'border-accent-red/30' },
};

export const TradingCyclePipeline: FC<TradingCyclePipelineProps> = ({ cycleRunning }) => {
  const [cycleLog, setCycleLog] = useState<Array<{ time: string; message: string; type: 'info' | 'success' | 'error' }>>([]);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [stages, setStages] = useState<Record<string, StageState>>(() => {
    // On mount, restore live cycle stages if a cycle was running when we navigated away
    try {
      const saved = localStorage.getItem(LIVE_STAGES_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        const hasRunning = Object.values(parsed).some((s: any) => s.status === 'running');
        const allComplete = Object.values(parsed).every((s: any) => s.status === 'complete' || s.status === 'error');
        if (hasRunning || !allComplete) {
          return parsed;
        }
      }
    } catch {
      // Ignore parse errors
    }
    return {};
  });
  const [persistedStages, setPersistedStages] = useState<Record<string, StageState> | null>(null);
  const [cycleHistory, setCycleHistory] = useState<CycleRun[]>([]);
  const [cycleComplete, setCycleComplete] = useState(false);
  const [selectedCycles, setSelectedCycles] = useState<Set<string>>(new Set());
  const [deletingCycles, setDeletingCycles] = useState(false);

  // Load persisted (last completed) stages from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(LOCALSTORAGE_KEY);
      if (saved) {
        setPersistedStages(JSON.parse(saved));
      }
    } catch {
      // Ignore parse errors
    }
  }, []);

  // Save stages to localStorage when a cycle completes
  useEffect(() => {
    if (cycleComplete && Object.keys(stages).length > 0) {
      try {
        localStorage.setItem(LOCALSTORAGE_KEY, JSON.stringify(stages));
        setPersistedStages(stages);
        localStorage.removeItem(LIVE_STAGES_KEY);
      } catch {
        // Ignore storage errors
      }
    }
  }, [cycleComplete, stages]);

  // Reset stages when a new cycle starts
  useEffect(() => {
    if (cycleRunning) {
      setStages({});
      setCycleComplete(false);
      setCycleLog([]);
      localStorage.removeItem(LIVE_STAGES_KEY);
    }
  }, [cycleRunning]);

  // Subscribe to cycle_progress WebSocket events
  useEffect(() => {
    const unsubscribe = wsManager.onCycleProgress((data: any) => {
      const progress = data?.data || data;
      if (!progress?.stage) return;

      // Accumulate log entries from phase messages
      const phase = progress.metrics?.phase;
      const now = new Date();
      const timeStr = now.toTimeString().slice(0, 8);
      if (phase) {
        setCycleLog(prev => [...prev, {
          time: timeStr,
          message: phase,
          type: progress.status === 'error' ? 'error' : progress.status === 'complete' ? 'success' : 'info',
        }]);
      } else if (progress.status === 'running' && !phase) {
        // Stage started — log it
        const label = STAGES.find(s => s.key === progress.stage)?.label || progress.stage;
        setCycleLog(prev => [...prev, { time: timeStr, message: `▶ ${label}...`, type: 'info' }]);
      } else if (progress.status === 'complete') {
        const label = STAGES.find(s => s.key === progress.stage)?.label || progress.stage;
        const metrics = progress.metrics || {};
        const detail = Object.entries(metrics)
          .filter(([k]) => k !== 'phase' && k !== 'skipped' && k !== 'reason')
          .map(([k, v]) => `${k}: ${v}`)
          .join(', ');
        setCycleLog(prev => [...prev, {
          time: timeStr,
          message: `✓ ${label}${detail ? ` — ${detail}` : ''}`,
          type: 'success',
        }]);
      } else if (progress.status === 'error') {
        const label = STAGES.find(s => s.key === progress.stage)?.label || progress.stage;
        setCycleLog(prev => [...prev, { time: timeStr, message: `✗ ${label}: ${progress.error || 'error'}`, type: 'error' }]);
      }

      setStages(prev => {
        const next = {
          ...prev,
          [progress.stage]: {
            status: progress.status || 'running',
            progress_pct: progress.progress_pct || 0,
            metrics: progress.metrics || {},
            error: progress.error,
          },
        };
        try {
          localStorage.setItem(LIVE_STAGES_KEY, JSON.stringify(next));
        } catch {
          // Ignore storage errors
        }
        return next;
      });

      if (progress.stage === 'order_submission' && progress.status === 'complete') {
        setCycleComplete(true);
        fetchHistory();
      }
    });

    const unsubCycle = wsManager.onAutonomousCycle((data: any) => {
      if (data?.event === 'cycle_completed' || data?.data?.event === 'cycle_completed') {
        setCycleComplete(true);
        setStages(prev => {
          const updated = { ...prev };
          for (const key of Object.keys(updated)) {
            if (updated[key].status === 'running') {
              updated[key] = { ...updated[key], status: 'complete' };
            }
          }
          return updated;
        });
        fetchHistory();
      }
    });

    return () => {
      unsubscribe();
      unsubCycle();
    };
  }, []);

  // Fetch cycle history on mount
  const fetchHistory = useCallback(async () => {
    try {
      const result = await apiClient.getAutonomousCycles(20);
      const runs = Array.isArray(result) ? result : (result.data || []);
      setCycleHistory(runs);
    } catch {
      // Non-critical
    }
  }, []);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // Auto-scroll log container (not the page) to bottom
  useEffect(() => {
    if (logEndRef.current) {
      const container = logEndRef.current.parentElement;
      if (container) container.scrollTop = container.scrollHeight;
    }
  }, [cycleLog]);

  const hasAnyStageData = Object.keys(stages).length > 0;
  const displayStages = hasAnyStageData ? stages : (persistedStages || {});
  const hasDisplayData = Object.keys(displayStages).length > 0;
  const isShowingPersisted = !hasAnyStageData && !cycleRunning && persistedStages !== null && Object.keys(persistedStages).length > 0;

  const getStageStatus = (stageKey: string): StageStatus => {
    return displayStages[stageKey]?.status || 'pending';
  };

  const buildMetricsSummary = (): { label: string; value: string; color: string }[] => {
    const items: { label: string; value: string; color: string }[] = [];
    const cleanup = displayStages.cleanup_retirement?.metrics;
    const proposals = displayStages.strategy_proposals?.metrics;
    const backtest = displayStages.walk_forward_backtesting?.metrics;
    const activation = displayStages.strategy_activation?.metrics;
    const signals = displayStages.signal_generation?.metrics;
    const orders = displayStages.order_submission?.metrics;

    if (cleanup?.cleaned != null) items.push({ label: 'Cleaned', value: String(cleanup.cleaned), color: 'text-gray-300' });
    if (proposals?.proposed != null) items.push({ label: 'Proposed', value: String(proposals.proposed), color: 'text-blue-400' });
    if (backtest?.passed != null && backtest?.backtested != null) {
      items.push({ label: 'BT', value: `${backtest.passed}/${backtest.backtested} passed`, color: 'text-purple-400' });
    }
    if (activation?.activated != null) items.push({ label: 'Activated', value: String(activation.activated), color: 'text-accent-green' });
    const sharpeVal = activation?.avg_sharpe ?? backtest?.avg_sharpe;
    if (sharpeVal != null) items.push({ label: 'Sharpe', value: Number(sharpeVal).toFixed(2), color: 'text-yellow-400' });
    if (signals?.signals_generated != null) items.push({ label: 'Signals', value: String(signals.signals_generated), color: 'text-blue-400' });
    if (orders?.orders_submitted != null) items.push({ label: 'Orders', value: String(orders.orders_submitted), color: 'text-accent-green' });

    return items;
  };

  return (
    <div className="space-y-3">
      {/* Horizontal Pipeline */}
      <div>
        <SectionLabel>
          Trading Cycle Pipeline{isShowingPersisted && ' (last run)'}
        </SectionLabel>

        {/* Horizontal pipeline stepper */}
        <div className="flex items-center justify-between px-2">
          {STAGES.map((stage, idx) => {
            const status = getStageStatus(stage.key);
            const isLast = idx === STAGES.length - 1;
            return (
              <React.Fragment key={stage.key}>
                <div className="flex flex-col items-center gap-1 min-w-0" title={formatStageTooltip(stage.key, displayStages[stage.key])}>
                  <div className={cn(
                    'w-9 h-9 rounded-full flex items-center justify-center border transition-all',
                    statusConfig[status].bg, statusConfig[status].border
                  )}>
                    {status === 'pending' && <Clock className="h-4 w-4 text-gray-500" />}
                    {status === 'running' && <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />}
                    {status === 'complete' && <CheckCircle2 className="h-4 w-4 text-accent-green" />}
                    {status === 'error' && <XCircle className="h-4 w-4 text-accent-red" />}
                  </div>
                  <span className={cn(
                    'text-xs font-mono text-center leading-tight',
                    status === 'pending' ? 'text-gray-600' : 'text-gray-300'
                  )}>
                    {stage.label}
                  </span>
                </div>
                {!isLast && (
                  <div className={cn(
                    'flex-1 h-0.5 mx-1',
                    status === 'complete' ? 'bg-accent-green/40' : 'bg-gray-700'
                  )} />
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Current activity text */}
        {cycleRunning && (() => {
          const runningStage = STAGES.find(s => displayStages[s.key]?.status === 'running');
          const phase = runningStage ? displayStages[runningStage.key]?.metrics?.phase : null;
          const progressPct = runningStage ? displayStages[runningStage.key]?.progress_pct : null;

          if (!runningStage) return null;

          return (
            <div className="mt-2 px-2">
              <div className="flex items-center gap-2 text-xs">
                <Loader2 className="h-3 w-3 text-blue-400 animate-spin flex-shrink-0" />
                <span className="text-blue-400 font-medium">{runningStage.label}</span>
                {progressPct != null && (
                  <span className="text-muted-foreground">{progressPct}%</span>
                )}
              </div>
              {phase && (
                <div className="mt-1 text-xs text-muted-foreground font-mono truncate pl-5">
                  {phase}
                </div>
              )}
              {progressPct != null && (
                <div className="mt-1.5 h-1 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, progressPct)}%` }}
                  />
                </div>
              )}
            </div>
          );
        })()}

        {/* Compact metrics summary below pipeline */}
        {hasDisplayData && (() => {
          const metrics = buildMetricsSummary();
          return metrics.length > 0 ? (
            <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-x-4 gap-y-1 text-xs font-mono">
              {metrics.map((m) => (
                <span key={m.label} className="text-muted-foreground">
                  {m.label}: <span className={m.color}>{m.value}</span>
                </span>
              ))}
            </div>
          ) : null;
        })()}
      </div>

      {/* Cycle Log — shown during and after a cycle run */}
      {cycleLog.length > 0 && (
        <div className="border border-[var(--color-dark-border)] rounded overflow-hidden">
          <div className="px-3 py-1.5 border-b border-[var(--color-dark-border)] flex items-center justify-between">
            <span className="text-[10px] text-gray-500 tracking-widest uppercase font-semibold">Cycle Log</span>
            <span className="text-[10px] text-gray-600 font-mono">{cycleRunning ? '● live' : 'last run'}</span>
          </div>
          <div className="max-h-[200px] overflow-y-auto bg-[var(--color-dark-bg)] p-2 space-y-0.5 font-mono text-[11px]">
            {cycleLog.map((entry, i) => (
              <div key={i} className="flex gap-2 leading-relaxed">
                <span className="text-gray-600 shrink-0">[{entry.time}]</span>
                <span className={
                  entry.type === 'error' ? 'text-accent-red' :
                  entry.type === 'success' ? 'text-accent-green' :
                  'text-gray-400'
                }>{entry.message}</span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {/* Cycle Summary */}
      {cycleComplete && hasAnyStageData && (
        <CycleSummaryCard stages={stages} />
      )}

      {/* Cycle History */}
      <div>
        <SectionLabel
          actions={
            selectedCycles.size > 0 ? (
              <Button
                variant="destructive"
                size="sm"
                onClick={async () => {
                  try {
                    setDeletingCycles(true);
                    await apiClient.deleteAutonomousCycles(Array.from(selectedCycles));
                    toast.success(`Deleted ${selectedCycles.size} cycle(s)`);
                    setSelectedCycles(new Set());
                    fetchHistory();
                  } catch {
                    toast.error('Failed to delete cycles');
                  } finally {
                    setDeletingCycles(false);
                  }
                }}
                disabled={deletingCycles}
                className="gap-1 text-xs"
              >
                <Trash2 className="h-3 w-3" />
                {deletingCycles ? 'Deleting...' : `Delete (${selectedCycles.size})`}
              </Button>
            ) : undefined
          }
        >
          Cycle History ({cycleHistory.length})
        </SectionLabel>

        {cycleHistory.length === 0 ? (
          <div className="text-center py-4 text-muted-foreground text-xs">
            No cycle history yet
          </div>
        ) : (
          <div className="max-h-[400px] overflow-y-auto space-y-2">
            {/* Select All */}
            <div className="flex items-center gap-2 pb-2 border-b border-border">
              <input
                type="checkbox"
                checked={cycleHistory.length > 0 && selectedCycles.size === cycleHistory.length}
                onChange={() => {
                  if (selectedCycles.size === cycleHistory.length) {
                    setSelectedCycles(new Set());
                  } else {
                    setSelectedCycles(new Set(cycleHistory.map(r => r.cycle_id)));
                  }
                }}
                className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
              />
              <span className="text-xs text-muted-foreground">Select All</span>
            </div>
            {cycleHistory.map((run) => (
              <CycleHistoryRow
                key={run.cycle_id}
                run={run}
                selected={selectedCycles.has(run.cycle_id)}
                onToggle={() => {
                  setSelectedCycles(prev => {
                    const next = new Set(prev);
                    if (next.has(run.cycle_id)) {
                      next.delete(run.cycle_id);
                    } else {
                      next.add(run.cycle_id);
                    }
                    return next;
                  });
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// Format tooltip text for a stage showing its metrics
function formatStageTooltip(stageKey: string, state?: StageState): string {
  if (!state) return stageKey.replace(/_/g, ' ');
  const parts = [stageKey.replace(/_/g, ' ')];
  if (state.status === 'error' && state.error) {
    parts.push(`Error: ${state.error}`);
  }
  if (state.metrics && Object.keys(state.metrics).length > 0) {
    for (const [k, v] of Object.entries(state.metrics)) {
      if (typeof v === 'object' && v !== null) {
        for (const [sk, sv] of Object.entries(v as Record<string, any>)) {
          parts.push(`${sk}: ${sv}`);
        }
      } else {
        parts.push(`${k.replace(/_/g, ' ')}: ${v}`);
      }
    }
  }
  return parts.join('\n');
}

// Cycle summary card shown after completion — flat bordered div
const CycleSummaryCard: FC<{ stages: Record<string, StageState> }> = ({ stages }) => {
  const cleanup = stages.cleanup_retirement?.metrics || {};
  const proposals = stages.strategy_proposals?.metrics || {};
  const backtest = stages.walk_forward_backtesting?.metrics || {};
  const activation = stages.strategy_activation?.metrics || {};
  const retirement = stages.cleanup_retirement?.metrics || {};
  const signals = stages.signal_generation?.metrics || {};
  const orderSubmission = stages.order_submission?.metrics || {};

  const summaryItems = [
    { label: 'Cleaned', value: cleanup.cleaned ?? '—', color: 'text-gray-300' },
    { label: 'Proposed', value: proposals.proposed ?? '—', color: 'text-blue-400' },
    { label: 'Backtested', value: backtest.backtested ?? '—', color: 'text-purple-400' },
    { label: 'BT Passed', value: backtest.passed ?? '—', color: 'text-accent-green' },
    { label: 'Activated', value: (activation.activated ?? activation.approved) ?? '—', color: 'text-accent-green' },
    { label: 'Avg Sharpe', value: activation.avg_sharpe ?? backtest.avg_sharpe ?? '—', color: 'text-yellow-400' },
    { label: 'Avg Win Rate', value: activation.avg_win_rate ? `${activation.avg_win_rate.toFixed ? activation.avg_win_rate.toFixed(0) : activation.avg_win_rate}%` : (backtest.avg_win_rate ? `${backtest.avg_win_rate.toFixed ? backtest.avg_win_rate.toFixed(0) : backtest.avg_win_rate}%` : '—'), color: 'text-yellow-400' },
    { label: 'Total Active', value: activation.total_active ?? '—', color: 'text-blue-400' },
    { label: 'Retired', value: retirement.retired ?? '—', color: (retirement.retired != null && retirement.retired > 0) ? 'text-red-400' : 'text-gray-400' },
    { label: 'Signals', value: signals.signals_generated != null ? signals.signals_generated : (stages.signal_generation?.status === 'running' ? 'Running...' : '—'), color: (signals.signals_generated != null && signals.signals_generated > 0) ? 'text-blue-400' : 'text-gray-400' },
    { label: 'Orders', value: orderSubmission.orders_submitted ?? '—', color: (orderSubmission.orders_submitted != null && orderSubmission.orders_submitted > 0) ? 'text-accent-green' : 'text-gray-400' },
  ];

  return (
    <div className="rounded-lg border border-accent-green/30 bg-accent-green/5 p-3">
      <div className="flex items-center gap-2 mb-2">
        <CheckCircle2 className="h-4 w-4 text-accent-green" />
        <span className="text-xs font-semibold text-accent-green uppercase tracking-wide">Cycle Complete</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {summaryItems.map((item) => (
          <div key={item.label} className="bg-muted/30 rounded-lg p-2">
            <div className="text-xs text-muted-foreground mb-0.5">{item.label}</div>
            <div className={cn('text-[12px] font-mono font-bold', item.color)}>
              {item.value}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Cycle history row — enhanced with trader-relevant metrics
const CycleHistoryRow: FC<{ run: CycleRun; selected: boolean; onToggle: () => void }> = ({ run, selected, onToggle }) => {
  const isSuccess = run.status === 'completed';
  const isError = run.status === 'error';
  const startDate = new Date(run.started_at);
  const timeAgo = getTimeAgo(startDate);

  const formatDuration = (seconds: number | null): string => {
    if (!seconds) return '—';
    if (seconds < 60) return `${seconds.toFixed(0)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  return (
    <div className={cn(
      'p-3 rounded-lg border',
      isSuccess ? 'border-accent-green/20 bg-accent-green/5' :
      isError ? 'border-accent-red/20 bg-accent-red/5' :
      'border-gray-700 bg-muted/20'
    )}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="h-4 w-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500 focus:ring-offset-0 cursor-pointer"
          />
          {isSuccess ? (
            <CheckCircle2 className="h-4 w-4 text-accent-green" />
          ) : isError ? (
            <XCircle className="h-4 w-4 text-accent-red" />
          ) : (
            <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />
          )}
          <span className="text-xs text-muted-foreground font-mono">{timeAgo}</span>
          <span className="text-xs text-gray-600">·</span>
          <span className="text-xs text-muted-foreground font-mono">
            ⏱ {formatDuration(run.duration_seconds)}
          </span>
        </div>
        <span className={cn(
          'text-xs font-mono px-1.5 py-0.5 rounded',
          isSuccess ? 'bg-accent-green/10 text-accent-green' :
          isError ? 'bg-accent-red/10 text-accent-red' :
          'bg-blue-500/10 text-blue-400'
        )}>
          {run.status.toUpperCase()}
        </span>
      </div>
      <div className="flex items-center gap-4 text-xs font-mono">
        <span className="text-blue-400" title="Proposed">
          {run.proposals_generated} proposed
        </span>
        <span className="text-purple-400" title="Backtested (passed/total)">
          {run.backtest_passed}/{run.backtested} passed BT
        </span>
        <span className="text-accent-green" title="Activated">
          {run.activated} activated
        </span>
        {run.strategies_retired > 0 && (
          <span className="text-accent-red" title="Retired">
            {run.strategies_retired} retired
          </span>
        )}
        {run.avg_sharpe != null && run.avg_sharpe > 0 && (
          <span className="text-yellow-400" title="Average Sharpe Ratio">
            Sharpe: {run.avg_sharpe.toFixed(2)}
          </span>
        )}
        {run.avg_win_rate != null && run.avg_win_rate > 0 && (
          <span className="text-yellow-400" title="Average Win Rate">
            WR: {(run.avg_win_rate * 100).toFixed(0)}%
          </span>
        )}
        {run.total_active > 0 && (
          <span className="text-gray-400" title="Total active strategies after cycle">
            ({run.total_active} active)
          </span>
        )}
        {run.total_backtested > 0 && (
          <span className="text-purple-400" title="Total BACKTESTED strategies after cycle">
            ({run.total_backtested} backtested)
          </span>
        )}
      </div>
    </div>
  );
};

function getTimeAgo(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays > 0) return `${diffDays}d ago`;
  if (diffHours > 0) return `${diffHours}h ago`;
  if (diffMins > 0) return `${diffMins}m ago`;
  return 'Just now';
}
