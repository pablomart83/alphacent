"""
Order endpoints for AlphaCent Trading Platform.

Provides endpoints for managing orders.
Validates: Requirement 11.4
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.models.enums import TradingMode, OrderSide, OrderType, OrderStatus
from src.api.dependencies import get_current_user, get_db_session, get_configuration
from src.models.orm import OrderORM
from src.core.config import Configuration
from src.api.etoro_client import EToroAPIClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])


def get_etoro_client(mode: TradingMode, config: Configuration) -> Optional[EToroAPIClient]:
    """Get eToro client with credentials."""
    try:
        credentials = config.load_credentials(mode)
        if credentials and credentials.get("public_key") and credentials.get("user_key"):
            return EToroAPIClient(
                public_key=credentials["public_key"],
                user_key=credentials["user_key"],
                mode=mode
            )
    except Exception as e:
        logger.warning(f"Could not initialize eToro client: {e}")
    return None


class OrderResponse(BaseModel):
    """Order response model."""
    id: str
    strategy_id: str
    strategy_name: Optional[str] = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    filled_at: Optional[str] = None
    filled_price: Optional[float] = None
    filled_quantity: Optional[float] = None
    etoro_order_id: Optional[str] = None
    # Execution quality fields
    expected_price: Optional[float] = None
    slippage: Optional[float] = None
    fill_time_seconds: Optional[float] = None
    order_action: Optional[str] = None  # 'entry', 'close', or 'retirement'


class OrdersResponse(BaseModel):
    """Orders list response model."""
    orders: List[OrderResponse]
    total_count: int


class PlaceOrderRequest(BaseModel):
    """Place order request model."""
    strategy_id: str
    symbol: str = Field(..., min_length=1)
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(..., gt=0)
    price: Optional[float] = Field(None, gt=0)
    stop_price: Optional[float] = Field(None, gt=0)


class PlaceOrderResponse(BaseModel):
    """Place order response model."""
    success: bool
    message: str
    order_id: str


class CancelOrderResponse(BaseModel):
    """Cancel order response model."""
    success: bool
    message: str
    order_id: str


@router.get("", response_model=OrdersResponse)
async def get_orders(
    mode: TradingMode,
    status_filter: Optional[OrderStatus] = None,
    limit: int = 0,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Get all orders from database.
    
    Database is kept fresh by MonitoringService running 24/7.
    No eToro API calls needed - just query the database.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        status_filter: Optional status filter
        limit: Maximum number of orders to return
        username: Current authenticated user
        session: Database session
        config: Configuration instance
        
    Returns:
        List of orders with current status from database
        
    Validates: Requirement 11.4
    """
    logger.info(f"Getting orders for {mode.value} mode, user {username}")
    
    # Query orders from database (MonitoringService keeps it fresh)
    query = session.query(OrderORM)
    
    # Apply status filter if provided
    if status_filter:
        query = query.filter(OrderORM.status == status_filter)
    
    # Get total count before applying limit
    total_count = query.count()

    # Apply ordering; only apply limit when explicitly requested
    orders_query = query.order_by(OrderORM.submitted_at.desc())
    orders = (orders_query.limit(limit).all() if limit and limit > 0 else orders_query.all())
    
    # Convert ORM models to response models
    order_responses = []
    # Bulk-fetch strategy names for all orders
    strategy_ids = list(set(o.strategy_id for o in orders if o.strategy_id))
    from src.models.orm import StrategyORM
    strategy_name_map = {}
    if strategy_ids:
        strats = session.query(StrategyORM.id, StrategyORM.name).filter(StrategyORM.id.in_(strategy_ids)).all()
        strategy_name_map = {s.id: s.name for s in strats}
    
    for order in orders:
        order_dict = order.to_dict()
        # Fallback for missing created_at
        if order_dict.get('created_at') is None:
            order_dict['created_at'] = order_dict.get('submitted_at') or datetime.now().isoformat()
        order_dict['strategy_name'] = strategy_name_map.get(order.strategy_id)
        # Infer order_action for legacy orders that don't have it set
        if not order_dict.get('order_action'):
            # Heuristic: if the order has a matching position with pending_closure or
            # closure_reason containing "retire", it's a retirement. If the order side
            # is opposite to what the strategy typically does, it's likely a close.
            # Default to 'entry' for orders without enough context.
            order_dict['order_action'] = 'entry'
        order_responses.append(OrderResponse(**order_dict))
    
    return OrdersResponse(
        orders=order_responses,
        total_count=total_count
    )


