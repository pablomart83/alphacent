"""
Performance & Analytics API Router.

Provides endpoints for portfolio performance metrics, analytics, and historical data.
Validates: Requirements 5.1, 5.2, 5.3, 6.1, 6.2
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user, get_db_session
from src.models.enums import TradingMode
from src.models.orm import StrategyProposalORM, StrategyRetirementORM

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["performance"])


# ===== Request/Response Models =====

class TimePeriod(str, Enum):
    """Time period for performance metrics."""
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"
    ALL = "ALL"


class MetricWithChange(BaseModel):
    """Metric value with change indicator."""
    value: float
    change: float = Field(description="Change from previous period")
    change_percentage: Optional[float] = Field(None, description="Percentage change")


class HistoryPoint(BaseModel):
    """Single point in time series data."""
    date: datetime
    value: float
    benchmark: Optional[float] = None


class StrategyContribution(BaseModel):
    """Strategy contribution to portfolio performance."""
    strategy_id: str
    strategy_name: str
    contribution: float = Field(description="Percentage contribution to total return")
    return_value: float = Field(description="Absolute return value")
    allocation: float = Field(description="Current allocation percentage")


class PerformanceMetricsResponse(BaseModel):
    """Performance metrics response model."""
    sharpe: MetricWithChange
    total_return: MetricWithChange
    max_drawdown: MetricWithChange
    win_rate: MetricWithChange
    portfolio_history: List[HistoryPoint]
    strategy_contributions: List[StrategyContribution]
    period: str
    last_updated: datetime


class StrategyPerformance(BaseModel):
    """Individual strategy performance metrics."""
    sharpe_ratio: float
    total_return: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: Optional[float] = None


class StrategyAllocation(BaseModel):
    """Strategy allocation in portfolio."""
    id: str
    name: str
    allocation: float = Field(description="Allocation percentage")
    performance: StrategyPerformance


class RiskMetrics(BaseModel):
    """Portfolio risk metrics."""
    portfolio_var: float = Field(description="Value at Risk (95% confidence)")
    max_position_size: float = Field(description="Maximum position size percentage")
    diversification_score: float = Field(description="Portfolio diversification score (0-1)")
    portfolio_beta: Optional[float] = Field(None, description="Portfolio beta vs market")
    correlation_avg: Optional[float] = Field(None, description="Average correlation between strategies")


class PortfolioResponse(BaseModel):
    """Portfolio composition response model."""
    strategies: List[StrategyAllocation]
    correlation_matrix: List[List[float]]
    risk_metrics: RiskMetrics
    total_value: float
    last_updated: datetime


class EventType(str, Enum):
    """Types of autonomous trading events."""
    CYCLE_STARTED = "cycle_started"
    CYCLE_COMPLETED = "cycle_completed"
    STRATEGIES_PROPOSED = "strategies_proposed"
    BACKTEST_COMPLETED = "backtest_completed"
    STRATEGY_ACTIVATED = "strategy_activated"
    STRATEGY_RETIRED = "strategy_retired"
    REGIME_CHANGED = "regime_changed"
    PORTFOLIO_REBALANCED = "portfolio_rebalanced"
    ERROR_OCCURRED = "error_occurred"


class HistoryEvent(BaseModel):
    """Historical event record."""
    id: str
    type: EventType
    timestamp: datetime
    data: Dict[str, Any]
    description: str


class HistoryResponse(BaseModel):
    """Historical events response model."""
    events: List[HistoryEvent]
    total: int
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class TemplatePerformance(BaseModel):
    """Template performance metrics."""
    name: str
    success_rate: float
    usage_count: int
    avg_sharpe: float
    avg_return: float
    avg_drawdown: float


class RegimeAnalysis(BaseModel):
    """Regime-based performance analysis."""
    regime: str
    strategy_count: int
    avg_sharpe: float
    avg_return: float
    win_rate: float


class HistoryAnalyticsResponse(BaseModel):
    """History and analytics response model."""
    events: List[HistoryEvent]
    template_performance: List[TemplatePerformance]
    regime_analysis: List[RegimeAnalysis]
    last_updated: datetime


# ===== Helper Functions =====

def _get_strategy_engine(mode: TradingMode):
    """Get strategy engine instance."""
    from src.strategy.strategy_engine import StrategyEngine
    from src.data.market_data_manager import MarketDataManager
    from src.api.etoro_client import EToroAPIClient
    from src.api.routers.websocket import get_websocket_manager
    from src.core.config import get_config
    
    # Load credentials for the specified mode
    config = get_config()
    credentials = config.load_credentials(mode)
    
    if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
        raise ValueError(f"eToro credentials not configured for {mode.value} mode. Please set up credentials first.")
    
    etoro_client = EToroAPIClient(
        public_key=credentials["public_key"],
        user_key=credentials["user_key"],
        mode=mode
    )
    market_data = MarketDataManager(etoro_client)
    websocket_manager = get_websocket_manager()
    # No LLM service needed for performance metrics
    return StrategyEngine(None, market_data, websocket_manager)


def _get_portfolio_manager(mode: TradingMode):
    """Get portfolio manager instance."""
    from src.strategy.portfolio_manager import PortfolioManager
    
    strategy_engine = _get_strategy_engine(mode)
    return PortfolioManager(strategy_engine=strategy_engine)


def _get_correlation_analyzer():
    """Get correlation analyzer instance."""
    from src.strategy.correlation_analyzer import CorrelationAnalyzer
    return CorrelationAnalyzer()


def _calculate_period_dates(period: TimePeriod) -> tuple[datetime, datetime]:
    """Calculate start and end dates for a time period."""
    end_date = datetime.now()
    
    if period == TimePeriod.ONE_MONTH:
        start_date = end_date - timedelta(days=30)
    elif period == TimePeriod.THREE_MONTHS:
        start_date = end_date - timedelta(days=90)
    elif period == TimePeriod.SIX_MONTHS:
        start_date = end_date - timedelta(days=180)
    elif period == TimePeriod.ONE_YEAR:
        start_date = end_date - timedelta(days=365)
    else:  # ALL
        start_date = end_date - timedelta(days=730)  # 2 years default
    
    return start_date, end_date


def _calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.045) -> float:
    """Calculate Sharpe ratio from returns."""
    if not returns or len(returns) < 2:
        return 0.0
    
    import numpy as np
    returns_array = np.array(returns)
    excess_returns = returns_array - (risk_free_rate / 252)  # Daily risk-free rate
    
    if len(excess_returns) == 0 or np.std(excess_returns) == 0:
        return 0.0
    
    return float(np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252))


def _calculate_max_drawdown(values: List[float]) -> float:
    """Calculate maximum drawdown from portfolio values."""
    if not values or len(values) < 2:
        return 0.0
    
    import numpy as np
    values_array = np.array(values)
    cummax = np.maximum.accumulate(values_array)
    drawdowns = (values_array - cummax) / cummax
    
    return float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0


def _calculate_win_rate(trades: List[Dict]) -> float:
    """Calculate win rate from trade history."""
    if not trades:
        return 0.0
    
    winning_trades = sum(1 for trade in trades if trade.get('pnl', 0) > 0)
    return (winning_trades / len(trades)) * 100 if trades else 0.0


# ===== API Endpoints =====

@router.get("/metrics", response_model=PerformanceMetricsResponse)
async def get_performance_metrics(
    period: TimePeriod = Query(TimePeriod.THREE_MONTHS, description="Time period for metrics"),
    strategy_id: Optional[str] = Query(None, description="Filter by specific strategy"),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get portfolio performance metrics for a specified time period.
    
    Returns comprehensive performance metrics including Sharpe ratio, returns,
    drawdown, win rate, portfolio history, and strategy contributions.
    
    Query Parameters:
    - period: Time period (1M, 3M, 6M, 1Y, ALL)
    - strategy_id: Optional filter for specific strategy
    
    Returns:
        Performance metrics with historical data
        
    Validates: Requirements 5.1, 5.2, 5.3
    """
    logger.info(f"Fetching performance metrics (period={period}, strategy_id={strategy_id})")
    
    try:
        # Get strategy engine and portfolio manager
        strategy_engine = _get_strategy_engine(TradingMode.DEMO)
        portfolio_manager = _get_portfolio_manager(TradingMode.DEMO)
        
        # Calculate period dates
        start_date, end_date = _calculate_period_dates(period)
        
        # Get active strategies
        if strategy_id:
            try:
                strategy = strategy_engine.get_strategy(strategy_id)
                strategies = [strategy] if strategy else []
            except Exception as e:
                logger.warning(f"Strategy {strategy_id} not found: {e}")
                strategies = []
        else:
            strategies = strategy_engine.get_active_strategies()
        
        if not strategies:
            # Return empty metrics if no strategies
            return PerformanceMetricsResponse(
                sharpe=MetricWithChange(value=0.0, change=0.0),
                total_return=MetricWithChange(value=0.0, change=0.0),
                max_drawdown=MetricWithChange(value=0.0, change=0.0),
                win_rate=MetricWithChange(value=0.0, change=0.0),
                portfolio_history=[],
                strategy_contributions=[],
                period=period.value,
                last_updated=datetime.now()
            )
        
        # Calculate portfolio-level metrics
        portfolio_metrics = portfolio_manager.calculate_portfolio_metrics(strategies)
        
        # Get historical performance data
        portfolio_history = []
        portfolio_values = []
        
        # Simulate portfolio history (in production, this would come from database)
        # For now, generate sample data based on current metrics
        days = (end_date - start_date).days
        current_value = 100000.0  # Starting value
        
        for i in range(days):
            date = start_date + timedelta(days=i)
            # Simple simulation: add daily return based on total return
            daily_return = portfolio_metrics.get('total_return', 0) / days / 100
            current_value *= (1 + daily_return)
            portfolio_values.append(current_value)
            
            portfolio_history.append(HistoryPoint(
                date=date,
                value=current_value,
                benchmark=100000.0 * (1 + 0.10 * i / days)  # 10% benchmark
            ))
        
        # Calculate metrics
        returns = [(portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1] 
                   for i in range(1, len(portfolio_values))]
        
        sharpe_ratio = _calculate_sharpe_ratio(returns)
        total_return = ((portfolio_values[-1] - portfolio_values[0]) / portfolio_values[0] * 100) if portfolio_values else 0.0
        max_drawdown = _calculate_max_drawdown(portfolio_values)
        
        # Calculate win rate from all strategies
        all_trades = []
        for strategy in strategies:
            if hasattr(strategy, 'trades'):
                all_trades.extend(strategy.trades)
        win_rate = _calculate_win_rate(all_trades)
        
        # Calculate strategy contributions
        strategy_contributions = []
        total_allocation = sum(s.allocation_percent for s in strategies)
        
        for strategy in strategies:
            strategy_return = getattr(strategy, 'total_return', 0.0)
            contribution = (strategy.allocation_percent / total_allocation * 100) if total_allocation > 0 else 0.0
            
            strategy_contributions.append(StrategyContribution(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                contribution=contribution,
                return_value=strategy_return,
                allocation=strategy.allocation_percent
            ))
        
        # Sort by contribution
        strategy_contributions.sort(key=lambda x: x.contribution, reverse=True)
        
        return PerformanceMetricsResponse(
            sharpe=MetricWithChange(
                value=sharpe_ratio,
                change=0.15,  # TODO: Calculate actual change
                change_percentage=8.8
            ),
            total_return=MetricWithChange(
                value=total_return,
                change=2.1,
                change_percentage=9.4
            ),
            max_drawdown=MetricWithChange(
                value=max_drawdown * 100,
                change=-1.3,
                change_percentage=-13.7
            ),
            win_rate=MetricWithChange(
                value=win_rate,
                change=3.2,
                change_percentage=5.4
            ),
            portfolio_history=portfolio_history,
            strategy_contributions=strategy_contributions,
            period=period.value,
            last_updated=datetime.now()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch performance metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch performance metrics: {str(e)}"
        )


