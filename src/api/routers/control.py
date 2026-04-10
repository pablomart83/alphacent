"""
Control endpoints for AlphaCent Trading Platform.

Provides endpoints for system control (kill switch, circuit breaker, rebalancing, system state).
Validates: Requirements 11.5, 11.11, 11.12, 16.12
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.models.enums import SystemStateEnum, TradingMode
from src.api.dependencies import get_current_user, get_db_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/control", tags=["control"])


# ============================================================================
# System State Management Models
# ============================================================================

class SystemStatusResponse(BaseModel):
    """System status response model."""
    state: SystemStateEnum
    timestamp: str
    active_strategies: int
    open_positions: int
    reason: str
    uptime_seconds: int
    last_signal_generated: Optional[str] = None
    last_order_executed: Optional[str] = None


class StateChangeRequest(BaseModel):
    """State change request model."""
    confirmation: bool = Field(..., description="User must confirm state change")


class StateChangeResponse(BaseModel):
    """State change response model."""
    success: bool
    message: str
    state: SystemStateEnum


# ============================================================================
# Control Action Models
# ============================================================================

class KillSwitchRequest(BaseModel):
    """Kill switch request model."""
    confirmation: bool = Field(..., description="User must confirm kill switch activation")
    reason: Optional[str] = Field(None, description="Reason for activation")


class KillSwitchResponse(BaseModel):
    """Kill switch response model."""
    success: bool
    message: str
    positions_closed: int
    orders_cancelled: int


class CircuitBreakerResetRequest(BaseModel):
    """Circuit breaker reset request model."""
    confirmation: bool = Field(..., description="User must confirm reset")


class CircuitBreakerResetResponse(BaseModel):
    """Circuit breaker reset response model."""
    success: bool
    message: str


class RebalanceRequest(BaseModel):
    """Manual rebalance request model."""
    confirmation: bool = Field(..., description="User must confirm rebalance")


class RebalanceResponse(BaseModel):
    """Rebalance response model."""
    success: bool
    message: str
    orders_created: int


class SessionSummaryResponse(BaseModel):
    """Session summary response model."""
    session_id: str
    start_time: str
    end_time: str
    duration_seconds: int
    total_return: float
    total_trades: int
    win_rate: float
    max_drawdown: float
    strategies_active: int


class SessionHistoryResponse(BaseModel):
    """Session history list response model."""
    sessions: list[SessionSummaryResponse]
    total_count: int


# ============================================================================
# System State Management Endpoints
# ============================================================================

@router.get("/system/status", response_model=SystemStatusResponse)
async def get_system_status(
    username: str = Depends(get_current_user),
    session: Session = Depends(get_db_session)
):
    """
    Get current autonomous trading system status.
    
    Args:
        username: Current authenticated user
        
    Returns:
        System status
        
    Validates: Requirements 11.11, 11.12, 16.12
    """
    logger.info(f"Getting system status, user {username}")
    
    try:
        from src.core.system_state_manager import get_system_state_manager
        
        # Get actual state from system state manager
        state_manager = get_system_state_manager()
        current_state = state_manager.get_current_state()
        
        # Get accurate counts from database
        from src.models.orm import StrategyORM, PositionORM
        try:
            active_strategies_count = session.query(StrategyORM).filter(
                StrategyORM.status.in_(["DEMO", "LIVE"])
            ).count()
            
            open_positions_count = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).count()
        except Exception:
            active_strategies_count = current_state.active_strategies_count
            open_positions_count = current_state.open_positions_count
        
        return SystemStatusResponse(
            state=current_state.state,
            timestamp=current_state.timestamp.isoformat(),
            active_strategies=active_strategies_count,
            open_positions=open_positions_count,
            reason=current_state.reason,
            uptime_seconds=current_state.uptime_seconds,
            last_signal_generated=current_state.last_signal_generated.isoformat() if current_state.last_signal_generated else None,
            last_order_executed=current_state.last_order_executed.isoformat() if current_state.last_order_executed else None
        )
    
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        # Return default state on error
        return SystemStatusResponse(
            state=SystemStateEnum.STOPPED,
            timestamp=datetime.now().isoformat(),
            active_strategies=0,
            open_positions=0,
            reason="Error retrieving system state",
            uptime_seconds=0,
            last_signal_generated=None,
            last_order_executed=None
        )


@router.get("/system/sessions", response_model=SessionHistoryResponse)
async def get_session_history(
    limit: int = 5,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Get historical session summaries.
    
    Returns performance summary from previous trading sessions.
    
    Args:
        limit: Maximum number of sessions to return (default 5)
        username: Current authenticated user
        db: Database session
        
    Returns:
        List of session summaries
        
    Validates: Requirements 11.14, 11.15
    """
    logger.info(f"Getting session history (limit={limit}), user {username}")
    
    # TODO: Integrate with database to get real session history from SystemState table
    # For now, return empty list until session tracking is fully implemented
    
    logger.warning("Session history not yet implemented, returning empty list")
    
    return SessionHistoryResponse(
        sessions=[],
        total_count=0
    )


