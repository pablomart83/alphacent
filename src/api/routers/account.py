"""
Account and portfolio endpoints for AlphaCent Trading Platform.

Provides endpoints for account information and positions.
Validates: Requirements 11.1, 11.2
"""

import logging
import uuid
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.models.enums import TradingMode, PositionSide
from src.models.orm import AccountInfoORM, PositionORM
from src.models.dataclasses import Position
from src.api.dependencies import get_current_user, get_db_session, get_configuration
from src.api.etoro_client import EToroAPIClient, EToroAPIError, CircuitBreakerOpen
from src.core.config import Configuration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])


def get_etoro_client(mode: TradingMode, config: Configuration = Depends(get_configuration)) -> Optional[EToroAPIClient]:
    """
    Get eToro API client for the specified mode.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        config: Configuration instance
        
    Returns:
        EToroAPIClient instance or None if credentials not configured
    """
    try:
        # Get credentials from config
        credentials = config.load_credentials(mode)
        
        if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
            logger.warning(f"eToro credentials not configured for {mode.value} mode")
            return None
        
        # Create client (no authentication needed - uses header-based auth)
        client = EToroAPIClient(
            public_key=credentials["public_key"],
            user_key=credentials["user_key"],
            mode=mode
        )
        
        return client
        
    except Exception as e:
        logger.error(f"Failed to create eToro client for {mode.value} mode: {e}")
        return None


def _finalize_position_close(position_orm) -> None:
    """Set closed_at and compute realized_pnl when closing a position.
    
    Calculates realized P&L from price difference (not stale unrealized_pnl).
    After closing, unrealized is zeroed out. Also logs the exit to the trade journal
    so the performance feedback loop has accurate data.
    """
    position_orm.closed_at = datetime.now()
    # Calculate realized PnL from actual price movement
    entry = position_orm.entry_price or 0
    current = position_orm.current_price or entry
    invested = getattr(position_orm, 'invested_amount', None) or getattr(position_orm, 'quantity', 0) or 0
    if entry > 0 and invested > 0:
        side_str = str(position_orm.side).upper() if position_orm.side else 'LONG'
        if 'SHORT' in side_str or 'SELL' in side_str:
            calculated_pnl = invested * (entry - current) / entry
        else:
            calculated_pnl = invested * (current - entry) / entry
        position_orm.realized_pnl = (position_orm.realized_pnl or 0) + calculated_pnl
    else:
        position_orm.realized_pnl = (position_orm.realized_pnl or 0) + (position_orm.unrealized_pnl or 0)
    position_orm.unrealized_pnl = 0.0
    position_orm.pending_closure = False

    # Log to trade journal for performance feedback loop
    try:
        from src.analytics.trade_journal import TradeJournal
        from src.models.database import get_database
        journal = TradeJournal(get_database())
        journal.log_exit(
            trade_id=str(position_orm.id),
            exit_time=position_orm.closed_at,
            exit_price=position_orm.current_price,
            exit_reason="position_closed",
            symbol=position_orm.symbol,
        )
    except Exception as e:
        logger.debug(f"Could not log exit to trade journal for {getattr(position_orm, 'symbol', '?')}: {e}")


class AccountInfoResponse(BaseModel):
    """Account information response model."""
    account_id: str
    mode: TradingMode
    balance: float
    equity: float
    buying_power: float
    margin_used: float
    margin_available: float
    daily_pnl: float
    total_pnl: float
    positions_count: int
    updated_at: str


class PositionResponse(BaseModel):
    """Position response model."""
    id: str
    strategy_id: str
    strategy_name: Optional[str] = None
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    realized_pnl: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: str
    closed_at: Optional[str] = None
    etoro_position_id: str
    closure_reason: Optional[str] = None
    invested_amount: Optional[float] = None
    pending_closure: Optional[bool] = False


class PositionsResponse(BaseModel):
    """Positions list response model."""
    positions: List[PositionResponse]
    total_count: int
    pending_count: Optional[int] = 0  # Number of pending orders (positions waiting for market open)
    market_open: Optional[bool] = None  # Whether the market is currently open



def _refresh_account_from_etoro(mode: TradingMode, config: Configuration):
    """Background refresh of account info from eToro API (fire-and-forget)."""
    import threading

    def _do_refresh():
        try:
            etoro_client = get_etoro_client(mode, config)
            if not etoro_client:
                return
            account_info = etoro_client.get_account_info()

            from src.models.database import get_database
            db_instance = get_database()
            session = db_instance.get_session()
            try:
                account_orm = session.query(AccountInfoORM).filter(
                    AccountInfoORM.mode == mode.value
                ).first()
                if not account_orm:
                    account_orm = session.query(AccountInfoORM).filter_by(
                        account_id=account_info.account_id
                    ).first()

                if account_orm:
                    account_orm.balance = account_info.balance
                    account_orm.equity = account_info.equity
                    account_orm.buying_power = account_info.buying_power
                    account_orm.margin_used = account_info.margin_used
                    account_orm.margin_available = account_info.margin_available
                    account_orm.daily_pnl = account_info.daily_pnl
                    account_orm.total_pnl = account_info.total_pnl
                    account_orm.positions_count = account_info.positions_count
                    account_orm.updated_at = account_info.updated_at
                else:
                    # No record exists yet — create one so dashboard has data
                    account_orm = AccountInfoORM(
                        account_id=account_info.account_id,
                        mode=account_info.mode,
                        balance=account_info.balance,
                        equity=account_info.equity,
                        buying_power=account_info.buying_power,
                        margin_used=account_info.margin_used,
                        margin_available=account_info.margin_available,
                        daily_pnl=account_info.daily_pnl,
                        total_pnl=account_info.total_pnl,
                        positions_count=account_info.positions_count,
                        updated_at=account_info.updated_at,
                    )
                    session.add(account_orm)
                session.commit()
                logger.debug(f"Background account refresh complete for {mode.value}")
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Background account refresh failed: {e}")

    threading.Thread(target=_do_refresh, daemon=True).start()