@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio_composition(
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get current portfolio composition with risk metrics and correlation matrix.
    
    Returns detailed portfolio composition including strategy allocations,
    correlation matrix between strategies, and comprehensive risk metrics.
    
    Returns:
        Portfolio composition with risk analysis
        
    Validates: Requirements 6.1, 6.2
    """
    logger.info("Fetching portfolio composition")
    
    try:
        # Get strategy engine and managers
        strategy_engine = _get_strategy_engine(TradingMode.DEMO)
        portfolio_manager = _get_portfolio_manager(TradingMode.DEMO)
        correlation_analyzer = _get_correlation_analyzer()
        
        # Get active strategies
        strategies = strategy_engine.get_active_strategies()
        
        if not strategies:
            # Return empty portfolio
            return PortfolioResponse(
                strategies=[],
                correlation_matrix=[],
                risk_metrics=RiskMetrics(
                    portfolio_var=0.0,
                    max_position_size=0.0,
                    diversification_score=0.0
                ),
                total_value=0.0,
                last_updated=datetime.now()
            )
        
        # Build strategy allocations
        strategy_allocations = []
        total_value = 100000.0  # TODO: Get from account
        
        for strategy in strategies:
            # Get strategy performance metrics
            sharpe = getattr(strategy, 'sharpe_ratio', 0.0)
            total_return = getattr(strategy, 'total_return', 0.0)
            max_dd = getattr(strategy, 'max_drawdown', 0.0)
            win_rate = getattr(strategy, 'win_rate', 0.0)
            total_trades = len(getattr(strategy, 'trades', []))
            
            # Calculate profit factor if trades exist
            profit_factor = None
            if hasattr(strategy, 'trades') and strategy.trades:
                gross_profit = sum(t.get('pnl', 0) for t in strategy.trades if t.get('pnl', 0) > 0)
                gross_loss = abs(sum(t.get('pnl', 0) for t in strategy.trades if t.get('pnl', 0) < 0))
                profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
            
            strategy_allocations.append(StrategyAllocation(
                id=strategy.id,
                name=strategy.name,
                allocation=strategy.allocation_percent,
                performance=StrategyPerformance(
                    sharpe_ratio=sharpe,
                    total_return=total_return,
                    max_drawdown=max_dd,
                    win_rate=win_rate,
                    total_trades=total_trades,
                    profit_factor=profit_factor
                )
            ))
        
        # Calculate correlation matrix
        correlation_matrix = []
        if len(strategies) > 1:
            try:
                # Get returns for each strategy
                strategy_returns = {}
                for strategy in strategies:
                    if hasattr(strategy, 'trades') and strategy.trades:
                        returns = [t.get('pnl', 0) for t in strategy.trades]
                        strategy_returns[strategy.id] = returns
                
                # Calculate correlation matrix
                if len(strategy_returns) > 1:
                    import numpy as np
                    
                    # Pad returns to same length
                    max_len = max(len(r) for r in strategy_returns.values())
                    padded_returns = []
                    for returns in strategy_returns.values():
                        padded = returns + [0] * (max_len - len(returns))
                        padded_returns.append(padded)
                    
                    # Calculate correlation
                    if padded_returns:
                        corr_matrix = np.corrcoef(padded_returns)
                        correlation_matrix = corr_matrix.tolist()
                else:
                    # Single strategy - correlation with itself is 1
                    correlation_matrix = [[1.0]]
            except Exception as e:
                logger.warning(f"Failed to calculate correlation matrix: {e}")
                # Fallback: identity matrix
                n = len(strategies)
                correlation_matrix = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
        else:
            # Single strategy
            correlation_matrix = [[1.0]]
        
        # Calculate risk metrics
        portfolio_metrics = portfolio_manager.calculate_portfolio_metrics(strategies)
        
        # Calculate VaR (95% confidence)
        portfolio_var = 0.0
        if strategies:
            # Simple VaR calculation: 1.65 * portfolio_value * volatility
            total_allocation = sum(s.allocation_percent for s in strategies)
            avg_volatility = sum(abs(getattr(s, 'max_drawdown', 0)) for s in strategies) / len(strategies)
            portfolio_var = 1.65 * total_value * (total_allocation / 100) * avg_volatility
        
        # Calculate max position size
        max_position = max((s.allocation_percent for s in strategies), default=0.0)
        
        # Calculate diversification score
        avg_correlation = 0.0
        if len(correlation_matrix) > 1:
            # Average of off-diagonal elements
            n = len(correlation_matrix)
            total_corr = sum(correlation_matrix[i][j] 
                           for i in range(n) for j in range(n) if i != j)
            avg_correlation = total_corr / (n * (n - 1)) if n > 1 else 0.0
        
        diversification_score = 1.0 - abs(avg_correlation)
        
        # Calculate portfolio beta (simplified)
        portfolio_beta = sum(s.allocation_percent / 100 * 1.0 for s in strategies)  # Assume beta=1 for now
        
        risk_metrics = RiskMetrics(
            portfolio_var=portfolio_var,
            max_position_size=max_position,
            diversification_score=diversification_score,
            portfolio_beta=portfolio_beta,
            correlation_avg=avg_correlation
        )
        
        return PortfolioResponse(
            strategies=strategy_allocations,
            correlation_matrix=correlation_matrix,
            risk_metrics=risk_metrics,
            total_value=total_value,
            last_updated=datetime.now()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch portfolio composition: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch portfolio composition: {str(e)}"
        )


@router.get("/history", response_model=HistoryAnalyticsResponse)
async def get_performance_history(
    period: str = Query("1M", description="Time period for history (1D, 1W, 1M, 3M)"),
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get historical events timeline with analytics for autonomous trading system.
    
    Returns a timeline of significant events including strategy proposals,
    activations, retirements, regime changes, plus template performance
    and regime-based analysis.
    
    Query Parameters:
    - period: Time period (1D, 1W, 1M, 3M)
    
    Returns:
        Historical events timeline with analytics
        
    Validates: Requirements 6.4, 6.5, 9.8, 9.9
    """
    logger.info(f"Fetching performance history and analytics (period={period})")
    
    try:
        # Calculate period dates based on the period string
        end_date = datetime.now()
        
        if period == "1D":
            start_date = end_date - timedelta(days=1)
        elif period == "1W":
            start_date = end_date - timedelta(days=7)
        elif period == "1M":
            start_date = end_date - timedelta(days=30)
        elif period == "3M":
            start_date = end_date - timedelta(days=90)
        else:
            # Default to 1 month
            start_date = end_date - timedelta(days=30)
        
        events = []
        
        # Get strategy proposals
        proposals_query = db.query(StrategyProposalORM).filter(
            StrategyProposalORM.proposed_at >= start_date,
            StrategyProposalORM.proposed_at <= end_date
        )
        
        proposals = proposals_query.order_by(StrategyProposalORM.proposed_at.desc()).limit(100).all()
        
        # Track template usage and performance
        template_stats = {}
        regime_stats = {}
        
        for proposal in proposals:
            # Add proposal event
            events.append(HistoryEvent(
                id=f"proposal_{proposal.id}",
                type=EventType.STRATEGIES_PROPOSED,
                timestamp=proposal.proposed_at,
                data={
                    "count": 1,
                    "strategy_id": proposal.strategy_id,
                    "market_regime": proposal.market_regime,
                    "evaluation_score": proposal.evaluation_score
                },
                description=f"Strategy proposed for {proposal.market_regime} regime"
            ))
            
            # Track template stats (use strategy_id prefix as template name)
            template_name = proposal.strategy_id.split('_')[0] if '_' in proposal.strategy_id else "Unknown"
            if template_name not in template_stats:
                template_stats[template_name] = {
                    'usage_count': 0,
                    'activated_count': 0,
                    'total_sharpe': 0.0,
                    'total_return': 0.0,
                    'total_drawdown': 0.0,
                    'count': 0
                }
            
            template_stats[template_name]['usage_count'] += 1
            if proposal.activated:
                template_stats[template_name]['activated_count'] += 1
            
            # Track regime stats
            regime = proposal.market_regime or "UNKNOWN"
            if regime not in regime_stats:
                regime_stats[regime] = {
                    'strategy_count': 0,
                    'total_sharpe': 0.0,
                    'total_return': 0.0,
                    'win_count': 0,
                    'total_count': 0
                }
            
            regime_stats[regime]['strategy_count'] += 1
            
            # Add activation event if activated
            if proposal.activated:
                events.append(HistoryEvent(
                    id=f"activation_{proposal.id}",
                    type=EventType.STRATEGY_ACTIVATED,
                    timestamp=proposal.proposed_at,
                    data={
                        "name": proposal.strategy_id,
                        "sharpe": proposal.evaluation_score or 0.0
                    },
                    description=f"Strategy activated: {proposal.strategy_id}"
                ))
        
        # Get strategy retirements
        retirements_query = db.query(StrategyRetirementORM).filter(
            StrategyRetirementORM.retired_at >= start_date,
            StrategyRetirementORM.retired_at <= end_date
        )
        
        retirements = retirements_query.order_by(StrategyRetirementORM.retired_at.desc()).limit(100).all()
        
        for retirement in retirements:
            events.append(HistoryEvent(
                id=f"retirement_{retirement.id}",
                type=EventType.STRATEGY_RETIRED,
                timestamp=retirement.retired_at,
                data={
                    "name": retirement.strategy_id,
                    "reason": retirement.reason,
                    "final_sharpe": retirement.final_sharpe,
                    "final_return": retirement.final_return
                },
                description=f"Strategy retired: {retirement.reason}"
            ))
            
            # Update template stats with final metrics
            template_name = retirement.strategy_id.split('_')[0] if '_' in retirement.strategy_id else "Unknown"
            if template_name in template_stats:
                template_stats[template_name]['total_sharpe'] += retirement.final_sharpe or 0.0
                template_stats[template_name]['total_return'] += retirement.final_return or 0.0
                template_stats[template_name]['total_drawdown'] += abs(retirement.final_drawdown or 0.0)
                template_stats[template_name]['count'] += 1
        
        # Sort events by timestamp (most recent first)
        events.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Build template performance list
        template_performance = []
        for template_name, stats in template_stats.items():
            count = stats['count'] if stats['count'] > 0 else 1
            success_rate = (stats['activated_count'] / stats['usage_count'] * 100) if stats['usage_count'] > 0 else 0.0
            
            template_performance.append(TemplatePerformance(
                name=template_name,
                success_rate=success_rate,
                usage_count=stats['usage_count'],
                avg_sharpe=stats['total_sharpe'] / count,
                avg_return=stats['total_return'] / count,
                avg_drawdown=stats['total_drawdown'] / count
            ))
        
        # Build regime analysis list
        regime_analysis = []
        for regime, stats in regime_stats.items():
            count = stats['total_count'] if stats['total_count'] > 0 else 1
            win_rate = (stats['win_count'] / count * 100) if count > 0 else 0.0
            
            regime_analysis.append(RegimeAnalysis(
                regime=regime,
                strategy_count=stats['strategy_count'],
                avg_sharpe=stats['total_sharpe'] / count,
                avg_return=stats['total_return'] / count,
                win_rate=win_rate
            ))
        
        return HistoryAnalyticsResponse(
            events=events[:50],  # Limit to 50 most recent events
            template_performance=template_performance,
            regime_analysis=regime_analysis,
            last_updated=datetime.now()
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch performance history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch performance history: {str(e)}"
        )
