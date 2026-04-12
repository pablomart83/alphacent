import { type FC, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { motion } from 'framer-motion';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
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

  // Filtered views for sidebar summaries
  const rejections = useMemo(() => entries.filter(e => e.event_type === 'signal_rejected'), [entries]);
  const lifecycleEvents = useMemo(() => entries.filter(e =>
    ['strategy_activated', 'strategy_retired', 'strategy_demoted'].includes(e.event_type)
  ), [entries]);
  const riskEvents = useMemo(() => entries.filter(e => e.event_type === 'risk_limit_hit'), [entries]);
  const warningCount = useMemo(() => entries.filter(e => e.severity === 'warning').length, [entries]);
  const errorCount = useMemo(() => entries.filter(e => e.severity === 'error').length, [entries]);

  // ── Side panel metrics ──────────────────────────────────────────────
  const sideMetrics: CompactMetric[] = useMemo(() => [
    {
      label: 'Events',
      value: entries.length.toLocaleString(),
      trend: 'neutral' as const,
    },
    {
      label: 'Warnings',
      value: warningCount.toLocaleString(),
      trend: warningCount > 0 ? 'down' as const : 'neutral' as const,
      color: warningCount > 0 ? '#eab308' : undefined,
    },
    {
      label: 'Errors',
      value: errorCount.toLocaleString(),
      trend: errorCount > 0 ? 'down' as const : 'neutral' as const,
      color: errorCount > 0 ? '#ef4444' : undefined,
    },
    {
      label: 'Rejections',
      value: rejections.length.toLocaleString(),
      trend: rejections.length > 0 ? 'down' as const : 'neutral' as const,
      color: rejections.length > 0 ? '#eab308' : undefined,
    },
  ], [entries.length, warningCount, errorCount, rejections.length]);

  // ── Header actions ──────────────────────────────────────────────────
  const headerActions = (
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
  );

  // ── Main Panel (65%) — Filters Bar + Audit DenseTable with Virtual Scroll ──
  const mainPanel = (
    <div className="flex flex-col h-full">
      <PanelHeader title="Audit Log" panelId="audit-main" onRefresh={fetch}>
        <div className="flex flex-col h-full">
          {/* Filters Bar */}
          <div className="p-2 border-b" style={{ borderColor: 'var(--color-dark-border)', backgroundColor: 'var(--color-dark-surface)' }}>
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => handleSearchChange(e.target.value)}
                placeholder="Search audit log..."
                className="flex-1 min-w-[150px] px-2 py-1 rounded text-xs font-mono border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              />
              <select
                value={filters.event_types[0] || ''}
                onChange={(e) => handleFilterChange('event_types', e.target.value ? [e.target.value] : [])}
                className="text-[10px] font-mono rounded px-1.5 py-1 border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              >
                <option value="">All Events</option>
                {EVENT_TYPES.map(t => <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>)}
              </select>
              <select
                value={filters.severity}
                onChange={(e) => handleFilterChange('severity', e.target.value)}
                className="text-[10px] font-mono rounded px-1.5 py-1 border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              >
                <option value="">All Severities</option>
                {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
              <input
                type="text"
                value={filters.symbol}
                onChange={(e) => handleFilterChange('symbol', e.target.value)}
                placeholder="Symbol"
                className="w-20 px-1.5 py-1 rounded text-[10px] font-mono border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              />
              <input
                type="text"
                value={filters.strategy_name}
                onChange={(e) => handleFilterChange('strategy_name', e.target.value)}
                placeholder="Strategy"
                className="w-24 px-1.5 py-1 rounded text-[10px] font-mono border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              />
              <input
                type="date"
                value={filters.start_date}
                onChange={(e) => handleFilterChange('start_date', e.target.value)}
                className="px-1.5 py-1 rounded text-[10px] font-mono border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              />
              <span className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>to</span>
              <input
                type="date"
                value={filters.end_date}
                onChange={(e) => handleFilterChange('end_date', e.target.value)}
                className="px-1.5 py-1 rounded text-[10px] font-mono border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              />
              <button
                onClick={() => { resetFilters(); setSearchInput(''); fetch(); }}
                className="text-[10px] font-mono px-1.5 py-1 rounded border"
                style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)' }}
              >
                Reset
              </button>
            </div>
          </div>

          {error && (
            <div className="mx-2 mt-2 rounded-lg border p-2" style={{ backgroundColor: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.3)' }}>
              <p className="text-[10px] text-red-400">{error}</p>
            </div>
          )}

          {/* DenseTable — virtual scroll audit log */}
          {entries.length > 0 ? (
            <div className="flex-1 min-h-0 flex flex-col">
              {/* Table Header */}
              <div className="flex items-center text-[10px] font-mono py-1.5 px-3 border-b" style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)', backgroundColor: 'var(--color-dark-bg)' }}>
                <span className="w-[140px] shrink-0">Timestamp</span>
                <span className="w-[120px] shrink-0">Event Type</span>
                <span className="w-[70px] shrink-0">Symbol</span>
                <span className="w-[120px] shrink-0">Strategy</span>
                <span className="w-[60px] shrink-0">Severity</span>
                <span className="flex-1">Description</span>
              </div>
              {/* Virtual scroll container */}
              <div ref={parentRef} className="flex-1 overflow-y-auto min-h-0">
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
                          className="flex items-center text-xs py-1 px-3 cursor-pointer hover:bg-white/[0.02] transition-colors"
                          style={{ borderBottom: '1px solid var(--color-dark-border)', height: '32px' }}
                          onClick={() => handleRowClick(entry)}
                        >
                          <span className="w-[140px] shrink-0 font-mono text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                            {new Date(entry.timestamp).toLocaleString()}
                          </span>
                          <span className="w-[120px] shrink-0 text-[10px] font-mono" style={{ color: 'var(--color-text-primary)' }}>
                            {entry.event_type?.replace(/_/g, ' ')}
                          </span>
                          <span className="w-[70px] shrink-0 font-mono text-[10px]" style={{ color: 'var(--color-text-primary)' }}>
                            {entry.symbol || '—'}
                          </span>
                          <span className="w-[120px] shrink-0 text-[10px] truncate" style={{ color: 'var(--color-text-secondary)' }}>
                            {entry.strategy_name || '—'}
                          </span>
                          <span className="w-[60px] shrink-0">
                            <span
                              className="text-[10px] font-mono px-1 py-0.5 rounded"
                              style={{ backgroundColor: severityBg(entry.severity), color: severityColor(entry.severity) }}
                            >
                              {entry.severity}
                            </span>
                          </span>
                          <span className="flex-1 text-[10px] truncate" style={{ color: 'var(--color-text-secondary)' }}>
                            {entry.description}
                          </span>
                        </div>
                        {isExpanded && (
                          <TradeLifecycleView data={tradeLifecycle} loading={tradeLifecycleLoading} entry={entry} />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
              {loading && <div className="text-center py-1 text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>Loading more...</div>}
              <div className="px-3 py-1 border-t text-[10px] font-mono" style={{ borderColor: 'var(--color-dark-border)', color: 'var(--color-text-secondary)' }}>
                {totalCount.toLocaleString()} total entries
              </div>
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <p className="text-sm font-mono" style={{ color: 'var(--color-text-secondary)' }}>No audit records</p>
                <p className="text-[10px] mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                  No audit records exist for the selected filters and date range.
                </p>
              </div>
            </div>
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Side Panel (35%) — CompactMetricRow + Summary Sections ──
  const sidePanel = (
    <div className="flex flex-col h-full">
      <PanelHeader title="Summary" panelId="audit-side" onRefresh={fetch}>
        <div className="flex flex-col gap-2 p-2 h-full">
          {/* CompactMetricRow: events today, warnings, errors, rejections */}
          <CompactMetricRow metrics={sideMetrics} />

          {/* Signal Rejections Summary */}
          <div className="border border-[var(--color-dark-border)] rounded-lg">
            <div className="px-3 py-1.5 border-b" style={{ borderColor: 'var(--color-dark-border)', backgroundColor: 'var(--color-dark-bg)' }}>
              <span className="text-[11px] text-gray-500 tracking-wide font-medium">Signal Rejections</span>
              <span className="ml-2 text-[10px] font-mono" style={{ color: '#eab308' }}>({rejections.length})</span>
            </div>
            {rejections.length > 0 ? (
              <div className="overflow-y-auto" style={{ maxHeight: '180px' }}>
                {rejections.slice(0, 10).map((e) => (
                  <div key={e.id} className="px-3 py-1.5" style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-primary)' }}>{e.symbol || '—'}</span>
                      <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                        {new Date(e.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <p className="text-[10px] mt-0.5 truncate" style={{ color: '#eab308' }}>
                      {e.metadata?.rejection_reason || e.description}
                    </p>
                    <div className="flex gap-3 mt-0.5">
                      <span className="text-[8px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                        Conv: {e.metadata?.conviction_score?.toFixed(2) ?? '—'}
                      </span>
                      <span className="text-[8px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                        Str: {e.metadata?.signal_strength?.toFixed(2) ?? '—'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 text-center">
                <p className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>No signal rejections.</p>
              </div>
            )}
          </div>

          {/* Lifecycle Events Summary */}
          <div className="border border-[var(--color-dark-border)] rounded-lg">
            <div className="px-3 py-1.5 border-b" style={{ borderColor: 'var(--color-dark-border)', backgroundColor: 'var(--color-dark-bg)' }}>
              <span className="text-[11px] text-gray-500 tracking-wide font-medium">Lifecycle Events</span>
              <span className="ml-2 text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>({lifecycleEvents.length})</span>
            </div>
            {lifecycleEvents.length > 0 ? (
              <div className="overflow-y-auto" style={{ maxHeight: '180px' }}>
                {lifecycleEvents.slice(0, 10).map((e) => (
                  <div key={e.id} className="px-3 py-1.5" style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                    <div className="flex items-center justify-between">
                      <span
                        className="text-[10px] font-mono"
                        style={{
                          color: e.event_type === 'strategy_activated' ? '#22c55e'
                            : e.event_type === 'strategy_retired' ? '#ef4444'
                            : '#eab308'
                        }}
                      >
                        {e.event_type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                        {new Date(e.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <p className="text-[10px] mt-0.5 truncate" style={{ color: 'var(--color-text-primary)' }}>
                      {e.strategy_name || '—'}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 text-center">
                <p className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>No lifecycle events.</p>
              </div>
            )}
          </div>

          {/* Risk Limit Events Summary */}
          <div className="border border-[var(--color-dark-border)] rounded-lg">
            <div className="px-3 py-1.5 border-b" style={{ borderColor: 'var(--color-dark-border)', backgroundColor: 'var(--color-dark-bg)' }}>
              <span className="text-[11px] text-gray-500 tracking-wide font-medium">Risk Limit Events</span>
              <span className="ml-2 text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>({riskEvents.length})</span>
            </div>
            {riskEvents.length > 0 ? (
              <div className="overflow-y-auto" style={{ maxHeight: '180px' }}>
                {riskEvents.slice(0, 10).map((e) => (
                  <div key={e.id} className="px-3 py-1.5" style={{ borderBottom: '1px solid var(--color-dark-border)' }}>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono" style={{ color: '#ef4444' }}>
                        {e.metadata?.limit_type || 'risk limit'}
                      </span>
                      <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                        {new Date(e.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="flex gap-3 mt-0.5">
                      <span className="text-[10px] font-mono" style={{ color: 'var(--color-text-primary)' }}>
                        {e.symbol || e.metadata?.sector || '—'}
                      </span>
                      {e.metadata?.exposure != null && (
                        <span className="text-[8px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                          Exp: {e.metadata.exposure}
                        </span>
                      )}
                      {e.metadata?.threshold != null && (
                        <span className="text-[8px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                          Thr: {e.metadata.threshold}
                        </span>
                      )}
                    </div>
                    <p className="text-[8px] mt-0.5 truncate" style={{ color: 'var(--color-text-secondary)' }}>
                      {e.metadata?.blocked_action || e.description}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 text-center">
                <p className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>No risk limit events.</p>
              </div>
            )}
          </div>
        </div>
      </PanelHeader>
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────
  if (loading && entries.length === 0) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="Audit Log" description="Decision trail and trade lifecycle events" actions={headerActions} compact={true}>
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="Audit Log"
        description={`Decision trail and trade lifecycle events — ${totalCount.toLocaleString()} total entries`}
        actions={headerActions}
        compact={true}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <RefreshIndicator visible={loading && entries.length > 0} />
          <ResizablePanelLayout
            layoutId="audit-log-panels"
            direction="horizontal"
            panels={[
              {
                id: 'audit-main',
                defaultSize: 65,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'audit-side',
                defaultSize: 35,
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

// Trade Lifecycle Detail View (preserved from original)
const TradeLifecycleView: FC<{ data: TradeLifecycleData | null; loading: boolean; entry: AuditLogEntry }> = ({ data, loading, entry }) => {
  if (loading) {
    return (
      <div className="px-6 py-3" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
        <p className="text-[10px] font-mono animate-pulse" style={{ color: 'var(--color-text-secondary)' }}>Loading trade lifecycle...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="px-6 py-3" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
        <p className="text-[10px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>
          Event details: {entry.description}
        </p>
        {entry.metadata && (
          <pre className="text-[10px] font-mono mt-1.5 p-2 rounded overflow-x-auto" style={{ backgroundColor: 'var(--color-dark-surface)', color: 'var(--color-text-secondary)' }}>
            {JSON.stringify(entry.metadata, null, 2)}
          </pre>
        )}
      </div>
    );
  }

  const steps = [
    { label: 'Signal', time: data.signal?.timestamp, detail: `Conviction: ${data.signal?.conviction_score?.toFixed(2)}, Strength: ${data.signal?.signal_strength?.toFixed(2)}` },
    { label: 'Risk Validation', time: data.risk_validation?.timestamp, detail: `Size: ${data.risk_validation?.position_size}, Passed: ${data.risk_validation?.checks_passed?.length ?? 0}, Failed: ${data.risk_validation?.checks_failed?.length ?? 0}` },
    { label: 'Order', time: data.order?.timestamp, detail: `${data.order?.type} @ ${data.order?.expected_price?.toFixed(2)}, Qty: ${data.order?.quantity}` },
    { label: 'Fill', time: data.fill?.timestamp, detail: `@ ${data.fill?.fill_price?.toFixed(2)}, Slippage: ${data.fill?.slippage?.toFixed(4)}` },
    { label: 'Position', time: data.position?.opened_at, detail: `SL: ${data.position?.stop_loss?.toFixed(2)}, TP: ${data.position?.take_profit?.toFixed(2)}` },
    ...(data.trailing_stops ?? []).map((ts, i) => ({
      label: `Trailing Stop #${i + 1}`,
      time: ts.timestamp,
      detail: `${ts.old_level?.toFixed(2)} → ${ts.new_level?.toFixed(2)}`,
    })),
    ...(data.close ? [{
      label: 'Close',
      time: data.close.timestamp,
      detail: `${data.close.exit_reason} — P&L: ${data.close.final_pnl?.toFixed(2)} (${data.close.final_pnl_pct?.toFixed(2)}%)`,
    }] : []),
  ].filter(s => s.time);

  return (
    <div className="px-6 py-3" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
      <p className="text-[10px] font-mono mb-2" style={{ color: 'var(--color-text-primary)' }}>Trade Lifecycle</p>
      <div className="flex items-start gap-0 overflow-x-auto">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start shrink-0">
            <div className="flex flex-col items-center">
              <div className="w-2.5 h-2.5 rounded-full bg-[#22c55e] shrink-0" />
              <div className="w-px h-6 bg-gray-600" />
            </div>
            <div className="ml-1.5 mr-4 min-w-[100px]">
              <p className="text-[10px] font-mono font-semibold" style={{ color: 'var(--color-text-primary)' }}>{step.label}</p>
              <p className="text-[8px] font-mono" style={{ color: 'var(--color-text-secondary)' }}>{new Date(step.time!).toLocaleString()}</p>
              <p className="text-[8px] mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>{step.detail}</p>
            </div>
            {i < steps.length - 1 && <span className="text-gray-600 mt-0.5 mr-1">→</span>}
          </div>
        ))}
      </div>
    </div>
  );
};