@router.get("", response_model=AccountInfoResponse)
async def get_account_info(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Get account information.

    Returns cached data from database immediately for fast page loads.
    Background monitoring service keeps the data fresh via periodic eToro API sync.

    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        config: Configuration instance

    Returns:
        Account information from database cache

    Validates: Requirement 11.1
    """
    logger.info(f"Getting account info for {mode.value} mode, user {username}")

    # DB-first: return cached data immediately
    account_orm = db.query(AccountInfoORM).filter(
        AccountInfoORM.mode == mode.value
    ).first()

    # Fallback: try by account_id pattern
    if not account_orm:
        account_id = f"{mode.value.lower()}_account_001"
        account_orm = db.query(AccountInfoORM).filter_by(account_id=account_id).first()

    if account_orm:
        logger.info(f"Returning cached account info from database (updated: {account_orm.updated_at})")

        # Trigger background refresh from eToro if data is stale (>60s old)
        if account_orm.updated_at:
            age_seconds = (datetime.now() - account_orm.updated_at).total_seconds()
            if age_seconds > 60:
                _refresh_account_from_etoro(mode, config)

        return AccountInfoResponse(**account_orm.to_dict())

    # No cached data — must fetch from eToro (first-time setup)
    etoro_client = get_etoro_client(mode, config)
    if etoro_client:
        try:
            account_info = etoro_client.get_account_info()

            account_orm = AccountInfoORM(
                account_id=account_info.account_id,
                mode=account_info.mode,
                balance=account_info.balance,
                equity=account_info.equity,
                buying_power=account_info.buying_power,
                margin_used=account_info.margin_used,
                margin_available=account_info.margin_available,
                daily_pnl=account_info.daily_pnl,
                total_pnl=account_info.total_pnl,
                positions_count=account_info.positions_count,
                updated_at=account_info.updated_at
            )
            db.add(account_orm)
            db.commit()
            db.refresh(account_orm)

            logger.info(f"Account info fetched from eToro (first time) and saved to database")
            return AccountInfoResponse(**account_orm.to_dict())

        except Exception as e:
            logger.error(f"Failed to fetch account info from eToro: {e}")

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Account data unavailable: no cached data and eToro API unavailable for {mode.value} mode"
    )



@router.get("/positions", response_model=PositionsResponse)
async def get_positions(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Get all open positions from database.
    
    Returns positions directly from database without calling eToro API.
    Positions are kept up-to-date by the background order monitor sync.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        config: Configuration instance
        
    Returns:
        List of open positions with current prices and P&L from database,
        plus count of pending orders (positions waiting for market open),
        and market open status
        
    Validates: Requirement 11.2
    """
    logger.info(f"Getting positions for {mode.value} mode, user {username}")
    
    # Get all open positions from database (updated by background sync)
    position_orms = db.query(PositionORM).filter(
        PositionORM.closed_at.is_(None)
    ).all()
    
    logger.info(f"Found {len(position_orms)} open positions in database")
    
    # Get pending orders count (orders waiting for market open)
    from src.models.orm import OrderORM
    from src.models.enums import OrderStatus
    
    pending_orders_count = db.query(OrderORM).filter(
        OrderORM.status == OrderStatus.PENDING
    ).count()
    
    logger.info(f"Found {pending_orders_count} pending orders (positions waiting for market open)")
    
    # Check if market is open
    from src.data.market_hours_manager import MarketHoursManager, AssetClass
    market_hours = MarketHoursManager()
    market_open = market_hours.is_market_open(AssetClass.STOCK)
    
    logger.info(f"Market status: {'OPEN' if market_open else 'CLOSED'}")
    
    # Return all positions directly from database (updated by background sync)
    # Bulk-fetch strategy names
    strategy_ids = list(set(p.strategy_id for p in position_orms if p.strategy_id))
    strategy_name_map = {}
    if strategy_ids:
        from src.models.orm import StrategyORM
        strats = db.query(StrategyORM.id, StrategyORM.name).filter(StrategyORM.id.in_(strategy_ids)).all()
        strategy_name_map = {s.id: s.name for s in strats}
    
    position_responses = []
    for pos in position_orms:
        d = pos.to_dict()
        d['strategy_name'] = strategy_name_map.get(pos.strategy_id)
        position_responses.append(PositionResponse(**d))
    
    logger.info(f"Returning {len(position_responses)} positions + {pending_orders_count} pending")
    return PositionsResponse(
        positions=position_responses,
        total_count=len(position_responses),
        pending_count=pending_orders_count,
        market_open=market_open
    )


@router.get("/positions/closed", response_model=PositionsResponse)
async def get_closed_positions(
    mode: TradingMode,
    limit: int = 100,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get closed positions history.
    
    Fetches positions that have been closed (closed_at is not null).
    Returns most recent closed positions first.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        limit: Maximum number of positions to return (default: 100)
        username: Current authenticated user
        db: Database session
        
    Returns:
        List of closed positions with realized P&L
        
    Validates: Requirement 11.2
    """
    logger.info(f"Getting closed positions for {mode.value} mode, user {username}, limit {limit}")
    
    # Get closed positions from database (closed_at is not null)
    position_orms = db.query(PositionORM).filter(
        PositionORM.closed_at.isnot(None)
    ).order_by(
        PositionORM.closed_at.desc()
    ).limit(limit).all()
    
    logger.info(f"Found {len(position_orms)} closed positions in database")
    
    # Return all closed positions with strategy names
    strategy_ids = list(set(p.strategy_id for p in position_orms if p.strategy_id))
    strategy_name_map = {}
    if strategy_ids:
        from src.models.orm import StrategyORM
        strats = db.query(StrategyORM.id, StrategyORM.name).filter(StrategyORM.id.in_(strategy_ids)).all()
        strategy_name_map = {s.id: s.name for s in strats}
    
    position_responses = []
    for pos in position_orms:
        d = pos.to_dict()
        d['strategy_name'] = strategy_name_map.get(pos.strategy_id, pos.strategy_id)
        
        # Determine exit reason from closure_reason or infer from price vs SL/TP
        exit_reason = getattr(pos, 'closure_reason', None)
        if not exit_reason:
            entry = pos.entry_price or 0
            close_price = pos.current_price or 0
            sl = pos.stop_loss or 0
            tp = pos.take_profit or 0
            side_str = str(pos.side).upper() if pos.side else 'LONG'
            is_long = 'LONG' in side_str or 'BUY' in side_str
            
            if tp > 0:
                if is_long and close_price >= tp * 0.995:
                    exit_reason = "Take Profit hit"
                elif not is_long and close_price <= tp * 1.005:
                    exit_reason = "Take Profit hit"
            if not exit_reason and sl > 0:
                if is_long and close_price <= sl * 1.005:
                    exit_reason = "Stop Loss hit"
                elif not is_long and close_price >= sl * 0.995:
                    exit_reason = "Stop Loss hit"
            if not exit_reason:
                exit_reason = "Closed"
        
        d['closure_reason'] = exit_reason
        position_responses.append(PositionResponse(**d))
    
    logger.info(f"Returning {len(position_responses)} closed positions")
    return PositionsResponse(
        positions=position_responses,
        total_count=len(position_responses)
    )


@router.get("/positions/pending-open", response_model=PositionsResponse)
async def get_pending_open_positions(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get all pending positions (orders waiting for market open).
    
    These are PENDING orders that will become positions when the market opens.
    Useful for showing "pending positions" when orders are placed after market close.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        
    Returns:
        List of pending positions (as PositionResponse with pending status)
    """
    logger.info(f"Getting pending open positions for {mode.value} mode, user {username}")
    
    from src.models.orm import OrderORM
    from src.models.enums import OrderStatus, OrderSide
    
    # Get PENDING orders (orders submitted but not yet filled)
    pending_orders = db.query(OrderORM).filter(
        OrderORM.status == OrderStatus.PENDING
    ).all()
    
    # Convert pending orders to position-like responses
    position_responses = []
    for order in pending_orders:
        # Create a position-like response for pending orders
        position_dict = {
            "id": f"pending_{order.id}",  # Prefix to distinguish from real positions
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "side": order.side.value if order.side == OrderSide.BUY else "LONG",  # Convert BUY to LONG
            "quantity": order.quantity,
            "entry_price": order.price or order.expected_price or 0.0,
            "current_price": order.price or order.expected_price or 0.0,
            "unrealized_pnl": 0.0,  # No P&L yet
            "unrealized_pnl_percent": 0.0,
            "realized_pnl": 0.0,
            "stop_loss": order.stop_price,
            "take_profit": order.take_profit_price,
            "opened_at": order.submitted_at.isoformat() if order.submitted_at else datetime.now().isoformat(),
            "closed_at": None,
            "etoro_position_id": order.etoro_order_id or "pending",
        }
        position_responses.append(PositionResponse(**position_dict))
    
    logger.info(f"Found {len(position_responses)} pending open positions")
    
    return PositionsResponse(
        positions=position_responses,
        total_count=len(position_responses)
    )


@router.get("/positions/pending-closures", response_model=PositionsResponse)
async def get_pending_closures(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get all positions pending closure approval.
    
    These are positions from retired strategies that need user approval to close.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        
    Returns:
        List of positions pending closure
    """
    logger.info(f"Getting pending closures for {mode.value} mode, user {username}")
    
    # Get positions marked for closure
    positions = db.query(PositionORM).filter(
        PositionORM.pending_closure == True,
        PositionORM.closed_at.is_(None)
    ).all()
    
    position_responses = []
    if positions:
        sids = list(set(p.strategy_id for p in positions if p.strategy_id))
        smap = {}
        if sids:
            from src.models.orm import StrategyORM
            smap = {s.id: s.name for s in db.query(StrategyORM.id, StrategyORM.name).filter(StrategyORM.id.in_(sids)).all()}
        for pos in positions:
            d = pos.to_dict()
            d['strategy_name'] = smap.get(pos.strategy_id)
            position_responses.append(PositionResponse(**d))
    
    return PositionsResponse(
        positions=position_responses,
        total_count=len(position_responses)
    )


@router.get("/positions/fundamental-alerts")
async def get_fundamental_alerts(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get positions flagged by fundamental exit monitoring.
    
    Returns positions with pending_closure=True where closure_reason contains
    fundamental-related keywords (earnings, revenue, sector, fundamental).
    """
    logger.info(f"Getting fundamental alerts for {mode.value} mode, user {username}")
    
    try:
        # Get positions flagged by fundamental monitoring
        fundamental_keywords = ["fundamental", "earnings", "revenue", "sector"]
        
        flagged_positions = db.query(PositionORM).filter(
            PositionORM.pending_closure == True,
            PositionORM.closed_at.is_(None),
            PositionORM.closure_reason.isnot(None)
        ).all()
        
        # Filter to only fundamental-related closure reasons
        alerts = []
        for pos in flagged_positions:
            reason_lower = (pos.closure_reason or "").lower()
            if any(kw in reason_lower for kw in fundamental_keywords):
                pos_dict = pos.to_dict()
                # Parse the closure reason to extract structured data
                pos_dict["flag_reason"] = _parse_flag_reason(pos.closure_reason)
                pos_dict["flag_timestamp"] = pos.opened_at.isoformat() if pos.opened_at else None
                pos_dict["fundamental_detail"] = _extract_fundamental_detail(pos.closure_reason)
                alerts.append(pos_dict)
        
        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts)
        }
    except Exception as e:
        logger.error(f"Failed to get fundamental alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get fundamental alerts: {str(e)}"
        )


@router.get("/positions/{position_id}", response_model=PositionResponse)
async def get_position(
    position_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get specific position details.
    
    Args:
        position_id: Position ID
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        
    Returns:
        Position details
        
    Raises:
        HTTPException: If position not found
        
    Validates: Requirement 11.2
    """
    logger.info(f"Getting position {position_id} for {mode.value} mode, user {username}")
    
    # Get from database
    position_orm = db.query(PositionORM).filter_by(id=position_id).first()
    
    if not position_orm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found"
        )
    
    return PositionResponse(**position_orm.to_dict())


@router.post("/positions/{position_id}/approve-closure")
async def approve_position_closure(
    position_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Approve and execute closure of a pending position.
    
    Args:
        position_id: Position ID to close
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        config: Configuration instance
        
    Returns:
        Success response
    """
    logger.info(f"Approving closure for position {position_id}, user {username}")
    
    # Get position
    position_orm = db.query(PositionORM).filter_by(id=position_id).first()
    
    if not position_orm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found"
        )
    
    if not position_orm.pending_closure:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Position {position_id} is not pending closure"
        )
    
    # Get eToro client
    etoro_client = get_etoro_client(mode, config)
    
    if not etoro_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eToro API not configured"
        )
    
    try:
        # Close position via eToro API
        from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
        instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(position_orm.symbol)
        etoro_client.close_position(position_orm.etoro_position_id, instrument_id=instrument_id)
        
        # Update position in database
        _finalize_position_close(position_orm)
        db.commit()
        
        logger.info(f"Position {position_id} closed successfully")
        
        return {
            "success": True,
            "message": "Position closed successfully",
            "position_id": position_id
        }
    
    except Exception as e:
        logger.error(f"Failed to close position {position_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close position: {str(e)}"
        )