# Response models for execution quality endpoint
class ExecutionQualityResponse(BaseModel):
    """Execution quality metrics response model."""
    avg_slippage: float = Field(description="Average slippage in basis points")
    fill_rate: float = Field(description="Percentage of orders filled")
    avg_fill_time_seconds: float = Field(description="Average time to fill in seconds")
    rejection_rate: float = Field(description="Percentage of orders rejected")
    total_orders: int
    filled_orders: int
    rejected_orders: int
    pending_orders: int
    slippage_by_strategy: Dict[str, float]
    rejection_reasons: Dict[str, int]


# Specific routes must come before parameterized routes like /{order_id}
@router.get("/execution-quality", response_model=ExecutionQualityResponse)
async def get_execution_quality(
    mode: TradingMode,
    period: str = "1M",
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get execution quality metrics.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        period: Time period (1D, 1W, 1M, 3M)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Execution quality metrics including slippage, fill rate, and rejection rate
    """
    logger.info(f"Getting execution quality for {mode.value} mode, period {period}, user {username}")
    
    # Parse period
    from datetime import timedelta
    from src.monitoring.execution_quality import get_execution_quality_tracker
    
    period_map = {
        '1D': timedelta(days=1),
        '1W': timedelta(weeks=1),
        '1M': timedelta(days=30),
        '3M': timedelta(days=90)
    }
    
    time_delta = period_map.get(period, timedelta(days=30))
    start_date = datetime.now() - time_delta
    
    # Get metrics from ExecutionQualityTracker
    tracker = get_execution_quality_tracker()
    metrics = tracker.get_metrics(start_date=start_date)
    
    return ExecutionQualityResponse(
        avg_slippage=metrics.avg_slippage_bps,  # Return in basis points
        fill_rate=metrics.fill_rate,
        avg_fill_time_seconds=metrics.avg_fill_time_seconds,
        rejection_rate=metrics.rejection_rate,
        total_orders=metrics.total_orders,
        filled_orders=metrics.filled_orders,
        rejected_orders=metrics.rejected_orders,
        pending_orders=metrics.pending_orders,
        slippage_by_strategy=metrics.slippage_by_strategy,
        rejection_reasons=metrics.rejection_reasons
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get specific order details.
    
    Args:
        order_id: Order ID
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Order details
        
    Raises:
        HTTPException: If order not found
        
    Validates: Requirement 11.4
    """
    logger.info(f"Getting order {order_id} for {mode.value} mode, user {username}")
    
    # Query order from database
    order = session.query(OrderORM).filter_by(id=order_id).first()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found"
        )
    
    # Convert to response model
    order_dict = order.to_dict()
    return OrderResponse(**order_dict)


