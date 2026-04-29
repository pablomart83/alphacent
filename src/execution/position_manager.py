"""Position management system for advanced position handling.

This module provides position management capabilities including:
- Trailing stop-loss logic
- Partial exit strategies
- Position monitoring and adjustments
"""

import logging
from datetime import datetime
from typing import List, Optional
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

    # ATR multiplier for minimum trail distance.
    # Trail distance = max(distance_pct * price, ATR_TRAIL_MULTIPLIER * daily_ATR)
    # This prevents penny-stop whipsaws on high-priced instruments where a fixed
    # percentage produces a stop that's within normal intraday noise.
    ATR_TRAIL_MULTIPLIER = 2.0  # Raised from 1.5 — 1.5x was within normal intraday noise for ranging markets

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

    def check_trailing_stops(self, positions: List[Position], skip_etoro_update: bool = False) -> List[Order]:
        """Check positions for trailing stop-loss adjustments.

        Two-stage profit protection:

        Stage 1 — Breakeven stop (fires first, lower threshold):
          When profit reaches BREAKEVEN_STOP_PARAMS threshold (3% stocks, 2% forex,
          5% crypto), move SL to entry price. One-time ratchet — position can no
          longer lose money. Eliminates the "gave back a winner" scenario.

        Stage 2 — Trailing stop (fires after breakeven, higher threshold):
          Uses asset-class-aware activation thresholds and trailing distances:
          - Stocks/ETFs: 5% activation, 7% distance
          - Crypto: 8% activation, 10% distance
          - Forex: 2% activation, 3% distance
          - Commodities/Indices: 4-5% activation, 5-7% distance

        The config-level trailing_stop_activation_pct and trailing_stop_distance_pct
        serve as overrides — if set, they take precedence over asset-class defaults.

        Args:
            positions: List of open positions to check
            skip_etoro_update: If True, only update Position objects without calling eToro API.

        Returns:
            List of orders created (empty for trailing stops)
        """
        if not self.risk_config.trailing_stop_enabled:
            logger.debug("Trailing stop-loss is disabled")
            return []

        logger.info(f"Checking {len(positions)} positions for trailing stop adjustments")

        orders_created = []
        positions_updated = 0

        for position in positions:
            try:
                if position.closed_at is not None:
                    continue

                if position.entry_price <= 0:
                    logger.warning(f"Position {position.id} has invalid entry_price: {position.entry_price}")
                    continue

                # Profit calculation
                if position.side.value == "LONG":
                    profit_pct = (position.current_price - position.entry_price) / position.entry_price
                else:
                    profit_pct = (position.entry_price - position.current_price) / position.entry_price

                # Asset-class-aware thresholds
                asset_class = self._get_asset_class(position.symbol)
                params = self.TRAILING_STOP_PARAMS.get(asset_class, self.TRAILING_STOP_PARAMS["stock"])
                activation_pct = params["activation"]
                distance_pct = params["distance"]

                # ── BREAKEVEN STOP ────────────────────────────────────────────────
                # When profit reaches the breakeven threshold, move SL to entry price.
                # This is a one-time ratchet — fires once, then becomes a no-op.
                # Runs BEFORE the trailing stop check so there's always a protection
                # window between breakeven and the trailing stop taking over.
                #
                # Example (stock): position reaches +3% → SL moves to entry price.
                # If price then reverses, the position closes at breakeven (no loss).
                # The trailing stop then takes over at +5% and follows price upward.
                breakeven_threshold = self.BREAKEVEN_STOP_PARAMS.get(asset_class, 0.03)
                if profit_pct >= breakeven_threshold and position.entry_price > 0:
                    # Only apply if SL is currently below entry (still in loss territory)
                    if position.side.value == "LONG":
                        be_sl = position.entry_price  # Breakeven = entry price for longs
                        if position.stop_loss is None or position.stop_loss < be_sl:
                            # Move SL to entry price
                            if skip_etoro_update:
                                position.stop_loss = be_sl
                                positions_updated += 1
                                logger.info(
                                    f"Breakeven stop set: {position.symbol} LONG "
                                    f"profit={profit_pct:.1%} → SL moved to entry {be_sl:.2f}"
                                )
                            else:
                                try:
                                    self.etoro_client.update_position_stop_loss(
                                        position_id=position.etoro_position_id,
                                        stop_loss_rate=be_sl
                                    )
                                    position.stop_loss = be_sl
                                    positions_updated += 1
                                    logger.info(
                                        f"Breakeven stop set: {position.symbol} LONG "
                                        f"profit={profit_pct:.1%} → SL moved to entry {be_sl:.2f}"
                                    )
                                except EToroAPIError as e:
                                    logger.warning(
                                        f"Could not set breakeven stop for {position.symbol}: {e}"
                                    )
                    else:  # SHORT
                        be_sl = position.entry_price  # Breakeven = entry price for shorts
                        if position.stop_loss is None or position.stop_loss > be_sl:
                            if skip_etoro_update:
                                position.stop_loss = be_sl
                                positions_updated += 1
                                logger.info(
                                    f"Breakeven stop set: {position.symbol} SHORT "
                                    f"profit={profit_pct:.1%} → SL moved to entry {be_sl:.2f}"
                                )
                            else:
                                try:
                                    self.etoro_client.update_position_stop_loss(
                                        position_id=position.etoro_position_id,
                                        stop_loss_rate=be_sl
                                    )
                                    position.stop_loss = be_sl
                                    positions_updated += 1
                                    logger.info(
                                        f"Breakeven stop set: {position.symbol} SHORT "
                                        f"profit={profit_pct:.1%} → SL moved to entry {be_sl:.2f}"
                                    )
                                except EToroAPIError as e:
                                    logger.warning(
                                        f"Could not set breakeven stop for {position.symbol}: {e}"
                                    )

                # ── PROFIT LOCK-IN ────────────────────────────────────────────────
                # When profit reaches the lock trigger, move SL to entry + lock_pct.
                # Closes the gap between breakeven (+3%) and trailing stop activation (+7.5%).
                # A position that goes +5% then reverses will now close with +2% profit,
                # not at breakeven.
                lock_params = self.PROFIT_LOCK_PARAMS.get(asset_class, self.PROFIT_LOCK_PARAMS["stock"])
                lock_trigger = lock_params["trigger"]
                lock_pct = lock_params["lock"]
                if profit_pct >= lock_trigger and position.entry_price > 0:
                    if position.side.value == "LONG":
                        lock_sl = position.entry_price * (1 + lock_pct)
                        if position.stop_loss is None or position.stop_loss < lock_sl:
                            if skip_etoro_update:
                                position.stop_loss = lock_sl
                                positions_updated += 1
                                logger.info(
                                    f"Profit lock: {position.symbol} LONG "
                                    f"profit={profit_pct:.1%} → SL locked at +{lock_pct:.1%} "
                                    f"({lock_sl:.2f})"
                                )
                            else:
                                try:
                                    self.etoro_client.update_position_stop_loss(
                                        position_id=position.etoro_position_id,
                                        stop_loss_rate=lock_sl
                                    )
                                    position.stop_loss = lock_sl
                                    positions_updated += 1
                                    logger.info(
                                        f"Profit lock: {position.symbol} LONG "
                                        f"profit={profit_pct:.1%} → SL locked at +{lock_pct:.1%} "
                                        f"({lock_sl:.2f})"
                                    )
                                except EToroAPIError as e:
                                    logger.warning(
                                        f"Could not set profit lock for {position.symbol}: {e}"
                                    )
                    else:  # SHORT
                        lock_sl = position.entry_price * (1 - lock_pct)
                        if position.stop_loss is None or position.stop_loss > lock_sl:
                            if skip_etoro_update:
                                position.stop_loss = lock_sl
                                positions_updated += 1
                                logger.info(
                                    f"Profit lock: {position.symbol} SHORT "
                                    f"profit={profit_pct:.1%} → SL locked at +{lock_pct:.1%} "
                                    f"({lock_sl:.2f})"
                                )
                            else:
                                try:
                                    self.etoro_client.update_position_stop_loss(
                                        position_id=position.etoro_position_id,
                                        stop_loss_rate=lock_sl
                                    )
                                    position.stop_loss = lock_sl
                                    positions_updated += 1
                                    logger.info(
                                        f"Profit lock: {position.symbol} SHORT "
                                        f"profit={profit_pct:.1%} → SL locked at +{lock_pct:.1%} "
                                        f"({lock_sl:.2f})"
                                    )
                                except EToroAPIError as e:
                                    logger.warning(
                                        f"Could not set profit lock for {position.symbol}: {e}"
                                    )

                # NOTE: Per-asset-class thresholds are always used.
                # The config-level trailing_stop_activation_pct / trailing_stop_distance_pct
                # are legacy fields kept for backward compatibility but no longer override
                # the asset-class-aware values. The per-asset-class calibration (based on
                # daily volatility ranges) is far more appropriate than a single global value.

                # Check activation threshold
                if profit_pct < activation_pct:
                    logger.debug(
                        f"Position {position.id} ({position.symbol}) profit {profit_pct:.2%} "
                        f"below {asset_class} activation {activation_pct:.0%}"
                    )
                    continue

                # Calculate new stop-loss level using ATR-aware minimum trail distance.
                # Trail distance = max(distance_pct * price, ATR_TRAIL_MULTIPLIER * daily_ATR)
                # This prevents penny-stop whipsaws on high-priced instruments where a fixed
                # percentage produces a stop within normal intraday noise.
                effective_distance = distance_pct
                try:
                    from src.data.market_data_manager import get_market_data_manager
                    from datetime import timedelta as _td, datetime as _dt
                    _mdm = get_market_data_manager()
                    _end = _dt.now()
                    _start = _end - _td(days=20)
                    _bars = _mdm.get_historical_data(position.symbol, _start, _end, interval="1d")
                    if _bars and len(_bars) >= 5:
                        _tr_list = []
                        for _i in range(1, len(_bars)):
                            _h = getattr(_bars[_i], 'high', None) or position.current_price
                            _l = getattr(_bars[_i], 'low', None) or position.current_price
                            _c_prev = getattr(_bars[_i - 1], 'close', None) or position.current_price
                            _tr_val = max(_h - _l, abs(_h - _c_prev), abs(_l - _c_prev))
                            _tr_list.append(_tr_val)
                        if _tr_list:
                            _atr = sum(_tr_list[-14:]) / min(14, len(_tr_list[-14:]))
                            _atr_pct = _atr / position.current_price if position.current_price > 0 else 0
                            _atr_floor = _atr_pct * self.ATR_TRAIL_MULTIPLIER
                            if _atr_floor > effective_distance:
                                logger.debug(
                                    f"ATR trail floor for {position.symbol}: "
                                    f"{effective_distance:.2%} → {_atr_floor:.2%} "
                                    f"(ATR={_atr_pct:.2%}, {self.ATR_TRAIL_MULTIPLIER}x)"
                                )
                                effective_distance = _atr_floor
                except Exception as _atr_err:
                    logger.debug(f"Could not compute ATR trail floor for {position.symbol}: {_atr_err}")

                if position.side.value == "LONG":
                    new_stop_loss = position.current_price * (1 - effective_distance)
                else:
                    new_stop_loss = position.current_price * (1 + effective_distance)

                # Only update if new stop is better than current
                should_update = False
                if position.stop_loss is None:
                    should_update = True
                    logger.info(
                        f"Position {position.id} ({position.symbol}) no stop-loss, "
                        f"setting trailing stop at {new_stop_loss:.2f} "
                        f"({asset_class}: {effective_distance:.2%} distance)"
                    )
                elif position.side.value == "LONG" and new_stop_loss > position.stop_loss:
                    should_update = True
                    logger.info(
                        f"Position {position.id} ({position.symbol}) trailing stop: "
                        f"{position.stop_loss:.2f} -> {new_stop_loss:.2f} "
                        f"(profit: {profit_pct:.2%}, {asset_class}: {effective_distance:.2%} distance)"
                    )
                elif position.side.value == "SHORT" and new_stop_loss < position.stop_loss:
                    should_update = True
                    logger.info(
                        f"Position {position.id} ({position.symbol}) trailing stop: "
                        f"{position.stop_loss:.2f} -> {new_stop_loss:.2f} "
                        f"(profit: {profit_pct:.2%}, {asset_class}: {effective_distance:.2%} distance)"
                    )

                if should_update:
                    if skip_etoro_update:
                        position.stop_loss = new_stop_loss
                        positions_updated += 1
                    else:
                        try:
                            self.etoro_client.update_position_stop_loss(
                                position_id=position.etoro_position_id,
                                stop_loss_rate=new_stop_loss
                            )
                            position.stop_loss = new_stop_loss
                            positions_updated += 1
                            logger.info(
                                f"Successfully updated trailing stop for {position.id} "
                                f"({position.symbol}) to {new_stop_loss:.2f}"
                            )
                        except EToroAPIError as e:
                            logger.error(
                                f"Failed to update stop-loss for {position.id} "
                                f"({position.symbol}): {e}"
                            )
                            continue

            except Exception as e:
                logger.error(f"Error processing position {position.id}: {e}")
                continue

        if positions_updated > 0:
            logger.info(f"Updated trailing stops for {positions_updated} positions")
        else:
            logger.debug("No trailing stop adjustments needed")

        return orders_created

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
