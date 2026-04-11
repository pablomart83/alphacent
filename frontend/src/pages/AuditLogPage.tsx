import { type FC, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { DashboardLayout } from '../components/DashboardLayout';
import { RefreshButton } from '../components/ui/RefreshButton';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { useAuditStore, type AuditLogEntry, type TradeLifecycleData } from '../lib/stores/audit-store';

const EVENT_TYPES = [
  'signal_generated', 'signal_rejected', 'risk_limit_hit',
  'order_submitted', 'order_filled', 'position_opened', 'position_closed',
  'strategy_activated', 'strategy_retired', 'strategy_demoted',
  'circuit_breaker_transition',
];

const SEVERITIES = ['info', 'warning', 'error'];

const severityColor = (s: string) => {
  if (s === 'error') return '#ef4444';
  if (s === 'warning') return '#eab308';
  return '#3b82f6';
};

const severityBg = (s: string) => {
  if (s === 'error') return 'rgba(239,68,68,0.1)';
  if (s === 'warning') return 'rgba(234,179,8,0.1)';
  return 'rgba(59,130,246,0.1)';
};

interface AuditLogPageProps {
  onLogout: () => void;
}

export const AuditLogPage: FC<AuditLogPageProps> = ({ onLogout }) => {
  const {
    entries, totalCount, loading, error, filters,
    setFilter, resetFilters, fetch, loadMore, hasMore,
    fetchTradeLifecycle, tradeLifecycle, tradeLifecycleLoading,
    exportCsv,
  } = useAuditStore();

  const [searchInput, setSearchInput] = useState('');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'log' | 'rejections' | 'lifecycle' | 'risk'>('log');
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const parentRef = useRef<HTMLDivElement>(null);

  // Initial fetch
  useEffect(() => { fetch(); }, []);

  // Debounced search
  const handleSearchChange = useCallback((value: string) => {
    setSearchInput(value);
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setFilter('search', value);
      fetch();
    }, 200);
  }, [setFilter, fetch]);

  // Filter change handlers
  const handleFilterChange = useCallback((key: string, value: any) => {
    setFilter(key as any, value);
    setTimeout(() => fetch(), 0);
  }, [setFilter, fetch]);

  // Virtual scrolling
  const rowVirtualizer = useVirtualizer({
    count: entries.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => expandedRow ? 200 : 44,
    overscan: 20,
  });

  // Infinite scroll
  useEffect(() => {
    const el = parentRef.current;
    if (!el) return;
    const handleScroll = () => {
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 200 && hasMore && !loading) {
        loadMore();
      }
    };
    el.addEventListener('scroll', handleScroll);
    return () => el.removeEventListener('scroll', handleScroll);
  }, [hasMore, loading, loadMore]);

  const handleRowClick = (entry: AuditLogEntry) => {
    if (expandedRow === entry.id) {
      setExpandedRow(null);
    } else {
      setExpandedRow(entry.id);
      if (entry.event_type === 'order_filled' || entry.event_type === 'position_closed' || entry.event_type === 'position_opened') {
        fetchTradeLifecycle(entry.id);
      }
    }
  };

  // Filtered views
  const rejections = useMemo(() => entries.filter(e => e.event_type === 'signal_rejected'), [entries]);
  const lifecycleEvents = useMemo(() => entries.filter(e =>
    ['strategy_activated', 'strategy_retired', 'strategy_demoted'].includes(e.event_type)
  ), [entries]);
  const riskEvents = useMemo(() => entries.filter(e => e.event_type === 'risk_limit_hit'), [entries]);

  return (
    <DashboardLayout onLogout={onLogout}>
      <div className="p-8 space-y-6 relative">
        <RefreshIndicator visible={loading && entries.length > 0} />

        {loading && entries.length === 0 ? (
          <PageSkeleton />
        ) : (
        <>
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-mono" style={{ color: 'var(--color-text-primary)' }}>Audit Log</h2>
            <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
              Decision trail and trade lifecycle events — {totalCount.toLocaleString()} total entries
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={exportCsv}
              className="px-3 py-1.5 rounded-lg text-xs font-mono border transition-colors"
              style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)', backgroundColor: 'transparent' }}
            >
              ↓ Export CSV
            </button>
            <RefreshButton loading={loading} onClick={fetch} label="Refresh" variant="outline" size="sm" />
          </div>
        </div>

        {error && (
          <div className="rounded-lg border p-4" style={{ backgroundColor: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.3)' }}>
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {/* Filters */}
        <div className="rounded-lg border p-4" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <div className="flex flex-wrap items-center gap-3">
            {/* Search */}
            <input
              type="text"
              value={searchInput}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search audit log..."
              className="flex-1 min-w-[200px] px-3 py-1.5 rounded-lg text-sm font-mono border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            />
            {/* Event Type */}
            <select
              value={filters.event_types[0] || ''}
              onChange={(e) => handleFilterChange('event_types', e.target.value ? [e.target.value] : [])}
              className="text-xs font-mono rounded px-2 py-1.5 border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            >
              <option value="">All Events</option>
              {EVENT_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
            </select>
            {/* Severity */}
            <select
              value={filters.severity}
              onChange={(e) => handleFilterChange('severity', e.target.value)}
              className="text-xs font-mono rounded px-2 py-1.5 border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            >
              <option value="">All Severities</option>
              {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            {/* Symbol */}
            <input
              type="text"
              value={filters.symbol}
              onChange={(e) => handleFilterChange('symbol', e.target.value)}
              placeholder="Symbol"
              className="w-24 px-2 py-1.5 rounded text-xs font-mono border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            />
            {/* Strategy */}
            <input
              type="text"
              value={filters.strategy_name}
              onChange={(e) => handleFilterChange('strategy_name', e.target.value)}
              placeholder="Strategy"
              className="w-28 px-2 py-1.5 rounded text-xs font-mono border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            />
            {/* Date Range */}
            <input
              type="date"
              value={filters.start_date}
              onChange={(e) => handleFilterChange('start_date', e.target.value)}
              className="px-2 py-1.5 rounded text-xs font-mono border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            />
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>to</span>
            <input
              type="date"
              value={filters.end_date}
              onChange={(e) => handleFilterChange('end_date', e.target.value)}
              className="px-2 py-1.5 rounded text-xs font-mono border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            />
            <button
              onClick={() => { resetFilters(); setSearchInput(''); fetch(); }}
              className="text-xs font-mono px-2 py-1.5 rounded border"
              style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)' }}
            >
              Reset
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b" style={{ borderColor: 'var(--color-dark-border)' }}>
          {[
            { key: 'log', label: 'All Events', count: entries.length },
            { key: 'rejections', label: 'Signal Rejections', count: rejections.length },
            { key: 'lifecycle', label: 'Strategy Lifecycle', count: lifecycleEvents.length },
            { key: 'risk', label: 'Risk Limits', count: riskEvents.length },
          ].map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key as any)}
              className={`px-4 py-2 text-sm font-mono border-b-2 transition-colors ${
                activeTab === key ? 'border-[#22c55e] text-[#22c55e]' : 'border-transparent'
              }`}
              style={{ color: activeTab === key ? '#22c55e' : 'var(--color-text-secondary)' }}
            >
              {label} <span className="text-xs opacity-60">({count})</span>
            </button>
          ))}
        </div>

        {/* Main Log Table with Virtual Scroll */}
        {activeTab === 'log' && (
          entries.length > 0 ? (
            <div className="rounded-lg border" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
              {/* Table Header */}
              <div className="flex items-center text-xs font-mono py-2 px-4 border-b" style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-dark-bg)' }}>
                <span className="w-[160px] shrink-0">Timestamp</span>
                <span className="w-[140px] shrink-0">Event Type</span>
                <span className="w-[80px] shrink-0">Symbol</span>
                <span className="w-[140px] shrink-0">Strategy</span>
                <span className="w-[70px] shrink-0">Severity</span>
                <span className="flex-1">Description</span>
              </div>
              {/* Virtual scroll container */}
              <div ref={parentRef} className="overflow-y-auto" style={{ height: '500px' }}>
                <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, width: '100%', position: 'relative' }}>
                  {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                    const entry = entries[virtualRow.index];
                    if (!entry) return null;
                    const isExpanded = expandedRow === entry.id;
                    return (
                      <div
                        key={virtualRow.key}
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          width: '100%',
                          transform: `translateY(${virtualRow.start}px)`,
                        }}
                      >
                        <div
                          className="flex items-center text-sm py-2 px-4 cursor-pointer hover:bg-white/[0.02] transition-colors"
                          style={{ borderBottom: '1px solid var(--color-dark-border)' }}
                          onClick={() => handleRowClick(entry)}
                        >
                          <span className="w-[160px] shrink-0 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                            {new Date(entry.timestamp).toLocaleString()}
                          </span>
                          <span className="w-[140px] shrink-0 text-xs font-mono" style={{ color: 'var(--color-text-primary)' }}>
                            {entry.event_type?.replace(/_/g, ' ')}
                          </span>
                          <span className="w-[80px] shrink-0 font-mono text-xs" style={{ color: 'var(--color-text-primary)' }}>
                            {entry.symbol || '—'}
                          </span>
                          <span className="w-[140px] shrink-0 text-xs truncate" style={{ color: 'var(--color-text-secondary)' }}>
                            {entry.strategy_name || '—'}
                          </span>
                          <span className="w-[70px] shrink-0">
                            <span
                              className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                              style={{ backgroundColor: severityBg(entry.severity), color: severityColor(entry.severity) }}
                            >
                              {entry.severity}
                            </span>
                          </span>
                          <span className="flex-1 text-xs truncate" style={{ color: 'var(--color-text-secondary)' }}>
                            {entry.description}
                          </span>
                        </div>
                        {/* Expanded Trade Lifecycle */}
                        {isExpanded && (
                          <TradeLifecycleView data={tradeLifecycle} loading={tradeLifecycleLoading} entry={entry} />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
              {loading && <div className="text-center py-2 text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>Loading more...</div>}
            </div>
          ) : (
            <div className="rounded-lg border p-12 text-center" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
              <p className="text-lg font-mono" style={{ color: 'var(--color-text-secondary)' }}>No audit records</p>
              <p className="text-sm mt-2" style={{ color: 'var(--color-text-secondary)' }}>
                No audit records exist for the selected filters and date range.
              </p>
            </div>
          )
        )}

        {/* Signal Rejections Tab (Req 21.5) */}
        {activeTab === 'rejections' && (
          <div className="rounded-lg border" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            {rejections.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs font-mono border-b" style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-dark-bg)' }}>
                      <th className="text-left py-2 px-4">Timestamp</th>
                      <th className="text-left py-2 px-4">Symbol</th>
                      <th className="text-left py-2 px-4">Strategy</th>
                      <th className="text-left py-2 px-4">Rejection Reason</th>
                      <th className="text-right py-2 px-4">Conviction</th>
                      <th className="text-right py-2 px-4">Strength</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rejections.map((e) => (
                      <tr key={e.id} style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                        <td className="py-2 px-4 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{new Date(e.timestamp).toLocaleString()}</td>
                        <td className="py-2 px-4 font-mono" style={{ color: 'var(--color-text-primary)' }}>{e.symbol || '—'}</td>
                        <td className="py-2 px-4 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{e.strategy_name || '—'}</td>
                        <td className="py-2 px-4 text-xs" style={{ color: '#eab308' }}>{e.metadata?.rejection_reason || e.description}</td>
                        <td className="py-2 px-4 font-mono text-right" style={{ color: 'var(--color-text-primary)' }}>{e.metadata?.conviction_score?.toFixed(2) ?? '—'}</td>
                        <td className="py-2 px-4 font-mono text-right" style={{ color: 'var(--color-text-primary)' }}>{e.metadata?.signal_strength?.toFixed(2) ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center">
                <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>No signal rejections in the current view.</p>
              </div>
            )}
          </div>
        )}

        {/* Strategy Lifecycle Tab (Req 21.6) */}
        {activeTab === 'lifecycle' && (
          <div className="rounded-lg border" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            {lifecycleEvents.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs font-mono border-b" style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-dark-bg)' }}>
                      <th className="text-left py-2 px-4">Timestamp</th>
                      <th className="text-left py-2 px-4">Event</th>
                      <th className="text-left py-2 px-4">Strategy</th>
                      <th className="text-left py-2 px-4">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lifecycleEvents.map((e) => (
                      <tr key={e.id} style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                        <td className="py-2 px-4 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{new Date(e.timestamp).toLocaleString()}</td>
                        <td className="py-2 px-4 font-mono text-xs" style={{ color: e.event_type === 'strategy_activated' ? '#22c55e' : e.event_type === 'strategy_retired' ? '#ef4444' : '#eab308' }}>
                          {e.event_type.replace(/_/g, ' ')}
                        </td>
                        <td className="py-2 px-4 text-xs" style={{ color: 'var(--color-text-primary)' }}>{e.strategy_name || '—'}</td>
                        <td className="py-2 px-4 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{e.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center">
                <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>No strategy lifecycle events in the current view.</p>
              </div>
            )}
          </div>
        )}

        {/* Risk Limit Events Tab (Req 21.7) */}
        {activeTab === 'risk' && (
          <div className="rounded-lg border" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            {riskEvents.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs font-mono border-b" style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-dark-bg)' }}>
                      <th className="text-left py-2 px-4">Timestamp</th>
                      <th className="text-left py-2 px-4">Limit Type</th>
                      <th className="text-left py-2 px-4">Symbol/Sector</th>
                      <th className="text-right py-2 px-4">Exposure</th>
                      <th className="text-right py-2 px-4">Threshold</th>
                      <th className="text-left py-2 px-4">Blocked Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {riskEvents.map((e) => (
                      <tr key={e.id} style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                        <td className="py-2 px-4 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{new Date(e.timestamp).toLocaleString()}</td>
                        <td className="py-2 px-4 font-mono text-xs" style={{ color: '#ef4444' }}>{e.metadata?.limit_type || '—'}</td>
                        <td className="py-2 px-4 font-mono text-xs" style={{ color: 'var(--color-text-primary)' }}>{e.symbol || e.metadata?.sector || '—'}</td>
                        <td className="py-2 px-4 font-mono text-xs text-right" style={{ color: 'var(--color-text-primary)' }}>{e.metadata?.exposure ?? '—'}</td>
                        <td className="py-2 px-4 font-mono text-xs text-right" style={{ color: 'var(--color-text-secondary)' }}>{e.metadata?.threshold ?? '—'}</td>
                        <td className="py-2 px-4 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{e.metadata?.blocked_action || e.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-8 text-center">
                <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>No risk limit events in the current view.</p>
              </div>
            )}
          </div>
        )}
        </>
        )}
      </div>
    </DashboardLayout>
  );
};

// Trade Lifecycle Detail View (Req 21.4)
const TradeLifecycleView: FC<{ data: TradeLifecycleData | null; loading: boolean; entry: AuditLogEntry }> = ({ data, loading, entry }) => {
  if (loading) {
    return (
      <div className="px-8 py-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
        <p className="text-xs font-mono animate-pulse" style={{ color: 'var(--color-text-secondary)' }}>Loading trade lifecycle...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="px-8 py-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
        <p className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>
          Event details: {entry.description}
        </p>
        {entry.metadata && (
          <pre className="text-xs font-mono mt-2 p-2 rounded overflow-x-auto" style={{ backgroundColor: 'var(--color-dark-surface)', color: 'var(--color-text-secondary)' }}>
            {JSON.stringify(entry.metadata, null, 2)}
          </pre>
        )}
      </div>
    );
  }

  const steps = [
    { label: 'Signal', time: data.signal?.timestamp, detail: `Conviction: ${data.signal?.conviction_score?.toFixed(2)}, Strength: ${data.signal?.signal_strength?.toFixed(2)}` },
    { label: 'Risk Validation', time: data.risk_validation?.timestamp, detail: `Size: ${data.risk_validation?.position_size}, Passed: ${data.risk_validation?.checks_passed?.length ?? 0}, Failed: ${data.risk_validation?.checks_failed?.length ?? 0}` },
    { label: 'Order', time: data.order?.timestamp, detail: `${data.order?.type} @ $${data.order?.expected_price?.toFixed(2)}, Qty: ${data.order?.quantity}` },
    { label: 'Fill', time: data.fill?.timestamp, detail: `@ $${data.fill?.fill_price?.toFixed(2)}, Slippage: ${data.fill?.slippage?.toFixed(4)}` },
    { label: 'Position', time: data.position?.opened_at, detail: `SL: $${data.position?.stop_loss?.toFixed(2)}, TP: $${data.position?.take_profit?.toFixed(2)}` },
    ...(data.trailing_stops ?? []).map((ts, i) => ({
      label: `Trailing Stop #${i + 1}`,
      time: ts.timestamp,
      detail: `${ts.old_level?.toFixed(2)} → ${ts.new_level?.toFixed(2)}`,
    })),
    ...(data.close ? [{
      label: 'Close',
      time: data.close.timestamp,
      detail: `${data.close.exit_reason} — P&L: $${data.close.final_pnl?.toFixed(2)} (${data.close.final_pnl_pct?.toFixed(2)}%)`,
    }] : []),
  ].filter(s => s.time);

  return (
    <div className="px-8 py-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
      <p className="text-xs font-mono mb-3" style={{ color: 'var(--color-text-primary)' }}>Trade Lifecycle</p>
      <div className="flex items-start gap-0 overflow-x-auto">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start shrink-0">
            <div className="flex flex-col items-center">
              <div className="w-3 h-3 rounded-full bg-[#22c55e] shrink-0" />
              <div className="w-px h-8 bg-gray-600" />
            </div>
            <div className="ml-2 mr-6 min-w-[120px]">
              <p className="text-xs font-mono font-semibold" style={{ color: 'var(--color-text-primary)' }}>{step.label}</p>
              <p className="text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>{new Date(step.time!).toLocaleString()}</p>
              <p className="text-[10px] mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>{step.detail}</p>
            </div>
            {i < steps.length - 1 && <span className="text-gray-600 mt-0.5 mr-2">→</span>}
          </div>
        ))}
      </div>
    </div>
  );
};
