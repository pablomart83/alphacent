// Trading Types
export const TradingMode = {
  DEMO: 'DEMO',
  LIVE: 'LIVE',
} as const;
export type TradingMode = typeof TradingMode[keyof typeof TradingMode];

export const OrderType = {
  MARKET: 'MARKET',
  LIMIT: 'LIMIT',
  STOP_LOSS: 'STOP_LOSS',
  TAKE_PROFIT: 'TAKE_PROFIT',
} as const;
export type OrderType = typeof OrderType[keyof typeof OrderType];

export const OrderSide = {
  BUY: 'BUY',
  SELL: 'SELL',
} as const;
export type OrderSide = typeof OrderSide[keyof typeof OrderSide];

export const OrderStatus = {
  PENDING: 'PENDING',
  SUBMITTED: 'SUBMITTED',
  FILLED: 'FILLED',
  PARTIALLY_FILLED: 'PARTIALLY_FILLED',
  CANCELLED: 'CANCELLED',
  REJECTED: 'REJECTED',
} as const;
export type OrderStatus = typeof OrderStatus[keyof typeof OrderStatus];

export const StrategyStatus = {
  PROPOSED: 'PROPOSED',
  BACKTESTED: 'BACKTESTED',
  DEMO: 'DEMO',
  LIVE: 'LIVE',
  RETIRED: 'RETIRED',
} as const;
export type StrategyStatus = typeof StrategyStatus[keyof typeof StrategyStatus];

export const SystemState = {
  ACTIVE: 'ACTIVE',
  PAUSED: 'PAUSED',
  STOPPED: 'STOPPED',
  EMERGENCY_HALT: 'EMERGENCY_HALT',
} as const;
export type SystemState = typeof SystemState[keyof typeof SystemState];

export const ServiceStatus = {
  RUNNING: 'RUNNING',
  STOPPED: 'STOPPED',
  ERROR: 'ERROR',
} as const;
export type ServiceStatus = typeof ServiceStatus[keyof typeof ServiceStatus];

// Data Models
export interface AccountInfo {
  balance: number;
  equity: number;
  buying_power: number;
  margin_used: number;
  daily_pnl: number;
  total_pnl: number;
  trading_mode: TradingMode;
}

export interface Position {
  id: string;
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  realized_pnl?: number;
  side: OrderSide;
  strategy_id?: string;
  strategy_name?: string;
  opened_at: string;
  closed_at?: string;
  pending_closure?: boolean;
  closure_reason?: string;
  stop_loss?: number;
  take_profit?: number;
  invested_amount?: number;
}

export interface Order {
  id: string;
  symbol: string;
  side: OrderSide;
  type: OrderType;
  quantity: number;
  price?: number;
  filled_quantity: number;
  status: OrderStatus;
  strategy_id?: string;
  strategy_name?: string;
  created_at: string;
  updated_at: string;
  order_action?: 'entry' | 'close' | 'retirement';
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  status: StrategyStatus;
  rules: string;
  symbols: string[];
  allocation_percent: number;
  performance_metrics?: PerformanceMetrics;
  reasoning?: StrategyReasoning;
  backtest_results?: BacktestResults;
  created_at: string;
  updated_at: string;
  last_order_date?: string;
  retired_at?: string;
  // Enhanced fields for autonomous trading
  source?: 'TEMPLATE' | 'USER';
  template_name?: string;
  market_regime?: string;
  entry_rules?: string[];
  exit_rules?: string[];
  walk_forward_results?: WalkForwardResults;
  parameters?: Record<string, any>;
  // Alpha Edge metadata
  metadata?: {
    template_name?: string;
    template_type?: string;
    strategy_category?: 'alpha_edge' | 'template_based' | 'manual';
    conviction_score?: number;
    ml_confidence?: number;
    fundamental_data?: {
      eps?: number;
      revenue_growth?: number;
      pe_ratio?: number;
      roe?: number;
      debt_to_equity?: number;
      market_cap?: number;
    };
    fundamental_checks?: {
      profitable?: boolean;
      growing?: boolean;
      reasonable_valuation?: boolean;
      no_dilution?: boolean;
      insider_buying?: boolean;
    };
    requires_fundamental_data?: boolean;
    requires_earnings_data?: boolean;
    [key: string]: any;
  };
  // Top-level strategy classification fields (resolved by backend)
  strategy_category?: 'alpha_edge' | 'template_based' | 'manual';
  strategy_type?: string;
  requires_fundamental_data?: boolean;
  requires_earnings_data?: boolean;
}

export interface WalkForwardResults {
  in_sample: {
    sharpe_ratio: number;
    total_return: number;
    max_drawdown: number;
    win_rate: number;
  };
  out_of_sample: {
    sharpe_ratio: number;
    total_return: number;
    max_drawdown: number;
    win_rate: number;
  };
  consistency_score: number;
}

export interface StrategyReasoning {
  hypothesis: string;
  alpha_sources: AlphaSource[];
  market_assumptions: string[];
  signal_logic: string;
  confidence_factors?: Record<string, number>;
}

export interface AlphaSource {
  type: string;
  weight: number;
  description: string;
}

export interface PerformanceMetrics {
  total_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  total_trades: number;
  total_pnl?: number;
  // Live trading stats
  live_orders?: number;
  open_positions?: number;
  unrealized_pnl?: number;
  // Strategy scores
  health_score?: number | null;  // 0-5: live performance
  decay_score?: number | null;   // 10→0: edge expiration countdown
}

export interface BacktestResults {
  total_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  total_trades: number;
  equity_curve?: Array<{ timestamp: string; equity: number }>;
  trades?: Array<{
    timestamp: string;
    symbol: string;
    side: string;
    quantity: number;
    price: number;
    pnl?: number;
  }>;
  backtest_period?: {
    start: string;
    end: string;
  };
}

