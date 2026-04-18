"""
Strategy endpoints for AlphaCent Trading Platform.

Provides endpoints for managing trading strategies.
Validates: Requirement 11.3
"""

import logging
import math
import os
import re
import threading
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from sqlalchemy import func as sa_func
from src.models.enums import StrategyStatus, TradingMode, OrderStatus
from src.api.dependencies import get_current_user, get_db_session
from src.api.websocket_manager import get_websocket_manager
from src.models.orm import StrategyORM, OrderORM, PositionORM
from src.models.database import get_database

# Pre-import strategy modules to prevent race conditions with background threads
# These were previously lazy-imported inside trigger_autonomous_cycle, causing
# KeyError: 'src.strategy' when the background services thread was still loading
from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
from src.strategy.strategy_engine import StrategyEngine
from src.data.market_data_manager import MarketDataManager
from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])

# Module-level tracking of running cycles
_running_cycle_thread: Optional[threading.Thread] = None
_running_cycle_id: Optional[str] = None

# Global DB write lock — prevents concurrent writes between manual cycle and scheduler
import threading as _threading
_db_cycle_lock = _threading.Lock()


def sanitize_float(value: float) -> float:
    """
    Sanitize float values for JSON serialization.
    
    Converts NaN and infinity to None-safe values.
    
    Args:
        value: Float value to sanitize
        
    Returns:
        Sanitized float value (0.0 for NaN/inf)
    """
    if math.isnan(value) or math.isinf(value):
        return 0.0
    return value


def _get_strategy_engine(mode: TradingMode):
    """
    Helper function to initialize StrategyEngine with proper dependencies.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        
    Returns:
        Initialized StrategyEngine instance
    """
    from src.strategy.strategy_engine import StrategyEngine
    from src.data.market_data_manager import MarketDataManager
    from src.api.etoro_client import EToroAPIClient
    from src.core.config import get_config
    
    # Load credentials for the specified mode
    config = get_config()
    credentials = config.load_credentials(mode)
    
    if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
        raise ValueError(f"eToro credentials not configured for {mode.value} mode. Please set up credentials first.")
    
    # Initialize components with proper dependencies
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=mode
    )
    market_data = MarketDataManager(etoro_client)
    websocket_manager = get_websocket_manager()
    # No LLM needed — strategy generation uses templates
    strategy_engine = StrategyEngine(None, market_data, websocket_manager)
    
    return strategy_engine


class PerformanceMetricsResponse(BaseModel):
    """Performance metrics response model."""
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    total_trades: int
    # Live trading stats
    live_orders: Optional[int] = 0  # Count of PENDING orders for this strategy
    open_positions: Optional[int] = 0  # Count of open positions for this strategy
    unrealized_pnl: Optional[float] = 0.0  # Sum of unrealized P&L from open positions
    total_pnl: Optional[float] = None  # Total P&L (realized + unrealized)
    # Strategy scores (computed by monitoring service)
    health_score: Optional[int] = None  # 0-5: live performance (0=retire, 5=excellent)
    decay_score: Optional[int] = None  # 10→0: edge expiration countdown (0=expired)


class StrategyResponse(BaseModel):
    """Strategy response model."""
    id: str
    name: str
    description: str
    status: StrategyStatus
    rules: Dict[str, Any]
    symbols: List[str]
    allocation_percent: float
    risk_params: Dict[str, float]
    created_at: str
    activated_at: Optional[str] = None
    retired_at: Optional[str] = None
    performance_metrics: PerformanceMetricsResponse
    reasoning: Optional[Dict[str, Any]] = None
    updated_at: Optional[str] = None
    # Enhanced fields for autonomous trading and Alpha Edge
    source: Optional[str] = None  # 'TEMPLATE' or 'USER'
    template_name: Optional[str] = None
    market_regime: Optional[str] = None
    entry_rules: Optional[List[str]] = None
    exit_rules: Optional[List[str]] = None
    walk_forward_results: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None  # Includes conviction_score, ml_confidence, fundamental_data, etc.
    # Task 9.7: Strategy metadata fields
    strategy_category: Optional[str] = None  # 'alpha_edge' or 'template_based'
    strategy_type: Optional[str] = None  # From StrategyType enum
    requires_fundamental_data: Optional[bool] = None
    requires_earnings_data: Optional[bool] = None
    traded_symbols: Optional[List[str]] = None  # Symbols with open positions/orders (not the full watchlist)


class StrategiesResponse(BaseModel):
    """Strategies list response model."""
    strategies: List[StrategyResponse]
    total_count: int


class CreateStrategyRequest(BaseModel):
    """Create strategy request model."""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    rules: Dict[str, Any]
    symbols: List[str] = Field(..., min_items=1)
    risk_params: Dict[str, float]


class UpdateStrategyRequest(BaseModel):
    """Update strategy request model."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1)
    rules: Optional[Dict[str, Any]] = None
    symbols: Optional[List[str]] = Field(None, min_items=1)
    risk_params: Optional[Dict[str, float]] = None


class StrategyActionResponse(BaseModel):
    """Strategy action response model."""
    success: bool
    message: str
    strategy_id: str


class VibeCodeRequest(BaseModel):
    """Vibe code translation request model."""
    natural_language: str = Field(..., min_length=1, max_length=500)


class TradingCommandResponse(BaseModel):
    """Trading command response model."""
    action: str
    symbol: str
    quantity: Optional[float] = None
    price: Optional[float] = None
    reason: str
    translated_from: str


class GenerateStrategyRequest(BaseModel):
    """Generate strategy request model."""
    prompt: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Natural language description of desired strategy"
    )
    constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Market context and constraints (risk_config, available_symbols, etc.)"
    )


class BootstrapRequest(BaseModel):
    """Bootstrap strategies request model."""
    strategy_types: Optional[List[str]] = Field(
        None,
        description="List of strategy types to generate (momentum, mean_reversion, breakout)"
    )
    auto_activate: bool = Field(
        False,
        description="Whether to automatically activate strategies meeting performance thresholds"
    )
    min_sharpe: float = Field(
        1.0,
        ge=0.0,
        description="Minimum Sharpe ratio for auto-activation"
    )
    backtest_days: int = Field(
        90,
        ge=30,
        le=365,
        description="Number of days to backtest (30-365)"
    )


class BacktestResultsSummary(BaseModel):
    """Backtest results summary for bootstrap response."""
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int


class BootstrapStrategyInfo(BaseModel):
    """Strategy information in bootstrap response."""
    id: str
    name: str
    description: str
    status: StrategyStatus
    symbols: List[str]
    allocation_percent: float
    backtest_results: Optional[BacktestResultsSummary] = None


class BootstrapResponse(BaseModel):
    """Bootstrap strategies response model."""
    success: bool
    message: str
    strategies: List[BootstrapStrategyInfo]
    summary: Dict[str, Any] = Field(
        description="Summary statistics including total_generated, total_backtested, total_activated, errors"
    )


class BacktestRequest(BaseModel):
    """Backtest strategy request model."""
    start_date: Optional[datetime] = Field(
        None,
        description="Start date for backtest period (defaults to 90 days ago)"
    )
    end_date: Optional[datetime] = Field(
        None,
        description="End date for backtest period (defaults to today)"
    )


class BacktestResultsResponse(BaseModel):
    """Backtest results response model."""
    strategy_id: str
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    total_trades: int
    backtest_period: Dict[str, str] = Field(
        description="Start and end dates of backtest period"
    )
    # Transaction cost analysis
    gross_return: float = Field(default=0.0, description="Return before transaction costs")
    net_return: float = Field(default=0.0, description="Return after transaction costs")
    total_transaction_costs: float = Field(default=0.0, description="Total transaction costs in dollars")
    transaction_costs_pct: float = Field(default=0.0, description="Transaction costs as % of initial capital")
    total_commission_cost: float = Field(default=0.0, description="Total commission costs")
    total_slippage_cost: float = Field(default=0.0, description="Total slippage costs")
    total_spread_cost: float = Field(default=0.0, description="Total spread costs")
    message: str


class UpdateAllocationRequest(BaseModel):
    """Update strategy allocation request model."""
    allocation_percent: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of portfolio to allocate (0.0 to 100.0)"
    )


class CycleStatsResponse(BaseModel):
    """Cycle statistics response model."""
    proposals_count: int
    backtested_count: int
    activated_count: int
    retired_count: int


class PortfolioHealthResponse(BaseModel):
    """Portfolio health response model."""
    active_strategies: int
    max_strategies: int
    total_allocation: float
    avg_correlation: float
    portfolio_sharpe: float


class TemplateStatsResponse(BaseModel):
    """Template statistics response model."""
    name: str
    success_rate: float
    usage_count: int


class AutonomousStatusResponse(BaseModel):
    """Autonomous trading system status response model."""
    enabled: bool
    market_regime: str
    market_confidence: float
    data_quality: str
    last_cycle_time: Optional[str]
    next_scheduled_run: Optional[str]
    cycle_duration: Optional[float]
    cycle_stats: CycleStatsResponse
    portfolio_health: PortfolioHealthResponse
    template_stats: List[TemplateStatsResponse]


class TemplateResponse(BaseModel):
    """Template information response model."""
    name: str
    description: str
    market_regimes: List[str]
    indicators: List[str]
    entry_rules: List[str]
    exit_rules: List[str]
    success_rate: float
    usage_count: int
    strategy_type: Optional[str] = None
    direction: Optional[str] = None
    asset_classes: Optional[List[str]] = None
    expected_trade_frequency: Optional[str] = None
    expected_holding_period: Optional[str] = None
    risk_reward_ratio: Optional[float] = None
    enabled: bool = True
    active_strategies: int = 0
    total_strategies_ever: int = 0
    avg_sharpe: Optional[float] = None
    avg_win_rate: Optional[float] = None
    avg_return: Optional[float] = None
    total_trades_live: int = 0
    total_pnl: Optional[float] = None
    best_symbol: Optional[str] = None
    worst_symbol: Optional[str] = None
    last_proposed: Optional[str] = None
    last_activated: Optional[str] = None
    is_intraday: bool = False
    is_4h: bool = False
    interval: Optional[str] = None
    activated_count: int = 0
    traded_count: int = 0
    proposed_count: int = 0
    approved_count: int = 0
    strategy_category: Optional[str] = None  # 'alpha_edge', 'template_based', 'statistical'


class TemplatesListResponse(BaseModel):
    """Templates list response model."""
    templates: List[TemplateResponse]
    total: int


class ToggleTemplateRequest(BaseModel):
    """Toggle template enabled/disabled."""
    enabled: bool


@router.get("", response_model=StrategiesResponse)
async def get_strategies(
    mode: TradingMode,
    status_filter: Optional[StrategyStatus] = None,
    include_retired: bool = False,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get all strategies.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        status_filter: Optional status filter
        include_retired: Whether to include retired strategies (default: False)
        username: Current authenticated user
        session: Database session
        
    Returns:
        List of strategies
        
    Validates: Requirement 11.3
    """
    logger.info(f"Getting strategies for {mode.value} mode, user {username}, include_retired={include_retired}")
    
    # Query strategies from database
    query = session.query(StrategyORM)
    
    # Exclude RETIRED strategies unless explicitly requested
    if not include_retired:
        query = query.filter(StrategyORM.status != StrategyStatus.RETIRED.value)
    
    # Apply additional status filter if provided
    if status_filter:
        query = query.filter(StrategyORM.status == status_filter)
    
    strategies = query.all()
    
    # Bulk query: count pending orders per strategy
    order_count_rows = session.query(
        OrderORM.strategy_id, sa_func.count(OrderORM.id)
    ).filter(
        OrderORM.status == OrderStatus.PENDING
    ).group_by(OrderORM.strategy_id).all()
    order_counts = {row[0]: row[1] for row in order_count_rows}

    # Bulk query: open positions stats per strategy
    position_stat_rows = session.query(
        PositionORM.strategy_id,
        sa_func.count(PositionORM.id),
        sa_func.coalesce(sa_func.sum(PositionORM.unrealized_pnl), 0.0)
    ).filter(
        PositionORM.closed_at.is_(None),
        PositionORM.pending_closure == False
    ).group_by(PositionORM.strategy_id).all()
    position_stats = {row[0]: {"count": row[1], "pnl": float(row[2])} for row in position_stat_rows}

    # Bulk query: traded symbols per strategy (symbols with open positions)
    traded_symbol_rows = session.query(
        PositionORM.strategy_id,
        PositionORM.symbol
    ).filter(
        PositionORM.closed_at.is_(None),
        PositionORM.pending_closure == False
    ).all()
    from collections import defaultdict
    traded_symbols_map: dict = defaultdict(list)
    for strat_id, symbol in traded_symbol_rows:
        if symbol not in traded_symbols_map[strat_id]:
            traded_symbols_map[strat_id].append(symbol)

    # Convert ORM models to response models
    strategy_responses = []
    for strategy in strategies:
        strategy_dict = strategy.to_dict()
        metadata = strategy_dict.get("metadata", {})
        
        # Extract entry/exit rules from rules dict
        rules_dict = strategy_dict.get("rules", {})
        entry_rules = rules_dict.get("entry", []) if isinstance(rules_dict.get("entry"), list) else None
        exit_rules = rules_dict.get("exit", []) if isinstance(rules_dict.get("exit"), list) else None
        
        # Extract walk-forward results from backtest_results
        backtest_results = strategy_dict.get("backtest_results", {})
        walk_forward_results = backtest_results.get("walk_forward_results") if backtest_results else None
        
        # Task 9.7: Extract strategy metadata fields with proper resolution
        ALPHA_EDGE_TEMPLATES = {
            # Original 3
            "earnings_momentum", "sector_rotation", "quality_mean_reversion",
            "Alpha Edge Earnings Momentum", "Alpha Edge Sector Rotation", "Alpha Edge Quality Mean Reversion",
            # Task 11.11 additions
            "dividend_aristocrat", "insider_buying", "revenue_acceleration", "relative_value",
            "Dividend Aristocrat", "Insider Buying", "Revenue Acceleration", "Relative Value",
            # Task 11.12 additions
            "end_of_month_momentum", "pairs_trading",
            "End-of-Month Momentum Long", "Pairs Trading Market Neutral",
        }
        template_name = metadata.get("template_name", "")
        if not template_name:
            # Backfill: extract template name from strategy name (strip version suffix like " V81")
            name = strategy_dict.get("name", "")
            # Remove version suffix (e.g., " V81", " V105") and symbol suffixes
            cleaned = re.sub(r'\s+V\d+$', '', name).strip()
            if cleaned:
                template_name = cleaned
                # Also persist the backfill to metadata for future queries
                metadata["template_name"] = template_name
        
        # Resolve strategy_category: check metadata first, then infer from template name
        strategy_category = metadata.get("strategy_category")
        if not strategy_category:
            # Check template_name first
            if template_name and (template_name in ALPHA_EDGE_TEMPLATES or 
                                  template_name.lower().replace(" ", "_") in {
                                      "earnings_momentum", "sector_rotation", "quality_mean_reversion",
                                      "dividend_aristocrat", "insider_buying", "revenue_acceleration",
                                      "relative_value", "end_of_month_momentum", "pairs_trading",
                                  }):
                strategy_category = "alpha_edge"
            elif template_name:
                strategy_category = "template_based"
            else:
                # Fallback: infer from strategy name if no template_name
                strategy_name_lower = strategy_dict.get("name", "").lower()
                alpha_edge_keywords = ["earnings momentum", "sector rotation", "quality mean reversion",
                                       "dividend aristocrat", "insider buying", "revenue acceleration",
                                       "relative value", "end-of-month momentum", "pairs trading"]
                if any(kw in strategy_name_lower for kw in alpha_edge_keywords):
                    strategy_category = "alpha_edge"
                elif metadata.get("source") == "TEMPLATE" or "V" in strategy_dict.get("name", "").split()[-1:]:
                    # Autonomous strategies typically end with "V{number}" (e.g., "BB Squeeze EMA Trend Multi V81")
                    strategy_category = "template_based"
                else:
                    strategy_category = "manual"
        
        # Resolve strategy_type: check metadata.strategy_type, then template_type
        strategy_type = metadata.get("strategy_type") or metadata.get("template_type")
        
        requires_fundamental_data = metadata.get("requires_fundamental_data", False)
        requires_earnings_data = metadata.get("requires_earnings_data", False)
        
        strategy_id = strategy_dict["id"]
        live_orders = order_counts.get(strategy_id, 0)
        pos_stat = position_stats.get(strategy_id, {"count": 0, "pnl": 0.0})
        traded_syms = traded_symbols_map.get(strategy_id, [])

        strategy_responses.append(StrategyResponse(
            id=strategy_id,
            name=strategy_dict["name"],
            description=strategy_dict["description"],
            status=StrategyStatus(strategy_dict["status"]),
            rules=strategy_dict["rules"],
            symbols=strategy_dict["symbols"],
            allocation_percent=strategy_dict["allocation_percent"],
            risk_params=strategy_dict["risk_params"],
            created_at=strategy_dict["created_at"],
            activated_at=strategy_dict.get("activated_at"),
            retired_at=strategy_dict.get("retired_at"),
            performance_metrics=PerformanceMetricsResponse(
                total_return=sanitize_float(strategy_dict["performance"]["total_return"]),
                sharpe_ratio=sanitize_float(strategy_dict["performance"]["sharpe_ratio"]),
                sortino_ratio=sanitize_float(strategy_dict["performance"]["sortino_ratio"]),
                max_drawdown=sanitize_float(strategy_dict["performance"]["max_drawdown"]),
                win_rate=sanitize_float(strategy_dict["performance"]["win_rate"]),
                avg_win=sanitize_float(strategy_dict["performance"]["avg_win"]),
                avg_loss=sanitize_float(strategy_dict["performance"]["avg_loss"]),
                total_trades=strategy_dict["performance"]["total_trades"],
                live_orders=live_orders,
                open_positions=pos_stat["count"],
                unrealized_pnl=pos_stat["pnl"],
                total_pnl=pos_stat["pnl"],
                health_score=metadata.get("health_score"),
                decay_score=metadata.get("decay_score"),
            ),
            reasoning=strategy_dict.get("reasoning"),
            updated_at=strategy_dict.get("created_at"),
            # Enhanced fields
            source=metadata.get("source", "USER" if not metadata.get("template_name") else "TEMPLATE"),
            template_name=metadata.get("template_name"),
            market_regime=metadata.get("market_regime") or metadata.get("activation_regime"),
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            walk_forward_results=walk_forward_results,
            metadata=metadata,
            # Task 9.7: Include strategy metadata fields
            strategy_category=strategy_category,
            strategy_type=strategy_type,
            requires_fundamental_data=requires_fundamental_data,
            requires_earnings_data=requires_earnings_data,
            traded_symbols=traded_syms if traded_syms else None,
        ))
    
    return StrategiesResponse(
        strategies=strategy_responses,
        total_count=len(strategy_responses)
    )


