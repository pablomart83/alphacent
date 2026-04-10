"""Integration tests for position management features.

This test suite validates the integration of all position management features:
- Trailing stop-loss logic
- Partial exit strategies
- Correlation-adjusted position sizing
- Order cancellation
- Slippage tracking
- Regime-based position sizing

Tests use real components where possible and mocks only for external dependencies.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal

from src.execution.position_manager import PositionManager
from src.risk import RiskManager
from src.core.order_monitor import OrderMonitor
from src.monitoring.execution_quality import ExecutionQualityTracker
from src.models.dataclasses import (
    Position, Order, RiskConfig, AccountInfo, TradingSignal
)
from src.models.enums import (
    PositionSide, OrderSide, OrderType, OrderStatus, 
    SignalAction, TradingMode
)
from src.api.etoro_client import EToroAPIError
from src.strategy.strategy_templates import MarketRegime


@pytest.fixture
def mock_etoro_client():
    """Create mock eToro client for testing."""
    client = Mock()
    client.update_position_stop_loss = Mock(return_value={"success": True})
    client.place_order = Mock(return_value={
        "order_id": "etoro_order_123",
        "status": "submitted",
        "filled_price": None
    })
    client.cancel_order = Mock(return_value={"success": True})
    client.get_order_status = Mock(return_value={
        "status": "filled",
        "filled_price": 110.5,
        "filled_at": datetime.now().isoformat()
    })
    return client


@pytest.fixture
def risk_config_full_features():
    """Create risk config with all position management features enabled."""
    return RiskConfig(
        # Basic risk settings
        max_position_size_pct=0.1,
        max_exposure_pct=0.8,
        max_daily_loss_pct=0.03,
        max_drawdown_pct=0.10,
        position_risk_pct=0.01,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
        
        # Trailing stops
        trailing_stop_enabled=True,
        trailing_stop_activation_pct=0.05,  # 5% profit to activate
        trailing_stop_distance_pct=0.03,     # 3% trailing distance
        
        # Partial exits
        partial_exit_enabled=True,
        partial_exit_levels=[
            {"profit_pct": 0.05, "exit_pct": 0.3},  # 5% profit -> 30% exit
            {"profit_pct": 0.10, "exit_pct": 0.5},  # 10% profit -> 50% exit
        ],
        
        # Correlation adjustment
        correlation_adjustment_enabled=True,
        
        # Regime-based sizing
        regime_based_sizing_enabled=True,
        regime_size_multipliers={
            "high_volatility": 0.5,
            "low_volatility": 1.0,
            "trending": 1.2,
            "ranging": 0.8
        }
    )


@pytest.fixture
def account_info():
    """Create sample account information."""
    return AccountInfo(
        account_id="test_account",
        mode=TradingMode.DEMO,
        balance=100000.0,  # Increased from 10000 to avoid position size limits
        buying_power=80000.0,
        margin_used=20000.0,
        margin_available=80000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        positions_count=0,
        updated_at=datetime.now()
    )


class TestTrailingStopsIntegration:
    """Integration tests for trailing stop-loss functionality."""

    def test_trailing_stops_with_profitable_position(
        self, mock_etoro_client, risk_config_full_features
    ):
        """Test trailing stops activate and update for profitable position."""
        manager = PositionManager(mock_etoro_client, risk_config_full_features)
        
        # Create profitable position (10% profit)
        position = Position(
            id="pos1",
            strategy_id="momentum_strategy",
            symbol="SPY",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=100.0,
            current_price=110.0,  # 10% profit
            unrealized_pnl=100.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos1",
            stop_loss=95.0,  # Old stop-loss
            take_profit=120.0,
            closed_at=None
        )
        
        # Check trailing stops
        orders = manager.check_trailing_stops([position])
        
        # Verify stop-loss was updated via API
        mock_etoro_client.update_position_stop_loss.assert_called_once()
        call_args = mock_etoro_client.update_position_stop_loss.call_args
        
        # Expected new stop: 110 * (1 - 0.03) = 106.7
        expected_stop = 110.0 * 0.97
        assert call_args[1]["position_id"] == "etoro_pos1"
        assert abs(call_args[1]["stop_loss_rate"] - expected_stop) < 0.01
        
        # Verify position was updated locally
        assert abs(position.stop_loss - expected_stop) < 0.01

    def test_trailing_stops_multiple_positions_mixed_profit(
        self, mock_etoro_client, risk_config_full_features
    ):
        """Test trailing stops handle multiple positions with different profit levels."""
        manager = PositionManager(mock_etoro_client, risk_config_full_features)
        
        positions = [
            # Position 1: High profit, should update
            Position(
                id="pos1",
                strategy_id="strat1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=10.0,
                entry_price=100.0,
                current_price=110.0,  # 10% profit
                unrealized_pnl=100.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos1",
                stop_loss=95.0,
                take_profit=120.0,
                closed_at=None
            ),
            # Position 2: Low profit, should not update
            Position(
                id="pos2",
                strategy_id="strat2",
                symbol="QQQ",
                side=PositionSide.LONG,
                quantity=5.0,
                entry_price=200.0,
                current_price=203.0,  # 1.5% profit (below 5% threshold)
                unrealized_pnl=15.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos2",
                stop_loss=190.0,
                take_profit=220.0,
                closed_at=None
            ),
            # Position 3: High profit, should update
            Position(
                id="pos3",
                strategy_id="strat3",
                symbol="AAPL",
                side=PositionSide.LONG,
                quantity=20.0,
                entry_price=150.0,
                current_price=165.0,  # 10% profit
                unrealized_pnl=300.0,
                realized_pnl=0.0,
                opened_at=datetime.now(),
                etoro_position_id="etoro_pos3",
                stop_loss=145.0,
                take_profit=180.0,
                closed_at=None
            )
        ]
        
        orders = manager.check_trailing_stops(positions)
        
        # Should update 2 positions (pos1 and pos3)
        assert mock_etoro_client.update_position_stop_loss.call_count == 2
        
        # Verify the correct positions were updated
        calls = mock_etoro_client.update_position_stop_loss.call_args_list
        updated_position_ids = {call[1]["position_id"] for call in calls}
        assert updated_position_ids == {"etoro_pos1", "etoro_pos3"}


class TestPartialExitsIntegration:
    """Integration tests for partial exit functionality."""

    def test_partial_exits_with_profit_levels(
        self, mock_etoro_client, risk_config_full_features
    ):
        """Test partial exits trigger at configured profit levels."""
        manager = PositionManager(mock_etoro_client, risk_config_full_features)
        
        # Create position with 15% profit (triggers both levels: 5% and 10%)
        position = Position(
            id="pos1",
            strategy_id="momentum_strategy",
            symbol="SPY",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=100.0,
            current_price=115.0,  # 15% profit
            unrealized_pnl=1500.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos1",
            stop_loss=95.0,
            take_profit=130.0,
            closed_at=None,
            partial_exits=[]
        )
        
        # Check partial exits
        orders = manager.check_partial_exits([position])
        
        # Should create 2 orders (one for each level)
        assert len(orders) == 2
        
        # First order: 30% of 100.0 = 30.0
        assert orders[0].symbol == "SPY"
        assert orders[0].side == OrderSide.SELL
        assert orders[0].quantity == 30.0
        assert orders[0].order_type == OrderType.MARKET
        
        # Second order: 50% of 100.0 = 50.0
        assert orders[1].quantity == 50.0
        
        # Verify partial exits were recorded
        assert len(position.partial_exits) == 2
        
        # Verify position quantity was reduced
        assert position.quantity == 20.0  # 100 - 30 - 50

    def test_partial_exits_not_retriggered(
        self, mock_etoro_client, risk_config_full_features
    ):
        """Test partial exits are not triggered again for same level."""
        manager = PositionManager(mock_etoro_client, risk_config_full_features)
        
        # Create position with existing partial exit
        position = Position(
            id="pos1",
            strategy_id="momentum_strategy",
            symbol="SPY",
            side=PositionSide.LONG,
            quantity=70.0,  # Already reduced from 100
            entry_price=100.0,
            current_price=115.0,  # 15% profit
            unrealized_pnl=1050.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos1",
            closed_at=None,
            partial_exits=[
                {
                    "profit_level": "0.0500",  # Already triggered 5% level
                    "profit_pct": 0.08,
                    "exit_pct": 0.3,
                    "exit_quantity": 30.0,
                    "exit_price": 108.0,
                    "timestamp": datetime.now().isoformat()
                }
            ]
        )
        
        # Check partial exits again
        orders = manager.check_partial_exits([position])
        
        # Should only create 1 order (for 10% level, not 5%)
        # Exit quantity is 50% of CURRENT quantity (70), not original (100)
        assert len(orders) == 1
        assert orders[0].quantity == 35.0  # 50% of current 70


class TestCorrelationAdjustedSizingIntegration:
    """Integration tests for correlation-adjusted position sizing."""

    def test_correlation_adjustment_with_same_symbol(
        self, mock_etoro_client, risk_config_full_features, account_info
    ):
        """Test correlation adjustment reduces size for same symbol positions."""
        risk_manager = RiskManager(risk_config_full_features)
        
        # Create existing position in AAPL
        existing_position = Position(
            id="pos1",
            strategy_id="momentum_strategy_1",
            symbol="AAPL",
            side=PositionSide.LONG,
            quantity=5.0,
            entry_price=150.0,
            current_price=155.0,
            unrealized_pnl=25.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos1",
            closed_at=None
        )
        
        # Create signal for same symbol
        signal = TradingSignal(
            strategy_id="momentum_strategy_2",
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Strong momentum",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal with correlation adjustment
        result = risk_manager.validate_signal(
            signal, account_info, [existing_position], 
            strategy_allocation_pct=10.0
        )
        
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Check metadata includes correlation adjustment
        assert "correlation_adjustment" in result.metadata
        correlation_reason = result.metadata["correlation_adjustment"]
        assert "same symbol" in correlation_reason.lower()
        assert "1.0" in correlation_reason  # correlation value
        
        # Position size should be reduced (50% of base size)
        base_size = result.metadata.get("base_position_size", 0)
        if base_size > 0:
            assert result.position_size < base_size


class TestRegimeBasedSizingIntegration:
    """Integration tests for regime-based position sizing."""

    def test_regime_based_sizing_high_volatility(
        self, mock_etoro_client, risk_config_full_features, account_info
    ):
        """Test regime-based sizing reduces position in high volatility."""
        risk_manager = RiskManager(risk_config_full_features)
        
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
        mock_pm.get_correlated_positions.return_value = []
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="SPY",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test signal",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal with regime adjustment
        result = risk_manager.validate_signal(
            signal, account_info, [], 
            strategy_allocation_pct=10.0,
            portfolio_manager=mock_pm
        )
        
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Check metadata includes regime adjustment
        assert "regime_adjustment" in result.metadata
        regime_reason = result.metadata["regime_adjustment"]
        assert "ranging_high_vol" in regime_reason.lower()
        assert "0.5" in regime_reason  # multiplier value

    def test_regime_based_sizing_trending_market(
        self, mock_etoro_client, risk_config_full_features, account_info
    ):
        """Test regime-based sizing increases position in trending markets."""
        risk_manager = RiskManager(risk_config_full_features)
        
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
        mock_pm.get_correlated_positions.return_value = []
        
        signal = TradingSignal(
            strategy_id="test_strategy",
            symbol="SPY",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test signal",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal with regime adjustment - use smaller allocation to avoid limits
        result = risk_manager.validate_signal(
            signal, account_info, [], 
            strategy_allocation_pct=5.0,  # Reduced from 10.0 to avoid position size limits
            portfolio_manager=mock_pm
        )
        
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Check metadata includes regime adjustment
        assert "regime_adjustment" in result.metadata
        regime_reason = result.metadata["regime_adjustment"]
        assert "trending_up_strong" in regime_reason.lower()
        assert "1.2" in regime_reason  # multiplier value


class TestOrderCancellationIntegration:
    """Integration tests for order cancellation."""

    def test_cancel_stale_orders(self, mock_etoro_client, risk_config_full_features):
        """Test cancellation of stale pending orders."""
        # Create order monitor with mock database
        mock_db = Mock()
        order_monitor = OrderMonitor(mock_etoro_client, mock_db)
        
        # Create stale pending order (older than 24 hours)
        stale_order = Mock()
        stale_order.id = "order1"
        stale_order.strategy_id = "test_strategy"
        stale_order.symbol = "SPY"
        stale_order.side = OrderSide.BUY
        stale_order.order_type = OrderType.LIMIT
        stale_order.quantity = 10.0
        stale_order.price = 100.0
        stale_order.status = OrderStatus.PENDING
        stale_order.submitted_at = datetime.now() - timedelta(hours=25)  # 25 hours ago
        stale_order.etoro_order_id = "etoro_order1"
        
        # Mock database query to return stale order
        mock_session = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.all.return_value = [stale_order]
        mock_session.query.return_value = mock_query
        mock_db.get_session.return_value = mock_session
        
        # Mock eToro client to return success
        mock_etoro_client.cancel_order.return_value = True
        
        # Cancel stale orders
        result = order_monitor.cancel_stale_orders(max_age_hours=24)
        
        # Verify order was cancelled
        assert result["checked"] == 1
        assert result["cancelled"] == 1
        mock_etoro_client.cancel_order.assert_called_once_with("etoro_order1")


class TestSlippageTrackingIntegration:
    """Integration tests for slippage and execution quality tracking."""

    def test_slippage_calculation_on_fill(self, mock_etoro_client):
        """Test slippage is calculated when order is filled."""
        # Create a mock database
        mock_db = Mock()
        tracker = ExecutionQualityTracker(db=mock_db)
        
        # Create order with expected price
        order_orm = Mock()
        order_orm.id = "order1"
        order_orm.strategy_id = "test_strategy"
        order_orm.symbol = "SPY"
        order_orm.side = OrderSide.BUY
        order_orm.order_type = OrderType.MARKET
        order_orm.quantity = 10.0
        order_orm.price = 100.0
        order_orm.status = OrderStatus.FILLED
        order_orm.submitted_at = datetime.now() - timedelta(seconds=5)
        order_orm.filled_at = datetime.now()
        order_orm.filled_price = 100.5  # 0.5 slippage
        order_orm.expected_price = 100.0
        order_orm.slippage = 0.5
        order_orm.fill_time_seconds = 5.0
        
        # Mock database query chain
        mock_session = Mock()
        mock_query = Mock()
        
        # The query chain: session.query(OrderORM).filter(...).filter(...).all()
        # We need to make filter() return itself to allow chaining
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [order_orm]
        mock_session.query.return_value = mock_query
        mock_db.get_session.return_value = mock_session
        
        # Get metrics
        metrics = tracker.get_metrics(strategy_id="test_strategy")
        
        # Verify metrics were calculated
        assert metrics.total_orders == 1
        assert metrics.filled_orders == 1
        assert abs(metrics.avg_slippage - 0.5) < 0.01


class TestCombinedFeaturesIntegration:
    """Integration tests for multiple features working together."""

    def test_trailing_stops_and_partial_exits_together(
        self, mock_etoro_client, risk_config_full_features
    ):
        """Test trailing stops and partial exits work together without conflicts."""
        manager = PositionManager(mock_etoro_client, risk_config_full_features)
        
        # Create profitable position
        position = Position(
            id="pos1",
            strategy_id="momentum_strategy",
            symbol="SPY",
            side=PositionSide.LONG,
            quantity=100.0,
            entry_price=100.0,
            current_price=115.0,  # 15% profit
            unrealized_pnl=1500.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos1",
            stop_loss=95.0,
            take_profit=130.0,
            closed_at=None,
            partial_exits=[]
        )
        
        # Check trailing stops first
        trailing_orders = manager.check_trailing_stops([position])
        
        # Verify trailing stop was updated
        mock_etoro_client.update_position_stop_loss.assert_called_once()
        expected_stop = 115.0 * 0.97  # 111.55
        assert abs(position.stop_loss - expected_stop) < 0.01
        
        # Check partial exits
        partial_exit_orders = manager.check_partial_exits([position])
        
        # Should create 2 partial exit orders
        assert len(partial_exit_orders) == 2
        
        # Verify position quantity was reduced
        assert position.quantity == 20.0  # 100 - 30 - 50
        
        # Verify both features worked without interfering
        assert len(position.partial_exits) == 2
        assert position.stop_loss is not None

    def test_correlation_and_regime_adjustments_combined(
        self, mock_etoro_client, risk_config_full_features, account_info
    ):
        """Test correlation and regime adjustments work together."""
        risk_manager = RiskManager(risk_config_full_features)
        
        # Create existing position in same symbol
        existing_position = Position(
            id="pos1",
            strategy_id="momentum_strategy_1",
            symbol="SPY",
            side=PositionSide.LONG,
            quantity=5.0,
            entry_price=100.0,
            current_price=105.0,
            unrealized_pnl=25.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos1",
            closed_at=None
        )
        
        # Create mock portfolio manager with market analyzer
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.RANGING_HIGH_VOL,  # High volatility (0.5x multiplier)
            0.85,
            "GOOD",
            {}
        )
        mock_pm.market_analyzer = mock_market_analyzer
        mock_pm.get_correlated_positions.return_value = []
        
        signal = TradingSignal(
            strategy_id="momentum_strategy_2",
            symbol="SPY",  # Same symbol as existing position
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test signal",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal with both adjustments
        result = risk_manager.validate_signal(
            signal, account_info, [existing_position],
            strategy_allocation_pct=10.0,
            portfolio_manager=mock_pm
        )
        
        assert result.is_valid is True
        assert result.position_size > 0
        
        # Check both adjustments are in metadata
        assert "correlation_adjustment" in result.metadata
        assert "regime_adjustment" in result.metadata
        
        # Verify correlation adjustment mentions same symbol
        correlation_reason = result.metadata["correlation_adjustment"]
        assert "same symbol" in correlation_reason.lower()
        
        # Verify regime adjustment mentions high volatility
        regime_reason = result.metadata["regime_adjustment"]
        assert "high_vol" in regime_reason.lower()

    def test_full_position_lifecycle_with_all_features(
        self, mock_etoro_client, risk_config_full_features, account_info
    ):
        """Test complete position lifecycle with all features enabled."""
        # Initialize components
        position_manager = PositionManager(mock_etoro_client, risk_config_full_features)
        risk_manager = RiskManager(risk_config_full_features)
        
        # Step 1: Create signal with correlation and regime adjustments
        mock_pm = Mock()
        mock_market_analyzer = Mock()
        mock_market_analyzer.detect_sub_regime.return_value = (
            MarketRegime.TRENDING_UP_STRONG,  # Trending (1.2x multiplier)
            0.92,
            "GOOD",
            {}
        )
        mock_pm.market_analyzer = mock_market_analyzer
        mock_pm.get_correlated_positions.return_value = []
        
        signal = TradingSignal(
            strategy_id="momentum_strategy",
            symbol="SPY",
            action=SignalAction.ENTER_LONG,
            confidence=0.85,
            reasoning="Strong uptrend",
            generated_at=datetime.now(),
            metadata={}
        )
        
        # Validate signal - use smaller allocation to avoid position size limits
        validation_result = risk_manager.validate_signal(
            signal, account_info, [],
            strategy_allocation_pct=5.0,  # Reduced from 10.0 to avoid position size limits
            portfolio_manager=mock_pm
        )
        
        assert validation_result.is_valid is True
        assert validation_result.position_size > 0
        
        # Step 2: Create position
        position = Position(
            id="pos1",
            strategy_id="momentum_strategy",
            symbol="SPY",
            side=PositionSide.LONG,
            quantity=validation_result.position_size / 100.0,  # Assume $100/share
            entry_price=100.0,
            current_price=100.0,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            opened_at=datetime.now(),
            etoro_position_id="etoro_pos1",
            stop_loss=98.0,
            take_profit=120.0,
            closed_at=None,
            partial_exits=[]
        )
        
        # Step 3: Simulate price increase to 110 (10% profit)
        position.current_price = 110.0
        position.unrealized_pnl = (110.0 - 100.0) * position.quantity
        
        # Check trailing stops
        trailing_orders = position_manager.check_trailing_stops([position])
        
        # Verify trailing stop was activated
        mock_etoro_client.update_position_stop_loss.assert_called()
        expected_stop = 110.0 * 0.97
        assert abs(position.stop_loss - expected_stop) < 0.01
        
        # Step 4: Check partial exits
        partial_exit_orders = position_manager.check_partial_exits([position])
        
        # Should create 2 partial exit orders (5% and 10% levels)
        assert len(partial_exit_orders) == 2
        
        # Verify position quantity was reduced
        original_quantity = validation_result.position_size / 100.0
        expected_remaining = original_quantity * 0.2  # 100% - 30% - 50% = 20%
        assert abs(position.quantity - expected_remaining) < 0.01
        
        # Step 5: Verify all features worked together
        assert position.stop_loss is not None  # Trailing stop set
        assert len(position.partial_exits) == 2  # Partial exits recorded
        assert validation_result.metadata.get("regime_adjustment")  # Regime adjustment applied


class TestRealDemoAccountIntegration:
    """Integration tests with real eToro DEMO account (requires API credentials)."""

    @pytest.mark.skip(reason="Requires real eToro DEMO account credentials")
    def test_with_real_demo_account(self):
        """Test position management features with real eToro DEMO account.
        
        This test is skipped by default. To run it:
        1. Set up eToro DEMO account credentials
        2. Remove the @pytest.mark.skip decorator
        3. Run: pytest tests/test_position_management_integration.py::TestRealDemoAccountIntegration -v
        """
        # This would test with real eToro API
        # Implementation would depend on actual API credentials and setup
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
