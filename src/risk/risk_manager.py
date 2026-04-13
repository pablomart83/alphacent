"""Risk management implementation for AlphaCent trading platform."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

from src.models import (
    AccountInfo,
    Position,
    PositionSide,
    RiskConfig,
    TradingSignal,
    SignalAction,
)

logger = logging.getLogger(__name__)


# --- Sector mapping for portfolio-level hedging ---
# Maps individual symbols to their sector classification.
# For non-stock asset classes (forex, crypto, commodities, indices),
# each is treated as its own "sector" for diversification purposes.

SYMBOL_SECTOR_MAP: Dict[str, str] = {}

def _load_sector_map():
    """Load sector map from SymbolRegistry (config/symbols.yaml)."""
    global SYMBOL_SECTOR_MAP
    try:
        from src.core.symbol_registry import get_registry
        SYMBOL_SECTOR_MAP = get_registry().get_sector_map()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not load sector map from registry: {e}")

# Load on import
_load_sector_map()


def get_symbol_sector(symbol: str) -> str:
    """Get the sector classification for a symbol.

    Returns the mapped sector or 'Unknown' if not found.
    """
    return SYMBOL_SECTOR_MAP.get(symbol.upper(), "Unknown")


# ---------------------------------------------------------------------------
# Volatility Estimators — asset-class-specific for position sizing
# ---------------------------------------------------------------------------
# Yang-Zhang (equities/commodities): uses open/high/low/close, ~14x efficiency
#   vs close-to-close. Captures overnight gap risk.
# Parkinson (crypto): uses high/low range, ~5.2x efficiency. Ideal for 24/7
#   markets with no gaps.
# Close-to-close with EWMA (forex): standard log-return variance with
#   exponential weighting. Low base vol → longer lookback avoids churn.
# Reference: Barroso & Santa-Clara (2015), RiskMetrics EWMA λ=0.94

def _get_asset_class_for_vol(symbol: str) -> str:
    """Classify symbol for volatility estimator selection."""
    sym = symbol.upper()
    try:
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
        )
        if sym in set(DEMO_ALLOWED_CRYPTO):
            return "crypto"
        if sym in set(DEMO_ALLOWED_FOREX):
            return "forex"
        if sym in set(DEMO_ALLOWED_COMMODITIES):
            return "commodity"
        if sym in set(DEMO_ALLOWED_INDICES):
            return "index"
    except ImportError:
        pass
    return "equity"


def estimate_realized_volatility(
    prices: list,
    asset_class: str = "equity",
    annualize: bool = True,
) -> Optional[float]:
    """
    Compute realized volatility using the best estimator for the asset class.

    Args:
        prices: List of dicts with keys 'open', 'high', 'low', 'close'.
                 For forex (close-to-close), only 'close' is required.
        asset_class: One of 'equity', 'crypto', 'commodity', 'forex', 'index'.
        annualize: If True, multiply by sqrt(252) for daily data.

    Returns:
        Annualized (or raw) volatility estimate, or None if insufficient data.
    """
    if not prices or len(prices) < 5:
        return None

    try:
        if asset_class in ("equity", "commodity", "index"):
            return _yang_zhang_vol(prices, annualize)
        elif asset_class == "crypto":
            return _parkinson_vol(prices, annualize)
        else:  # forex
            return _ewma_vol(prices, annualize, lam=0.97)
    except Exception as e:
        logger.debug(f"Volatility estimation failed ({asset_class}): {e}")
        return None


def _yang_zhang_vol(prices: list, annualize: bool) -> Optional[float]:
    """Yang-Zhang estimator: open/high/low/close. Best for gapped markets."""
    n = len(prices)
    if n < 5:
        return None

    log_oc = []  # overnight: log(open_t / close_{t-1})
    log_co = []  # close-to-open intraday: log(close_t / open_t)
    log_rs = []  # Rogers-Satchell

    for i in range(1, n):
        o = prices[i].get("open") or prices[i].get("close")
        h = prices[i].get("high") or prices[i].get("close")
        l = prices[i].get("low") or prices[i].get("close")
        c = prices[i].get("close")
        c_prev = prices[i - 1].get("close")

        if not all(v and v > 0 for v in [o, h, l, c, c_prev]):
            continue

        log_oc.append(math.log(o / c_prev))
        log_co.append(math.log(c / o))
        # Rogers-Satchell: log(h/c)*log(h/o) + log(l/c)*log(l/o)
        log_rs.append(
            math.log(h / c) * math.log(h / o) + math.log(l / c) * math.log(l / o)
        )

    if len(log_oc) < 5:
        return None

    T = len(log_oc)
    k = 0.34 / (1.34 + T / (T - 2)) if T > 2 else 0.34

    var_oc = sum(x ** 2 for x in log_oc) / (T - 1)
    var_co = sum(x ** 2 for x in log_co) / (T - 1)
    var_rs = sum(log_rs) / T

    sigma2 = var_oc + k * var_co + (1 - k) * var_rs
    sigma = math.sqrt(max(sigma2, 0))

    return sigma * math.sqrt(252) if annualize else sigma


def _parkinson_vol(prices: list, annualize: bool) -> Optional[float]:
    """Parkinson estimator: high-low range. Best for 24/7 crypto markets."""
    log_hl = []
    for p in prices:
        h = p.get("high")
        l = p.get("low")
        if h and l and h > 0 and l > 0 and h >= l:
            log_hl.append(math.log(h / l) ** 2)

    if len(log_hl) < 5:
        return None

    factor = 1.0 / (4.0 * len(log_hl) * math.log(2))
    sigma = math.sqrt(factor * sum(log_hl))

    return sigma * math.sqrt(365) if annualize else sigma  # crypto trades 365 days


def _ewma_vol(
    prices: list, annualize: bool, lam: float = 0.94
) -> Optional[float]:
    """EWMA close-to-close volatility. Best for forex (low base vol)."""
    closes = [p.get("close") for p in prices if p.get("close") and p["close"] > 0]
    if len(closes) < 5:
        return None

    log_returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    if not log_returns:
        return None

    # Initialize with first return squared
    var = log_returns[0] ** 2
    for r in log_returns[1:]:
        var = lam * var + (1 - lam) * r ** 2

    sigma = math.sqrt(max(var, 0))
    return sigma * math.sqrt(252) if annualize else sigma


@dataclass
class PortfolioBalanceReport:
    """Report on portfolio balance across sectors, directions, and strategy types."""
    is_balanced: bool
    violations: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    sector_exposures: Dict[str, float] = field(default_factory=dict)  # sector -> pct of total
    long_pct: float = 0.0
    short_pct: float = 0.0
    strategy_types: List[str] = field(default_factory=list)
    total_exposure: float = 0.0

# Strategy IDs that represent external (non-autonomous) positions
# Strategy IDs that represent external (non-autonomous) positions
# These are synced from eToro but not managed by the autonomous system
EXTERNAL_POSITION_STRATEGY_IDS = {
    "etoro_position",
    # Note: "manual" and "vibe_coding" removed as they're no longer used
    # Test data (strategy_1/2/3) has been cleaned up
}


@dataclass
class ValidationResult:
    """Result of signal validation."""
    is_valid: bool
    position_size: float
    reason: str
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class RiskManager:
    """Enforces risk limits and circuit breakers."""

    def __init__(self, config: RiskConfig):
        """
        Initialize RiskManager with risk configuration.

        Args:
            config: Risk configuration with limits and thresholds
        """
        self.config = config
        self._circuit_breaker_active = False
        self._kill_switch_active = False
        self._circuit_breaker_activated_at: Optional[datetime] = None
        self._kill_switch_activated_at: Optional[datetime] = None
        
        logger.info(
            f"RiskManager initialized with config: "
            f"max_position_size={config.max_position_size_pct:.1%}, "
            f"max_exposure={config.max_exposure_pct:.1%}, "
            f"max_daily_loss={config.max_daily_loss_pct:.1%}"
        )

    @staticmethod
    def _get_position_value(pos: Position) -> float:
        """Calculate the dollar value of a position.
        
        For eToro demo, quantity represents the dollar amount invested (not shares).
        Use invested_amount if available, otherwise use quantity directly since
        it IS the dollar amount for eToro positions.
        
        Args:
            pos: Position to calculate value for
            
        Returns:
            Dollar value of the position (actual capital invested)
        """
        # Use invested_amount if available (most accurate)
        invested = getattr(pos, 'invested_amount', None)
        if invested and invested > 0:
            return invested
        # For eToro demo, quantity = amount (dollars invested)
        # This works for both external and autonomous positions
        return pos.quantity

    @staticmethod
    def _filter_autonomous_positions(positions: List[Position]) -> List[Position]:
        """Filter positions to only include those managed by active autonomous strategies.
        
        Excludes:
        - External positions (from eToro sync, manual trades)
        - Closed positions
        - Positions pending closure
        - Orphaned positions (strategy no longer exists or is retired)
        
        Args:
            positions: All positions
            
        Returns:
            Only positions from active autonomous strategies
        """
        # Get set of active strategy IDs to detect orphaned positions
        active_strategy_ids = set()
        try:
            from src.models.database import get_database
            from src.models.orm import StrategyORM
            db = get_database()
            session = db.get_session()
            try:
                active = session.query(StrategyORM.id).filter(
                    StrategyORM.status.in_(["DEMO", "LIVE"])
                ).all()
                active_strategy_ids = {s.id for s in active}
            finally:
                session.close()
        except Exception:
            pass  # If DB unavailable, fall back to old behavior

        return [
            pos for pos in positions
            if pos.strategy_id not in EXTERNAL_POSITION_STRATEGY_IDS
            and pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
            and (not active_strategy_ids or pos.strategy_id in active_strategy_ids)
        ]

    def validate_signal(
        self, 
        signal: TradingSignal, 
        account: AccountInfo,
        positions: List[Position],
        strategy_allocation_pct: float = 1.0,
        portfolio_manager=None
    ) -> ValidationResult:
        """
        Validate trading signal against risk parameters.

        Args:
            signal: Trading signal to validate
            account: Current account information
            positions: List of current positions
            strategy_allocation_pct: Percentage of portfolio allocated to this strategy (default: 1.0%)
            portfolio_manager: PortfolioManager instance for correlation analysis (optional)

        Returns:
            ValidationResult with validation outcome and position size
        """
        # Check if kill switch is active
        if self._kill_switch_active:
            return ValidationResult(
                is_valid=False,
                position_size=0.0,
                reason="Kill switch is active - all trading halted"
            )

        # Check if circuit breaker is active (only blocks new entries)
        if self._circuit_breaker_active:
            if signal.action in [SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT]:
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason="Circuit breaker is active - new positions blocked"
                )

        # For entry signals, validate position limits and calculate size
        if signal.action in [SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT]:
            # Attach price history for volatility-scaled position sizing if not already present.
            # This fetches the last ~60 daily bars for the symbol — cheap call, cached by
            # market_data_manager, and only happens on entry signals (not exits).
            if signal.metadata is None:
                signal.metadata = {}
            if 'price_history' not in signal.metadata and hasattr(signal, 'symbol'):
                try:
                    from src.data.market_data_manager import MarketDataManager
                    import yaml
                    from pathlib import Path
                    config_path = Path("config/autonomous_trading.yaml")
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            cfg = yaml.safe_load(f) or {}
                        mdm = MarketDataManager(cfg)
                        from datetime import timedelta
                        end = datetime.now()
                        start = end - timedelta(days=90)
                        bars = mdm.get_historical_data(signal.symbol, start, end, interval="1d")
                        if bars and len(bars) >= 10:
                            signal.metadata['price_history'] = [
                                {
                                    'open': getattr(b, 'open', None),
                                    'high': getattr(b, 'high', None),
                                    'low': getattr(b, 'low', None),
                                    'close': getattr(b, 'close', None),
                                }
                                for b in bars[-63:]  # ~3 months of daily bars
                            ]
                except Exception as e:
                    logger.debug(f"Could not fetch price history for vol-scaling: {e}")

            # Calculate base position size with strategy allocation
            base_position_size = self.calculate_position_size(signal, account, positions, strategy_allocation_pct)
            
            if base_position_size <= 0:
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason="Calculated position size is zero or negative"
                )

            # Apply correlation adjustment if enabled
            position_size, correlation_reason = self.calculate_correlation_adjusted_size(
                base_position_size,
                signal,
                positions,
                portfolio_manager
            )
            
            # Apply regime-based adjustment if enabled
            position_size, regime_reason = self.calculate_regime_adjusted_size(
                position_size,
                signal,
                portfolio_manager
            )

            # Post-adjustment minimum floor: if correlation or regime adjustments
            # pushed the size below eToro's minimum, bump back up to minimum.
            # The system decided to trade this signal — submit at minimum rather than failing.
            MINIMUM_ORDER_SIZE_POST = 2000.0

            if 0 < position_size < MINIMUM_ORDER_SIZE_POST:
                MAX_BUMP_RATIO_POST = 10.0
                if position_size > 0 and MINIMUM_ORDER_SIZE_POST / position_size > MAX_BUMP_RATIO_POST:
                    logger.warning(
                        f"Post-adjustment size ${position_size:.2f} below eToro minimum "
                        f"${MINIMUM_ORDER_SIZE_POST:.0f} for {signal.symbol} — bump would be "
                        f"{MINIMUM_ORDER_SIZE_POST/position_size:.1f}x (>{MAX_BUMP_RATIO_POST:.0f}x max). "
                        f"Rejecting to avoid over-sizing."
                    )
                    return ValidationResult(
                        is_valid=False,
                        position_size=0.0,
                        reason=f"Post-adjustment size ${position_size:.2f} too far below minimum "
                               f"${MINIMUM_ORDER_SIZE_POST:.0f} (would require {MINIMUM_ORDER_SIZE_POST/position_size:.1f}x bump)"
                    )
                logger.info(
                    f"Post-adjustment size ${position_size:.2f} below eToro minimum "
                    f"${MINIMUM_ORDER_SIZE_POST:.0f} for {signal.symbol} — bumping to minimum"
                )
                position_size = MINIMUM_ORDER_SIZE_POST
            if not self.check_position_limits(signal.symbol, position_size, account, positions):
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason=f"Position would exceed max position size limit of {self.config.max_position_size_pct:.1%}"
                )

            # Check exposure limits
            if not self.check_exposure_limits(position_size, account, positions):
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason=f"Position would exceed max exposure limit of {self.config.max_exposure_pct:.1%}"
                )

            # Check symbol concentration limits (NEW)
            is_valid, reason = self.check_symbol_concentration(signal.symbol, position_size, account, positions)
            if not is_valid:
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason=reason
                )

            logger.info(
                f"Signal validated: {signal.symbol} {signal.action.value} "
                f"size={position_size:.2f} (base={base_position_size:.2f}) "
                f"confidence={signal.confidence:.2f} "
                f"allocation={strategy_allocation_pct:.1f}% "
                f"correlation_adjustment={correlation_reason} "
                f"regime_adjustment={regime_reason}"
            )

            return ValidationResult(
                is_valid=True,
                position_size=position_size,
                reason="Signal passed all risk checks",
                metadata={
                    "signal_id": signal.strategy_id,
                    "confidence": signal.confidence,
                    "generated_at": signal.generated_at.isoformat(),
                    "base_position_size": base_position_size,
                    "correlation_adjustment": correlation_reason,
                    "regime_adjustment": regime_reason
                }
            )

        # For exit signals, always allow (need to be able to close positions)
        else:
            logger.info(f"Exit signal validated: {signal.symbol} {signal.action.value}")
            return ValidationResult(
                is_valid=True,
                position_size=0.0,  # Exit signals don't need position size
                reason="Exit signal approved",
                metadata={"signal_id": signal.strategy_id}
            )

    def calculate_position_size(
        self,
        signal: TradingSignal,
        account: AccountInfo,
        positions: List[Position],
        strategy_allocation_pct: float = 1.0
    ) -> float:
        """
        Calculate position size based on account balance, risk percentage, and strategy allocation.

        Smart position sizing that:
        1. Uses strategy allocation percentage to limit capital per strategy
        2. Uses Kelly Criterion-inspired approach for optimal position sizing
        3. Applies volatility-based adjustment (reduces size in high volatility)
        4. Respects max position size limits
        5. Accounts for existing exposure
        6. Ensures minimum order size requirements

        Args:
            signal: Trading signal (may include volatility in metadata)
            account: Account information
            positions: Current positions
            strategy_allocation_pct: Percentage of portfolio allocated to this strategy (default: 1.0%)

        Returns:
            Position size in dollars
        """
        # Get available capital for new positions.
        # CRITICAL: On eToro, balance = cash only, margin_used = capital in positions.
        # When positions are profitable, equity > balance + margin_used because of
        # unrealized gains. Using (balance - margin_used) goes negative when margin
        # exceeds cash — which is normal when you have profitable positions.
        # The correct available capital is equity minus what's already deployed.
        portfolio_value = getattr(account, 'equity', None) or account.balance
        if portfolio_value <= 0:
            portfolio_value = account.balance

        # Calculate current exposure from ALL open positions
        current_exposure = sum(
            self._get_position_value(pos)
            for pos in positions
            if pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
        )

        available_capital = portfolio_value - current_exposure
        
        if available_capital <= 0:
            logger.warning(
                f"No available capital: equity=${portfolio_value:.0f}, "
                f"exposure=${current_exposure:.0f}, available=${available_capital:.0f}"
            )
            return 0.0

        # Calculate remaining exposure capacity based on EQUITY
        max_total_exposure = portfolio_value * self.config.max_exposure_pct
        remaining_exposure = max_total_exposure - current_exposure
        
        if remaining_exposure <= 0:
            logger.warning(f"Max exposure reached: {current_exposure:.2f} / {max_total_exposure:.2f} (equity=${portfolio_value:.0f})")
            return 0.0

        # Strategy allocation: use EQUITY (portfolio value) for the dollar amount.
        # The allocation percentage represents the strategy's share of the total portfolio.
        # Cash balance is low because capital is deployed in positions — that's normal.
        # A 5% allocation on $461K equity = $23K, which is the right scale for a
        # strategy managing positions worth $2-5K each.
        # The available_capital and remaining_exposure caps below prevent over-deployment.
        strategy_allocated_capital = portfolio_value * (strategy_allocation_pct / 100.0)
        
        # Calculate current exposure for THIS strategy
        strategy_current_exposure = sum(
            self._get_position_value(pos)
            for pos in positions 
            if pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
            and pos.strategy_id == signal.strategy_id
        )
        
        # Calculate remaining capital for this strategy
        strategy_remaining_capital = strategy_allocated_capital - strategy_current_exposure
        
        if strategy_remaining_capital <= 0:
            logger.warning(
                f"Strategy allocation exhausted: {strategy_current_exposure:.2f} / {strategy_allocated_capital:.2f} "
                f"(allocation: {strategy_allocation_pct:.1f}%)"
            )
            return 0.0

        # Smart position sizing based on confidence and available capital
        # Base position size: use signal confidence to scale between min and max
        confidence_factor = signal.confidence if signal.confidence > 0 else 0.5
        
        # Volatility-scaled position sizing: normalize risk contribution across
        # all asset classes by dividing by realized volatility.
        # Target vol per position: equity-like 16% annualized.
        # A crypto position with 60% vol gets sized ~3.75x smaller than a stock
        # with 16% vol. A forex pair with 8% vol gets sized 2x larger.
        # This is how institutional momentum funds (AQR, Barroso & Santa-Clara 2015)
        # ensure high-vol assets don't dominate portfolio risk.
        TARGET_VOL = 0.16  # 16% annualized — equity-like baseline
        VOL_SCALE_MIN = 0.25  # Never scale below 25% of base size
        VOL_SCALE_MAX = 2.5   # Never scale above 250% of base size
        
        volatility_adjustment = 1.0
        if signal.metadata and 'price_history' in signal.metadata:
            # Full OHLC history available — use asset-class-specific estimator
            asset_class = _get_asset_class_for_vol(getattr(signal, 'symbol', ''))
            realized_vol = estimate_realized_volatility(
                signal.metadata['price_history'], asset_class=asset_class
            )
            if realized_vol and realized_vol > 0:
                raw_scale = TARGET_VOL / realized_vol
                volatility_adjustment = max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, raw_scale))
                logger.debug(
                    f"Vol-scaling {getattr(signal, 'symbol', '?')}: "
                    f"realized_vol={realized_vol:.1%}, target={TARGET_VOL:.0%}, "
                    f"scale={volatility_adjustment:.2f}x ({asset_class})"
                )
        elif signal.metadata and 'volatility' in signal.metadata:
            # Legacy path: single volatility number provided
            volatility = signal.metadata['volatility']
            if volatility > 0:
                raw_scale = TARGET_VOL / volatility
                volatility_adjustment = max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, raw_scale))
                logger.debug(f"Vol-scaling (legacy): vol={volatility:.4f} -> {volatility_adjustment:.2f}x")
        
        # Calculate position size as percentage of STRATEGY'S allocated capital
        # Scale from 20% (low confidence) to 100% (high confidence) of strategy allocation
        min_position_pct = 0.20  # 20% of strategy allocation minimum
        max_position_pct = 1.00  # 100% of strategy allocation maximum
        position_pct = min_position_pct + (max_position_pct - min_position_pct) * confidence_factor
        
        # Apply volatility adjustment to position percentage
        position_pct *= volatility_adjustment
        
        # Calculate dollar amount based on strategy's allocated capital
        position_size = strategy_allocated_capital * position_pct

        # Cap at strategy's remaining capital
        position_size = min(position_size, strategy_remaining_capital)

        # Cap at remaining total exposure capacity
        position_size = min(position_size, remaining_exposure)

        # Cap at available capital
        position_size = min(position_size, available_capital)

        # Ensure minimum order size: $2000 across all asset classes
        MINIMUM_ORDER_SIZE = 2000.0

        if position_size < MINIMUM_ORDER_SIZE:
            # Bump to minimum if the calculated size is at least $200 (10x guard).
            # A strategy that wants to trade with $400-$500 gets bumped to $2K —
            # that's acceptable, the strategy has conviction and we want meaningful
            # position sizes. Only reject truly tiny allocations (<$200).
            MAX_BUMP_RATIO = 10.0
            if available_capital >= MINIMUM_ORDER_SIZE and remaining_exposure >= MINIMUM_ORDER_SIZE:
                if position_size > 0 and MINIMUM_ORDER_SIZE / position_size > MAX_BUMP_RATIO:
                    logger.warning(
                        f"Position size ${position_size:.2f} below eToro minimum ${MINIMUM_ORDER_SIZE:.0f} "
                        f"for {getattr(signal, 'symbol', '?')} — bump would be {MINIMUM_ORDER_SIZE/position_size:.1f}x "
                        f"(>{MAX_BUMP_RATIO:.0f}x max). Rejecting to avoid over-sizing. "
                        f"Strategy allocation too small for this asset class."
                    )
                    return 0.0
                logger.info(
                    f"Position size ${position_size:.2f} below eToro minimum ${MINIMUM_ORDER_SIZE:.0f} "
                    f"for {getattr(signal, 'symbol', '?')} — bumping to minimum"
                )
                position_size = MINIMUM_ORDER_SIZE
            else:
                logger.warning(
                    f"Calculated position size ${position_size:.2f} is below minimum ${MINIMUM_ORDER_SIZE:.0f}. "
                    f"Strategy allocation too low ({strategy_allocation_pct:.1f}% = ${strategy_allocated_capital:.2f})"
                )
                return 0.0

        logger.debug(
            f"Position size calculation: balance=${account.balance:.2f}, "
            f"strategy_allocation={strategy_allocation_pct:.1f}% (${strategy_allocated_capital:.2f}), "
            f"confidence={confidence_factor:.2f}, position_pct={position_pct:.1%}, "
            f"calculated_size=${position_size:.2f}, "
            f"strategy_exposure={strategy_current_exposure:.2f}/{strategy_allocated_capital:.2f}, "
            f"total_exposure={current_exposure:.2f}/{max_total_exposure:.2f}"
        )

        return position_size

    def check_position_limits(
        self,
        symbol: str,
        position_size: float,
        account: AccountInfo,
        positions: List[Position]
    ) -> bool:
        """
        Check if new position would exceed position size limits.

        Args:
            symbol: Symbol for the position
            position_size: Size of the new position in dollars
            account: Account information
            positions: Current positions

        Returns:
            True if within limits, False otherwise
        """
        # Check if position size exceeds max position size (based on equity)
        portfolio_value = getattr(account, 'equity', None) or account.balance
        max_position_value = portfolio_value * self.config.max_position_size_pct
        
        # Check existing position in this symbol (all positions including external)
        existing_position_value = 0.0
        for pos in positions:
            if pos.symbol == symbol and pos.closed_at is None and not getattr(pos, 'pending_closure', False):
                existing_position_value += self._get_position_value(pos)

        total_position_value = existing_position_value + position_size

        if total_position_value > max_position_value:
            logger.warning(
                f"Position limit exceeded for {symbol}: "
                f"total={total_position_value:.2f} > max={max_position_value:.2f}"
            )
            return False

        return True
    def check_symbol_concentration(
        self,
        symbol: str,
        position_size: float,
        account: AccountInfo,
        positions: List[Position]
    ) -> tuple[bool, str]:
        """
        Check if new position would exceed symbol concentration limits.

        Prevents too much capital concentrated in a single symbol across all strategies.
        This is critical for managing correlation risk and avoiding over-exposure.

        Args:
            symbol: Symbol for the position
            position_size: Size of the new position in dollars
            account: Account information
            positions: Current positions

        Returns:
            Tuple of (is_valid, reason)
        """
        # Calculate existing exposure to this symbol (all positions including external)
        existing_symbol_exposure = 0.0
        strategies_holding_symbol = set()

        for pos in positions:
            if pos.symbol == symbol and pos.closed_at is None and not getattr(pos, 'pending_closure', False):
                existing_symbol_exposure += self._get_position_value(pos)
                strategies_holding_symbol.add(pos.strategy_id)

        # Check 1: Symbol exposure limit (based on equity)
        total_symbol_exposure = existing_symbol_exposure + position_size
        portfolio_value = getattr(account, 'equity', None) or account.balance
        max_symbol_exposure = portfolio_value * self.config.max_symbol_exposure_pct

        if total_symbol_exposure > max_symbol_exposure:
            logger.warning(
                f"Symbol concentration limit exceeded for {symbol}: "
                f"total={total_symbol_exposure:.2f} > max={max_symbol_exposure:.2f} "
                f"({self.config.max_symbol_exposure_pct:.1%} of portfolio)"
            )
            return False, (
                f"Symbol concentration limit: {symbol} exposure would be "
                f"${total_symbol_exposure:.2f} (max ${max_symbol_exposure:.2f}, "
                f"{self.config.max_symbol_exposure_pct:.1%} of portfolio)"
            )

        # Check 2: Max strategies per symbol limit
        if len(strategies_holding_symbol) >= self.config.max_strategies_per_symbol:
            logger.warning(
                f"Max strategies per symbol limit reached for {symbol}: "
                f"{len(strategies_holding_symbol)} strategies already holding "
                f"(max {self.config.max_strategies_per_symbol})"
            )
            return False, (
                f"Max strategies per symbol: {len(strategies_holding_symbol)} strategies "
                f"already hold {symbol} (max {self.config.max_strategies_per_symbol})"
            )

        # Check 3: Max positions per symbol limit (count-based, not just strategy-based)
        position_count_for_symbol = sum(
            1 for pos in positions
            if pos.symbol == symbol and pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
        )
        max_positions = getattr(self.config, 'max_positions_per_symbol', 3)
        if position_count_for_symbol >= max_positions:
            logger.warning(
                f"Max positions per symbol limit reached for {symbol}: "
                f"{position_count_for_symbol} positions already open "
                f"(max {max_positions})"
            )
            return False, (
                f"Max positions per symbol: {position_count_for_symbol} positions "
                f"already open for {symbol} (max {max_positions})"
            )

        return True, "Symbol concentration checks passed"

    def check_directional_balance(
        self,
        signal: TradingSignal,
        position_size: float,
        account: AccountInfo,
        positions: List[Position]
    ) -> tuple[bool, str]:
        """
        Check if new position would create excessive directional imbalance.

        Prevents the portfolio from being overwhelmingly long or short,
        which creates systemic risk during market moves.

        Args:
            signal: Trading signal (to determine direction)
            position_size: Size of the new position in dollars
            account: Account information
            positions: Current positions

        Returns:
            Tuple of (is_valid, reason)
        """
        # Calculate current long and short exposure (all positions including external)
        long_exposure = 0.0
        short_exposure = 0.0

        for pos in positions:
            if pos.closed_at is None and not getattr(pos, 'pending_closure', False):
                value = self._get_position_value(pos)
                if pos.side == PositionSide.LONG:
                    long_exposure += value
                elif pos.side == PositionSide.SHORT:
                    short_exposure += value

        # Add the proposed position
        is_long = signal.action == SignalAction.ENTER_LONG
        if is_long:
            proposed_long = long_exposure + position_size
            proposed_short = short_exposure
        else:
            proposed_long = long_exposure
            proposed_short = short_exposure + position_size

        total_exposure = proposed_long + proposed_short
        if total_exposure <= 0:
            return True, "No exposure to check"

        # Check long exposure limit (based on equity)
        portfolio_value = getattr(account, 'equity', None) or account.balance
        max_long = portfolio_value * getattr(self.config, 'max_long_exposure_pct', 0.75)
        if proposed_long > max_long:
            logger.warning(
                f"Long exposure limit exceeded: ${proposed_long:.2f} > ${max_long:.2f} "
                f"({getattr(self.config, 'max_long_exposure_pct', 0.75):.0%} of equity)"
            )
            return False, (
                f"Long exposure limit: ${proposed_long:.2f} exceeds max ${max_long:.2f} "
                f"({getattr(self.config, 'max_long_exposure_pct', 0.75):.0%} of equity)"
            )

        # Check short exposure limit (based on equity)
        max_short = portfolio_value * getattr(self.config, 'max_short_exposure_pct', 0.50)
        if proposed_short > max_short:
            logger.warning(
                f"Short exposure limit exceeded: ${proposed_short:.2f} > ${max_short:.2f} "
                f"({getattr(self.config, 'max_short_exposure_pct', 0.50):.0%} of equity)"
            )
            return False, (
                f"Short exposure limit: ${proposed_short:.2f} exceeds max ${max_short:.2f} "
                f"({getattr(self.config, 'max_short_exposure_pct', 0.50):.0%} of equity)"
            )

        long_pct = proposed_long / portfolio_value if portfolio_value > 0 else 0
        short_pct = proposed_short / portfolio_value if portfolio_value > 0 else 0
        logger.info(
            f"Directional balance OK: long={long_pct:.1%}, short={short_pct:.1%}"
        )
        return True, "Directional balance checks passed"

    def calculate_correlation_adjusted_size(
        self,
        base_position_size: float,
        signal: TradingSignal,
        positions: List[Position],
        portfolio_manager=None
    ) -> tuple[float, str]:
        """
        Adjust position size based on correlation with existing positions.

        Uses PortfolioManager.get_correlated_positions() to identify positions
        that are highly correlated (same symbol or high strategy correlation).
        Reduces position size when adding correlated positions to avoid
        over-concentration and correlation risk.

        Formula: adjusted_size = base_size * (1 - correlation * 0.5)

        Args:
            base_position_size: Base position size before adjustment
            signal: Trading signal with strategy_id and symbol
            positions: Current positions
            portfolio_manager: PortfolioManager instance (optional, for strategy correlation)

        Returns:
            Tuple of (adjusted_size, reason)
        """
        if not self.config.correlation_adjustment_enabled:
            return (base_position_size, "Correlation adjustment disabled")

        # Check for same symbol positions (perfect correlation = 1.0)
        # Exclude external positions — they represent manual trades that the
        # autonomous system shouldn't adjust its sizing for.
        same_symbol_positions = [
            pos for pos in positions
            if pos.symbol == signal.symbol
            and pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
            and pos.strategy_id not in EXTERNAL_POSITION_STRATEGY_IDS
        ]

        if same_symbol_positions:
            # Same symbol = correlation 1.0
            correlation = 1.0
            adjusted_size = base_position_size * (1 - correlation * 0.5)
            
            reason = (
                f"Reduced to {adjusted_size:.2f} (from {base_position_size:.2f}) "
                f"due to same symbol correlation (1.0) with {len(same_symbol_positions)} position(s)"
            )
            
            logger.info(
                f"Correlation-adjusted position sizing for {signal.symbol}: "
                f"${base_position_size:.2f} → ${adjusted_size:.2f} (50% reduction). "
                f"Reason: {reason}"
            )
            
            return (adjusted_size, reason)

        # Check for strategy correlation if PortfolioManager is available
        if portfolio_manager is not None:
            try:
                correlated_positions = portfolio_manager.get_correlated_positions(
                    new_trade_symbol=signal.symbol,
                    new_trade_strategy_id=signal.strategy_id,
                    correlation_threshold=0.7
                )

                if correlated_positions:
                    # Find the highest correlation
                    max_correlation = max(pos['correlation'] for pos in correlated_positions)
                    
                    # Apply adjustment formula
                    adjusted_size = base_position_size * (1 - max_correlation * 0.5)
                    
                    correlated_symbols = [pos['symbol'] for pos in correlated_positions]
                    reason = (
                        f"Reduced to {adjusted_size:.2f} (from {base_position_size:.2f}) "
                        f"due to correlation {max_correlation:.2f} with {len(correlated_positions)} position(s): "
                        f"{', '.join(correlated_symbols)}"
                    )
                    
                    logger.info(
                        f"Correlation-adjusted position sizing for {signal.symbol}: "
                        f"${base_position_size:.2f} → ${adjusted_size:.2f} "
                        f"({(1 - max_correlation * 0.5):.1%} of base). "
                        f"Reason: {reason}"
                    )
                    
                    return (adjusted_size, reason)

            except Exception as e:
                logger.warning(
                    f"Failed to calculate strategy correlation for {signal.symbol}: {e}. "
                    f"Using base position size."
                )

        # No correlation found
        return (base_position_size, "No correlated positions found")
    def calculate_regime_adjusted_size(
        self,
        base_position_size: float,
        signal: TradingSignal,
        portfolio_manager=None
    ) -> tuple[float, str]:
        """
        Adjust position size based on current market regime.

        Different market conditions warrant different position sizing:
        - High volatility: Reduce size to manage risk (0.5x)
        - Low volatility: Normal size (1.0x)
        - Trending: Increase size to capture momentum (1.2x)
        - Ranging: Reduce size due to choppiness (0.8x)

        Uses MarketStatisticsAnalyzer via PortfolioManager to detect current regime.

        Args:
            base_position_size: Base position size before adjustment
            signal: Trading signal with strategy_id and symbol
            portfolio_manager: PortfolioManager instance (optional, for regime detection)

        Returns:
            Tuple of (adjusted_size, reason)
        """
        if not self.config.regime_based_sizing_enabled:
            return (base_position_size, "Regime-based sizing disabled")

        if portfolio_manager is None or not hasattr(portfolio_manager, 'market_analyzer'):
            return (base_position_size, "No market analyzer available")

        try:
            # Get current market regime from MarketStatisticsAnalyzer
            market_analyzer = portfolio_manager.market_analyzer
            regime, confidence, data_quality, metrics = market_analyzer.detect_sub_regime(
                symbols=[signal.symbol]
            )

            # Map detailed regime to multiplier category
            regime_str = regime.value if hasattr(regime, 'value') else str(regime)

            # Determine multiplier category based on regime
            if 'high_vol' in regime_str.lower() or 'volatile' in regime_str.lower():
                category = 'high_volatility'
            elif 'low_vol' in regime_str.lower():
                category = 'low_volatility'
            elif 'trending' in regime_str.lower():
                category = 'trending'
            elif 'ranging' in regime_str.lower():
                category = 'ranging'
            else:
                # Default to ranging for unknown regimes
                category = 'ranging'

            # Get multiplier from config
            multiplier = self.config.regime_size_multipliers.get(category, 1.0)

            # Apply multiplier
            adjusted_size = base_position_size * multiplier

            reason = (
                f"Adjusted to {adjusted_size:.2f} (from {base_position_size:.2f}) "
                f"based on {regime_str} regime (multiplier: {multiplier:.1f}x, "
                f"confidence: {confidence:.2f})"
            )

            logger.info(
                f"Regime-based position sizing for {signal.symbol}: "
                f"${base_position_size:.2f} → ${adjusted_size:.2f} "
                f"(regime: {regime_str}, multiplier: {multiplier:.1f}x). "
                f"Reason: {reason}"
            )

            return (adjusted_size, reason)

        except Exception as e:
            logger.warning(
                f"Failed to apply regime-based sizing for {signal.symbol}: {e}. "
                f"Using base position size."
            )
            return (base_position_size, f"Regime detection failed: {str(e)}")



    def check_exposure_limits(
        self,
        position_size: float,
        account: AccountInfo,
        positions: List[Position]
    ) -> bool:
        """
        Check if total exposure within limits.

        Args:
            position_size: Size of the new position in dollars
            account: Account information
            positions: Current positions

        Returns:
            True if within limits, False otherwise
        """
        # Calculate current total exposure (all positions including external)
        # External positions are now included so the system sees manual eToro
        # trades and doesn't pile on more exposure to the same assets
        current_exposure = sum(
            self._get_position_value(pos)
            for pos in positions 
            if pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
        )

        # Add new position
        total_exposure = current_exposure + position_size

        # Check against max exposure (based on equity, not cash balance)
        portfolio_value = getattr(account, 'equity', None) or account.balance
        max_exposure = portfolio_value * self.config.max_exposure_pct

        if total_exposure > max_exposure:
            logger.warning(
                f"Exposure limit exceeded: "
                f"total={total_exposure:.2f} > max={max_exposure:.2f}"
            )
            return False

        return True

    def check_portfolio_balance(
        self,
        positions: List[Position],
        account: AccountInfo,
        strategy_types: List[str] = None,
        max_sector_exposure_pct: float = 0.40,
        max_directional_exposure_pct: float = 0.60,
        min_strategy_types: int = 2,
    ) -> PortfolioBalanceReport:
        """
        Check portfolio balance across sectors, directions, and strategy types.

        Evaluates whether the current portfolio is well-diversified or has
        concentration risks that should influence signal prioritization.

        Args:
            positions: Current open positions
            account: Account information
            strategy_types: List of currently active strategy type names
            max_sector_exposure_pct: Max allowed exposure to any single sector (0-1)
            max_directional_exposure_pct: Max allowed exposure in one direction (0-1)
            min_strategy_types: Minimum number of different strategy types required

        Returns:
            PortfolioBalanceReport with violations and recommendations
        """
        if strategy_types is None:
            strategy_types = []

        violations = []
        recommendations = []

        # Filter to autonomous open positions only
        auto_positions = self._filter_autonomous_positions(positions)

        if not auto_positions:
            return PortfolioBalanceReport(
                is_balanced=True,
                violations=[],
                recommendations=["No open positions — portfolio is empty"],
                sector_exposures={},
                long_pct=0.0,
                short_pct=0.0,
                strategy_types=strategy_types,
                total_exposure=0.0,
            )

        # --- Calculate sector exposure ---
        sector_values: Dict[str, float] = {}
        total_exposure = 0.0
        long_exposure = 0.0
        short_exposure = 0.0

        for pos in auto_positions:
            value = self._get_position_value(pos)
            total_exposure += value
            sector = get_symbol_sector(pos.symbol)
            sector_values[sector] = sector_values.get(sector, 0.0) + value

            if pos.side == PositionSide.LONG:
                long_exposure += value
            elif pos.side == PositionSide.SHORT:
                short_exposure += value

        # Compute percentages
        sector_exposures: Dict[str, float] = {}
        if total_exposure > 0:
            for sector, value in sector_values.items():
                pct = value / total_exposure
                sector_exposures[sector] = round(pct, 4)
                if pct > max_sector_exposure_pct:
                    violations.append(
                        f"Sector '{sector}' exposure {pct:.1%} exceeds max {max_sector_exposure_pct:.0%}"
                    )
                    recommendations.append(
                        f"Reduce '{sector}' exposure or add positions in other sectors"
                    )

        # --- Directional balance ---
        long_pct = 0.0
        short_pct = 0.0
        if total_exposure > 0:
            long_pct = long_exposure / total_exposure
            short_pct = short_exposure / total_exposure

            if long_pct > max_directional_exposure_pct:
                violations.append(
                    f"Long exposure {long_pct:.1%} exceeds max {max_directional_exposure_pct:.0%}"
                )
                recommendations.append("Add short positions to balance directional exposure")

            if short_pct > max_directional_exposure_pct:
                violations.append(
                    f"Short exposure {short_pct:.1%} exceeds max {max_directional_exposure_pct:.0%}"
                )
                recommendations.append("Add long positions to balance directional exposure")

        # --- Strategy type diversity ---
        unique_types = list(set(strategy_types)) if strategy_types else []
        if len(unique_types) < min_strategy_types and len(auto_positions) >= min_strategy_types:
            violations.append(
                f"Only {len(unique_types)} strategy type(s) active, need at least {min_strategy_types}"
            )
            recommendations.append("Activate strategies of different types for diversification")

        is_balanced = len(violations) == 0

        if is_balanced:
            logger.info(
                f"Portfolio balance OK: {len(auto_positions)} positions, "
                f"{len(sector_exposures)} sectors, long={long_pct:.1%}, short={short_pct:.1%}, "
                f"{len(unique_types)} strategy types"
            )
        else:
            logger.warning(
                f"Portfolio imbalance detected: {len(violations)} violation(s) — "
                + "; ".join(violations)
            )

        return PortfolioBalanceReport(
            is_balanced=is_balanced,
            violations=violations,
            recommendations=recommendations,
            sector_exposures=sector_exposures,
            long_pct=round(long_pct, 4),
            short_pct=round(short_pct, 4),
            strategy_types=unique_types,
            total_exposure=round(total_exposure, 2),
        )

    def would_signal_improve_balance(
        self,
        signal: TradingSignal,
        balance_report: PortfolioBalanceReport,
    ) -> bool:
        """
        Determine whether a signal would improve portfolio balance.

        A signal improves balance if:
        - It adds exposure to an under-represented sector
        - It adds a position in the under-represented direction
        - The portfolio is already balanced (any signal is fine)

        Args:
            signal: The candidate trading signal
            balance_report: Current portfolio balance report

        Returns:
            True if the signal would improve or maintain balance
        """
        if balance_report.is_balanced:
            return True

        signal_sector = get_symbol_sector(signal.symbol)
        is_long = signal.action == SignalAction.ENTER_LONG

        improves = False

        for violation in balance_report.violations:
            # If long-heavy, a short signal helps
            if "Long exposure" in violation and not is_long:
                improves = True
            # If short-heavy, a long signal helps
            elif "Short exposure" in violation and is_long:
                improves = True
            # If a sector is over-exposed, a signal in a DIFFERENT sector helps
            elif "Sector" in violation and signal_sector not in violation:
                improves = True

        return improves

    def would_signal_worsen_balance(
        self,
        signal: TradingSignal,
        balance_report: PortfolioBalanceReport,
        max_sector_exposure_pct: float = 0.40,
        max_directional_exposure_pct: float = 0.60,
    ) -> tuple[bool, str]:
        """
        Determine whether a signal would worsen an existing imbalance.

        Args:
            signal: The candidate trading signal
            balance_report: Current portfolio balance report
            max_sector_exposure_pct: Sector exposure threshold
            max_directional_exposure_pct: Directional exposure threshold

        Returns:
            Tuple of (would_worsen, reason)
        """
        if balance_report.is_balanced:
            return False, ""

        signal_sector = get_symbol_sector(signal.symbol)
        is_long = signal.action == SignalAction.ENTER_LONG

        # Check if signal adds to an already over-exposed sector
        sector_pct = balance_report.sector_exposures.get(signal_sector, 0.0)
        if sector_pct > max_sector_exposure_pct:
            return True, (
                f"Would worsen sector imbalance: '{signal_sector}' already at {sector_pct:.1%} "
                f"(max {max_sector_exposure_pct:.0%})"
            )

        # Check if signal adds to an already over-exposed direction
        if is_long and balance_report.long_pct > max_directional_exposure_pct:
            return True, (
                f"Would worsen directional imbalance: long already at {balance_report.long_pct:.1%} "
                f"(max {max_directional_exposure_pct:.0%})"
            )
        if not is_long and balance_report.short_pct > max_directional_exposure_pct:
            return True, (
                f"Would worsen directional imbalance: short already at {balance_report.short_pct:.1%} "
                f"(max {max_directional_exposure_pct:.0%})"
            )

        return False, ""

    def check_circuit_breaker(self, account: AccountInfo, daily_pnl: float) -> bool:
        """
        Check if circuit breaker should activate based on daily loss limits.

        Args:
            account: Account information
            daily_pnl: Daily profit/loss

        Returns:
            True if circuit breaker should activate, False otherwise
        """
        portfolio_value = getattr(account, 'equity', None) or account.balance
        max_daily_loss = -portfolio_value * self.config.max_daily_loss_pct

        if daily_pnl <= max_daily_loss:
            logger.warning(
                f"Daily loss limit reached: "
                f"daily_pnl={daily_pnl:.2f} <= max_loss={max_daily_loss:.2f}"
            )
            return True

        return False

    def activate_circuit_breaker(self) -> None:
        """
        Activate circuit breaker to halt new positions.
        
        When active, the circuit breaker prevents new position entries
        but allows exits to close existing positions.
        """
        if not self._circuit_breaker_active:
            self._circuit_breaker_active = True
            self._circuit_breaker_activated_at = datetime.now()
            logger.critical(
                f"CIRCUIT BREAKER ACTIVATED at {self._circuit_breaker_activated_at.isoformat()}"
            )
        else:
            logger.warning("Circuit breaker already active")

    def reset_circuit_breaker(self) -> None:
        """
        Reset circuit breaker to allow new positions.
        
        This should typically be called at the start of a new trading day
        or manually by the user after reviewing the situation.
        """
        if self._circuit_breaker_active:
            self._circuit_breaker_active = False
            deactivated_at = datetime.now()
            duration = (deactivated_at - self._circuit_breaker_activated_at).total_seconds()
            logger.info(
                f"Circuit breaker reset after {duration:.0f} seconds. "
                f"New positions now allowed."
            )
            self._circuit_breaker_activated_at = None
        else:
            logger.info("Circuit breaker was not active")

    def is_circuit_breaker_active(self) -> bool:
        """Check if circuit breaker is currently active."""
        return self._circuit_breaker_active

    def is_kill_switch_active(self) -> bool:
        """Check if kill switch is currently active."""
        return self._kill_switch_active

    def execute_kill_switch(self, reason: str) -> None:
        """
        Execute kill switch to halt all trading.
        
        This is a destructive operation that:
        1. Sets kill switch flag to block all new signals
        2. Marks the system for position closure (actual closure handled by OrderExecutor)
        
        Args:
            reason: Reason for kill switch activation
        """
        if not self._kill_switch_active:
            self._kill_switch_active = True
            self._kill_switch_activated_at = datetime.now()
            logger.critical(
                f"KILL SWITCH ACTIVATED at {self._kill_switch_activated_at.isoformat()}: {reason}"
            )
        else:
            logger.warning(f"Kill switch already active. Additional reason: {reason}")

    def reset_kill_switch(self) -> None:
        """
        Reset kill switch to allow trading.
        
        This should only be called manually by the user after:
        1. Reviewing the situation that triggered the kill switch
        2. Confirming all positions are closed
        3. Verifying system state is correct
        """
        if self._kill_switch_active:
            self._kill_switch_active = False
            deactivated_at = datetime.now()
            duration = (deactivated_at - self._kill_switch_activated_at).total_seconds()
            logger.info(
                f"Kill switch reset after {duration:.0f} seconds. "
                f"Trading now allowed."
            )
            self._kill_switch_activated_at = None
        else:
            logger.info("Kill switch was not active")

    def get_status(self) -> dict:
        """
        Get current risk manager status.

        Returns:
            Dictionary with status information
        """
        return {
            "circuit_breaker_active": self._circuit_breaker_active,
            "circuit_breaker_activated_at": (
                self._circuit_breaker_activated_at.isoformat() 
                if self._circuit_breaker_activated_at else None
            ),
            "kill_switch_active": self._kill_switch_active,
            "kill_switch_activated_at": (
                self._kill_switch_activated_at.isoformat() 
                if self._kill_switch_activated_at else None
            ),
            "config": {
                "max_position_size_pct": self.config.max_position_size_pct,
                "max_exposure_pct": self.config.max_exposure_pct,
                "max_daily_loss_pct": self.config.max_daily_loss_pct,
                "max_drawdown_pct": self.config.max_drawdown_pct,
                "position_risk_pct": self.config.position_risk_pct,
            }
        }