class BulkClosureRequest(BaseModel):
    """Request body for bulk position closure approval."""
    position_ids: List[str]


@router.post("/positions/approve-closures-bulk")
async def approve_bulk_closures(
    request: BulkClosureRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Approve and execute closure of multiple pending positions.
    
    Args:
        request: Request body containing position_ids list
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        config: Configuration instance
        
    Returns:
        Success response with counts
    """
    position_ids = request.position_ids
    logger.info(f"Approving bulk closures for {len(position_ids)} positions, user {username}")
    
    # Get eToro client
    etoro_client = get_etoro_client(mode, config)
    
    if not etoro_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eToro API not configured"
        )
    
    success_count = 0
    fail_count = 0
    errors = []
    
    for position_id in position_ids:
        try:
            position_orm = db.query(PositionORM).filter_by(id=position_id).first()
            
            if not position_orm:
                errors.append(f"Position {position_id} not found")
                fail_count += 1
                continue
            
            if not position_orm.pending_closure:
                errors.append(f"Position {position_id} is not pending closure")
                fail_count += 1
                continue
            
            # If monitoring service already submitted a close order, just mark as closed in DB
            if position_orm.close_order_id:
                logger.info(f"Position {position_id} ({position_orm.symbol}) already has close order {position_orm.close_order_id} — marking as closed")
                _finalize_position_close(position_orm)
                success_count += 1
                continue
            
            # Try to close via eToro API
            try:
                from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
                instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(position_orm.symbol)
                etoro_client.close_position(position_orm.etoro_position_id, instrument_id=instrument_id)
                _finalize_position_close(position_orm)
                success_count += 1
            except CircuitBreakerOpen:
                # Circuit breaker tripped — mark for monitoring service to handle
                logger.warning(f"Circuit breaker open for position {position_id} ({position_orm.symbol}) — monitoring service will retry")
                # Don't count as failure — it will be retried
                errors.append(f"Position {position_id} ({position_orm.symbol}): circuit breaker open, will retry")
                fail_count += 1
            except EToroAPIError as e:
                error_msg = str(e).lower()
                # If position is already closed on eToro (404, not found, etc.), mark as closed
                if "not found" in error_msg or "404" in error_msg or "already closed" in error_msg or "does not exist" in error_msg:
                    logger.info(f"Position {position_id} ({position_orm.symbol}) appears already closed on eToro — marking as closed")
                    _finalize_position_close(position_orm)
                    success_count += 1
                else:
                    logger.error(f"Failed to close position {position_id}: {e}")
                    errors.append(f"Position {position_id}: {str(e)}")
                    fail_count += 1
            
        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            errors.append(f"Position {position_id}: {str(e)}")
            fail_count += 1
    
    # Commit all successful closures
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit bulk closures: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit closures: {str(e)}"
        )
    
    logger.info(f"Bulk closure complete: {success_count} succeeded, {fail_count} failed")
    
    return {
        "success": True,
        "message": f"Closed {success_count} positions, {fail_count} failed",
        "success_count": success_count,
        "fail_count": fail_count,
        "errors": errors if errors else None
    }


@router.post("/positions/{position_id}/dismiss-closure")
async def dismiss_position_closure(
    position_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Dismiss pending closure flag on a position, keeping it open.
    
    Args:
        position_id: Position ID to unflag
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        
    Returns:
        Success response
    """
    logger.info(f"Dismissing closure for position {position_id}, user {username}")
    
    position_orm = db.query(PositionORM).filter_by(id=position_id).first()
    
    if not position_orm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found"
        )
    
    if not position_orm.pending_closure:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Position {position_id} is not pending closure"
        )
    
    try:
        position_orm.pending_closure = False
        position_orm.closure_reason = None
        position_orm.close_attempts = 0
        position_orm.close_order_id = None
        db.commit()
        
        logger.info(f"Position {position_id} closure dismissed")
        
        return {
            "success": True,
            "message": "Closure dismissed — position will remain open",
            "position_id": position_id
        }
    except Exception as e:
        logger.error(f"Failed to dismiss closure for position {position_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dismiss closure: {str(e)}"
        )