@router.post("", response_model=StrategyActionResponse)
async def create_strategy(
    request: CreateStrategyRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Create new strategy.
    
    Args:
        request: Strategy creation request
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Created strategy ID
        
    Validates: Requirement 11.3
    """
    logger.info(f"Creating strategy '{request.name}' for {mode.value} mode, user {username}")
    
    # Generate strategy ID
    strategy_id = f"strat_{uuid4().hex[:8]}"
    
    # Create strategy ORM object
    strategy = StrategyORM(
        id=strategy_id,
        name=request.name,
        description=request.description,
        status=StrategyStatus.PROPOSED,
        rules=request.rules,
        symbols=request.symbols,
        allocation_percent=0.0,
        risk_params=request.risk_params,
        created_at=datetime.now(),
        activated_at=None,
        retired_at=None,
        performance={
            "total_return": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "total_trades": 0
        }
    )
    
    # Save to database
    session.add(strategy)
    session.commit()
    session.refresh(strategy)
    
    logger.info(f"Strategy created: {strategy_id}")
    
    return StrategyActionResponse(
        success=True,
        message="Strategy created successfully",
        strategy_id=strategy_id
    )


# --- Template endpoints (MUST be before /{strategy_id} to avoid path conflict) ---

@router.get("/templates", response_model=TemplatesListResponse)
async def get_strategy_templates(
    market_regime: Optional[str] = Query(None, description="Filter by market regime"),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """Get all strategy templates with rich metadata, usage stats, and live performance."""
    logger.info(f"Fetching strategy templates (regime={market_regime})")

    try:
        from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime
        import json, yaml
        from pathlib import Path

        template_library = StrategyTemplateLibrary()

        if market_regime:
            try:
                regime_enum = MarketRegime(market_regime)
                templates = template_library.get_templates_for_regime(regime_enum)
            except ValueError:
                templates = template_library.get_all_templates()
        else:
            templates = template_library.get_all_templates()

        # Load user-disabled templates list
        disabled_templates = set()
        try:
            disabled_path = Path("config/.disabled_templates.json")
            if disabled_path.exists():
                with open(disabled_path, 'r') as f:
                    disabled_templates = set(json.load(f))
        except Exception as e:
            logger.debug(f"Could not load disabled templates: {e}")

        # Query all strategies from DB for usage/performance stats
        all_strategies = db.query(StrategyORM).all()

        # Build per-template stats from real strategies
        template_stats: Dict[str, Dict] = {}
        
        # Pre-load open position counts per strategy for the "Active" column
        # (how many positions are open right now, not how many strategies)
        open_positions_by_strategy: Dict[str, int] = {}
        try:
            from sqlalchemy import func as _pos_func
            pos_counts = db.query(
                PositionORM.strategy_id,
                _pos_func.count(PositionORM.id)
            ).filter(
                PositionORM.closed_at.is_(None)
            ).group_by(PositionORM.strategy_id).all()
            open_positions_by_strategy = {sid: cnt for sid, cnt in pos_counts}
        except Exception as e:
            logger.debug(f"Could not load open position counts: {e}")

        # Pre-load total trade counts per strategy (open + closed positions)
        # for the "Traded" column
        total_trades_by_strategy: Dict[str, int] = {}
        try:
            from sqlalchemy import func as _trade_func
            trade_counts = db.query(
                PositionORM.strategy_id,
                _trade_func.count(PositionORM.id)
            ).group_by(PositionORM.strategy_id).all()
            total_trades_by_strategy = {sid: cnt for sid, cnt in trade_counts}
        except Exception as e:
            logger.debug(f"Could not load total trade counts: {e}")

        for s in all_strategies:
            md = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
            tname = md.get("template_name", "")
            if not tname:
                name = s.name or ""
                tname = re.sub(r'\s+V\d+$', '', name).strip()
            if not tname:
                continue

            if tname not in template_stats:
                template_stats[tname] = {
                    "total": 0, "active": 0, "activated": 0, "traded": 0,
                    "sharpes": [], "win_rates": [],
                    "returns": [], "trades": 0, "pnl": 0.0,
                    "symbols_pnl": {}, "last_proposed": None, "last_activated": None,
                }
            ts = template_stats[tname]
            ts["total"] += 1

            # Active = open positions right now for strategies using this template
            ts["active"] += open_positions_by_strategy.get(s.id, 0)

            # Traded = total positions (open + closed) for strategies using this template
            ts["traded"] += total_trades_by_strategy.get(s.id, 0)

            # Count strategies that passed activation (for success_rate calculation)
            is_activated = (
                s.status in (StrategyStatus.DEMO.value, StrategyStatus.LIVE.value, "DEMO", "LIVE")
                or (md.get('activation_approved', False))
            )
            if is_activated:
                ts["activated"] += 1

            perf = s.performance if isinstance(s.performance, dict) else {}
            sharpe = perf.get("sharpe_ratio", 0)
            wr = perf.get("win_rate", 0)
            ret = perf.get("total_return", 0)
            trades = perf.get("total_trades", 0)

            if s.status in (StrategyStatus.DEMO.value, StrategyStatus.LIVE.value, "DEMO", "LIVE"):
                if sharpe and not (math.isnan(sharpe) or math.isinf(sharpe)):
                    ts["sharpes"].append(sharpe)
                if wr and not (math.isnan(wr) or math.isinf(wr)):
                    ts["win_rates"].append(wr)
                if ret and not (math.isnan(ret) or math.isinf(ret)):
                    ts["returns"].append(ret)
                ts["trades"] += trades

            syms = s.symbols if isinstance(s.symbols, list) else []
            primary = syms[0] if syms else None
            if primary:
                pos_pnl = db.query(
                    sa_func.coalesce(sa_func.sum(PositionORM.unrealized_pnl), 0.0)
                ).filter(
                    PositionORM.strategy_id == s.id,
                    PositionORM.closed_at.is_(None)
                ).scalar() or 0.0
                ts["symbols_pnl"][primary] = ts["symbols_pnl"].get(primary, 0.0) + float(pos_pnl)
                ts["pnl"] += float(pos_pnl)

            created = str(s.created_at) if s.created_at else None
            activated = str(s.activated_at) if s.activated_at else None
            if created and (not ts["last_proposed"] or created > ts["last_proposed"]):
                ts["last_proposed"] = created
            if activated and (not ts["last_activated"] or activated > ts["last_activated"]):
                ts["last_activated"] = activated

        def _get_template_asset_classes(template) -> List[str]:
            md = template.metadata or {}
            classes = set()
            if md.get('crypto_only') or 'crypto' in template.name.lower():
                classes.add('crypto')
            if md.get('forex_only') or 'forex' in template.name.lower():
                classes.add('forex')
            fixed = md.get('fixed_symbols', [])
            if fixed:
                from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX
                crypto_set = set(DEMO_ALLOWED_CRYPTO)
                forex_set = set(DEMO_ALLOWED_FOREX)
                for sym in (fixed if isinstance(fixed, list) else [fixed]):
                    if sym in crypto_set:
                        classes.add('crypto')
                    elif sym in forex_set:
                        classes.add('forex')
                    else:
                        classes.add('stock')
            if not classes:
                classes = {'stock', 'etf', 'crypto', 'forex', 'index', 'commodity'}
            return sorted(classes)

        # Load proposal tracker for Proposed/Approved counts
        proposal_counts = {}
        try:
            from src.strategy.strategy_proposer import StrategyProposer
            # Load directly from disk (don't need a full StrategyProposer instance)
            import json as _json_pt
            from pathlib import Path as _Path_pt
            _pt_path = _Path_pt("config/.proposal_tracker.json")
            if _pt_path.exists():
                with open(_pt_path, 'r') as f:
                    proposal_counts = _json_pt.load(f)
        except Exception as e:
            logger.debug(f"Could not load proposal tracker: {e}")

        template_responses = []
        for template in templates:
            md = template.metadata or {}
            ts = template_stats.get(template.name, {})

            sharpes = ts.get("sharpes", [])
            win_rates = ts.get("win_rates", [])
            returns = ts.get("returns", [])
            symbols_pnl = ts.get("symbols_pnl", {})

            best_sym = max(symbols_pnl, key=symbols_pnl.get) if symbols_pnl else None
            worst_sym = min(symbols_pnl, key=symbols_pnl.get) if symbols_pnl else None

            total_used = ts.get("total", 0)
            active_count = ts.get("active", 0)
            success_rate = (ts.get("activated", 0) / total_used * 100) if total_used > 0 else 0.0

            is_intraday = md.get('intraday', False) and not md.get('interval_4h', False)
            is_4h = md.get('interval_4h', False)
            interval = '1h' if is_intraday else ('4h' if is_4h else '1d')

            template_responses.append(TemplateResponse(
                name=template.name,
                description=template.description,
                market_regimes=[r.value for r in template.market_regimes],
                indicators=template.required_indicators,
                entry_rules=template.entry_conditions,
                exit_rules=template.exit_conditions,
                success_rate=round(success_rate, 1),
                usage_count=total_used,
                strategy_type=template.strategy_type.value if template.strategy_type else None,
                direction=md.get('direction', 'long'),
                asset_classes=_get_template_asset_classes(template),
                expected_trade_frequency=template.expected_trade_frequency,
                expected_holding_period=template.expected_holding_period,
                risk_reward_ratio=template.risk_reward_ratio,
                enabled=template.name not in disabled_templates,
                active_strategies=active_count,
                total_strategies_ever=total_used,
                avg_sharpe=round(sum(sharpes) / len(sharpes), 2) if sharpes else None,
                avg_win_rate=round(sum(win_rates) / len(win_rates), 3) if win_rates else None,
                avg_return=round(sum(returns) / len(returns), 4) if returns else None,
                total_trades_live=ts.get("trades", 0),
                total_pnl=round(ts.get("pnl", 0), 2) if ts.get("pnl") else None,
                best_symbol=best_sym,
                worst_symbol=worst_sym,
                last_proposed=ts.get("last_proposed"),
                last_activated=ts.get("last_activated"),
                is_intraday=is_intraday,
                is_4h=is_4h,
                interval=interval,
                activated_count=ts.get("activated", 0),
                traded_count=ts.get("traded", 0),
                proposed_count=proposal_counts.get(template.name, {}).get('proposed', 0),
                approved_count=proposal_counts.get(template.name, {}).get('approved', 0),
                strategy_category=md.get('strategy_category', 'template_based'),
            ))

        return TemplatesListResponse(templates=template_responses, total=len(template_responses))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch strategy templates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch templates: {str(e)}")


class SymbolStatsResponse(BaseModel):
    """Per-symbol statistics response model."""
    symbol: str
    asset_class: str
    sector: str
    active_strategies: int = 0
    activated_count: int = 0
    traded_count: int = 0
    usage_count: int = 0
    proposed_count: int = 0
    approved_count: int = 0
    avg_sharpe: Optional[float] = None
    avg_win_rate: Optional[float] = None
    total_pnl: Optional[float] = None
    total_trades_live: int = 0
    open_positions: int = 0
    best_template: Optional[str] = None
    worst_template: Optional[str] = None
    last_signal: Optional[str] = None
    last_trade: Optional[str] = None


class SymbolsListResponse(BaseModel):
    """Symbols list response model."""
    symbols: List[SymbolStatsResponse]
    total: int


@router.get("/symbols", response_model=SymbolsListResponse)
async def get_symbol_stats(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """Get all tradeable symbols with usage stats and live performance."""
    logger.info("Fetching symbol stats")

    try:
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_STOCKS, DEMO_ALLOWED_ETFS, DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_CRYPTO,
            get_all_tradeable_symbols,
        )
        from src.risk.risk_manager import get_symbol_sector

        all_symbols = get_all_tradeable_symbols()

        # Build asset class lookup
        asset_class_map = {}
        for s in DEMO_ALLOWED_STOCKS:
            asset_class_map[s] = "stock"
        for s in DEMO_ALLOWED_ETFS:
            asset_class_map[s] = "etf"
        for s in DEMO_ALLOWED_FOREX:
            asset_class_map[s] = "forex"
        for s in DEMO_ALLOWED_INDICES:
            asset_class_map[s] = "index"
        for s in DEMO_ALLOWED_COMMODITIES:
            asset_class_map[s] = "commodity"
        for s in DEMO_ALLOWED_CRYPTO:
            asset_class_map[s] = "crypto"

        # Query all strategies for per-symbol stats
        all_strategies = db.query(StrategyORM).all()

        # Build per-symbol stats
        symbol_stats: Dict[str, Dict] = {}
        for sym in all_symbols:
            symbol_stats[sym] = {
                "active": 0, "activated": 0, "traded": 0, "total": 0,
                "sharpes": [], "win_rates": [], "trades": 0, "pnl": 0.0,
                "templates_pnl": {}, "last_signal": None, "last_trade": None,
            }

        for s in all_strategies:
            md = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
            syms = s.symbols if isinstance(s.symbols, list) else []
            perf = s.performance if isinstance(s.performance, dict) else {}

            is_activated = (
                s.status in (StrategyStatus.DEMO.value, StrategyStatus.LIVE.value, "DEMO", "LIVE")
                or md.get('activation_approved', False)
            )
            live_trades = perf.get("total_trades", 0)
            has_traded = (
                s.status in (StrategyStatus.DEMO.value, StrategyStatus.LIVE.value, "DEMO", "LIVE")
                and live_trades > 0
            )

            tname = md.get("template_name", s.name or "")

            for sym in syms:
                sym_upper = sym.upper()
                if sym_upper not in symbol_stats:
                    symbol_stats[sym_upper] = {
                        "active": 0, "activated": 0, "traded": 0, "total": 0,
                        "sharpes": [], "win_rates": [], "trades": 0, "pnl": 0.0,
                        "templates_pnl": {}, "last_signal": None, "last_trade": None,
                    }

                ss = symbol_stats[sym_upper]
                ss["total"] += 1

                if is_activated:
                    ss["activated"] += 1
                if has_traded:
                    ss["traded"] += 1

                if s.status in (StrategyStatus.DEMO.value, StrategyStatus.LIVE.value, "DEMO", "LIVE"):
                    ss["active"] += 1
                    sharpe = perf.get("sharpe_ratio", 0)
                    wr = perf.get("win_rate", 0)
                    if sharpe and not (math.isnan(sharpe) or math.isinf(sharpe)):
                        ss["sharpes"].append(sharpe)
                    if wr and not (math.isnan(wr) or math.isinf(wr)):
                        ss["win_rates"].append(wr)
                    ss["trades"] += live_trades

                # P&L from open positions for this symbol
                pos_pnl = db.query(
                    sa_func.coalesce(sa_func.sum(PositionORM.unrealized_pnl), 0.0)
                ).filter(
                    PositionORM.strategy_id == s.id,
                    PositionORM.symbol == sym_upper,
                    PositionORM.closed_at.is_(None)
                ).scalar() or 0.0
                ss["pnl"] += float(pos_pnl)

                if tname:
                    ss["templates_pnl"][tname] = ss["templates_pnl"].get(tname, 0.0) + float(pos_pnl)

                created = str(s.created_at) if s.created_at else None
                activated = str(s.activated_at) if s.activated_at else None
                if created and (not ss["last_signal"] or created > ss["last_signal"]):
                    ss["last_signal"] = created
                if activated and (not ss["last_trade"] or activated > ss["last_trade"]):
                    ss["last_trade"] = activated

        # Count open positions per symbol
        open_positions = db.query(
            PositionORM.symbol, sa_func.count(PositionORM.id)
        ).filter(
            PositionORM.closed_at.is_(None),
            PositionORM.pending_closure == False
        ).group_by(PositionORM.symbol).all()
        pos_count_map = {row[0]: row[1] for row in open_positions}

        # Build response
        symbol_responses = []
        for sym in all_symbols:
            ss = symbol_stats.get(sym, {})
            sharpes = ss.get("sharpes", [])
            win_rates = ss.get("win_rates", [])
            templates_pnl = ss.get("templates_pnl", {})

            best_tpl = max(templates_pnl, key=templates_pnl.get) if templates_pnl else None
            worst_tpl = min(templates_pnl, key=templates_pnl.get) if templates_pnl else None

            symbol_responses.append(SymbolStatsResponse(
                symbol=sym,
                asset_class=asset_class_map.get(sym, "unknown"),
                sector=get_symbol_sector(sym),
                active_strategies=ss.get("active", 0),
                activated_count=ss.get("activated", 0),
                traded_count=ss.get("traded", 0),
                usage_count=ss.get("total", 0),
                avg_sharpe=round(sum(sharpes) / len(sharpes), 2) if sharpes else None,
                avg_win_rate=round(sum(win_rates) / len(win_rates), 3) if win_rates else None,
                total_pnl=round(ss.get("pnl", 0), 2) if ss.get("pnl") else None,
                total_trades_live=ss.get("trades", 0),
                open_positions=pos_count_map.get(sym, 0),
                best_template=best_tpl,
                worst_template=worst_tpl,
                last_signal=ss.get("last_signal"),
                last_trade=ss.get("last_trade"),
            ))

        return SymbolsListResponse(symbols=symbol_responses, total=len(symbol_responses))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch symbol stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch symbol stats: {str(e)}")


@router.put("/templates/bulk-toggle", response_model=StrategyActionResponse)
async def bulk_toggle_templates(
    request: Dict[str, Any],
    username: str = Depends(get_current_user),
):
    """Bulk enable/disable templates. Body: { "templates": {"name": true/false, ...} }"""
    import json
    from pathlib import Path

    toggles = request.get("templates", {})
    logger.info(f"Bulk toggle {len(toggles)} templates by {username}")

    disabled_path = Path("config/.disabled_templates.json")
    disabled_templates = set()
    try:
        if disabled_path.exists():
            with open(disabled_path, 'r') as f:
                disabled_templates = set(json.load(f))
    except Exception:
        pass

    for name, enabled in toggles.items():
        if enabled:
            disabled_templates.discard(name)
        else:
            disabled_templates.add(name)

    with open(disabled_path, 'w') as f:
        json.dump(sorted(disabled_templates), f, indent=2)

    return StrategyActionResponse(
        success=True,
        message=f"Updated {len(toggles)} templates",
        strategy_id="bulk",
    )


@router.put("/templates/{template_name}/toggle", response_model=StrategyActionResponse)
async def toggle_template(
    template_name: str,
    request: ToggleTemplateRequest,
    username: str = Depends(get_current_user),
):
    """Enable or disable a strategy template for autonomous cycles."""
    import json
    from pathlib import Path

    logger.info(f"Toggle template '{template_name}' enabled={request.enabled} by {username}")

    disabled_path = Path("config/.disabled_templates.json")
    disabled_templates = set()
    try:
        if disabled_path.exists():
            with open(disabled_path, 'r') as f:
                disabled_templates = set(json.load(f))
    except Exception:
        pass

    if request.enabled:
        disabled_templates.discard(template_name)
    else:
        disabled_templates.add(template_name)

    with open(disabled_path, 'w') as f:
        json.dump(sorted(disabled_templates), f, indent=2)

    return StrategyActionResponse(
        success=True,
        message=f"Template '{template_name}' {'enabled' if request.enabled else 'disabled'}",
        strategy_id=template_name,
    )


# ============================================================================
# Static-path GET routes — MUST be defined before /{strategy_id} wildcard
# ============================================================================

class TemplateRankingResponse(BaseModel):
    name: str
    win_rate: Optional[float] = None
    avg_sharpe: Optional[float] = None
    total_trades: int = 0
    active_count: int = 0
    last_proposal_date: Optional[str] = None

class TemplateRankingsListResponse(BaseModel):
    rankings: List[TemplateRankingResponse]
    total: int

class BlacklistEntry(BaseModel):
    template: str
    symbol: str
    count: int
    timestamp: str
    type: str

class BlacklistResponse(BaseModel):
    entries: List[BlacklistEntry]
    total: int

class IdleDemotionEntry(BaseModel):
    name: str
    strategy_id: str
    timestamp: str
    reason: str

class IdleDemotionsResponse(BaseModel):
    entries: List[IdleDemotionEntry]
    total: int


@router.get("/template-rankings", response_model=TemplateRankingsListResponse)
async def get_template_rankings(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    """Get template performance rankings with aggregate metrics."""
    logger.info(f"Fetching template rankings for {mode.value} mode, user {username}")
    try:
        all_strategies = session.query(StrategyORM).all()
        from sqlalchemy import func as _tf
        pos_counts = session.query(
            PositionORM.strategy_id, _tf.count(PositionORM.id),
        ).filter(PositionORM.closed_at.is_(None)).group_by(PositionORM.strategy_id).all()
        open_positions_by_strategy = {sid: cnt for sid, cnt in pos_counts}
        template_data: Dict[str, Dict[str, Any]] = {}
        for s in all_strategies:
            md = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
            tname = md.get("template_name", "")
            if not tname:
                name = s.name or ""
                tname = re.sub(r'\s+V\d+$', '', name).strip()
            if not tname:
                continue
            if tname not in template_data:
                template_data[tname] = {"win_rates": [], "sharpes": [], "total_trades": 0, "active_count": 0, "last_proposal_date": None}
            td = template_data[tname]
            td["active_count"] += open_positions_by_strategy.get(s.id, 0)
            perf = s.performance if isinstance(s.performance, dict) else {}
            wr = perf.get("win_rate", 0)
            sharpe = perf.get("sharpe_ratio", 0)
            trades = perf.get("total_trades", 0)
            if s.status in (StrategyStatus.DEMO.value, StrategyStatus.LIVE.value, "DEMO", "LIVE"):
                if wr and not (math.isnan(wr) or math.isinf(wr)):
                    td["win_rates"].append(wr)
                if sharpe and not (math.isnan(sharpe) or math.isinf(sharpe)):
                    td["sharpes"].append(sharpe)
                td["total_trades"] += trades
            created = str(s.created_at) if s.created_at else None
            if created and (not td["last_proposal_date"] or created > td["last_proposal_date"]):
                td["last_proposal_date"] = created
        rankings = []
        for tname, td in template_data.items():
            win_rates = td["win_rates"]
            sharpes = td["sharpes"]
            rankings.append(TemplateRankingResponse(
                name=tname,
                win_rate=round(sum(win_rates) / len(win_rates), 4) if win_rates else None,
                avg_sharpe=round(sum(sharpes) / len(sharpes), 2) if sharpes else None,
                total_trades=td["total_trades"],
                active_count=td["active_count"],
                last_proposal_date=td["last_proposal_date"],
            ))
        rankings.sort(key=lambda r: r.avg_sharpe if r.avg_sharpe is not None else float('-inf'), reverse=True)
        return TemplateRankingsListResponse(rankings=rankings, total=len(rankings))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch template rankings: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/blacklisted-combos", response_model=BlacklistResponse)
async def get_blacklisted_combos(
    username: str = Depends(get_current_user),
):
    """Get all blacklisted template+symbol combinations from config files."""
    import json
    from pathlib import Path
    entries: List[BlacklistEntry] = []
    rej_path = Path("config/.rejection_blacklist.json")
    if rej_path.exists():
        try:
            with open(rej_path) as f:
                data = json.load(f)
            for e in data.get("entries", []):
                if e.get("count", 0) >= 3:
                    entries.append(BlacklistEntry(template=e.get("template", ""), symbol=e.get("symbol", ""), count=e.get("count", 0), timestamp=e.get("timestamp", ""), type="rejection"))
        except Exception as ex:
            logger.warning(f"Failed to load rejection blacklist: {ex}")
    zt_path = Path("config/.zero_trade_blacklist.json")
    if zt_path.exists():
        try:
            with open(zt_path) as f:
                data = json.load(f)
            for e in data.get("entries", []):
                entries.append(BlacklistEntry(template=e.get("template", ""), symbol=e.get("symbol", ""), count=e.get("count", 0), timestamp=e.get("timestamp", ""), type="zero_trade"))
        except Exception as ex:
            logger.warning(f"Failed to load zero-trade blacklist: {ex}")
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return BlacklistResponse(entries=entries, total=len(entries))


@router.get("/idle-demotions", response_model=IdleDemotionsResponse)
async def get_idle_demotions(
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    """Get recently demoted strategies."""
    from src.models.orm import StrategyRetirementORM
    entries: List[IdleDemotionEntry] = []
    demoted = session.query(StrategyORM).filter(StrategyORM.status == "BACKTESTED").all()
    for s in demoted:
        md = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
        if md.get("demoted") or md.get("demotion_reason"):
            entries.append(IdleDemotionEntry(
                name=s.name or "",
                strategy_id=s.id,
                timestamp=md.get("demoted_at", str(s.created_at) if s.created_at else ""),
                reason=md.get("demotion_reason", "Idle — no positions or orders"),
            ))
    retirements = session.query(StrategyRetirementORM).order_by(StrategyRetirementORM.retired_at.desc()).limit(50).all()
    for r in retirements:
        reason = r.reason if hasattr(r, 'reason') else ""
        if reason and ("idle" in reason.lower() or "inactiv" in reason.lower() or "no trade" in reason.lower()):
            strat = session.query(StrategyORM).filter(StrategyORM.id == r.strategy_id).first()
            entries.append(IdleDemotionEntry(
                name=strat.name if strat else r.strategy_id,
                strategy_id=r.strategy_id,
                timestamp=r.retired_at.isoformat() if r.retired_at else "",
                reason=reason,
            ))
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return IdleDemotionsResponse(entries=entries, total=len(entries))


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get specific strategy.
    
    Args:
        strategy_id: Strategy ID
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Strategy details
        
    Raises:
        HTTPException: If strategy not found
        
    Validates: Requirement 11.3
    """
    logger.info(f"Getting strategy {strategy_id} for {mode.value} mode, user {username}")
    
    # Query strategy from database
    strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {strategy_id} not found"
        )
    
    # Convert to response model
    strategy_dict = strategy.to_dict()
    metadata = strategy_dict.get("metadata", {})
    
    # Extract entry/exit rules from rules dict
    rules_dict = strategy_dict.get("rules", {})
    entry_rules = rules_dict.get("entry", []) if isinstance(rules_dict.get("entry"), list) else None
    exit_rules = rules_dict.get("exit", []) if isinstance(rules_dict.get("exit"), list) else None
    
    # Extract walk-forward results from backtest_results
    backtest_results = strategy_dict.get("backtest_results", {})
    walk_forward_results = backtest_results.get("walk_forward_results") if backtest_results else None
    
    # Task 9.7: Extract strategy metadata fields
    strategy_category = metadata.get("strategy_category", "template_based")
    strategy_type = metadata.get("strategy_type")
    requires_fundamental_data = metadata.get("requires_fundamental_data", False)
    requires_earnings_data = metadata.get("requires_earnings_data", False)
    
    return StrategyResponse(
        id=strategy_dict["id"],
        name=strategy_dict["name"],
        description=strategy_dict["description"],
        status=StrategyStatus(strategy_dict["status"]),
        rules=strategy_dict["rules"],
        symbols=strategy_dict["symbols"],
        allocation_percent=strategy_dict["allocation_percent"],
        risk_params=strategy_dict["risk_params"],
        created_at=strategy_dict["created_at"],
        activated_at=strategy_dict.get("activated_at"),
        retired_at=strategy_dict.get("retired_at"),
        performance_metrics=PerformanceMetricsResponse(**strategy_dict["performance"]),
        reasoning=strategy_dict.get("reasoning"),
        updated_at=strategy_dict.get("created_at"),
        # Enhanced fields
        source=metadata.get("source", "USER" if not metadata.get("template_name") else "TEMPLATE"),
        template_name=metadata.get("template_name"),
        market_regime=metadata.get("market_regime") or metadata.get("activation_regime"),
        entry_rules=entry_rules,
        exit_rules=exit_rules,
        walk_forward_results=walk_forward_results,
        metadata=metadata,
        # Task 9.7: Include strategy metadata fields
        strategy_category=strategy_category,
        strategy_type=strategy_type,
        requires_fundamental_data=requires_fundamental_data,
        requires_earnings_data=requires_earnings_data
    )


