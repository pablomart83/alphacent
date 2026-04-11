import { type FC, useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, RefreshCw, AlertCircle } from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { AssetPlot } from '../components/charts/AssetPlot';
import { InteractiveChart } from '../components/charts/InteractiveChart';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { classifyError } from '../lib/errors';
import { colors as designColors } from '../lib/design-tokens';
import { PageSkeleton } from '../components/ui/skeleton';

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

  const fetchDetail = useCallback(async () => {
    if (!tradingMode || !symbol) return;
    try {
      setLoading(true);
      setError(null);
      const data = await apiClient.getPositionDetail(symbol, tradingMode);
      setDetail(data);
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
        <PageSkeleton />
      </DashboardLayout>
    );
  }

  const priceData = detail?.price_history || [];
  const orders = detail?.orders || [];
  const pnlHistory = detail?.pnl_history || [];
  const position = detail?.position;
  const hasOrders = orders.length > 0;

  return (
    <DashboardLayout onLogout={onLogout}>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="p-4 sm:p-6 lg:p-8 max-w-[1800px] mx-auto"
      >
        {/* Header */}
        <div className="mb-6 flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/portfolio')} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <div className="flex-1">
            <h1 className="text-2xl font-bold text-gray-100 font-mono">{symbol}</h1>
            <p className="text-sm text-muted-foreground">Position Detail</p>
          </div>
          <Button variant="outline" size="sm" onClick={fetchDetail} className="gap-2">
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>

        {error ? (
          <Card className="border-accent-red/30 bg-accent-red/5">
            <CardContent className="pt-6">
              <div className="flex flex-col items-center text-center py-8">
                <AlertCircle className="h-12 w-12 text-accent-red mb-4" />
                <p className="text-sm text-muted-foreground mb-4">{error}</p>
                <Button variant="outline" onClick={fetchDetail} className="gap-2">
                  <RefreshCw className="h-4 w-4" />
                  Retry
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            {/* Position Summary */}
            {position && (
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground mb-1">Side</p>
                    <Badge className={cn(
                      'font-mono text-xs',
                      position.side === 'BUY' ? 'bg-accent-green/20 text-accent-green' : 'bg-accent-red/20 text-accent-red'
                    )}>
                      {position.side}
                    </Badge>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground mb-1">Entry Price</p>
                    <p className="text-lg font-bold font-mono">{formatCurrency(position.entry_price || 0)}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground mb-1">Current Price</p>
                    <p className="text-lg font-bold font-mono">{formatCurrency(position.current_price || 0)}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground mb-1">Unrealized P&L</p>
                    <p className={cn('text-lg font-bold font-mono', (position.unrealized_pnl || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                      {formatCurrency(position.unrealized_pnl || 0)}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground mb-1">P&L %</p>
                    <p className={cn('text-lg font-bold font-mono', (position.unrealized_pnl_percent || 0) >= 0 ? 'text-accent-green' : 'text-accent-red')}>
                      {formatPercentage(position.unrealized_pnl_percent || 0)}
                    </p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-4 pb-3">
                    <p className="text-xs text-muted-foreground mb-1">Strategy</p>
                    <p className="text-sm font-mono text-gray-300 truncate">{position.strategy_name || position.strategy_id?.slice(0, 8) || '—'}</p>
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Asset Plot — Price Chart with Order Annotations */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">Price Chart — {symbol}</CardTitle>
                    <CardDescription>Price over holding period with buy/sell annotations</CardDescription>
                  </div>
                  {!hasOrders && (
                    <Badge variant="secondary" className="text-xs font-mono">Order history unavailable</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>

            {/* P&L Time-Series Chart */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">P&L Over Time</CardTitle>
                <CardDescription>Unrealized P&L for this position over its holding period</CardDescription>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>

            {/* Order History Table */}
            {hasOrders && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Order History</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono">
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
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </motion.div>
    </DashboardLayout>
  );
};