export interface MarketData {
  symbol: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  bid: number;
  ask: number;
  timestamp: string;
  source: 'ETORO' | 'YAHOO_FINANCE';
}

export interface SystemStatus {
  state: SystemState;
  timestamp: string;
  active_strategies: number;
  open_positions: number;
  reason?: string;
  uptime_seconds: number;
  last_signal_generated?: string | null;
  last_order_executed?: string | null;
}

export interface DependentService {
  name: string;
  status: ServiceStatus;
  endpoint: string;
  last_health_check: string;
  error_message?: string;
}

export interface Notification {
  id: string;
  severity: 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
}

export interface SessionSummary {
  session_id: string;
  start_time: string;
  end_time: string;
  duration_seconds: number;
  total_return: number;
  total_trades: number;
  win_rate: number;
  max_drawdown: number;
  strategies_active: number;
}

export interface TradingSignal {
  strategy_id: string;
  strategy_name?: string;
  symbol: string;
  action: OrderSide;
  quantity: number;
  price?: number;
  confidence: number;
  reasoning: string;
  indicators?: Record<string, number>;
  timestamp: string;
}

// API Response Types
export interface ApiResponse<T> {
  data?: T;
  error?: string;
  message?: string;
}

export interface AuthResponse {
  token: string;
  user: {
    username: string;
  };
}

export interface ConfigData {
  etoro_public_key?: string;
  etoro_user_key?: string;
  trading_mode: TradingMode;
  risk_params: RiskParams;
}

export interface RiskParams {
  max_position_size: number;
  max_portfolio_exposure: number;
  max_daily_loss: number;
  risk_per_trade: number;
}

// Autonomous Trading Types
export interface CycleStats {
  proposals_count: number;
  backtested_count: number;
  activated_count: number;
  retired_count: number;
}

export interface PortfolioHealth {
  active_strategies: number;
  max_strategies: number;
  total_allocation: number;
  avg_correlation: number;
  portfolio_sharpe: number;
}

export interface TemplateStats {
  name: string;
  success_rate: number;
  usage_count: number;
}

export interface AutonomousStatus {
  enabled: boolean;
  market_regime: string;
  market_confidence: number;
  data_quality: string;
  last_cycle_time: string | null;
  next_scheduled_run: string | null;
  cycle_duration: number | null;
  cycle_stats: CycleStats;
  portfolio_health: PortfolioHealth;
  template_stats: TemplateStats[];
}

// Performance Dashboard Types
export interface MetricWithChange {
  value: number;
  change: number;
}

export interface HistoryPoint {
  date: string;
  value: number;
  benchmark?: number;
}

export interface StrategyContribution {
  strategy_name: string;
  contribution: number; // percentage
  return: number;
}

export interface PerformanceDashboardMetrics {
  sharpe: MetricWithChange;
  total_return: MetricWithChange;
  max_drawdown: MetricWithChange;
  win_rate: MetricWithChange;
  portfolio_history: HistoryPoint[];
  strategy_contributions: StrategyContribution[];
}

export type TimePeriod = '1M' | '3M' | '6M' | '1Y' | 'ALL';

// Autonomous Configuration Types
export interface TemplateConfig {
  name: string;
  enabled: boolean;
  priority: 'high' | 'medium' | 'low';
}

export interface AutonomousConfig {
  general: {
    enabled: boolean;
    proposal_frequency: 'daily' | 'weekly' | 'monthly';
    proposal_count: number;
    max_active_strategies: number;
    min_active_strategies: number;
  };
  templates: TemplateConfig[];
  activation_thresholds: {
    min_sharpe: number;
    max_drawdown: number;
    min_win_rate: number;
    min_trades: number;
  };
  retirement_triggers: {
    max_sharpe: number;
    max_drawdown: number;
    min_win_rate: number;
    min_trades_for_eval: number;
  };
  advanced: {
    backtest_period: number; // days
    walk_forward_train: number; // days
    walk_forward_test: number; // days
    correlation_threshold: number;
    risk_free_rate: number;
  };
  last_updated?: string;
  updated_by?: string;
}

// WebSocket Message Types
export interface WebSocketMessage {
  type: 'market_data' | 'position_update' | 'order_update' | 'strategy_update' | 'system_state' | 'notification' | 'service_status' | 'social_insights' | 'smart_portfolio_update' | 'signal_generated' | 'signal_decision' | 'autonomous_status' | 'autonomous_cycle' | 'autonomous_strategies' | 'autonomous_notifications';
  data: Record<string, unknown>;
}

// Fundamental Alert Types
export interface FundamentalAlert {
  id: string;
  symbol: string;
  side: OrderSide;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_percent?: number;
  flag_reason: string;
  flag_timestamp: string;
  fundamental_data?: Record<string, number | string>;
  fundamental_detail?: string;
  closure_reason?: string;
  strategy_id?: string;
  opened_at?: string;
}

// Analytics Types
export interface TradeJournalPattern {
  pattern: string;
  pattern_type?: string;
  description: string;
  win_rate?: number;
  avg_return?: number;
  trade_count?: number;
  total_trades?: number;
  avg_pnl?: number;
}

export interface ApiUsageStats {
  fmp_usage: { calls_today: number; limit: number; percentage: number; remaining: number };
  alpha_vantage_usage: { calls_today: number; limit: number; percentage: number; remaining: number };
  cache_stats?: { size: number; hits?: number; misses?: number; hit_rate: number };
}

export interface ExecutionQualityData {
  avg_slippage: number;
  fill_rate: number;
  avg_fill_time: number;
  order_metrics?: Array<{
    order_id: string;
    slippage: number;
    fill_time_seconds: number;
  }>;
}
