"""Dataclasses for AlphaCent data models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .enums import (
    DataSource,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    SignalAction,
    StrategyStatus,
    SystemStateEnum,
    TradingMode,
)


@dataclass
class RiskConfig:
    """Risk management configuration."""
    max_position_size_pct: float = 0.05  # 5% max per position
    max_exposure_pct: float = 0.90  # 90% max total exposure (of equity)
    max_daily_loss_pct: float = 0.03  # 3% daily loss limit
    max_drawdown_pct: float = 0.10  # 10% max drawdown
    position_risk_pct: float = 0.02  # 2% risk per trade (increased from 1%)
    stop_loss_pct: float = 0.04  # 4% default stop loss (increased from 2%)
    take_profit_pct: float = 0.10  # 10% default take profit (increased from 4%)
    trailing_stop: bool = False  # Whether to use trailing stop-loss (deprecated, use trailing_stop_enabled)

    # Symbol concentration limits (NEW)
    max_symbol_exposure_pct: float = 0.15  # 15% max exposure per symbol across all strategies
    max_strategies_per_symbol: int = 5  # Max number of strategies that can hold the same symbol simultaneously
    max_positions_per_symbol: int = 3  # Max number of open positions per symbol
    
    # Directional balance limits
    max_long_exposure_pct: float = 0.75  # Max 75% of portfolio in long positions
    max_short_exposure_pct: float = 0.50  # Max 50% of portfolio in short positions
    max_portfolio_drawdown_pct: float = 0.15  # Max portfolio-level drawdown before halting
    
    # Trailing stop-loss configuration
    trailing_stop_enabled: bool = False  # Enable trailing stop-loss for profitable positions
    trailing_stop_activation_pct: float = 0.05  # 5% profit before trailing activates
    trailing_stop_distance_pct: float = 0.03  # 3% trailing distance from current price
    
    # Partial exit configuration
    partial_exit_enabled: bool = False  # Enable partial exits at profit levels
    partial_exit_levels: List[Dict[str, float]] = None  # List of profit levels and exit percentages
    
    # Correlation-adjusted position sizing
    correlation_adjustment_enabled: bool = True  # Enable correlation-based position size reduction
    
    # Market regime-based position sizing
    regime_based_sizing_enabled: bool = False  # Enable regime-based position size adjustment
    regime_size_multipliers: Dict[str, float] = None  # Multipliers for different market regimes
    
    def __post_init__(self):
        """Initialize default partial exit levels and regime multipliers if not provided."""
        if self.partial_exit_levels is None:
            self.partial_exit_levels = [{"profit_pct": 0.05, "exit_pct": 0.5}]
        
        if self.regime_size_multipliers is None:
            self.regime_size_multipliers = {
                "high_volatility": 0.5,
                "low_volatility": 1.0,
                "trending": 1.2,
                "ranging": 0.8
            }


@dataclass
class PerformanceMetrics:
    """Strategy performance metrics."""
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    total_trades: int = 0


@dataclass
class AlphaSource:
    """Alpha source for a trading strategy."""
    type: str  # "momentum", "mean_reversion", "volatility", etc.
    weight: float  # Relative importance (0.0 to 1.0)
    description: str


@dataclass
class StrategyReasoning:
    """LLM reasoning metadata for strategy generation."""
    hypothesis: str  # Core market hypothesis
    alpha_sources: List[AlphaSource]  # Sources of alpha
    market_assumptions: List[str]  # Assumptions about market behavior
    signal_logic: str  # Explanation of signal generation
    confidence_factors: Dict[str, float] = field(default_factory=dict)  # Factors affecting confidence
    llm_prompt: Optional[str] = None  # Original prompt
    llm_response: Optional[str] = None  # Raw LLM response


@dataclass
class BacktestResults:
    """Results from strategy backtest."""
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    total_trades: int
    equity_curve: Optional[Any] = None  # pd.Series - using Any to avoid pandas import
    trades: Optional[Any] = None  # pd.DataFrame - using Any to avoid pandas import
    backtest_period: Optional[tuple] = None  # (start_datetime, end_datetime)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional metrics like signal overlap
    # Transaction cost analysis
    total_commission_cost: float = 0.0  # Total commission paid
    total_slippage_cost: float = 0.0  # Total slippage cost
    total_spread_cost: float = 0.0  # Total spread cost
    total_transaction_costs: float = 0.0  # Sum of all costs
    transaction_costs_pct: float = 0.0  # Costs as % of gross returns
    gross_return: float = 0.0  # Return before costs
    net_return: float = 0.0  # Return after costs (same as total_return)


@dataclass
class Strategy:
    """Trading strategy definition."""
    id: str
    name: str
    description: str
    status: StrategyStatus
    rules: Dict[str, Any]
    symbols: List[str]
    risk_params: RiskConfig
    created_at: datetime
    allocation_percent: float = 0.0
    activated_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    reasoning: Optional[StrategyReasoning] = None
    backtest_results: Optional[BacktestResults] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    retirement_evaluation_history: List[Dict[str, Any]] = field(default_factory=list)
    live_trade_count: int = 0
    last_retirement_evaluation: Optional[datetime] = None


@dataclass
class Order:
    """Order representation."""
    id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    status: OrderStatus
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = None
    filled_quantity: Optional[float] = None
    etoro_order_id: Optional[str] = None
    # Execution quality tracking
    expected_price: Optional[float] = None
    slippage: Optional[float] = None
    fill_time_seconds: Optional[float] = None
    # Signal metadata (market_regime, conviction_score, etc.)
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class Position:
    """Position representation."""
    id: str
    strategy_id: str
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    opened_at: datetime
    etoro_position_id: str
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    closed_at: Optional[datetime] = None
    pending_closure: bool = False
    partial_exits: List[Dict[str, Any]] = field(default_factory=list)  # Track partial exit history
    invested_amount: Optional[float] = None  # Actual capital invested (eToro 'amount' field)


@dataclass
class MarketData:
    """Market data representation."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: DataSource