@router.put("/{strategy_id}", response_model=StrategyActionResponse)
async def update_strategy(
    strategy_id: str,
    request: UpdateStrategyRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Update strategy.
    
    Args:
        strategy_id: Strategy ID
        request: Strategy update request
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Success response
        
    Validates: Requirement 11.3
    """
    logger.info(f"Updating strategy {strategy_id} for {mode.value} mode, user {username}")
    
    try:
        # Integrate with StrategyEngine to update real strategy
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        
        # Initialize components
        strategy_engine = _get_strategy_engine(mode)
        
        # Get strategy
        strategy = strategy_engine.get_strategy(strategy_id)
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Update fields if provided
        if request.name:
            strategy.name = request.name
        if request.description:
            strategy.description = request.description
        if request.rules:
            strategy.rules = request.rules
        if request.symbols:
            strategy.symbols = request.symbols
        if request.risk_params:
            # Update risk params
            for key, value in request.risk_params.items():
                if hasattr(strategy.risk_params, key):
                    setattr(strategy.risk_params, key, value)
        
        # Save updated strategy
        strategy_engine._save_strategy(strategy)
        
        logger.info(f"Strategy {strategy_id} updated successfully")
        
        return StrategyActionResponse(
            success=True,
            message="Strategy updated successfully",
            strategy_id=strategy_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update strategy: {str(e)}"
        )


@router.delete("/{strategy_id}", response_model=StrategyActionResponse)
async def retire_strategy(
    strategy_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Retire strategy and remove it from the database.
    
    Args:
        strategy_id: Strategy ID
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Success response
        
    Validates: Requirement 11.3
    """
    logger.info(f"Retiring strategy {strategy_id} for {mode.value} mode, user {username}")
    
    try:
        # Integrate with StrategyEngine to retire real strategy
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        
        # Initialize components
        strategy_engine = _get_strategy_engine(mode)
        
        # Retire strategy
        strategy_engine.retire_strategy(
            strategy_id=strategy_id,
            reason=f"Manual retirement by {username}"
        )
        
        # Delete the strategy from the database
        strategy_orm = session.query(StrategyORM).filter(StrategyORM.id == strategy_id).first()
        if strategy_orm:
            session.delete(strategy_orm)
            session.commit()
            logger.info(f"Strategy {strategy_id} deleted from database")
        
        logger.info(f"Strategy {strategy_id} retired successfully")
        
        return StrategyActionResponse(
            success=True,
            message="Strategy retired and removed successfully",
            strategy_id=strategy_id
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to retire strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retire strategy: {str(e)}"
        )


@router.delete("/{strategy_id}/permanent", response_model=StrategyActionResponse)
async def permanently_delete_strategy(
    strategy_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Permanently delete a retired strategy from the database.
    
    This endpoint only works for strategies with RETIRED status.
    Active or backtested strategies must be retired first.
    
    Args:
        strategy_id: Strategy ID
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Success response
    """
    logger.info(f"Permanently deleting strategy {strategy_id} for {mode.value} mode, user {username}")
    
    try:
        # Check if strategy exists and is retired
        strategy_orm = session.query(StrategyORM).filter(StrategyORM.id == strategy_id).first()
        
        if not strategy_orm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        if strategy_orm.status != StrategyStatus.RETIRED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Can only permanently delete RETIRED strategies. Current status: {strategy_orm.status.value}"
            )
        
        # Cancel all pending orders for this strategy
        from src.models.orm import OrderORM
        from src.models.enums import OrderStatus
        from src.api.etoro_client import EToroAPIClient
        from src.core.config import get_config
        
        pending_orders = session.query(OrderORM).filter(
            OrderORM.strategy_id == strategy_id,
            OrderORM.status == OrderStatus.PENDING
        ).all()
        
        if pending_orders:
            logger.info(f"Cancelling {len(pending_orders)} pending orders for strategy {strategy_id}")
            
            # Initialize eToro client
            config = get_config()
            credentials = config.get_etoro_credentials(mode)
            etoro_client = EToroAPIClient(
                account_id=credentials["account_id"],
                public_key=credentials["public_key"],
                user_key=credentials["user_key"],
                mode=mode
            )
            
            for order in pending_orders:
                try:
                    # Cancel via eToro API if order has eToro ID
                    if order.etoro_order_id:
                        success = etoro_client.cancel_order(order.etoro_order_id)
                        if success:
                            order.status = OrderStatus.CANCELLED
                            logger.info(f"Cancelled order {order.id} (eToro: {order.etoro_order_id}) on eToro")
                        else:
                            logger.warning(f"Failed to cancel order {order.id} on eToro, marking as cancelled locally")
                            order.status = OrderStatus.CANCELLED
                    else:
                        # Order not yet submitted to eToro, just mark as cancelled
                        order.status = OrderStatus.CANCELLED
                        logger.info(f"Cancelled order {order.id} (not yet submitted to eToro)")
                except Exception as e:
                    logger.error(f"Error cancelling order {order.id}: {e}")
                    # Still mark as cancelled locally
                    order.status = OrderStatus.CANCELLED
        
        # Delete the strategy from the database
        session.delete(strategy_orm)
        session.commit()
        logger.info(f"Strategy {strategy_id} permanently deleted from database by {username}")
        
        return StrategyActionResponse(
            success=True,
            message="Strategy permanently deleted successfully",
            strategy_id=strategy_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to permanently delete strategy: {e}")
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to permanently delete strategy: {str(e)}"
        )


@router.post("/{strategy_id}/activate", response_model=StrategyActionResponse)
async def activate_strategy(
    strategy_id: str,
    mode: TradingMode,
    allocation_percent: float = 5.0,
    username: str = Depends(get_current_user)
):
    """
    Activate strategy.
    
    Args:
        strategy_id: Strategy ID
        mode: Trading mode (DEMO or LIVE)
        allocation_percent: Percentage of portfolio to allocate (0.0 to 100.0)
        username: Current authenticated user
        
    Returns:
        Success response
        
    Validates: Requirement 11.3
    """
    logger.info(
        f"Activating strategy {strategy_id} for {mode.value} mode "
        f"with {allocation_percent:.1f}% allocation, user {username}"
    )
    
    try:
        # Get strategy engine with proper dependencies
        strategy_engine = _get_strategy_engine(mode)
        
        # Activate strategy
        strategy_engine.activate_strategy(strategy_id, mode, allocation_percent)
        
        logger.info(
            f"Strategy {strategy_id} activated in {mode.value} mode "
            f"with {allocation_percent:.1f}% allocation"
        )
        
        return StrategyActionResponse(
            success=True,
            message=f"Strategy activated in {mode.value} mode with {allocation_percent:.1f}% allocation",
            strategy_id=strategy_id
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to activate strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate strategy: {str(e)}"
        )


@router.post("/{strategy_id}/deactivate", response_model=StrategyActionResponse)
async def deactivate_strategy(
    strategy_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user)
):
    """
    Deactivate strategy.
    
    Args:
        strategy_id: Strategy ID
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        
    Returns:
        Success response
        
    Validates: Requirement 11.3
    """
    logger.info(f"Deactivating strategy {strategy_id} for {mode.value} mode, user {username}")
    
    try:
        # Get strategy engine with proper dependencies
        strategy_engine = _get_strategy_engine(mode)
        
        # Deactivate strategy
        strategy_engine.deactivate_strategy(strategy_id)
        
        logger.info(f"Strategy {strategy_id} deactivated")
        
        return StrategyActionResponse(
            success=True,
            message="Strategy deactivated",
            strategy_id=strategy_id
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to deactivate strategy: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate strategy: {str(e)}"
        )


@router.get("/{strategy_id}/performance", response_model=PerformanceMetricsResponse)
async def get_strategy_performance(
    strategy_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get strategy performance metrics.
    
    Args:
        strategy_id: Strategy ID
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Performance metrics
        
    Validates: Requirement 11.3
    """
    logger.info(f"Getting performance for strategy {strategy_id}, {mode.value} mode, user {username}")
    
    # Get strategy from database
    strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy {strategy_id} not found"
        )
    
    # Return performance from database
    return PerformanceMetricsResponse(**strategy.performance)


@router.post("/vibe-code/translate", response_model=TradingCommandResponse)
async def translate_vibe_code(
    request: VibeCodeRequest,
    username: str = Depends(get_current_user)
):
    """
    Translate natural language to trading command using vibe-coding.
    
    Args:
        request: Natural language trading command
        username: Current authenticated user
        
    Returns:
        Structured trading command
        
    Raises:
        HTTPException: If translation fails or LLM unavailable
        
    Validates: Requirement 11.10
    """
    logger.info(f"Translating vibe code for user {username}: '{request.natural_language}'")
    
    try:
        # Integrate with LLM service for real translation
        from src.llm.llm_service import LLMService
        
        llm_service = LLMService()
        command = llm_service.translate_vibe_code(request.natural_language)
        
        return TradingCommandResponse(
            action=command.action.value,
            symbol=command.symbol,
            quantity=command.quantity,
            price=command.price,
            reason=command.reason,
            translated_from=request.natural_language
        )
        
    except ConnectionError as e:
        logger.error(f"LLM service unavailable: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service is not available. Check logs for details."
        )
    except ValueError as e:
        logger.error(f"Failed to parse vibe code: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not understand the command: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error translating vibe code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while translating the command"
        )


@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_strategies(
    request: BootstrapRequest,
    username: str = Depends(get_current_user)
):
    """
    Bootstrap initial trading strategies.
    
    Generates 2-3 sample strategies with different trading approaches,
    automatically backtests each strategy, and optionally activates
    strategies that meet minimum performance thresholds.
    
    Args:
        request: Bootstrap configuration
        username: Current authenticated user
        
    Returns:
        Summary of created strategies and backtest results
        
    Raises:
        HTTPException: If bootstrap fails or LLM unavailable
        
    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
    """
    logger.info(
        f"Bootstrapping strategies for user {username}: "
        f"types={request.strategy_types}, auto_activate={request.auto_activate}, "
        f"min_sharpe={request.min_sharpe}, backtest_days={request.backtest_days}"
    )
    
    try:
        # Initialize components
        from src.strategy.bootstrap_service import BootstrapService
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        
        strategy_engine = _get_strategy_engine(mode)
        bootstrap_service = BootstrapService(strategy_engine, llm_service, market_data)
        
        # Execute bootstrap
        result = bootstrap_service.bootstrap_strategies(
            strategy_types=request.strategy_types,
            auto_activate=request.auto_activate,
            min_sharpe=request.min_sharpe,
            backtest_days=request.backtest_days
        )
        
        # Build response with strategy information and backtest results
        strategy_infos = []
        for strategy in result["strategies"]:
            # Get backtest results if available
            backtest_summary = None
            if strategy.id in result["backtest_results"]:
                bt_results = result["backtest_results"][strategy.id]
                backtest_summary = BacktestResultsSummary(
                    total_return=bt_results.total_return,
                    sharpe_ratio=bt_results.sharpe_ratio,
                    sortino_ratio=bt_results.sortino_ratio,
                    max_drawdown=bt_results.max_drawdown,
                    win_rate=bt_results.win_rate,
                    total_trades=bt_results.total_trades
                )
            
            strategy_infos.append(BootstrapStrategyInfo(
                id=strategy.id,
                name=strategy.name,
                description=strategy.description,
                status=strategy.status,
                symbols=strategy.symbols,
                allocation_percent=strategy.allocation_percent,
                backtest_results=backtest_summary
            ))
        
        # Build success message
        summary = result["summary"]
        message_parts = [
            f"Generated {summary['total_generated']} strategies",
            f"backtested {summary['total_backtested']}"
        ]
        
        if request.auto_activate:
            message_parts.append(f"activated {summary['total_activated']}")
        
        if summary.get("errors"):
            message_parts.append(f"with {len(summary['errors'])} errors")
        
        message = ", ".join(message_parts)
        
        logger.info(f"Bootstrap complete: {message}")
        
        return BootstrapResponse(
            success=True,
            message=message,
            strategies=strategy_infos,
            summary=summary
        )
        
    except ConnectionError as e:
        logger.error(f"LLM service unavailable during bootstrap: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service is not available. Strategy generation uses templates — check logs for details."
        )
    except Exception as e:
        logger.error(f"Bootstrap failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bootstrap strategies: {str(e)}"
        )


@router.post("/generate", response_model=StrategyResponse)
async def generate_strategy(
    request: GenerateStrategyRequest,
    mode: TradingMode = Query(TradingMode.DEMO, description="Trading mode"),
    username: str = Depends(get_current_user)
):
    """
    Generate trading strategy from natural language prompt.
    
    Uses LLM to translate natural language description into a structured
    strategy definition with rules, indicators, and risk parameters.
    The generated strategy is created with PROPOSED status.
    
    Args:
        request: Strategy generation request with prompt and constraints
        username: Current authenticated user
        
    Returns:
        Generated strategy with PROPOSED status
        
    Raises:
        HTTPException: If generation fails or LLM unavailable
        
    Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
    """
    logger.info(
        f"Generating strategy for user {username}: prompt='{request.prompt[:50]}...'"
    )
    
    try:
        # Initialize components
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        
        strategy_engine = _get_strategy_engine(mode)
        
        # Generate strategy using LLM
        strategy = strategy_engine.generate_strategy(
            prompt=request.prompt,
            constraints=request.constraints
        )
        
        # Convert reasoning to dict if present
        reasoning_dict = None
        if strategy.reasoning:
            reasoning_dict = {
                "hypothesis": strategy.reasoning.hypothesis,
                "alpha_sources": [
                    {
                        "type": source.type,
                        "weight": source.weight,
                        "description": source.description
                    }
                    for source in strategy.reasoning.alpha_sources
                ],
                "market_assumptions": strategy.reasoning.market_assumptions,
                "signal_logic": strategy.reasoning.signal_logic,
                "confidence_factors": strategy.reasoning.confidence_factors,
                "llm_prompt": strategy.reasoning.llm_prompt,
                "llm_response": strategy.reasoning.llm_response
            }
        
        # Convert to response model
        strategy_dict = {
            "id": strategy.id,
            "name": strategy.name,
            "description": strategy.description,
            "status": strategy.status,
            "rules": strategy.rules,
            "symbols": strategy.symbols,
            "allocation_percent": 0.0,  # New strategies start with 0% allocation
            "risk_params": {
                "max_position_size_pct": strategy.risk_params.max_position_size_pct,
                "max_exposure_pct": strategy.risk_params.max_exposure_pct,
                "max_daily_loss_pct": strategy.risk_params.max_daily_loss_pct,
                "max_drawdown_pct": strategy.risk_params.max_drawdown_pct,
                "position_risk_pct": strategy.risk_params.position_risk_pct,
                "stop_loss_pct": strategy.risk_params.stop_loss_pct,
                "take_profit_pct": strategy.risk_params.take_profit_pct
            },
            "created_at": strategy.created_at.isoformat(),
            "activated_at": None,
            "retired_at": None,
            "performance_metrics": PerformanceMetricsResponse(
                total_return=strategy.performance.total_return,
                sharpe_ratio=strategy.performance.sharpe_ratio,
                sortino_ratio=strategy.performance.sortino_ratio,
                max_drawdown=strategy.performance.max_drawdown,
                win_rate=strategy.performance.win_rate,
                avg_win=strategy.performance.avg_win,
                avg_loss=strategy.performance.avg_loss,
                total_trades=strategy.performance.total_trades
            ),
            "reasoning": reasoning_dict,
            "updated_at": strategy.created_at.isoformat()
        }
        
        logger.info(f"Strategy generated successfully: {strategy.name} (ID: {strategy.id})")
        
        return StrategyResponse(**strategy_dict)
        
    except ConnectionError as e:
        logger.error(f"LLM service unavailable during strategy generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service is not available. Strategy generation uses templates — check logs for details."
        )
    except ValueError as e:
        logger.error(f"Strategy generation validation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to generate valid strategy: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Strategy generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate strategy: {str(e)}"
        )


@router.post("/{strategy_id}/backtest", response_model=BacktestResultsResponse)
async def backtest_strategy(
    strategy_id: str,
    request: BacktestRequest = BacktestRequest(),
    username: str = Depends(get_current_user)
):
    """
    Backtest strategy against historical data.
    
    Executes a vectorbt backtest using historical market data to calculate
    performance metrics. Updates strategy status to BACKTESTED on success.
    
    Args:
        strategy_id: Strategy ID to backtest
        request: Backtest configuration with optional date range
        username: Current authenticated user
        
    Returns:
        Backtest results with performance metrics
        
    Raises:
        HTTPException: If strategy not found, not PROPOSED, or backtest fails
        
    Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.6, 2.7
    """
    logger.info(
        f"Backtesting strategy {strategy_id} for user {username}: "
        f"start={request.start_date}, end={request.end_date}"
    )
    
    try:
        # Initialize components
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        from datetime import timedelta
        
        # Use DEMO mode for backtesting (doesn't affect results, just for initialization)
        strategy_engine = _get_strategy_engine(TradingMode.DEMO)
        
        # Get strategy
        strategy = strategy_engine.get_strategy(strategy_id)
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Validate strategy status
        if strategy.status != StrategyStatus.PROPOSED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Strategy must be PROPOSED to backtest (current status: {strategy.status.value})"
            )
        
        # Set default date range if not provided (90 days)
        end_date = request.end_date if request.end_date else datetime.now()
        start_date = request.start_date if request.start_date else end_date - timedelta(days=90)
        
        # Execute backtest
        results = strategy_engine.backtest_strategy(strategy, start_date, end_date)
        
        # Build response with sanitized float values
        response = BacktestResultsResponse(
            strategy_id=strategy_id,
            total_return=sanitize_float(results.total_return),
            sharpe_ratio=sanitize_float(results.sharpe_ratio),
            sortino_ratio=sanitize_float(results.sortino_ratio),
            max_drawdown=sanitize_float(results.max_drawdown),
            win_rate=sanitize_float(results.win_rate),
            avg_win=sanitize_float(results.avg_win),
            avg_loss=sanitize_float(results.avg_loss),
            total_trades=results.total_trades,
            backtest_period={
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            # Transaction cost analysis
            gross_return=sanitize_float(results.gross_return),
            net_return=sanitize_float(results.net_return),
            total_transaction_costs=sanitize_float(results.total_transaction_costs),
            transaction_costs_pct=sanitize_float(results.transaction_costs_pct),
            total_commission_cost=sanitize_float(results.total_commission_cost),
            total_slippage_cost=sanitize_float(results.total_slippage_cost),
            total_spread_cost=sanitize_float(results.total_spread_cost),
            message=f"Backtest completed successfully. Strategy status updated to BACKTESTED."
        )
        
        logger.info(
            f"Backtest completed for {strategy_id}: "
            f"return={results.total_return:.2%}, sharpe={results.sharpe_ratio:.2f}, "
            f"trades={results.total_trades}"
        )
        
        return response
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Backtest validation failed for {strategy_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Backtest failed for {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to backtest strategy: {str(e)}"
        )



@router.put("/{strategy_id}/allocation", response_model=StrategyActionResponse)
async def update_strategy_allocation(
    strategy_id: str,
    request: UpdateAllocationRequest,
    username: str = Depends(get_current_user)
):
    """
    Update strategy allocation percentage.
    
    Updates the allocation percentage for an active strategy (DEMO or LIVE).
    Validates that total portfolio allocation does not exceed 100%.
    Broadcasts update via WebSocket to connected clients.
    
    Args:
        strategy_id: Strategy ID
        request: Allocation update request
        username: Current authenticated user
        
    Returns:
        Success response
        
    Raises:
        HTTPException: If strategy not found, not active, or allocation exceeds limits
        
    Validates: Requirements 3.4, 7.2, 7.3, 13.1
    """
    logger.info(
        f"Updating allocation for strategy {strategy_id} to {request.allocation_percent:.1f}% "
        f"by user {username}"
    )
    
    try:
        # Initialize components
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        from src.api.websocket_manager import get_websocket_manager
        
        # First, load strategy to determine mode
        db = get_database()
        session = db.get_session()
        try:
            strategy_orm = session.query(StrategyORM).filter_by(id=strategy_id).first()
            
            if not strategy_orm:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Strategy {strategy_id} not found"
                )
            
            # Determine mode from strategy status
            if strategy_orm.status == StrategyStatus.DEMO.value:
                mode = TradingMode.DEMO
            elif strategy_orm.status == StrategyStatus.LIVE.value:
                mode = TradingMode.LIVE
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot update allocation for strategy in {strategy_orm.status} status. "
                           f"Strategy must be active (DEMO or LIVE)."
                )
        finally:
            session.close()
        
        strategy_engine = _get_strategy_engine(mode)
        ws_manager = get_websocket_manager()
        
        # Get strategy
        strategy = strategy_engine.get_strategy(strategy_id)
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found"
            )
        
        # Calculate total allocation of other active strategies
        current_total_allocation = strategy_engine._calculate_total_active_allocation(
            exclude_strategy_id=strategy_id
        )
        
        # Check if new allocation would exceed 100%
        new_total_allocation = current_total_allocation + request.allocation_percent
        if new_total_allocation > 100.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total allocation would exceed 100% (current: {current_total_allocation:.1f}%, "
                       f"requested: {request.allocation_percent:.1f}%, total: {new_total_allocation:.1f}%). "
                       f"Please reduce allocation or deactivate other strategies."
            )
        
        # Store old allocation for logging
        old_allocation = strategy.allocation_percent
        
        # Update strategy allocation
        strategy.allocation_percent = request.allocation_percent
        
        # Save to database
        strategy_engine._save_strategy(strategy)
        
        logger.info(
            f"Updated allocation for strategy {strategy.name} from {old_allocation:.1f}% "
            f"to {request.allocation_percent:.1f}% (total allocation: {new_total_allocation:.1f}%)"
        )
        
        # Broadcast update via WebSocket
        await ws_manager.broadcast({
            "type": "strategy_allocation_update",
            "strategy_id": strategy_id,
            "strategy_name": strategy.name,
            "old_allocation": old_allocation,
            "new_allocation": request.allocation_percent,
            "total_allocation": new_total_allocation,
            "timestamp": datetime.now().isoformat()
        })
        
        return StrategyActionResponse(
            success=True,
            message=f"Strategy allocation updated to {request.allocation_percent:.1f}%",
            strategy_id=strategy_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update strategy allocation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update strategy allocation: {str(e)}"
        )



