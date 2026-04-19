"""
Risk management endpoints for AlphaCent Trading Platform.

Provides endpoints for risk metrics, limits, and monitoring.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import numpy as np

from src.models.enums import TradingMode, PositionSide
from src.api.dependencies import get_current_user, get_db_session, get_configuration
from src.models.orm import PositionORM, OrderORM, StrategyORM
from src.core.config import Configuration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"])


def _get_position_value(pos: PositionORM) -> float:
    """Get the actual dollar value of a position on eToro.
    
    On eToro, quantity = dollar amount invested (not shares).
    invested_amount is the most accurate field when available.
    NEVER use quantity * current_price — that's dollars × price = nonsense.
    """
    if pos.invested_amount and pos.invested_amount > 0:
        return pos.invested_amount
    return abs(pos.quantity)


class RiskMetricsResponse(BaseModel):
    """Risk metrics response model."""
    portfolio_var: float = Field(description="Portfolio Value at Risk (95% confidence)")
    current_drawdown: float = Field(description="Current drawdown percentage")
    max_drawdown: float = Field(description="Maximum drawdown percentage")
    leverage: float = Field(description="Current leverage ratio")
    margin_utilization: float = Field(description="Margin utilization percentage")
    portfolio_beta: float = Field(description="Portfolio beta")
    max_position_size: float = Field(description="Maximum position size percentage")
    total_exposure: float = Field(description="Total portfolio exposure")
    risk_score: str = Field(description="Overall risk level: safe, warning, danger")
    risk_reasons: List[str] = Field(default_factory=list, description="Reasons for the current risk level")
    active_positions_count: int
    risk_breakdown: Dict[str, float] = Field(description="Risk by strategy")


class PositionRiskResponse(BaseModel):
    """Position risk details."""
    position_id: str
    symbol: str
    strategy_id: str
    risk_amount: float
    risk_percent: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    risk_level: str  # high, medium, low


class RiskHistoryPoint(BaseModel):
    """Risk history data point."""
    timestamp: str
    var: float
    drawdown: float
    leverage: float
    beta: float


class RiskHistoryResponse(BaseModel):
    """Risk history response model."""
    history: List[RiskHistoryPoint]
    period: str


class RiskLimitsResponse(BaseModel):
    """Risk limits response model."""
    max_position_size: float
    max_portfolio_exposure: float
    max_daily_loss: float
    max_drawdown: float
    max_leverage: float
    risk_per_trade: float


class UpdateRiskLimitsRequest(BaseModel):
    """Update risk limits request model."""
    max_position_size: Optional[float] = Field(None, ge=0.0, le=100.0)
    max_portfolio_exposure: Optional[float] = Field(None, ge=0.0, le=100.0)
    max_daily_loss: Optional[float] = Field(None, ge=0.0, le=100.0)
    max_drawdown: Optional[float] = Field(None, ge=0.0, le=100.0)
    max_leverage: Optional[float] = Field(None, ge=1.0, le=10.0)
    risk_per_trade: Optional[float] = Field(None, ge=0.0, le=10.0)


class RiskAlertResponse(BaseModel):
    """Risk alert response model."""
    id: str
    severity: str  # info, warning, danger
    metric: str
    current_value: float
    threshold: float
    message: str
    timestamp: str


def calculate_portfolio_var(positions: List[PositionORM], confidence: float = 0.95) -> float:
    """
    Calculate portfolio Value at Risk using position-level risk.
    
    Uses each position's actual P&L volatility relative to invested capital.
    For positions without enough history, falls back to asset-class-specific
    volatility assumptions calibrated to real market data.
    """
    if not positions:
        return 0.0
    
    z_score = 1.645 if confidence == 0.95 else 2.326
    
    # Asset-class daily volatility assumptions (annualized vol / sqrt(252))
    # Calibrated to long-run averages: stocks ~16%, crypto ~60%, forex ~8%, commodities ~20%
    from src.risk.risk_manager import SYMBOL_SECTOR_MAP
    ASSET_VOL = {
        'Crypto': 0.038,      # ~60% annualized
        'Forex': 0.005,       # ~8% annualized
        'Commodities': 0.013, # ~20% annualized
        'Indices': 0.010,     # ~16% annualized
        'default': 0.010,     # ~16% annualized (stocks)
    }
    
    total_var_sq = 0.0
    for pos in positions:
        pos_value = _get_position_value(pos)
        if pos_value <= 0:
            continue
        
        # Determine asset class for volatility assumption
        sector = SYMBOL_SECTOR_MAP.get(pos.symbol.upper(), 'Unknown')
        if sector == 'Crypto':
            daily_vol = ASSET_VOL['Crypto']
        elif sector == 'Forex':
            daily_vol = ASSET_VOL['Forex']
        elif sector in ('Commodities', 'Commodities ETF'):
            daily_vol = ASSET_VOL['Commodities']
        elif sector == 'Indices':
            daily_vol = ASSET_VOL['Indices']
        else:
            daily_vol = ASSET_VOL['default']
        
        # Position VaR (assuming independence for simplification)
        pos_var = pos_value * daily_vol * z_score
        total_var_sq += pos_var ** 2
    
    # Portfolio VaR assuming partial correlation (~0.3 average)
    # sqrt(sum of squared VaRs) gives uncorrelated VaR
    # Multiply by correlation factor to account for typical cross-asset correlation
    uncorrelated_var = np.sqrt(total_var_sq)
    correlation_factor = 1.15  # Empirical: portfolios are ~15% riskier than uncorrelated
    return round(uncorrelated_var * correlation_factor, 2)


def calculate_drawdown(positions: List[PositionORM], account_equity: float = 0.0) -> tuple[float, float]:
    """
    Calculate current drawdown from unrealized P&L relative to equity.
    
    Args:
        positions: Open positions
        account_equity: Current account equity (balance + unrealized P&L)
    """
    if not positions:
        return 0.0, 0.0
    
    total_unrealized = sum(p.unrealized_pnl or 0 for p in positions)
    total_invested = sum(_get_position_value(p) for p in positions)
    
    if total_invested == 0:
        return 0.0, 0.0
    
    # Current drawdown: how much are we down from invested capital
    if total_unrealized < 0:
        current_dd = abs(total_unrealized) / total_invested * 100
    else:
        current_dd = 0.0
    
    # Max drawdown: check each position's worst unrealized loss
    # This is an approximation — true max DD needs historical equity curve
    worst_position_dd = 0.0
    for pos in positions:
        pos_val = _get_position_value(pos)
        if pos_val > 0 and (pos.unrealized_pnl or 0) < 0:
            pos_dd = abs(pos.unrealized_pnl) / pos_val * 100
            worst_position_dd = max(worst_position_dd, pos_dd)
    
    # Max DD is at least the current DD
    max_dd = max(current_dd, worst_position_dd)
    
    return round(current_dd, 2), round(max_dd, 2)


def calculate_portfolio_beta(positions: List[PositionORM]) -> float:
    """
    Calculate portfolio beta using asset-class-weighted approach.
    
    Uses known betas by asset class since we don't have per-symbol beta data.
    This is more honest than returning 1.0 for everything.
    """
    if not positions:
        return 0.0
    
    from src.risk.risk_manager import SYMBOL_SECTOR_MAP
    
    # Asset class betas (relative to S&P 500)
    ASSET_BETAS = {
        'Technology': 1.2,
        'Finance': 1.1,
        'Healthcare': 0.8,
        'Energy': 1.0,
        'Industrials': 1.0,
        'Consumer': 0.9,
        'Utilities': 0.5,
        'Commodities': 0.3,
        'Commodities ETF': 0.3,
        'Crypto': 1.5,
        'Forex': 0.0,
        'Indices': 1.0,
        'Broad Market ETF': 1.0,
        'Technology ETF': 1.2,
        'Bonds ETF': -0.2,
        'International ETF': 0.8,
        'Real Estate': 0.7,
    }
    
    total_value = 0.0
    weighted_beta = 0.0
    
    for pos in positions:
        pos_value = _get_position_value(pos)
        if pos_value <= 0:
            continue
        
        sector = SYMBOL_SECTOR_MAP.get(pos.symbol.upper(), 'Unknown')
        beta = ASSET_BETAS.get(sector, 1.0)
        
        # Short positions have negative beta contribution
        if pos.side == PositionSide.SHORT:
            beta = -beta
        
        weighted_beta += beta * pos_value
        total_value += pos_value
    
    if total_value == 0:
        return 0.0
    
    return round(weighted_beta / total_value, 2)


def calculate_risk_score(var: float, drawdown: float, leverage: float, 
                         max_var: float = 10000, max_drawdown: float = 15.0, 
                         max_leverage: float = 2.0) -> tuple[str, list]:
    """
    Calculate overall risk score with explanations.
    
    Returns:
        Tuple of (risk_level, reasons) where reasons explain each flag.
    """
    reasons = []
    danger_count = 0
    warning_count = 0
    
    # Check VaR
    if var > max_var:
        danger_count += 1
        reasons.append(f"VaR ${var:,.0f} exceeds limit ${max_var:,.0f} (DANGER)")
    elif var > max_var * 0.8:
        warning_count += 1
        reasons.append(f"VaR ${var:,.0f} approaching limit ${max_var:,.0f} ({var/max_var*100:.0f}%)")
    
    # Check drawdown
    if drawdown > max_drawdown:
        danger_count += 1
        reasons.append(f"Drawdown {drawdown:.1f}% exceeds limit {max_drawdown:.1f}% (DANGER)")
    elif drawdown > max_drawdown * 0.8:
        warning_count += 1
        reasons.append(f"Drawdown {drawdown:.1f}% approaching limit {max_drawdown:.1f}%")
    
    # Check leverage
    if leverage > max_leverage:
        danger_count += 1
        reasons.append(f"Leverage {leverage:.2f}x exceeds limit {max_leverage:.1f}x (DANGER)")
    elif leverage > max_leverage * 0.8:
        warning_count += 1
        reasons.append(f"Leverage {leverage:.2f}x approaching limit {max_leverage:.1f}x")
    
    if not reasons:
        reasons.append("All risk metrics within acceptable limits")
    
    if danger_count > 0:
        return 'danger', reasons
    elif warning_count > 0:
        return 'warning', reasons
    else:
        return 'safe', reasons


@router.get("/metrics", response_model=RiskMetricsResponse)
async def get_risk_metrics(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Get comprehensive risk metrics for the portfolio.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        config: Configuration instance
        
    Returns:
        Risk metrics including VaR, drawdown, leverage, beta
    """
    logger.info(f"Getting risk metrics for {mode.value} mode, user {username}")
    
    # Get all open positions
    positions = session.query(PositionORM).filter(
        PositionORM.closed_at.is_(None)
    ).all()
    
    # Get risk configuration
    risk_config = config.load_risk_config(mode)
    
    # Get account info first (needed for drawdown calculation)
    from src.models.orm import AccountInfoORM
    account_id = f"{mode.value.lower()}_account_001"
    account = session.query(AccountInfoORM).filter_by(account_id=account_id).first()
    account_balance = account.balance if account else 100000.0
    account_equity = getattr(account, 'equity', None) or account_balance
    
    # Calculate metrics
    portfolio_var = calculate_portfolio_var(positions)
    current_drawdown, max_drawdown = calculate_drawdown(positions, account_equity)
    portfolio_beta = calculate_portfolio_beta(positions)
    
    # Calculate leverage and exposure
    total_position_value = sum(_get_position_value(p) for p in positions)
    
    leverage = total_position_value / account_equity if account_equity > 0 else 0.0
    margin_utilization = (total_position_value / account_equity * 100) if account_equity > 0 else 0.0
    
    # Calculate max position size
    position_sizes = [_get_position_value(p) / account_balance * 100 
                      for p in positions] if account_balance > 0 else []
    max_position_size = max(position_sizes) if position_sizes else 0.0
    
    # Calculate risk breakdown by strategy
    risk_breakdown = {}
    for position in positions:
        strategy_id = position.strategy_id or 'unknown'
        position_risk = _get_position_value(position)
        risk_breakdown[strategy_id] = risk_breakdown.get(strategy_id, 0.0) + position_risk
    
    # Calculate risk score
    risk_score, risk_reasons = calculate_risk_score(
        portfolio_var, 
        current_drawdown, 
        leverage,
        max_var=risk_config.max_daily_loss_pct * account_equity,
        max_drawdown=risk_config.max_drawdown_pct * 100,
        max_leverage=2.0
    )
    
    return RiskMetricsResponse(
        portfolio_var=portfolio_var,
        current_drawdown=current_drawdown,
        max_drawdown=max_drawdown,
        leverage=leverage,
        margin_utilization=margin_utilization,
        portfolio_beta=portfolio_beta,
        max_position_size=max_position_size,
        total_exposure=total_position_value,
        risk_score=risk_score,
        risk_reasons=risk_reasons,
        active_positions_count=len(positions),
        risk_breakdown=risk_breakdown
    )


