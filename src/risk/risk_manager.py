"""Risk management implementation for AlphaCent trading platform."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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

        # Last sizing decision — populated by calculate_position_size on
        # every call, read by validate_signal for observability (decision-log
        # writes when a signal dies in sizing). Key is used as the `reason`
        # field in the gate_blocked decision row.
        self._last_sizing_reason: str = ""

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

    def _get_pending_entry_exposure(
        self,
        symbol: str,
    ) -> tuple[float, set, int]:
        """Return pending (not-yet-filled) entry exposure for a symbol.

        Returns:
            (pending_exposure_dollars, strategies_with_pending_entry, pending_entry_count)

        Why this exists (2026-05-04 audit):
            The symbol concentration cap used to scan only `positions`
            (filled, closed_at IS NULL). Between signal-time and
            fill-time (minutes to hours on a market-closed deferral),
            two distinct strategies with different primary symbols but
            overlapping watchlists could both fire entries on the same
            watchlist symbol. Each strategy's cap check saw
            existing_exposure = $0 (no fills yet) and sized to the full
            5% budget. When both filled, combined exposure hit ~7.3%
            of equity — cap breached. Observed live: URI 2×$17.5K
            orders from '4H ADX Trend Swing CAT LONG' + '...NXPI LONG'
            at 09:34 and 09:43 UTC.

            The proper fix is to make the cap check read the same world
            the next cycle will read: filled positions PLUS pending
            entries. This helper is the bridge.

        Why only 'entry' orders:
            - entry orders add exposure
            - close orders reduce an existing position that is already
              counted in `positions`; counting them would double-count
              the reduction
            - retirement orders are position-closures with a different
              origin; same net-zero on current-exposure reasoning
            - NULL order_action (legacy rows pre-2026-05-02): treat as
              entry to be conservative (any remaining ambiguity leans
              toward NOT over-sizing)

        Fail-open: DB errors return (0, set(), 0) and log a warning.
        A broken DB read must not cause the risk manager to crash the
        signal path; the worst case is this check reverts to the
        previous (positions-only) behaviour for the single failure.

        Args:
            symbol: Symbol to check. Case-insensitive — normalized
                    to the form stored in orders.symbol via upper().

        Returns:
            Tuple of (pending_dollars, pending_strategy_id_set, count).
        """
        try:
            from src.models.database import get_database
            from src.models.orm import OrderORM
            from src.models.enums import OrderStatus
            db = get_database()
            session = db.get_session()
            try:
                # PENDING + PARTIALLY_FILLED cover the in-flight states.
                # Entries in these states WILL consume symbol budget once
                # they fill (or have already consumed part of it via the
                # filled leg of a PARTIALLY_FILLED order — which is why
                # we count the full notional; the filled leg is already
                # in `positions` but the still-pending leg is not).
                rows = (
                    session.query(
                        OrderORM.strategy_id,
                        OrderORM.quantity,
                        OrderORM.order_action,
                    )
                    .filter(
                        OrderORM.symbol == symbol.upper(),
                        OrderORM.status.in_([
                            OrderStatus.PENDING.value,
                            OrderStatus.PARTIALLY_FILLED.value,
                        ]),
                    )
                    .all()
                )
            finally:
                session.close()
        except Exception as e:
            logger.warning(
                f"Pending-order exposure query failed for {symbol}: {e} — "
                f"cap check will use positions-only exposure (fail-open)"
            )
            return 0.0, set(), 0

        pending_exposure = 0.0
        pending_strategies: set = set()
        pending_count = 0
        for strategy_id, quantity, order_action in rows:
            # Treat NULL order_action as 'entry' (conservative default
            # for legacy rows — counting them can only tighten the cap,
            # which is the safe direction).
            if order_action in ('close', 'retirement'):
                continue
            try:
                q = float(quantity or 0.0)
            except (TypeError, ValueError):
                q = 0.0
            if q <= 0:
                continue
            pending_exposure += q
            if strategy_id:
                pending_strategies.add(strategy_id)
            pending_count += 1

        if pending_count > 0:
            logger.debug(
                f"Pending-entry exposure for {symbol}: "
                f"${pending_exposure:.0f} across {pending_count} order(s) "
                f"from {len(pending_strategies)} strategy/ies"
            )

        return pending_exposure, pending_strategies, pending_count

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

    def check_portfolio_var(
        self,
        signal: TradingSignal,
        account: AccountInfo,
        positions: List[Position],
    ) -> tuple[bool, str]:
        """
        Pre-trade portfolio VaR check (3.1).

        Computes 1-day 95% historical simulation VaR for the portfolio including
        the proposed position. Rejects if VaR > max_var_pct of equity.

        Fail-open: returns (True, "skipped") when insufficient history.

        Returns:
            (passes, reason) — passes=True means signal is allowed.
        """
        try:
            import yaml as _yaml
            from pathlib import Path as _Path
            _cfg_path = _Path("config/autonomous_trading.yaml")
            if not _cfg_path.exists():
                return True, "config unavailable"
            with open(_cfg_path) as _f:
                _cfg = _yaml.safe_load(_f) or {}
            var_cfg = (_cfg.get("position_management") or {}).get("portfolio_var") or {}
            if not var_cfg.get("enabled", True):
                return True, "VaR check disabled"

            confidence = float(var_cfg.get("confidence", 0.95))
            max_var_pct = float(var_cfg.get("max_var_pct", 0.02))
            lookback_days = int(var_cfg.get("lookback_days", 252))
            min_history_days = int(var_cfg.get("min_history_days", 30))

            from src.models.database import get_database
            from src.models.orm import EquitySnapshotORM
            db = get_database()
            session = db.get_session()
            try:
                rows = (
                    session.query(EquitySnapshotORM.equity)
                    .filter(EquitySnapshotORM.snapshot_type == "daily")
                    .order_by(EquitySnapshotORM.date.desc())
                    .limit(lookback_days + 1)
                    .all()
                )
            finally:
                session.close()

            equities = [r.equity for r in rows if r.equity and r.equity > 0]
            if len(equities) < min_history_days:
                return True, f"insufficient history ({len(equities)} days < {min_history_days})"

            # Daily returns (oldest first)
            equities = list(reversed(equities))
            port_returns = [
                (equities[i] - equities[i - 1]) / equities[i - 1]
                for i in range(1, len(equities))
            ]

            # Estimate new position's contribution using symbol price history
            symbol_returns: list[float] = []
            try:
                from src.data.market_data_manager import get_market_data_manager
                from datetime import timedelta as _td
                _mdm = get_market_data_manager()
                _end = datetime.now()
                _start = _end - _td(days=lookback_days + 10)
                _bars = _mdm.get_historical_data(signal.symbol, _start, _end, interval="1d")
                if _bars and len(_bars) >= min_history_days:
                    closes = [getattr(b, 'close', None) for b in _bars if getattr(b, 'close', None)]
                    symbol_returns = [
                        (closes[i] - closes[i - 1]) / closes[i - 1]
                        for i in range(1, len(closes))
                    ]
            except Exception:
                pass

            portfolio_value = getattr(account, 'equity', None) or account.balance
            if portfolio_value <= 0:
                return True, "invalid equity"

            # Estimate position weight (use $2K minimum as proxy if size unknown)
            position_weight = 2000.0 / portfolio_value

            # Combine portfolio returns with new position contribution
            if symbol_returns:
                n = min(len(port_returns), len(symbol_returns))
                combined = [
                    port_returns[-n + i] + position_weight * symbol_returns[-n + i]
                    for i in range(n)
                ]
            else:
                combined = port_returns

            # Historical simulation VaR at confidence level
            combined_sorted = sorted(combined)
            var_idx = int((1.0 - confidence) * len(combined_sorted))
            var_idx = max(0, min(var_idx, len(combined_sorted) - 1))
            var_1d = abs(combined_sorted[var_idx])  # positive number = loss

            if var_1d > max_var_pct:
                return False, (
                    f"Portfolio VaR {var_1d:.2%} exceeds limit {max_var_pct:.2%} "
                    f"(1-day {confidence:.0%} historical simulation)"
                )

            logger.debug(
                f"VaR check passed for {signal.symbol}: "
                f"1-day {confidence:.0%} VaR = {var_1d:.2%} (limit {max_var_pct:.2%})"
            )
            return True, f"VaR {var_1d:.2%} within limit"

        except Exception as e:
            logger.debug(f"VaR check failed with exception — fail open: {e}")
            return True, f"VaR check error (fail open): {e}"

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
                    from src.data.market_data_manager import get_market_data_manager
                    from datetime import timedelta
                    mdm = get_market_data_manager()
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
                # Use the detailed rejection reason stashed by
                # calculate_position_size — otherwise we'd write a useless
                # "zero or negative" reason to signal_decisions and have to
                # grep risk.log to find the real cause. The sentinel is
                # reset at the top of every calculate_position_size call.
                _rej_reason = getattr(self, "_last_sizing_reason", "") or (
                    "Calculated position size is zero or negative"
                )
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason=_rej_reason,
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
                logger.info(
                    f"Post-adjustment size ${position_size:.2f} below eToro minimum "
                    f"${MINIMUM_ORDER_SIZE_POST:.0f} for {signal.symbol} — bumping to minimum"
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

            # Pre-trade portfolio VaR check (3.1)
            var_passes, var_reason = self.check_portfolio_var(signal, account, positions)
            if not var_passes:
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason=f"Portfolio VaR check failed: {var_reason}"
                )

            # Check exposure limits
            if not self.check_exposure_limits(position_size, account, positions):
                return ValidationResult(
                    is_valid=False,
                    position_size=0.0,
                    reason=f"Position would exceed max exposure limit of {self.config.max_exposure_pct:.1%}"
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
        Calculate position size using risk-based fixed-fractional sizing.

        Design (Rob Carver / fixed-fractional / AQR volatility targeting):

          position_size = (equity × risk_per_trade_pct) / stop_loss_pct

        Sizing by risk-dollars, not by capital allocation, means the function
        always produces a meaningful number. The strategy's allocation_pct
        controls how many concurrent positions it may hold (not a capital
        bucket that empties and blocks new trades).

        Calculation pipeline:
          1. Base risk per trade: 0.5% of equity (configurable)
          2. Confidence scalar: scales risk 0.25%→0.5% between floor and 1.0
          3. Volatility scalar: TARGET_VOL / realized_vol (Yang-Zhang / Parkinson / EWMA)
          4. Convert to position size: risk_dollars / stop_loss_pct
          5. Strategy concurrent-position cap (only legitimate early-zero)
          6. Symbol concentration cap (5% of equity)
          7. Sector soft cap (30% of equity → halve)
          8. Portfolio heat cap (total open risk-dollars ≤ 8% of equity)
          9. Drawdown sizing (50%/75% reduction at 5%/10% drawdown)
         10. Available balance cap — re-read live from DB (not stale account object)
         11. Minimum floor ($2,000) — applied last, after all caps

        Args:
            signal: Trading signal (may include price_history in metadata)
            account: Account information
            positions: Current open positions
            strategy_allocation_pct: Strategy's portfolio weight % (default 1.0%)

        Returns:
            Position size in dollars, or 0.0 only on a hard limit.
        """
        symbol = getattr(signal, 'symbol', '?')

        # Reset the rejection-reason sentinel at the start of every call so
        # stale reasons from a previous (0-returning) call don't bleed into
        # this one if this call succeeds and skips the explicit clear at
        # the bottom of the function.
        self._last_sizing_reason = ""

        # ── Account state ────────────────────────────────────────────────────
        # Re-read balance live from DB for every order — the account object passed
        # in was fetched once at the start of the signal cycle and is stale by the
        # time the 2nd, 3rd... Nth order is sized. With 93 orders in a batch and
        # only $4K cash, every order after the first would be sized against the
        # same stale balance and hit eToro error 604 (insufficient funds).
        # Each order is independent — it checks the real current balance right now.
        available_balance = account.balance  # fallback if DB read fails
        try:
            from src.models.database import get_database
            from src.models.orm import AccountInfoORM
            _db = get_database()
            _sess = _db.get_session()
            try:
                _acct_row = _sess.query(AccountInfoORM).order_by(
                    AccountInfoORM.updated_at.desc()
                ).first()
                if _acct_row and _acct_row.balance is not None:
                    available_balance = float(_acct_row.balance)
            finally:
                _sess.close()
        except Exception as _bal_err:
            logger.debug(f"Could not refresh balance from DB for {symbol}: {_bal_err} — using account object")

        equity = getattr(account, 'equity', None) or account.balance
        if equity <= 0:
            equity = account.balance

        MINIMUM_ORDER_SIZE = 5000.0
        if available_balance < MINIMUM_ORDER_SIZE:
            logger.warning(
                f"Insufficient balance for {symbol}: ${available_balance:.0f} available "
                f"(minimum order ${MINIMUM_ORDER_SIZE:.0f}) — skipping"
            )
            self._last_sizing_reason = (
                f"insufficient_balance (${available_balance:.0f} < "
                f"${MINIMUM_ORDER_SIZE:.0f} minimum)"
            )
            return 0.0

        # Track whether any risk-reducing penalty fired. When True, the
        # Step 11 minimum-floor bump is suppressed and we return 0 instead.
        # Bumping a penalty-reduced size back to $5K defeats the penalty.
        penalty_applied = False

        # ── Step 1: Base risk per trade ──────────────────────────────────────
        # 0.6% of equity = ~$2,800 at current $470K equity.
        # If this trade hits its stop loss, we lose ~$2,800 (0.6% of equity).
        # With a 6% SL: position_size = $470K × 0.6% / 6% = $4,700 raw.
        # After vol scaling (0.5x-1.5x) this produces $2,350-$7,050 positions.
        # With minimum floor of $5,000 this gives $5K-$10K positions — right for
        # a concentrated 40-60 position book deploying ~$400K of $470K equity.
        # (Was 0.2% — produced $1,567 raw → bumped to $2,000 minimum → avg $3,457.
        #  That's 130 positions × $3.5K = noise trading, not systematic alpha.)
        BASE_RISK_PCT = 0.006  # 0.6% of equity per trade

        # ── Step 2: Confidence scalar ────────────────────────────────────────
        # Scales risk linearly from 0.5× at confidence floor to 1.0× at max.
        # A 0.95 confidence signal risks the full 0.6%. A 0.60 signal risks ~0.53%.
        # Confidence floor raised from 0.30 to 0.50 — signals below 0.50 are noise.
        # The data shows 0.30-0.45 confidence signals have < 35% win rate and
        # negative expectancy. Only trade signals where the strategy is genuinely firing.
        CONFIDENCE_FLOOR = 0.50
        confidence = signal.confidence if signal.confidence and signal.confidence > 0 else 0.5
        if confidence < CONFIDENCE_FLOOR:
            logger.info(f"Signal confidence {confidence:.2f} below floor {CONFIDENCE_FLOOR} for {symbol} — skipping")
            self._last_sizing_reason = (
                f"confidence_below_floor ({confidence:.2f} < {CONFIDENCE_FLOOR})"
            )
            return 0.0
        confidence_scalar = 0.5 + 0.5 * (confidence - CONFIDENCE_FLOOR) / (1.0 - CONFIDENCE_FLOOR)
        risk_pct = BASE_RISK_PCT * confidence_scalar  # 0.30%–0.60%

        # ── Step 3: Volatility scalar ────────────────────────────────────────
        # Normalize risk contribution across asset classes.
        # TARGET_VOL / realized_vol: crypto (60% vol) → 0.27x, forex (8%) → 2.0x capped at 1.5x.
        TARGET_VOL = 0.16
        VOL_SCALE_MIN = 0.10
        VOL_SCALE_MAX = 1.50
        vol_scalar = 1.0

        if signal.metadata and 'price_history' in signal.metadata:
            asset_class = _get_asset_class_for_vol(symbol)
            realized_vol = estimate_realized_volatility(
                signal.metadata['price_history'], asset_class=asset_class
            )
            if realized_vol and realized_vol > 0:
                vol_scalar = max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, TARGET_VOL / realized_vol))
                if vol_scalar < 1.0:
                    penalty_applied = True
                logger.debug(
                    f"Vol-scaling {symbol}: realized={realized_vol:.1%}, "
                    f"target={TARGET_VOL:.0%}, scalar={vol_scalar:.2f}x ({asset_class})"
                )
        elif signal.metadata and 'volatility' in signal.metadata:
            v = signal.metadata['volatility']
            if v and v > 0:
                vol_scalar = max(VOL_SCALE_MIN, min(VOL_SCALE_MAX, TARGET_VOL / v))
                if vol_scalar < 1.0:
                    penalty_applied = True
                logger.debug(f"Vol-scaling (legacy) {symbol}: vol={v:.4f} → {vol_scalar:.2f}x")

        risk_pct *= vol_scalar

        # ── Step 4: Convert risk to position size ────────────────────────────
        # position_size = risk_dollars / stop_loss_pct
        # stop_loss_pct from strategy risk_params (6% stocks, 2% forex, 8% crypto).
        # Fallback to 6% if not available.
        stop_loss_pct = 0.06  # default: stock SL
        try:
            _sl = getattr(signal, 'metadata', {}) or {}
            _sl_val = _sl.get('stop_loss_pct') or _sl.get('stop_loss')
            if _sl_val and 0 < float(_sl_val) < 1.0:
                stop_loss_pct = float(_sl_val)
            else:
                # Infer from asset class if not in metadata
                _sym = getattr(signal, 'symbol', '') or ''
                _sym_up = _sym.upper()
                _forex_ccy = ["USD","EUR","GBP","JPY","AUD","NZD","CAD","CHF","SEK","NOK"]
                _is_forex = len(_sym_up) == 6 and _sym_up[:3] in _forex_ccy and _sym_up[3:] in _forex_ccy
                _is_crypto = any(c in _sym_up for c in ["BTC","ETH","XRP","ADA","DOGE","SOL"])
                if _is_forex:
                    stop_loss_pct = 0.02  # forex: 2% SL
                elif _is_crypto:
                    stop_loss_pct = 0.08  # crypto: 8% SL
        except Exception:
            pass

        risk_dollars = equity * risk_pct
        position_size = risk_dollars / stop_loss_pct

        logger.debug(
            f"{symbol}: equity=${equity:.0f}, risk_pct={risk_pct:.3%}, "
            f"risk_dollars=${risk_dollars:.0f}, sl={stop_loss_pct:.1%}, "
            f"raw_size=${position_size:.0f}"
        )

        # ── Step 5: Strategy concurrent-position cap ─────────────────────────
        # strategy_allocation_pct governs how many positions this strategy may
        # hold simultaneously, NOT a capital bucket.
        # 0.5% → 1 position, 1.0% → 2, 1.5% → 3, 2.0% → 4 (floor at 1).
        max_concurrent = max(1, round(strategy_allocation_pct / 0.5))
        strategy_open_count = sum(
            1 for pos in positions
            if pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
            and pos.strategy_id == signal.strategy_id
        )
        if strategy_open_count >= max_concurrent:
            logger.info(
                f"Strategy concurrent cap: {symbol} — {strategy_open_count}/{max_concurrent} "
                f"positions open (allocation={strategy_allocation_pct:.1f}%)"
            )
            self._last_sizing_reason = (
                f"strategy_concurrent_cap ({strategy_open_count}/{max_concurrent} "
                f"positions already open for this strategy)"
            )
            return 0.0

        # ── Step 6: Symbol concentration cap ────────────────────────────────
        # No single symbol > 5% of equity across all strategies.
        # Raised from 3% on 2026-05-02 after audit — 3% was too tight given
        # typical per-trade size ($5-10K) and the 50+ position book. At 5% of
        # ~$480K equity the cap is ~$24K per symbol, which lets a 2-3 position
        # conviction stack build on winners like NVDA without every new signal
        # being room-capped to near-zero.
        #
        # 2026-05-04: now also accounts for pending (unfilled) entry orders
        # on this symbol. Without this, two strategies signalling the same
        # watchlist symbol during market-closed hours each sized to the
        # full 5% budget (each saw filled_exposure=0) and combined to
        # breach the cap on market open. See `_get_pending_entry_exposure`.
        symbol_cap = equity * 0.05
        filled_symbol_exposure = sum(
            self._get_position_value(pos)
            for pos in positions
            if pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
            and pos.symbol == symbol
        )
        pending_symbol_exposure, _pending_strats, _pending_count = (
            self._get_pending_entry_exposure(symbol)
        )
        existing_symbol_exposure = filled_symbol_exposure + pending_symbol_exposure
        if existing_symbol_exposure >= symbol_cap:
            logger.info(
                f"Symbol cap exhausted: {symbol} "
                f"filled=${filled_symbol_exposure:.0f} + "
                f"pending=${pending_symbol_exposure:.0f} "
                f"({_pending_count} order(s)) = ${existing_symbol_exposure:.0f} "
                f">= cap=${symbol_cap:.0f}"
            )
            self._last_sizing_reason = (
                f"symbol_cap_exhausted ({symbol} at "
                f"${existing_symbol_exposure:.0f}/${symbol_cap:.0f}, "
                f"${pending_symbol_exposure:.0f} pending)"
            )
            return 0.0
        position_size = min(position_size, symbol_cap - existing_symbol_exposure)

        # ── Step 7: Sector soft cap ──────────────────────────────────────────
        # If sector already > 30% of equity, halve the position size.
        try:
            symbol_sector = get_symbol_sector(symbol)
            if symbol_sector and symbol_sector not in ('Unknown', 'Crypto', 'Forex', 'Index', 'Commodity'):
                sector_exposure = sum(
                    self._get_position_value(pos)
                    for pos in positions
                    if pos.closed_at is None
                    and not getattr(pos, 'pending_closure', False)
                    and get_symbol_sector(pos.symbol) == symbol_sector
                )
                if sector_exposure / equity > 0.30:
                    logger.info(
                        f"Sector soft cap: {symbol_sector} at {sector_exposure/equity:.1%} "
                        f"— halving size ${position_size:.0f} → ${position_size/2:.0f}"
                    )
                    position_size *= 0.5
        except Exception:
            pass

        # ── Step 8: Portfolio heat cap ───────────────────────────────────────
        # Portfolio heat = sum of (position_value × stop_loss_pct) for all open
        # positions. This is the total capital at risk if every stop fires.
        # Raised from 8% to 30% — with larger positions ($5-10K each) and a target
        # of 40-60 positions, the old 8% cap was blocking new trades constantly:
        # 125 positions × $3.5K × 6% SL = $26K heat vs $37K cap (8% of $470K).
        # At 30%: $141K max heat allows ~50 positions × $8K × 6% = $24K — well within.
        # This is still conservative: a 30% heat cap means worst-case drawdown if
        # every single stop fires simultaneously is 30% of equity.
        MAX_PORTFOLIO_HEAT_PCT = 0.30
        max_heat = equity * MAX_PORTFOLIO_HEAT_PCT
        current_heat = sum(
            self._get_position_value(pos) * 0.06  # assume 6% SL as proxy
            for pos in positions
            if pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
        )
        new_heat = position_size * stop_loss_pct
        if current_heat + new_heat > max_heat:
            heat_remaining = max(0.0, max_heat - current_heat)
            if heat_remaining < 1.0:
                logger.info(
                    f"Portfolio heat cap reached: current=${current_heat:.0f}, "
                    f"max=${max_heat:.0f} ({MAX_PORTFOLIO_HEAT_PCT:.0%} of equity)"
                )
                self._last_sizing_reason = (
                    f"portfolio_heat_cap_reached (current=${current_heat:.0f}, "
                    f"max=${max_heat:.0f})"
                )
                return 0.0
            # Scale down to fit within remaining heat budget
            position_size = min(position_size, heat_remaining / stop_loss_pct)
            logger.info(
                f"Portfolio heat cap: clamping {symbol} size to ${position_size:.0f} "
                f"(heat remaining=${heat_remaining:.0f})"
            )

        # ── Step 9: Drawdown-based sizing ────────────────────────────────────
        # Reduce position sizes when portfolio is in drawdown from 30d peak.
        # Also applies Market Quality Score sizing multiplier — in choppy/noisy
        # markets (low quality score), reduce all position sizes by up to 30%.
        try:
            from src.strategy.market_analyzer import MarketStatisticsAnalyzer
            from src.data.market_data_manager import get_market_data_manager
            _mdm_mqs = get_market_data_manager()
            if _mdm_mqs:
                _mqs_analyzer = MarketStatisticsAnalyzer(_mdm_mqs)
                _mqs = _mqs_analyzer.get_market_quality_score()
                _mqs_mult = _mqs.get("sizing_multiplier", 1.0)
                if _mqs_mult < 1.0:
                    position_size *= _mqs_mult
                    logger.info(
                        f"Market quality sizing: {symbol} size reduced to ${position_size:.0f} "
                        f"(quality={_mqs.get('score', 50):.0f}/100, grade={_mqs.get('grade', 'normal')}, "
                        f"multiplier={_mqs_mult:.2f}x)"
                    )
        except Exception as _mqs_err:
            logger.debug(f"Market quality sizing check failed: {_mqs_err}")

        try:
            import yaml as _yaml
            from pathlib import Path as _Path
            _cfg_path = _Path("config/autonomous_trading.yaml")
            if _cfg_path.exists():
                with open(_cfg_path) as _f:
                    _cfg = _yaml.safe_load(_f) or {}
                dd_cfg = (_cfg.get("position_management") or {}).get("drawdown_sizing") or {}
                if dd_cfg.get("enabled", True):
                    dd_lookback = int(dd_cfg.get("lookback_days", 30))
                    dd_thresh5 = float(dd_cfg.get("threshold_5pct", 0.50))
                    dd_thresh10 = float(dd_cfg.get("threshold_10pct", 0.25))
                    from src.models.database import get_database
                    from src.models.orm import EquitySnapshotORM
                    _db = get_database()
                    _sess = _db.get_session()
                    try:
                        _rows = (
                            _sess.query(EquitySnapshotORM.equity)
                            .filter(EquitySnapshotORM.snapshot_type == "daily")
                            .order_by(EquitySnapshotORM.date.desc())
                            .limit(dd_lookback)
                            .all()
                        )
                    finally:
                        _sess.close()
                    _equities = [r.equity for r in _rows if r.equity and r.equity > 0]
                    if len(_equities) >= 5:
                        _peak = max(_equities)
                        _drawdown = (_peak - equity) / _peak if _peak > 0 else 0.0
                        if _drawdown > 0.10:
                            position_size *= dd_thresh10
                            penalty_applied = True
                            logger.info(
                                f"Drawdown sizing: {_drawdown:.1%} from 30d peak "
                                f"— 75% reduction (×{dd_thresh10})"
                            )
                        elif _drawdown > 0.05:
                            position_size *= dd_thresh5
                            penalty_applied = True
                            logger.info(
                                f"Drawdown sizing: {_drawdown:.1%} from 30d peak "
                                f"— 50% reduction (×{dd_thresh5})"
                            )
        except Exception as _dd_err:
            logger.debug(f"Drawdown sizing check failed — skipping: {_dd_err}")

        # ── Step 10: Available balance cap ───────────────────────────────────
        position_size = min(position_size, available_balance)

        # ── Step 10b: Per-symbol+template loser penalty ─────────────────────
        # If this (template, symbol) pair has >=3 closed trades in trade_journal
        # with negative net P&L, halve the size. Prevents repeatedly sizing up
        # into a combo that has demonstrated it doesn't work. Resets naturally
        # once a winning trade flips net P&L positive (TSLA audit 2026-05-01).
        try:
            _tname = None
            if signal.metadata and isinstance(signal.metadata, dict):
                _tname = signal.metadata.get('template_name')
            if _tname and symbol:
                pair_stats = self._get_symbol_template_loser_stats(symbol, _tname)
                if pair_stats and pair_stats.get('trades', 0) >= 3 and pair_stats.get('pnl', 0) < 0:
                    old_size = position_size
                    position_size *= 0.5
                    penalty_applied = True
                    logger.info(
                        f"Loser penalty: {symbol} × {_tname} has "
                        f"{pair_stats['trades']} trades / ${pair_stats['pnl']:.0f} P&L "
                        f"→ size halved ${old_size:.0f} → ${position_size:.0f}"
                    )
        except Exception as _lp_err:
            logger.debug(f"Loser penalty check failed (non-fatal): {_lp_err}")

        # ── Step 10c: Conviction-tier size multiplier ────────────────────────
        # Signals with high conviction scores have demonstrated better P&L
        # outcomes (scorer audit 2026-05-04: ≥75 bucket +$51/trade vs
        # 65-70 bucket -$52/trade). Scale up size proportionally to conviction
        # quality, capped so the result never breaches symbol/heat caps above.
        #
        # Tiers (configurable via autonomous_trading.yaml
        # position_management.conviction_tier_sizing):
        #   score ≥ 80 → 1.30× (strong signal, proven positive EV)
        #   score ≥ 75 → 1.15× (above-average signal)
        #   score < 75 → 1.00× (baseline, no change)
        #
        # Conservative multipliers by design — sample is still thin (48 trades
        # in upper buckets over 14 days). Will be raised once 3-4 weeks of
        # clean data accumulates. Multiplier is applied AFTER all penalty/cap
        # steps so it never inflates a penalised position.
        try:
            _conv_score = None
            if signal.metadata and isinstance(signal.metadata, dict):
                _conv_score = signal.metadata.get('conviction_score')
            if _conv_score is None:
                # Fall back to signal.confidence as a proxy (0-1 scale → 0-100)
                _conv_score = (signal.confidence or 0) * 100 if signal.confidence and signal.confidence <= 1.0 else signal.confidence

            if _conv_score and _conv_score >= 75 and not penalty_applied:
                # Read tier config from yaml; fall back to conservative defaults.
                _tier_cfg = {}
                try:
                    import yaml as _yaml
                    from pathlib import Path as _Path
                    _cfg_path = _Path("config/autonomous_trading.yaml")
                    if _cfg_path.exists():
                        with open(_cfg_path) as _f:
                            _full_cfg = _yaml.safe_load(_f) or {}
                        _tier_cfg = (
                            (_full_cfg.get("position_management") or {})
                            .get("conviction_tier_sizing") or {}
                        )
                except Exception:
                    pass

                _mult_80 = float(_tier_cfg.get("multiplier_score_80", 1.30))
                _mult_75 = float(_tier_cfg.get("multiplier_score_75", 1.15))
                _enabled = _tier_cfg.get("enabled", True)

                if _enabled:
                    if _conv_score >= 80:
                        _tier_mult = _mult_80
                        _tier_label = f"≥80 ({_conv_score:.1f})"
                    else:
                        _tier_mult = _mult_75
                        _tier_label = f"75-80 ({_conv_score:.1f})"

                    old_size = position_size
                    position_size = min(
                        position_size * _tier_mult,
                        # Hard cap: never exceed symbol cap or available balance
                        # (both already enforced above, but re-apply after scaling)
                        symbol_cap - existing_symbol_exposure,
                        available_balance,
                    )
                    if position_size > old_size * 1.01:  # only log if actually scaled up
                        logger.info(
                            f"Conviction-tier sizing: {symbol} score={_tier_label} "
                            f"→ {_tier_mult:.2f}× ${old_size:.0f} → ${position_size:.0f}"
                        )
        except Exception as _ct_err:
            logger.debug(f"Conviction-tier sizing check failed (non-fatal): {_ct_err}")

        # ── Step 11: Minimum floor — applied last ────────────────────────────
        # If caps reduced the size below $5K but no penalty fired, bump to minimum.
        # If ANY risk-reducing penalty (drawdown sizing, vol scale <1.0, loser
        # penalty) fired, DO NOT bump — bumping would defeat the penalty. Return
        # 0 instead so the trade is skipped.
        if position_size <= 0:
            # Earlier caps brought size to 0 without explicit early return
            # (shouldn't happen in practice but defensive). Reason was
            # already set by the cap that trimmed it, or fallback below.
            if not self._last_sizing_reason:
                self._last_sizing_reason = "size_collapsed_after_all_caps"
            return 0.0
        if position_size < MINIMUM_ORDER_SIZE:
            if penalty_applied:
                logger.info(
                    f"Size ${position_size:.0f} below minimum ${MINIMUM_ORDER_SIZE:.0f} "
                    f"for {symbol} AND penalty applied — skipping trade "
                    f"(penalty mechanisms would be defeated by floor bump)"
                )
                self._last_sizing_reason = (
                    f"below_min_with_penalty (size=${position_size:.0f} < "
                    f"${MINIMUM_ORDER_SIZE:.0f}, penalty_applied=True)"
                )
                return 0.0
            if available_balance >= MINIMUM_ORDER_SIZE:
                logger.info(
                    f"Size ${position_size:.0f} below minimum ${MINIMUM_ORDER_SIZE:.0f} "
                    f"for {symbol} — bumping to minimum"
                )
                position_size = MINIMUM_ORDER_SIZE
            else:
                logger.warning(
                    f"Size ${position_size:.0f} below minimum and insufficient balance "
                    f"(${available_balance:.0f}) for {symbol}"
                )
                self._last_sizing_reason = (
                    f"insufficient_balance_for_min (size=${position_size:.0f}, "
                    f"available=${available_balance:.0f}, min=${MINIMUM_ORDER_SIZE:.0f})"
                )
                return 0.0

        # Successful sizing — clear the reason so a subsequent call doesn't
        # inherit the last-call's rejection reason by mistake.
        self._last_sizing_reason = ""
        logger.info(
            f"Position size: {symbol} ${position_size:.0f} "
            f"(equity=${equity:.0f}, risk={risk_pct:.3%}, sl={stop_loss_pct:.1%}, "
            f"conf={confidence:.2f}, vol_scalar={vol_scalar:.2f}x, "
            f"strategy_positions={strategy_open_count}/{max_concurrent})"
        )
        return position_size

    # Cached per-cycle loser-stats lookup (reset on TTL expiry).
    _loser_cache: Dict[Tuple[str, str], Tuple[float, Dict]] = {}
    _loser_cache_ttl_seconds: float = 120.0

    def _get_symbol_template_loser_stats(self, symbol: str, template_name: str) -> Optional[Dict]:
        """Return {'trades': n, 'pnl': sum_pnl} for the (symbol, template) pair
        from trade_journal closed trades. Returns None on any error.

        Cached in-process 2 min to avoid repeated DB hits during a signal burst.
        """
        import time as _t
        key = (symbol.upper(), template_name)
        now = _t.time()
        cache = type(self)._loser_cache
        hit = cache.get(key)
        if hit and (now - hit[0] < type(self)._loser_cache_ttl_seconds):
            return hit[1]

        try:
            from src.models.database import get_database
            from src.analytics.trade_journal import TradeJournalEntryORM
            from sqlalchemy import func as _sa_func

            db = get_database()
            session = db.get_session()
            try:
                # trade_metadata->'template_name' in the original log path.
                # Also fall back to template_name stored on the strategies row via join is
                # expensive; here we match on symbol only and filter template in Python.
                rows = (
                    session.query(TradeJournalEntryORM.pnl, TradeJournalEntryORM.trade_metadata)
                    .filter(
                        TradeJournalEntryORM.symbol == symbol.upper(),
                        TradeJournalEntryORM.pnl.isnot(None),
                    )
                    .all()
                )
            finally:
                session.close()

            pnl_sum = 0.0
            n = 0
            for pnl_val, meta in rows:
                if pnl_val is None:
                    continue
                tname = None
                if isinstance(meta, dict):
                    tname = meta.get('template_name') or meta.get('template')
                # If no template stored on the trade, don't match — be conservative
                if tname and str(tname).strip().lower() == template_name.strip().lower():
                    pnl_sum += float(pnl_val)
                    n += 1

            result = {'trades': n, 'pnl': pnl_sum}
            cache[key] = (now, result)
            return result
        except Exception:
            return None


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
        #
        # 2026-05-04: extended to include pending (unfilled) entry orders.
        # See `_get_pending_entry_exposure` for rationale. Without this,
        # two strategies firing on the same symbol during market-closed
        # hours each passed this check (filled-only exposure = 0) and
        # combined to breach the cap on fill.
        existing_symbol_exposure = 0.0
        strategies_holding_symbol = set()

        for pos in positions:
            if pos.symbol == symbol and pos.closed_at is None and not getattr(pos, 'pending_closure', False):
                existing_symbol_exposure += self._get_position_value(pos)
                strategies_holding_symbol.add(pos.strategy_id)

        # Pending entry orders (PENDING / PARTIALLY_FILLED, order_action='entry'
        # or NULL). Contribute to exposure, strategy-count, and position-count
        # budgets so the cap check sees the same world the next cycle will see.
        pending_exposure, pending_strategies, pending_count = (
            self._get_pending_entry_exposure(symbol)
        )
        existing_symbol_exposure += pending_exposure
        strategies_holding_symbol |= pending_strategies

        # Check 1: Symbol exposure limit (based on equity)
        total_symbol_exposure = existing_symbol_exposure + position_size
        portfolio_value = getattr(account, 'equity', None) or account.balance
        max_symbol_exposure = portfolio_value * self.config.max_symbol_exposure_pct

        if total_symbol_exposure > max_symbol_exposure:
            logger.warning(
                f"Symbol concentration limit exceeded for {symbol}: "
                f"total={total_symbol_exposure:.2f} > max={max_symbol_exposure:.2f} "
                f"({self.config.max_symbol_exposure_pct:.1%} of portfolio) "
                f"[filled+positions=${existing_symbol_exposure - pending_exposure:.0f}, "
                f"pending=${pending_exposure:.0f} ({pending_count} order(s)), "
                f"new=${position_size:.0f}]"
            )
            return False, (
                f"Symbol concentration limit: {symbol} exposure would be "
                f"${total_symbol_exposure:.2f} (max ${max_symbol_exposure:.2f}, "
                f"{self.config.max_symbol_exposure_pct:.1%} of portfolio; "
                f"includes ${pending_exposure:.0f} from {pending_count} pending order(s))"
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
        # Includes pending entry orders — each will become a position once filled.
        position_count_for_symbol = sum(
            1 for pos in positions
            if pos.symbol == symbol and pos.closed_at is None
            and not getattr(pos, 'pending_closure', False)
        )
        position_count_for_symbol += pending_count
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
