"""Tests for RiskManager."""

import pytest
from datetime import datetime
from unittest.mock import Mock

from src.risk import RiskManager, ValidationResult
from src.models import (
    AccountInfo,
    Position,
    RiskConfig,
    TradingSignal,
    SignalAction,
    PositionSide,
    TradingMode,
)


@pytest.fixture
def risk_config():
    """Create default risk configuration."""
    return RiskConfig(
        max_position_size_pct=0.1,  # 10%
        max_exposure_pct=0.8,  # 80%
        max_daily_loss_pct=0.03,  # 3%
        max_drawdown_pct=0.10,  # 10%
        position_risk_pct=0.01,  # 1%
        stop_loss_pct=0.02,  # 2%
        take_profit_pct=0.04,  # 4%
    )


@pytest.fixture
def risk_manager(risk_config):
    """Create RiskManager with default config."""
    return RiskManager(risk_config)


@pytest.fixture
def account_info():
    """Create sample account information."""
    return AccountInfo(
        account_id="test_account",
        mode=TradingMode.DEMO,
        balance=10000.0,
        buying_power=8000.0,
        margin_used=2000.0,
        margin_available=8000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        positions_count=0,
        updated_at=datetime.now()
    )


@pytest.fixture
def sample_signal():
    """Create sample trading signal."""
    return TradingSignal(
        strategy_id="test_strategy",
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        reasoning="Test signal",
        generated_at=datetime.now(),
        metadata={}
    )


@pytest.fixture
def sample_position():
    """Create sample position.
    
    On eToro, quantity = dollar amount invested (not shares).
    invested_amount is the most accurate field.
    """
    return Position(
        id="pos_1",
        strategy_id="test_strategy",
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=1550.0,       # $1,550 invested (eToro: quantity = dollars)
        entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=50.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro_pos_1",
        stop_loss=147.0,
        take_profit=156.0,
        closed_at=None
    )


class TestRiskManagerInitialization:
    """Tests for RiskManager initialization."""

    def test_initialization(self, risk_config):
        """Test RiskManager initializes correctly."""
        manager = RiskManager(risk_config)
        
        assert manager.config == risk_config
        assert not manager.is_circuit_breaker_active()
        assert not manager.is_kill_switch_active()

    def test_get_status(self, risk_manager):
        """Test get_status returns correct information."""
        status = risk_manager.get_status()
        
        assert status["circuit_breaker_active"] is False
        assert status["kill_switch_active"] is False
        assert status["circuit_breaker_activated_at"] is None
        assert status["kill_switch_activated_at"] is None
        assert "config" in status


class TestSignalValidation:
    """Tests for signal validation."""

    def test_validate_entry_signal_success(self, risk_manager, sample_signal, account_info):
        """Test successful validation of entry signal."""
        result = risk_manager.validate_signal(sample_signal, account_info, [])
        
        assert result.is_valid is True
        assert result.position_size > 0
        assert "passed all risk checks" in result.reason.lower()

    def test_validate_exit_signal_always_allowed(self, risk_manager, account_info):
        """Test exit signals are always allowed."""
        exit_signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.EXIT_LONG,
            confidence=0.9,
            reasoning="Take profit",
            generated_at=datetime.now(),
            metadata={}
        )
        
        result = risk_manager.validate_signal(exit_signal, account_info, [])
        
        assert result.is_valid is True
        assert result.position_size == 0.0

    def test_validate_signal_blocked_by_kill_switch(self, risk_manager, sample_signal, account_info):
        """Test signals blocked when kill switch active."""
        risk_manager.execute_kill_switch("Test kill switch")
        
        result = risk_manager.validate_signal(sample_signal, account_info, [])
        
        assert result.is_valid is False
        assert "kill switch" in result.reason.lower()

    def test_validate_entry_blocked_by_circuit_breaker(self, risk_manager, sample_signal, account_info):
        """Test entry signals blocked when circuit breaker active."""
        risk_manager.activate_circuit_breaker()
        
        result = risk_manager.validate_signal(sample_signal, account_info, [])
        
        assert result.is_valid is False
        assert "circuit breaker" in result.reason.lower()

    def test_validate_exit_allowed_during_circuit_breaker(self, risk_manager, account_info):
        """Test exit signals allowed even when circuit breaker active."""
        risk_manager.activate_circuit_breaker()
        
        exit_signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.EXIT_LONG,
            confidence=0.9,
            reasoning="Exit during circuit breaker",
            generated_at=datetime.now(),
            metadata={}
        )
        
        result = risk_manager.validate_signal(exit_signal, account_info, [])
        
        assert result.is_valid is True


