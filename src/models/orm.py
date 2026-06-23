"""SQLAlchemy ORM models for database persistence."""

import json
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (
    JSON as _RawJSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float as _RawFloat,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    TypeDecorator,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from .enums import (
    DataSource,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    SignalAction,
    StrategyStatus,
    SystemStateEnum,
    TradingMode,
)


import numpy as _np


def _sanitize_numpy(obj):
    """Recursively convert numpy types to Python natives for PostgreSQL.
    
    SQLite silently coerces np.float64 → float. PostgreSQL does not.
    This runs at the SQLAlchemy type level so every write is covered.
    """
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(_sanitize_numpy(v) for v in obj)
    if hasattr(obj, 'item'):  # numpy scalar
        return obj.item()
    if isinstance(obj, float) and (_np.isnan(obj) or _np.isinf(obj)):
        return 0.0
    return obj


class EnumString(TypeDecorator):
    """Store enums as plain strings. Works on both SQLite and PostgreSQL."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return value.value if hasattr(value, 'value') else str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return _EnumValue(value)


class _EnumValue(str):
    """A string that also has a .value property, so code using .value doesn't break."""
    @property
    def value(self):
        return str(self)


class NumpySafeJSON(TypeDecorator):
    """JSON column that auto-converts numpy types on write.
    
    Drop-in replacement for SQLAlchemy's JSON. Intercepts all writes
    and recursively converts np.float64, np.int64, np.bool_ etc. to
    Python natives before they hit the database driver.
    """
    impl = _RawJSON
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return _sanitize_numpy(value)


class NumpySafeFloat(TypeDecorator):
    """Float column that auto-converts numpy scalars on write."""
    impl = _RawFloat
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if hasattr(value, 'item'):
            return value.item()
        return float(value)


# Alias so every Column(JSON, ...) and Column(Float, ...) in this file
# automatically gets numpy safety. Zero changes needed in column definitions.
JSON = NumpySafeJSON
Float = NumpySafeFloat


Base = declarative_base()


class StrategyORM(Base):
    """Strategy ORM model."""
    __tablename__ = "strategies"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=False)
    status = Column(EnumString, nullable=False)
    rules = Column(JSON, nullable=False)
    symbols = Column(JSON, nullable=False)
    allocation_percent = Column(Float, nullable=False, default=0.0)
    risk_params = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False)
    activated_at = Column(DateTime, nullable=True)
    retired_at = Column(DateTime, nullable=True)
    performance = Column(JSON, nullable=False)
    reasoning = Column(JSON, nullable=True)
    backtest_results = Column(JSON, nullable=True)
    strategy_metadata = Column(JSON, nullable=True, default=dict)  # For revision tracking and other metadata
    retirement_evaluation_history = Column(JSON, nullable=True, default=list)  # Track retirement evaluation attempts
    live_trade_count = Column(Integer, nullable=False, default=0)  # Count of live trades executed
    last_retirement_evaluation = Column(DateTime, nullable=True)  # Last time retirement was evaluated
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value if self.status else None,
            "rules": self.rules,
            "symbols": self.symbols,
            "allocation_percent": self.allocation_percent,
            "risk_params": self.risk_params,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "retired_at": self.retired_at.isoformat() if self.retired_at else None,
            "performance": self.performance,
            "reasoning": self.reasoning,
            "backtest_results": self.backtest_results,
            "metadata": self.strategy_metadata or {},
            "retirement_evaluation_history": self.retirement_evaluation_history or [],
            "live_trade_count": self.live_trade_count,
            "last_retirement_evaluation": self.last_retirement_evaluation.isoformat() if self.last_retirement_evaluation else None
        }


class OrderORM(Base):
    """Order ORM model."""
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    strategy_id = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(EnumString, nullable=False)
    order_type = Column(EnumString, nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(EnumString, nullable=False)
    price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    take_profit_price = Column(Float, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    filled_at = Column(DateTime, nullable=True)
    filled_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=True)
    etoro_order_id = Column(String, nullable=True)
    
    # Execution quality tracking fields
    expected_price = Column(Float, nullable=True)  # Expected price at order creation
    slippage = Column(Float, nullable=True)  # Calculated: filled_price - expected_price
    fill_time_seconds = Column(Float, nullable=True)  # Time from submission to fill
    order_action = Column(String, nullable=True)  # 'entry', 'close', or 'retirement' — distinguishes order purpose

    # Signal-time metadata (market_regime, conviction_score, fundamentals, etc.)
    # Persisted as JSON so async fill handlers can recover regime at trade-journal write
    # time. Previously lost when fills came back async — caused 99.9% NULL
    # market_regime rows in trade_journal.
    order_metadata = Column(JSON, nullable=True)

    # Phase 2: which account this order belongs to ('demo' or 'live')
    account_type = Column(String(10), nullable=False, default='demo')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side.value if self.side else None,
            "order_type": self.order_type.value if self.order_type else None,
            "quantity": self.quantity,
            "status": self.status.value if self.status else None,
            "price": self.price,
            "stop_price": self.stop_price,
            "take_profit_price": self.take_profit_price,
            "created_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "updated_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "filled_price": self.filled_price,
            "filled_quantity": self.filled_quantity,
            "etoro_order_id": self.etoro_order_id,
            "expected_price": self.expected_price,
            "slippage": self.slippage,
            "fill_time_seconds": self.fill_time_seconds,
            "order_action": self.order_action
        }