# ============================================================================
# Position Sync and Bulk Close Endpoints (Task 11.10.2)
# ============================================================================

class ClosePositionsRequest(BaseModel):
    """Request model for closing multiple positions."""
    position_ids: List[str]


@router.post("/positions/sync")
async def sync_positions(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Force sync positions with eToro. Fetches fresh position data from eToro
    and updates the database.
    """
    logger.info(f"Syncing positions with eToro for {mode.value} mode, user {username}")
    
    etoro_client = get_etoro_client(mode, config)
    if not etoro_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eToro API not configured"
        )
    
    try:
        # Fetch positions from eToro
        etoro_positions = etoro_client.get_positions()
        
        synced_count = 0
        new_count = 0
        closed_count = 0
        
        etoro_position_ids = set()
        
        for ep in etoro_positions:
            etoro_pos_id = str(ep.etoro_position_id or ep.id or "")
            etoro_position_ids.add(etoro_pos_id)
            
            # Check if position exists in DB
            existing = db.query(PositionORM).filter_by(etoro_position_id=etoro_pos_id).first()
            
            if existing:
                # Update current price if available
                current_price = ep.current_price
                if current_price:
                    existing.current_price = float(current_price)
                    # Recalculate P&L
                    # quantity is dollars invested (eToro demo), not shares
                    # P&L = invested_amount * price_change_pct
                    if existing.entry_price and existing.entry_price > 0:
                        if existing.side == PositionSide.LONG:
                            existing.unrealized_pnl = existing.quantity * (float(current_price) - existing.entry_price) / existing.entry_price
                        else:
                            existing.unrealized_pnl = existing.quantity * (existing.entry_price - float(current_price)) / existing.entry_price
                        existing.unrealized_pnl_percent = (existing.unrealized_pnl / existing.quantity) * 100 if existing.quantity > 0 else 0
                synced_count += 1
            else:
                # New position found on eToro but not in DB — create it
                from src.utils.symbol_normalizer import normalize_symbol
                
                normalized_symbol = normalize_symbol(ep.symbol)
                
                # Check if a position already exists for this symbol (different etoro_position_id)
                existing_by_symbol = db.query(PositionORM).filter(
                    PositionORM.symbol == normalized_symbol,
                    PositionORM.closed_at.is_(None),
                ).first()
                
                if existing_by_symbol:
                    # Update existing position's etoro_position_id
                    existing_by_symbol.etoro_position_id = etoro_pos_id
                    existing_by_symbol.current_price = float(ep.current_price) if ep.current_price else existing_by_symbol.current_price
                    logger.info(f"Updated existing {normalized_symbol} position with new eToro ID {etoro_pos_id}")
                    synced_count += 1
                else:
                    # Create new position
                    new_pos = PositionORM(
                        id=str(uuid.uuid4()),
                        strategy_id=getattr(ep, 'strategy_id', 'etoro_position') or 'etoro_position',
                        symbol=normalized_symbol,
                        side=ep.side,
                        quantity=ep.quantity,
                        entry_price=float(ep.entry_price),
                        current_price=float(ep.current_price) if ep.current_price else float(ep.entry_price),
                        unrealized_pnl=float(ep.unrealized_pnl) if ep.unrealized_pnl else 0.0,
                        realized_pnl=0.0,
                        opened_at=ep.opened_at or datetime.now(),
                        etoro_position_id=etoro_pos_id,
                        stop_loss=ep.stop_loss,
                        take_profit=ep.take_profit,
                    )
                    db.add(new_pos)
                    new_count += 1
                    logger.info(f"Created new position for {normalized_symbol} (eToro ID: {etoro_pos_id})")
        
        # Check for positions in DB that are no longer on eToro
        open_positions = db.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()
        
        for pos in open_positions:
            if pos.etoro_position_id and pos.etoro_position_id not in etoro_position_ids:
                _finalize_position_close(pos)
                closed_count += 1
                logger.info(f"Position {pos.id} ({pos.symbol}) no longer on eToro — marking closed")
        
        db.commit()
        
        logger.info(f"Position sync complete: {synced_count} synced, {new_count} new, {closed_count} closed")
        
        return {
            "success": True,
            "message": f"Synced {synced_count} positions, {new_count} new found, {closed_count} marked closed",
            "synced_count": synced_count,
            "new_count": new_count,
            "closed_count": closed_count
        }
        
    except Exception as e:
        logger.error(f"Failed to sync positions: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync positions: {str(e)}"
        )


@router.post("/positions/close")
async def close_positions(
    request: ClosePositionsRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Close selected positions by ID. Cancels any pending orders on the position
    first, then submits close orders to eToro.
    Works regardless of position status (open, pending, partial).
    """
    logger.info(f"Closing {len(request.position_ids)} positions, user {username}")
    
    etoro_client = get_etoro_client(mode, config)
    if not etoro_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eToro API not configured"
        )
    
    from src.models.orm import OrderORM
    from src.models.enums import OrderStatus
    
    success_count = 0
    fail_count = 0
    errors = []
    
    for position_id in request.position_ids:
        try:
            position_orm = db.query(PositionORM).filter_by(id=position_id).first()
            
            if not position_orm:
                errors.append(f"Position {position_id} not found")
                fail_count += 1
                continue
            
            if position_orm.closed_at:
                errors.append(f"Position {position_id} already closed")
                fail_count += 1
                continue
            
            # Cancel any pending orders for this position's symbol/strategy
            pending_orders = db.query(OrderORM).filter(
                OrderORM.strategy_id == position_orm.strategy_id,
                OrderORM.symbol == position_orm.symbol,
                OrderORM.status == OrderStatus.PENDING
            ).all()
            
            for order in pending_orders:
                try:
                    if order.etoro_order_id:
                        etoro_client.cancel_order(order.etoro_order_id)
                    order.status = OrderStatus.CANCELLED
                    logger.info(f"Cancelled pending order {order.id} for position {position_id}")
                except Exception as cancel_err:
                    logger.warning(f"Failed to cancel order {order.id}: {cancel_err}")
            
            # Close position via eToro API
            from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
            instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(position_orm.symbol)
            etoro_client.close_position(position_orm.etoro_position_id, instrument_id=instrument_id)
            
            # Update position in database
            _finalize_position_close(position_orm)
            success_count += 1
            
            logger.info(f"Position {position_id} ({position_orm.symbol}) closed successfully")
            
            # Log to trade journal for analytics
            try:
                from src.analytics.trade_journal import TradeJournal
                from src.models.database import get_database
                journal = TradeJournal(get_database())
                journal.log_exit(
                    trade_id=str(position_orm.id),
                    exit_time=position_orm.closed_at,
                    exit_price=position_orm.current_price,
                    exit_reason="manual_close",
                    symbol=position_orm.symbol,
                )
            except Exception as journal_err:
                logger.debug(f"Could not log to trade journal: {journal_err}")
            
        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            errors.append(f"Position {position_id}: {str(e)}")
            fail_count += 1
    
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit position closures: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit closures: {str(e)}"
        )
    
    return {
        "success": True,
        "message": f"Closed {success_count} positions, {fail_count} failed",
        "success_count": success_count,
        "fail_count": fail_count,
        "errors": errors if errors else None
    }