class TestPositionSizeCalculation:
    """Tests for position size calculation."""

    def test_calculate_position_size_basic(self, risk_manager, sample_signal, account_info):
        """Test basic position size calculation."""
        position_size = risk_manager.calculate_position_size(sample_signal, account_info, [])
        
        # With 1% risk and 2% stop loss: (10000 * 0.01) / 0.02 = 5000
        # But capped at 10% max position size = 1000
        assert position_size > 0
        assert position_size <= account_info.balance * risk_manager.config.max_position_size_pct

    def test_calculate_position_size_no_available_capital(self, risk_manager, sample_signal):
        """Test position size is zero when no available capital."""
        account = AccountInfo(
            account_id="test_account",
            mode=TradingMode.DEMO,
            balance=10000.0,
            buying_power=0.0,
            margin_used=10000.0,
            margin_available=0.0,
            daily_pnl=0.0,
            total_pnl=0.0,
            positions_count=5,
            updated_at=datetime.now()
        )
        
        # Create positions that consume all available capital.
        # On eToro, quantity = dollar amount invested.
        # Total exposure = $10,000 = 100% of balance → no capital left.
        existing_positions = [
            Position(
                id=f"pos_{i}",
                strategy_id="test_strategy",
                symbol=f"STOCK{i}",
                side=PositionSide.LONG,
                quantity=2000.0,  # $2,000 each
                entry_price=100.0,
                current_price=100.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id=f"etoro_pos_{i}",
                closed_at=None
            )
            for i in range(5)  # 5 × $2,000 = $10,000 total
        ]
        
        position_size = risk_manager.calculate_position_size(sample_signal, account, existing_positions)
        
        assert position_size == 0.0

    def test_calculate_position_size_respects_max_limit(self, risk_manager, sample_signal, account_info):
        """Test position size respects maximum position size limit."""
        position_size = risk_manager.calculate_position_size(sample_signal, account_info, [])
        
        max_position_size = account_info.balance * risk_manager.config.max_position_size_pct
        assert position_size <= max_position_size


class TestPositionLimits:
    """Tests for position limit checks."""

    def test_check_position_limits_new_position(self, risk_manager, account_info):
        """Test position limits for new position."""
        position_size = 500.0  # 5% of balance
        
        result = risk_manager.check_position_limits("AAPL", position_size, account_info, [])
        
        assert result is True

    def test_check_position_limits_exceeds_max(self, risk_manager, account_info):
        """Test position limits when exceeding maximum."""
        # Try to create position larger than max (10% = 1000)
        position_size = 1500.0
        
        result = risk_manager.check_position_limits("AAPL", position_size, account_info, [])
        
        assert result is False

    def test_check_position_limits_with_existing_position(self, risk_manager, account_info, sample_position):
        """Test position limits with existing position in same symbol."""
        # sample_position: quantity=$1,550 invested in AAPL
        # Max position: 10% of $10,000 = $1,000
        # Existing $1,550 already exceeds limit, so any new position should fail
        
        result = risk_manager.check_position_limits(
            "AAPL", 
            100.0, 
            account_info, 
            [sample_position]
        )
        
        assert result is False

    def test_check_position_limits_different_symbols(self, risk_manager, account_info, sample_position):
        """Test position limits for different symbols."""
        # Existing position in AAPL shouldn't affect GOOGL
        position_size = 500.0
        
        result = risk_manager.check_position_limits(
            "GOOGL", 
            position_size, 
            account_info, 
            [sample_position]
        )
        
        assert result is True


