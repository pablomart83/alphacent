import { type FC, useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, RefreshCw, AlertCircle } from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { SectionLabel } from '../components/ui/SectionLabel';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { AssetPlot } from '../components/charts/AssetPlot';
import { TvChart } from '../components/charts/TvChart';
import { InteractiveChart } from '../components/charts/InteractiveChart';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { classifyError } from '../lib/errors';
import { colors as designColors } from '../lib/design-tokens';
import { PageSkeleton } from '../components/ui/skeleton';
import { useMarketData, useWebSocketConnection } from '../hooks/useWebSocket';

interface PositionDetailViewProps {
  onLogout: () => void;
}

export const PositionDetailView: FC<PositionDetailViewProps> = ({ onLogout }) => {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);

  // Multi-timeframe data: 1d, 4h, 1h
  const [mtfData, setMtfData] = useState<Record<string, any[]>>({});
  const [mtfLoading, setMtfLoading] = useState(false);

  // Real-time price streaming via WebSocket
  const wsConnected = useWebSocketConnection();
  const marketTick = useMarketData(symbol);
  const [livePriceData, setLivePriceData] = useState<Array<{ date: string; price: number }>>([]);
  const lastTickRef = useRef<string | null>(null);

  // Append live price ticks to chart data
  useEffect(() => {
    if (!marketTick || !symbol) return;
    const tickData = marketTick as any;
    const price = tickData.price ?? tickData.data?.price;
    const ts = tickData.timestamp ?? tickData.data?.timestamp;
    if (typeof price !== 'number' || !ts) return;

    // Deduplicate by timestamp
    const tsKey = String(ts);
    if (tsKey === lastTickRef.current) return;
    lastTickRef.current = tsKey;

    const dateStr = new Date(ts).toISOString().slice(0, 10);

    setLivePriceData((prev) => {
      // Update existing date or append
      const existing = prev.findIndex((p) => p.date === dateStr);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = { date: dateStr, price };
        return updated;
      }
      return [...prev, { date: dateStr, price }];
    });

    // Also update position current_price in detail state
    setDetail((prev: any) => {
      if (!prev?.position) return prev;
      return {
        ...prev,
        position: { ...prev.position, current_price: price },
      };
    });
  }, [marketTick, symbol]);

  const fetchDetail = useCallback(async () => {
    if (!tradingMode || !symbol) return;
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.getPositionDetail(symbol, tradingMode, '1d');
      setDetail(data);
      setLivePriceData([]); // Reset live ticks on fresh fetch
      lastTickRef.current = null;

      // Fetch multi-timeframe data in background (non-blocking)
      setMtfLoading(true);
      Promise.all([
        apiClient.getPositionDetail(symbol, tradingMode, '4h').catch(() => null),
        apiClient.getPositionDetail(symbol, tradingMode, '1h').catch(() => null),
      ]).then(([data4h, data1h]) => {
        setMtfData({
          '1d': data?.price_history || [],
          '4h': data4h?.price_history || [],
          '1h': data1h?.price_history || [],
        });
        setMtfLoading(false);
      });
    } catch (err) {
      const classified = classifyError(err, 'position detail');
      setError(classified.message);
    } finally {
      setLoading(false);
    }
  }, [tradingMode, symbol]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title={`◆ ${symbol || 'Position'}`} description="Position Detail">
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  const priceData = (() => {
    const base = detail?.price_history || [];
    if (livePriceData.length === 0) return base;
    // Merge live ticks: override matching dates, append new ones
    const map = new Map<string, number>();
    for (const p of base) map.set(p.date, p.price);
    for (const p of livePriceData) map.set(p.date, p.price);
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, price]) => ({ date, price }));
  })();
  const orders = detail?.orders || [];
  const pnlHistory = detail?.pnl_history || [];
  const position = detail?.position;
  const hasOrders = orders.length > 0;
  const isLive = wsConnected && !!symbol;

  const headerActions = (
    <div className="flex items-center gap-2">
      <Button variant="ghost" size="sm" onClick={() => navigate('/portfolio')} className="gap-2">
        <ArrowLeft className="h-4 w-4" />
        Back
      </Button>
      <Button variant="outline" size="sm" onClick={fetchDetail} className="gap-2">
        <RefreshCw className="h-4 w-4" />
        Refresh
      </Button>
    </div>
  );

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title={`◆ ${symbol || 'Position'}`}
        description="Position Detail"
        actions={headerActions}
      >
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto"
      >

        {error ? (
          <div className="border border-accent-red/30 bg-accent-red/5 rounded-md p-6">
            <div className="flex flex-col items-center text-center py-8">
              <AlertCircle className="h-12 w-12 text-accent-red mb-4" />
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button variant="outline" onClick={fetchDetail} className="gap-2">
                <RefreshCw className="h-4 w-4" />
                Retry
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Position Summary */}
            {position && (
              <>
                <SectionLabel>Position Summary</SectionLabel>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                  <div className="border border-border rounded-md px-3 pt-3 pb-2">
                    <p className="text-xs text-muted-foreground mb-1">Side</p>
                    <Badge className={cn(
                      'font-mono text-xs',
                      position.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'
                    )}>
                      {position.side}
                    </Badge>
                  </div>
                  <div className="border border-border rounded-md px-3 pt-3 pb-2">
                    <p className="text-xs text-muted-foreground mb-1">Entry Price</p>
                    <p className="text-[13px] font-bold font-mono">{formatCurrency(position.entry_price || 0)}</p>
                  </div>
                  <div className="border border-border rounded-md px-3 pt-3 pb-2">
                    <p className="text-xs text-muted-foreground mb-1">Current Price</p>
                    <p className="text-[13px] font-bold font-mono">{formatCurrency(position.current_price || 0)}</p>
                  </div>
                  <div className="border border-border rounded-md px-3 pt-3 pb-2">
                    <p className="text-xs text-muted-foreground mb-1">Unrealized P&L</p>
                    <p className={cn('text-[13px] font-bold font-mono', (position.unrealized_pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                      {formatCurrency(position.unrealized_pnl || 0)}
                    </p>
                  </div>
                  <div className="border border-border rounded-md px-3 pt-3 pb-2">
                    <p className="text-xs text-muted-foreground mb-1">P&L %</p>
                    <p className={cn('text-[13px] font-bold font-mono', (position.unrealized_pnl_percent || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                      {formatPercentage(position.unrealized_pnl_percent || 0)}
                    </p>
                  </div>
                  <div className="border border-border rounded-md px-3 pt-3 pb-2">
                    <p className="text-xs text-muted-foreground mb-1">Strategy</p>
                    <p className="text-[13px] font-mono text-gray-300 truncate">{position.strategy_name || position.strategy_id?.slice(0, 8) || '—'}</p>
                  </div>
                </div>
              </>
            )}

            {/* Asset Plot — Price Chart with Order Annotations */}
            <div className="border border-border rounded-md p-4">
              <div className="flex items-center justify-between mb-1.5">
                <div>
                  <SectionLabel className="mb-0">Price Chart — {symbol}</SectionLabel>
                  <p className="text-xs text-muted-foreground">Price over holding period with buy/sell annotations</p>
                </div>
                <div className="flex items-center gap-2">
                  {isLive ? (
                    <Badge className="text-xs font-mono bg-accent-green/20 text-accent-green border-accent-green/30 gap-1">
                      <span className="relative flex h-1.5 w-1.5">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-green opacity-75" />
                        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-accent-green" />
                      </span>
                      Live
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="text-xs font-mono gap-1">
                      <span className="inline-flex rounded-full h-1.5 w-1.5 bg-gray-500" />
                      Paused
                    </Badge>
                  )}
                  {!hasOrders && (
                    <Badge variant="secondary" className="text-xs font-mono">Order history unavailable</Badge>
                  )}
                </div>
              </div>
              {priceData.length > 0 ? (
                <AssetPlot
                  priceData={priceData}
                  orders={orders.map((o: any) => ({
                    date: o.date || o.created_at,
                    price: o.price || o.fill_price,
                    side: o.side,
                    quantity: o.quantity,
                  }))}
                  symbol={symbol || ''}
                  height={350}
                />
              ) : (
                <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
                  No price data available for {symbol}
                </div>
              )}
            </div>

            {/* Multi-Timeframe View — 2×2 grid of synchronized charts */}
            <div className="border border-border rounded-md p-3">
              <div className="flex items-center justify-between mb-2">
                <SectionLabel className="mb-0">Multi-Timeframe — {symbol}</SectionLabel>
                {mtfLoading && <span className="text-[10px] text-gray-500 font-mono">Loading...</span>}
              </div>
              <div className="grid grid-cols-2 gap-1">
                {(['1d', '4h', '1h'] as const).map((tf) => {
                  const tfData = tf === '1d' ? (detail?.price_history || []) : (mtfData[tf] || []);
                  const series = tfData.length > 0 ? [{
                    id: `price_${tf}`,
                    type: 'area' as const,
                    data: tfData.map((d: any) => ({
                      time: d.date?.slice(0, 10) || d.date,
                      value: d.close ?? d.price ?? 0,
                    })).filter((d: any) => d.value > 0),
                    lineColor: '#3b82f6',
                    topColor: 'rgba(59,130,246,0.15)',
                    bottomColor: 'transparent',
                    lineWidth: 1,
                  }] : [];
                  return (
                    <div key={tf} className="rounded border border-[var(--color-dark-border)] overflow-hidden">
                      <div className="px-2 py-0.5 bg-[var(--color-dark-surface)] border-b border-[var(--color-dark-border)]">
                        <span className="text-[10px] font-mono text-gray-400">{tf.toUpperCase()}</span>
                      </div>
                      {series.length > 0 ? (
                        <TvChart height={120} series={series} showTimeScale={false} showPriceScale={true} />
                      ) : (
                        <div className="flex items-center justify-center h-[120px] text-[10px] text-gray-600 font-mono">
                          {mtfLoading ? 'Loading...' : 'No data'}
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* 4th pane: P&L chart */}
                <div className="rounded border border-[var(--color-dark-border)] overflow-hidden">
                  <div className="px-2 py-0.5 bg-[var(--color-dark-surface)] border-b border-[var(--color-dark-border)]">
                    <span className="text-[10px] font-mono text-gray-400">P&L</span>
                  </div>
                  {(detail?.pnl_series || []).length > 0 ? (
                    <TvChart
                      height={120}
                      series={[{
                        id: 'pnl_mtf',
                        type: 'baseline',
                        data: (detail.pnl_series || []).map((d: any) => ({
                          time: d.date?.slice(0, 10),
                          value: d.pnl ?? 0,
                        })).filter((d: any) => d.time),
                        baseValue: 0,
                        topFillColor1: 'rgba(34,197,94,0.2)',
                        topFillColor2: 'rgba(34,197,94,0.02)',
                        bottomFillColor1: 'rgba(239,68,68,0.02)',
                        bottomFillColor2: 'rgba(239,68,68,0.2)',
                        topLineColor: '#22c55e',
                        bottomLineColor: '#ef4444',
                        lineWidth: 1,
                      }]}
                      showTimeScale={false}
                    />
                  ) : (
                    <div className="flex items-center justify-center h-[120px] text-[10px] text-gray-600 font-mono">No P&L data</div>
                  )}
                </div>
              </div>
            </div>

            {/* P&L Time-Series Chart */}
            <div className="border border-border rounded-md p-4">
              <SectionLabel>P&L Over Time</SectionLabel>              <p className="text-xs text-muted-foreground mb-2">Unrealized P&L for this position over its holding period</p>
              {pnlHistory.length > 0 ? (
                <InteractiveChart
                  data={pnlHistory}
                  dataKeys={[{ key: 'pnl', color: designColors.green, type: 'area' }]}
                  xAxisKey="date"
                  height={250}
                  tooltipFormatter={(v: number) => [formatCurrency(v), 'P&L']}
                />
              ) : priceData.length > 0 && position ? (
                <InteractiveChart
                  data={priceData.map((p: any) => ({
                    date: p.date,
                    pnl: ((p.price - (position.entry_price || p.price)) / (position.entry_price || 1)) * (position.invested_amount || position.quantity || 100),
                  }))}
                  dataKeys={[{ key: 'pnl', color: designColors.green, type: 'area' }]}
                  xAxisKey="date"
                  height={250}
                  tooltipFormatter={(v: number) => [formatCurrency(v), 'P&L']}
                />
              ) : (
                <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
                  No P&L history available
                </div>
              )}
            </div>

            {/* Order History Table */}
            {hasOrders && (
              <div className="border border-border rounded-md p-4">
                <SectionLabel>Order History</SectionLabel>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono table-dense">
                    <thead>
                      <tr className="border-b border-dark-border text-muted-foreground">
                        <th className="py-2 px-2 text-left">Date</th>
                        <th className="py-2 px-2 text-left">Side</th>
                        <th className="py-2 px-2 text-right">Quantity</th>
                        <th className="py-2 px-2 text-right">Price</th>
                        <th className="py-2 px-2 text-left">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map((o: any, idx: number) => (
                        <tr key={idx} className="border-b border-dark-border/30 hover:bg-dark-hover/50">
                          <td className="py-2 px-2 text-muted-foreground">{o.date || o.created_at ? new Date(o.date || o.created_at).toLocaleString() : '—'}</td>
                          <td className="py-2 px-2">
                            <span className={cn(o.side === 'BUY' ? 'text-accent-green' : 'text-accent-red')}>{o.side}</span>
                          </td>
                          <td className="py-2 px-2 text-right">{o.quantity?.toFixed(2) ?? '—'}</td>
                          <td className="py-2 px-2 text-right">{o.price ? formatCurrency(o.price) : '—'}</td>
                          <td className="py-2 px-2">{o.status || 'FILLED'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