@dataclass
class TradingSignal:
    """Trading signal from strategy."""
    strategy_id: str
    symbol: str
    action: SignalAction
    confidence: float  # 0.0 to 1.0 - strength of signal based on indicator alignment
    reasoning: str  # Explanation of why this signal was generated
    generated_at: datetime
    indicators: Dict[str, float] = field(default_factory=dict)  # Indicator values at signal time
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional context
    signal_type: str = "standard"  # Signal type: standard, alpha_edge, etc.


@dataclass
class AccountInfo:
    """Account information."""
    account_id: str
    mode: TradingMode
    balance: float
    buying_power: float
    margin_used: float
    margin_available: float
    daily_pnl: float
    total_pnl: float
    positions_count: int
    updated_at: datetime
    equity: float = 0.0


@dataclass
class SocialInsights:
    """Social trading insights for an instrument."""
    symbol: str
    sentiment_score: float  # -1.0 to 1.0
    trending_rank: Optional[int]  # Rank in trending list
    popularity_score: float  # 0.0 to 1.0
    pro_investor_positions: int  # Number of Pro Investors holding
    updated_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SmartPortfolio:
    """eToro Smart Portfolio information."""
    id: str
    name: str
    description: str
    composition: Dict[str, float]  # symbol -> allocation percentage
    performance_1m: float  # 1-month return
    performance_3m: float  # 3-month return
    performance_1y: float  # 1-year return
    risk_rating: int  # 1-10 scale
    min_investment: float
    updated_at: datetime



@dataclass
class SystemState:
    """System autonomous trading state."""
    state: SystemStateEnum
    timestamp: datetime
    reason: str
    initiated_by: Optional[str] = None  # Username who initiated change
    active_strategies_count: int = 0
    open_positions_count: int = 0
    uptime_seconds: int = 0
    last_signal_generated: Optional[datetime] = None
    last_order_executed: Optional[datetime] = None
