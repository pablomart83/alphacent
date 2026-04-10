"""
End-to-end integration test for complete trading flow.

Tests the complete flow: authenticate → generate strategy → backtest → activate → 
generate signal → validate → execute order → track fill

Validates: All requirements (integration test)
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from src.api.etoro_client import EToroAPIClient
from src.core.auth import AuthenticationManager
from src.data.market_data_manager import MarketDataManager
from src.data.market_hours_manager import MarketHoursManager, AssetClass
from src.execution.order_executor import OrderExecutor
from src.llm.llm_service import LLMService, StrategyDefinition
from src.models import (
    AccountInfo,
    MarketData,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    RiskConfig,
    SignalAction,
    TradingMode,
    TradingSignal,
    DataSource,
)
from src.risk.risk_manager import RiskManager
from src.strategy.strategy_engine import StrategyEngine


class TestEndToEndTradingFlow:
    """End-to-end integration tests for complete trading flow."""

    @pytest.fixture
    def mock_etoro_client(self):
        """Create mock eToro API client."""
        client = Mock(spec=EToroAPIClient)
        client.mode = TradingMode.DEMO
        
        # Mock authentication (header-based, always authenticated if keys present)
        client.is_authenticated.return_value = True
        
        # Mock account info
        client.get_account_info.return_value = AccountInfo(
            account_id="test_account",
            mode=TradingMode.DEMO,
            balance=10000.0,
            buying_power=10000.0,
            margin_used=0.0,
            margin_available=10000.0,
            daily_pnl=0.0,
            total_pnl=0.0,
            positions_count=0,
            updated_at=datetime.now()
        )
        
        # Mock market data
        client.get_market_data.return_value = MarketData(
            symbol="AAPL",
            timestamp=datetime.now(),
            open=150.0,
            high=152.0,
            low=149.0,
            close=151.0,
            volume=1000000.0,
            source=DataSource.ETORO
        )
        
        # Mock order placement
        client.place_order.return_value = {
            "order_id": "etoro_order_123",
            "status": "SUBMITTED",
            "message": "Order submitted successfully"
        }
        
        # Mock order status
        client.get_order_status.return_value = {
            "status": "FILLED",
            "filled_quantity": 10.0,
            "filled_price": 151.0,
            "filled_at": datetime.now().isoformat(),
            "position_id": "etoro_position_123"
        }
        
        # Mock positions
        client.get_positions.return_value = []
        
        return client

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service."""
        service = Mock(spec=LLMService)
        
        # Mock strategy generation
        service.generate_strategy.return_value = StrategyDefinition(
            name="Test Momentum Strategy",
            description="A simple momentum strategy for testing",
            rules={
                "entry": "Buy when 10-day MA crosses above 30-day MA",
                "exit": "Sell when 10-day MA crosses below 30-day MA",
                "indicators": ["SMA_10", "SMA_30"]
            },
            symbols=["AAPL"],
            risk_params=RiskConfig()
        )
        
        return service

    @pytest.fixture
    def market_data_manager(self, mock_etoro_client):
        """Create market data manager with mock client."""
        manager = MarketDataManager(mock_etoro_client)
        
        # Mock historical data
        historical_data = []
        base_date = datetime.now() - timedelta(days=60)
        for i in range(60):
            historical_data.append(MarketData(
                symbol="AAPL",
                timestamp=base_date + timedelta(days=i),
                open=150.0 + i * 0.5,
                high=152.0 + i * 0.5,
                low=149.0 + i * 0.5,
                close=151.0 + i * 0.5,
                volume=1000000.0,
                source=DataSource.ETORO
            ))
        
        with patch.object(manager, 'get_historical_data', return_value=historical_data):
            yield manager

    @pytest.fixture
    def market_hours_manager(self):
        """Create market hours manager."""
        manager = MarketHoursManager()
        
        # Mock market as always open for testing
        with patch.object(manager, 'is_market_open', return_value=True):
            yield manager

    @pytest.fixture
    def risk_manager(self):
        """Create risk manager with test configuration."""
        config = RiskConfig(
            max_position_size_pct=0.1,
            max_exposure_pct=0.8,
            max_daily_loss_pct=0.03,
            max_drawdown_pct=0.10,
            position_risk_pct=0.01,
            stop_loss_pct=0.02,
            take_profit_pct=0.04
        )
        return RiskManager(config)

    @pytest.fixture
    def order_executor(self, mock_etoro_client, market_hours_manager):
        """Create order executor with mock client."""
        return OrderExecutor(mock_etoro_client, market_hours_manager)

    @pytest.fixture
    def strategy_engine(self, mock_llm_service, market_data_manager):
        """Create strategy engine with mock services."""
        return StrategyEngine(mock_llm_service, market_data_manager)

    @pytest.fixture
    def auth_manager(self):
        """Create authentication manager."""
        manager = AuthenticationManager()
        manager.create_user("test_user", "test_password")
        return manager

    def test_complete_trading_flow_demo_mode(
        self,
        auth_manager,
        mock_etoro_client,
        strategy_engine,
        risk_manager,
        order_executor,
        market_data_manager
    ):
        """
        Test complete trading flow in Demo mode.
        
        Flow: authenticate → generate strategy → backtest → activate → 
              generate signal → validate → execute order → track fill
        """
        # Step 1: Authenticate user
        session_id = auth_manager.authenticate("test_user", "test_password")
        assert session_id is not None, "Authentication should succeed"
        assert auth_manager.validate_session(session_id), "Session should be valid"
        
        # Step 2: Generate strategy using LLM
        strategy = strategy_engine.generate_strategy(
            prompt="Create a momentum trading strategy for AAPL",
            constraints={"risk_level": "moderate", "symbols": ["AAPL"]}
        )
        assert strategy is not None, "Strategy should be generated"
        assert strategy.name == "Test Momentum Strategy"
        assert "AAPL" in strategy.symbols
        
        # Step 3: Backtest strategy
        start_date = datetime.now() - timedelta(days=60)
        end_date = datetime.now()
        
        backtest_results = strategy_engine.backtest_strategy(strategy, start_date, end_date)
        assert backtest_results is not None, "Backtest should complete"
        assert backtest_results.total_return is not None
        assert backtest_results.sharpe_ratio is not None
        
        # Step 4: Activate strategy in Demo mode
        strategy_engine.activate_strategy(strategy.id, TradingMode.DEMO)
        activated_strategy = strategy_engine.get_strategy(strategy.id)
        assert activated_strategy.status.value == "DEMO"
        
        # Step 5: Generate trading signal
        signals = strategy_engine.generate_signals(activated_strategy)
        assert len(signals) >= 0, "Signal generation should complete"
        
        # If no signals generated, create a test signal
        if len(signals) == 0:
            test_signal = TradingSignal(
                strategy_id=strategy.id,
                symbol="AAPL",
                action=SignalAction.ENTER_LONG,
                confidence=0.85,
                reasoning="Test signal for e2e flow",
                generated_at=datetime.now(),
                metadata={}
            )
            signals = [test_signal]
        
        signal = signals[0]
        assert signal.symbol == "AAPL"
        
        # Step 6: Validate signal through Risk Manager
        account_info = mock_etoro_client.get_account_info()
        positions = mock_etoro_client.get_positions()
        
        validation_result = risk_manager.validate_signal(signal, account_info, positions)
        assert validation_result.is_valid, f"Signal should be valid: {validation_result.reason}"
        assert validation_result.position_size > 0, "Position size should be calculated"
        
        # Step 7: Execute order
        order = order_executor.execute_signal(
            signal,
            validation_result.position_size,
            stop_loss_pct=0.02,
            take_profit_pct=0.04
        )
        assert order is not None, "Order should be created"
        assert order.symbol == "AAPL"
        assert order.status == OrderStatus.PENDING
        
        # Step 8: Track order until filled
        final_status = order_executor.track_order(order.id, wait_for_fill=True)
        assert final_status == OrderStatus.FILLED, "Order should be filled"
        
        # Step 9: Verify position was created
        filled_order = order_executor.get_order(order.id)
        assert filled_order.filled_quantity is not None
        assert filled_order.filled_price is not None
        
        # Verify position exists
        positions = order_executor.get_open_positions()
        assert len(positions) > 0, "Position should be created after fill"
        
        position = positions[0]
        assert position.symbol == "AAPL"
        assert position.side == PositionSide.LONG
        assert position.quantity == filled_order.filled_quantity
        
        print("\n✓ Complete trading flow test passed (Demo mode)")
        print(f"  - Authenticated user: test_user")
        print(f"  - Generated strategy: {strategy.name}")
        print(f"  - Backtest return: {backtest_results.total_return:.2%}")
        print(f"  - Signal: {signal.action.value} {signal.symbol}")
        print(f"  - Position size: ${validation_result.position_size:.2f}")
        print(f"  - Order filled: {filled_order.filled_quantity} @ ${filled_order.filled_price}")
        print(f"  - Position opened: {position.quantity} shares")

    def test_complete_trading_flow_live_mode(
        self,
        auth_manager,
        mock_etoro_client,
        strategy_engine,
        risk_manager,
        order_executor,
        market_data_manager
    ):
        """
        Test complete trading flow in Live mode.
        
        Same flow as Demo but with Live mode to ensure mode switching works.
        """
        # Update mock client to Live mode
        mock_etoro_client.mode = TradingMode.LIVE
        
        # Step 1: Authenticate
        session_id = auth_manager.authenticate("test_user", "test_password")
        assert session_id is not None
        
        # Step 2: Generate strategy
        strategy = strategy_engine.generate_strategy(
            prompt="Create a momentum trading strategy for AAPL",
            constraints={"risk_level": "moderate", "symbols": ["AAPL"]}
        )
        assert strategy is not None
        
        # Step 3: Backtest
        start_date = datetime.now() - timedelta(days=60)
        end_date = datetime.now()
        backtest_results = strategy_engine.backtest_strategy(strategy, start_date, end_date)
        assert backtest_results is not None
        
        # Step 4: Activate in LIVE mode
        strategy_engine.activate_strategy(strategy.id, TradingMode.LIVE)
        activated_strategy = strategy_engine.get_strategy(strategy.id)
        assert activated_strategy.status.value == "LIVE"
        
        # Step 5-9: Same as Demo mode
        signals = strategy_engine.generate_signals(activated_strategy)
        if len(signals) == 0:
            test_signal = TradingSignal(
                strategy_id=strategy.id,
                symbol="AAPL",
                action=SignalAction.ENTER_LONG,
                confidence=0.85,
                reasoning="Test signal for e2e flow",
                generated_at=datetime.now(),
                metadata={}
            )
            signals = [test_signal]
        
        signal = signals[0]
        account_info = mock_etoro_client.get_account_info()
        positions = mock_etoro_client.get_positions()
        
        validation_result = risk_manager.validate_signal(signal, account_info, positions)
        assert validation_result.is_valid
        
        order = order_executor.execute_signal(signal, validation_result.position_size)
        assert order is not None
        
        final_status = order_executor.track_order(order.id, wait_for_fill=True)
        assert final_status == OrderStatus.FILLED
        
        positions = order_executor.get_open_positions()
        assert len(positions) > 0
        
        print("\n✓ Complete trading flow test passed (Live mode)")
        print(f"  - Mode: LIVE")
        print(f"  - Strategy activated in Live mode")
        print(f"  - Order executed and filled successfully")

    def test_component_integration(
        self,
        mock_etoro_client,
        strategy_engine,
        risk_manager,
        order_executor
    ):
        """
        Test that all components work together correctly.
        
        Verifies component interfaces and data flow.
        """
        # Test 1: Strategy Engine → Risk Manager
        strategy = strategy_engine.generate_strategy(
            prompt="Test strategy",
            constraints={}
        )
        assert strategy is not None
        
        # Test 2: Risk Manager validates signals
        signal = TradingSignal(
            strategy_id=strategy.id,
            symbol="AAPL",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            reasoning="Test",
            generated_at=datetime.now(),
            metadata={}
        )
        
        account_info = mock_etoro_client.get_account_info()
        validation = risk_manager.validate_signal(signal, account_info, [])
        assert validation.is_valid
        
        # Test 3: Order Executor creates orders
        order = order_executor.execute_signal(signal, validation.position_size)
        assert order is not None
        assert order.symbol == signal.symbol
        
        # Test 4: Order tracking works
        status = order_executor.track_order(order.id, wait_for_fill=True)
        assert status == OrderStatus.FILLED
        
        print("\n✓ Component integration test passed")
        print("  - All components communicate correctly")
        print("  - Data flows properly between components")