@router.post("/positions/close-all")
async def close_all_positions(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Close all open positions. Cancels pending orders first, then closes all positions.
    eToro terminology: "Close All Trades".
    """
    logger.info(f"Closing ALL positions for {mode.value} mode, user {username}")
    
    etoro_client = get_etoro_client(mode, config)
    if not etoro_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="eToro API not configured"
        )
    
    from src.models.orm import OrderORM
    from src.models.enums import OrderStatus
    
    # Get all open positions
    open_positions = db.query(PositionORM).filter(
        PositionORM.closed_at.is_(None)
    ).all()
    
    if not open_positions:
        return {
            "success": True,
            "message": "No open positions to close",
            "success_count": 0,
            "fail_count": 0
        }
    
    # Cancel all pending orders first
    pending_orders = db.query(OrderORM).filter(
        OrderORM.status == OrderStatus.PENDING
    ).all()
    
    cancelled_orders = 0
    for order in pending_orders:
        try:
            if order.etoro_order_id:
                etoro_client.cancel_order(order.etoro_order_id)
            order.status = OrderStatus.CANCELLED
            cancelled_orders += 1
        except Exception as e:
            logger.warning(f"Failed to cancel order {order.id}: {e}")
    
    success_count = 0
    fail_count = 0
    errors = []
    
    for position_orm in open_positions:
        try:
            from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
            instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(position_orm.symbol)
            etoro_client.close_position(position_orm.etoro_position_id, instrument_id=instrument_id)
            _finalize_position_close(position_orm)
            success_count += 1
            
            # Log to trade journal for analytics
            try:
                from src.analytics.trade_journal import TradeJournal
                from src.models.database import get_database
                journal = TradeJournal(get_database())
                journal.log_exit(
                    trade_id=str(position_orm.id),
                    exit_time=position_orm.closed_at,
                    exit_price=position_orm.current_price,
                    exit_reason="manual_close_all",
                    symbol=position_orm.symbol,
                )
            except Exception as journal_err:
                logger.debug(f"Could not log to trade journal: {journal_err}")
        except Exception as e:
            logger.error(f"Failed to close position {position_orm.id} ({position_orm.symbol}): {e}")
            errors.append(f"{position_orm.symbol}: {str(e)}")
            fail_count += 1
    
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit close-all: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit closures: {str(e)}"
        )
    
    logger.info(f"Close all complete: {success_count} closed, {fail_count} failed, {cancelled_orders} orders cancelled")
    
    return {
        "success": True,
        "message": f"Closed {success_count} of {len(open_positions)} positions ({cancelled_orders} orders cancelled)",
        "success_count": success_count,
        "fail_count": fail_count,
        "cancelled_orders": cancelled_orders,
        "errors": errors if errors else None
    }


# ============================================================================
# Fundamental Alerts Endpoints (Task 11.10.3)
# ============================================================================

@router.post("/positions/{position_id}/dismiss-alert")
async def dismiss_fundamental_alert(
    position_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Dismiss a fundamental alert for a position, removing the pending_closure flag.
    User disagrees with the fundamental signal and wants to keep the position open.
    """
    logger.info(f"Dismissing fundamental alert for position {position_id}, user {username}")
    
    position_orm = db.query(PositionORM).filter_by(id=position_id).first()
    
    if not position_orm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Position {position_id} not found"
        )
    
    if not position_orm.pending_closure:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Position {position_id} has no active alert"
        )
    
    try:
        position_orm.pending_closure = False
        position_orm.closure_reason = None
        position_orm.close_attempts = 0
        position_orm.close_order_id = None
        db.commit()
        
        logger.info(f"Fundamental alert dismissed for position {position_id}")
        
        return {
            "success": True,
            "message": "Alert dismissed — position will remain open",
            "position_id": position_id
        }
    except Exception as e:
        logger.error(f"Failed to dismiss alert for position {position_id}: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dismiss alert: {str(e)}"
        )