class PositionORM(Base):
    """Position ORM model."""
    __tablename__ = "positions"

    # etoro_position_id is unique per account_type, not globally.
    # eToro reuses numeric position IDs across demo and live accounts.
    # The composite unique constraint (etoro_position_id, account_type) enforces
    # that the same eToro ID cannot appear twice within the same account, while
    # allowing the same numeric ID to exist in both demo and live rows.
    __table_args__ = (
        UniqueConstraint('etoro_position_id', 'account_type', name='uq_positions_etoro_id_account'),
    )

    id = Column(String, primary_key=True)
    strategy_id = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(EnumString, nullable=False)
    quantity = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False)
    realized_pnl = Column(Float, nullable=False)
    opened_at = Column(DateTime, nullable=False)
    etoro_position_id = Column(String, nullable=False)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    partial_exits = Column(JSON, nullable=True, default=list)  # Track partial exit history
    pending_closure = Column(Boolean, nullable=False, default=False)  # Position queued for closure approval
    closure_reason = Column(String, nullable=True)  # Reason for pending closure (e.g., "Strategy retired")
    close_order_id = Column(String, nullable=True)  # ID of the close order submitted for this position
    close_attempts = Column(Integer, nullable=False, default=0)  # Number of close order attempts
    invested_amount = Column(Float, nullable=True)  # Actual capital invested (from eToro 'amount' field, not leveraged notional)
    # A2 (staleness unification): timestamp current_price was last refreshed from
    # eToro by the position sync. Single source of truth for "how fresh is this
    # position's price" — used by breach enforcement (stops must act on fresh
    # prices), and the canonical input the FIX-09 / D1-D2 staleness predicates
    # should standardise on. Nullable: backfilled on the next sync after migration.
    price_updated_at = Column(DateTime, nullable=True)

    # Phase 2: which account this position belongs to ('demo' or 'live')
    account_type = Column(String(10), nullable=False, default='demo')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        unrealized_pnl_percent = 0.0
        if self.entry_price > 0:
            if self.side == PositionSide.SHORT:
                unrealized_pnl_percent = ((self.entry_price - self.current_price) / self.entry_price) * 100
            else:
                unrealized_pnl_percent = ((self.current_price - self.entry_price) / self.entry_price) * 100

        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": "BUY" if self.side == PositionSide.LONG else "SELL" if self.side == PositionSide.SHORT else None,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "unrealized_pnl_percent": unrealized_pnl_percent,
            "realized_pnl": self.realized_pnl,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "etoro_position_id": self.etoro_position_id,
            "partial_exits": self.partial_exits or [],
            "pending_closure": self.pending_closure if hasattr(self, 'pending_closure') else False,
            "closure_reason": self.closure_reason if hasattr(self, 'closure_reason') else None,
            "close_order_id": self.close_order_id if hasattr(self, 'close_order_id') else None,
            "close_attempts": self.close_attempts if hasattr(self, 'close_attempts') else 0,
            "invested_amount": self.invested_amount if hasattr(self, 'invested_amount') else None
        }


class MarketDataORM(Base):
    """Market data ORM model."""
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    source = Column(EnumString, nullable=False)


class TradingSignalORM(Base):
    """Trading signal ORM model."""
    __tablename__ = "trading_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    action = Column(EnumString, nullable=False)
    confidence = Column(Float, nullable=False)
    reason = Column(String, nullable=False)
    generated_at = Column(DateTime, nullable=False)
    signal_metadata = Column(JSON, nullable=False)