@router.post("", response_model=PlaceOrderResponse)
async def place_order(
    request: PlaceOrderRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Place manual order.
    
    Args:
        request: Order placement request
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Placed order ID
        
    Validates: Requirement 11.4
    """
    logger.info(
        f"Placing {request.side.value} order for {request.symbol} "
        f"in {mode.value} mode, user {username}"
    )
    
    # Validate order parameters
    if request.order_type == OrderType.LIMIT and request.price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price required for limit orders"
        )
    
    if request.order_type == OrderType.STOP_LOSS and request.stop_price is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stop price required for stop loss orders"
        )
    
    try:
        # Integrate with OrderExecutor to place real order
        from src.execution.order_executor import OrderExecutor
        from src.api.etoro_client import EToroAPIClient
        from src.data.market_hours_manager import get_market_hours_manager
        from src.core.config import get_config
        from src.models.dataclasses import Order as OrderDataclass
        
        # Get configuration
        config = get_config()
        
        # Load eToro credentials
        try:
            credentials = config.load_credentials(mode)
            if not credentials or not credentials.get("public_key") or not credentials.get("user_key"):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"eToro credentials not configured for {mode.value} mode"
                )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to load eToro credentials: {str(e)}"
            )
        
        # Initialize components with credentials
        etoro_client = EToroAPIClient(
            public_key=credentials["public_key"],
            user_key=credentials["user_key"],
            mode=mode
        )
        market_hours = get_market_hours_manager()
        order_executor = OrderExecutor(etoro_client, market_hours)
        
        # eToro API expects dollar amounts, not units/shares
        # The quantity field should already be in dollars from vibe coding or frontend
        position_size_dollars = request.quantity
        
        # Validate minimum order size (eToro requires minimum $10)
        if position_size_dollars < 10.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Order size must be at least $10.00 (eToro minimum). Requested: ${position_size_dollars:.2f}"
            )
        
        # Create order dataclass
        order_dc = OrderDataclass(
            id=f"order_{uuid4().hex[:8]}",
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            status=OrderStatus.PENDING,
            price=request.price,
            stop_price=request.stop_price,
            submitted_at=None,
            filled_at=None,
            filled_price=None,
            filled_quantity=None,
            etoro_order_id=None
        )
        
        # Submit order through executor
        # Note: For manual orders, we create a simple signal-like structure
        from src.models.dataclasses import TradingSignal
        from src.models.enums import SignalAction
        
        # Determine signal action from order side
        if request.side == OrderSide.BUY:
            action = SignalAction.ENTER_LONG
        else:
            action = SignalAction.EXIT_LONG

        # Recover template_name from the parent strategy so manual orders still
        # flow through the (template, symbol) loser-pair feedback loop. A manual
        # order associated with a strategy deserves the same accounting as an
        # autonomous order.
        _manual_tname = None
        try:
            from src.models.database import get_database as _get_db
            from src.models.orm import StrategyORM as _SORM
            _sess_m = _get_db().get_session()
            try:
                _s_row = _sess_m.query(_SORM).filter(_SORM.id == request.strategy_id).first()
                if _s_row and isinstance(_s_row.strategy_metadata, dict):
                    _manual_tname = _s_row.strategy_metadata.get('template_name') or getattr(_s_row, 'name', None)
            finally:
                _sess_m.close()
        except Exception:
            _manual_tname = None

        _manual_meta: Dict[str, Any] = {"manual": True, "user": username}
        if _manual_tname:
            _manual_meta["template_name"] = _manual_tname

        signal = TradingSignal(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            action=action,
            confidence=1.0,  # Manual orders have full confidence
            reasoning=f"Manual order by {username}",
            generated_at=datetime.now(),
            metadata=_manual_meta
        )
        
        # Execute signal
        executed_order = order_executor.execute_signal(
            signal=signal,
            position_size=position_size_dollars,  # Use converted dollar amount
            stop_loss_pct=None,
            take_profit_pct=None
        )
        
        # Save to database
        order_orm = OrderORM(
            id=executed_order.id,
            strategy_id=executed_order.strategy_id,
            symbol=executed_order.symbol,
            side=executed_order.side,
            order_type=executed_order.order_type,
            quantity=executed_order.quantity,
            status=executed_order.status,
            price=executed_order.price,
            stop_price=executed_order.stop_price,
            submitted_at=executed_order.submitted_at or datetime.now(),
            filled_at=executed_order.filled_at,
            filled_price=executed_order.filled_price,
            filled_quantity=executed_order.filled_quantity,
            etoro_order_id=executed_order.etoro_order_id,
            order_action='entry',
        )
        
        session.add(order_orm)
        session.commit()
        session.refresh(order_orm)
        
        logger.info(f"Order placed and saved to database: {executed_order.id}")
        
        return PlaceOrderResponse(
            success=True,
            message="Order placed successfully",
            order_id=executed_order.id
        )
    
    except Exception as e:
        logger.error(f"Failed to place order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place order: {str(e)}"
        )



@router.delete("/{order_id}", response_model=CancelOrderResponse)
async def cancel_order(
    order_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Cancel pending/submitted order with eToro pending check.

    For SUBMITTED orders:
    1. Check eToro API for pending orders matching this symbol/side
    2. If found on eToro as pending, cancel via eToro API first, then update DB
    3. If not found on eToro (already filled or expired), update DB status accordingly

    Args:
        order_id: Order ID to cancel
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session

    Returns:
        Cancellation confirmation
    """
    logger.info(f"Canceling order {order_id} for {mode.value} mode, user {username}")

    try:
        # Get order from database
        order_orm = session.query(OrderORM).filter_by(id=order_id).first()

        if not order_orm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found"
            )

        # Check if order can be cancelled
        if order_orm.status != OrderStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel order in {order_orm.status.value} status"
            )

        from src.core.config import get_config
        config = get_config()

        # Try to get eToro client
        etoro_client = None
        try:
            credentials = config.load_credentials(mode)
            if credentials and credentials.get("public_key") and credentials.get("user_key"):
                etoro_client = EToroAPIClient(
                    public_key=credentials["public_key"],
                    user_key=credentials["user_key"],
                    mode=mode
                )
        except Exception as e:
            logger.warning(f"Failed to load credentials: {e}")

        if not etoro_client:
            # No eToro connection — just update local status
            order_orm.status = OrderStatus.CANCELLED
            session.commit()
            return CancelOrderResponse(
                success=True,
                message="Order cancelled locally (no eToro connection)",
                order_id=order_id
            )

        # For orders with eToro order ID, check eToro status first
        if order_orm.etoro_order_id:
            try:
                status_data = etoro_client.get_order_status(order_orm.etoro_order_id)
                etoro_status = status_data.get("statusID") or status_data.get("status")
                has_positions = bool(status_data.get("positions"))
                error_code = status_data.get("errorCode")

                logger.info(f"eToro status for order {order_id}: statusID={etoro_status}, hasPositions={has_positions}, errorCode={error_code}")

                # Check if already filled on eToro
                if etoro_status in [2, 3, 7, "filled", "FILLED", "executed", "EXECUTED"]:
                    if has_positions or etoro_status in [2, 7]:
                        # Order already filled — update DB to FILLED, can't cancel
                        order_orm.status = OrderStatus.FILLED
                        order_orm.filled_at = datetime.utcnow()
                        order_orm.filled_quantity = order_orm.quantity
                        session.commit()
                        return CancelOrderResponse(
                            success=False,
                            message="Order already executed on eToro. Status updated to Executed.",
                            order_id=order_id
                        )

                # Check if already cancelled/failed on eToro
                if etoro_status in ["cancelled", "CANCELLED"] or (etoro_status == 3 and not has_positions):
                    order_orm.status = OrderStatus.CANCELLED
                    session.commit()
                    return CancelOrderResponse(
                        success=True,
                        message="Order was already cancelled on eToro. Local status updated.",
                        order_id=order_id
                    )

                if error_code and error_code != 0:
                    order_orm.status = OrderStatus.FAILED
                    session.commit()
                    return CancelOrderResponse(
                        success=True,
                        message=f"Order failed on eToro (error {error_code}). Status updated.",
                        order_id=order_id
                    )

                # Order is still pending on eToro — try to cancel it
                if etoro_status in [1, 11, "pending", "PENDING"]:
                    try:
                        etoro_cancelled = etoro_client.cancel_order(order_orm.etoro_order_id)
                        if etoro_cancelled:
                            order_orm.status = OrderStatus.CANCELLED
                            session.commit()
                            logger.info(f"Cancelled order {order_id} on eToro successfully")
                            return CancelOrderResponse(
                                success=True,
                                message="Order cancelled successfully on eToro",
                                order_id=order_id
                            )
                    except Exception as e:
                        logger.warning(f"eToro cancel API failed: {e}")

            except Exception as e:
                logger.warning(f"Failed to check eToro order status: {e}")

        # For PENDING orders (not yet on eToro) or if eToro check failed,
        # cancel via eToro API if we have an eToro order ID
        etoro_cancelled = False
        if order_orm.etoro_order_id:
            try:
                etoro_cancelled = etoro_client.cancel_order(order_orm.etoro_order_id)
                if etoro_cancelled:
                    logger.info(f"Cancelled order {order_id} (eToro: {order_orm.etoro_order_id}) via eToro API")
            except Exception as e:
                logger.warning(f"Failed to cancel order via eToro API: {e}")

        # Update order status in database
        order_orm.status = OrderStatus.CANCELLED
        session.commit()

        if order_orm.etoro_order_id:
            if etoro_cancelled:
                message = "Order cancelled successfully on eToro"
            else:
                message = "Order cancelled locally. eToro cancellation may require manual action."
        else:
            message = "Order cancelled locally (not yet submitted to eToro)"

        logger.info(f"Order {order_id} cancelled successfully")

        return CancelOrderResponse(
            success=True,
            message=message,
            order_id=order_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order: {str(e)}"
        )







