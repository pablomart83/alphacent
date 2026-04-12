import { type FC, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { RefreshButton } from '../components/ui/RefreshButton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { usePolling } from '../hooks/usePolling';
import { useSystemHealthStore } from '../lib/stores/system-health-store';
import { wsManager } from '../services/websocket';
import { useWebSocketConnection } from '../hooks/useWebSocket';

interface SystemHealthPageProps {
  onLogout: () => void;
}

const cbStateColor = (state: string) => {
  if (state === 'CLOSED' || state === 'closed') return 'bg-green-400';
  if (state === 'HALF_OPEN' || state === 'half_open') return 'bg-amber-400';
  return 'bg-red-400';
};

const cbStateBorderColor = (state: string) => {
  if (state === 'CLOSED' || state === 'closed') return 'rgba(34, 197, 94, 0.3)';
  if (state === 'HALF_OPEN' || state === 'half_open') return 'rgba(234, 179, 8, 0.3)';
  return 'rgba(239, 68, 68, 0.3)';
};

const cbStateBgColor = (state: string) => {
  if (state === 'CLOSED' || state === 'closed') return 'rgba(34, 197, 94, 0.05)';
  if (state === 'HALF_OPEN' || state === 'half_open') return 'rgba(234, 179, 8, 0.05)';
  return 'rgba(239, 68, 68, 0.05)';
};

const cbStateLabel = (state: string) => {
  if (state === 'CLOSED' || state === 'closed') return 'Closed';
  if (state === 'HALF_OPEN' || state === 'half_open') return 'Half-Open';
  return 'Open';
};

const statusDot = (status: string) => {
  if (status === 'healthy') return 'bg-green-400';
  if (status === 'stale') return 'bg-amber-400';
  return 'bg-red-400';
};

const formatAge = (iso: string | null) => {
  if (!iso) return '—';
  const age = (Date.now() - new Date(iso).getTime()) / 1000;
  if (age < 0) return 'just now';
  if (age < 60) return `${Math.round(age)}s ago`;
  if (age < 3600) return `${Math.round(age / 60)}m ago`;
  return `${(age / 3600).toFixed(1)}h ago`;
};

export const SystemHealthPage: FC<SystemHealthPageProps> = ({ onLogout }) => {
  const { data, loading, error, lastFetchedAt, fetch } = useSystemHealthStore();
  useWebSocketConnection();

  usePolling({ fetchFn: fetch, intervalMs: 15000, enabled: true, skipWhenWsConnected: true });

  useEffect(() => {
    const unsub = wsManager.on('system_health', () => fetch());
    return unsub;
  }, [fetch]);

  const hasOpenCB = data?.circuit_breakers?.some(
    (cb) => cb.state === 'OPEN' || cb.state === 'open'
  );
  const hasStaleMonitoring = data?.monitoring_service?.sub_tasks?.some(
    (t) => t.status === 'stale' || t.status === 'error'
  );

  // ── Side panel metrics ──────────────────────────────────────────────
  const sideMetrics: CompactMetric[] = useMemo(() => {
    const errorRate = data?.etoro_api?.error_rate_5m;
    const avgResponse = data?.etoro_api?.avg_response_ms;
    const cacheHit = data?.cache_stats
      ? ((data.cache_stats.order_cache_hit_rate + data.cache_stats.position_cache_hit_rate + data.cache_stats.historical_cache_hit_rate) / 3)
      : null;

    return [
      {
        label: 'Uptime',
        value: data?.monitoring_service?.running ? 'Online' : 'Offline',
        trend: data?.monitoring_service?.running ? 'up' as const : 'down' as const,
        color: data?.monitoring_service?.running ? '#22c55e' : '#ef4444',
      },
      {
        label: 'Err Rate',
        value: errorRate != null ? `${errorRate.toFixed(1)}%` : '—',
        trend: errorRate != null ? (errorRate > 5 ? 'down' as const : errorRate > 1 ? 'neutral' as const : 'up' as const) : 'neutral' as const,
        color: errorRate != null ? (errorRate > 5 ? '#ef4444' : errorRate > 1 ? '#eab308' : '#22c55e') : undefined,
      },
      {
        label: 'Response',
        value: avgResponse != null ? `${avgResponse}ms` : '—',
        trend: avgResponse != null ? (avgResponse > 2000 ? 'down' as const : avgResponse > 1000 ? 'neutral' as const : 'up' as const) : 'neutral' as const,
        color: avgResponse != null ? (avgResponse > 2000 ? '#eab308' : undefined) : undefined,
      },
      {
        label: 'Cache Hit',
        value: cacheHit != null ? `${(cacheHit * 100).toFixed(0)}%` : '—',
        trend: cacheHit != null ? (cacheHit > 0.8 ? 'up' as const : cacheHit > 0.5 ? 'neutral' as const : 'down' as const) : 'neutral' as const,
        color: cacheHit != null ? (cacheHit > 0.8 ? '#22c55e' : cacheHit > 0.5 ? '#eab308' : '#ef4444') : undefined,
      },
    ];
  }, [data]);

  // ── Header actions ──────────────────────────────────────────────────
  const headerActions = (
    <div className="flex items-center gap-2">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <RefreshButton loading={loading} onClick={fetch} label="Refresh" variant="outline" size="sm" />
    </div>
  );

  // ── Main Panel (60%) — 24h Event Timeline Hero + Service Status Cards ──
  const mainPanel = (
    <div className="flex flex-col h-full">
      <PanelHeader title="System" panelId="syshealth-main" onRefresh={fetch}>
        <div className="flex flex-col gap-2 p-2 h-full">
          {/* Alert Banner */}
          {(hasOpenCB || hasStaleMonitoring) && (
            <div className="rounded-lg border p-3" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
              <div className="flex items-center gap-2">
                <span className="text-red-400 text-sm">🚨</span>
                <div>
                  <p className="text-[10px] font-semibold text-red-400">System Alert</p>
                  <p className="text-[9px] text-red-400/80">
                    {hasOpenCB && 'Circuit breaker OPEN detected. '}
                    {hasStaleMonitoring && 'Monitoring service stale or errored.'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border p-3" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
              <p className="text-[10px] text-red-400">{error}</p>
            </div>
          )}

          {data && (
            <>
              {/* 24-Hour Event Timeline Hero (~40% of main panel) */}
              <div className="rounded-lg border" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)', minHeight: '200px', maxHeight: '40%' }}>
                <div className="px-3 py-2 border-b" style={{ borderColor: 'var(--color-dark-border)' }}>
                  <span className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold">24-Hour Event Timeline</span>
                </div>
                {(data.events_24h ?? []).length > 0 ? (
                  <div className="space-y-0 overflow-y-auto p-2" style={{ maxHeight: 'calc(100% - 32px)' }}>
                    {data.events_24h.map((evt, i) => (
                      <div key={i} className="flex items-start gap-2 py-1" style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                        <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${
                          evt.severity === 'error' ? 'bg-red-400' : evt.severity === 'warning' ? 'bg-amber-400' : 'bg-blue-400'
                        }`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-[9px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                              {new Date(evt.timestamp).toLocaleTimeString()}
                            </span>
                            <span className="text-[9px] font-mono px-1 py-0.5 rounded" style={{ backgroundColor: 'var(--color-dark-bg)', color: 'var(--color-text-secondary)' }}>
                              {evt.type}
                            </span>
                          </div>
                          <p className="text-[10px] mt-0.5 truncate" style={{ color: 'var(--color-text-primary)' }}>{evt.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center justify-center p-6">
                    <p className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>No events in the last 24 hours.</p>
                  </div>
                )}
              </div>

              {/* Service Status Cards — below the timeline */}
              {/* Monitoring Service */}
              <div className="rounded-lg border p-3" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold">Monitoring Service</span>
                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${data.monitoring_service?.running ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                    {data.monitoring_service?.running ? 'Running' : 'Stopped'}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {(data.monitoring_service?.sub_tasks ?? []).map((task) => (
                    <div key={task.name} className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                      <div className="flex items-center gap-1.5 mb-1">
                        <div className={`w-1.5 h-1.5 rounded-full ${statusDot(task.status)} ${task.status !== 'healthy' ? 'animate-pulse' : ''}`} />
                        <p className="text-[9px] font-mono truncate" style={{ color: 'var(--color-text-secondary)' }}>{task.name}</p>
                      </div>
                      <p className="text-[10px] font-mono" style={{ color: 'var(--color-text-primary)' }}>{formatAge(task.last_cycle)}</p>
                      <p className="text-[8px] mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>every {task.interval_seconds}s</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Trading Scheduler */}
              <div className="rounded-lg border p-3" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
                <span className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold">Trading Scheduler</span>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
                  {[
                    { label: 'Last Signal', value: formatAge(data.trading_scheduler?.last_signal_time) },
                    { label: 'Next Run', value: formatAge(data.trading_scheduler?.next_expected_run) },
                    { label: 'Signals', value: data.trading_scheduler?.signals_last_run ?? '—' },
                    { label: 'Orders', value: data.trading_scheduler?.orders_last_run ?? '—' },
                  ].map(({ label, value }) => (
                    <div key={label} className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                      <p className="text-[8px] mb-0.5" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                      <p className="text-[11px] font-mono" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Background Threads */}
              <div className="rounded-lg border p-3" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
                <span className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold">Background Threads</span>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                  {['quick_price_update', 'full_price_sync'].map((key) => {
                    const thread = (data as any)?.[key] ?? (data as any)?.background_threads?.[key];
                    return (
                      <div key={key} className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                        <p className="text-[10px] font-mono mb-1" style={{ color: 'var(--color-text-primary)' }}>
                          {key === 'quick_price_update' ? 'Quick Price Update' : 'Full Price Sync'}
                        </p>
                        <div className="grid grid-cols-3 gap-1.5 text-[9px]">
                          <div>
                            <p style={{ color: 'var(--color-text-secondary)' }}>Last Run</p>
                            <p className="font-mono" style={{ color: 'var(--color-text-primary)' }}>{thread?.last_run ? formatAge(thread.last_run) : '—'}</p>
                          </div>
                          <div>
                            <p style={{ color: 'var(--color-text-secondary)' }}>Duration</p>
                            <p className="font-mono" style={{ color: 'var(--color-text-primary)' }}>{thread?.duration_s != null ? `${thread.duration_s}s` : '—'}</p>
                          </div>
                          <div>
                            <p style={{ color: 'var(--color-text-secondary)' }}>Symbols</p>
                            <p className="font-mono" style={{ color: 'var(--color-text-primary)' }}>{thread?.symbols_updated ?? thread?.symbols_synced ?? '—'}</p>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Cache Statistics */}
              <div className="rounded-lg border p-3" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
                <span className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold">Cache Statistics</span>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-2">
                  {[
                    { label: 'Order Cache', value: data.cache_stats?.order_cache_hit_rate, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                    { label: 'Position Cache', value: data.cache_stats?.position_cache_hit_rate, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                    { label: 'Historical Cache', value: data.cache_stats?.historical_cache_hit_rate, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                    { label: 'FMP Warm', value: null, custom: true },
                  ].map(({ label, value, fmt, custom }) => (
                    <div key={label} className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                      <p className="text-[8px] mb-0.5" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                      {custom ? (
                        <div>
                          <p className="text-[10px] font-mono" style={{ color: 'var(--color-text-primary)' }}>
                            {data.cache_stats?.fmp_cache_warm_status?.last_warm_time ? formatAge(data.cache_stats.fmp_cache_warm_status.last_warm_time) : '—'}
                          </p>
                          <p className="text-[8px] mt-0.5 font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                            API: {data.cache_stats?.fmp_cache_warm_status?.symbols_from_api ?? 0} / Cache: {data.cache_stats?.fmp_cache_warm_status?.symbols_from_cache ?? 0}
                          </p>
                        </div>
                      ) : (
                        <p className="text-[11px] font-mono" style={{ color: value != null && value > 0.8 ? '#22c55e' : value != null && value > 0.5 ? '#eab308' : 'var(--color-text-primary)' }}>
                          {value != null ? fmt!(value) : '—'}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Side Panel (40%) — Circuit Breakers + CompactMetricRow + eToro API ──
  const sidePanel = (
    <div className="flex flex-col h-full">
      <PanelHeader title="Alerts" panelId="syshealth-side" onRefresh={fetch}>
        <div className="flex flex-col gap-2 p-2 h-full">
          {/* CompactMetricRow: uptime, error rate, response, cache hit */}
          <CompactMetricRow metrics={sideMetrics} />

          {/* Circuit Breaker Cards — prominent, color-coded */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">Circuit Breakers</div>
            <div className="grid grid-cols-1 gap-2">
              {(data?.circuit_breakers ?? []).map((cb) => (
                <div
                  key={cb.category}
                  className="rounded-lg p-3 border"
                  style={{
                    backgroundColor: cbStateBgColor(cb.state),
                    borderColor: cbStateBorderColor(cb.state),
                  }}
                >
                  <div className="flex items-center gap-2 mb-1.5">
                    <div className={`w-3 h-3 rounded-full ${cbStateColor(cb.state)} ${cb.state === 'OPEN' || cb.state === 'open' ? 'animate-pulse' : ''}`} />
                    <span className="text-[11px] font-mono font-semibold capitalize" style={{ color: 'var(--color-text-primary)' }}>{cb.category}</span>
                    <span className={`ml-auto text-[9px] font-mono px-1.5 py-0.5 rounded ${
                      cb.state === 'CLOSED' || cb.state === 'closed' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                      cb.state === 'HALF_OPEN' || cb.state === 'half_open' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
                      'bg-red-500/10 text-red-400 border border-red-500/20'
                    }`}>
                      {cbStateLabel(cb.state)}
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <div>
                      <p className="text-[8px]" style={{ color: 'var(--color-text-secondary)' }}>Failures</p>
                      <p className="text-[11px] font-mono" style={{ color: cb.failure_count > 0 ? '#ef4444' : 'var(--color-text-primary)' }}>
                        {cb.failure_count}
                      </p>
                    </div>
                    {cb.cooldown_remaining_seconds > 0 && (
                      <div>
                        <p className="text-[8px]" style={{ color: 'var(--color-text-secondary)' }}>Cooldown</p>
                        <p className="text-[11px] font-mono text-amber-400">{cb.cooldown_remaining_seconds}s</p>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {(data?.circuit_breakers ?? []).length === 0 && (
                <p className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>No circuit breaker data available.</p>
              )}
            </div>
          </div>

          {/* eToro API Health */}
          {data?.etoro_api && (
            <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
              <div className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold mb-2">eToro API Health</div>
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className="text-[8px]" style={{ color: 'var(--color-text-secondary)' }}>Req/min</p>
                  <p className="text-[11px] font-mono" style={{ color: 'var(--color-text-primary)' }}>{data.etoro_api.requests_per_minute ?? '—'}</p>
                </div>
                <div className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className="text-[8px]" style={{ color: 'var(--color-text-secondary)' }}>Error Rate (5m)</p>
                  <p className="text-[11px] font-mono" style={{ color: (data.etoro_api.error_rate_5m ?? 0) > 5 ? '#ef4444' : '#22c55e' }}>
                    {data.etoro_api.error_rate_5m != null ? `${data.etoro_api.error_rate_5m.toFixed(1)}%` : '—'}
                  </p>
                </div>
                <div className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className="text-[8px]" style={{ color: 'var(--color-text-secondary)' }}>Avg Response</p>
                  <p className="text-[11px] font-mono" style={{ color: (data.etoro_api.avg_response_ms ?? 0) > 2000 ? '#eab308' : 'var(--color-text-primary)' }}>
                    {data.etoro_api.avg_response_ms != null ? `${data.etoro_api.avg_response_ms}ms` : '—'}
                  </p>
                </div>
                <div className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className="text-[8px]" style={{ color: 'var(--color-text-secondary)' }}>Rate Limit Left</p>
                  <p className="text-[11px] font-mono" style={{ color: (data.etoro_api.rate_limit_remaining ?? 100) < 20 ? '#ef4444' : 'var(--color-text-primary)' }}>
                    {data.etoro_api.rate_limit_remaining ?? '—'}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────
  if (loading && !data) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="System Health" description="Backend services, circuit breakers, and API health" actions={headerActions} compact={true}>
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="System Health"
        description="Backend services, circuit breakers, and API health"
        actions={headerActions}
        compact={true}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <RefreshIndicator visible={loading && !!data} />
          <ResizablePanelLayout
            layoutId="system-health-panels"
            direction="horizontal"
            panels={[
              {
                id: 'syshealth-main',
                defaultSize: 60,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'syshealth-side',
                defaultSize: 40,
                minSize: 280,
                content: sidePanel,
              },
            ]}
          />
        </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