class TestExposureLimits:
    """Tests for exposure limit checks."""

    def test_check_exposure_limits_no_positions(self, risk_manager, account_info):
        """Test exposure limits with no existing positions."""
        position_size = 5000.0  # 50% of balance
        
        result = risk_manager.check_exposure_limits(position_size, account_info, [])
        
        assert result is True

    def test_check_exposure_limits_exceeds_max(self, risk_manager, account_info):
        """Test exposure limits when exceeding maximum."""
        # Max exposure: 80% of 10000 = 8000
        position_size = 9000.0
        
        result = risk_manager.check_exposure_limits(position_size, account_info, [])
        
        assert result is False

    def test_check_exposure_limits_with_existing_positions(self, risk_manager, account_info):
        """Test exposure limits with existing positions."""
        # Create positions totaling $6,000 (60% of $10K balance).
        # On eToro, quantity = dollar amount invested.
        positions = [
            Position(
                id=f"pos_{i}",
                strategy_id="test_strategy",
                symbol=f"STOCK{i}",
                side=PositionSide.LONG,
                quantity=1000.0,  # $1,000 each
                entry_price=100.0,
                current_price=100.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id=f"etoro_pos_{i}",
                closed_at=None
            )
            for i in range(6)  # 6 × $1,000 = $6,000
        ]
        
        # Try to add $3,000 more (total would be $9,000 = 90%, exceeds 80% limit)
        result = risk_manager.check_exposure_limits(3000.0, account_info, positions)
        
        assert result is False

    def test_check_exposure_limits_ignores_closed_positions(self, risk_manager, account_info, sample_position):
        """Test exposure limits ignores closed positions."""
        # Close the position
        sample_position.closed_at = datetime.now()
        
        # Should be able to use full exposure since closed position doesn't count
        position_size = 7000.0  # 70% of balance
        
        result = risk_manager.check_exposure_limits(position_size, account_info, [sample_position])
        
        assert result is True


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    def test_check_circuit_breaker_no_loss(self, risk_manager, account_info):
        """Test circuit breaker check with no loss."""
        result = risk_manager.check_circuit_breaker(account_info, 0.0)
        
        assert result is False

    def test_check_circuit_breaker_small_loss(self, risk_manager, account_info):
        """Test circuit breaker check with small loss."""
        # 2% loss (below 3% threshold)
        daily_pnl = -200.0
        
        result = risk_manager.check_circuit_breaker(account_info, daily_pnl)
        
        assert result is False

    def test_check_circuit_breaker_threshold_reached(self, risk_manager, account_info):
        """Test circuit breaker check when threshold reached."""
        # 3% loss (at threshold)
        daily_pnl = -300.0
        
        result = risk_manager.check_circuit_breaker(account_info, daily_pnl)
        
        assert result is True

    def test_check_circuit_breaker_threshold_exceeded(self, risk_manager, account_info):
        """Test circuit breaker check when threshold exceeded."""
        # 5% loss (exceeds 3% threshold)
        daily_pnl = -500.0
        
        result = risk_manager.check_circuit_breaker(account_info, daily_pnl)
        
        assert result is True

    def test_activate_circuit_breaker(self, risk_manager):
        """Test circuit breaker activation."""
        assert not risk_manager.is_circuit_breaker_active()
        
        risk_manager.activate_circuit_breaker()
        
        assert risk_manager.is_circuit_breaker_active()

    def test_activate_circuit_breaker_idempotent(self, risk_manager):
        """Test activating circuit breaker multiple times."""
        risk_manager.activate_circuit_breaker()
        risk_manager.activate_circuit_breaker()  # Should not error
        
        assert risk_manager.is_circuit_breaker_active()

    def test_reset_circuit_breaker(self, risk_manager):
        """Test circuit breaker reset."""
        risk_manager.activate_circuit_breaker()
        assert risk_manager.is_circuit_breaker_active()
        
        risk_manager.reset_circuit_breaker()
        
        assert not risk_manager.is_circuit_breaker_active()

    def test_reset_circuit_breaker_when_not_active(self, risk_manager):
        """Test resetting circuit breaker when not active."""
        risk_manager.reset_circuit_breaker()  # Should not error
        
        assert not risk_manager.is_circuit_breaker_active()


