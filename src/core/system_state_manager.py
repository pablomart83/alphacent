"""
System state manager for autonomous trading state.

Manages system state transitions and persistence.
Validates: Requirements 11.12, 14.1, 16.12
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.models.enums import SystemStateEnum
from src.models.dataclasses import SystemState
from src.models.orm import SystemStateORM, StateTransitionHistoryORM
from src.models.database import get_database

logger = logging.getLogger(__name__)


class StateTransitionError(Exception):
    """Error during state transition."""
    pass


class SystemStateManager:
    """
    Manages autonomous trading system state with persistence.
    
    Validates: Requirements 11.12, 14.1, 16.12
    """
    
    def __init__(self, service_manager=None):
        """
        Initialize system state manager.
        
        Args:
            service_manager: Optional ServiceManager instance for service checks
        """
        self._current_state: Optional[SystemState] = None
        self._startup_time: datetime = datetime.now()
        self._service_manager = service_manager
        logger.info("SystemStateManager initialized")
    
    def get_current_state(self) -> SystemState:
        """
        Get current system state.
        
        Returns:
            Current system state
        """
        if self._current_state is None:
            # Load from database or initialize
            self._current_state = self._load_state_from_db()
            if self._current_state is None:
                # Initialize with STOPPED state
                self._current_state = SystemState(
                    state=SystemStateEnum.STOPPED,
                    timestamp=datetime.now(),
                    reason="System initialized",
                    initiated_by=None,
                    active_strategies_count=0,
                    open_positions_count=0,
                    uptime_seconds=0,
                    last_signal_generated=None,
                    last_order_executed=None
                )
                self._save_state_to_db(self._current_state)
        
        # Update uptime
        self._current_state.uptime_seconds = int(
            (datetime.now() - self._startup_time).total_seconds()
        )
        
        return self._current_state
    
    def transition_to(
        self,
        new_state: SystemStateEnum,
        reason: str,
        initiated_by: Optional[str] = None
    ) -> SystemState:
        """
        Transition to new system state.
        
        Args:
            new_state: Target state
            reason: Reason for transition
            initiated_by: Username who initiated transition
            
        Returns:
            New system state
            
        Raises:
            StateTransitionError: If transition fails
            
        Validates: Requirements 11.12, 16.12, 16.1.2, 16.1.3, 16.1.4, 16.1.5
        """
        current = self.get_current_state()
        old_state = current.state
        
        # If already in target state, return current state (idempotent)
        if old_state == new_state:
            logger.info(f"Already in {new_state.value} state, no transition needed")
            return current
        
        # Validate transition
        if not self._is_valid_transition(old_state, new_state):
            logger.error(
                f"Invalid state transition: {old_state.value} -> {new_state.value}"
            )
            raise StateTransitionError(
                f"Invalid state transition: {old_state.value} -> {new_state.value}"
            )
        
        # Check service dependencies for ACTIVE state (currently no external services required)
        if new_state == SystemStateEnum.ACTIVE and self._service_manager:
            logger.info("Checking service dependencies before transitioning to ACTIVE")
            
            all_healthy, failed_services = self._service_manager.ensure_services_running()
            
            if not all_healthy:
                error_msg = (
                    f"Cannot start autonomous trading: "
                    f"services not available: {', '.join(failed_services)}"
                )
                logger.error(error_msg)
                
                # Transition to PAUSED instead
                paused_state = SystemState(
                    state=SystemStateEnum.PAUSED,
                    timestamp=datetime.now(),
                    reason=f"Required services unavailable: {', '.join(failed_services)}",
                    initiated_by=initiated_by,
                    active_strategies_count=current.active_strategies_count,
                    open_positions_count=current.open_positions_count,
                    uptime_seconds=current.uptime_seconds,
                    last_signal_generated=current.last_signal_generated,
                    last_order_executed=current.last_order_executed
                )
                
                self._save_state_to_db(paused_state)
                self._record_transition(old_state, paused_state)
                self._current_state = paused_state
                
                raise StateTransitionError(
                    f"Services unavailable: {', '.join(failed_services)}. "
                    f"System transitioned to PAUSED. Please start required services."
                )
        
        # Create new state
        new_state_obj = SystemState(
            state=new_state,
            timestamp=datetime.now(),
            reason=reason,
            initiated_by=initiated_by,
            active_strategies_count=current.active_strategies_count,
            open_positions_count=current.open_positions_count,
            uptime_seconds=current.uptime_seconds,
            last_signal_generated=current.last_signal_generated,
            last_order_executed=current.last_order_executed
        )
        
        # Save to database
        self._save_state_to_db(new_state_obj)
        
        # Record transition history
        self._record_transition(old_state, new_state_obj)
        
        # Update current state
        self._current_state = new_state_obj
        
        logger.info(
            f"State transition: {old_state.value} -> {new_state.value}, "
            f"reason: {reason}, by: {initiated_by or 'system'}"
        )
        
        return new_state_obj
    
    def update_counts(
        self,
        active_strategies: Optional[int] = None,
        open_positions: Optional[int] = None
    ):
        """
        Update strategy and position counts.
        
        Args:
            active_strategies: Number of active strategies
            open_positions: Number of open positions
        """
        current = self.get_current_state()
        
        if active_strategies is not None:
            current.active_strategies_count = active_strategies
        
        if open_positions is not None:
            current.open_positions_count = open_positions
        
        self._save_state_to_db(current)
    
    def record_signal_generated(self):
        """Record that a signal was generated."""
        current = self.get_current_state()
        current.last_signal_generated = datetime.now()
        self._save_state_to_db(current)
    
    def record_order_executed(self):
        """Record that an order was executed."""
        current = self.get_current_state()
        current.last_order_executed = datetime.now()
        self._save_state_to_db(current)
    
    def _is_valid_transition(
        self,
        from_state: SystemStateEnum,
        to_state: SystemStateEnum
    ) -> bool:
        """
        Check if state transition is valid.
        
        Args:
            from_state: Current state
            to_state: Target state
            
        Returns:
            True if transition is valid
        """
        # Define valid transitions
        valid_transitions = {
            SystemStateEnum.STOPPED: {
                SystemStateEnum.ACTIVE,
            },
            SystemStateEnum.ACTIVE: {
                SystemStateEnum.PAUSED,
                SystemStateEnum.STOPPED,
                SystemStateEnum.EMERGENCY_HALT,
            },
            SystemStateEnum.PAUSED: {
                SystemStateEnum.ACTIVE,
                SystemStateEnum.STOPPED,
            },
            SystemStateEnum.EMERGENCY_HALT: {
                SystemStateEnum.STOPPED,
            },
        }
        
        return to_state in valid_transitions.get(from_state, set())
    
    def _load_state_from_db(self) -> Optional[SystemState]:
        """
        Load current state from database.
        
        Returns:
            Current system state or None if not found
            
        Validates: Requirement 14.1
        """
        try:
            db = get_database()
            session = db.get_session()
            
            # Get current state (is_current = 1)
            state_orm = session.query(SystemStateORM).filter(
                SystemStateORM.is_current == 1
            ).first()
            
            if state_orm:
                return SystemState(
                    state=state_orm.state,
                    timestamp=state_orm.timestamp,
                    reason=state_orm.reason,
                    initiated_by=state_orm.initiated_by,
                    active_strategies_count=state_orm.active_strategies_count,
                    open_positions_count=state_orm.open_positions_count,
                    uptime_seconds=state_orm.uptime_seconds,
                    last_signal_generated=state_orm.last_signal_generated,
                    last_order_executed=state_orm.last_order_executed
                )
            
            return None
        
        except Exception as e:
            logger.error(f"Error loading state from database: {e}")
            return None
    
    def _save_state_to_db(self, state: SystemState):
        """
        Save state to database.
        
        Args:
            state: System state to save
            
        Validates: Requirement 14.1
        """
        try:
            db = get_database()
            session = db.get_session()
            
            # Mark all existing states as not current
            session.query(SystemStateORM).update({"is_current": 0})
            
            # Create new state record
            state_orm = SystemStateORM(
                state=state.state,
                timestamp=state.timestamp,
                reason=state.reason,
                initiated_by=state.initiated_by,
                active_strategies_count=state.active_strategies_count,
                open_positions_count=state.open_positions_count,
                uptime_seconds=state.uptime_seconds,
                last_signal_generated=state.last_signal_generated,
                last_order_executed=state.last_order_executed,
                is_current=1
            )
            
            session.add(state_orm)
            session.commit()
            
            logger.debug(f"State saved to database: {state.state.value}")
        
        except Exception as e:
            logger.error(f"Error saving state to database: {e}")
            session.rollback()
    
    def _record_transition(
        self,
        from_state: SystemStateEnum,
        to_state_obj: SystemState
    ):
        """
        Record state transition in history.
        
        Args:
            from_state: Previous state
            to_state_obj: New state object
            
        Validates: Requirement 14.1
        """
        try:
            db = get_database()
            session = db.get_session()
            
            transition = StateTransitionHistoryORM(
                from_state=from_state,
                to_state=to_state_obj.state,
                timestamp=to_state_obj.timestamp,
                reason=to_state_obj.reason,
                initiated_by=to_state_obj.initiated_by,
                active_strategies_count=to_state_obj.active_strategies_count,
                open_positions_count=to_state_obj.open_positions_count
            )
            
            session.add(transition)
            session.commit()
            
            logger.debug(
                f"Transition recorded: {from_state.value} -> {to_state_obj.state.value}"
            )
        
        except Exception as e:
            logger.error(f"Error recording transition: {e}")
            session.rollback()


# Global system state manager instance
_state_manager: Optional[SystemStateManager] = None


def get_system_state_manager() -> SystemStateManager:
    """
    Get or create global system state manager instance.
    
    Returns:
        SystemStateManager instance
    """
    global _state_manager
    if _state_manager is None:
        _state_manager = SystemStateManager()
    return _state_manager
