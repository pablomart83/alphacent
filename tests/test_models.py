"""Tests for data models."""

import pytest
from datetime import datetime

from src.models import (
    AccountInfo,
    MarketData,
    Order,
    Position,
    RiskConfig,
    Strategy,
    TradingSignal,
    DataSource,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    SignalAction,
    StrategyStatus,
    TradingMode,
)


def test_risk_config_defaults():
    """Test RiskConfig default values."""
    config = RiskConfig()
    assert config.max_position_size_pct == 0.1
    assert config.max_exposure_pct == 0.8
    assert config.max_daily_loss_pct == 0.03
    assert config.max_drawdown_pct == 0.10
    assert config.position_risk_pct == 0.01
    assert config.stop_loss_pct == 0.02
    assert config.take_profit_pct == 0.04


def test_strategy_creation():
    """Test Strategy dataclass creation."""
    strategy = Strategy(
        id="test-strategy-1",
        name="Test Strategy",
        description="A test strategy",
        status=StrategyStatus.PROPOSED,
        rules={"rule1": "value1"},
        symbols=["AAPL", "GOOGL"],
        risk_params=RiskConfig(),
        created_at=datetime.now()
    )
    assert strategy.id == "test-strategy-1"
    assert strategy.name == "Test Strategy"
    assert strategy.status == StrategyStatus.PROPOSED
    assert len(strategy.symbols) == 2


def test_order_creation():
    """Test Order dataclass creation."""
    order = Order(
        id="order-1",
        strategy_id="strategy-1",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.PENDING
    )
    assert order.id == "order-1"
    assert order.symbol == "AAPL"
    assert order.side == OrderSide.BUY
    assert order.order_type == OrderType.MARKET


def test_position_creation():
    """Test Position dataclass creation."""
    position = Position(
        id="pos-1",
        strategy_id="strategy-1",
        symbol="AAPL",
        side=PositionSide.LONG,
        quantity=10.0,
        entry_price=150.0,
        current_price=155.0,
        unrealized_pnl=50.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id="etoro-pos-1"
    )
    assert position.id == "pos-1"
    assert position.symbol == "AAPL"
    assert position.side == PositionSide.LONG
    assert position.unrealized_pnl == 50.0


def test_market_data_creation():
    """Test MarketData dataclass creation."""
    data = MarketData(
        symbol="AAPL",
        timestamp=datetime.now(),
        open=150.0,
        high=155.0,
        low=149.0,
        close=154.0,
        volume=1000000.0,
        source=DataSource.ETORO
    )
    assert data.symbol == "AAPL"
    assert data.close == 154.0
    assert data.source == DataSource.ETORO


def test_trading_signal_creation():
    """Test TradingSignal dataclass creation."""
    signal = TradingSignal(
        strategy_id="strategy-1",
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="Strong uptrend",
        generated_at=datetime.now(),
        indicators={"ma_fast": 150.5, "ma_slow": 145.2},
        metadata={"indicator": "MA_crossover"}
    )
    assert signal.strategy_id == "strategy-1"
    assert signal.action == SignalAction.ENTER_LONG
    assert signal.confidence == 0.85


def test_account_info_creation():
    """Test AccountInfo dataclass creation."""
    account = AccountInfo(
        account_id="acc-1",
        mode=TradingMode.DEMO,
        balance=10000.0,
        buying_power=8000.0,
        margin_used=2000.0,
        margin_available=8000.0,
        daily_pnl=100.0,
        total_pnl=500.0,
        positions_count=3,
        updated_at=datetime.now()
    )
    assert account.account_id == "acc-1"
    assert account.mode == TradingMode.DEMO
    assert account.balance == 10000.0