@router.get("/autonomous/status", response_model=AutonomousStatusResponse)
async def get_autonomous_status(
    username: str = Depends(get_current_user)
):
    """
    Get autonomous trading system status.

    Returns status from database and config files — no heavy initialization.
    """
    logger.info(f"Fetching autonomous status for user {username}")

    try:
        import yaml
        from pathlib import Path
        from datetime import timedelta
        from src.core.config import get_config
        from src.models.orm import StrategyProposalORM, StrategyRetirementORM, PositionORM, AutonomousCycleRunORM

        config = get_config()

        # Load config from YAML (fast file read)
        config_file = Path(config.config_dir) / "autonomous_trading.yaml"
        full_config = {}
        if config_file.exists():
            with open(config_file, 'r') as f:
                full_config = yaml.safe_load(f) or {}

        autonomous_config = full_config.get('autonomous', {})
        enabled = autonomous_config.get('enabled', True)

        # Get market regime from config or default
        market_regime = full_config.get('market_regime', {}).get('current', 'unknown')
        market_confidence = full_config.get('market_regime', {}).get('confidence', 0.0)

        # DB queries for counts and cycle info
        db = get_database()
        session = db.get_session()
        try:
            # Active strategies count
            active_strategy_count = session.query(StrategyORM).filter(
                StrategyORM.status.in_(["DEMO", "LIVE"])
            ).count()

            # Open positions count
            open_positions_count = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).count()

            # Last cycle info
            last_cycle = session.query(AutonomousCycleRunORM).order_by(
                AutonomousCycleRunORM.started_at.desc()
            ).first()

            last_cycle_time = last_cycle.completed_at.isoformat() if last_cycle and last_cycle.completed_at else None
            cycle_duration = last_cycle.duration_seconds if last_cycle else None

            # Try to get regime from last cycle's extra data if not in YAML
            if market_regime == 'unknown' and last_cycle:
                try:
                    cycle_extra = last_cycle.extra_data if hasattr(last_cycle, 'extra_data') else None
                    if cycle_extra and isinstance(cycle_extra, dict):
                        market_regime = cycle_extra.get('market_regime', market_regime)
                        market_confidence = cycle_extra.get('market_confidence', market_confidence)
                except Exception:
                    pass

            # Cycle stats — cumulative totals across ALL cycles
            from sqlalchemy import func as _sqla_func
            cumulative = session.query(
                _sqla_func.coalesce(_sqla_func.sum(AutonomousCycleRunORM.proposals_generated), 0),
                _sqla_func.coalesce(_sqla_func.sum(AutonomousCycleRunORM.backtested), 0),
                _sqla_func.coalesce(_sqla_func.sum(AutonomousCycleRunORM.activated), 0),
                _sqla_func.coalesce(_sqla_func.sum(AutonomousCycleRunORM.strategies_retired), 0),
            ).first()
            proposals_count = int(cumulative[0]) if cumulative else 0
            backtested_count = int(cumulative[1]) if cumulative else 0
            activated_count = int(cumulative[2]) if cumulative else 0
            retired_count = int(cumulative[3]) if cumulative else 0

            # Fallback: if no cycle data, count from DB tables
            if proposals_count == 0:
                proposals_count = session.query(StrategyProposalORM).count()
            if retired_count == 0:
                retired_count = session.query(StrategyRetirementORM).count()

            # Total allocation from active strategies
            total_allocation_result = session.query(
                sa_func.sum(StrategyORM.allocation_percent)
            ).filter(
                StrategyORM.status.in_(["DEMO", "LIVE"])
            ).scalar()
            total_allocation = float(total_allocation_result) if total_allocation_result else 0.0

        finally:
            session.close()

        # Build response with lightweight data
        max_strategies = autonomous_config.get('max_active_strategies', 25)

        response = AutonomousStatusResponse(
            enabled=enabled,
            market_regime=market_regime,
            market_confidence=market_confidence,
            data_quality="good",
            last_cycle_time=last_cycle_time,
            next_scheduled_run=None,
            cycle_duration=cycle_duration,
            cycle_stats=CycleStatsResponse(
                proposals_count=proposals_count,
                backtested_count=backtested_count,
                activated_count=activated_count,
                retired_count=retired_count
            ),
            portfolio_health=PortfolioHealthResponse(
                active_strategies=active_strategy_count,
                max_strategies=max_strategies,
                total_allocation=total_allocation,
                avg_correlation=0.0,
                portfolio_sharpe=0.0
            ),
            template_stats=[]
        )

        logger.info(f"Autonomous status: enabled={enabled}, regime={market_regime}, active={active_strategy_count}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch autonomous status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch autonomous status: {str(e)}"
        )