class DeleteOrderResponse(BaseModel):
    """Delete order response model."""
    success: bool
    message: str
    order_id: str


@router.delete("/{order_id}/permanent", response_model=DeleteOrderResponse)
async def delete_order_permanent(
    order_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Permanently delete a CANCELLED order from the database.
    
    This endpoint is for cleanup purposes - removing test orders or orders
    that were cancelled locally but couldn't be cancelled on eToro.
    
    Args:
        order_id: Order ID to delete
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Deletion confirmation
        
    Validates: Requirement 11.4
    """
    logger.info(f"Permanently deleting order {order_id} for {mode.value} mode, user {username}")
    
    try:
        # Get order from database
        order_orm = session.query(OrderORM).filter_by(id=order_id).first()
        
        if not order_orm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found"
            )
        
        # Only allow deletion of terminal-state orders
        if order_orm.status not in [OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.FAILED]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Can only delete CANCELLED, FILLED, or FAILED orders. Order status is {order_orm.status.value}"
            )
        
        # Delete the order from database
        session.delete(order_orm)
        session.commit()
        
        logger.info(f"Order {order_id} permanently deleted successfully")
        
        return DeleteOrderResponse(
            success=True,
            message="Order permanently deleted from database",
            order_id=order_id
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete order: {str(e)}"
        )


class BulkDeleteOrdersRequest(BaseModel):
    """Bulk delete orders request model."""
    order_ids: List[str]


class BulkDeleteOrdersResponse(BaseModel):
    """Bulk delete orders response model."""
    success_count: int
    fail_count: int
    deleted_order_ids: List[str]
    failed_order_ids: List[str]


@router.post("/bulk-delete", response_model=BulkDeleteOrdersResponse)
async def bulk_delete_orders(
    request: BulkDeleteOrdersRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Permanently delete multiple CANCELLED orders from the database.
    
    This endpoint is for cleanup purposes - removing multiple test orders or orders
    that were cancelled locally but couldn't be cancelled on eToro.
    
    Args:
        request: List of order IDs to delete
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        
    Returns:
        Bulk deletion results
        
    Validates: Requirement 11.4
    """
    logger.info(f"Bulk deleting {len(request.order_ids)} orders for {mode.value} mode, user {username}")
    
    deleted_order_ids = []
    failed_order_ids = []
    
    for order_id in request.order_ids:
        try:
            # Get order from database
            order_orm = session.query(OrderORM).filter_by(id=order_id).first()
            
            if not order_orm:
                logger.warning(f"Order {order_id} not found")
                failed_order_ids.append(order_id)
                continue
            
            # Only allow deletion of terminal-state orders
            if order_orm.status not in [OrderStatus.CANCELLED, OrderStatus.FILLED, OrderStatus.FAILED]:
                logger.warning(f"Order {order_id} is not in a terminal state (status: {order_orm.status.value})")
                failed_order_ids.append(order_id)
                continue
            
            # Delete the order from database
            session.delete(order_orm)
            deleted_order_ids.append(order_id)
            
        except Exception as e:
            logger.error(f"Failed to delete order {order_id}: {e}")
            failed_order_ids.append(order_id)
    
    # Commit all deletions
    try:
        session.commit()
        logger.info(f"Bulk delete completed: {len(deleted_order_ids)} deleted, {len(failed_order_ids)} failed")
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to commit bulk delete: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit bulk delete: {str(e)}"
        )
    
    return BulkDeleteOrdersResponse(
        success_count=len(deleted_order_ids),
        fail_count=len(failed_order_ids),
        deleted_order_ids=deleted_order_ids,
        failed_order_ids=failed_order_ids
    )