@router.post("/system/start", response_model=StateChangeResponse)
async def start_autonomous_trading(
    request: StateChangeRequest,
    mode: TradingMode = TradingMode.DEMO,
    username: str = Depends(get_current_user)
):
    """
    Start autonomous trading.
    
    Transitions system to ACTIVE state.
    
    Args:
        request: State change request with confirmation
        mode: Trading mode (DEMO or LIVE), defaults to DEMO
        username: Current authenticated user
        
    Returns:
        State change confirmation
        
    Validates: Requirements 11.11, 11.12, 16.12
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to start autonomous trading"
        )
    
    logger.info(f"Starting autonomous trading in {mode.value} mode, user {username}")
    
    try:
        # Import here to avoid circular dependencies
        from src.core.system_state_manager import get_system_state_manager
        from src.core.service_manager import get_service_manager
        
        # Get system state manager
        state_manager = get_system_state_manager()
        
        # Transition to ACTIVE state
        new_state = state_manager.transition_to(
            SystemStateEnum.ACTIVE,
            reason=f"User {username} started autonomous trading in {mode.value} mode",
            initiated_by=username
        )
        
        # Start health checks (no-op currently, no external services)
        service_manager = get_service_manager()
        service_manager.start_health_checks()
        
        logger.info(f"Successfully transitioned to ACTIVE state")
        
        return StateChangeResponse(
            success=True,
            message=f"Autonomous trading started in {mode.value} mode",
            state=new_state.state
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start autonomous trading: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start autonomous trading: {str(e)}"
        )


@router.post("/system/pause", response_model=StateChangeResponse)
async def pause_autonomous_trading(
    request: StateChangeRequest,
    username: str = Depends(get_current_user)
):
    """
    Pause autonomous trading.
    
    Transitions system to PAUSED state. Existing positions maintained.
    
    Args:
        request: State change request with confirmation
        username: Current authenticated user
        
    Returns:
        State change confirmation
        
    Validates: Requirements 11.11, 11.12, 16.12
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to pause autonomous trading"
        )
    
    logger.info(f"Pausing autonomous trading, user {username}")
    
    try:
        from src.core.system_state_manager import get_system_state_manager
        
        state_manager = get_system_state_manager()
        new_state = state_manager.transition_to(
            SystemStateEnum.PAUSED,
            reason=f"User {username} paused autonomous trading",
            initiated_by=username
        )
        
        logger.info(f"Successfully transitioned to PAUSED state")
        
        return StateChangeResponse(
            success=True,
            message="Autonomous trading paused",
            state=new_state.state
        )
    
    except Exception as e:
        logger.error(f"Failed to pause autonomous trading: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause autonomous trading: {str(e)}"
        )