class TriggerCycleRequest(BaseModel):
    """Trigger autonomous cycle request model."""
    force: bool = Field(
        False,
        description="Force cycle execution even if not scheduled"
    )
    asset_classes: Optional[List[str]] = Field(
        None,
        description="Filter by asset classes: stock, etf, crypto, forex, index, commodity"
    )
    intervals: Optional[List[str]] = Field(
        None,
        description="Filter by intervals: 1d, 1h, 4h"
    )
    strategy_types: Optional[List[str]] = Field(
        None,
        description="Filter by strategy types: dsl, alpha_edge"
    )


class TriggerCycleResponse(BaseModel):
    """Trigger autonomous cycle response model."""
    success: bool
    message: str
    cycle_id: Optional[str] = None
    estimated_duration: Optional[int] = None


class AutonomousConfigResponse(BaseModel):
    """Autonomous configuration response model."""
    config: Dict[str, Any]
    last_updated: Optional[str] = None
    updated_by: Optional[str] = None


class UpdateConfigRequest(BaseModel):
    """Update autonomous configuration request model."""
    config: Dict[str, Any] = Field(
        ...,
        description="Configuration updates (partial or full)"
    )


class UpdateConfigResponse(BaseModel):
    """Update configuration response model."""
    success: bool
    message: str
    config: Dict[str, Any]


