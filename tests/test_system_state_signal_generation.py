"""
Test system state checks in signal generation.

Validates: Requirements 11.12, 11.16, 16.12
"""

import logging
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.models.dataclasses import Strategy, SystemState
from src.models.enums import StrategyStatus, SystemStateEnum
from src.strategy.strategy_engine import StrategyEngine

logger = logging.getLogger(__name__)


class TestSystemStateSignalGeneration:
    """Test system state checks in signal generation."""
    
    @pytest.fixture
    def mock_market_data(self):
        """Mock market data manager."""
        return Mock()
    
    @pytest.fixture
    def mock_llm_service(self):
        """Mock LLM service."""
        return Mock()
    
    @pytest.fixture
    def strategy_engine(self, mock_llm_service, mock_market_data):
        """Create strategy engine with mocked dependencies."""
        return StrategyEngine(mock_llm_service, mock_market_data)
    
    @pytest.fixture
    def active_strategy(self):
        """Create an active strategy for testing."""
        return Strategy(
            id="test_strategy_1",
            name="Test Strategy",
            description="Test strategy for signal generation",
            status=StrategyStatus.LIVE,
            rules={"type": "momentum"},
            symbols=["AAPL", "GOOGL"],
            risk_params=Mock(),
            created_at=datetime.now(),
            activated_at=datetime.now(),
            retired_at=None,
            performance=Mock()
        )
    
    @patch('src.core.system_state_manager.get_system_state_manager')
    def test_signal_generation_skipped_when_paused(
        self,
        mock_get_state_manager,
        strategy_engine,
        active_strategy
    ):
        """Test that signal generation is skipped when system is PAUSED."""
        # Setup: System state is PAUSED
        mock_state_manager = Mock()
        mock_state = SystemState(
            state=SystemStateEnum.PAUSED,
            timestamp=datetime.now(),
            reason="User paused trading",
            initiated_by="test_user",
            active_strategies_count=1,
            open_positions_count=0,
            uptime_seconds=100,
            last_signal_generated=None,
            last_order_executed=None
        )
        mock_state_manager.get_current_state.return_value = mock_state
        mock_get_state_manager.return_value = mock_state_manager
        
        # Execute: Try to generate signals
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify: No signals generated
        assert signals == []
        logger.info("✓ Signal generation correctly skipped when system is PAUSED")
    
    @patch('src.core.system_state_manager.get_system_state_manager')
    def test_signal_generation_skipped_when_stopped(
        self,
        mock_get_state_manager,
        strategy_engine,
        active_strategy
    ):
        """Test that signal generation is skipped when system is STOPPED."""
        # Setup: System state is STOPPED
        mock_state_manager = Mock()
        mock_state = SystemState(
            state=SystemStateEnum.STOPPED,
            timestamp=datetime.now(),
            reason="User stopped trading",
            initiated_by="test_user",
            active_strategies_count=0,
            open_positions_count=0,
            uptime_seconds=0,
            last_signal_generated=None,
            last_order_executed=None
        )
        mock_state_manager.get_current_state.return_value = mock_state
        mock_get_state_manager.return_value = mock_state_manager
        
        # Execute: Try to generate signals
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify: No signals generated
        assert signals == []
        logger.info("✓ Signal generation correctly skipped when system is STOPPED")
    
    @patch('src.core.system_state_manager.get_system_state_manager')
    def test_signal_generation_skipped_when_emergency_halt(
        self,
        mock_get_state_manager,
        strategy_engine,
        active_strategy
    ):
        """Test that signal generation is skipped when system is in EMERGENCY_HALT."""
        # Setup: System state is EMERGENCY_HALT
        mock_state_manager = Mock()
        mock_state = SystemState(
            state=SystemStateEnum.EMERGENCY_HALT,
            timestamp=datetime.now(),
            reason="Kill switch activated",
            initiated_by="system",
            active_strategies_count=0,
            open_positions_count=0,
            uptime_seconds=500,
            last_signal_generated=None,
            last_order_executed=None
        )
        mock_state_manager.get_current_state.return_value = mock_state
        mock_get_state_manager.return_value = mock_state_manager
        
        # Execute: Try to generate signals
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify: No signals generated
        assert signals == []
        logger.info("✓ Signal generation correctly skipped when system is in EMERGENCY_HALT")
    
    @patch('src.core.system_state_manager.get_system_state_manager')
    def test_signal_generation_proceeds_when_active(
        self,
        mock_get_state_manager,
        strategy_engine,
        active_strategy,
        mock_market_data
    ):
        """Test that signal generation proceeds when system is ACTIVE."""
        # Setup: System state is ACTIVE
        mock_state_manager = Mock()
        mock_state = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="User started trading",
            initiated_by="test_user",
            active_strategies_count=1,
            open_positions_count=0,
            uptime_seconds=300,
            last_signal_generated=None,
            last_order_executed=None
        )
        mock_state_manager.get_current_state.return_value = mock_state
        mock_get_state_manager.return_value = mock_state_manager
        
        # Mock market data to return insufficient data (so no signals generated, but method proceeds)
        mock_market_data.get_historical_data.return_value = []
        
        # Execute: Try to generate signals
        signals = strategy_engine.generate_signals(active_strategy)
        
        # Verify: Method proceeded (even if no signals due to insufficient data)
        # The key is that it didn't return early due to state check
        assert isinstance(signals, list)
        mock_market_data.get_historical_data.assert_called()
        logger.info("✓ Signal generation correctly proceeds when system is ACTIVE")
    
    @patch('src.core.system_state_manager.get_system_state_manager')
    def test_signal_generation_fails_for_inactive_strategy(
        self,
        mock_get_state_manager,
        strategy_engine
    ):
        """Test that signal generation fails for strategies not in DEMO or LIVE status."""
        # Setup: Mock system state as ACTIVE
        mock_state_manager = Mock()
        mock_state = SystemState(
            state=SystemStateEnum.ACTIVE,
            timestamp=datetime.now(),
            reason="User started trading",
            initiated_by="test_user",
            active_strategies_count=1,
            open_positions_count=0,
            uptime_seconds=300,
            last_signal_generated=None,
            last_order_executed=None
        )
        mock_state_manager.get_current_state.return_value = mock_state
        mock_get_state_manager.return_value = mock_state_manager
        
        # Setup: Strategy in PROPOSED status
        inactive_strategy = Strategy(
            id="test_strategy_2",
            name="Inactive Strategy",
            description="Strategy not yet activated",
            status=StrategyStatus.PROPOSED,
            rules={"type": "momentum"},
            symbols=["AAPL"],
            risk_params=Mock(),
            created_at=datetime.now(),
            activated_at=None,
            retired_at=None,
            performance=Mock()
        )
        
        # Execute & Verify: Should raise ValueError
        with pytest.raises(ValueError, match="Cannot generate signals for strategy in StrategyStatus.PROPOSED status"):
            strategy_engine.generate_signals(inactive_strategy)
        
        logger.info("✓ Signal generation correctly fails for inactive strategy")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
