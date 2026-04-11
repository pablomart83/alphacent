import { type FC, useEffect } from 'react';
import { DashboardLayout } from '../components/DashboardLayout';
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
  useWebSocketConnection(); // Keep WS connection active for skipWhenWsConnected

  usePolling({ fetchFn: fetch, intervalMs: 15000, enabled: true, skipWhenWsConnected: true });

  // WS-driven updates
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

  return (
    <DashboardLayout onLogout={onLogout}>
      <div className="p-8 space-y-6 relative">
        <RefreshIndicator visible={loading && !!data} />

        {loading && !data ? (
          <PageSkeleton />
        ) : (
        <>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-mono" style={{ color: 'var(--color-text-primary)' }}>System Health</h2>
            <div className="flex items-center gap-3 mt-1">
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                Backend services, circuit breakers, and API health
              </p>
              <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
            </div>
          </div>
          <RefreshButton loading={loading} onClick={fetch} label="Refresh" variant="outline" size="sm" />
        </div>

        {/* Alert Banner */}
        {(hasOpenCB || hasStaleMonitoring) && (
          <div className="rounded-lg border p-4" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
            <div className="flex items-center gap-2">
              <span className="text-red-400 text-lg">🚨</span>
              <div>
                <p className="text-sm font-semibold text-red-400">System Alert</p>
                <p className="text-xs text-red-400/80">
                  {hasOpenCB && 'Circuit breaker OPEN detected. '}
                  {hasStaleMonitoring && 'Monitoring service stale or errored.'}
                </p>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-lg border p-4" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {data && (
          <>
          {/* Circuit Breakers (Req 17.2) */}
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Circuit Breakers</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {(data.circuit_breakers ?? []).map((cb) => (
                <div key={cb.category} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-3 h-3 rounded-full ${cbStateColor(cb.state)} ${cb.state === 'OPEN' || cb.state === 'open' ? 'animate-pulse' : ''}`} />
                    <span className="text-sm font-mono capitalize" style={{ color: 'var(--color-text-primary)' }}>{cb.category}</span>
                  </div>
                  <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    State: <span className="font-mono">{cbStateLabel(cb.state)}</span>
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                    Failures: <span className="font-mono" style={{ color: cb.failure_count > 0 ? '#ef4444' : 'var(--color-text-primary)' }}>{cb.failure_count}</span>
                  </p>
                  {cb.cooldown_remaining_seconds > 0 && (
                    <p className="text-xs mt-1 font-mono text-amber-400">
                      Cooldown: {cb.cooldown_remaining_seconds}s
                    </p>
                  )}
                </div>
              ))}
              {(data.circuit_breakers ?? []).length === 0 && (
                <p className="text-sm col-span-3" style={{ color: 'var(--color-text-secondary)' }}>No circuit breaker data available.</p>
              )}
            </div>
          </div>

          {/* Monitoring Service (Req 17.3) */}
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <div className="flex items-center gap-2 mb-4">
              <h3 className="text-lg font-mono" style={{ color: 'var(--color-text-primary)' }}>Monitoring Service</h3>
              <span className={`text-xs font-mono px-2 py-0.5 rounded ${data.monitoring_service?.running ? 'bg-green-500/10 text-green-400 border border-green-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'}`}>
                {data.monitoring_service?.running ? 'Running' : 'Stopped'}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {(data.monitoring_service?.sub_tasks ?? []).map((task) => (
                <div key={task.name} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <div className="flex items-center gap-2 mb-2">
                    <div className={`w-2 h-2 rounded-full ${statusDot(task.status)} ${task.status !== 'healthy' ? 'animate-pulse' : ''}`} />
                    <p className="text-xs font-mono truncate" style={{ color: 'var(--color-text-secondary)' }}>{task.name}</p>
                  </div>
                  <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>{formatAge(task.last_cycle)}</p>
                  <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>every {task.interval_seconds}s</p>
                </div>
              ))}
            </div>
          </div>

          {/* Trading Scheduler (Req 17.4) */}
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Trading Scheduler</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: 'Last Signal Time', value: formatAge(data.trading_scheduler?.last_signal_time) },
                { label: 'Next Run', value: formatAge(data.trading_scheduler?.next_expected_run) },
                { label: 'Signals Last Run', value: data.trading_scheduler?.signals_last_run ?? '—' },
                { label: 'Orders Last Run', value: data.trading_scheduler?.orders_last_run ?? '—' },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                  <p className="text-lg font-mono" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* eToro API Health (Req 17.5) */}
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>eToro API Health</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Req/min</p>
                <p className="text-xl font-mono" style={{ color: 'var(--color-text-primary)' }}>{data.etoro_api?.requests_per_minute ?? '—'}</p>
              </div>
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Error Rate (5m)</p>
                <p className="text-xl font-mono" style={{ color: (data.etoro_api?.error_rate_5m ?? 0) > 5 ? '#ef4444' : '#22c55e' }}>
                  {data.etoro_api?.error_rate_5m != null ? `${data.etoro_api.error_rate_5m.toFixed(1)}%` : '—'}
                </p>
              </div>
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Avg Response</p>
                <p className="text-xl font-mono" style={{ color: (data.etoro_api?.avg_response_ms ?? 0) > 2000 ? '#eab308' : 'var(--color-text-primary)' }}>
                  {data.etoro_api?.avg_response_ms != null ? `${data.etoro_api.avg_response_ms}ms` : '—'}
                </p>
              </div>
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Rate Limit Left</p>
                <p className="text-xl font-mono" style={{ color: (data.etoro_api?.rate_limit_remaining ?? 100) < 20 ? '#ef4444' : 'var(--color-text-primary)' }}>
                  {data.etoro_api?.rate_limit_remaining ?? '—'}
                </p>
              </div>
            </div>
          </div>

          {/* Background Threads (Req 17.6) */}
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Background Threads</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {['quick_price_update', 'full_price_sync'].map((key) => {
                const thread = (data as any)?.[key] ?? (data as any)?.background_threads?.[key];
                return (
                  <div key={key} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-sm font-mono mb-2" style={{ color: 'var(--color-text-primary)' }}>
                      {key === 'quick_price_update' ? 'Quick Price Update' : 'Full Price Sync'}
                    </p>
                    <div className="grid grid-cols-3 gap-2 text-xs">
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

          {/* Cache Statistics (Req 17.7) */}
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Cache Statistics</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: 'Order Cache Hit Rate', value: data.cache_stats?.order_cache_hit_rate, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                { label: 'Position Cache Hit Rate', value: data.cache_stats?.position_cache_hit_rate, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                { label: 'Historical Cache Hit Rate', value: data.cache_stats?.historical_cache_hit_rate, fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
                { label: 'FMP Warm Status', value: null, custom: true },
              ].map(({ label, value, fmt, custom }) => (
                <div key={label} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                  {custom ? (
                    <div>
                      <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                        {data.cache_stats?.fmp_cache_warm_status?.last_warm_time ? formatAge(data.cache_stats.fmp_cache_warm_status.last_warm_time) : '—'}
                      </p>
                      <p className="text-xs mt-1 font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                        API: {data.cache_stats?.fmp_cache_warm_status?.symbols_from_api ?? 0} / Cache: {data.cache_stats?.fmp_cache_warm_status?.symbols_from_cache ?? 0}
                      </p>
                    </div>
                  ) : (
                    <p className="text-xl font-mono" style={{ color: value != null && value > 0.8 ? '#22c55e' : value != null && value > 0.5 ? '#eab308' : 'var(--color-text-primary)' }}>
                      {value != null ? fmt!(value) : '—'}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* 24-Hour Event Timeline (Req 17.9) */}
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>24-Hour Event Timeline</h3>
            {(data.events_24h ?? []).length > 0 ? (
              <div className="space-y-1 max-h-[300px] overflow-y-auto">
                {data.events_24h.map((evt, i) => (
                  <div key={i} className="flex items-start gap-3 py-1.5" style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                    <span className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${
                      evt.severity === 'error' ? 'bg-red-400' : evt.severity === 'warning' ? 'bg-amber-400' : 'bg-blue-400'
                    }`} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                          {new Date(evt.timestamp).toLocaleTimeString()}
                        </span>
                        <span className="text-xs font-mono px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--color-dark-bg)', color: 'var(--color-text-secondary)' }}>
                          {evt.type}
                        </span>
                      </div>
                      <p className="text-sm mt-0.5 truncate" style={{ color: 'var(--color-text-primary)' }}>{evt.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>No events in the last 24 hours.</p>
            )}
          </div>
          </>
        )}
        </>
        )}
      </div>
    </DashboardLayout>
  );
};