class TestKillSwitch:
    """Tests for kill switch functionality."""

    def test_execute_kill_switch(self, risk_manager):
        """Test kill switch execution."""
        assert not risk_manager.is_kill_switch_active()
        
        risk_manager.execute_kill_switch("Test emergency")
        
        assert risk_manager.is_kill_switch_active()

    def test_execute_kill_switch_idempotent(self, risk_manager):
        """Test executing kill switch multiple times."""
        risk_manager.execute_kill_switch("First reason")
        risk_manager.execute_kill_switch("Second reason")  # Should not error
        
        assert risk_manager.is_kill_switch_active()

    def test_reset_kill_switch(self, risk_manager):
        """Test kill switch reset."""
        risk_manager.execute_kill_switch("Test emergency")
        assert risk_manager.is_kill_switch_active()
        
        risk_manager.reset_kill_switch()
        
        assert not risk_manager.is_kill_switch_active()

    def test_reset_kill_switch_when_not_active(self, risk_manager):
        """Test resetting kill switch when not active."""
        risk_manager.reset_kill_switch()  # Should not error
        
        assert not risk_manager.is_kill_switch_active()

    def test_kill_switch_blocks_all_signals(self, risk_manager, sample_signal, account_info):
        """Test kill switch blocks all signals including exits."""
        risk_manager.execute_kill_switch("Test emergency")
        
        # Test entry signal
        entry_result = risk_manager.validate_signal(sample_signal, account_info, [])
        assert entry_result.is_valid is False
        
        # Test exit signal
        exit_signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.EXIT_LONG,
            confidence=0.9,
            reasoning="Exit",
            generated_at=datetime.now(),
            metadata={}
        )
        exit_result = risk_manager.validate_signal(exit_signal, account_info, [])
        assert exit_result.is_valid is False