@router.post("/autonomous/trigger", response_model=TriggerCycleResponse)
async def trigger_autonomous_cycle(
    request: TriggerCycleRequest = TriggerCycleRequest(),
    username: str = Depends(get_current_user)
):
    """Manually trigger an autonomous trading cycle in a background thread."""
    import sys
    print(f"[TRIGGER] Received trigger request from {username}, force={request.force}", flush=True)
    sys.stdout.flush()
    global _running_cycle_thread, _running_cycle_id
    
    logger.info(f"Manual trigger of autonomous cycle by user {username}, force={request.force}")
    
    # Check if a cycle is already running
    if _running_cycle_thread and _running_cycle_thread.is_alive():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A cycle is already running (ID: {_running_cycle_id}). Please wait for it to complete."
        )
    
    try:
        config = get_config()
        credentials = config.load_credentials(TradingMode.DEMO)
        
        if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="eToro credentials not configured."
            )
        
        etoro_client = EToroAPIClient(
            public_key=credentials["public_key"],
            user_key=credentials["user_key"],
            mode=TradingMode.DEMO
        )
        market_data = MarketDataManager(etoro_client)
        ws_manager = get_websocket_manager()
        strategy_engine = StrategyEngine(None, market_data, ws_manager)
        
        autonomous_manager = AutonomousStrategyManager(
            llm_service=None,
            market_data=market_data,
            strategy_engine=strategy_engine,
            websocket_manager=ws_manager
        )
        
        if not autonomous_manager.config["autonomous"]["enabled"] and not request.force:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Autonomous system is disabled. Use force=true to override."
            )
        
        if not request.force and not autonomous_manager.should_run_cycle():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cycle not scheduled yet. Use force=true to override."
            )
        
        cycle_id = f"cycle_{uuid4().hex[:8]}"
        
        # Broadcast cycle start — show cache_warming as the first stage
        await ws_manager.broadcast({
            "type": "cycle_progress",
            "data": {
                "stage": "cache_warming",
                "status": "running",
                "progress_pct": 0,
                "metrics": {"phase": "Initializing..."},
                "timestamp": datetime.now().isoformat(),
            }
        })
        
        logger.info(f"Starting autonomous cycle {cycle_id} in background thread")
        
        def _make_serializable(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: _make_serializable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_make_serializable(v) for v in obj]
            return obj
        
        def run_cycle_in_thread():
            global _running_cycle_thread, _running_cycle_id
            with open('cycle_error.log', 'w') as f:
                f.write(f"Thread started for {cycle_id} at {datetime.now().isoformat()}\n")
            try:
                # Acquire DB lock — waits for scheduler signal gen to finish if running
                logger.info(f"Cycle {cycle_id}: acquiring DB lock...")
                acquired = _db_cycle_lock.acquire(timeout=30)
                if not acquired:
                    raise RuntimeError("Could not acquire DB lock — scheduler may be stuck")
                logger.info(f"Cycle {cycle_id}: DB lock acquired")
                try:
                    print(f"[TRIGGER] Background thread STARTED for cycle {cycle_id}", flush=True)
                    logger.info(f"Background thread started for cycle {cycle_id}")
                    
                    # Wait for any running signal generation batch to finish before starting
                    # the heavy market analysis. Signal gen takes 150-250s and competes for
                    # CPU/GIL, causing the autonomous cycle to crawl.
                    try:
                        from src.core.trading_scheduler import get_trading_scheduler
                        ts = get_trading_scheduler()
                        if ts and hasattr(ts, '_strategy_engine') and ts._strategy_engine:
                            import time as _wait_time
                            _wait_start = _wait_time.time()
                            _max_wait = 300  # 5 min max
                            while _wait_time.time() - _wait_start < _max_wait:
                                if not getattr(ts._strategy_engine, '_batch_signal_running', False):
                                    break
                                elapsed = _wait_time.time() - _wait_start
                                logger.info(f"Cycle {cycle_id}: waiting for signal generation to finish ({elapsed:.0f}s)")
                                _wait_time.sleep(5)
                            waited = _wait_time.time() - _wait_start
                            if waited > 1:
                                logger.info(f"Cycle {cycle_id}: signal generation finished after {waited:.0f}s wait")
                    except Exception as e:
                        logger.debug(f"Could not check signal gen status: {e}")
                    
                    cycle_filters = {}
                    if request.asset_classes:
                        cycle_filters['asset_classes'] = request.asset_classes
                    if request.intervals:
                        cycle_filters['intervals'] = request.intervals
                    if request.strategy_types:
                        cycle_filters['strategy_types'] = request.strategy_types
                    logger.info(f"Cycle {cycle_id} filters: {cycle_filters if cycle_filters else 'none (all strategies)'}")
                    cycle_result = autonomous_manager.run_strategy_cycle(filters=cycle_filters if cycle_filters else None)
                    
                    # Broadcast completion via new event loop
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(ws_manager.broadcast({
                            "type": "autonomous:cycle_completed",
                            "cycle_id": cycle_id,
                            "timestamp": datetime.now().isoformat(),
                            "result": _make_serializable(cycle_result)
                        }))
                    finally:
                        loop.close()
                    
                    logger.info(f"Autonomous cycle {cycle_id} completed successfully")
                    logger.info("Cycle complete — signal generation ran as part of the cycle")
                    
                    with open('cycle_error.log', 'w') as f:
                        f.write(f"Cycle {cycle_id} completed successfully at {datetime.now().isoformat()}\n")
                finally:
                    _db_cycle_lock.release()
                    logger.info(f"Cycle {cycle_id}: DB lock released")
            except Exception as e:
                import traceback
                with open('cycle_error.log', 'w') as f:
                    f.write(f"CYCLE ERROR for {cycle_id}:\n")
                    f.write(f"{str(e)}\n\n")
                    f.write(traceback.format_exc())
                print(f"[TRIGGER] Background thread FAILED for cycle {cycle_id}: {e}", flush=True)
                logger.error(f"Background cycle {cycle_id} failed: {e}", exc_info=True)
                try:
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        loop.run_until_complete(ws_manager.broadcast({
                            "type": "autonomous:cycle_error",
                            "cycle_id": cycle_id,
                            "timestamp": datetime.now().isoformat(),
                            "error": str(e)
                        }))
                    finally:
                        loop.close()
                except:
                    pass
            finally:
                _running_cycle_id = None
        
        # Start in a daemon thread
        _running_cycle_id = cycle_id
        _running_cycle_thread = threading.Thread(
            target=run_cycle_in_thread,
            name=f"autonomous-cycle-{cycle_id}",
            daemon=True
        )
        print(f"[TRIGGER] Starting background thread for cycle {cycle_id}", flush=True)
        sys.stdout.flush()
        _running_cycle_thread.start()
        
        return TriggerCycleResponse(
            success=True,
            message=f"Autonomous cycle {cycle_id} started in background",
            cycle_id=cycle_id,
            estimated_duration=300
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger autonomous cycle: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger autonomous cycle: {str(e)}"
        )


