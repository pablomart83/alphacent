"""Enumerations for AlphaCent data models."""

from enum import Enum


class TradingMode(str, Enum):
    """Trading mode: demo or live."""
    DEMO = "DEMO"
    LIVE = "LIVE"


class StrategyStatus(str, Enum):
    """Strategy lifecycle status."""
    PROPOSED = "PROPOSED"
    BACKTESTED = "BACKTESTED"
    DEMO = "DEMO"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"
    INVALID = "INVALID"


class OrderSide(str, Enum):
    """Order side: buy or sell."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class PositionSide(str, Enum):
    """Position side: long or short."""
    LONG = "LONG"
    SHORT = "SHORT"


class SignalAction(str, Enum):
    """Trading signal action."""
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT_LONG = "EXIT_LONG"
    EXIT_SHORT = "EXIT_SHORT"


class DataSource(str, Enum):
    """Market data source."""
    ETORO = "ETORO"
    YAHOO_FINANCE = "YAHOO_FINANCE"
    FMP = "FMP"


class SystemStateEnum(str, Enum):
    """System autonomous trading state."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    EMERGENCY_HALT = "EMERGENCY_HALT"