class TestIntegration:
    """Integration tests for RiskManager."""

    def test_full_risk_workflow(self, risk_manager, account_info):
        """Test complete risk management workflow."""
        # Create a signal
        signal = TradingSignal(
            strategy_id="momentum_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.85,
            reasoning="Strong momentum",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal
        result = risk_manager.validate_signal(signal, account_info, [])
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Simulate loss and check circuit breaker
        account_info.daily_pnl = -350.0  # 3.5% loss
        should_activate = risk_manager.check_circuit_breaker(account_info, account_info.daily_pnl)
        assert should_activate is True
        
        # Activate circuit breaker
        risk_manager.activate_circuit_breaker()
        
        # Try to validate another entry signal
        result2 = risk_manager.validate_signal(signal, account_info, [])
        assert result2.is_valid is False
        
        # Exit signal should still work
        exit_signal = TradingSignal(
            strategy_id="momentum_strategy",
            symbol="AAPL",
            action=SignalAction.EXIT_LONG,
            confidence=0.9,
            reasoning="Circuit breaker exit",
            generated_at=datetime.now(),
            metadata={}
        )
        exit_result = risk_manager.validate_signal(exit_signal, account_info, [])
        assert exit_result.is_valid is True

    def test_position_accumulation_limits(self, risk_manager, account_info):
        """Test that multiple positions respect exposure limits."""
        positions = []
        
        # Add positions until we approach the limit
        for i in range(7):
            signal = TradingSignal(
                strategy_id="test_strategy",
                symbol=f"STOCK{i}",
                action=SignalAction.ENTER_LONG,
                confidence=0.8,
                reasoning="Test",
                generated_at=datetime.now(),
                metadata={}
            )
            
            result = risk_manager.validate_signal(signal, account_info, positions)
            
            if result.is_valid:
                # Create position
                pos = Position(
                    id=f"pos_{i}",
                    strategy_id="test_strategy",
                    symbol=f"STOCK{i}",
                    side=PositionSide.LONG,
                    quantity=result.position_size / 100.0,  # Assume $100 per share
                    entry_price=100.0,
                    current_price=100.0,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    opened_at=datetime.now(),
                    etoro_position_id=f"etoro_pos_{i}",
                    closed_at=None
                )
                positions.append(pos)
        
        # Calculate total exposure
        total_exposure = sum(p.quantity * p.current_price for p in positions)
        max_exposure = account_info.balance * risk_manager.config.max_exposure_pct
        
        # Should not exceed max exposure
        assert total_exposure <= max_exposure


class TestCorrelationAdjustedPositionSizing:
    """Tests for correlation-adjusted position sizing."""

    def test_correlation_adjustment_disabled(self, account_info):
        """Test that correlation adjustment can be disabled."""
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            correlation_adjustment_enabled=False
        )
        risk_manager = RiskManager(config)
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, [], None
        )
        
        assert adjusted_size == base_size
        assert "disabled" in reason.lower()

    def test_correlation_adjustment_same_symbol(self, risk_manager, account_info):
        """Test correlation adjustment for same symbol positions."""
        # Create existing position in AAPL
        existing_position = Position(
            id="pos_1",
            strategy_id="momentum_strategy_1",  # Use non-external strategy ID
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=50.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos_1",
            closed_at=None
        )
        
        # Create signal for same symbol
        signal = TradingSignal(
            strategy_id="momentum_strategy_2",  # Use non-external strategy ID
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, [existing_position], None
        )
        
        # Same symbol = correlation 1.0, so adjusted_size = base_size * (1 - 1.0 * 0.5) = base_size * 0.5
        expected_size = base_size * 0.5
        assert adjusted_size == expected_size
        assert "same symbol" in reason.lower()
        assert "1.0" in reason  # correlation value

    def test_correlation_adjustment_no_correlated_positions(self, risk_manager, account_info):
        """Test correlation adjustment when no correlated positions exist."""
        # Create existing position in different symbol
        existing_position = Position(
            id="pos_1",
            strategy_id="strategy_1",
            symbol="GOOGL",
            side=PositionSide.LONG,
            quantity=5.0,
            entry_price=100.0,
            current_price=105.0,
            unrealized_pnl=25.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos_1",
            closed_at=None
        )
        
        # Create signal for different symbol
        signal = TradingSignal(
            strategy_id="strategy_2",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, [existing_position], None
        )
        
        # No correlation, size should remain the same
        assert adjusted_size == base_size
        assert "no correlated positions" in reason.lower()

    def test_correlation_adjustment_ignores_external_positions(self, risk_manager, account_info):
        """Test that correlation adjustment ignores external positions."""
        # Create external position (eToro synced)
        external_position = Position(
            id="pos_1",
            strategy_id="etoro_position",  # External position
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=1500.0,  # Dollar amount for eToro positions
            entry_price=1.0,
            current_price=1.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos_1",
            closed_at=None
        )
        
        # Create signal for same symbol
        signal = TradingSignal(
            strategy_id="strategy_1",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, [external_position], None
        )
        
        # External positions should be ignored
        assert adjusted_size == base_size
        assert "no correlated positions" in reason.lower()

    def test_correlation_adjustment_ignores_closed_positions(self, risk_manager, account_info):
        """Test that correlation adjustment ignores closed positions."""
        # Create closed position
        closed_position = Position(
            id="pos_1",
            strategy_id="strategy_1",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=0.0,
            realized_pnl=50.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos_1",
            closed_at=datetime.now()  # Position is closed
        )
        
        # Create signal for same symbol
        signal = TradingSignal(
            strategy_id="strategy_2",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, [closed_position], None
        )
        
        # Closed positions should be ignored
        assert adjusted_size == base_size
        assert "no correlated positions" in reason.lower()

    def test_correlation_adjustment_formula(self, risk_manager, account_info):
        """Test the correlation adjustment formula: adjusted_size = base_size * (1 - correlation * 0.5)."""
        # Test with same symbol (correlation = 1.0)
        existing_position = Position(
            id="pos_1",
            strategy_id="momentum_strategy_1",  # Use non-external strategy ID
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=50.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos_1",
            closed_at=None
        )
        
        signal = TradingSignal(
            strategy_id="momentum_strategy_2",  # Use non-external strategy ID
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, [existing_position], None
        )
        
        # Formula: adjusted_size = base_size * (1 - correlation * 0.5)
        # With correlation = 1.0: adjusted_size = 1000 * (1 - 1.0 * 0.5) = 1000 * 0.5 = 500
        expected_size = base_size * (1 - 1.0 * 0.5)
        assert adjusted_size == expected_size

    def test_correlation_adjustment_multiple_same_symbol_positions(self, risk_manager, account_info):
        """Test correlation adjustment with multiple positions in the same symbol."""
        # Create multiple positions in AAPL
        positions = [
            Position(
                id=f"pos_{i}",
                strategy_id=f"momentum_strategy_{i}",  # Use non-external strategy IDs
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=150.0,
                current_price=155.0,
                unrealized_pnl=50.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id=f"etoro_pos_{i}",
                closed_at=None
            )
            for i in range(3)
        ]
        
        signal = TradingSignal(
            strategy_id="momentum_strategy_new",  # Use non-external strategy ID
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, positions, None
        )
        
        # Should still apply 50% reduction for same symbol
        expected_size = base_size * 0.5
        assert adjusted_size == expected_size
        # Check that reason mentions multiple positions
        assert "position(s)" in reason

    def test_validate_signal_with_correlation_adjustment(self, risk_manager, account_info):
        """Test that validate_signal applies correlation adjustment."""
        # Create existing position in AAPL from a different strategy (smaller position)
        existing_position = Position(
            id="pos_1",
            strategy_id="momentum_strategy_1",  # Use non-external strategy ID
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=2.0,  # Smaller quantity to avoid exceeding position limits
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=10.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos_1",
            closed_at=None
        )
        
        # Create signal for same symbol but different strategy
        signal = TradingSignal(
            strategy_id="momentum_strategy_2",  # Use non-external strategy ID
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal without existing positions first to get base size
        result_no_correlation = risk_manager.validate_signal(
            signal, account_info, [], strategy_allocation_pct=10.0
        )
        base_size_expected = result_no_correlation.position_size
        
        # Now validate with existing position
        result = risk_manager.validate_signal(
            signal, account_info, [existing_position], strategy_allocation_pct=10.0
        )
        
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Check metadata includes correlation adjustment info
        assert "base_position_size" in result.metadata
        assert "correlation_adjustment" in result.metadata
        
        # Position size should be less than base size due to same symbol correlation
        base_size = result.metadata["base_position_size"]
        assert result.position_size < base_size
        # Should be approximately 50% of base size (correlation = 1.0)
        assert abs(result.position_size - base_size * 0.5) < 1.0  # Allow small rounding error

    def test_correlation_adjustment_with_portfolio_manager_mock(self, risk_manager, account_info):
        """Test correlation adjustment with mocked PortfolioManager."""
        from unittest.mock import Mock
        
        # Create mock portfolio manager
        mock_pm = Mock()
        mock_pm.get_correlated_positions.return_value = [
            {
                'position_id': 'pos_1',
                'symbol': 'GOOGL',
                'strategy_id': 'strategy_1',
                'value': 1000.0,
                'correlation': 0.8,
                'reason': 'Strategy correlation 0.80'
            }
        ]
        
        signal = TradingSignal(
            strategy_id="strategy_2",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_correlation_adjusted_size(
            base_size, signal, [], mock_pm
        )
        
        # Formula: adjusted_size = base_size * (1 - 0.8 * 0.5) = 1000 * 0.6 = 600
        expected_size = base_size * (1 - 0.8 * 0.5)
        assert abs(adjusted_size - expected_size) < 0.01
        assert "0.8" in reason or "0.80" in reason  # correlation value
        assert "GOOGL" in reason



class TestRegimeBasedPositionSizing:
    """Tests for regime-based position sizing."""

    def test_regime_based_sizing_disabled(self, account_info):
        """Test that regime-based sizing can be disabled."""
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=False
        )
        risk_manager = RiskManager(config)
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, None
        )
        
        assert adjusted_size == base_size
        assert "disabled" in reason.lower()

    def test_regime_based_sizing_no_portfolio_manager(self, account_info):
        """Test regime-based sizing when no portfolio manager available."""
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True
        )
        risk_manager = RiskManager(config)
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, None
        )
        
        assert adjusted_size == base_size
        assert "no market analyzer" in reason.lower()

    def test_regime_based_sizing_high_volatility(self, account_info):
        """Test regime-based sizing reduces position in high volatility."""
        from unittest.mock import Mock
        from src.strategy.strategy_templates import MarketRegime
        
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True,
            regime_size_multipliers={
                "high_volatility": 0.5,
                "low_volatility": 1.0,
                "trending": 1.2,
                "ranging": 0.8
            }
        )
        risk_manager = RiskManager(config)
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.RANGING_HIGH_VOL,  # High volatility regime
            0.85,  # confidence
            "GOOD",  # data quality
            {}  # metrics
        )
        mock_pm.market_analyzer = mock_market_analyzer
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, mock_pm
        )
        
        # High volatility multiplier is 0.5
        expected_size = base_size * 0.5
        assert adjusted_size == expected_size
        assert "ranging_high_vol" in reason.lower()
        assert "0.5" in reason  # multiplier value

    def test_regime_based_sizing_low_volatility(self, account_info):
        """Test regime-based sizing maintains position in low volatility."""
        from unittest.mock import Mock
        from src.strategy.strategy_templates import MarketRegime
        
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True,
            regime_size_multipliers={
                "high_volatility": 0.5,
                "low_volatility": 1.0,
                "trending": 1.2,
                "ranging": 0.8
            }
        )
        risk_manager = RiskManager(config)
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.RANGING_LOW_VOL,  # Low volatility regime
            0.90,  # confidence
            "GOOD",  # data quality
            {}  # metrics
        )
        mock_pm.market_analyzer = mock_market_analyzer
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, mock_pm
        )
        
        # Low volatility multiplier is 1.0 (no change)
        expected_size = base_size * 1.0
        assert adjusted_size == expected_size
        assert "ranging_low_vol" in reason.lower()
        assert "1.0" in reason  # multiplier value

    def test_regime_based_sizing_trending(self, account_info):
        """Test regime-based sizing increases position in trending markets."""
        from unittest.mock import Mock
        from src.strategy.strategy_templates import MarketRegime
        
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True,
            regime_size_multipliers={
                "high_volatility": 0.5,
                "low_volatility": 1.0,
                "trending": 1.2,
                "ranging": 0.8
            }
        )
        risk_manager = RiskManager(config)
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.TRENDING_UP_STRONG,  # Trending regime
            0.92,  # confidence
            "GOOD",  # data quality
            {}  # metrics
        )
        mock_pm.market_analyzer = mock_market_analyzer
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, mock_pm
        )
        
        # Trending multiplier is 1.2
        expected_size = base_size * 1.2
        assert adjusted_size == expected_size
        assert "trending_up_strong" in reason.lower()
        assert "1.2" in reason  # multiplier value

    def test_regime_based_sizing_ranging(self, account_info):
        """Test regime-based sizing reduces position in ranging markets."""
        from unittest.mock import Mock
        from src.strategy.strategy_templates import MarketRegime
        
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True,
            regime_size_multipliers={
                "high_volatility": 0.5,
                "low_volatility": 1.0,
                "trending": 1.2,
                "ranging": 0.8
            }
        )
        risk_manager = RiskManager(config)
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.RANGING,  # Legacy ranging regime
            0.75,  # confidence
            "GOOD",  # data quality
            {}  # metrics
        )
        mock_pm.market_analyzer = mock_market_analyzer
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, mock_pm
        )
        
        # Ranging multiplier is 0.8
        expected_size = base_size * 0.8
        assert adjusted_size == expected_size
        assert "ranging" in reason.lower()
        assert "0.8" in reason  # multiplier value

    def test_regime_based_sizing_custom_multipliers(self, account_info):
        """Test regime-based sizing with custom multipliers."""
        from unittest.mock import Mock
        from src.strategy.strategy_templates import MarketRegime
        
        # Custom multipliers
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True,
            regime_size_multipliers={
                "high_volatility": 0.3,  # More conservative
                "low_volatility": 1.5,   # More aggressive
                "trending": 1.5,
                "ranging": 0.6
            }
        )
        risk_manager = RiskManager(config)
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.RANGING_HIGH_VOL,
            0.85,
            "GOOD",
            {}
        )
        mock_pm.market_analyzer = mock_market_analyzer
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, mock_pm
        )
        
        # Custom high volatility multiplier is 0.3
        expected_size = base_size * 0.3
        assert adjusted_size == expected_size
        assert "0.3" in reason  # custom multiplier value

    def test_regime_based_sizing_error_handling(self, account_info):
        """Test regime-based sizing handles errors gracefully."""
        from unittest.mock import Mock
        
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True
        )
        risk_manager = RiskManager(config)
        
        # Create mock portfolio manager that raises exception
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.side_effect = Exception("Market data unavailable")
        mock_pm.market_analyzer = mock_market_analyzer
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        base_size = 1000.0
        adjusted_size, reason = risk_manager.calculate_regime_adjusted_size(
            base_size, signal, mock_pm
        )
        
        # Should return base size on error
        assert adjusted_size == base_size
        assert "failed" in reason.lower()
        assert "Market data unavailable" in reason

    def test_validate_signal_with_regime_adjustment(self, account_info):
        """Test that validate_signal applies regime-based adjustment."""
        from unittest.mock import Mock
        from src.strategy.strategy_templates import MarketRegime
        
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            regime_based_sizing_enabled=True,
            regime_size_multipliers={
                "high_volatility": 0.5,
                "low_volatility": 1.0,
                "trending": 1.2,
                "ranging": 0.8
            }
        )
        risk_manager = RiskManager(config)
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.RANGING_HIGH_VOL,  # High volatility
            0.85,
            "GOOD",
            {}
        )
        mock_pm.market_analyzer = mock_market_analyzer
        mock_pm.get_correlated_positions.return_value = []  # No correlated positions
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal without regime adjustment first
        result_no_regime = risk_manager.validate_signal(
            signal, account_info, [], strategy_allocation_pct=10.0, portfolio_manager=None
        )
        base_size_expected = result_no_regime.position_size
        
        # Now validate with regime adjustment
        result = risk_manager.validate_signal(
            signal, account_info, [], strategy_allocation_pct=10.0, portfolio_manager=mock_pm
        )
        
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Check metadata includes regime adjustment info
        assert "regime_adjustment" in result.metadata
        
        # Position size should be less than without regime adjustment (0.5x multiplier)
        # Note: correlation adjustment is also applied, so we check the metadata
        regime_reason = result.metadata["regime_adjustment"]
        assert "ranging_high_vol" in regime_reason.lower()
        assert "0.5" in regime_reason

    def test_regime_based_sizing_combined_with_correlation(self, account_info):
        """Test regime-based sizing works together with correlation adjustment."""
        from unittest.mock import Mock
        from src.strategy.strategy_templates import MarketRegime
        
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            correlation_adjustment_enabled=True,
            regime_based_sizing_enabled=True,
            regime_size_multipliers={
                "high_volatility": 0.5,
                "low_volatility": 1.0,
                "trending": 1.2,
                "ranging": 0.8
            }
        )
        risk_manager = RiskManager(config)
        
        # Create existing position in same symbol
        existing_position = Position(
            id="pos_1",
            strategy_id="momentum_strategy_1",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=2.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=10.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos_1",
            closed_at=None
        )
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.TRENDING_UP_STRONG,  # Trending (1.2x multiplier)
            0.92,
            "GOOD",
            {}
        )
        mock_pm.market_analyzer = mock_market_analyzer
        mock_pm.get_correlated_positions.return_value = []  # No strategy correlation
        
        signal = TradingSignal(
            strategy_id="momentum_strategy_2",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        result = risk_manager.validate_signal(
            signal, account_info, [existing_position], 
            strategy_allocation_pct=10.0, portfolio_manager=mock_pm
        )
        
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Check both adjustments are in metadata
        assert "correlation_adjustment" in result.metadata
        assert "regime_adjustment" in result.metadata
        
        # Correlation adjustment should mention same symbol
        correlation_reason = result.metadata["correlation_adjustment"]
        assert "same symbol" in correlation_reason.lower()
        
        # Regime adjustment should mention trending
        regime_reason = result.metadata["regime_adjustment"]
        assert "trending" in regime_reason.lower()
        assert "1.2" in regime_reason