@router.get("/autonomous/config", response_model=AutonomousConfigResponse)
async def get_autonomous_config(
    username: str = Depends(get_current_user)
):
    """
    Get autonomous trading system configuration.
    
    Returns the current configuration including:
    - General settings (enabled, frequency, strategy limits)
    - Template settings (enabled templates and priorities)
    - Activation thresholds (min Sharpe, max drawdown, etc.)
    - Retirement triggers
    - Advanced settings (backtest period, correlation threshold, etc.)
    
    Args:
        username: Current authenticated user
        
    Returns:
        Current autonomous configuration
        
    Raises:
        HTTPException: If configuration cannot be loaded
        
    Validates: Requirements 3.1, 3.2
    """
    logger.info(f"Fetching autonomous configuration for user {username}")
    
    try:
        import yaml
        from pathlib import Path
        
        config_path = "config/autonomous_trading.yaml"
        
        # Check if config file exists
        if not os.path.exists(config_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Configuration file not found: {config_path}"
            )
        
        # Load configuration from file
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        # Get file modification time
        file_stat = os.stat(config_path)
        last_updated = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
        
        logger.info(f"Successfully loaded autonomous configuration")
        
        return AutonomousConfigResponse(
            config=config,
            last_updated=last_updated,
            updated_by=None  # Could track this in a separate metadata file
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to load autonomous configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load configuration: {str(e)}"
        )


@router.put("/autonomous/config", response_model=UpdateConfigResponse)
async def update_autonomous_config(
    request: UpdateConfigRequest,
    username: str = Depends(get_current_user)
):
    """
    Update autonomous trading system configuration.
    
    Updates the configuration file with new settings. Supports partial updates
    (only specified fields are changed). Validates configuration before saving.
    
    Validation includes:
    - Numeric ranges (e.g., Sharpe ratio >= 0, drawdown 0-1)
    - Strategy limits (min <= max)
    - Frequency values (daily, weekly, monthly)
    - Threshold consistency (activation vs retirement)
    
    Args:
        request: Configuration update request
        username: Current authenticated user
        
    Returns:
        Updated configuration
        
    Raises:
        HTTPException: If validation fails or update cannot be saved
        
    Validates: Requirements 3.1, 3.2
    """
    logger.info(f"Updating autonomous configuration by user {username}")
    
    try:
        import yaml
        from pathlib import Path
        
        config_path = "config/autonomous_trading.yaml"
        
        # Load current configuration
        current_config = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                current_config = yaml.safe_load(f) or {}
        
        # Merge with updates (deep merge)
        def deep_merge(base: Dict, updates: Dict) -> Dict:
            """Recursively merge updates into base configuration."""
            result = base.copy()
            for key, value in updates.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result
        
        updated_config = deep_merge(current_config, request.config)
        
        # Validate configuration
        validation_errors = []
        
        # Validate autonomous settings
        if "autonomous" in updated_config:
            auto_config = updated_config["autonomous"]
            
            if "enabled" in auto_config and not isinstance(auto_config["enabled"], bool):
                validation_errors.append("autonomous.enabled must be a boolean")
            
            if "proposal_frequency" in auto_config:
                valid_frequencies = ["daily", "weekly", "monthly"]
                if auto_config["proposal_frequency"] not in valid_frequencies:
                    validation_errors.append(
                        f"autonomous.proposal_frequency must be one of: {', '.join(valid_frequencies)}"
                    )
            
            if "max_active_strategies" in auto_config:
                max_strat = auto_config["max_active_strategies"]
                if not isinstance(max_strat, int) or max_strat < 1:
                    validation_errors.append("autonomous.max_active_strategies must be >= 1")
            
            if "min_active_strategies" in auto_config:
                min_strat = auto_config["min_active_strategies"]
                if not isinstance(min_strat, int) or min_strat < 1:
                    validation_errors.append("autonomous.min_active_strategies must be >= 1")
            
            # Check min <= max
            if "min_active_strategies" in auto_config and "max_active_strategies" in auto_config:
                if auto_config["min_active_strategies"] > auto_config["max_active_strategies"]:
                    validation_errors.append(
                        "autonomous.min_active_strategies must be <= max_active_strategies"
                    )
        
        # Validate activation thresholds
        if "activation_thresholds" in updated_config:
            thresholds = updated_config["activation_thresholds"]
            
            if "min_sharpe" in thresholds:
                if not isinstance(thresholds["min_sharpe"], (int, float)) or thresholds["min_sharpe"] < 0:
                    validation_errors.append("activation_thresholds.min_sharpe must be >= 0")
            
            if "max_drawdown" in thresholds:
                dd = thresholds["max_drawdown"]
                if not isinstance(dd, (int, float)) or dd < 0 or dd > 1:
                    validation_errors.append("activation_thresholds.max_drawdown must be between 0 and 1")
            
            if "min_win_rate" in thresholds:
                wr = thresholds["min_win_rate"]
                if not isinstance(wr, (int, float)) or wr < 0 or wr > 1:
                    validation_errors.append("activation_thresholds.min_win_rate must be between 0 and 1")
            
            if "min_trades" in thresholds:
                if not isinstance(thresholds["min_trades"], int) or thresholds["min_trades"] < 1:
                    validation_errors.append("activation_thresholds.min_trades must be >= 1")
        
        # Validate retirement thresholds
        if "retirement_thresholds" in updated_config:
            thresholds = updated_config["retirement_thresholds"]
            
            if "max_sharpe" in thresholds:
                if not isinstance(thresholds["max_sharpe"], (int, float)) or thresholds["max_sharpe"] < 0:
                    validation_errors.append("retirement_thresholds.max_sharpe must be >= 0")
            
            if "max_drawdown" in thresholds:
                dd = thresholds["max_drawdown"]
                if not isinstance(dd, (int, float)) or dd < 0 or dd > 1:
                    validation_errors.append("retirement_thresholds.max_drawdown must be between 0 and 1")
            
            if "min_win_rate" in thresholds:
                wr = thresholds["min_win_rate"]
                if not isinstance(wr, (int, float)) or wr < 0 or wr > 1:
                    validation_errors.append("retirement_thresholds.min_win_rate must be between 0 and 1")
            
            if "min_trades_for_evaluation" in thresholds:
                if not isinstance(thresholds["min_trades_for_evaluation"], int) or thresholds["min_trades_for_evaluation"] < 1:
                    validation_errors.append("retirement_thresholds.min_trades_for_evaluation must be >= 1")
        
        # Validate backtest settings
        if "backtest" in updated_config:
            backtest = updated_config["backtest"]
            
            if "days" in backtest:
                if not isinstance(backtest["days"], int) or backtest["days"] < 30 or backtest["days"] > 3650:
                    validation_errors.append("backtest.days must be between 30 and 3650")
            
            if "warmup_days" in backtest:
                if not isinstance(backtest["warmup_days"], int) or backtest["warmup_days"] < 0:
                    validation_errors.append("backtest.warmup_days must be >= 0")
            
            if "min_trades" in backtest:
                if not isinstance(backtest["min_trades"], int) or backtest["min_trades"] < 1:
                    validation_errors.append("backtest.min_trades must be >= 1")
        
        # If validation errors, return them
        if validation_errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Configuration validation failed: {'; '.join(validation_errors)}"
            )
        
        # Save updated configuration
        with open(config_path, "w") as f:
            yaml.dump(updated_config, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Successfully updated autonomous configuration by {username}")
        
        # Broadcast configuration update event
        ws_manager = get_websocket_manager()
        await ws_manager.broadcast({
            "type": "autonomous:config_updated",
            "timestamp": datetime.now().isoformat(),
            "updated_by": username
        })
        
        return UpdateConfigResponse(
            success=True,
            message="Configuration updated successfully",
            config=updated_config
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update autonomous configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}"
        )


# ===== Strategy Management Endpoints =====

class ProposalResponse(BaseModel):
    """Single strategy proposal response model."""
    id: int
    strategy_id: str
    proposed_at: str
    market_regime: str
    backtest_sharpe: Optional[float] = None
    activated: bool
    strategy: Optional[Dict[str, Any]] = None
    evaluation_score: Optional[float] = None


class ProposalsListResponse(BaseModel):
    """Strategy proposals list response model."""
    proposals: List[ProposalResponse]
    total: int
    page: int
    page_size: int


class RetirementResponse(BaseModel):
    """Single strategy retirement response model."""
    id: int
    strategy_id: str
    strategy_name: Optional[str] = None
    retired_at: str
    reason: str
    final_metrics: Dict[str, Optional[float]]


class RetirementsListResponse(BaseModel):
    """Strategy retirements list response model."""
    retirements: List[RetirementResponse]
    total: int
    page: int
    page_size: int



# Task 9.7: New response models for categories and types
class CategoryInfo(BaseModel):
    """Category information."""
    category: str
    count: int
    description: Optional[str] = None


class CategoriesResponse(BaseModel):
    """Categories response."""
    categories: List[CategoryInfo]
    total_count: int


class TypeInfo(BaseModel):
    """Strategy type information."""
    type: str
    count: int
    description: Optional[str] = None


class TypesResponse(BaseModel):
    """Strategy types response."""
    types: List[TypeInfo]
    total_count: int


