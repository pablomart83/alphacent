"""
Tests for TradingScheduler WebSocket broadcasting functionality.

Uses real components with an in-memory database and a recording WebSocketManager
to verify that the trading cycle correctly broadcasts signal, validation, and
order events.

Validates: Task 26.1 - Update TradingScheduler to broadcast signals
"""

import pytest
import uuid
from datetime import datetime
from typing import Dict, List, Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.websocket_manager import WebSocketManager
from src.core.trading_scheduler import TradingScheduler
from src.models.enums import (
    SignalAction, StrategyStatus, PositionSide,
    OrderSide, OrderType, OrderStatus,
)
from src.models.dataclasses import (
    TradingSignal, Strategy, PerformanceMetrics, RiskConfig,
    AccountInfo, Position, Order,
)
from src.models.orm import Base, StrategyORM, PositionORM
from src.risk.risk_manager import RiskManager, ValidationResult
from src.strategy.strategy_engine import StrategyEngine
from src.models.enums import TradingMode


# ---------------------------------------------------------------------------
# Helpers – lightweight real objects that record behaviour
# ---------------------------------------------------------------------------

class RecordingWebSocketManager(WebSocketManager):
    """A real WebSocketManager that records every broadcast for assertions."""

    def __init__(self):
        super().__init__()
        self.recorded_messages: List[dict] = []

    async def broadcast(self, message: dict):
        """Record the message instead of sending to (non-existent) clients."""
        self.recorded_messages.append(message)

    def messages_of_type(self, msg_type: str) -> List[dict]:
        return [m for m in self.recorded_messages if m.get("type") == msg_type]

    def signal_messages(self) -> List[dict]:
        return [
            m for m in self.recorded_messages
            if m.get("type") == "signal_generated"
        ]

    def validation_messages(self) -> List[dict]:
        return [
            m for m in self.recorded_messages
            if m.get("type") == "signal_validated"
        ]

    def order_messages(self) -> List[dict]:
        return [
            m for m in self.recorded_messages
            if m.get("type") == "order_update"
        ]


class FakeOrderExecutor:
    """Minimal order executor that creates real Order objects without calling eToro."""

    def execute_signal(self, signal, position_size, stop_loss_pct=None, take_profit_pct=None):
        side = OrderSide.BUY if signal.action == SignalAction.ENTER_LONG else OrderSide.SELL
        return Order(
            id=str(uuid.uuid4()),
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=position_size,
            status=OrderStatus.PENDING,
            submitted_at=datetime.now(),
            etoro_order_id=f"etoro-{uuid.uuid4().hex[:8]}",
        )


class FakeOrderMonitor:
    """Minimal order monitor that does nothing."""

    def run_monitoring_cycle(self):
        return {
            "pending": {"submitted": 0},
            "orders": {"filled": 0},
            "positions": {"created": 0},
        }