@router.post("/system/stop", response_model=StateChangeResponse)
async def stop_autonomous_trading(
    request: StateChangeRequest,
    username: str = Depends(get_current_user)
):
    """
    Stop autonomous trading.
    
    Transitions system to STOPPED state. Existing positions maintained.
    
    Args:
        request: State change request with confirmation
        username: Current authenticated user
        
    Returns:
        State change confirmation
        
    Validates: Requirements 11.11, 11.12, 16.12
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to stop autonomous trading"
        )
    
    logger.info(f"Stopping autonomous trading, user {username}")
    
    try:
        from src.core.system_state_manager import get_system_state_manager
        
        state_manager = get_system_state_manager()
        new_state = state_manager.transition_to(
            SystemStateEnum.STOPPED,
            reason=f"User {username} stopped autonomous trading",
            initiated_by=username
        )
        
        # Stop health checks (best-effort, don't fail the stop operation)
        try:
            from src.core.service_manager import get_service_manager
            service_manager = get_service_manager()
            service_manager.stop_health_checks()
        except Exception as e:
            logger.warning(f"Failed to stop health checks (non-critical): {e}")
        
        logger.info(f"Successfully transitioned to STOPPED state")
        
        return StateChangeResponse(
            success=True,
            message="Autonomous trading stopped",
            state=new_state.state
        )
    
    except Exception as e:
        logger.error(f"Failed to stop autonomous trading: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop autonomous trading: {str(e)}"
        )


@router.post("/system/resume", response_model=StateChangeResponse)
async def resume_autonomous_trading(
    request: StateChangeRequest,
    mode: TradingMode = TradingMode.DEMO,
    username: str = Depends(get_current_user)
):
    """
    Resume autonomous trading from paused state.
    
    Transitions system from PAUSED to ACTIVE state.
    
    Args:
        request: State change request with confirmation
        mode: Trading mode (DEMO or LIVE), defaults to DEMO
        username: Current authenticated user
        
    Returns:
        State change confirmation
        
    Validates: Requirements 11.11, 11.12, 16.12
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to resume autonomous trading"
        )
    
    logger.info(f"Resuming autonomous trading in {mode.value} mode, user {username}")
    
    try:
        from src.core.system_state_manager import get_system_state_manager
        
        state_manager = get_system_state_manager()
        new_state = state_manager.transition_to(
            SystemStateEnum.ACTIVE,
            reason=f"User {username} resumed autonomous trading in {mode.value} mode",
            initiated_by=username
        )
        
        logger.info(f"Successfully transitioned to ACTIVE state")
        
        return StateChangeResponse(
            success=True,
            message=f"Autonomous trading resumed in {mode.value} mode",
            state=new_state.state
        )
    
    except Exception as e:
        logger.error(f"Failed to resume autonomous trading: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume autonomous trading: {str(e)}"
        )


@router.post("/system/reset", response_model=StateChangeResponse)
async def reset_from_emergency_halt(
    request: StateChangeRequest,
    username: str = Depends(get_current_user)
):
    """
    Reset system from emergency halt.
    
    Transitions system from EMERGENCY_HALT to STOPPED state.
    
    Args:
        request: State change request with confirmation
        username: Current authenticated user
        
    Returns:
        State change confirmation
        
    Validates: Requirements 11.11, 11.12, 16.12
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to reset from emergency halt"
        )
    
    logger.info(f"Resetting from emergency halt, user {username}")
    
    try:
        from src.core.system_state_manager import get_system_state_manager
        
        state_manager = get_system_state_manager()
        new_state = state_manager.transition_to(
            SystemStateEnum.STOPPED,
            reason=f"User {username} reset from emergency halt",
            initiated_by=username
        )
        
        logger.info(f"Successfully reset from emergency halt to STOPPED state")
        
        return StateChangeResponse(
            success=True,
            message="System reset from emergency halt, ready to start",
            state=new_state.state
        )
    
    except Exception as e:
        logger.error(f"Failed to reset from emergency halt: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset from emergency halt: {str(e)}"
        )


# ============================================================================
# Control Action Endpoints
# ============================================================================

@router.post("/kill-switch", response_model=KillSwitchResponse)
async def activate_kill_switch(
    request: KillSwitchRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user)
):
    """
    Activate kill switch - emergency shutdown.
    
    Closes all positions, cancels all orders, halts trading.
    
    Args:
        request: Kill switch request with confirmation
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        
    Returns:
        Kill switch activation result
        
    Validates: Requirement 11.5
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to activate kill switch"
        )
    
    reason = request.reason or f"Manual activation by {username}"
    logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
    
    try:
        # Integrate with RiskManager to execute kill switch
        from src.risk.risk_manager import RiskManager
        from src.execution.order_executor import OrderExecutor
        from src.api.etoro_client import EToroAPIClient
        from src.data.market_hours_manager import MarketHoursManager
        from src.core.config import get_config
        from src.core.system_state_manager import get_system_state_manager
        from src.models.enums import SystemStateEnum
        
        # Get configuration
        config = get_config()
        risk_config = config.load_risk_config(mode)
        
        # Initialize components
        risk_manager = RiskManager(risk_config)
        etoro_client = EToroAPIClient(mode=mode)
        market_hours = MarketHoursManager()
        order_executor = OrderExecutor(etoro_client, market_hours)
        
        # Execute kill switch through risk manager
        risk_manager.execute_kill_switch(reason)
        
        # Close all positions through order executor
        close_orders = order_executor.close_all_positions()
        positions_closed = len(close_orders)
        
        # Cancel all pending orders
        pending_orders = order_executor.get_pending_orders()
        orders_cancelled = 0
        for order in pending_orders:
            try:
                if order.etoro_order_id:
                    etoro_client.cancel_order(order.etoro_order_id)
                orders_cancelled += 1
            except Exception as e:
                logger.error(f"Failed to cancel order {order.id}: {e}")
        
        # Transition system to EMERGENCY_HALT state
        state_manager = get_system_state_manager()
        state_manager.transition_to(
            SystemStateEnum.EMERGENCY_HALT,
            reason=reason,
            initiated_by=username
        )
        
        logger.critical(
            f"KILL SWITCH COMPLETE: {positions_closed} positions closed, "
            f"{orders_cancelled} orders cancelled"
        )
        
        return KillSwitchResponse(
            success=True,
            message="Kill switch activated - all positions closed, trading halted",
            positions_closed=positions_closed,
            orders_cancelled=orders_cancelled
        )
    
    except Exception as e:
        logger.error(f"Failed to execute kill switch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute kill switch: {str(e)}"
        )