class CloseFilledOrderResponse(BaseModel):
    """Close filled order response model."""
    success: bool
    message: str
    order_id: str
    position_closed: bool


@router.post("/{order_id}/close-position", response_model=CloseFilledOrderResponse)
async def close_filled_order_position(
    order_id: str,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Close the position created by a FILLED order.
    
    This finds the open position with matching symbol/strategy and closes it on eToro.
    
    Args:
        order_id: Order ID whose position to close
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        config: Configuration instance
        
    Returns:
        Position closure confirmation
        
    Validates: Requirement 11.4
    """
    logger.info(f"Closing position for filled order {order_id} in {mode.value} mode, user {username}")
    
    try:
        # Get order from database
        order_orm = session.query(OrderORM).filter_by(id=order_id).first()
        
        if not order_orm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found"
            )
        
        # Only allow closing positions for FILLED orders
        if order_orm.status != OrderStatus.FILLED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Can only close positions for FILLED orders. Order status is {order_orm.status.value}"
            )
        
        # Find matching open position
        from src.models.orm import PositionORM
        from src.models.enums import PositionSide
        
        # Determine expected position side from order side
        expected_position_side = PositionSide.LONG if order_orm.side == OrderSide.BUY else PositionSide.SHORT
        
        # Find open position with matching symbol and strategy
        position_orm = session.query(PositionORM).filter_by(
            symbol=order_orm.symbol,
            strategy_id=order_orm.strategy_id,
            side=expected_position_side
        ).filter(
            PositionORM.closed_at.is_(None)
        ).first()
        
        if not position_orm:
            # Position doesn't exist or was already closed - this is OK
            logger.info(f"No open position found for order {order_id} - may have been closed manually")
            return CloseFilledOrderResponse(
                success=True,
                message=f"No open position found (may have been closed manually)",
                order_id=order_id,
                position_closed=False
            )
        
        # Get eToro client
        etoro_client = get_etoro_client(mode, config)
        if not etoro_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"eToro credentials not configured for {mode.value} mode"
            )
        
        # Close position on eToro
        try:
            # Extract instrument ID from symbol if available (format: ID_1137)
            instrument_id = None
            if position_orm.symbol.startswith('ID_'):
                try:
                    instrument_id = int(position_orm.symbol.replace('ID_', ''))
                except ValueError:
                    pass
            
            etoro_client.close_position(
                position_id=position_orm.etoro_position_id,
                instrument_id=instrument_id
            )
            
            # Update position in database
            from datetime import datetime
            position_orm.closed_at = datetime.now()
            session.commit()
            
            logger.info(f"Closed position {position_orm.id} for order {order_id}")
            
            return CloseFilledOrderResponse(
                success=True,
                message=f"Position closed successfully on eToro",
                order_id=order_id,
                position_closed=True
            )
            
        except Exception as e:
            logger.error(f"Failed to close position on eToro: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to close position on eToro: {str(e)}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to close position for order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close position: {str(e)}"
        )


class SyncOrdersResponse(BaseModel):
    """Response for order sync."""
    success: bool
    message: str
    checked: int = 0
    filled: int = 0
    cancelled: int = 0
    failed: int = 0


@router.post("/sync", response_model=SyncOrdersResponse)
async def sync_orders(
    mode: TradingMode,
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session),
    config: Configuration = Depends(get_configuration)
):
    """
    Sync all order statuses with eToro.
    
    Checks all SUBMITTED orders against eToro API and updates their status.
    
    Args:
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        session: Database session
        config: Configuration instance
        
    Returns:
        Sync results with counts of updated orders
    """
    logger.info(f"Syncing orders with eToro for {mode.value} mode, user {username}")
    
    try:
        etoro_client = get_etoro_client(mode, config)
        if not etoro_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"eToro credentials not configured for {mode.value} mode"
            )
        
        from src.core.order_monitor import OrderMonitor
        from src.models.database import Database
        
        db = Database()
        order_monitor = OrderMonitor(etoro_client, db)
        
        # Run the submitted orders check
        result = order_monitor.check_submitted_orders()
        
        return SyncOrdersResponse(
            success=True,
            message=f"Synced {result.get('checked', 0)} orders with eToro",
            checked=result.get("checked", 0),
            filled=result.get("filled", 0),
            cancelled=result.get("cancelled", 0),
            failed=result.get("failed", 0)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to sync orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync orders: {str(e)}"
        )