class AccountInfoORM(Base):
    """Account info ORM model."""
    __tablename__ = "account_info"

    account_id = Column(String, primary_key=True)
    mode = Column(EnumString, nullable=False)
    balance = Column(Float, nullable=False)
    equity = Column(Float, nullable=False, default=0.0)
    buying_power = Column(Float, nullable=False)
    margin_used = Column(Float, nullable=False)
    margin_available = Column(Float, nullable=False)
    daily_pnl = Column(Float, nullable=False)
    total_pnl = Column(Float, nullable=False)
    positions_count = Column(Integer, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "account_id": self.account_id,
            "mode": self.mode.value if self.mode else None,
            "balance": self.balance,
            "equity": self.equity,
            "buying_power": self.buying_power,
            "margin_used": self.margin_used,
            "margin_available": self.margin_available,
            "daily_pnl": self.daily_pnl,
            "total_pnl": self.total_pnl,
            "positions_count": self.positions_count,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class EquitySnapshotORM(Base):
    """Equity snapshots for P&L period calculations.
    
    Supports two resolutions:
    - daily: date = "YYYY-MM-DD", one per day (end-of-day)
    - hourly: date = "YYYY-MM-DD HH:00", one per hour (intraday)
    
    Daily snapshots are used for period P&L (today/week/month).
    Hourly snapshots enable intraday equity curve resolution.
    """
    __tablename__ = "equity_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False)  # YYYY-MM-DD or YYYY-MM-DD HH:00 — indexed via uq_equity_snapshot_date_type_account
    snapshot_type = Column(String, nullable=False, default='daily')  # 'daily' or 'hourly'
    equity = Column(Float, nullable=False)
    balance = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    realized_pnl_cumulative = Column(Float, nullable=False, default=0.0)
    positions_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    # Market quality score persisted with each snapshot for historical analysis
    market_quality_score = Column(Float, nullable=True)   # 0-100
    market_quality_grade = Column(String, nullable=True)  # 'high' | 'normal' | 'low'

    # Phase 2: which account this snapshot belongs to ('demo' or 'live')
    account_type = Column(String(10), nullable=False, default='demo')

    __table_args__ = (
        UniqueConstraint('date', 'snapshot_type', 'account_type', name='uq_equity_snapshot_date_type_account'),
    )


class RiskConfigORM(Base):
    """Risk configuration ORM model."""
    __tablename__ = "risk_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mode = Column(EnumString, nullable=False, unique=True)
    max_position_size_pct = Column(Float, nullable=False)
    max_exposure_pct = Column(Float, nullable=False)
    max_daily_loss_pct = Column(Float, nullable=False)
    max_drawdown_pct = Column(Float, nullable=False)
    position_risk_pct = Column(Float, nullable=False)
    stop_loss_pct = Column(Float, nullable=False)
    take_profit_pct = Column(Float, nullable=False)
    trailing_stop_enabled = Column(Integer, nullable=False, default=0)  # SQLite uses 0/1 for boolean
    trailing_stop_activation_pct = Column(Float, nullable=False, default=0.05)
    trailing_stop_distance_pct = Column(Float, nullable=False, default=0.03)
    partial_exit_enabled = Column(Integer, nullable=False, default=0)  # SQLite uses 0/1 for boolean
    partial_exit_levels = Column(JSON, nullable=True, default=None)  # List of profit levels and exit percentages
    # Correlation-adjusted position sizing
    correlation_adjustment_enabled = Column(Integer, nullable=False, default=1)  # 1 = True
    correlation_threshold = Column(Float, nullable=False, default=0.7)
    correlation_reduction_factor = Column(Float, nullable=False, default=0.5)
    # Regime-based position sizing
    regime_based_sizing_enabled = Column(Integer, nullable=False, default=0)
    regime_multipliers = Column(JSON, nullable=True, default=None)
    # Stale order cancellation
    cancel_stale_orders = Column(Integer, nullable=False, default=1)  # 1 = True
    stale_order_hours = Column(Integer, nullable=False, default=24)



class SystemStateORM(Base):
    """System state ORM model."""
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    state = Column(EnumString, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    reason = Column(String, nullable=False)
    initiated_by = Column(String, nullable=True)
    active_strategies_count = Column(Integer, nullable=False, default=0)
    open_positions_count = Column(Integer, nullable=False, default=0)
    uptime_seconds = Column(Integer, nullable=False, default=0)
    last_signal_generated = Column(DateTime, nullable=True)
    last_order_executed = Column(DateTime, nullable=True)
    is_current = Column(Integer, nullable=False, default=0)  # 1 for current state, 0 for history


class StateTransitionHistoryORM(Base):
    """State transition history ORM model."""
    __tablename__ = "state_transition_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_state = Column(EnumString, nullable=False)
    to_state = Column(EnumString, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    reason = Column(String, nullable=False)
    initiated_by = Column(String, nullable=True)
    active_strategies_count = Column(Integer, nullable=False, default=0)
    open_positions_count = Column(Integer, nullable=False, default=0)


class StrategyProposalORM(Base):
    """Strategy proposal ORM model.

    One row per proposal emitted by the autonomous cycle. Survives strategy
    retirement/deletion, which is the whole point — the `strategies` table is
    pruned when strategies cycle out, but proposal history is auditable
    forever. The `symbols` JSON snapshot is critical for per-symbol analytics
    (Symbols tab) because strategies.symbols disappears when the strategy is
    deleted.
    """
    __tablename__ = "strategy_proposals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False)
    proposed_at = Column(DateTime, nullable=False)
    market_regime = Column(String, nullable=False)
    backtest_sharpe = Column(Float, nullable=True)
    activated = Column(Integer, nullable=False, default=0)
    # Snapshot of the strategy's symbols list at proposal time. List[str].
    symbols = Column(JSON, nullable=True)
    # Snapshot of the originating template name (free-text, e.g. "RSI Dip Buy").
    template_name = Column(String, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "proposed_at": self.proposed_at.isoformat() if self.proposed_at else None,
            "market_regime": self.market_regime,
            "backtest_sharpe": self.backtest_sharpe,
            "activated": bool(self.activated),
            "symbols": self.symbols or [],
            "template_name": self.template_name,
        }


class StrategyRetirementORM(Base):
    """Strategy retirement ORM model."""
    __tablename__ = "strategy_retirements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False)
    retired_at = Column(DateTime, nullable=False)
    reason = Column(String, nullable=False)
    final_sharpe = Column(Float, nullable=True)
    final_return = Column(Float, nullable=True)
    final_drawdown = Column(Float, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "retired_at": self.retired_at.isoformat() if self.retired_at else None,
            "reason": self.reason,
            "final_sharpe": self.final_sharpe,
            "final_return": self.final_return,
            "final_drawdown": self.final_drawdown
        }


class RegimeHistoryORM(Base):
    """Regime history ORM model for tracking market regime changes."""
    __tablename__ = "regime_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False)
    detected_at = Column(DateTime, nullable=False)
    activation_regime = Column(String, nullable=False)
    current_regime = Column(String, nullable=False)
    regime_changed = Column(Integer, nullable=False)  # SQLite doesn't have boolean, use 0/1
    change_type = Column(String, nullable=True)
    change_magnitude = Column(Float, nullable=True)
    recommendation = Column(String, nullable=True)
    activation_metrics = Column(JSON, nullable=True)
    current_metrics = Column(JSON, nullable=True)
    details = Column(JSON, nullable=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "activation_regime": self.activation_regime,
            "current_regime": self.current_regime,
            "regime_changed": bool(self.regime_changed),
            "change_type": self.change_type,
            "change_magnitude": self.change_magnitude,
            "recommendation": self.recommendation,
            "activation_metrics": self.activation_metrics,
            "current_metrics": self.current_metrics,
            "details": self.details
        }


class EarningsHistoryORM(Base):
    """Earnings history ORM model for tracking earnings announcements."""
    __tablename__ = "earnings_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    earnings_date = Column(DateTime, nullable=False, index=True)
    fiscal_period = Column(String, nullable=True)
    actual_eps = Column(Float, nullable=True)
    estimated_eps = Column(Float, nullable=True)
    surprise_pct = Column(Float, nullable=True)
    revenue = Column(Float, nullable=True)
    estimated_revenue = Column(Float, nullable=True)
    revenue_surprise_pct = Column(Float, nullable=True)
    source = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "earnings_date": self.earnings_date.isoformat() if self.earnings_date else None,
            "fiscal_period": self.fiscal_period,
            "actual_eps": self.actual_eps,
            "estimated_eps": self.estimated_eps,
            "surprise_pct": self.surprise_pct,
            "revenue": self.revenue,
            "estimated_revenue": self.estimated_revenue,
            "revenue_surprise_pct": self.revenue_surprise_pct,
            "source": self.source,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class RejectedSignalORM(Base):
    """Rejected signal ORM model for tracking signals rejected by frequency limiter."""
    __tablename__ = "rejected_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    signal_type = Column(String, nullable=False)
    rejection_reason = Column(String, nullable=False)
    trades_this_month = Column(Integer, nullable=False)
    days_since_last_trade = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "rejection_reason": self.rejection_reason,
            "trades_this_month": self.trades_this_month,
            "days_since_last_trade": self.days_since_last_trade,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class FundamentalFilterLogORM(Base):
    """Fundamental filter log ORM model for tracking filter results."""
    __tablename__ = "fundamental_filter_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    strategy_type = Column(String, nullable=False)
    passed = Column(Boolean, nullable=False, index=True)
    checks_passed = Column(Integer, nullable=False)
    checks_failed = Column(Integer, nullable=False)
    profitable = Column(Boolean, nullable=True)
    growing = Column(Boolean, nullable=True)
    valuation = Column(Boolean, nullable=True)
    dilution = Column(Boolean, nullable=True)
    insider_buying = Column(Boolean, nullable=True)
    failure_reasons = Column(JSON, nullable=True)
    data_quality_score = Column(Float, nullable=False, default=0.0)  # 0-100 scale
    timestamp = Column(DateTime, nullable=False, index=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "symbol": self.symbol,
            "strategy_type": self.strategy_type,
            "passed": self.passed,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "profitable": self.profitable,
            "growing": self.growing,
            "valuation": self.valuation,
            "dilution": self.dilution,
            "insider_buying": self.insider_buying,
            "failure_reasons": self.failure_reasons,
            "data_quality_score": self.data_quality_score,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class MLFilterLogORM(Base):
    """ML filter log ORM model for tracking ML predictions."""
    __tablename__ = "ml_filter_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    signal_type = Column(String, nullable=False)
    passed = Column(Boolean, nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    features = Column(JSON, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "passed": self.passed,
            "confidence": self.confidence,
            "features": self.features,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class ConvictionScoreLogORM(Base):
    """Conviction score log ORM model for tracking conviction scores."""
    __tablename__ = "conviction_score_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False)
    signal_type = Column(String, nullable=False)
    conviction_score = Column(Float, nullable=False, index=True)
    signal_strength_score = Column(Float, nullable=False)
    fundamental_quality_score = Column(Float, nullable=False)
    regime_alignment_score = Column(Float, nullable=False)
    passed_threshold = Column(Boolean, nullable=False)
    threshold = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "signal_type": self.signal_type,
            "conviction_score": self.conviction_score,
            "signal_strength_score": self.signal_strength_score,
            "fundamental_quality_score": self.fundamental_quality_score,
            "regime_alignment_score": self.regime_alignment_score,
            "passed_threshold": self.passed_threshold,
            "threshold": self.threshold,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }


class FundamentalDataORM(Base):
    """Fundamental data ORM model for caching FMP API responses."""
    __tablename__ = "fundamental_data_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True, unique=True)
    
    # Income statement
    eps = Column(Float, nullable=True)
    revenue = Column(Float, nullable=True)
    revenue_growth = Column(Float, nullable=True)
    
    # Balance sheet
    total_debt = Column(Float, nullable=True)
    total_equity = Column(Float, nullable=True)
    debt_to_equity = Column(Float, nullable=True)
    
    # Key metrics
    roe = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    
    # Insider trading
    insider_net_buying = Column(Float, nullable=True)
    
    # Share dilution
    shares_outstanding = Column(Float, nullable=True)
    shares_change_percent = Column(Float, nullable=True)
    
    # Dividend data
    dividend_yield = Column(Float, nullable=True)
    
    # Earnings data
    earnings_surprise = Column(Float, nullable=True)
    
    # Metadata
    source = Column(String, nullable=False)  # "FMP" or "AlphaVantage"
    fetched_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "symbol": self.symbol,
            "eps": self.eps,
            "revenue": self.revenue,
            "revenue_growth": self.revenue_growth,
            "total_debt": self.total_debt,
            "total_equity": self.total_equity,
            "debt_to_equity": self.debt_to_equity,
            "roe": self.roe,
            "pe_ratio": self.pe_ratio,
            "market_cap": self.market_cap,
            "insider_net_buying": self.insider_net_buying,
            "shares_outstanding": self.shares_outstanding,
            "shares_change_percent": self.shares_change_percent,
            "dividend_yield": self.dividend_yield,
            "earnings_surprise": self.earnings_surprise,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class HistoricalPriceCacheORM(Base):
    """Historical OHLCV price data cache for Yahoo Finance and FMP forex data."""
    __tablename__ = "historical_price_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    interval = Column(String, nullable=False, default="1d")  # "1d", "1h", "4h"
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)
    source = Column(String, nullable=False)  # "YAHOO_FINANCE", "FMP", "ETORO"

    # Metadata
    fetched_at = Column(DateTime, nullable=False, default=datetime.now)

    # Unique constraint: one bar per symbol per date per interval
    __table_args__ = (
        UniqueConstraint('symbol', 'date', 'interval', name='uq_historical_symbol_date_interval'),
    )


class CacheMetadataORM(Base):
    """Metadata for tracking cache warming timestamps and other cache state.
    
    Persists cache state to DB so it survives backend restarts.
    """
    __tablename__ = "cache_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String, nullable=False, unique=True, index=True)
    value = Column(String, nullable=True)  # Stored as ISO timestamp string or JSON
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class SignalDecisionLogORM(Base):
    """[DEPRECATED 2026-05-04] Legacy signal-decision table.

    WRITERS: `trading_scheduler._log_signal_decision` still writes here for
    backward compatibility during the deprecation window. All other paths
    use `SignalDecisionORM` (the unified funnel).

    READERS: All application code now reads from `SignalDecisionORM`. This
    table is retained read-only for historical data lookups until the
    next clean-up pass.

    Do NOT add new writers. Do NOT add new readers. Use `SignalDecisionORM`
    and `src.analytics.decision_log.record_decision()` for any new code.

    Retirement plan: after 30 days of the unified funnel serving all
    endpoints cleanly, drop the dual-write in `_log_signal_decision` and
    then drop this table.
    """
    __tablename__ = "signal_decision_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String, nullable=False, index=True)
    strategy_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)  # BUY / SELL
    signal_type = Column(String, nullable=False)  # ENTRY / EXIT
    decision = Column(String, nullable=False, index=True)  # ACCEPTED / REJECTED
    rejection_reason = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    metadata_json = Column(JSON, nullable=True)  # conviction score, portfolio balance state, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "signal_type": self.signal_type,
            "decision": self.decision,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata_json,
        }




class DataQualityReportORM(Base):
    """Cached data quality validation reports."""
    __tablename__ = "data_quality_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    quality_score = Column(Float, nullable=False)
    total_points = Column(Integer, nullable=False, default=0)
    issue_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    warning_count = Column(Integer, nullable=False, default=0)
    issues_json = Column(JSON, nullable=True)  # Serialized list of issues
    metrics_json = Column(JSON, nullable=True)  # Serialized metrics dict
    validated_at = Column(DateTime, nullable=False, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quality_score": self.quality_score,
            "total_points": self.total_points,
            "issue_count": self.issue_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "validated_at": self.validated_at.isoformat() if self.validated_at else None,
        }



class QuarterlyFundamentalsORM(Base):
    """Quarterly fundamental data cache for Alpha Edge backtesting."""
    __tablename__ = "quarterly_fundamentals_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    quarter_date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    eps = Column(Float, nullable=True)
    revenue = Column(Float, nullable=True)
    revenue_growth = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    roe = Column(Float, nullable=True)
    debt_to_equity = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    earnings_surprise = Column(Float, nullable=True)
    actual_eps = Column(Float, nullable=True)
    estimated_eps = Column(Float, nullable=True)
    earnings_surprise_source = Column(String, nullable=True)  # "analyst_estimate" or "sequential_fallback"
    quality_data_source = Column(String, nullable=True)  # "quarterly" or "annual_interpolated"
    # Phase 1: New institutional-grade fundamental metrics
    net_income = Column(Float, nullable=True)
    total_assets = Column(Float, nullable=True)
    operating_cash_flow = Column(Float, nullable=True)
    capital_expenditure = Column(Float, nullable=True)
    free_cash_flow = Column(Float, nullable=True)
    accruals_ratio = Column(Float, nullable=True)  # (net_income - operating_cf) / total_assets
    fcf_yield = Column(Float, nullable=True)  # free_cash_flow / market_cap
    piotroski_f_score = Column(Integer, nullable=True)  # 0-9
    sue = Column(Float, nullable=True)  # Standardized Unexpected Earnings
    gross_profit = Column(Float, nullable=True)
    current_ratio = Column(Float, nullable=True)
    long_term_debt = Column(Float, nullable=True)
    gross_margin = Column(Float, nullable=True)
    asset_turnover = Column(Float, nullable=True)
    shares_outstanding = Column(Float, nullable=True)
    market_cap = Column(Float, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        UniqueConstraint('symbol', 'quarter_date', name='uq_quarterly_symbol_date'),
    )




class AutonomousCycleRunORM(Base):
    """Autonomous cycle run history for tracking cycle executions and their results."""
    __tablename__ = "autonomous_cycle_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cycle_id = Column(String, nullable=False, unique=True, index=True)
    status = Column(EnumString, nullable=False, default="running")  # running, completed, error
    started_at = Column(DateTime, nullable=False, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Stage metrics
    strategies_cleaned = Column(Integer, nullable=False, default=0)
    strategies_retired = Column(Integer, nullable=False, default=0)
    trades_analyzed = Column(Integer, nullable=False, default=0)
    template_adjustments = Column(Integer, nullable=False, default=0)
    proposals_generated = Column(Integer, nullable=False, default=0)
    proposals_pre_wf = Column(Integer, nullable=False, default=0)  # Raw proposer output pre-WF (added 2026-05-02 D4)
    proposals_alpha_edge = Column(Integer, nullable=False, default=0)
    proposals_template = Column(Integer, nullable=False, default=0)
    symbols_checked = Column(Integer, nullable=False, default=0)
    symbols_passed = Column(Integer, nullable=False, default=0)
    symbols_failed = Column(Integer, nullable=False, default=0)
    backtested = Column(Integer, nullable=False, default=0)
    backtest_passed = Column(Integer, nullable=False, default=0)
    backtest_failed = Column(Integer, nullable=False, default=0)
    avg_sharpe = Column(Float, nullable=True)
    avg_win_rate = Column(Float, nullable=True)
    activated = Column(Integer, nullable=False, default=0)
    promoted_to_paper = Column(Integer, nullable=False, default=0)  # Strategies that got first order → PAPER status (renamed from promoted_to_demo 2026-05-10)
    total_active = Column(Integer, nullable=False, default=0)
    total_backtested = Column(Integer, nullable=False, default=0)
    signals_generated = Column(Integer, nullable=False, default=0)
    signals_passed = Column(Integer, nullable=False, default=0)
    orders_submitted = Column(Integer, nullable=False, default=0)
    orders_filled = Column(Integer, nullable=False, default=0)
    orders_pending = Column(Integer, nullable=False, default=0)
    orders_rejected = Column(Integer, nullable=False, default=0)

    # Full stage details as JSON
    stage_details = Column(JSON, nullable=True)
    errors = Column(JSON, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cycle_id": self.cycle_id,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "strategies_cleaned": self.strategies_cleaned,
            "strategies_retired": self.strategies_retired,
            "trades_analyzed": self.trades_analyzed,
            "template_adjustments": self.template_adjustments,
            "proposals_generated": self.proposals_generated,
            "proposals_pre_wf": self.proposals_pre_wf,
            "proposals_alpha_edge": self.proposals_alpha_edge,
            "proposals_template": self.proposals_template,
            "symbols_checked": self.symbols_checked,
            "symbols_passed": self.symbols_passed,
            "symbols_failed": self.symbols_failed,
            "backtested": self.backtested,
            "backtest_passed": self.backtest_passed,
            "backtest_failed": self.backtest_failed,
            "avg_sharpe": self.avg_sharpe,
            "avg_win_rate": self.avg_win_rate,
            "activated": self.activated,
            "promoted_to_paper": self.promoted_to_paper,
            "total_active": self.total_active,
            "total_backtested": self.total_backtested,
            "signals_generated": self.signals_generated,
            "signals_passed": self.signals_passed,
            "orders_submitted": self.orders_submitted,
            "orders_filled": self.orders_filled,
            "orders_pending": self.orders_pending,
            "orders_rejected": self.orders_rejected,
            "stage_details": self.stage_details,
            "errors": self.errors,
        }


class AlertConfigORM(Base):
    """User alert configuration preferences."""
    __tablename__ = "alert_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # P&L threshold alerts
    pnl_loss_enabled = Column(Boolean, nullable=False, default=False)
    pnl_loss_threshold = Column(Float, nullable=False, default=1000.0)  # Alert when daily P&L drops below -$X
    pnl_gain_enabled = Column(Boolean, nullable=False, default=False)
    pnl_gain_threshold = Column(Float, nullable=False, default=5000.0)  # Alert when daily P&L exceeds +$X
    # Drawdown alerts
    drawdown_enabled = Column(Boolean, nullable=False, default=True)
    drawdown_threshold = Column(Float, nullable=False, default=10.0)  # Alert when drawdown exceeds X%
    # Position alerts
    position_loss_enabled = Column(Boolean, nullable=False, default=True)
    position_loss_threshold = Column(Float, nullable=False, default=5.0)  # Alert when any position loses > X%
    # Margin alerts
    margin_enabled = Column(Boolean, nullable=False, default=False)
    margin_threshold = Column(Float, nullable=False, default=80.0)  # Alert when margin utilization > X%
    # Cycle alerts (always on)
    cycle_complete_enabled = Column(Boolean, nullable=False, default=True)
    # Strategy alerts
    strategy_retired_enabled = Column(Boolean, nullable=False, default=True)
    # Browser push notifications
    browser_push_enabled = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pnl_loss_enabled": self.pnl_loss_enabled,
            "pnl_loss_threshold": self.pnl_loss_threshold,
            "pnl_gain_enabled": self.pnl_gain_enabled,
            "pnl_gain_threshold": self.pnl_gain_threshold,
            "drawdown_enabled": self.drawdown_enabled,
            "drawdown_threshold": self.drawdown_threshold,
            "position_loss_enabled": self.position_loss_enabled,
            "position_loss_threshold": self.position_loss_threshold,
            "margin_enabled": self.margin_enabled,
            "margin_threshold": self.margin_threshold,
            "cycle_complete_enabled": self.cycle_complete_enabled,
            "strategy_retired_enabled": self.strategy_retired_enabled,
            "browser_push_enabled": self.browser_push_enabled,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AlertHistoryORM(Base):
    """Alert history log for persistent notification tracking."""
    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(String, nullable=False, index=True)  # pnl_loss, pnl_gain, drawdown, position_loss, margin, cycle_complete, strategy_retired
    severity = Column(String, nullable=False, default="info")  # info, warning, critical
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    alert_metadata = Column(JSON, nullable=True)  # Extra context (symbol, strategy_id, values, etc.)
    read = Column(Boolean, nullable=False, default=False)
    acknowledged = Column(Boolean, nullable=False, default=False)  # For critical alerts
    link_page = Column(String, nullable=True)  # Page to navigate to (e.g., "/portfolio", "/strategies")
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "metadata": self.alert_metadata,
            "read": self.read,
            "acknowledged": self.acknowledged,
            "link_page": self.link_page,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserORM(Base):
    """User accounts with role-based permissions."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="viewer")  # admin, trader, viewer
    permissions = Column(NumpySafeJSON, nullable=False, default=dict)  # {"pages": [...], "actions": [...]}
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    last_login = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "permissions": self.permissions or {},
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created_by": self.created_by,
        }


class UserSessionORM(Base):
    """Persistent user sessions — survive backend restarts.

    Sessions are written to DB on creation and deleted on logout/expiry.
    On startup, AuthenticationManager loads all non-expired rows back into
    its in-memory dict so the fast-path validation (dict lookup) still works.

    This table is the source of truth for 'is this session_id still valid?'
    across restarts, deploys, and systemd service bounces.
    """
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    username = Column(String, nullable=False, index=True)
    role = Column(String, nullable=False)
    permissions = Column(NumpySafeJSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    last_activity = Column(DateTime, nullable=False, default=datetime.now)
    expires_at = Column(DateTime, nullable=False, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "username": self.username,
            "role": self.role,
            "permissions": self.permissions or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class SignalDecisionORM(Base):
    """Audit log of every template × symbol × direction decision per cycle.

    One row per evaluated (template, symbol, action) triplet per autonomous
    or signal cycle. Captures the full decision path so "why didn't we trade X"
    becomes a single SQL query instead of a multi-log-file investigation.

    Stages:
      proposed       — proposer generated the combo
      wf_validated   — passed walk-forward
      wf_rejected    — failed walk-forward (with reason)
      mc_validated   — passed Monte Carlo bootstrap
      mc_rejected    — failed MC
      activated      — proposer selected for activation
      rejected_act   — failed activation criteria
      signal_emitted — strategy_engine produced a signal
      gate_blocked   — order_executor gate (VIX, trend-consistency, etc.) blocked
      order_submitted— order sent to eToro
      order_filled   — fill confirmed
      order_failed   — order rejected / errored

    Kept for 30 days (retention policy enforced by a cleanup job).
    """
    __tablename__ = "signal_decisions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)
    cycle_id = Column(String, nullable=True, index=True)
    strategy_id = Column(String, nullable=True, index=True)
    template_name = Column(String, nullable=True, index=True)
    symbol = Column(String, nullable=True, index=True)
    direction = Column(String, nullable=True)  # 'long' | 'short'
    market_regime = Column(String, nullable=True)
    stage = Column(String, nullable=False, index=True)  # see docstring
    decision = Column(String, nullable=False)  # 'accepted' | 'rejected' | 'emitted' | 'blocked'
    reason = Column(String, nullable=True)  # human-readable short reason
    score = Column(Float, nullable=True)
    # Account the decision was made for. 'demo' (PAPER) | 'live' | NULL (legacy
    # rows written before this column / writers that don't yet pass it). Lets the
    # gate scoreboard split blocked-vs-passed realized edge per account (the gates
    # are account-asymmetric: C1 VIX / C3 trend-consistency / BTC-trend are LIVE-only).
    account_type = Column(String, nullable=True, index=True)
    decision_metadata = Column(JSON, nullable=True)  # Free-form (sharpe, conviction, gate_name, etc.)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "cycle_id": self.cycle_id,
            "strategy_id": self.strategy_id,
            "template_name": self.template_name,
            "symbol": self.symbol,
            "direction": self.direction,
            "market_regime": self.market_regime,
            "stage": self.stage,
            "decision": self.decision,
            "reason": self.reason,
            "score": self.score,
            "account_type": self.account_type,
            "metadata": self.decision_metadata,
        }


class GraduationApprovalORM(Base):
    """Records CIO approval/rejection decisions for promoting a (template, symbol) pair to live trading.

    One row per decision. A pair can be rejected and later re-approved after the 14-day cooldown.
    When approved_at is set and rejected_at is NULL, the pair is eligible for live fills.
    """
    __tablename__ = "graduation_approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(String(36), nullable=False)
    symbol = Column(String(20), nullable=False)
    template_name = Column(String(200), nullable=False)
    approved_at = Column(DateTime, nullable=True)
    rejected_at = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)

    # CIO overrides applied at approval time (None = use strategy defaults)
    position_size_override = Column(Float, nullable=True)
    sl_pct_override = Column(Float, nullable=True)
    tp_pct_override = Column(Float, nullable=True)
    conviction_min_override = Column(Integer, nullable=True)

    # Paper trading stats at time of decision (snapshot for audit trail)
    paper_trades = Column(Integer, nullable=True)
    paper_sharpe = Column(Float, nullable=True)
    paper_win_rate = Column(Float, nullable=True)
    paper_total_pnl = Column(Float, nullable=True)
    wf_sharpe = Column(Float, nullable=True)
    qualification_ratio = Column(Float, nullable=True)  # paper_sharpe / wf_sharpe

    created_at = Column(DateTime, nullable=False, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "template_name": self.template_name,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "notes": self.notes,
            "position_size_override": self.position_size_override,
            "sl_pct_override": self.sl_pct_override,
            "tp_pct_override": self.tp_pct_override,
            "conviction_min_override": self.conviction_min_override,
            "paper_trades": self.paper_trades,
            "paper_sharpe": self.paper_sharpe,
            "paper_win_rate": self.paper_win_rate,
            "paper_total_pnl": self.paper_total_pnl,
            "wf_sharpe": self.wf_sharpe,
            "qualification_ratio": self.qualification_ratio,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LiveStrategyORM(Base):
    """Active live-trading authorizations.

    One row per approved (strategy_id, symbol) pair. retired_at NULL = currently live.
    Linked to the graduation_approvals row that created it.

    Risk parameters here are the effective values used for live order sizing —
    either the strategy defaults or the CIO overrides from graduation_approvals.
    """
    __tablename__ = "live_strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    graduation_id = Column(Integer, nullable=True)  # FK to graduation_approvals.id
    strategy_id = Column(String(36), nullable=False)
    template_name = Column(String(200), nullable=False)
    symbol = Column(String(20), nullable=False)
    activated_at = Column(DateTime, nullable=False, default=datetime.now)
    retired_at = Column(DateTime, nullable=True)

    # Effective risk parameters for live fills
    position_size = Column(Float, nullable=False)
    sl_pct = Column(Float, nullable=False)
    tp_pct = Column(Float, nullable=False)
    conviction_min = Column(Integer, nullable=False, default=74)

    # Live performance tracking (updated on each fill/close)
    live_trades = Column(Integer, nullable=False, default=0)
    live_pnl = Column(Float, nullable=False, default=0.0)
    live_sharpe = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint('strategy_id', 'symbol', name='uq_live_strategy_strategy_symbol'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "graduation_id": self.graduation_id,
            "strategy_id": self.strategy_id,
            "template_name": self.template_name,
            "symbol": self.symbol,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "retired_at": self.retired_at.isoformat() if self.retired_at else None,
            "position_size": self.position_size,
            "sl_pct": self.sl_pct,
            "tp_pct": self.tp_pct,
            "conviction_min": self.conviction_min,
            "live_trades": self.live_trades,
            "live_pnl": self.live_pnl,
            "live_sharpe": self.live_sharpe,
            "is_active": self.retired_at is None,
        }


class WfValidationLedgerORM(Base):
    """Durable walk-forward validation record per (template_name, symbol).

    WHY THIS EXISTS
    ---------------
    The walk-forward (WF) test Sharpe is the baseline "true edge" estimate the
    graduation gate divides paper Sharpe by (the qualification ratio). It is
    written into `strategies.strategy_metadata` JSON at proposal/validation time
    — but that JSON dies with the strategy row when the BACKTESTED TTL deletes a
    stale version. The graduation gate recovers the WF Sharpe per template from
    the surviving sibling versions (`best_wf_by_template`), but that value
    collapses to 0 when *every* surviving version of a template simultaneously
    lacks a `wf_test_sharpe` (e.g. all WF-carrying versions were TTL-deleted and
    the re-proposed versions have not re-validated yet). When that happens the
    graduation gate fail-closes a pair whose WF edge WAS established — the same
    class of bug as the trade-history loss fixed in commit `1a373bd` (metadata
    not surviving version deletion).

    This table persists the WF Sharpe at the (template, symbol) level so it
    survives version deletion. It is upserted whenever a (template, symbol)
    passes walk-forward (see `src/strategy/wf_ledger.record_wf_validation`) and
    is NEVER pruned by a TTL — a pair that established a WF edge keeps that fact
    permanently. The graduation gate reads it as a recovery source for the WF
    Sharpe, between the current representative version's JSON (freshest) and the
    template-level `best_wf_by_template` fallback (coarsest).

    Stored value semantics: `wf_test_sharpe` is the MOST RECENT validated test
    Sharpe (re-validation updates it, so the ledger tracks the current edge and
    self-heals). `best_wf_test_sharpe` is the max ever observed, kept for
    diagnostics. Both are recorded only for passes with a positive test Sharpe.
    """
    __tablename__ = "wf_validation_ledger"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_name = Column(String(200), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    # Most-recent validated WF test Sharpe (self-heals on re-validation)
    wf_test_sharpe = Column(Float, nullable=False)
    wf_test_trades = Column(Integer, nullable=True)
    # Max WF test Sharpe ever observed for this pair (diagnostics)
    best_wf_test_sharpe = Column(Float, nullable=True)

    first_validated_at = Column(DateTime, nullable=False, default=datetime.now)
    last_validated_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    validation_count = Column(Integer, nullable=False, default=1)
    source = Column(String(40), nullable=True)  # 'proposer' | 'backfill_strategies'

    __table_args__ = (
        UniqueConstraint('template_name', 'symbol', name='uq_wf_ledger_template_symbol'),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "template_name": self.template_name,
            "symbol": self.symbol,
            "wf_test_sharpe": self.wf_test_sharpe,
            "wf_test_trades": self.wf_test_trades,
            "best_wf_test_sharpe": self.best_wf_test_sharpe,
            "first_validated_at": self.first_validated_at.isoformat() if self.first_validated_at else None,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "validation_count": self.validation_count,
            "source": self.source,
        }


class ImprovementRecommendationORM(Base):
    """Tier-1 improvement recommendations — the approval rail's pending queue.

    A data-driven, evidence-backed PROPOSAL produced by an analytics job
    (e.g. the MAE/MFE → SL/TP recommender). NOTHING here is applied
    automatically: a recommendation sits 'pending' until the CIO approves it
    via the approval rail (Path A), at which point the running system reads the
    override and applies it live (no deploy). LIVE recommendations are visibly
    gated and require explicit approval.

    rec_type:   'sl_tp' (stop/target) — extensible to other parameter classes.
    scope_type: 'symbol' (per-pair, maps to live_strategies params) |
                'template_asset_class' (template default for an asset class).
    scope_key:  the unique target key, e.g. 'SOXL' or 'ADX Trend::stocks'.
    status:     'pending' | 'applied' | 'rejected' | 'reverted'.
    """
    __tablename__ = "improvement_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.now, index=True)
    rec_type = Column(String(40), nullable=False, default="sl_tp")
    scope_type = Column(String(40), nullable=False)   # 'symbol' | 'template_asset_class'
    scope_key = Column(String(160), nullable=False, index=True)
    symbol = Column(String(40), nullable=True)
    template_name = Column(String(200), nullable=True)
    asset_class = Column(String(40), nullable=True)
    account_type = Column(String(20), nullable=True)  # 'demo' | 'live' | None (research/default)

    current_sl = Column(Float, nullable=True)
    proposed_sl = Column(Float, nullable=True)
    current_tp = Column(Float, nullable=True)
    proposed_tp = Column(Float, nullable=True)

    n_trades = Column(Integer, nullable=True)
    summary = Column(String, nullable=True)            # one-line human rationale
    evidence = Column(_RawJSON, nullable=True)         # mae/mfe percentiles, capture, etc.

    status = Column(String(20), nullable=False, default="pending", index=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewer = Column(String(80), nullable=True)
    applied_at = Column(DateTime, nullable=True)
    reverted_at = Column(DateTime, nullable=True)
    notes = Column(String, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "rec_type": self.rec_type,
            "scope_type": self.scope_type,
            "scope_key": self.scope_key,
            "symbol": self.symbol,
            "template_name": self.template_name,
            "asset_class": self.asset_class,
            "account_type": self.account_type,
            "current_sl": self.current_sl,
            "proposed_sl": self.proposed_sl,
            "current_tp": self.current_tp,
            "proposed_tp": self.proposed_tp,
            "n_trades": self.n_trades,
            "summary": self.summary,
            "evidence": self.evidence,
            "status": self.status,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer": self.reviewer,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "reverted_at": self.reverted_at.isoformat() if self.reverted_at else None,
            "notes": self.notes,
        }