@router.post("/circuit-breaker/reset", response_model=CircuitBreakerResetResponse)
async def reset_circuit_breaker(
    request: CircuitBreakerResetRequest,
    username: str = Depends(get_current_user)
):
    """
    Reset circuit breaker.
    
    Allows trading to resume after circuit breaker activation.
    
    Args:
        request: Reset request with confirmation
        username: Current authenticated user
        
    Returns:
        Reset confirmation
        
    Validates: Requirement 11.5
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to reset circuit breaker"
        )
    
    logger.info(f"Resetting circuit breaker, user {username}")
    
    try:
        # Integrate with RiskManager to reset circuit breaker
        from src.risk.risk_manager import RiskManager
        from src.core.config import get_config
        from src.models.enums import TradingMode
        
        # Get configuration (use DEMO mode as default for risk config)
        config = get_config()
        risk_config = config.load_risk_config(TradingMode.DEMO)
        
        # Initialize risk manager
        risk_manager = RiskManager(risk_config)
        
        # Reset circuit breaker
        risk_manager.reset_circuit_breaker()
        
        logger.info(f"Circuit breaker reset successfully by {username}")
        
        return CircuitBreakerResetResponse(
            success=True,
            message="Circuit breaker reset"
        )
    
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset circuit breaker: {str(e)}"
        )


@router.post("/rebalance", response_model=RebalanceResponse)
async def manual_rebalance(
    request: RebalanceRequest,
    mode: TradingMode,
    username: str = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """
    Trigger manual portfolio rebalancing.
    
    Args:
        request: Rebalance request with confirmation
        mode: Trading mode (DEMO or LIVE)
        username: Current authenticated user
        db: Database session
        
    Returns:
        Rebalance result
        
    Validates: Requirement 11.5
    """
    if not request.confirmation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation required to rebalance portfolio"
        )
    
    logger.info(f"Manual rebalance triggered for {mode.value} mode, user {username}")
    
    try:
        # Integrate with StrategyEngine to rebalance portfolio
        from src.strategy.strategy_engine import StrategyEngine
        from src.data.market_data_manager import MarketDataManager
        from src.llm.llm_service import LLMService
        from src.api.etoro_client import EToroAPIClient
        from src.api.websocket_manager import get_websocket_manager
        from src.models.orm import PositionORM
        
        # Initialize components
        market_data = MarketDataManager()
        llm_service = LLMService()
        websocket_manager = get_websocket_manager()
        strategy_engine = StrategyEngine(llm_service, market_data, websocket_manager)
        etoro_client = EToroAPIClient(mode=mode)
        
        # Get active strategies
        active_strategies = strategy_engine.get_active_strategies()
        
        if not active_strategies:
            logger.info("No active strategies to rebalance")
            return RebalanceResponse(
                success=True,
                message="No active strategies to rebalance",
                orders_created=0
            )
        
        # Calculate optimal allocations
        target_allocations = strategy_engine.optimize_allocations(active_strategies)
        
        # Get account info
        account_info = etoro_client.get_account_info()
        account_balance = account_info.get("balance", 0.0)
        
        # Get current positions
        positions = db.query(PositionORM).filter(
            PositionORM.closed_at.is_(None)
        ).all()
        
        # Calculate rebalancing orders
        rebalancing_orders = strategy_engine.rebalance_portfolio(
            target_allocations=target_allocations,
            account_balance=account_balance,
            current_positions=positions
        )
        
        # TODO: Execute rebalancing orders through OrderExecutor
        # For now, just log the orders
        for order_spec in rebalancing_orders:
            logger.info(
                f"Rebalancing order: {order_spec['action'].value} "
                f"${order_spec['value']:.2f} {order_spec['symbol']} "
                f"for strategy {order_spec['strategy_name']}"
            )
        
        logger.info(f"Portfolio rebalancing complete: {len(rebalancing_orders)} orders created")
        
        return RebalanceResponse(
            success=True,
            message="Portfolio rebalancing initiated",
            orders_created=len(rebalancing_orders)
        )
    
    except Exception as e:
        logger.error(f"Failed to rebalance portfolio: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rebalance portfolio: {str(e)}"
        )



# ============================================================================
# Service Management Models
# ============================================================================

class ServiceStatusResponse(BaseModel):
    """Service status response model."""
    name: str
    is_healthy: bool
    status: str
    endpoint: str
    last_check: str
    error_message: Optional[str] = None


class ServicesStatusResponse(BaseModel):
    """All services status response model."""
    services: dict


class ServiceActionResponse(BaseModel):
    """Service action response model."""
    success: bool
    message: str


# ============================================================================
# Service Management Endpoints
# ============================================================================

@router.get("/services", response_model=ServicesStatusResponse)
async def get_services_status(
    username: str = Depends(get_current_user)
):
    """
    Get status of all dependent services.
    
    Args:
        username: Current authenticated user
        
    Returns:
        Status of all services
        
    Validates: Requirements 16.1.8, 16.1.9
    """
    logger.info(f"Getting services status, user {username}")
    
    # No external service dependencies — strategy generation uses templates
    return ServicesStatusResponse(
        services={}
    )


@router.get("/services/{service_name}/health", response_model=ServiceStatusResponse)
async def get_service_health(
    service_name: str,
    username: str = Depends(get_current_user)
):
    """
    Health check a specific service.
    
    Args:
        service_name: Name of service
        username: Current authenticated user
        
    Returns:
        Service health status
        
    Validates: Requirement 16.1.6
    """
    logger.info(f"Checking health of service {service_name}, user {username}")
    
    # No external services — all service names return 404
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Service {service_name} not found. No external service dependencies."
    )


@router.post("/services/{service_name}/start", response_model=ServiceActionResponse)
async def start_service(
    service_name: str,
    username: str = Depends(get_current_user)
):
    """
    Start a specific service.
    
    Args:
        service_name: Name of service to start
        username: Current authenticated user
        
    Returns:
        Service start result
        
    Validates: Requirement 16.1.3
    """
    logger.info(f"Starting service {service_name}, user {username}")
    
    try:
        # Integrate with ServiceManager
        from src.core.service_manager import get_service_manager
        
        service_manager = get_service_manager()
        
        # Start the service
        success = service_manager.start_service(service_name)
        
        if success:
            return ServiceActionResponse(
                success=True,
                message=f"Service {service_name} started successfully"
            )
        else:
            return ServiceActionResponse(
                success=False,
                message=f"Failed to start service {service_name}"
            )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error starting service {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting service: {str(e)}"
        )


@router.post("/services/{service_name}/stop", response_model=ServiceActionResponse)
async def stop_service(
    service_name: str,
    username: str = Depends(get_current_user)
):
    """
    Stop a specific service.
    
    Args:
        service_name: Name of service to stop
        username: Current authenticated user
        
    Returns:
        Service stop result
        
    Validates: Requirement 16.1.7
    """
    logger.info(f"Stopping service {service_name}, user {username}")
    
    try:
        # Integrate with ServiceManager
        from src.core.service_manager import get_service_manager
        
        service_manager = get_service_manager()
        
        # Stop the service
        success = service_manager.stop_service(service_name)
        
        if success:
            return ServiceActionResponse(
                success=True,
                message=f"Service {service_name} stopped successfully"
            )
        else:
            return ServiceActionResponse(
                success=False,
                message=f"Failed to stop service {service_name}"
            )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error stopping service {service_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error stopping service: {str(e)}"
        )


# ============================================================================
# Autonomous Schedule Management
# ============================================================================


class AutonomousScheduleConfig(BaseModel):
    """Autonomous cycle schedule configuration."""
    enabled: bool = Field(True, description="Whether scheduled autonomous cycles are enabled")
    frequency: str = Field("weekly", description="Schedule frequency: weekly or daily")
    day_of_week: str = Field("sunday", description="Day of week for weekly schedule")
    hour: int = Field(2, ge=0, le=23, description="Hour of day to run (0-23)")
    minute: int = Field(0, ge=0, le=59, description="Minute of hour to run (0-59)")


class AutonomousScheduleResponse(BaseModel):
    """Response for autonomous schedule endpoints."""
    success: bool
    schedule: AutonomousScheduleConfig
    next_run: Optional[str] = None
    last_run: Optional[str] = None
    message: str = ""


@router.get("/autonomous/schedule", response_model=AutonomousScheduleResponse)
async def get_autonomous_schedule(
    username: str = Depends(get_current_user)
):
    """
    Get the current autonomous cycle schedule configuration and next run time.
    """
    import yaml
    from pathlib import Path

    try:
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        schedule_config = config.get("autonomous_schedule", {})
        schedule = AutonomousScheduleConfig(
            enabled=schedule_config.get("enabled", True),
            frequency=schedule_config.get("frequency", "weekly"),
            day_of_week=schedule_config.get("day_of_week", "sunday"),
            hour=schedule_config.get("hour", 2),
            minute=schedule_config.get("minute", 0),
        )

        # Calculate next run time
        next_run = _calculate_next_run(schedule)
        
        # Get last run time from monitoring service
        last_run = None
        try:
            from src.core.monitoring_service import get_monitoring_service
            ms = get_monitoring_service()
            if ms and hasattr(ms, '_last_scheduled_cycle_time') and ms._last_scheduled_cycle_time:
                last_run = ms._last_scheduled_cycle_time.isoformat()
        except Exception:
            pass

        return AutonomousScheduleResponse(
            success=True,
            schedule=schedule,
            next_run=next_run,
            last_run=last_run,
            message="Schedule retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Error getting autonomous schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting schedule: {str(e)}",
        )


@router.post("/autonomous/schedule", response_model=AutonomousScheduleResponse)
async def update_autonomous_schedule(
    request: AutonomousScheduleConfig,
    username: str = Depends(get_current_user)
):
    """
    Update the autonomous cycle schedule configuration.
    """
    import yaml
    from pathlib import Path

    try:
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        # Update the schedule section
        config["autonomous_schedule"] = {
            "enabled": request.enabled,
            "frequency": request.frequency,
            "day_of_week": request.day_of_week,
            "hour": request.hour,
            "minute": request.minute,
        }

        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        # Notify monitoring service of config change
        try:
            from src.core.monitoring_service import get_monitoring_service
            ms = get_monitoring_service()
            if ms and hasattr(ms, '_reload_schedule_config'):
                ms._reload_schedule_config()
        except Exception:
            pass

        next_run = _calculate_next_run(request)

        logger.info(f"Autonomous schedule updated by {username}: enabled={request.enabled}, "
                     f"frequency={request.frequency}, day={request.day_of_week}, hour={request.hour}")

        return AutonomousScheduleResponse(
            success=True,
            schedule=request,
            next_run=next_run,
            message="Schedule updated successfully",
        )
    except Exception as e:
        logger.error(f"Error updating autonomous schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating schedule: {str(e)}",
        )


def _calculate_next_run(schedule: AutonomousScheduleConfig) -> Optional[str]:
    """Calculate the next scheduled run time based on config."""
    if not schedule.enabled:
        return None

    from datetime import timedelta

    now = datetime.utcnow()
    day_map = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    if schedule.frequency == "weekly":
        target_day = day_map.get(schedule.day_of_week.lower(), 6)
        days_ahead = target_day - now.weekday()
        if days_ahead < 0:
            days_ahead += 7

        next_run = now.replace(
            hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0
        ) + timedelta(days=days_ahead)

        # If the calculated time is in the past (same day but earlier), move to next week
        if next_run <= now:
            next_run += timedelta(weeks=1)

        return next_run.isoformat() + "Z"

    elif schedule.frequency == "daily":
        next_run = now.replace(
            hour=schedule.hour, minute=schedule.minute, second=0, microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        return next_run.isoformat() + "Z"

    return None

# ============================================================================
# Sync Status


class SyncSourceStatus(BaseModel):
    """Status of a single data source sync."""
    source: str
    last_sync: Optional[str] = None
    age_seconds: Optional[float] = None
    status: str = "unknown"  # "fresh", "stale", "never_synced", "unknown"


class SyncStatusResponse(BaseModel):
    """Response for sync status endpoint."""
    success: bool = True
    data: dict = Field(default_factory=dict)
    error: Optional[str] = None


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_sync_status(
    session: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
):
    """
    Get last sync timestamps for all data sources.

    Returns the last sync time for positions, orders, fundamental data,
    and market data so the frontend can display freshness indicators.
    """
    from src.models.orm import CacheMetadataORM, PositionORM, OrderORM

    try:
        sources = []
        now = datetime.now(tz=None)  # naive UTC-like timestamp matching DB records

        # 1. FMP Fundamental Data — last cache warm
        fmp_record = session.query(CacheMetadataORM).filter_by(
            key="fmp_last_cache_warm"
        ).first()
        if fmp_record and fmp_record.value:
            try:
                fmp_ts = datetime.fromisoformat(fmp_record.value)
                age = (now - fmp_ts).total_seconds()
                sources.append(SyncSourceStatus(
                    source="fundamental_data",
                    last_sync=fmp_ts.isoformat() + "Z",
                    age_seconds=round(age, 0),
                    status="fresh" if age < 86400 else "stale",
                ))
            except (ValueError, TypeError):
                sources.append(SyncSourceStatus(source="fundamental_data", status="unknown"))
        else:
            sources.append(SyncSourceStatus(source="fundamental_data", status="never_synced"))

        # 2. Positions — use most recent position opened_at as proxy for last activity
        latest_position = (
            session.query(PositionORM)
            .order_by(PositionORM.opened_at.desc())
            .first()
        )
        if latest_position and latest_position.opened_at:
            pos_ts = latest_position.opened_at
            age = (now - pos_ts).total_seconds()
            sources.append(SyncSourceStatus(
                source="positions",
                last_sync=pos_ts.isoformat() + "Z",
                age_seconds=round(age, 0),
                status="fresh" if age < 300 else "stale",
            ))
        else:
            sources.append(SyncSourceStatus(source="positions", status="never_synced"))

        # 3. Orders — use most recent order submitted_at as proxy for last activity
        latest_order = (
            session.query(OrderORM)
            .order_by(OrderORM.submitted_at.desc())
            .first()
        )
        if latest_order and latest_order.submitted_at:
            ord_ts = latest_order.submitted_at
            age = (now - ord_ts).total_seconds()
            sources.append(SyncSourceStatus(
                source="orders",
                last_sync=ord_ts.isoformat() + "Z",
                age_seconds=round(age, 0),
                status="fresh" if age < 300 else "stale",
            ))
        else:
            sources.append(SyncSourceStatus(source="orders", status="never_synced"))

        # 4. Market Data — check historical price cache freshness
        market_data_record = session.query(CacheMetadataORM).filter_by(
            key="market_data_last_sync"
        ).first()
        if market_data_record and market_data_record.value:
            try:
                md_ts = datetime.fromisoformat(market_data_record.value)
                age = (now - md_ts).total_seconds()
                sources.append(SyncSourceStatus(
                    source="market_data",
                    last_sync=md_ts.isoformat() + "Z",
                    age_seconds=round(age, 0),
                    status="fresh" if age < 86400 else "stale",
                ))
            except (ValueError, TypeError):
                sources.append(SyncSourceStatus(source="market_data", status="unknown"))
        else:
            sources.append(SyncSourceStatus(source="market_data", status="never_synced"))

        return SyncStatusResponse(
            success=True,
            data={
                "sources": [s.model_dump() for s in sources],
                "checked_at": now.isoformat() + "Z",
            },
        )

    except Exception as e:
        logger.error(f"Error fetching sync status: {e}", exc_info=True)
        return SyncStatusResponse(
            success=False,
            data={},
            error=str(e),
        )



# Autonomous Cycle History


@router.get("/autonomous/cycles")
async def get_autonomous_cycles(
    limit: int = 20,
    session: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
):
    """
    Get autonomous cycle run history with metrics.

    Returns the most recent cycle runs ordered by start time descending.
    """
    from src.models.orm import AutonomousCycleRunORM

    try:
        runs = (
            session.query(AutonomousCycleRunORM)
            .order_by(AutonomousCycleRunORM.started_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "success": True,
            "data": [run.to_dict() for run in runs],
        }
    except Exception as e:
        logger.error(f"Error fetching cycle history: {e}", exc_info=True)
        return {
            "success": False,
            "data": [],
            "error": str(e),
        }

@router.post("/autonomous/cycles/delete")
async def delete_autonomous_cycles(
    request: dict,
    session: Session = Depends(get_db_session),
    _user: str = Depends(get_current_user),
):
    """Delete autonomous cycle run records by ID."""
    from src.models.orm import AutonomousCycleRunORM

    cycle_ids = request.get("cycle_ids", [])
    if not cycle_ids:
        return {"success": False, "deleted": 0, "error": "No cycle IDs provided"}
    try:
        deleted = session.query(AutonomousCycleRunORM).filter(
            AutonomousCycleRunORM.cycle_id.in_(cycle_ids)
        ).delete(synchronize_session=False)
        session.commit()
        return {"success": True, "deleted": deleted}
    except Exception as e:
        session.rollback()
        return {"success": False, "deleted": 0, "error": str(e)}



@router.post("/autonomous/clear-blacklists")
async def clear_blacklists(
    _user: str = Depends(get_current_user),
):
    """Clear WF validated combos, zero-trade blacklist, and in-memory WF cache."""
    import json
    from pathlib import Path

    cleared = []
    try:
        wf_path = Path("config/.wf_validated_combos.json")
        if wf_path.exists():
            with open(wf_path) as f:
                count = len(json.load(f))
            wf_path.write_text("{}")
            cleared.append(f"WF combos ({count} entries)")

        bl_path = Path("config/.zero_trade_blacklist.json")
        if bl_path.exists():
            with open(bl_path) as f:
                count = len(json.load(f))
            bl_path.write_text("{}")
            cleared.append(f"Zero-trade blacklist ({count} entries)")

        rej_path = Path("config/.rejection_blacklist.json")
        if rej_path.exists():
            with open(rej_path) as f:
                count = len(json.load(f))
            rej_path.write_text("{}")
            cleared.append(f"Rejection blacklist ({count} entries)")

        # Clear in-memory WF cache on the proposer singleton
        try:
            from src.core.trading_scheduler import get_trading_scheduler
            scheduler = get_trading_scheduler()
            if scheduler and hasattr(scheduler, '_strategy_engine'):
                engine = scheduler._strategy_engine
                if hasattr(engine, '_strategy_proposer') and engine._strategy_proposer:
                    cache_size = len(engine._strategy_proposer._wf_results_cache)
                    engine._strategy_proposer._wf_results_cache.clear()
                    cleared.append(f"In-memory WF cache ({cache_size} entries)")
        except Exception:
            pass

        return {"success": True, "message": f"Cleared: {', '.join(cleared) if cleared else 'nothing to clear'}"}
    except Exception as e:
        return {"success": False, "message": str(e)}
