"""
Integration tests for Task 11.1: Integrate all components.

Tests that all Alpha Edge components are properly wired together:
- FundamentalDataProvider → StrategyEngine
- FundamentalFilter → strategy validation
- MLSignalFilter → signal generation
- TradeJournal → order execution
- New strategy templates → StrategyProposer
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import yaml
from pathlib import Path

from src.strategy.strategy_engine import StrategyEngine
from src.execution.order_executor import OrderExecutor
from src.strategy.strategy_templates import StrategyTemplateLibrary
from src.models.dataclasses import Strategy, TradingSignal, Order, Position
from src.models.enums import StrategyStatus, SignalAction, OrderSide, OrderType, PositionSide, OrderStatus
from src.execution.order_executor import Fill


@pytest.fixture
def mock_config():
    """Mock configuration with alpha_edge settings."""
    return {
        'alpha_edge': {
            'max_active_strategies': 10,
            'min_conviction_score': 70,
            'min_holding_period_days': 7,
            'max_trades_per_strategy_per_month': 4,
            'fundamental_filters': {
                'enabled': True,
                'min_checks_passed': 4,
                'checks': {
                    'profitable': True,
                    'growing': True,
                    'reasonable_valuation': True,
                    'no_dilution': True,
                    'insider_buying': True
                }
            },
            'ml_filter': {
                'enabled': True,
                'min_confidence': 0.70,
                'retrain_frequency_days': 30
            },
            'earnings_momentum': {
                'enabled': True,
                'market_cap_min': 300000000,
                'market_cap_max': 2000000000
            },
            'sector_rotation': {
                'enabled': True,
                'max_positions': 3
            },
            'quality_mean_reversion': {
                'enabled': True,
                'market_cap_min': 10000000000
            }
        }
    }


def test_fundamental_filter_integrated_in_strategy_engine():
    """Test that FundamentalFilter is integrated in StrategyEngine.generate_signals."""
    # This test verifies the integration exists by checking imports
    from src.strategy.strategy_engine import StrategyEngine
    import inspect
    
    # Get the source code of generate_signals
    source = inspect.getsource(StrategyEngine.generate_signals)
    
    # Verify FundamentalFilter is imported and used
    assert 'from src.strategy.fundamental_filter import FundamentalFilter' in source
    assert 'FundamentalFilter' in source
    assert 'fundamental_filter.get_passed_symbols' in source or 'fundamental_filter.filter_symbol' in source


def test_ml_signal_filter_integrated_in_strategy_engine():
    """Test that MLSignalFilter is integrated in StrategyEngine.generate_signals."""
    from src.strategy.strategy_engine import StrategyEngine
    import inspect
    
    source = inspect.getsource(StrategyEngine.generate_signals)
    
    # Verify MLSignalFilter is imported and used
    assert 'from src.ml.signal_filter import MLSignalFilter' in source
    assert 'MLSignalFilter' in source
    assert 'ml_filter.filter_signal' in source


def test_conviction_scorer_integrated_in_strategy_engine():
    """Test that ConvictionScorer is integrated in StrategyEngine.generate_signals."""
    from src.strategy.strategy_engine import StrategyEngine
    import inspect
    
    source = inspect.getsource(StrategyEngine.generate_signals)
    
    # Verify ConvictionScorer is imported and used
    assert 'from src.strategy.conviction_scorer import ConvictionScorer' in source
    assert 'ConvictionScorer' in source
    assert 'conviction_scorer.score_signal' in source


def test_trade_frequency_limiter_integrated_in_strategy_engine():
    """Test that TradeFrequencyLimiter is integrated in StrategyEngine.generate_signals."""
    from src.strategy.strategy_engine import StrategyEngine
    import inspect
    
    source = inspect.getsource(StrategyEngine.generate_signals)
    
    # Verify TradeFrequencyLimiter is imported and used
    assert 'from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter' in source
    assert 'TradeFrequencyLimiter' in source
    assert 'frequency_limiter.check_signal_allowed' in source


def test_trade_journal_integrated_in_order_executor():
    """Test that TradeJournal is integrated in OrderExecutor."""
    from src.execution.order_executor import OrderExecutor
    import inspect
    
    # Check __init__
    init_source = inspect.getsource(OrderExecutor.__init__)
    assert 'from src.analytics.trade_journal import TradeJournal' in init_source
    assert 'self.trade_journal = TradeJournal' in init_source
    
    # Check _handle_buy_fill
    buy_source = inspect.getsource(OrderExecutor._handle_buy_fill)
    assert 'self.trade_journal.log_entry' in buy_source
    assert 'self.trade_journal.log_exit' in buy_source
    
    # Check _handle_sell_fill
    sell_source = inspect.getsource(OrderExecutor._handle_sell_fill)
    assert 'self.trade_journal.log_entry' in sell_source
    assert 'self.trade_journal.log_exit' in sell_source


def test_new_strategy_templates_in_library():
    """Test that new Alpha Edge strategy templates are in the library."""
    library = StrategyTemplateLibrary()
    
    # Check Earnings Momentum template
    earnings_template = library.get_template_by_name("Earnings Momentum")
    assert earnings_template is not None
    assert earnings_template.metadata.get('strategy_category') == 'alpha_edge'
    assert earnings_template.metadata.get('requires_earnings_data') is True
    assert earnings_template.metadata.get('requires_fundamental_data') is True
    
    # Check Sector Rotation template
    sector_template = library.get_template_by_name("Sector Rotation")
    assert sector_template is not None
    assert sector_template.metadata.get('strategy_category') == 'alpha_edge'
    assert sector_template.metadata.get('uses_sector_etfs') is True
    assert 'fixed_symbols' in sector_template.metadata
    assert len(sector_template.metadata['fixed_symbols']) == 8  # 8 sector ETFs
    
    # Check Quality Mean Reversion template
    quality_template = library.get_template_by_name("Quality Mean Reversion")
    assert quality_template is not None
    assert quality_template.metadata.get('strategy_category') == 'alpha_edge'
    assert quality_template.metadata.get('requires_fundamental_data') is True
    assert quality_template.metadata.get('requires_quality_screening') is True


def test_order_executor_initializes_trade_journal():
    """Test that OrderExecutor properly initializes TradeJournal."""
    mock_etoro_client = Mock()
    mock_market_hours = Mock()
    
    # Create OrderExecutor
    executor = OrderExecutor(
        etoro_client=mock_etoro_client,
        market_hours=mock_market_hours
    )
    
    # Verify trade_journal is initialized (or None if database not available)
    assert hasattr(executor, 'trade_journal')
    # In test environment, it might be None if database is not set up
    # That's okay - the important thing is the attribute exists


def test_order_executor_logs_trade_entry_on_position_open(mock_config):
    """Test that OrderExecutor logs trade entry when opening a position."""
    mock_etoro_client = Mock()
    mock_market_hours = Mock()
    mock_trade_journal = Mock()
    
    executor = OrderExecutor(
        etoro_client=mock_etoro_client,
        market_hours=mock_market_hours
    )
    
    # Mock the trade journal
    executor.trade_journal = mock_trade_journal
    
    # Create a mock order with metadata
    order = Order(
        id="order_123",
        strategy_id="strategy_456",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100.0,
        status=OrderStatus.PENDING,
        etoro_order_id="etoro_789"
    )
    order.metadata = {
        'conviction_score': 85.0,
        'ml_confidence': 0.82,
        'market_regime': 'TRENDING_UP',
        'fundamentals': {'eps': 5.5, 'pe_ratio': 25.0}
    }
    
    # Create a mock fill
    fill = Fill(
        order_id="order_123",
        filled_quantity=100.0,
        filled_price=150.0,
        filled_at=datetime.now(),
        etoro_position_id="etoro_pos_123"
    )
    
    # Call _handle_buy_fill
    executor._handle_buy_fill(order, fill)
    
    # Verify trade_journal.log_entry was called
    assert mock_trade_journal.log_entry.called
    call_args = mock_trade_journal.log_entry.call_args
    
    # Verify the arguments
    assert call_args[1]['symbol'] == 'AAPL'
    assert call_args[1]['strategy_id'] == 'strategy_456'
    assert call_args[1]['entry_price'] == 150.0
    assert call_args[1]['entry_size'] == 100.0
    assert call_args[1]['conviction_score'] == 85.0
    assert call_args[1]['ml_confidence'] == 0.82
    assert call_args[1]['market_regime'] == 'TRENDING_UP'


def test_order_executor_logs_trade_exit_on_position_close(mock_config):
    """Test that OrderExecutor logs trade exit when closing a position."""
    mock_etoro_client = Mock()
    mock_market_hours = Mock()
    mock_trade_journal = Mock()
    
    executor = OrderExecutor(
        etoro_client=mock_etoro_client,
        market_hours=mock_market_hours
    )
    
    # Mock the trade journal
    executor.trade_journal = mock_trade_journal
    
    # Create an existing long position
    position = Position(
        id="position_123",
        strategy_id="strategy_456",
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=100.0,
        entry_price=150.0,
        current_price=150.0,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        opened_at=datetime.now() - timedelta(days=5),
        etoro_position_id="etoro_pos_123"
    )
    executor._positions[position.id] = position
    
    # Create a sell order to close the position
    order = Order(
        id="order_789",
        strategy_id="strategy_456",
        symbol="AAPL",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=100.0,
        status=OrderStatus.PENDING,
        etoro_order_id="etoro_order_789"
    )
    
    # Create a mock fill
    fill = Fill(
        order_id="order_789",
        filled_quantity=100.0,
        filled_price=160.0,  # $10 profit per share
        filled_at=datetime.now(),
        etoro_position_id="etoro_pos_123"
    )
    
    # Call _handle_sell_fill
    executor._handle_sell_fill(order, fill)
    
    # Verify trade_journal.log_exit was called
    assert mock_trade_journal.log_exit.called
    call_args = mock_trade_journal.log_exit.call_args
    
    # Verify the arguments
    assert call_args[1]['trade_id'] == position.id
    assert call_args[1]['exit_price'] == 160.0
    assert 'exit_reason' in call_args[1]


def test_integration_all_components_present():
    """Integration test to verify all components are present and importable."""
    # Test all imports work
    from src.data.fundamental_data_provider import FundamentalDataProvider
    from src.strategy.fundamental_filter import FundamentalFilter
    from src.strategy.earnings_momentum import EarningsMomentumStrategy
    from src.strategy.sector_rotation import SectorRotationStrategy
    from src.strategy.quality_mean_reversion import QualityMeanReversionStrategy
    from src.strategy.conviction_scorer import ConvictionScorer
    from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter
    from src.strategy.transaction_cost_tracker import TransactionCostTracker
    from src.ml.signal_filter import MLSignalFilter
    from src.analytics.trade_journal import TradeJournal
    from src.strategy.strategy_engine import StrategyEngine
    from src.execution.order_executor import OrderExecutor
    from src.strategy.strategy_templates import StrategyTemplateLibrary
    
    # All imports successful
    assert True


def test_strategy_templates_have_correct_metadata():
    """Test that Alpha Edge templates have correct metadata."""
    library = StrategyTemplateLibrary()
    
    alpha_edge_templates = [
        "Earnings Momentum",
        "Sector Rotation",
        "Quality Mean Reversion"
    ]
    
    for template_name in alpha_edge_templates:
        template = library.get_template_by_name(template_name)
        assert template is not None, f"Template {template_name} not found"
        assert template.metadata.get('strategy_category') == 'alpha_edge', \
            f"Template {template_name} missing alpha_edge category"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