class FixedSignalStrategyEngine:
    """A real-ish strategy engine that returns predetermined signals.

    It delegates ORM conversion to a real StrategyEngine instance but
    overrides generate_signals_batch to return controlled signals.
    """

    def __init__(self, signals_by_strategy: Dict[str, List[TradingSignal]]):
        self._signals = signals_by_strategy
        self._real_engine = StrategyEngine.__new__(StrategyEngine)

    def _orm_to_strategy(self, orm) -> Strategy:
        """Use the real conversion logic."""
        return Strategy(
            id=orm.id,
            name=orm.name,
            description=orm.description,
            status=orm.status,
            rules=orm.rules,
            symbols=orm.symbols,
            risk_params=RiskConfig(**(orm.risk_params or {})),
            created_at=orm.created_at,
            allocation_percent=orm.allocation_percent,
            activated_at=orm.activated_at,
            retired_at=orm.retired_at,
            performance=PerformanceMetrics(),
        )

    def generate_signals_batch(self, strategies):
        return {s.id: self._signals.get(s.id, []) for s in strategies}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_session():
    """Create an in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def ws_manager():
    return RecordingWebSocketManager()


@pytest.fixture
def risk_manager():
    return RiskManager(RiskConfig(
        max_position_size_pct=0.1,
        max_exposure_pct=0.8,
        max_daily_loss_pct=0.03,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
    ))


@pytest.fixture
def account_info():
    return AccountInfo(
        account_id="demo_test",
        mode=TradingMode.DEMO,
        balance=100_000.0,
        buying_power=100_000.0,
        margin_used=0.0,
        margin_available=100_000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        positions_count=0,
        updated_at=datetime.now(),
    )


STRATEGY_ID = "test-strategy-001"
STRATEGY_RISK_PARAMS = {
    "max_position_size_pct": 0.1,
    "max_exposure_pct": 0.8,
    "max_daily_loss_pct": 0.03,
    "position_risk_pct": 0.01,
    "stop_loss_pct": 0.02,
    "take_profit_pct": 0.04,
}


@pytest.fixture
def demo_strategy_orm(in_memory_session):
    """Insert a DEMO strategy into the in-memory DB and return the ORM."""
    orm = StrategyORM(
        id=STRATEGY_ID,
        name="Test Momentum Strategy",
        description="A test strategy for broadcasting tests",
        status=StrategyStatus.DEMO,
        rules={"entry": ["RSI(14) < 30"], "exit": ["RSI(14) > 70"], "indicators": ["RSI:14"]},
        symbols=["AAPL"],
        allocation_percent=10.0,
        risk_params=STRATEGY_RISK_PARAMS,
        created_at=datetime.now(),
        performance={},
    )
    in_memory_session.add(orm)
    in_memory_session.commit()
    return orm


@pytest.fixture
def sample_signal():
    return TradingSignal(
        strategy_id=STRATEGY_ID,
        symbol="AAPL",
        action=SignalAction.ENTER_LONG,
        confidence=0.85,
        reasoning="RSI below 30, strong buy signal",
        indicators={"RSI": 28.5, "SMA_20": 150.0},
        generated_at=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Helper to build a pre-wired scheduler
# ---------------------------------------------------------------------------

def _build_scheduler(
    ws_manager: RecordingWebSocketManager,
    risk_manager: RiskManager,
    account_info: AccountInfo,
    strategy_engine,
    in_memory_session,
):
    """Create a TradingScheduler with all components pre-injected (no eToro calls)."""
    scheduler = TradingScheduler(signal_generation_interval=1)

    # Inject real components directly
    scheduler._websocket_manager = ws_manager
    scheduler._risk_manager = risk_manager
    scheduler._order_executor = FakeOrderExecutor()
    scheduler._order_monitor = FakeOrderMonitor()
    scheduler._strategy_engine = strategy_engine
    scheduler._components_initialized = True
    # Force signal generation on next cycle
    scheduler._last_signal_check = 0

    # Monkey-patch the eToro client to return our account_info
    class _FakeEtoro:
        def get_account_info(self):
            return account_info

    scheduler._etoro_client = _FakeEtoro()

    return scheduler


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_signal_generated(
    ws_manager, risk_manager, account_info, in_memory_session,
    demo_strategy_orm, sample_signal,
):
    """Signals are broadcasted when generated during a trading cycle."""
    engine = FixedSignalStrategyEngine({STRATEGY_ID: [sample_signal]})

    # Patch get_database to return our in-memory session
    import src.models.database as db_mod
    original_get_db = db_mod.get_database

    class _FakeDB:
        def get_session(self):
            return in_memory_session

    db_mod.get_database = lambda *a, **kw: _FakeDB()
    try:
        scheduler = _build_scheduler(
            ws_manager, risk_manager, account_info, engine, in_memory_session,
        )
        await scheduler._run_trading_cycle()
    finally:
        db_mod.get_database = original_get_db

    # Verify signal_generated broadcast
    sig_msgs = ws_manager.signal_messages()
    assert len(sig_msgs) == 1
    payload = sig_msgs[0]["signal"]
    assert payload["strategy_id"] == sample_signal.strategy_id
    assert payload["symbol"] == sample_signal.symbol
    assert payload["action"] == sample_signal.action.value
    assert payload["confidence"] == sample_signal.confidence
    assert payload["reasoning"] == sample_signal.reasoning


@pytest.mark.asyncio
async def test_broadcast_signal_validated(
    ws_manager, risk_manager, account_info, in_memory_session,
    demo_strategy_orm, sample_signal,
):
    """Signal validation results are broadcasted during a trading cycle."""
    engine = FixedSignalStrategyEngine({STRATEGY_ID: [sample_signal]})

    import src.models.database as db_mod
    original_get_db = db_mod.get_database

    class _FakeDB:
        def get_session(self):
            return in_memory_session

    db_mod.get_database = lambda *a, **kw: _FakeDB()
    try:
        scheduler = _build_scheduler(
            ws_manager, risk_manager, account_info, engine, in_memory_session,
        )
        await scheduler._run_trading_cycle()
    finally:
        db_mod.get_database = original_get_db

    # Verify signal_validated broadcast
    val_msgs = ws_manager.validation_messages()
    assert len(val_msgs) == 1
    msg = val_msgs[0]
    assert msg["signal"]["symbol"] == sample_signal.symbol
    assert msg["signal"]["action"] == sample_signal.action.value
    # With $100k balance and default risk config, signal should pass
    assert msg["validation"]["is_valid"] is True
    assert msg["validation"]["position_size"] > 0


@pytest.mark.asyncio
async def test_broadcast_order_executed(
    ws_manager, risk_manager, account_info, in_memory_session,
    demo_strategy_orm, sample_signal,
):
    """Order execution is broadcasted when a validated signal produces an order."""
    engine = FixedSignalStrategyEngine({STRATEGY_ID: [sample_signal]})

    import src.models.database as db_mod
    original_get_db = db_mod.get_database

    class _FakeDB:
        def get_session(self):
            return in_memory_session

    db_mod.get_database = lambda *a, **kw: _FakeDB()
    try:
        scheduler = _build_scheduler(
            ws_manager, risk_manager, account_info, engine, in_memory_session,
        )
        await scheduler._run_trading_cycle()
    finally:
        db_mod.get_database = original_get_db

    # Verify order_update broadcast
    order_msgs = ws_manager.order_messages()
    assert len(order_msgs) == 1
    order = order_msgs[0]["order"]
    assert order["strategy_id"] == STRATEGY_ID
    assert order["symbol"] == sample_signal.symbol
    assert order["side"] == OrderSide.BUY.value
    assert order["status"] == OrderStatus.PENDING.value
    assert order["quantity"] > 0


@pytest.mark.asyncio
async def test_no_broadcast_when_no_signals(
    ws_manager, risk_manager, account_info, in_memory_session,
    demo_strategy_orm,
):
    """No signal/validation/order broadcasts occur when no signals are generated."""
    engine = FixedSignalStrategyEngine({})  # No signals

    import src.models.database as db_mod
    original_get_db = db_mod.get_database

    class _FakeDB:
        def get_session(self):
            return in_memory_session

    db_mod.get_database = lambda *a, **kw: _FakeDB()
    try:
        scheduler = _build_scheduler(
            ws_manager, risk_manager, account_info, engine, in_memory_session,
        )
        await scheduler._run_trading_cycle()
    finally:
        db_mod.get_database = original_get_db

    assert len(ws_manager.signal_messages()) == 0
    assert len(ws_manager.validation_messages()) == 0
    assert len(ws_manager.order_messages()) == 0