async def trigger_fundamental_check(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Trigger an on-demand fundamental exit check.
    Checks open stock positions against FMP fundamental data.
    """
    logger.info(f"Manual fundamental check triggered by user {username}")

    try:
        from src.data.fundamental_data_provider import FundamentalDataProvider, get_fundamental_data_provider
        from src.risk.risk_manager import get_symbol_sector

        # Get open positions (stocks only)
        open_positions = db.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()

        checked = 0
        flagged = 0
        details = []

        # Initialize FMP provider
        try:
            fmp_provider = get_fundamental_data_provider()
        except Exception as e:
            logger.warning(f"Could not initialize FundamentalDataProvider: {e}")
            return {
                "success": True,
                "message": "Fundamental check skipped — FMP provider not available",
                "checked": 0,
                "flagged": 0,
                "details": {"error": str(e)}
            }

        for pos in open_positions:
            # Skip non-stock positions
            sector = get_symbol_sector(pos.symbol)
            if sector in ("Forex", "Crypto", "Indices", "Commodities"):
                continue

            checked += 1

            try:
                # Get fundamental data from FMP
                fund_data = fmp_provider.get_fundamental_data(pos.symbol)
                if not fund_data:
                    continue

                reasons = []

                # Check earnings surprise
                eps_surprise = fund_data.get("earnings_surprise_pct", 0)
                if eps_surprise and eps_surprise < -5:
                    reasons.append(f"Earnings miss: surprise {eps_surprise:.1f}%")

                # Check revenue growth
                rev_growth = fund_data.get("revenue_growth", 0)
                if rev_growth and rev_growth < 0:
                    reasons.append(f"Revenue decline: growth {rev_growth:.1f}%")

                if reasons:
                    # Flag position for closure
                    reason_str = f"Fundamental exit: {'; '.join(reasons)}"
                    if not pos.pending_closure:
                        pos.pending_closure = True
                        pos.closure_reason = reason_str
                        flagged += 1
                        details.append({"symbol": pos.symbol, "reason": reason_str})
                        logger.info(f"Flagged {pos.symbol} for fundamental exit: {reason_str}")

            except Exception as e:
                logger.warning(f"Error checking fundamentals for {pos.symbol}: {e}")

        db.commit()

        return {
            "success": True,
            "message": f"Fundamental check complete: {checked} checked, {flagged} flagged",
            "checked": checked,
            "flagged": flagged,
            "details": details
        }
    except Exception as e:
        logger.error(f"Failed to trigger fundamental check: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger fundamental check: {str(e)}"
        )


def _parse_flag_reason(closure_reason: str) -> str:
    """Extract a human-readable flag reason category from the closure reason string."""
    if not closure_reason:
        return "Unknown"
    reason_lower = closure_reason.lower()
    if "earnings miss" in reason_lower or "earnings" in reason_lower:
        return "Earnings Miss"
    elif "revenue decline" in reason_lower or "revenue" in reason_lower:
        return "Revenue Decline"
    elif "sector rotation" in reason_lower or "sector" in reason_lower:
        return "Sector Rotation"
    elif "fundamental" in reason_lower:
        return "Fundamental Exit"
    return "Other"


def _extract_fundamental_detail(closure_reason: str) -> str:
    """Extract the specific fundamental data detail from the closure reason."""
    if not closure_reason:
        return ""
    # The closure_reason format is: "Fundamental exit: Earnings miss: surprise -8.2% < -5.0%; Revenue decline: growth -3.5%"
    # Strip the "Fundamental exit: " prefix if present
    detail = closure_reason
    if detail.lower().startswith("fundamental exit: "):
        detail = detail[len("Fundamental exit: "):]
    return detail


# ============================================================================
# Dashboard Summary Endpoint
# ============================================================================

class PnLPeriod(BaseModel):
    """P&L for a specific time period."""
    label: str
    pnl_absolute: float
    pnl_percent: float

class EquityPoint(BaseModel):
    """Single point on the equity curve."""
    date: str
    equity: float
    benchmark: Optional[float] = None

class DrawdownPoint(BaseModel):
    """Single point on the drawdown chart."""
    date: str
    drawdown_pct: float

class SectorExposure(BaseModel):
    """Exposure for a single sector."""
    sector: str
    allocation_pct: float
    pnl: float
    pnl_pct: float
    position_count: int

class MarketRegimeInfo(BaseModel):
    """Current market regime information."""
    current_regime: str
    regime_color: str
    regime_description: str

class AccountHealthScore(BaseModel):
    """Composite account health score."""
    score: int
    drawdown_score: int
    concentration_score: int
    margin_score: int
    diversity_score: int

class QuickStats(BaseModel):
    """Quick stats row data."""
    open_positions: int
    active_strategies: int
    pending_orders: int
    todays_trades: int
    win_rate_30d: float

class DashboardSummaryResponse(BaseModel):
    """Complete dashboard summary response."""
    pnl_periods: List[PnLPeriod]
    equity_curve: List[EquityPoint]
    drawdown_data: List[DrawdownPoint]
    sector_exposure: List[SectorExposure]
    market_regime: MarketRegimeInfo
    health_score: AccountHealthScore
    quick_stats: QuickStats
    account_balance: float
    account_equity: float
    available_cash: float
    total_unrealized_pnl: float = 0.0
    total_invested: float = 0.0


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration),
):
    """
    Get aggregated dashboard summary data in a single call.
    Combines P&L periods, equity curve, drawdown, exposure, regime, health score, and quick stats.
    """
    from datetime import timedelta
    from sqlalchemy import func, and_, or_
    from src.models.orm import (
        StrategyORM, OrderORM
    )
    from src.risk.risk_manager import get_symbol_sector

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    # --- Account Info ---
    account = db.query(AccountInfoORM).filter(
        AccountInfoORM.mode == mode.value
    ).first()
    balance = account.balance if account else 0.0

    # Trigger background refresh if equity looks stale (0 or same as balance)
    stored_equity_val = (account.equity if account else 0.0) or 0.0
    if account and (not stored_equity_val or stored_equity_val == balance):
        _refresh_account_from_etoro(mode, config)

    # --- Open Positions ---
    open_positions = db.query(PositionORM).filter(
        PositionORM.closed_at.is_(None)
    ).all()

    total_unrealized = sum(p.unrealized_pnl or 0 for p in open_positions)
    # Total invested capital = sum of invested_amount (or quantity as fallback for eToro demo where quantity = dollars)
    total_invested = sum(
        getattr(p, 'invested_amount', None) or p.quantity or 0
        for p in open_positions
    )

    # Equity = balance + unrealized P&L (what the account is worth right now)
    # Use stored equity if it looks valid (non-zero and different from balance),
    # otherwise compute from balance + unrealized P&L
    stored_equity = (account.equity if account else 0.0) or 0.0
    if stored_equity and stored_equity != balance:
        equity = stored_equity
    else:
        equity = balance + total_unrealized

    # Available cash: on eToro DEMO, credit IS the available-to-trade amount.
    # eToro DEMO doesn't lock margin — you can deploy the full credit.
    # On LIVE, buying_power reflects actual margin availability.
    if mode == TradingMode.DEMO:
        available_cash = balance  # credit = available to trade on DEMO
    else:
        stored_buying_power = (account.buying_power if account else 0.0) or 0.0
        stored_margin_used = (account.margin_used if account else 0.0) or 0.0
        if stored_margin_used > 0:
            available_cash = max(0.0, balance - stored_margin_used)
        else:
            available_cash = stored_buying_power

    # --- P&L Periods ---
    # Compute period P&L using equity snapshots (most accurate — matches eToro).
    # Today = current_equity - yesterday's closing equity
    # This Week = current_equity - last Sunday's closing equity
    # This Month = current_equity - last day of previous month's closing equity
    # All-Time = eToro's total_pnl (realized + unrealized)
    
    from src.models.orm import EquitySnapshotORM
    
    def get_snapshot_equity(target_date: str) -> float:
        """Get equity from the most recent snapshot on or before target_date."""
        try:
            snapshot = db.query(EquitySnapshotORM).filter(
                EquitySnapshotORM.date <= target_date
            ).order_by(EquitySnapshotORM.date.desc()).first()
            return snapshot.equity if snapshot else 0.0
        except Exception:
            return 0.0
    
    # Get reference equity values from snapshots
    yesterday = (today_start - timedelta(days=1)).strftime("%Y-%m-%d")
    last_sunday = (today_start - timedelta(days=today_start.weekday() + 1)).strftime("%Y-%m-%d")
    last_month_end = (month_start - timedelta(days=1)).strftime("%Y-%m-%d")
    
    yesterday_equity = get_snapshot_equity(yesterday)
    week_start_equity = get_snapshot_equity(last_sunday)
    month_start_equity = get_snapshot_equity(last_month_end)
    
    # Use eToro's total_pnl for All-Time (most accurate)
    etoro_total_pnl = getattr(account, 'total_pnl', None) or 0.0
    
    # Fallback: if no snapshots exist yet, use realized + unrealized
    def get_realized_pnl_since(since: datetime) -> float:
        """Get realized P&L from closed positions since a date."""
        try:
            result = db.query(func.sum(PositionORM.realized_pnl)).filter(
                PositionORM.closed_at.isnot(None),
                PositionORM.closed_at >= since
            ).scalar()
            return float(result) if result else 0.0
        except Exception:
            return 0.0
    
    all_time_realized = 0.0
    try:
        result = db.query(func.sum(PositionORM.realized_pnl)).filter(
            PositionORM.closed_at.isnot(None)
        ).scalar()
        all_time_realized = float(result) if result else 0.0
    except Exception:
        pass
    
    if yesterday_equity > 0:
        # Snapshot-based: accurate equity change
        today_pnl = equity - yesterday_equity
    else:
        # Fallback: realized today + current unrealized (approximate)
        today_pnl = get_realized_pnl_since(today_start) + total_unrealized
    
    if week_start_equity > 0:
        week_pnl = equity - week_start_equity
    else:
        week_pnl = get_realized_pnl_since(week_start) + total_unrealized
    
    if month_start_equity > 0:
        month_pnl = equity - month_start_equity
    else:
        month_pnl = get_realized_pnl_since(month_start) + total_unrealized
    
    all_time_pnl = etoro_total_pnl if etoro_total_pnl != 0 else (all_time_realized + total_unrealized)

    # Percentages calculated vs equity (total account value).
    pct_base = equity if equity > 0 else balance
    pnl_periods = [
        PnLPeriod(label="Today", pnl_absolute=round(today_pnl, 2), pnl_percent=round((today_pnl / pct_base * 100), 2) if pct_base else 0),
        PnLPeriod(label="This Week", pnl_absolute=round(week_pnl, 2), pnl_percent=round((week_pnl / pct_base * 100), 2) if pct_base else 0),
        PnLPeriod(label="This Month", pnl_absolute=round(month_pnl, 2), pnl_percent=round((month_pnl / pct_base * 100), 2) if pct_base else 0),
        PnLPeriod(label="All-Time", pnl_absolute=round(all_time_pnl, 2), pnl_percent=round((all_time_pnl / pct_base * 100), 2) if pct_base else 0),
    ]
    
    # Save today's equity snapshot (updates on every dashboard load for freshness)
    try:
        today_str = now.strftime("%Y-%m-%d")
        existing_snap = db.query(EquitySnapshotORM).filter_by(date=today_str).first()
        if existing_snap:
            existing_snap.equity = equity
            existing_snap.balance = balance
            existing_snap.unrealized_pnl = total_unrealized
            existing_snap.realized_pnl_cumulative = all_time_realized
            existing_snap.positions_count = len(open_positions)
        else:
            db.add(EquitySnapshotORM(
                date=today_str,
                equity=equity,
                balance=balance,
                unrealized_pnl=total_unrealized,
                realized_pnl_cumulative=all_time_realized,
                positions_count=len(open_positions),
                created_at=now,
            ))
        db.commit()
    except Exception:
        db.rollback()

    # --- Equity Curve (prefer snapshots, fallback to realized P&L) ---
    equity_curve = []
    try:
        ninety_days_ago = now - timedelta(days=90)
        ninety_days_str = ninety_days_ago.strftime("%Y-%m-%d")
        
        # Try equity snapshots first (most accurate — includes unrealized)
        snapshots = db.query(EquitySnapshotORM).filter(
            EquitySnapshotORM.date >= ninety_days_str
        ).order_by(EquitySnapshotORM.date.asc()).all()
        
        if snapshots and len(snapshots) > 1:
            # Use snapshot-based equity curve
            for snap in snapshots:
                equity_curve.append(EquityPoint(
                    date=snap.date,
                    equity=round(snap.equity, 2),
                    benchmark=None
                ))
            # Add today's live equity if not already the last snapshot
            today_str = now.strftime("%Y-%m-%d")
            if not snapshots or snapshots[-1].date != today_str:
                equity_curve.append(EquityPoint(
                    date=today_str,
                    equity=round(equity, 2),
                    benchmark=None
                ))
        else:
            # Fallback: build from closed positions (less accurate — realized only)
            closed_positions = db.query(PositionORM).filter(
                PositionORM.closed_at.isnot(None),
                PositionORM.closed_at >= ninety_days_ago
            ).order_by(PositionORM.closed_at.asc()).all()

            daily_pnl_map: dict = {}
            for pos in closed_positions:
                day_key = pos.closed_at.strftime("%Y-%m-%d")
                daily_pnl_map[day_key] = daily_pnl_map.get(day_key, 0) + (pos.realized_pnl or 0)

            running_equity = balance - all_time_pnl
            current_date = ninety_days_ago
            while current_date <= now:
                day_key = current_date.strftime("%Y-%m-%d")
                day_pnl_val = daily_pnl_map.get(day_key, 0)
                running_equity += day_pnl_val
                day_equity = running_equity
                if current_date.strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d"):
                    day_equity += total_unrealized
                equity_curve.append(EquityPoint(
                    date=day_key,
                    equity=round(day_equity, 2),
                    benchmark=None
                ))
                current_date += timedelta(days=1)
    except Exception as e:
        logger.warning(f"Error building equity curve: {e}")

    # --- Drawdown Data ---
    drawdown_data = []
    if equity_curve:
        peak = equity_curve[0].equity
        for point in equity_curve:
            if point.equity > peak:
                peak = point.equity
            dd_pct = ((point.equity - peak) / peak * 100) if peak > 0 else 0
            drawdown_data.append(DrawdownPoint(
                date=point.date,
                drawdown_pct=round(dd_pct, 2)
            ))

    # --- Sector Exposure ---
    sector_data: dict = {}
    total_exposure = 0.0
    for pos in open_positions:
        sector = get_symbol_sector(pos.symbol)
        # Use invested_amount (or quantity as fallback) — NOT entry_price * quantity
        pos_val = getattr(pos, 'invested_amount', None) or abs(pos.quantity or 0)
        total_exposure += pos_val
        if sector not in sector_data:
            sector_data[sector] = {"value": 0.0, "pnl": 0.0, "count": 0}
        sector_data[sector]["value"] += pos_val
        sector_data[sector]["pnl"] += (pos.unrealized_pnl or 0)
        sector_data[sector]["count"] += 1

    sector_exposure = []
    for sector, data in sorted(sector_data.items(), key=lambda x: x[1]["value"], reverse=True):
        alloc_pct = (data["value"] / total_exposure * 100) if total_exposure > 0 else 0
        pnl_pct = (data["pnl"] / data["value"] * 100) if data["value"] > 0 else 0
        sector_exposure.append(SectorExposure(
            sector=sector,
            allocation_pct=round(alloc_pct, 1),
            pnl=round(data["pnl"], 2),
            pnl_pct=round(pnl_pct, 2),
            position_count=data["count"]
        ))

    # --- Market Regime ---
    regime_str = "unknown"
    try:
        # Read persisted market regime from YAML config (set by autonomous cycle)
        import yaml
        from pathlib import Path
        config_path = Path("config/autonomous_trading.yaml")
        if config_path.exists():
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f) or {}
            regime_str = yaml_config.get('market_regime', {}).get('current', 'unknown')
        
        # Fallback: try strategy metadata
        if regime_str == 'unknown':
            latest_strategy = db.query(StrategyORM).filter(
                StrategyORM.status.in_(["DEMO", "LIVE"])
            ).order_by(StrategyORM.activated_at.desc()).first()
            if latest_strategy and latest_strategy.strategy_metadata:
                import json
                meta = json.loads(latest_strategy.strategy_metadata) if isinstance(latest_strategy.strategy_metadata, str) else latest_strategy.strategy_metadata
                regime_str = meta.get("market_regime") or meta.get("activation_regime") or "unknown"
    except Exception:
        pass

    regime_colors = {
        "trending_up": "#22c55e",
        "trending_up_strong": "#16a34a",
        "trending_up_weak": "#4ade80",
        "trending_down": "#ef4444",
        "trending_down_strong": "#dc2626",
        "trending_down_weak": "#f87171",
        "ranging": "#3b82f6",
        "ranging_high_vol": "#f59e0b",
        "ranging_low_vol": "#3b82f6",
    }
    regime_descriptions = {
        "trending_up": "Bullish trend — momentum strategies favored",
        "trending_up_strong": "Strong bullish trend — trend following strategies optimal",
        "trending_up_weak": "Weak bullish trend — cautious momentum positioning",
        "trending_down": "Bearish trend — defensive positioning recommended",
        "trending_down_strong": "Strong bearish trend — short strategies favored",
        "trending_down_weak": "Weak bearish trend — hedging recommended",
        "ranging": "Range-bound market — mean reversion opportunities",
        "ranging_high_vol": "High volatility range — mean reversion with wider stops",
        "ranging_low_vol": "Low volatility range — breakout strategies on standby",
    }

    market_regime = MarketRegimeInfo(
        current_regime=regime_str,
        regime_color=regime_colors.get(regime_str, "#6b7280"),
        regime_description=regime_descriptions.get(regime_str, "Market regime not yet determined")
    )

    # --- Account Health Score ---
    # Drawdown severity (0-25 points)
    max_dd = min(drawdown_data, key=lambda d: d.drawdown_pct).drawdown_pct if drawdown_data else 0
    dd_score = max(0, 25 + int(max_dd))  # max_dd is negative, so adding reduces score

    # Exposure concentration (0-25 points)
    max_sector_pct = max((s.allocation_pct for s in sector_exposure), default=0)
    conc_score = max(0, 25 - int(max(0, max_sector_pct - 25)))  # Penalize if any sector > 25%

    # Margin utilization (0-25 points)
    margin_used = account.margin_used if account and hasattr(account, 'margin_used') else 0
    margin_pct = (margin_used / balance * 100) if balance > 0 else 0
    margin_score = max(0, 25 - int(max(0, margin_pct - 50)))

    # Strategy diversity (0-25 points)
    active_strategies = db.query(StrategyORM).filter(
        StrategyORM.status.in_(["DEMO", "LIVE"])
    ).count()
    diversity_score = min(25, active_strategies * 5)  # 5 points per active strategy, max 25

    total_health = dd_score + conc_score + margin_score + diversity_score

    health_score = AccountHealthScore(
        score=min(100, total_health),
        drawdown_score=dd_score,
        concentration_score=conc_score,
        margin_score=margin_score,
        diversity_score=diversity_score
    )

    # --- Quick Stats ---
    pending_orders = db.query(OrderORM).filter(
        or_(OrderORM.status == "PENDING", OrderORM.status == "SUBMITTED")
    ).count()

    todays_trades = db.query(OrderORM).filter(
        OrderORM.status == "FILLED",
        OrderORM.filled_at >= today_start
    ).count()

    # Win rate last 30 days
    thirty_days_ago = now - timedelta(days=30)
    recent_closed = db.query(PositionORM).filter(
        PositionORM.closed_at.isnot(None),
        PositionORM.closed_at >= thirty_days_ago
    ).all()
    wins = sum(1 for p in recent_closed if (p.realized_pnl or 0) > 0)
    win_rate = (wins / len(recent_closed) * 100) if recent_closed else 0

    quick_stats = QuickStats(
        open_positions=len(open_positions),
        active_strategies=active_strategies,
        pending_orders=pending_orders,
        todays_trades=todays_trades,
        win_rate_30d=round(win_rate, 1)
    )

    return DashboardSummaryResponse(
        pnl_periods=pnl_periods,
        equity_curve=equity_curve,
        drawdown_data=drawdown_data,
        sector_exposure=sector_exposure,
        market_regime=market_regime,
        health_score=health_score,
        quick_stats=quick_stats,
        account_balance=balance,
        account_equity=equity,
        available_cash=available_cash,
        total_unrealized_pnl=total_unrealized,
        total_invested=total_invested,
    )

@router.post("/positions/delete-closed")
async def delete_closed_positions(
    request: dict,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Permanently delete closed position records from the database."""
    position_ids = request.get("position_ids", [])
    if not position_ids:
        raise HTTPException(status_code=400, detail="No position IDs provided")

    try:
        # Only delete positions that are actually closed
        deleted = db.query(PositionORM).filter(
            PositionORM.id.in_(position_ids),
            PositionORM.closed_at.isnot(None),
        ).delete(synchronize_session=False)
        db.commit()
        return {"success": True, "deleted": deleted, "message": f"Deleted {deleted} closed positions"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================================
# Position Detail Endpoint (Task 9.8)
# ============================================================================

class OHLCVPoint(BaseModel):
    """OHLCV price data point."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderAnnotation(BaseModel):
    """Buy/sell order annotation for asset plot."""
    date: str
    side: str  # "BUY" or "SELL"
    price: float
    order_id: Optional[str] = None


class PnLPoint(BaseModel):
    """P&L data point over time."""
    date: str
    pnl: float


class PositionDetailResponse(BaseModel):
    """Position detail response with price history, order annotations, and P&L series."""
    symbol: str
    entry_price: float
    current_price: float
    side: str
    opened_at: Optional[str] = None
    price_history: List[OHLCVPoint]
    order_annotations: List[OrderAnnotation]
    pnl_series: List[PnLPoint]


@router.get("/positions/{symbol}/detail", response_model=PositionDetailResponse)
async def get_position_detail(
    symbol: str,
    mode: TradingMode,
    interval: str = "1d",
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """
    Get detailed position data for a symbol including price history,
    order annotations, and P&L time series.

    Args:
        symbol: Trading symbol (e.g., AAPL, BTCUSD)
        mode: Trading mode (DEMO or LIVE)
        interval: Price data interval — 1d, 4h, 1h (default: 1d)
        username: Current authenticated user
        db: Database session

    Returns:
        PositionDetailResponse with price history, order annotations, and P&L series

    Validates: Requirements 13.1, 13.2, 13.4
    """
    logger.info(f"Fetching position detail for {symbol} in {mode.value} mode, interval={interval}, user {username}")

    # Validate interval
    valid_intervals = {"1d", "4h", "1h"}
    if interval not in valid_intervals:
        interval = "1d"

    # Find the most recent open position for this symbol (or most recent closed)
    position = db.query(PositionORM).filter(
        PositionORM.symbol == symbol,
        PositionORM.closed_at.is_(None),
    ).order_by(PositionORM.opened_at.desc()).first()

    if not position:
        # Fall back to most recent closed position
        position = db.query(PositionORM).filter(
            PositionORM.symbol == symbol,
        ).order_by(PositionORM.opened_at.desc()).first()

    if not position:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No position found for symbol {symbol}",
        )

    opened_at = position.opened_at
    side_str = "BUY" if position.side == PositionSide.LONG else "SELL"

    # --- Price history from historical_price_cache ---
    price_history: List[OHLCVPoint] = []
    try:
        from src.models.orm import HistoricalPriceCacheORM

        price_query = db.query(HistoricalPriceCacheORM).filter(
            HistoricalPriceCacheORM.symbol == symbol,
            HistoricalPriceCacheORM.interval == interval,
        )
        # For intraday intervals, extend lookback to show more context
        if opened_at:
            if interval == "1d":
                price_query = price_query.filter(HistoricalPriceCacheORM.date >= opened_at)
            # For 4h/1h, show last 90 days regardless of position open date
            # (gives enough context for the chart)

        price_rows = price_query.order_by(HistoricalPriceCacheORM.date.asc()).all()

        for row in price_rows:
            price_history.append(OHLCVPoint(
                date=row.date.strftime("%Y-%m-%d") if row.date else "",
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            ))
    except Exception as e:
        logger.warning(f"Could not load price history for {symbol}: {e}")

    # --- Order annotations from orders table ---
    order_annotations: List[OrderAnnotation] = []
    try:
        from src.models.orm import OrderORM
        from src.models.enums import OrderStatus

        orders = db.query(OrderORM).filter(
            OrderORM.symbol == symbol,
            OrderORM.status.in_([OrderStatus.FILLED.value, "FILLED"]),
        ).order_by(OrderORM.filled_at.asc()).all()

        for order in orders:
            if order.filled_at and order.filled_price:
                order_side = "BUY" if str(order.side).upper() in ("BUY", "LONG") else "SELL"
                # Handle _EnumValue wrapper
                side_val = order.side.value if hasattr(order.side, 'value') else str(order.side)
                if side_val.upper() in ("BUY", "LONG"):
                    order_side = "BUY"
                else:
                    order_side = "SELL"

                order_annotations.append(OrderAnnotation(
                    date=order.filled_at.strftime("%Y-%m-%d") if order.filled_at else "",
                    side=order_side,
                    price=order.filled_price,
                    order_id=order.id,
                ))
    except Exception as e:
        logger.warning(f"Could not load order annotations for {symbol}: {e}")

    # --- P&L series ---
    # Compute daily P&L from price history relative to entry price
    pnl_series: List[PnLPoint] = []
    entry_price = position.entry_price
    invested = position.invested_amount or abs(position.quantity) or 0
    is_short = position.side == PositionSide.SHORT

    for ph in price_history:
        if entry_price and entry_price > 0 and invested > 0:
            if is_short:
                pct_move = (entry_price - ph.close) / entry_price
            else:
                pct_move = (ph.close - entry_price) / entry_price
            pnl = invested * pct_move
        else:
            pnl = 0.0
        pnl_series.append(PnLPoint(date=ph.date, pnl=round(pnl, 2)))

    return PositionDetailResponse(
        symbol=symbol,
        entry_price=position.entry_price,
        current_price=position.current_price,
        side=side_str,
        opened_at=position.opened_at.isoformat() if position.opened_at else None,
        price_history=price_history,
        order_annotations=order_annotations,
        pnl_series=pnl_series,
    )
