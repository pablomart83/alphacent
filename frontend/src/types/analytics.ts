export interface RollingStatsData {
  rolling_sharpe: Array<{ date: string; value: number }>;
  rolling_beta: Array<{ date: string; value: number }>;
  rolling_alpha: Array<{ date: string; value: number }>;
  rolling_volatility: Array<{ date: string; value: number }>;
  probabilistic_sharpe: number;
  information_ratio: number;
  treynor_ratio: number;
  tracking_error: number;
}

export interface AttributionSector {
  sector: string;
  portfolio_weight: number;
  benchmark_weight: number;
  portfolio_return: number;
  benchmark_return: number;
  allocation_effect: number;
  selection_effect: number;
  interaction_effect: number;
  total_contribution: number;
}

export interface AttributionData {
  sectors: AttributionSector[];
  cumulative_effects: Array<{
    date: string;
    allocation: number;
    selection: number;
    interaction: number;
  }>;
}

export interface TearSheetData {
  underwater_plot: Array<{ date: string; drawdown_pct: number }>;
  worst_drawdowns: Array<{
    rank: number;
    start_date: string;
    trough_date: string;
    recovery_date: string | null;
    depth_pct: number;
    duration_days: number;
    recovery_days: number | null;
  }>;
  return_distribution: Array<{ bin: number; count: number }>;
  skew: number;
  kurtosis: number;
  annual_returns: Array<{ year: number; return_pct: number }>;
  monthly_returns: Array<{ year: number; month: number; return_pct: number }>;
}

export interface TCAData {
  slippage_by_symbol: Array<{ symbol: string; avg_slippage_pct: number; trade_count: number }>;
  slippage_by_hour: Array<{ hour: number; day: string; avg_slippage: number }>;
  slippage_by_size: Array<{ bucket: string; avg_slippage: number; trade_count: number }>;
  implementation_shortfall: Array<{
    symbol: string;
    expected_price: number;
    fill_price: number;
    market_close_price: number;
    shortfall_dollars: number;
    shortfall_bps: number;
    trade_date: string;
  }>;
  total_shortfall_dollars: number;
  total_shortfall_bps: number;
  fill_rate_buckets: Array<{ within_seconds: number; percentage: number }>;
  cost_as_pct_of_alpha: number;
  execution_quality_trend: Array<{ date: string; avg_slippage: number }>;
  per_asset_class: Array<{
    asset_class: string;
    avg_slippage: number;
    avg_shortfall_bps: number;
    trade_count: number;
  }>;
  worst_executions: Array<{
    symbol: string;
    expected_price: number;
    fill_price: number;
    slippage_pct: number;
    timestamp: string;
    order_size_dollars: number;
    asset_class: string;
  }>;
}