@router.get("/proposals", response_model=ProposalsListResponse)
async def get_strategy_proposals(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    market_regime: Optional[str] = Query(None, description="Filter by market regime"),
    activated: Optional[bool] = Query(None, description="Filter by activation status"),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get strategy proposals with pagination and filtering.

    Returns a paginated list of strategy proposals from the autonomous system.
    Each proposal includes the strategy details, backtest results, and activation status.

    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - market_regime: Filter by market regime (optional)
    - activated: Filter by activation status (optional)

    Returns:
        Paginated list of strategy proposals

    Validates: Requirements 2.6, 4.1
    """
    logger.info(f"Fetching strategy proposals (page={page}, page_size={page_size}, regime={market_regime}, activated={activated})")

    try:
        from src.models.orm import StrategyProposalORM

        # Build query
        query = db.query(StrategyProposalORM)

        # Apply filters
        if market_regime:
            query = query.filter(StrategyProposalORM.market_regime == market_regime)

        if activated is not None:
            query = query.filter(StrategyProposalORM.activated == (1 if activated else 0))

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        proposals_orm = query.order_by(StrategyProposalORM.proposed_at.desc()).offset(offset).limit(page_size).all()

        # Get strategy engine to fetch strategy details
        strategy_engine = _get_strategy_engine(TradingMode.DEMO)

        # Build response
        proposals = []
        for proposal_orm in proposals_orm:
            proposal_dict = proposal_orm.to_dict()

            # Try to fetch strategy details
            strategy_data = None
            try:
                strategy = strategy_engine.get_strategy(proposal_orm.strategy_id)
                if strategy:
                    strategy_data = {
                        "id": strategy.id,
                        "name": strategy.name,
                        "status": strategy.status.value if hasattr(strategy.status, 'value') else str(strategy.status),
                        "symbols": strategy.symbols,
                        "template_name": getattr(strategy, 'template_name', None),
                        "rules": {
                            "entry": strategy.entry_rules if hasattr(strategy, 'entry_rules') else [],
                            "exit": strategy.exit_rules if hasattr(strategy, 'exit_rules') else []
                        }
                    }
            except Exception as e:
                logger.warning(f"Could not fetch strategy {proposal_orm.strategy_id}: {e}")

            # Calculate evaluation score (simple heuristic based on Sharpe)
            evaluation_score = None
            if proposal_dict.get("backtest_sharpe"):
                evaluation_score = min(100.0, max(0.0, proposal_dict["backtest_sharpe"] * 50))

            proposals.append(ProposalResponse(
                id=proposal_dict["id"],
                strategy_id=proposal_dict["strategy_id"],
                proposed_at=proposal_dict["proposed_at"],
                market_regime=proposal_dict["market_regime"],
                backtest_sharpe=proposal_dict.get("backtest_sharpe"),
                activated=proposal_dict["activated"],
                strategy=strategy_data,
                evaluation_score=evaluation_score
            ))

        return ProposalsListResponse(
            proposals=proposals,
            total=total,
            page=page,
            page_size=page_size
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch strategy proposals: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch proposals: {str(e)}"
        )


@router.get("/retirements", response_model=RetirementsListResponse)
async def get_strategy_retirements(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    reason: Optional[str] = Query(None, description="Filter by retirement reason"),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get strategy retirements with pagination and filtering.

    Returns a paginated list of retired strategies from the autonomous system.
    Each retirement includes the strategy details, retirement reason, and final metrics.

    Query Parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - reason: Filter by retirement reason (optional)

    Returns:
        Paginated list of strategy retirements

    Validates: Requirements 2.7, 4.2
    """
    logger.info(f"Fetching strategy retirements (page={page}, page_size={page_size}, reason={reason})")

    try:
        from src.models.orm import StrategyRetirementORM

        # Build query
        query = db.query(StrategyRetirementORM)

        # Apply filters
        if reason:
            query = query.filter(StrategyRetirementORM.reason.like(f"%{reason}%"))

        # Get total count
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        retirements_orm = query.order_by(StrategyRetirementORM.retired_at.desc()).offset(offset).limit(page_size).all()

        # Get strategy engine to fetch strategy names
        strategy_engine = _get_strategy_engine(TradingMode.DEMO)

        # Build response
        retirements = []
        for retirement_orm in retirements_orm:
            retirement_dict = retirement_orm.to_dict()

            # Try to fetch strategy name
            strategy_name = None
            try:
                strategy = strategy_engine.get_strategy(retirement_orm.strategy_id)
                if strategy:
                    strategy_name = strategy.name
            except Exception as e:
                logger.warning(f"Could not fetch strategy {retirement_orm.strategy_id}: {e}")

            # Build final metrics
            final_metrics = {
                "sharpe": retirement_dict.get("final_sharpe"),
                "totalReturn": retirement_dict.get("final_return"),
                "maxDrawdown": None,  # Not stored in current schema
                "winRate": None  # Not stored in current schema
            }

            retirements.append(RetirementResponse(
                id=retirement_dict["id"],
                strategy_id=retirement_dict["strategy_id"],
                strategy_name=strategy_name,
                retired_at=retirement_dict["retired_at"],
                reason=retirement_dict["reason"],
                final_metrics=final_metrics
            ))

        return RetirementsListResponse(
            retirements=retirements,
            total=total,
            page=page,
            page_size=page_size
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch strategy retirements: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch retirements: {str(e)}"
        )




# Task 9.7: New endpoints for categories and types
@router.get("/categories", response_model=CategoriesResponse)
async def get_strategy_categories(
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get available strategy categories with counts.
    
    Returns:
        List of strategy categories with counts
        
    Validates: Requirement 9.7
    """
    logger.info(f"Getting strategy categories for user {username}")
    
    try:
        # Query all non-retired strategies
        strategies = session.query(StrategyORM).filter(
            StrategyORM.status != StrategyStatus.RETIRED.value
        ).all()
        
        # Count strategies by category (using same resolution logic as get_strategies)
        ALPHA_EDGE_TEMPLATES = {"earnings_momentum", "sector_rotation", "quality_mean_reversion",
                                "Alpha Edge Earnings Momentum", "Alpha Edge Sector Rotation", "Alpha Edge Quality Mean Reversion"}
        category_counts = {}
        for strategy in strategies:
            strategy_dict = strategy.to_dict()
            metadata = strategy_dict.get("metadata", {})
            template_name = metadata.get("template_name", "")
            
            category = metadata.get("strategy_category")
            if not category:
                if template_name and (template_name in ALPHA_EDGE_TEMPLATES or 
                                      template_name.lower().replace(" ", "_") in {"earnings_momentum", "sector_rotation", "quality_mean_reversion"}):
                    category = "alpha_edge"
                elif template_name:
                    category = "template_based"
                else:
                    category = "manual"
            
            if category not in category_counts:
                category_counts[category] = 0
            category_counts[category] += 1
        
        # Build response
        categories = []
        category_descriptions = {
            "alpha_edge": "Advanced strategies using fundamental data and ML filtering",
            "template_based": "Standard technical analysis strategies from templates",
            "manual": "User-created strategies"
        }
        
        for category, count in category_counts.items():
            categories.append(CategoryInfo(
                category=category,
                count=count,
                description=category_descriptions.get(category)
            ))
        
        return CategoriesResponse(
            categories=categories,
            total_count=len(categories)
        )
        
    except Exception as e:
        logger.error(f"Failed to get strategy categories: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get categories: {str(e)}"
        )


@router.get("/types", response_model=TypesResponse)
async def get_strategy_types(
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get available strategy types with counts.
    
    Returns:
        List of strategy types with counts
        
    Validates: Requirement 9.7
    """
    logger.info(f"Getting strategy types for user {username}")
    
    try:
        # Query all non-retired strategies
        strategies = session.query(StrategyORM).filter(
            StrategyORM.status != StrategyStatus.RETIRED.value
        ).all()
        
        # Count strategies by type
        type_counts = {}
        for strategy in strategies:
            strategy_dict = strategy.to_dict()
            metadata = strategy_dict.get("metadata", {})
            strategy_type = metadata.get("strategy_type")
            
            if strategy_type:
                if strategy_type not in type_counts:
                    type_counts[strategy_type] = 0
                type_counts[strategy_type] += 1
        
        # Build response
        types = []
        type_descriptions = {
            "mean_reversion": "Strategies that profit from price returning to average",
            "trend_following": "Strategies that follow established price trends",
            "momentum": "Strategies that capitalize on price momentum",
            "breakout": "Strategies that trade price breakouts from ranges",
            "volatility": "Strategies that trade based on volatility patterns"
        }
        
        for strategy_type, count in type_counts.items():
            types.append(TypeInfo(
                type=strategy_type,
                count=count,
                description=type_descriptions.get(strategy_type)
            ))
        
        return TypesResponse(
            types=types,
            total_count=len(types)
        )
        
    except Exception as e:
        logger.error(f"Failed to get strategy types: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get types: {str(e)}"
        )


class ResetStrategiesResponse(BaseModel):
    """Response for reset strategies endpoint."""
    success: bool
    message: str
    deleted_count: int


@router.post("/reset", response_model=ResetStrategiesResponse)
async def reset_all_strategies(
    username: str = Depends(get_current_user)
):
    """
    Delete all strategies from the database.
    
    WARNING: This is a destructive operation that cannot be undone.
    
    Args:
        username: Current authenticated user
        
    Returns:
        ResetStrategiesResponse with deletion count
    """
    logger.warning(f"User {username} initiated strategy reset - deleting all strategies")
    
    try:
        db = get_database()
        session = db.get_session()
        
        try:
            # Count strategies before deletion
            total_count = session.query(StrategyORM).count()
            
            # Delete all strategies
            session.query(StrategyORM).delete()
            session.commit()
            
            logger.info(f"Successfully deleted {total_count} strategies")
            
            return ResetStrategiesResponse(
                success=True,
                message=f"Successfully deleted {total_count} strategies",
                deleted_count=total_count
            )
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Failed to reset strategies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset strategies: {str(e)}"
        )


# ============================================================================
# Walk-Forward Analytics Endpoint (Task 9.7)
# ============================================================================

class WalkForwardCycleStats(BaseModel):
    """Per-cycle walk-forward statistics."""
    cycle_id: str
    started_at: Optional[str] = None
    proposals_generated: int = 0
    backtests_run: int = 0
    pass_rate_pct: float = 0.0
    avg_sharpe_passed: Optional[float] = None
    avg_sharpe_failed: Optional[float] = None


class PassRatePoint(BaseModel):
    """Historical pass rate data point."""
    date: str
    pass_rate: float


class WalkForwardAnalyticsResponse(BaseModel):
    """Walk-forward analytics response."""
    cycles: List[WalkForwardCycleStats]
    pass_rate_history: List[PassRatePoint]


@router.get("/autonomous/walk-forward-analytics", response_model=WalkForwardAnalyticsResponse)
async def get_walk_forward_analytics(
    mode: TradingMode,
    period: str = Query("3M", description="Time period filter: 1M, 3M, 6M, 1Y, ALL"),
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    """
    Get walk-forward analytics with per-cycle stats and historical pass rate.

    Returns per-cycle walk-forward statistics (proposals generated, backtests
    run, pass rate, avg Sharpe passed/failed) and a historical pass rate time
    series.

    Validates: Requirements 18.3, 18.4
    """
    logger.info(f"Fetching walk-forward analytics for {mode.value} mode, period={period}, user {username}")

    try:
        from src.models.orm import AutonomousCycleRunORM
        from datetime import timedelta

        # Determine date cutoff from period
        now = datetime.utcnow()
        period_map = {
            "1M": timedelta(days=30),
            "3M": timedelta(days=90),
            "6M": timedelta(days=180),
            "1Y": timedelta(days=365),
        }
        cutoff = now - period_map.get(period, timedelta(days=90)) if period != "ALL" else None

        query = session.query(AutonomousCycleRunORM).order_by(
            AutonomousCycleRunORM.started_at.desc()
        )
        if cutoff:
            query = query.filter(AutonomousCycleRunORM.started_at >= cutoff)

        runs = query.all()

        cycles: List[WalkForwardCycleStats] = []
        pass_rate_history: List[PassRatePoint] = []

        for run in runs:
            backtests_run = (run.backtested or 0)
            passed = (run.backtest_passed or 0)
            failed = (run.backtest_failed or 0)
            pass_rate = (passed / backtests_run * 100) if backtests_run > 0 else 0.0

            # Avg Sharpe for passed/failed — we only have the overall avg_sharpe
            # from the cycle. Use it for passed; failed gets None.
            avg_sharpe_passed = None
            avg_sharpe_failed = None
            if run.avg_sharpe is not None and not (math.isnan(run.avg_sharpe) or math.isinf(run.avg_sharpe)):
                if passed > 0:
                    avg_sharpe_passed = round(run.avg_sharpe, 2)

            cycles.append(WalkForwardCycleStats(
                cycle_id=run.cycle_id,
                started_at=run.started_at.isoformat() if run.started_at else None,
                proposals_generated=run.proposals_generated or 0,
                backtests_run=backtests_run,
                pass_rate_pct=round(pass_rate, 1),
                avg_sharpe_passed=avg_sharpe_passed,
                avg_sharpe_failed=avg_sharpe_failed,
            ))

            if run.started_at:
                pass_rate_history.append(PassRatePoint(
                    date=run.started_at.strftime("%Y-%m-%d"),
                    pass_rate=round(pass_rate, 1),
                ))

        # Reverse pass_rate_history to chronological order
        pass_rate_history.reverse()

        return WalkForwardAnalyticsResponse(
            cycles=cycles,
            pass_rate_history=pass_rate_history,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch walk-forward analytics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch walk-forward analytics: {str(e)}",
        )

