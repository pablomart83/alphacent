"""Position management system for advanced position handling.

This module provides position management capabilities including:
- Trailing stop-loss logic
- Partial exit strategies
- Position monitoring and adjustments

Note on eToro: `etoro_client.update_position_stop_loss` is a no-op stub because
eToro's public API does not expose an SL-modification endpoint for open
positions. Trailing stops are enforced DB-side — this module updates
`Position.stop_loss`, the monitoring service persists the new value to DB, and
a separate breach-detection pass closes positions whose current price crosses
the stored stop. Any `except EToroAPIError` in this module is dead code kept
only for defensive signalling if the stub is ever replaced with a live call.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.models.dataclasses import Position, Order, RiskConfig
from src.models.enums import OrderSide, OrderType, OrderStatus

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages advanced position handling including trailing stops."""

    def __init__(self, etoro_client: EToroAPIClient, risk_config: Optional[RiskConfig] = None):
        """Initialize position manager.
        
        Args:
            etoro_client: eToro API client for position updates
            risk_config: Risk configuration with trailing stop settings
        """
        self.etoro_client = etoro_client
        self.risk_config = risk_config or RiskConfig()
        # Populated on every check_trailing_stops call. Consumers (monitoring_service)
        # read this to emit a per-cycle INFO summary. See check_trailing_stops docstring.
        self._last_tsl_summary: Dict = {
            "checked": 0, "breakeven": 0, "lock": 0, "trail": 0,
            "errors": 0, "invalid_entry": 0, "updated_ids": set(),
        }
        logger.info("PositionManager initialized")

    # Asset-class-aware trailing stop thresholds.
    # Activation = minimum profit before trailing stop kicks in.
    # Distance = how far below current price (longs) or above (shorts) the stop sits.
    # The distance must be outside normal daily noise for that asset class.
    #
    # Calibration logic (ATR-aware):
    # - Stocks: ~1-2% daily ATR → activate at 5%, trail at 7% (3.5-7x daily noise)
    # - ETFs: similar to stocks but slightly tighter (diversified, less volatile)
    # - Crypto: ~3-5% daily ATR → activate at 8%, trail at 10% (2-3x daily noise)
    # - Forex: ~0.5-1% daily ATR → activate at 2%, trail at 3% (3-6x daily noise)
    # - Commodities: ~1.5-3% daily ATR → activate at 5%, trail at 7% (2-4x daily noise)
    # - Indices: ~1% daily ATR → activate at 4%, trail at 5% (4-5x daily noise)
    #
    # IMPORTANT: These are percentage-based FLOORS. The actual trail distance is
    # max(distance_pct * price, ATR_MULTIPLIER * daily_ATR) to prevent penny-stop
    # whipsaws on high-priced instruments. See check_trailing_stops() for ATR logic.
    TRAILING_STOP_PARAMS = {
        "stock":     {"activation": 0.05, "distance": 0.07},
        "etf":       {"activation": 0.04, "distance": 0.05},
        "crypto":    {"activation": 0.08, "distance": 0.10},
        "forex":     {"activation": 0.02, "distance": 0.03},
        "commodity": {"activation": 0.05, "distance": 0.07},
        "index":     {"activation": 0.04, "distance": 0.05},
    }

    # Breakeven stop thresholds — move SL to entry price when profit reaches this level.
    # This is a one-time ratchet that fires BEFORE the trailing stop activation.
    # Once SL >= entry price, the position cannot lose money (excluding spread/slippage).
    # Set lower than trailing stop activation so there's always a profit-protection
    # window between breakeven and the trailing stop taking over.
    #
    # Rationale: a position that reaches +3% and then reverses to -6% is a loss that
    # could have been avoided. Moving SL to breakeven at +3% costs nothing and
    # eliminates the "gave back a winner" scenario entirely.
    BREAKEVEN_STOP_PARAMS = {
        "stock":     0.03,   # Move SL to entry at +3% profit
        "etf":       0.025,  # ETFs are less volatile — tighter breakeven
        "crypto":    0.05,   # Crypto needs more room before locking in breakeven
        "forex":     0.015,  # Forex: tight, 1.5% is meaningful
        "commodity": 0.03,
        "index":     0.025,
    }

    # Profit lock-in thresholds — move SL to entry + lock_pct when profit reaches this level.
    # Fires between breakeven stop and trailing stop activation.
    # Ensures a position that moves +5% and reverses still closes with a profit.
    #
    # Without this, the gap between breakeven (+3%) and trailing stop activation (+7.5%)
    # means a position can go +6% then reverse to 0% and close at breakeven — you made
    # nothing on a 6% move. The profit lock closes that gap.
    #
    # Three-stage ladder (stocks):
    #   +3%  → SL to entry (breakeven)
    #   +5%  → SL to entry + 2% (lock in 2% profit)
    #   +7.5%+ → trailing stop takes over, follows price at 7% distance
    PROFIT_LOCK_PARAMS = {
        "stock":     {"trigger": 0.05, "lock": 0.02},   # At +5%, lock in +2%
        "etf":       {"trigger": 0.04, "lock": 0.015},  # At +4%, lock in +1.5%
        "crypto":    {"trigger": 0.08, "lock": 0.03},   # At +8%, lock in +3%
        "forex":     {"trigger": 0.025,"lock": 0.01},   # At +2.5%, lock in +1%
        "commodity": {"trigger": 0.05, "lock": 0.02},
        "index":     {"trigger": 0.04, "lock": 0.015},
    }

    # ATR multiplier for minimum trail distance, per asset class.
    # Trail distance = max(distance_pct * price, ATR_MULTIPLIER * ATR_pct)
    # This prevents penny-stop whipsaws on high-priced instruments where a fixed
    # percentage produces a stop within normal intraday noise.
    #
    # Per-class tuning rationale:
    # - Stocks/commodities: 2.0x — high intraday noise, wide stop protects from whipsaw.
    # - ETFs: 2.0x — diversified but still subject to sector-driven intraday moves.
    # - Crypto: 1.5x — ATR is already ~5%, 2x produces 10%+ stops that erode edge.
    # - Forex: 1.0x — ATR is tight (~0.5-1%), 2x would produce 1-2% stops eating into
    #   the 2-3% fixed distance; 1x means ATR only lifts above the fixed 3% in
    #   high-vol regimes (CPI days etc.), which is what we want.
    # - Indices: 1.5x — ~1% ATR, 1.5x keeps trails near the 5% fixed distance.
    ATR_MULTIPLIER_BY_ASSET_CLASS = {
        "stock":     2.0,
        "etf":       2.0,
        "crypto":    1.5,
        "forex":     1.0,
        "commodity": 2.0,
        "index":     1.5,
    }
    # Legacy single-value multiplier kept for any external callers that read it.
    ATR_TRAIL_MULTIPLIER = 2.0

    def _get_asset_class(self, symbol: str) -> str:
        """Classify symbol for trailing stop parameter selection."""
        sym = symbol.upper() if symbol else ""
        try:
            from src.core.tradeable_instruments import (
                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
                DEMO_ALLOWED_ETFS,
            )
            if sym in set(DEMO_ALLOWED_CRYPTO):
                return "crypto"
            if sym in set(DEMO_ALLOWED_FOREX):
                return "forex"
            if sym in set(DEMO_ALLOWED_COMMODITIES):
                return "commodity"
            if sym in set(DEMO_ALLOWED_INDICES):
                return "index"
            if sym in set(DEMO_ALLOWED_ETFS):
                return "etf"
        except ImportError:
            pass
        return "stock"

    def check_trailing_stops(
        self,
        positions: List[Position],
        skip_etoro_update: bool = False,
        position_intervals: Optional[Dict[str, str]] = None,
    ) -> List[Order]:
        """Check positions for trailing stop-loss adjustments.

        Three-stage profit-protection ladder (stocks as example):

        1. Breakeven stop: when profit ≥ BREAKEVEN_STOP_PARAMS[class], move SL to
           entry. One-time ratchet — position can no longer lose money.
        2. Profit lock:    when profit ≥ PROFIT_LOCK_PARAMS[class]["trigger"], move
           SL to entry × (1 ± lock_pct). Closes the gap between breakeven and
           trailing activation.
        3. Trailing stop:  when profit ≥ TRAILING_STOP_PARAMS[class]["activation"],
           compute trail_sl = current × (1 ± effective_distance). Only updates if
           the new stop is a favourable move (ratchet).

        effective_distance = max(distance_pct, ATR_pct × ATR_MULTIPLIER[class]).
        ATR is computed from the strategy's own timeframe bars when available
        (via `position_intervals`) so 4H strategies don't inherit daily ATR.

        Note: eToro has no SL-modification API for open positions; the
        `etoro_client.update_position_stop_loss` call is a no-op stub that
        returns {"status": "db_only"}. Trailing stops are enforced DB-side:
        this method mutates `position.stop_loss`; the caller persists; a
        separate breach-detection pass closes positions that cross the stop.

        Args:
            positions: List of open positions to check.
            skip_etoro_update: Kept for API compatibility. eToro SL-modify is not
                supported, so the flag is effectively a no-op — the "eToro path"
                and "DB-only path" produce the same result.
            position_intervals: Optional mapping of position.id → strategy interval
                ('1d', '4h', '1h'). If omitted, ATR uses 1d bars (legacy behaviour).

        Returns:
            List of orders created (always empty for trailing stops; kept for
            signature compatibility with other check_* methods).

        Side effects:
            Sets `self._last_tsl_summary` to a dict with per-action counts so the
            caller can emit an INFO-level per-cycle summary line.
        """
        # Reset summary for this cycle
        self._last_tsl_summary = {
            "checked": len(positions),
            "breakeven": 0,
            "lock": 0,
            "trail": 0,
            "errors": 0,
            "invalid_entry": 0,
            "updated_ids": set(),
        }

        if not self.risk_config.trailing_stop_enabled:
            logger.debug("Trailing stop-loss is disabled")
            return []

        logger.info(f"Checking {len(positions)} positions for trailing stop adjustments")

        orders_created: List[Order] = []

        for position in positions:
            try:
                if position.closed_at is not None:
                    continue

                if position.entry_price is None or position.entry_price <= 0:
                    logger.warning(
                        f"Position {position.id} ({position.symbol}) has invalid "
                        f"entry_price: {position.entry_price}"
                    )
                    self._last_tsl_summary["invalid_entry"] += 1
                    continue

                if position.current_price is None or position.current_price <= 0:
                    logger.debug(
                        f"Position {position.id} ({position.symbol}) has no "
                        f"current_price; skipping TSL"
                    )
                    continue

                # Profit calculation (fraction, not percent)
                if position.side.value == "LONG":
                    profit_pct = (position.current_price - position.entry_price) / position.entry_price
                else:
                    profit_pct = (position.entry_price - position.current_price) / position.entry_price

                asset_class = self._get_asset_class(position.symbol)
                trail_params = self.TRAILING_STOP_PARAMS.get(asset_class, self.TRAILING_STOP_PARAMS["stock"])
                activation_pct = trail_params["activation"]
                distance_pct = trail_params["distance"]

                is_long = position.side.value == "LONG"

                # ── Stage 1: Breakeven stop ──────────────────────────────────
                breakeven_threshold = self.BREAKEVEN_STOP_PARAMS.get(asset_class, 0.03)
                if profit_pct >= breakeven_threshold:
                    be_sl = position.entry_price
                    if self._is_favourable_move(position.stop_loss, be_sl, is_long):
                        self._apply_sl(
                            position,
                            be_sl,
                            f"Breakeven stop set: {position.symbol} {position.side.value} "
                            f"profit={profit_pct:.1%} → SL moved to entry {be_sl:.4f}",
                        )
                        self._last_tsl_summary["breakeven"] += 1

                # ── Stage 2: Profit lock ─────────────────────────────────────
                lock_params = self.PROFIT_LOCK_PARAMS.get(asset_class, self.PROFIT_LOCK_PARAMS["stock"])
                lock_trigger = lock_params["trigger"]
                lock_pct = lock_params["lock"]
                if profit_pct >= lock_trigger:
                    lock_sl = position.entry_price * (1 + lock_pct) if is_long else position.entry_price * (1 - lock_pct)
                    if self._is_favourable_move(position.stop_loss, lock_sl, is_long):
                        self._apply_sl(
                            position,
                            lock_sl,
                            f"Profit lock: {position.symbol} {position.side.value} "
                            f"profit={profit_pct:.1%} → SL locked at ±{lock_pct:.1%} ({lock_sl:.4f})",
                        )
                        self._last_tsl_summary["lock"] += 1

                # ── Stage 3: Trailing stop ───────────────────────────────────
                if profit_pct < activation_pct:
                    continue  # Not yet in trail zone

                # ATR-aware effective distance, timeframe-aware when we know the strategy interval
                strategy_interval = (position_intervals or {}).get(position.id, "1d")
                effective_distance = self._compute_effective_trail_distance(
                    symbol=position.symbol,
                    current_price=position.current_price,
                    asset_class=asset_class,
                    fixed_distance_pct=distance_pct,
                    interval=strategy_interval,
                )

                trail_sl = position.current_price * (1 - effective_distance) if is_long else position.current_price * (1 + effective_distance)

                if self._is_favourable_move(position.stop_loss, trail_sl, is_long):
                    old_sl_str = f"{position.stop_loss:.4f}" if position.stop_loss else "None"
                    self._apply_sl(
                        position,
                        trail_sl,
                        f"Trailing stop: {position.symbol} {position.side.value} "
                        f"{old_sl_str} → {trail_sl:.4f} "
                        f"(profit={profit_pct:.2%}, {asset_class}/{strategy_interval}: {effective_distance:.2%} distance)",
                    )
                    self._last_tsl_summary["trail"] += 1

            except Exception as e:
                logger.error(
                    f"Error processing position {position.id} ({position.symbol}): {e}"
                )
                self._last_tsl_summary["errors"] += 1
                continue

        updated_n = len(self._last_tsl_summary["updated_ids"])
        if updated_n > 0:
            logger.info(f"Updated trailing stops for {updated_n} positions")
        else:
            logger.debug("No trailing stop adjustments needed")

        return orders_created

    # ── Helpers for check_trailing_stops ─────────────────────────────────────

    @staticmethod
    def _is_favourable_move(current_sl: Optional[float], new_sl: float, is_long: bool) -> bool:
        """A SL move is favourable (ratchet) only in the direction that locks in more profit.
        Longs: new_sl > current_sl. Shorts: new_sl < current_sl. None always favourable."""
        if current_sl is None:
            return True
        if is_long:
            return new_sl > current_sl
        return new_sl < current_sl

    def _apply_sl(self, position: Position, new_sl: float, log_message: str) -> None:
        """Mutate Position.stop_loss, mark id as updated in the cycle summary, log.

        eToro's public API does not support SL modification on open positions.
        `etoro_client.update_position_stop_loss` is a no-op stub — we call it for
        future-proofing but do not rely on it to persist anything. The caller
        (monitoring_service) commits the new DB value.
        """
        try:
            # Stub call — returns {"status": "db_only"}. Kept for symmetry.
            if position.etoro_position_id:
                self.etoro_client.update_position_stop_loss(
                    position_id=position.etoro_position_id,
                    stop_loss_rate=new_sl,
                )
        except EToroAPIError as e:
            # Unreachable with the current stub, but preserved in case a live
            # SL-modify endpoint is wired in later. We still apply the DB-side
            # value because that's the enforcement mechanism.
            logger.warning(f"eToro SL-modify returned error for {position.symbol}: {e}")

        position.stop_loss = new_sl
        self._last_tsl_summary["updated_ids"].add(position.id)
        logger.info(log_message)

    def _compute_effective_trail_distance(
        self,
        symbol: str,
        current_price: float,
        asset_class: str,
        fixed_distance_pct: float,
        interval: str = "1d",
    ) -> float:
        """Compute the trail distance as max(fixed_pct, ATR_pct × ATR_MULTIPLIER[class]).

        Uses bars at the strategy's own interval so a 4H trail isn't forced to
        use daily ATR (and vice versa). Falls back to the fixed percentage if
        bars are unavailable or too few.
        """
        effective = fixed_distance_pct

        try:
            from src.data.market_data_manager import get_market_data_manager
            from datetime import timedelta

            mdm = get_market_data_manager()
            # Window sized for the interval so we always have enough bars for ATR(14)
            if interval == "1h":
                lookback_days = 3  # ~24 bars
            elif interval == "4h":
                lookback_days = 10  # ~45 bars (6 bars/day × 10)
            else:
                lookback_days = 20  # 20 daily bars
            end = datetime.now(timezone.utc).replace(tzinfo=None)
            start = end - timedelta(days=lookback_days)

            bars = mdm.get_historical_data(symbol, start, end, interval=interval)

            if not bars or len(bars) < 5:
                # Not enough bars on this interval; fall back to 1d if we asked for something else
                if interval != "1d":
                    start = end - timedelta(days=20)
                    bars = mdm.get_historical_data(symbol, start, end, interval="1d")
                    interval = "1d"

            if bars and len(bars) >= 5:
                tr_list = []
                for i in range(1, len(bars)):
                    h = getattr(bars[i], "high", None) or current_price
                    l = getattr(bars[i], "low", None) or current_price
                    c_prev = getattr(bars[i - 1], "close", None) or current_price
                    tr_list.append(max(h - l, abs(h - c_prev), abs(l - c_prev)))

                if tr_list:
                    window = tr_list[-14:]
                    atr = sum(window) / len(window)
                    atr_pct = atr / current_price if current_price > 0 else 0.0
                    multiplier = self.ATR_MULTIPLIER_BY_ASSET_CLASS.get(asset_class, self.ATR_TRAIL_MULTIPLIER)
                    atr_floor = atr_pct * multiplier

                    if atr_floor > effective:
                        # Log only when the floor meaningfully widens the trail
                        # (avoids noise for tiny upward adjustments)
                        if atr_floor >= effective * 1.2 or (atr_floor - effective) >= 0.01:
                            logger.info(
                                f"ATR trail floor for {symbol} ({interval}): "
                                f"{effective:.2%} → {atr_floor:.2%} "
                                f"(ATR%={atr_pct:.2%}, multiplier={multiplier:.1f}x, class={asset_class})"
                            )
                        effective = atr_floor
        except Exception as e:
            logger.debug(f"Could not compute ATR trail floor for {symbol} ({interval}): {e}")

        return effective

    def check_partial_exits(self, positions: List[Position]) -> List[Order]:
        """Check positions for partial exit opportunities.
        
        For each position that hits a profit level:
        - Calculate exit quantity (position_size * exit_pct)
        - Create SELL order for partial quantity
        - Mark position as "partially exited" to avoid re-triggering
        - Log partial exit
        
        Args:
            positions: List of open positions to check
            
        Returns:
            List of orders created for partial exits
        """
        if not self.risk_config.partial_exit_enabled:
            logger.debug("Partial exits are disabled")
            return []
        
        if not self.risk_config.partial_exit_levels:
            logger.warning("Partial exits enabled but no levels configured")
            return []
        
        logger.info(f"Checking {len(positions)} positions for partial exit opportunities")
        
        orders_created = []
        
        for position in positions:
            try:
                # Skip closed positions
                if position.closed_at is not None:
                    continue
                
                # Calculate profit percentage
                if position.entry_price <= 0:
                    logger.warning(f"Position {position.id} has invalid entry_price: {position.entry_price}")
                    continue
                
                # For long positions: profit when price goes up
                # For short positions: profit when price goes down
                if position.side.value == "LONG":
                    profit_pct = (position.current_price - position.entry_price) / position.entry_price
                else:  # SHORT
                    profit_pct = (position.entry_price - position.current_price) / position.entry_price
                
                # Store original quantity for calculating all exits
                original_quantity = position.quantity
                total_exit_quantity = 0.0
                
                # Check each profit level
                for level in self.risk_config.partial_exit_levels:
                    profit_threshold = level.get("profit_pct", 0.0)
                    exit_pct = level.get("exit_pct", 0.0)
                    
                    # Validate level configuration
                    if profit_threshold <= 0 or exit_pct <= 0 or exit_pct > 1.0:
                        logger.warning(f"Invalid partial exit level: {level}")
                        continue
                    
                    # Check if profit threshold is met
                    if profit_pct < profit_threshold:
                        continue
                    
                    # Check if this level has already been triggered
                    level_key = f"{profit_threshold:.4f}"
                    already_triggered = any(
                        exit.get("profit_level") == level_key
                        for exit in position.partial_exits
                    )
                    
                    if already_triggered:
                        logger.debug(
                            f"Position {position.id} ({position.symbol}) already triggered "
                            f"partial exit at {profit_threshold:.1%} level"
                        )
                        continue
                    
                    # Calculate exit quantity based on ORIGINAL position size
                    exit_quantity = original_quantity * exit_pct
                    
                    if exit_quantity <= 0:
                        logger.warning(
                            f"Invalid exit quantity {exit_quantity} for position {position.id}"
                        )
                        continue
                    
                    # Create partial exit order
                    order_id = f"partial_exit_{position.id}_{uuid4().hex[:8]}"
                    
                    # Determine order side (opposite of position side)
                    order_side = OrderSide.SELL if position.side.value == "LONG" else OrderSide.BUY
                    
                    order = Order(
                        id=order_id,
                        strategy_id=position.strategy_id,
                        symbol=position.symbol,
                        side=order_side,
                        order_type=OrderType.MARKET,
                        quantity=exit_quantity,
                        status=OrderStatus.PENDING,
                        price=position.current_price,
                        submitted_at=datetime.now()
                    )
                    
                    orders_created.append(order)
                    
                    # Record partial exit in position history
                    partial_exit_record = {
                        "profit_level": level_key,
                        "profit_pct": profit_pct,
                        "exit_pct": exit_pct,
                        "exit_quantity": exit_quantity,
                        "exit_price": position.current_price,
                        "timestamp": datetime.now().isoformat(),
                        "order_id": order_id
                    }
                    
                    position.partial_exits.append(partial_exit_record)
                    
                    # Track total exit quantity
                    total_exit_quantity += exit_quantity
                    
                    logger.info(
                        f"Created partial exit order for position {position.id} ({position.symbol}): "
                        f"profit={profit_pct:.2%}, exit_qty={exit_quantity:.4f} ({exit_pct:.1%}), "
                        f"price={position.current_price:.2f}"
                    )
                
                # Update position quantity once after all exits are calculated
                if total_exit_quantity > 0:
                    position.quantity -= total_exit_quantity
                    
            except Exception as e:
                logger.error(f"Error processing position {position.id} for partial exits: {e}")
                continue
        
        if orders_created:
            logger.info(f"Created {len(orders_created)} partial exit orders")
        else:
            logger.debug("No partial exit opportunities found")
        
        return orders_created