@router.get("/history", response_model=RiskHistoryResponse)
async def get_risk_history(
    mode: TradingMode,
    period: str = "1W",
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """Get historical risk metrics computed from actual position snapshots."""
    logger.info(f"Getting risk history for {mode.value} mode, period {period}, user {username}")
    
    period_map = {
        '1D': timedelta(days=1),
        '1W': timedelta(weeks=1),
        '1M': timedelta(days=30),
        '3M': timedelta(days=90)
    }
    
    time_delta = period_map.get(period, timedelta(weeks=1))
    start_date = datetime.now() - time_delta
    
    # Get all positions that were open during this period
    # (opened before end of period AND not closed before start of period)
    all_positions = session.query(PositionORM).filter(
        PositionORM.opened_at <= datetime.now(),
        (PositionORM.closed_at.is_(None)) | (PositionORM.closed_at >= start_date)
    ).order_by(PositionORM.opened_at).all()
    
    if not all_positions:
        return RiskHistoryResponse(history=[], period=period)
    
    # Build daily snapshots by checking which positions were open each day
    history = []
    num_points = min(30, max(7, int(time_delta.days)))
    
    for i in range(num_points):
        snapshot_date = start_date + (time_delta / num_points) * i
        
        # Positions open at this snapshot
        open_at_snapshot = [
            p for p in all_positions
            if p.opened_at <= snapshot_date
            and (p.closed_at is None or p.closed_at > snapshot_date)
        ]
        
        if not open_at_snapshot:
            continue
        
        snapshot_var = calculate_portfolio_var(open_at_snapshot)
        snapshot_dd, _ = calculate_drawdown(open_at_snapshot)
        snapshot_beta = calculate_portfolio_beta(open_at_snapshot)
        total_val = sum(_get_position_value(p) for p in open_at_snapshot)
        
        # Leverage approximation (would need account balance at that point)
        from src.models.orm import AccountInfoORM
        account_id = f"{mode.value.lower()}_account_001"
        account = session.query(AccountInfoORM).filter_by(account_id=account_id).first()
        acct_equity = getattr(account, 'equity', None) or getattr(account, 'balance', 100000.0) if account else 100000.0
        leverage = total_val / acct_equity if acct_equity > 0 else 0.0
        
        history.append(RiskHistoryPoint(
            timestamp=snapshot_date.isoformat(),
            var=round(snapshot_var, 2),
            drawdown=round(snapshot_dd, 2),
            leverage=round(leverage, 2),
            beta=round(snapshot_beta, 2)
        ))
    
    return RiskHistoryResponse(history=history, period=period)


@router.get("/limits", response_model=RiskLimitsResponse)
async def get_risk_limits(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Get current risk limits.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        config: Configuration instance
        
    Returns:
        Current risk limits
    """
    logger.info(f"Getting risk limits for {mode.value} mode, user {username}")
    
    risk_config = config.load_risk_config(mode)
    
    return RiskLimitsResponse(
        max_position_size=risk_config.max_position_size_pct * 100,
        max_portfolio_exposure=risk_config.max_exposure_pct * 100,
        max_daily_loss=risk_config.max_daily_loss_pct * 100,
        max_drawdown=risk_config.max_drawdown_pct * 100,
        max_leverage=2.0,
        risk_per_trade=risk_config.position_risk_pct * 100
    )


@router.put("/limits", response_model=dict)
async def update_risk_limits(
    request: UpdateRiskLimitsRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    config: Configuration = Depends(get_configuration)
):
    """
    Update risk limits.
    
    Args:
        request: Risk limits update request
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        config: Configuration instance
        
    Returns:
        Success response with updated limits
    """
    logger.info(f"Updating risk limits for {mode.value} mode, user {username}")
    
    # Get current risk config
    risk_config = config.load_risk_config(mode)
    
    # Update provided fields
    if request.max_position_size is not None:
        risk_config['max_position_size'] = request.max_position_size
    if request.max_portfolio_exposure is not None:
        risk_config['max_portfolio_exposure'] = request.max_portfolio_exposure
    if request.max_daily_loss is not None:
        risk_config['max_daily_loss'] = request.max_daily_loss
    if request.max_drawdown is not None:
        risk_config['max_drawdown'] = request.max_drawdown
    if request.max_leverage is not None:
        risk_config['max_leverage'] = request.max_leverage
    if request.risk_per_trade is not None:
        risk_config['risk_per_trade'] = request.risk_per_trade
    
    # Save updated config
    config.update_risk_config(mode, risk_config)
    
    logger.info(f"Risk limits updated successfully")
    
    return {
        "success": True,
        "message": "Risk limits updated successfully",
        "limits": risk_config
    }


@router.get("/alerts", response_model=List[RiskAlertResponse])
async def get_risk_alerts(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Get active risk alerts.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        config: Configuration instance
        
    Returns:
        List of active risk alerts
    """
    logger.info(f"Getting risk alerts for {mode.value} mode, user {username}")
    
    alerts = []
    
    # Get current metrics
    positions = session.query(PositionORM).filter(
        PositionORM.closed_at.is_(None)
    ).all()
    
    risk_config = config.load_risk_config(mode)
    
    # Get account balance for calculating max daily loss
    from src.models.orm import AccountInfoORM, AlertHistoryORM
    account_id = f"{mode.value.lower()}_account_001"
    account = session.query(AccountInfoORM).filter_by(account_id=account_id).first()
    account_balance = account.balance if account else 100000.0
    account_equity = getattr(account, 'equity', None) or account_balance
    
    portfolio_var = calculate_portfolio_var(positions)
    current_drawdown, _ = calculate_drawdown(positions, account_equity)
    
    # --- Generate current alerts and persist new ones ---
    current_breaches = []  # (alert_type, severity, title, message, metadata)
    
    # Check VaR threshold
    max_daily_loss = risk_config.max_daily_loss_pct * account_equity
    var_pct = (portfolio_var / max_daily_loss * 100) if max_daily_loss > 0 else 0
    if portfolio_var > max_daily_loss:
        current_breaches.append((
            'var_breach', 'danger', 'VaR Limit Exceeded',
            f"Portfolio VaR (${portfolio_var:,.0f}) exceeds limit (${max_daily_loss:,.0f})",
            {'var': portfolio_var, 'limit': max_daily_loss}
        ))
    elif var_pct > 80:
        current_breaches.append((
            'var_warning', 'warning', 'VaR Approaching Limit',
            f"Portfolio VaR (${portfolio_var:,.0f}) at {var_pct:.0f}% of limit (${max_daily_loss:,.0f})",
            {'var': portfolio_var, 'limit': max_daily_loss}
        ))
    
    # Check drawdown threshold
    max_drawdown = risk_config.max_drawdown_pct * 100
    if current_drawdown > max_drawdown:
        current_breaches.append((
            'drawdown_breach', 'danger', 'Drawdown Limit Exceeded',
            f"Current drawdown ({current_drawdown:.1f}%) exceeds limit ({max_drawdown:.1f}%)",
            {'drawdown': current_drawdown, 'limit': max_drawdown}
        ))
    elif current_drawdown > max_drawdown * 0.8:
        current_breaches.append((
            'drawdown_warning', 'warning', 'Drawdown Approaching Limit',
            f"Current drawdown ({current_drawdown:.1f}%) at {current_drawdown/max_drawdown*100:.0f}% of limit ({max_drawdown:.1f}%)",
            {'drawdown': current_drawdown, 'limit': max_drawdown}
        ))
    
    # Check exposure vs equity
    total_exposure = sum(_get_position_value(p) for p in positions)
    max_exposure = risk_config.max_exposure_pct * account_equity
    exposure_pct = (total_exposure / max_exposure * 100) if max_exposure > 0 else 0
    if total_exposure > max_exposure:
        current_breaches.append((
            'exposure_breach', 'warning', 'Exposure Limit Exceeded',
            f"Total exposure (${total_exposure:,.0f}) exceeds {risk_config.max_exposure_pct:.0%} of equity (${max_exposure:,.0f})",
            {'exposure': total_exposure, 'limit': max_exposure}
        ))
    elif exposure_pct > 80:
        current_breaches.append((
            'exposure_warning', 'info', 'Exposure Approaching Limit',
            f"Total exposure (${total_exposure:,.0f}) at {exposure_pct:.0f}% of limit (${max_exposure:,.0f})",
            {'exposure': total_exposure, 'limit': max_exposure}
        ))
    
    # Always add a status summary alert so the section is never empty
    if not current_breaches:
        leverage_val = total_exposure / account_equity if account_equity > 0 else 0
        alerts.append(RiskAlertResponse(
            id='status_summary',
            severity='info',
            metric='Risk Status',
            current_value=0,
            threshold=0,
            message=f"All clear — VaR ${portfolio_var:,.0f} ({var_pct:.0f}% of limit), DD {current_drawdown:.1f}%, Leverage {leverage_val:.2f}x, {len(positions)} positions",
            timestamp=datetime.now().isoformat()
        ))
    
    # Persist new breaches (avoid duplicates — only insert if no matching alert in last hour)
    one_hour_ago = datetime.now() - timedelta(hours=1)
    for alert_type, severity, title, message, metadata in current_breaches:
        existing = session.query(AlertHistoryORM).filter(
            AlertHistoryORM.alert_type == alert_type,
            AlertHistoryORM.created_at >= one_hour_ago
        ).first()
        if not existing:
            new_alert = AlertHistoryORM(
                alert_type=alert_type,
                severity=severity,
                title=title,
                message=message,
                alert_metadata=metadata,
                link_page='/risk',
                created_at=datetime.now()
            )
            session.add(new_alert)
    
    try:
        session.commit()
    except Exception:
        session.rollback()
    
    # Return recent alerts (last 30 days) — ALL types, not just risk breaches.
    # Include monitoring alerts (pnl_loss, strategy_retired, position_loss, etc.)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_alerts = session.query(AlertHistoryORM).filter(
        AlertHistoryORM.created_at >= thirty_days_ago,
    ).order_by(AlertHistoryORM.created_at.desc()).limit(30).all()
    
    for alert in recent_alerts:
        meta = alert.alert_metadata or {}
        alerts.append(RiskAlertResponse(
            id=str(alert.id),
            severity=alert.severity or 'info',
            metric=alert.title or alert.alert_type or 'Alert',
            current_value=meta.get('var', 0) or meta.get('drawdown', 0) or meta.get('exposure', 0) or meta.get('pnl', 0) or meta.get('value', 0),
            threshold=meta.get('limit', 0) or meta.get('threshold', 0),
            message=alert.message,
            timestamp=alert.created_at.isoformat() if alert.created_at else datetime.now().isoformat()
        ))
    
    return alerts


@router.get("/positions", response_model=List[PositionRiskResponse])
async def get_position_risks(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get risk details for all positions.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        List of position risk details
    """
    logger.info(f"Getting position risks for {mode.value} mode, user {username}")
    
    positions = session.query(PositionORM).filter(
        PositionORM.closed_at.is_(None)
    ).all()
    
    position_risks = []
    
    for position in positions:
        # Calculate risk amount (potential loss to stop loss)
        risk_amount = abs(position.unrealized_pnl) if (position.unrealized_pnl or 0) < 0 else 0.0
        position_value = _get_position_value(position)
        risk_percent = (risk_amount / position_value * 100) if position_value > 0 else 0.0
        
        # Determine risk level
        if risk_percent > 10:
            risk_level = 'high'
        elif risk_percent > 5:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        position_risks.append(PositionRiskResponse(
            position_id=position.id,
            symbol=position.symbol,
            strategy_id=position.strategy_id or 'unknown',
            risk_amount=risk_amount,
            risk_percent=risk_percent,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            risk_level=risk_level
        ))
    
    return position_risks


# ============================================================================
# Advanced Risk Visualisation (Task 11.10.13)
# ============================================================================

class CorrelatedPair(BaseModel):
    """A pair of correlated positions."""
    symbol_a: str
    symbol_b: str
    correlation: float
    risk_level: str  # high, medium, low


class VaRResult(BaseModel):
    """Value at Risk calculation result."""
    var_95: float
    var_99: float
    var_95_pct: float
    var_99_pct: float
    method: str = "historical_simulation"
    trading_days_used: int


class StressScenario(BaseModel):
    """Stress test scenario result."""
    name: str
    description: str
    estimated_loss: float
    estimated_loss_pct: float
    affected_positions: int


class MarginUtilization(BaseModel):
    """Margin utilization data."""
    used: float
    available: float
    total: float
    utilization_pct: float
    zone: str  # green, amber, red


class ExposureBreakdown(BaseModel):
    """Exposure breakdown item."""
    name: str
    value: float
    percentage: float
    limit: Optional[float] = None


class DirectionalExposure(BaseModel):
    """Long vs short exposure."""
    long_value: float
    long_pct: float
    short_value: float
    short_pct: float
    net_value: float
    net_pct: float
    limit_pct: float = 60.0


class AdvancedRiskResponse(BaseModel):
    """Advanced risk visualization response."""
    correlated_pairs: List[CorrelatedPair]
    var: VaRResult
    stress_tests: List[StressScenario]
    margin: MarginUtilization
    sector_exposure: List[ExposureBreakdown]
    asset_class_exposure: List[ExposureBreakdown]
    directional_exposure: DirectionalExposure


def _get_asset_class(symbol: str) -> str:
    """Classify a symbol into its asset class using the SymbolRegistry."""
    try:
        from src.core.symbol_registry import get_registry
        ac = get_registry().get_asset_class(symbol.upper())
        if ac:
            # Normalize to display names
            _AC_DISPLAY = {
                "stocks": "Stocks",
                "etfs": "ETFs",
                "forex": "Forex",
                "indices": "Indices",
                "commodities": "Commodities",
                "crypto": "Crypto",
            }
            return _AC_DISPLAY.get(ac.lower(), ac.capitalize())
    except Exception:
        pass
    # Fallback: infer from sector map
    from src.risk.risk_manager import SYMBOL_SECTOR_MAP
    sector = SYMBOL_SECTOR_MAP.get(symbol.upper(), "")
    if sector == "Forex":
        return "Forex"
    if sector == "Crypto":
        return "Crypto"
    if sector in ("Commodities", "Commodities ETF"):
        return "Commodities"
    if sector == "Indices":
        return "Indices"
    if "ETF" in sector:
        return "ETFs"
    return "Stocks"


def _calculate_correlated_pairs(
    positions: List[PositionORM], session: Session
) -> List[CorrelatedPair]:
    """Calculate top correlated position pairs using historical price data from DB."""
    from src.models.orm import HistoricalPriceCacheORM

    if len(positions) < 2:
        return []

    symbols = list(set(p.symbol for p in positions))
    if len(symbols) < 2:
        return []

    # Fetch last 60 days of close prices per symbol from DB
    cutoff = datetime.now() - timedelta(days=90)
    price_data: Dict[str, List[float]] = {}

    for symbol in symbols[:20]:  # Limit to 20 symbols for performance
        rows = (
            session.query(HistoricalPriceCacheORM)
            .filter(
                HistoricalPriceCacheORM.symbol == symbol,
                HistoricalPriceCacheORM.date >= cutoff,
            )
            .order_by(HistoricalPriceCacheORM.date.asc())
            .all()
        )
        if len(rows) >= 20:
            closes = [r.close for r in rows if r.close and r.close > 0]
            if len(closes) >= 20:
                # Calculate daily returns
                returns = []
                for i in range(1, len(closes)):
                    returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
                price_data[symbol] = returns

    # Calculate pairwise correlations
    pairs: List[CorrelatedPair] = []
    syms = list(price_data.keys())

    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a_returns = price_data[syms[i]]
            b_returns = price_data[syms[j]]
            # Align lengths
            min_len = min(len(a_returns), len(b_returns))
            if min_len < 15:
                continue
            a = np.array(a_returns[:min_len])
            b = np.array(b_returns[:min_len])
            if np.std(a) == 0 or np.std(b) == 0:
                continue
            corr = float(np.corrcoef(a, b)[0, 1])
            if not np.isfinite(corr):
                continue

            risk_level = "low"
            if abs(corr) > 0.7:
                risk_level = "high"
            elif abs(corr) > 0.4:
                risk_level = "medium"

            pairs.append(CorrelatedPair(
                symbol_a=syms[i],
                symbol_b=syms[j],
                correlation=round(corr, 3),
                risk_level=risk_level,
            ))

    # Sort by absolute correlation descending, return top 10
    pairs.sort(key=lambda p: abs(p.correlation), reverse=True)
    return pairs[:10]


def _calculate_var_historical(
    positions: List[PositionORM], session: Session
) -> VaRResult:
    """Calculate VaR using historical simulation (last 252 trading days)."""
    from src.models.orm import HistoricalPriceCacheORM

    if not positions:
        return VaRResult(
            var_95=0, var_99=0, var_95_pct=0, var_99_pct=0, trading_days_used=0
        )

    cutoff = datetime.now() - timedelta(days=400)  # ~252 trading days
    portfolio_value = sum(_get_position_value(p) for p in positions)
    if portfolio_value == 0:
        return VaRResult(
            var_95=0, var_99=0, var_95_pct=0, var_99_pct=0, trading_days_used=0
        )

    # Collect daily returns per position, weighted by position value
    all_portfolio_returns: List[np.ndarray] = []
    weights: List[float] = []

    for pos in positions:
        pos_value = _get_position_value(pos)
        if pos_value == 0:
            continue

        rows = (
            session.query(HistoricalPriceCacheORM)
            .filter(
                HistoricalPriceCacheORM.symbol == pos.symbol,
                HistoricalPriceCacheORM.date >= cutoff,
            )
            .order_by(HistoricalPriceCacheORM.date.asc())
            .all()
        )
        closes = [r.close for r in rows if r.close and r.close > 0]
        if len(closes) < 30:
            continue

        returns = []
        for i in range(1, len(closes)):
            returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

        all_portfolio_returns.append(np.array(returns))
        weights.append(pos_value / portfolio_value)

    if not all_portfolio_returns:
        return VaRResult(
            var_95=0, var_99=0, var_95_pct=0, var_99_pct=0, trading_days_used=0
        )

    # Align all return series to same length
    min_len = min(len(r) for r in all_portfolio_returns)
    trading_days = min(min_len, 252)

    # Calculate weighted portfolio returns
    portfolio_daily_returns = np.zeros(trading_days)
    for ret_arr, w in zip(all_portfolio_returns, weights):
        portfolio_daily_returns += ret_arr[-trading_days:] * w

    # Historical VaR: percentile of losses
    var_95_pct = float(-np.percentile(portfolio_daily_returns, 5))
    var_99_pct = float(-np.percentile(portfolio_daily_returns, 1))

    var_95 = var_95_pct * portfolio_value
    var_99 = var_99_pct * portfolio_value

    return VaRResult(
        var_95=round(var_95, 2),
        var_99=round(var_99, 2),
        var_95_pct=round(var_95_pct * 100, 2),
        var_99_pct=round(var_99_pct * 100, 2),
        trading_days_used=trading_days,
    )


def _calculate_stress_tests(positions: List[PositionORM]) -> List[StressScenario]:
    """Calculate stress test scenario impacts on the portfolio."""
    from src.risk.risk_manager import get_symbol_sector

    if not positions:
        return []

    portfolio_value = sum(_get_position_value(p) for p in positions)
    if portfolio_value == 0:
        return []

    scenarios: List[StressScenario] = []

    # 1. Market crash -5%
    crash_loss = portfolio_value * 0.05
    scenarios.append(StressScenario(
        name="Market Crash -5%",
        description="All positions drop 5% simultaneously",
        estimated_loss=round(crash_loss, 2),
        estimated_loss_pct=5.0,
        affected_positions=len(positions),
    ))

    # 2. Sector rotation: top sector drops 10%
    sector_values: Dict[str, float] = {}
    sector_counts: Dict[str, int] = {}
    for pos in positions:
        sector = get_symbol_sector(pos.symbol)
        val = _get_position_value(pos)
        sector_values[sector] = sector_values.get(sector, 0) + val
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    if sector_values:
        top_sector = max(sector_values, key=sector_values.get)
        top_sector_loss = sector_values[top_sector] * 0.10
        scenarios.append(StressScenario(
            name=f"Sector Rotation ({top_sector} -10%)",
            description=f"Your top sector '{top_sector}' drops 10%",
            estimated_loss=round(top_sector_loss, 2),
            estimated_loss_pct=round(top_sector_loss / portfolio_value * 100, 2),
            affected_positions=sector_counts.get(top_sector, 0),
        ))

    # 3. Volatility spike (VIX +50%)
    # Higher vol typically hurts long positions more; estimate ~3% impact
    vol_loss = portfolio_value * 0.03
    scenarios.append(StressScenario(
        name="Volatility Spike (VIX +50%)",
        description="Sudden volatility increase impacts all positions",
        estimated_loss=round(vol_loss, 2),
        estimated_loss_pct=round(vol_loss / portfolio_value * 100, 2),
        affected_positions=len(positions),
    ))

    # 4. Interest rate shock: impacts bonds, utilities, rate-sensitive
    rate_sensitive_sectors = {"Bonds ETF", "Utilities", "Finance"}
    rate_loss = 0.0
    rate_count = 0
    for pos in positions:
        sector = get_symbol_sector(pos.symbol)
        if sector in rate_sensitive_sectors:
            val = _get_position_value(pos)
            rate_loss += val * 0.07  # 7% impact on rate-sensitive
            rate_count += 1

    scenarios.append(StressScenario(
        name="Interest Rate Shock (+100bps)",
        description="Rate-sensitive positions (bonds, utilities, financials) impacted",
        estimated_loss=round(rate_loss, 2),
        estimated_loss_pct=round(rate_loss / portfolio_value * 100, 2) if portfolio_value > 0 else 0,
        affected_positions=rate_count,
    ))

    return scenarios


@router.get("/advanced")
async def get_advanced_risk(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
):
    """
    Get advanced risk visualization data including correlation matrix,
    VaR, stress tests, margin utilization, and exposure breakdowns.
    """
    from src.risk.risk_manager import get_symbol_sector

    logger.info(f"Getting advanced risk data for {mode.value} mode, user {username}")

    positions = (
        session.query(PositionORM)
        .filter(PositionORM.closed_at.is_(None))
        .all()
    )

    portfolio_value = sum(_get_position_value(p) for p in positions)

    # 1. Correlated pairs
    try:
        correlated_pairs = _calculate_correlated_pairs(positions, session)
    except Exception as e:
        logger.warning(f"Failed to calculate correlations: {e}")
        correlated_pairs = []

    # 2. VaR
    try:
        var_result = _calculate_var_historical(positions, session)
    except Exception as e:
        logger.warning(f"Failed to calculate VaR: {e}")
        var_result = VaRResult(
            var_95=0, var_99=0, var_95_pct=0, var_99_pct=0, trading_days_used=0
        )

    # 3. Stress tests
    try:
        stress_tests = _calculate_stress_tests(positions)
    except Exception as e:
        logger.warning(f"Failed to calculate stress tests: {e}")
        stress_tests = []

    # 4. Margin utilization (estimate from portfolio)
    from src.models.orm import AccountInfoORM
    account_id = f"{mode.value.lower()}_account_001"
    account = session.query(AccountInfoORM).filter_by(account_id=account_id).first()
    account_balance = getattr(account, 'equity', None) or getattr(account, 'balance', 100000.0) if account else 100000.0
    margin_used = portfolio_value  # On eToro, invested amount IS the margin used
    margin_available = max(0, account_balance - margin_used)
    margin_total = account_balance
    margin_pct = (margin_used / margin_total * 100) if margin_total > 0 else 0

    margin_zone = "green"
    if margin_pct > 75:
        margin_zone = "red"
    elif margin_pct > 50:
        margin_zone = "amber"

    margin = MarginUtilization(
        used=round(margin_used, 2),
        available=round(margin_available, 2),
        total=round(margin_total, 2),
        utilization_pct=round(margin_pct, 2),
        zone=margin_zone,
    )

    # 5. Sector exposure
    sector_values: Dict[str, float] = {}
    for pos in positions:
        sector = get_symbol_sector(pos.symbol)
        val = _get_position_value(pos)
        sector_values[sector] = sector_values.get(sector, 0) + val

    sector_exposure = []
    for sector, val in sorted(sector_values.items(), key=lambda x: -x[1]):
        pct = (val / portfolio_value * 100) if portfolio_value > 0 else 0
        sector_exposure.append(ExposureBreakdown(
            name=sector,
            value=round(val, 2),
            percentage=round(pct, 2),
            limit=40.0,  # Max 40% per sector
        ))

    # 6. Asset class exposure
    ac_values: Dict[str, float] = {}
    for pos in positions:
        ac = _get_asset_class(pos.symbol)
        val = _get_position_value(pos)
        ac_values[ac] = ac_values.get(ac, 0) + val

    asset_class_exposure = []
    for ac, val in sorted(ac_values.items(), key=lambda x: -x[1]):
        pct = (val / portfolio_value * 100) if portfolio_value > 0 else 0
        asset_class_exposure.append(ExposureBreakdown(
            name=ac,
            value=round(val, 2),
            percentage=round(pct, 2),
        ))

    # 7. Directional exposure
    long_val = sum(
        _get_position_value(p)
        for p in positions
        if p.side == PositionSide.LONG
    )
    short_val = sum(
        _get_position_value(p)
        for p in positions
        if p.side == PositionSide.SHORT
    )
    total_dir = long_val + short_val
    long_pct = (long_val / total_dir * 100) if total_dir > 0 else 0
    short_pct = (short_val / total_dir * 100) if total_dir > 0 else 0

    directional = DirectionalExposure(
        long_value=round(long_val, 2),
        long_pct=round(long_pct, 2),
        short_value=round(short_val, 2),
        short_pct=round(short_pct, 2),
        net_value=round(long_val - short_val, 2),
        net_pct=round(long_pct - short_pct, 2),
        limit_pct=60.0,
    )

    return {
        "success": True,
        "data": AdvancedRiskResponse(
            correlated_pairs=correlated_pairs,
            var=var_result,
            stress_tests=stress_tests,
            margin=margin,
            sector_exposure=sector_exposure,
            asset_class_exposure=asset_class_exposure,
            directional_exposure=directional,
        ).model_dump(),
    }


# ============================================================================
# CIO Risk Dashboard (Institutional-Grade Risk Metrics)
# ============================================================================

class ConcentrationMetrics(BaseModel):
    """Portfolio concentration risk metrics."""
    top5_positions_pct: float = Field(description="Top 5 positions as % of portfolio")
    top3_sectors_pct: float = Field(description="Top 3 sectors as % of portfolio")
    herfindahl_index: float = Field(description="HHI — sum of squared weights. Lower = more diversified. <0.1 = diversified, >0.25 = concentrated")
    largest_position_symbol: str
    largest_position_pct: float


class FactorExposure(BaseModel):
    """Current factor exposure from the fundamental ranker."""
    factor: str
    weight_pct: float
    current_tilt: str = Field(description="overweight, neutral, underweight vs equal-weight baseline")


class CIORiskResponse(BaseModel):
    """Institutional-grade risk dashboard response."""
    # Exposure headlines
    gross_exposure: float = Field(description="Long + Short (total capital at risk)")
    net_exposure: float = Field(description="Long - Short (directional bet)")
    gross_exposure_pct: float
    net_exposure_pct: float
    
    # Expected Shortfall (CVaR)
    cvar_95: float = Field(description="Expected loss in worst 5% of days")
    cvar_99: float = Field(description="Expected loss in worst 1% of days")
    cvar_95_pct: float
    cvar_99_pct: float
    
    # Concentration
    concentration: ConcentrationMetrics
    
    # Factor exposure
    factor_exposures: List[FactorExposure]
    regime: str
    
    # Risk budget
    var_budget_used_pct: float = Field(description="Current VaR / Max allowed VaR × 100")
    exposure_budget_used_pct: float = Field(description="Current exposure / Max exposure × 100")
    drawdown_budget_used_pct: float = Field(description="Current drawdown / Max drawdown × 100")


@router.get("/cio-risk")
async def get_cio_risk(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    CIO-grade risk dashboard: gross/net exposure, CVaR, concentration metrics,
    factor exposure, risk budget utilization.
    """
    logger.info(f"Getting CIO risk dashboard for {mode.value} mode")
    
    try:
        positions = session.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()
        
        risk_config = config.load_risk_config(mode)
        
        # Account info
        from src.models.orm import AccountInfoORM
        account = session.query(AccountInfoORM).filter_by(
            account_id=f"{mode.value.lower()}_account_001"
        ).first()
        account_equity = getattr(account, 'equity', None) or getattr(account, 'balance', 100000.0) if account else 100000.0
        
        # --- Gross/Net Exposure ---
        long_val = sum(_get_position_value(p) for p in positions if p.side == PositionSide.LONG)
        short_val = sum(_get_position_value(p) for p in positions if p.side == PositionSide.SHORT)
        gross = long_val + short_val
        net = long_val - short_val
        gross_pct = (gross / account_equity * 100) if account_equity > 0 else 0
        net_pct = (net / account_equity * 100) if account_equity > 0 else 0
        
        # --- Expected Shortfall (CVaR) ---
        # CVaR = average loss in the worst X% of days
        # Use historical simulation from the advanced VaR calculation
        cvar_95 = 0.0
        cvar_99 = 0.0
        cvar_95_pct = 0.0
        cvar_99_pct = 0.0
        try:
            from src.models.orm import HistoricalPriceCacheORM
            cutoff = datetime.now() - timedelta(days=400)
            portfolio_value = gross if gross > 0 else 1.0
            
            all_returns = []
            weights = []
            for pos in positions:
                pos_value = _get_position_value(pos)
                if pos_value <= 0:
                    continue
                rows = session.query(HistoricalPriceCacheORM).filter(
                    HistoricalPriceCacheORM.symbol == pos.symbol,
                    HistoricalPriceCacheORM.date >= cutoff,
                ).order_by(HistoricalPriceCacheORM.date.asc()).all()
                closes = [r.close for r in rows if r.close and r.close > 0]
                if len(closes) < 30:
                    continue
                returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
                all_returns.append(np.array(returns))
                weights.append(pos_value / portfolio_value)
            
            if all_returns:
                min_len = min(len(r) for r in all_returns)
                trading_days = min(min_len, 252)
                port_returns = np.zeros(trading_days)
                for ret_arr, w in zip(all_returns, weights):
                    port_returns += ret_arr[-trading_days:] * w
                
                # CVaR = mean of returns below the VaR threshold
                var_95_threshold = np.percentile(port_returns, 5)
                var_99_threshold = np.percentile(port_returns, 1)
                tail_95 = port_returns[port_returns <= var_95_threshold]
                tail_99 = port_returns[port_returns <= var_99_threshold]
                
                cvar_95_pct = float(-np.mean(tail_95)) * 100 if len(tail_95) > 0 else 0
                cvar_99_pct = float(-np.mean(tail_99)) * 100 if len(tail_99) > 0 else 0
                cvar_95 = cvar_95_pct / 100 * portfolio_value
                cvar_99 = cvar_99_pct / 100 * portfolio_value
        except Exception as e:
            logger.warning(f"CVaR calculation failed: {e}")
        
        # --- Concentration Metrics ---
        from src.risk.risk_manager import get_symbol_sector
        
        position_values = [(p.symbol, _get_position_value(p)) for p in positions]
        position_values.sort(key=lambda x: x[1], reverse=True)
        
        total_val = sum(v for _, v in position_values) or 1.0
        
        # Top 5 positions
        top5_val = sum(v for _, v in position_values[:5])
        top5_pct = top5_val / total_val * 100
        
        # Top 3 sectors
        sector_vals = defaultdict(float)
        for sym, val in position_values:
            sector_vals[get_symbol_sector(sym)] += val
        sorted_sectors = sorted(sector_vals.values(), reverse=True)
        top3_sectors_pct = sum(sorted_sectors[:3]) / total_val * 100 if sorted_sectors else 0
        
        # Herfindahl Index
        weights_sq = [(v / total_val) ** 2 for _, v in position_values]
        hhi = sum(weights_sq)
        
        largest_sym = position_values[0][0] if position_values else "N/A"
        largest_pct = (position_values[0][1] / total_val * 100) if position_values else 0
        
        concentration = ConcentrationMetrics(
            top5_positions_pct=round(top5_pct, 1),
            top3_sectors_pct=round(top3_sectors_pct, 1),
            herfindahl_index=round(hhi, 4),
            largest_position_symbol=largest_sym,
            largest_position_pct=round(largest_pct, 1),
        )
        
        # --- Factor Exposure ---
        factor_exposures = []
        regime_str = "unknown"
        try:
            from src.strategy.fundamental_ranker import FundamentalRanker
            weights_map = FundamentalRanker.REGIME_WEIGHTS
            
            # Detect current regime — MarketStatisticsAnalyzer needs an etoro_client,
            # so we skip live detection here and use the stored regime from the DB instead.
            from src.models.orm import StrategyORM as _SO
            latest_strategy = session.query(_SO).filter(
                _SO.market_regime.isnot(None)
            ).order_by(_SO.updated_at.desc()).first()
            regime_str = (latest_strategy.market_regime or "ranging_low_vol") if latest_strategy else "ranging_low_vol"
            
            # Get current weights for this regime
            regime_key = regime_str.lower()
            current_weights = None
            for rk, rw in weights_map.items():
                if rk == regime_key or rk in regime_key or regime_key in rk:
                    current_weights = rw
                    break
            if current_weights is None:
                current_weights = {"value": 0.25, "quality": 0.25, "momentum": 0.25, "growth": 0.25}
            
            equal_weight = 0.25
            for factor, weight in current_weights.items():
                if weight > equal_weight + 0.05:
                    tilt = "overweight"
                elif weight < equal_weight - 0.05:
                    tilt = "underweight"
                else:
                    tilt = "neutral"
                factor_exposures.append(FactorExposure(
                    factor=factor.capitalize(),
                    weight_pct=round(weight * 100, 1),
                    current_tilt=tilt,
                ))
        except Exception as e:
            logger.warning(f"Factor exposure calculation failed: {e}")
            for f in ["Value", "Quality", "Momentum", "Growth"]:
                factor_exposures.append(FactorExposure(factor=f, weight_pct=25.0, current_tilt="neutral"))
        
        # --- Risk Budget Utilization ---
        current_var = calculate_portfolio_var(positions)
        current_dd, _ = calculate_drawdown(positions, account_equity)
        
        max_var = risk_config.max_daily_loss_pct * account_equity
        max_dd = risk_config.max_drawdown_pct * 100
        max_exposure = risk_config.max_exposure_pct * account_equity
        
        var_budget = (current_var / max_var * 100) if max_var > 0 else 0
        exposure_budget = (gross / max_exposure * 100) if max_exposure > 0 else 0
        dd_budget = (current_dd / max_dd * 100) if max_dd > 0 else 0
        
        return {
            "success": True,
            "data": CIORiskResponse(
                gross_exposure=round(gross, 2),
                net_exposure=round(net, 2),
                gross_exposure_pct=round(gross_pct, 1),
                net_exposure_pct=round(net_pct, 1),
                cvar_95=round(cvar_95, 2),
                cvar_99=round(cvar_99, 2),
                cvar_95_pct=round(cvar_95_pct, 2),
                cvar_99_pct=round(cvar_99_pct, 2),
                concentration=concentration,
                factor_exposures=factor_exposures,
                regime=regime_str,
                var_budget_used_pct=round(min(var_budget, 100), 1),
                exposure_budget_used_pct=round(min(exposure_budget, 100), 1),
                drawdown_budget_used_pct=round(min(dd_budget, 100), 1),
            ).model_dump(),
        }
    
    except Exception as e:
        logger.error(f"Failed to get CIO risk dashboard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get CIO risk dashboard: {str(e)}"
        )
