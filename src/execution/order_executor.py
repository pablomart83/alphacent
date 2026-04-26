"""Order executor for managing order lifecycle via eToro API."""

import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.data.market_hours_manager import AssetClass, MarketHoursManager
from src.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    SignalAction,
    TradingSignal,
)

logger = logging.getLogger(__name__)


class OrderExecutionError(Exception):
    """Order execution related errors."""
    pass


class Fill:
    """Represents an order fill event."""

    def __init__(
        self,
        order_id: str,
        filled_quantity: float,
        filled_price: float,
        filled_at: datetime,
        etoro_position_id: Optional[str] = None
    ):
        """Initialize fill event.
        
        Args:
            order_id: Order ID that was filled
            filled_quantity: Quantity filled
            filled_price: Price at which order was filled
            filled_at: Timestamp of fill
            etoro_position_id: eToro position ID (for new positions)
        """
        self.order_id = order_id
        self.filled_quantity = filled_quantity
        self.filled_price = filled_price
        self.filled_at = filled_at
        self.etoro_position_id = etoro_position_id


class OrderExecutor:
    """Manages order lifecycle via eToro API."""

    def __init__(
        self,
        etoro_client: EToroAPIClient,
        market_hours: MarketHoursManager,
        poll_interval: float = 1.0,
        max_poll_attempts: int = 300
    ):
        """Initialize order executor.
        
        Args:
            etoro_client: eToro API client for order submission
            market_hours: Market hours manager for checking market status
            poll_interval: Seconds between order status polls
            max_poll_attempts: Maximum number of polling attempts
        """
        self.etoro_client = etoro_client
        self.market_hours = market_hours
        self.poll_interval = poll_interval
        self.max_poll_attempts = max_poll_attempts

        # Track orders and positions
        self._orders: Dict[str, Order] = {}
        self._positions: Dict[str, Position] = {}
        self._queued_orders: List[Order] = []

        # Initialize TradeJournal for comprehensive trade logging (Task 11.1)
        try:
            from src.analytics.trade_journal import TradeJournal
            from src.models.database import get_database
            database = get_database()
            self.trade_journal = TradeJournal(database)
            logger.info("OrderExecutor initialized with TradeJournal")
        except Exception as e:
            logger.warning(f"Failed to initialize TradeJournal: {e}")
            self.trade_journal = None

        logger.info("Initialized OrderExecutor")

    def execute_signal(
        self,
        signal: TradingSignal,
        position_size: float,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None
    ) -> Order:
        """Create and submit order from validated signal.
        
        Args:
            signal: Trading signal to execute
            position_size: Position size (quantity or dollar amount)
            stop_loss_pct: Stop loss percentage (optional)
            take_profit_pct: Take profit percentage (optional)
            
        Returns:
            Created order
            
        Raises:
            OrderExecutionError: If order creation or submission fails
        """
        # Normalize symbol to ensure consistency (GE, 1017, ID_1017 all become "GE")
        from src.utils.symbol_normalizer import normalize_symbol
        normalized_symbol = normalize_symbol(signal.symbol)
        
        logger.info(f"Executing signal: {signal.action.value} {normalized_symbol} (size: {position_size})")

        try:
            # Validate minimum order size ($2000 for stocks/ETFs/crypto, $1000 for commodities/forex/indices)
            if position_size < 1000.0:
                raise OrderExecutionError(
                    f"Order size must be at least $1,000.00 (minimum position size). "
                    f"Requested: ${position_size:.2f} for {normalized_symbol}"
                )
            
            # Determine order side and type from signal action
            side, order_type = self._signal_to_order_params(signal.action)

            # Calculate stop loss and take profit rates from percentages
            stop_loss_rate = None
            take_profit_rate = None
            expected_price = None  # Track expected price for slippage calculation
            
            if stop_loss_pct or take_profit_pct:
                # Always fetch the real current price for SL/TP.
                # Use get_market_data which tries eToro's public rate endpoint first
                # (the same price eToro validates SL/TP against), then falls back to Yahoo.
                current_price = None
                spread_pct = 0.0
                try:
                    market_data = self.etoro_client.get_market_data(normalized_symbol)
                    current_price = market_data.close
                    expected_price = current_price  # Use this as expected price
                    
                    # Calculate spread from bid/ask if available
                    try:
                        _iid = self.etoro_client._get_instrument_id(normalized_symbol)
                        _resp = self.etoro_client._session.get(
                            f"{self.etoro_client.PUBLIC_URL}/sapi/trade-real/rates/{_iid}",
                            timeout=self.etoro_client.timeout
                        )
                        if _resp.status_code == 200:
                            _data = _resp.json()
                            _rate = _data.get("Rate", {})
                            _ask = float(_rate.get("Ask", 0))
                            _bid = float(_rate.get("Bid", 0))
                            if _ask > 0 and _bid > 0:
                                spread_pct = (_ask - _bid) / ((_ask + _bid) / 2)
                                logger.info(
                                    f"Spread for {normalized_symbol}: bid={_bid:.4f} ask={_ask:.4f} "
                                    f"spread={spread_pct:.4%}"
                                )
                    except Exception as spread_err:
                        logger.warning(f"Could not fetch spread for {normalized_symbol}: {spread_err}")
                    
                    logger.info(f"Fetched live price for {normalized_symbol} from {market_data.source.value}: {current_price}")
                except Exception as e:
                    logger.warning(f"Could not fetch live price for SL/TP calculation: {e}")

                # Fallback: use signal indicator price only if all price sources failed
                if not current_price:
                    current_price = signal.indicators.get("price") or signal.indicators.get("close")
                    if current_price:
                        expected_price = current_price
                        logger.warning(
                            f"Using signal indicator price {current_price} for {normalized_symbol} "
                            f"as fallback — live price unavailable"
                        )

                if current_price:
                    is_buy = side == OrderSide.BUY
                    
                    # ATR-based minimum floor: ensure SL gives the trade enough room
                    # relative to the instrument's actual volatility. This catches cases
                    # where a strategy's risk params were calibrated for a different asset
                    # class (e.g., forex primary symbol but trading a stock watchlist symbol).
                    if stop_loss_pct and current_price > 0:
                        try:
                            from src.data.market_data_manager import get_market_data_manager
                            from datetime import timedelta as _td

                            _mdm = get_market_data_manager()
                            if _mdm is None:
                                # Fallback: use shared singleton
                                from src.data.market_data_manager import get_market_data_manager
                                _mdm = get_market_data_manager()

                            _end = datetime.now()
                            _start = _end - _td(days=30)
                            _bars = _mdm.get_historical_data(normalized_symbol, _start, _end, interval="1d")

                            if _bars and len(_bars) > 14:
                                _highs = [b.high for b in _bars if b.high and b.low and b.close]
                                _lows = [b.low for b in _bars if b.high and b.low and b.close]
                                _closes = [b.close for b in _bars if b.high and b.low and b.close]
                                if len(_closes) > 14:
                                    _tr_list = []
                                    for _i in range(1, len(_closes)):
                                        _tr_val = max(
                                            _highs[_i] - _lows[_i],
                                            abs(_highs[_i] - _closes[_i - 1]),
                                            abs(_lows[_i] - _closes[_i - 1])
                                        )
                                        _tr_list.append(_tr_val)
                                    if _tr_list:
                                        _atr14 = sum(_tr_list[-14:]) / min(14, len(_tr_list[-14:]))
                                        _atr_pct = _atr14 / current_price
                                        # SL must be at least 2.5x ATR (raised from 2x).
                                        # In ranging_low_vol regime, 2x ATR is too tight —
                                        # normal intraday noise consumes the entire stop distance.
                                        # 2.5x gives the trade room to breathe without being
                                        # so wide that the R:R ratio collapses.
                                        _atr_floor = _atr_pct * 2.5

                                        if stop_loss_pct < _atr_floor:
                                            original_rr = (take_profit_pct / stop_loss_pct) if take_profit_pct and stop_loss_pct else 2.0
                                            old_sl = stop_loss_pct
                                            stop_loss_pct = round(_atr_floor, 4)
                                            if take_profit_pct:
                                                take_profit_pct = round(stop_loss_pct * original_rr, 4)
                                            # Clamp SL to max 12% to avoid absurdly wide stops
                                            if stop_loss_pct > 0.12:
                                                stop_loss_pct = 0.12
                                                if take_profit_pct:
                                                    take_profit_pct = round(0.12 * original_rr, 4)
                                            logger.info(
                                                f"ATR floor at order time for {normalized_symbol}: "
                                                f"SL {old_sl:.2%} → {stop_loss_pct:.2%} "
                                                f"(ATR={_atr_pct:.2%}, floor=2.5x ATR={_atr_floor:.2%}). "
                                                f"TP adjusted to {take_profit_pct:.2%} (R:R={original_rr:.1f}x)"
                                            )
                        except Exception as _atr_err:
                            logger.debug(f"Could not compute ATR floor for {normalized_symbol}: {_atr_err}")
                    
                    # Adjust SL/TP for spread: add spread buffer to SL distance,
                    # scale TP proportionally to maintain reward-risk ratio.
                    # This prevents positions from hitting SL immediately due to
                    # bid-ask spread (especially on low-priced or illiquid instruments).
                    effective_sl_pct = stop_loss_pct
                    effective_tp_pct = take_profit_pct
                    if spread_pct > 0.001 and stop_loss_pct:  # Only adjust if spread > 0.1%
                        original_rr = (take_profit_pct / stop_loss_pct) if take_profit_pct and stop_loss_pct else 2.0
                        effective_sl_pct = stop_loss_pct + spread_pct
                        if take_profit_pct:
                            effective_tp_pct = effective_sl_pct * original_rr
                        logger.info(
                            f"Spread-adjusted SL/TP for {normalized_symbol}: "
                            f"SL {stop_loss_pct:.2%} → {effective_sl_pct:.2%}, "
                            f"TP {take_profit_pct:.2%} → {effective_tp_pct:.2%} "
                            f"(spread={spread_pct:.2%}, R:R={original_rr:.1f})"
                        )
                    
                    if stop_loss_pct:
                        if is_buy:
                            stop_loss_rate = round(current_price * (1 - effective_sl_pct), 4)
                        else:
                            stop_loss_rate = round(current_price * (1 + effective_sl_pct), 4)
                        logger.info(f"Calculated stop loss rate: {stop_loss_rate} ({effective_sl_pct*100:.2f}% from {current_price})")
                    if take_profit_pct:
                        if is_buy:
                            take_profit_rate = round(current_price * (1 + effective_tp_pct), 4)
                        else:
                            take_profit_rate = round(current_price * (1 - effective_tp_pct), 4)
                        logger.info(f"Calculated take profit rate: {take_profit_rate} ({effective_tp_pct*100:.2f}% from {current_price})")
                else:
                    logger.warning(f"No price available for {normalized_symbol} — submitting order without SL/TP")
            else:
                # Even without SL/TP, try to get expected price for slippage tracking
                try:
                    market_data = self.etoro_client.get_market_data(normalized_symbol)
                    expected_price = market_data.close
                    logger.debug(f"Expected price for {normalized_symbol}: {expected_price}")
                except Exception as e:
                    # Fallback to signal indicator price
                    expected_price = signal.indicators.get("price") or signal.indicators.get("close")
                    if expected_price:
                        logger.debug(f"Using signal price as expected price: {expected_price}")

            # Create order object with normalized symbol
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id=signal.strategy_id,
                symbol=normalized_symbol,  # Use normalized symbol
                side=side,
                order_type=order_type,
                quantity=position_size,
                status=OrderStatus.PENDING,
                price=None,  # Market orders don't have limit price
                stop_price=stop_loss_rate,
                take_profit_price=take_profit_rate,
                submitted_at=None,
                filled_at=None,
                filled_price=None,
                filled_quantity=None,
                etoro_order_id=None,
                expected_price=expected_price,  # Set expected price for slippage tracking
                metadata=signal.metadata if hasattr(signal, 'metadata') else None,
            )

            # Store order
            self._orders[order.id] = order

            # Market hours gate: don't submit to eToro when the market is closed
            # for this asset class. eToro queues the order silently and executes it
            # at the next open — creating positions we can't track until reconciliation.
            # Crypto is 24/7 and always passes. Stocks/ETFs/indices/forex/commodities
            # are blocked outside regular session hours.
            # The signal will re-fire on the next scheduler cycle when market is open.
            try:
                from src.data.market_hours_manager import MarketHoursManager, AssetClass as _AssetClass
                _mhm = MarketHoursManager()
                _asset_cls = self._determine_asset_class(normalized_symbol)
                if not _mhm.is_market_open(_asset_cls):
                    raise OrderExecutionError(
                        f"Market closed for {normalized_symbol} ({_asset_cls.value}) — "
                        f"order not submitted to eToro. Signal will re-fire at next open."
                    )
            except OrderExecutionError:
                raise
            except Exception as _mh_err:
                # If market hours check itself fails, log and proceed — fail-open
                # is safer than blocking valid orders due to a timezone library issue.
                logger.warning(f"Market hours check failed for {normalized_symbol}: {_mh_err} — proceeding with submission")

            # Always submit to eToro — eToro handles market hours internally
            # (stocks trade 24x5 Mon-Fri, crypto trades 24x7)
            # Submit order to eToro
            self._submit_order(order)

            # If order submitted successfully and it's an entry signal, log SL/TP info
            if signal.action in [SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT]:
                if order.stop_price or order.take_profit_price:
                    logger.info(f"Order {order.id} submitted with SL={order.stop_price}, TP={order.take_profit_price}")

            return order

        except Exception as e:
            logger.error(f"Failed to execute signal: {e}")
            raise OrderExecutionError(f"Failed to execute signal: {e}")

    def _signal_to_order_params(self, action: SignalAction) -> tuple[OrderSide, OrderType]:
        """Convert signal action to order parameters.
        
        Args:
            action: Signal action
            
        Returns:
            Tuple of (order_side, order_type)
        """
        if action == SignalAction.ENTER_LONG:
            return OrderSide.BUY, OrderType.MARKET
        elif action == SignalAction.ENTER_SHORT:
            return OrderSide.SELL, OrderType.MARKET
        elif action == SignalAction.EXIT_LONG:
            return OrderSide.SELL, OrderType.MARKET
        elif action == SignalAction.EXIT_SHORT:
            return OrderSide.BUY, OrderType.MARKET
        else:
            raise ValueError(f"Unknown signal action: {action}")

    def _determine_asset_class(self, symbol: str) -> AssetClass:
        """Determine asset class from symbol.
        
        Args:
            symbol: Instrument symbol
            
        Returns:
            Asset class
        """
        # Simple heuristic - in production would use a proper symbol database
        crypto_indicators = ["BTC", "ETH", "USDT", "XRP", "ADA", "DOGE", "SOL", "-USD"]
        if any(indicator in symbol.upper() for indicator in crypto_indicators):
            return AssetClass.CRYPTOCURRENCY

        # Default to stock
        return AssetClass.STOCK

    def _submit_order(self, order: Order) -> None:
        """Submit order to eToro API.
        
        Args:
            order: Order to submit
            
        Raises:
            OrderExecutionError: If submission fails
        """
        try:
            logger.info(f"Submitting order {order.id} to eToro: {order.side.value} {order.quantity} {order.symbol}")

            # Submit to eToro
            response = self.etoro_client.place_order(
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                price=order.price,
                stop_price=order.stop_price,
                take_profit_price=order.take_profit_price
            )

            # Update order with eToro response
            order.etoro_order_id = response.get("order_id")
            order.status = OrderStatus.PENDING
            order.submitted_at = datetime.now()

            logger.info(f"Order {order.id} submitted successfully, eToro order ID: {order.etoro_order_id}")

        except EToroAPIError as e:
            logger.error(f"Failed to submit order {order.id}: {e}")
            order.status = OrderStatus.FAILED
            raise OrderExecutionError(f"Failed to submit order: {e}")

    def track_order(self, order_id: str, wait_for_fill: bool = True) -> OrderStatus:
        """Monitor order status until filled/cancelled.
        
        Args:
            order_id: Order ID to track
            wait_for_fill: If True, poll until order is filled or cancelled
            
        Returns:
            Final order status
            
        Raises:
            OrderExecutionError: If order not found or tracking fails
        """
        order = self._orders.get(order_id)
        if order is None:
            raise OrderExecutionError(f"Order {order_id} not found")

        if not order.etoro_order_id:
            logger.warning(f"Order {order_id} has no eToro order ID, cannot track")
            return order.status

        logger.info(f"Tracking order {order_id} (eToro ID: {order.etoro_order_id})")

        if not wait_for_fill:
            # Just check current status once
            return self._check_order_status(order)

        # Poll until order is in terminal state
        attempts = 0
        while attempts < self.max_poll_attempts:
            status = self._check_order_status(order)

            # Check if order is in terminal state
            # Note: PARTIALLY_FILLED is not terminal - we continue tracking
            if status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.FAILED]:
                logger.info(f"Order {order_id} reached terminal state: {status.value}")
                return status

            # Wait before next poll
            time.sleep(self.poll_interval)
            attempts += 1

        logger.warning(f"Order {order_id} tracking timed out after {attempts} attempts")
        return order.status

    def _check_order_status(self, order: Order) -> OrderStatus:
        """Check order status from eToro API.
        
        Args:
            order: Order to check
            
        Returns:
            Current order status
        """
        try:
            response = self.etoro_client.get_order_status(order.etoro_order_id)

            # Parse status
            status_str = response.get("status", "").upper()
            filled_quantity = float(response.get("filled_quantity", 0.0))
            
            if status_str == "FILLED":
                order.status = OrderStatus.FILLED
                order.filled_at = datetime.fromisoformat(response.get("filled_at", datetime.now().isoformat()))
                order.filled_price = float(response.get("filled_price", 0.0))
                order.filled_quantity = filled_quantity

                # Handle fill
                fill = Fill(
                    order_id=order.id,
                    filled_quantity=order.filled_quantity,
                    filled_price=order.filled_price,
                    filled_at=order.filled_at,
                    etoro_position_id=response.get("position_id")
                )
                self.handle_fill(order, fill)

            elif status_str == "PARTIALLY_FILLED":
                # Handle partial fill
                order.status = OrderStatus.PARTIALLY_FILLED
                order.filled_quantity = filled_quantity
                order.filled_price = float(response.get("average_fill_price", 0.0))
                
                # Calculate remaining quantity
                remaining_quantity = order.quantity - filled_quantity
                
                logger.info(
                    f"Order {order.id} partially filled: "
                    f"{filled_quantity}/{order.quantity} filled, "
                    f"{remaining_quantity} remaining"
                )
                
                # Handle partial fill (update position with partial quantity)
                if filled_quantity > 0:
                    fill = Fill(
                        order_id=order.id,
                        filled_quantity=filled_quantity,
                        filled_price=order.filled_price,
                        filled_at=datetime.now(),
                        etoro_position_id=response.get("position_id")
                    )
                    self.handle_partial_fill(order, fill, remaining_quantity)

            elif status_str == "CANCELLED":
                order.status = OrderStatus.CANCELLED
            elif status_str == "FAILED":
                order.status = OrderStatus.FAILED
            elif status_str == "PENDING":
                order.status = OrderStatus.PENDING
            elif status_str == "SUBMITTED":
                order.status = OrderStatus.PENDING

            return order.status

        except EToroAPIError as e:
            logger.error(f"Failed to check order status for {order.id}: {e}")
            return order.status

    def handle_fill(self, order: Order, fill: Fill) -> None:
        """Update position records when order filled.
        
        Args:
            order: Filled order
            fill: Fill event details
        """
        logger.info(f"Handling fill for order {order.id}: {fill.filled_quantity} @ {fill.filled_price}")

        try:
            # Determine if this is opening or closing a position
            if order.side == OrderSide.BUY:
                # Opening long or closing short
                self._handle_buy_fill(order, fill)
            else:
                # Opening short or closing long
                self._handle_sell_fill(order, fill)
            
            # Increment live_trade_count for the strategy
            self._increment_strategy_live_trade_count(order.strategy_id)
            
            # Track trade for frequency limiting (Task 6)
            try:
                from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter
                import yaml
                from pathlib import Path
                
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f)
                    
                    frequency_limiter = TradeFrequencyLimiter(config, self.database)
                    frequency_limiter.record_trade(
                        strategy_id=order.strategy_id,
                        symbol=order.symbol,
                        timestamp=fill.filled_at
                    )
                    logger.debug(f"Recorded trade for frequency tracking: {order.symbol}")
            except Exception as e:
                logger.warning(f"Failed to record trade for frequency tracking: {e}")
            
            # Log transaction costs (Task 6)
            try:
                from src.strategy.transaction_cost_tracker import TransactionCostTracker
                
                if config_path.exists():
                    cost_tracker = TransactionCostTracker(config, self.database)
                    costs = cost_tracker.calculate_trade_cost(
                        symbol=order.symbol,
                        quantity=fill.filled_quantity,
                        price=order.price or fill.filled_price,
                        filled_price=fill.filled_price
                    )
                    logger.info(
                        f"Transaction costs for {order.symbol}: ${costs['total']:.2f} "
                        f"({costs['total_percent']:.3f}% of trade value) - "
                        f"commission: ${costs['commission']:.2f}, "
                        f"slippage: ${costs['slippage']:.2f}, "
                        f"spread: ${costs['spread']:.2f}"
                    )
            except Exception as e:
                logger.warning(f"Failed to calculate transaction costs: {e}")

        except Exception as e:
            logger.error(f"Failed to handle fill for order {order.id}: {e}")
            raise OrderExecutionError(f"Failed to handle fill: {e}")

    def handle_partial_fill(self, order: Order, fill: Fill, remaining_quantity: float) -> None:
        """Handle partial fill with remaining quantity tracking.
        
        Args:
            order: Partially filled order
            fill: Fill event details
            remaining_quantity: Quantity remaining to be filled
        """
        logger.info(
            f"Handling partial fill for order {order.id}: "
            f"{fill.filled_quantity} filled @ {fill.filled_price}, "
            f"{remaining_quantity} remaining"
        )

        try:
            # Update position with partial quantity
            if order.side == OrderSide.BUY:
                self._handle_buy_fill(order, fill)
            else:
                self._handle_sell_fill(order, fill)

            # Log partial fill tracking
            logger.info(
                f"Partial fill tracking - "
                f"Order ID: {order.id}, "
                f"Original quantity: {order.quantity}, "
                f"Filled quantity: {fill.filled_quantity}, "
                f"Remaining quantity: {remaining_quantity}, "
                f"Fill percentage: {(fill.filled_quantity / order.quantity) * 100:.2f}%"
            )

            # Notify user about partial fill
            self._notify_user_partial_fill(order, fill, remaining_quantity)

        except Exception as e:
            logger.error(f"Failed to handle partial fill for order {order.id}: {e}")
            raise OrderExecutionError(f"Failed to handle partial fill: {e}")

    def _notify_user_partial_fill(self, order: Order, fill: Fill, remaining_quantity: float) -> None:
        """Send user notification about partial fill.
        
        Args:
            order: Partially filled order
            fill: Fill event details
            remaining_quantity: Quantity remaining to be filled
        """
        # In production, this would send notification via WebSocket to Dashboard
        notification = {
            "type": "PARTIAL_FILL",
            "severity": "INFO",
            "timestamp": datetime.now().isoformat(),
            "order_id": order.id,
            "symbol": order.symbol,
            "side": order.side.value,
            "original_quantity": order.quantity,
            "filled_quantity": fill.filled_quantity,
            "remaining_quantity": remaining_quantity,
            "fill_price": fill.filled_price,
            "fill_percentage": (fill.filled_quantity / order.quantity) * 100,
            "message": (
                f"Partial fill: {order.side.value} {fill.filled_quantity}/{order.quantity} "
                f"{order.symbol} @ {fill.filled_price} ({remaining_quantity} remaining)"
            )
        }
        
        logger.info(f"USER_NOTIFICATION: {notification}")

    def _handle_buy_fill(self, order: Order, fill: Fill) -> None:
        """Handle buy order fill (open long or close short).
        
        Args:
            order: Filled order
            fill: Fill event
        """
        # Check if we have an existing short position to close
        existing_position = self._find_position(order.symbol, PositionSide.SHORT)

        if existing_position:
            # Closing short position
            logger.info(f"Closing short position {existing_position.id}")
            existing_position.quantity -= fill.filled_quantity
            existing_position.current_price = fill.filled_price

            # Calculate realized P&L
            pnl = (existing_position.entry_price - fill.filled_price) * fill.filled_quantity
            existing_position.realized_pnl += pnl

            if existing_position.quantity <= 0:
                existing_position.closed_at = fill.filled_at
                logger.info(f"Short position {existing_position.id} fully closed, realized P&L: {existing_position.realized_pnl}")
                
                # Log trade exit to journal (Task 11.1)
                if self.trade_journal:
                    try:
                        self.trade_journal.log_exit(
                            trade_id=existing_position.id,
                            exit_time=fill.filled_at,
                            exit_price=fill.filled_price,
                            exit_reason="Position closed (buy to cover short)",
                            exit_order_id=order.id,
                            symbol=existing_position.symbol
                        )
                        logger.debug(f"Logged trade exit to journal: {existing_position.id}")
                    except Exception as e:
                        logger.warning(f"Failed to log trade exit to journal: {e}")
        else:
            # Opening new long position
            position = Position(
                id=str(uuid.uuid4()),
                strategy_id=order.strategy_id,
                symbol=order.symbol,
                side=PositionSide.LONG,
                quantity=fill.filled_quantity,  # eToro uses dollar amount as quantity
                entry_price=fill.filled_price,
                current_price=fill.filled_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=fill.filled_at,
                etoro_position_id=fill.etoro_position_id or f"etoro_{order.etoro_order_id}",
                stop_loss=order.stop_price,
                take_profit=order.take_profit_price,
                closed_at=None
            )
            self._positions[position.id] = position
            logger.info(
                f"Opened long position {position.id}: ${position.quantity:.2f} in {position.symbol} "
                f"@ ${position.entry_price:.2f}"
            )
            
            # Persist position to database
            from src.models.database import get_database
            from src.models.orm import PositionORM
            
            db = get_database()
            session = db.get_session()
            try:
                position_orm = PositionORM(
                    id=position.id,
                    strategy_id=position.strategy_id,
                    symbol=position.symbol,
                    side=position.side,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    unrealized_pnl=position.unrealized_pnl,
                    realized_pnl=position.realized_pnl,
                    opened_at=position.opened_at,
                    etoro_position_id=position.etoro_position_id,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    closed_at=position.closed_at
                )
                session.add(position_orm)
                session.commit()
                logger.info(f"Position {position.id} persisted to database")
            except Exception as e:
                logger.error(f"Failed to persist position to database: {e}")
                session.rollback()
            finally:
                session.close()
            
            # Automatically attach stop loss and take profit based on strategy risk params
            self._auto_attach_risk_orders(position, order)
            
            # Log trade entry to journal (Task 11.1)
            if self.trade_journal:
                try:
                    # Extract metadata from order if available
                    metadata = getattr(order, 'metadata', {}) or {}
                    conviction_score = metadata.get('conviction_score')
                    ml_confidence = metadata.get('ml_confidence')
                    market_regime = metadata.get('market_regime')
                    fundamentals = metadata.get('fundamentals')
                    
                    self.trade_journal.log_entry(
                        trade_id=position.id,
                        strategy_id=position.strategy_id,
                        symbol=position.symbol,
                        entry_time=position.opened_at,
                        entry_price=position.entry_price,
                        entry_size=position.quantity,
                        entry_reason=f"Long position opened via {order.side.value} order",
                        entry_order_id=order.id,
                        market_regime=market_regime,
                        sector=None,  # Could be enriched from symbol metadata
                        fundamentals=fundamentals,
                        conviction_score=conviction_score,
                        ml_confidence=ml_confidence,
                        metadata=metadata,
                        expected_price=order.expected_price,
                        order_side=order.side.value if order.side else None
                    )
                    logger.debug(f"Logged trade entry to journal: {position.id}")
                except Exception as e:
                    logger.warning(f"Failed to log trade entry to journal: {e}")

    def _handle_sell_fill(self, order: Order, fill: Fill) -> None:
        """Handle sell order fill (open short or close long).
        
        Args:
            order: Filled order
            fill: Fill event
        """
        # Check if we have an existing long position to close
        existing_position = self._find_position(order.symbol, PositionSide.LONG)

        if existing_position:
            # Closing long position
            logger.info(f"Closing long position {existing_position.id}")
            existing_position.quantity -= fill.filled_quantity
            existing_position.current_price = fill.filled_price

            # Calculate realized P&L
            pnl = (fill.filled_price - existing_position.entry_price) * fill.filled_quantity
            existing_position.realized_pnl += pnl

            if existing_position.quantity <= 0:
                existing_position.closed_at = fill.filled_at
                logger.info(f"Long position {existing_position.id} fully closed, realized P&L: {existing_position.realized_pnl}")
                
                # Log trade exit to journal (Task 11.1)
                if self.trade_journal:
                    try:
                        self.trade_journal.log_exit(
                            trade_id=existing_position.id,
                            exit_time=fill.filled_at,
                            exit_price=fill.filled_price,
                            exit_reason="Position closed (sell to close long)",
                            exit_order_id=order.id,
                            symbol=existing_position.symbol
                        )
                        logger.debug(f"Logged trade exit to journal: {existing_position.id}")
                    except Exception as e:
                        logger.warning(f"Failed to log trade exit to journal: {e}")
        else:
            # Opening new short position
            position = Position(
                id=str(uuid.uuid4()),
                strategy_id=order.strategy_id,
                symbol=order.symbol,
                side=PositionSide.SHORT,
                quantity=fill.filled_quantity,  # eToro uses dollar amount as quantity
                entry_price=fill.filled_price,
                current_price=fill.filled_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=fill.filled_at,
                etoro_position_id=fill.etoro_position_id or f"etoro_{order.etoro_order_id}",
                stop_loss=order.stop_price,
                take_profit=order.take_profit_price,
                closed_at=None
            )
            self._positions[position.id] = position
            logger.info(
                f"Opened short position {position.id}: ${position.quantity:.2f} in {position.symbol} "
                f"@ ${position.entry_price:.2f}"
            )
            
            # Persist position to database
            from src.models.database import get_database
            from src.models.orm import PositionORM
            
            db = get_database()
            session = db.get_session()
            try:
                position_orm = PositionORM(
                    id=position.id,
                    strategy_id=position.strategy_id,
                    symbol=position.symbol,
                    side=position.side,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    current_price=position.current_price,
                    unrealized_pnl=position.unrealized_pnl,
                    realized_pnl=position.realized_pnl,
                    opened_at=position.opened_at,
                    etoro_position_id=position.etoro_position_id,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    closed_at=position.closed_at
                )
                session.add(position_orm)
                session.commit()
                logger.info(f"Position {position.id} persisted to database")
            except Exception as e:
                logger.error(f"Failed to persist position to database: {e}")
                session.rollback()
            finally:
                session.close()
            
            # Automatically attach stop loss and take profit based on strategy risk params
            self._auto_attach_risk_orders(position, order)
            
            # Log trade entry to journal (Task 11.1)
            if self.trade_journal:
                try:
                    # Extract metadata from order if available
                    metadata = getattr(order, 'metadata', {}) or {}
                    conviction_score = metadata.get('conviction_score')
                    ml_confidence = metadata.get('ml_confidence')
                    market_regime = metadata.get('market_regime')
                    fundamentals = metadata.get('fundamentals')
                    
                    self.trade_journal.log_entry(
                        trade_id=position.id,
                        strategy_id=position.strategy_id,
                        symbol=position.symbol,
                        entry_time=position.opened_at,
                        entry_price=position.entry_price,
                        entry_size=position.quantity,
                        entry_reason=f"Short position opened via {order.side.value} order",
                        entry_order_id=order.id,
                        market_regime=market_regime,
                        sector=None,  # Could be enriched from symbol metadata
                        fundamentals=fundamentals,
                        conviction_score=conviction_score,
                        ml_confidence=ml_confidence,
                        metadata=metadata,
                        expected_price=order.expected_price,
                        order_side=order.side.value if order.side else None
                    )
                    logger.debug(f"Logged trade entry to journal: {position.id}")
                except Exception as e:
                    logger.warning(f"Failed to log trade entry to journal: {e}")

    def _find_position(self, symbol: str, side: PositionSide) -> Optional[Position]:
        """Find open position for symbol and side.
        
        Args:
            symbol: Instrument symbol
            side: Position side
            
        Returns:
            Position if found, None otherwise
        """
        for position in self._positions.values():
            if position.symbol == symbol and position.side == side and position.closed_at is None:
                return position
        return None

    def _auto_attach_risk_orders(self, position: Position, order: Order) -> None:
        """Automatically attach stop loss and take profit orders to new position.
        
        This method retrieves risk parameters from the order metadata (if provided by the strategy)
        or uses default risk parameters. It then calculates and attaches stop loss and take profit
        orders based on the position's entry price and side.
        
        Args:
            position: Newly opened position
            order: Order that created the position (may contain risk params in metadata)
        """
        try:
            # Try to get risk parameters from order metadata (if strategy provided them)
            # Otherwise use default values
            from src.models import RiskConfig
            
            # Default risk config
            default_risk = RiskConfig()
            stop_loss_pct = default_risk.stop_loss_pct
            take_profit_pct = default_risk.take_profit_pct
            
            # Calculate stop loss and take profit prices based on position side
            if position.side == PositionSide.LONG:
                # For long positions: stop loss below entry, take profit above
                stop_price = position.entry_price * (1 - stop_loss_pct)
                target_price = position.entry_price * (1 + take_profit_pct)
            else:
                # For short positions: stop loss above entry, take profit below
                stop_price = position.entry_price * (1 + stop_loss_pct)
                target_price = position.entry_price * (1 - take_profit_pct)
            
            # Attach stop loss
            logger.info(f"Auto-attaching stop loss to position {position.id} at {stop_price}")
            self.attach_stop_loss(position, stop_price)
            
            # Attach take profit
            logger.info(f"Auto-attaching take profit to position {position.id} at {target_price}")
            self.attach_take_profit(position, target_price)
            
        except Exception as e:
            # Log error but don't fail the position creation
            logger.error(f"Failed to auto-attach risk orders to position {position.id}: {e}")
            logger.warning(f"Position {position.id} opened without automatic stop loss/take profit")

    def attach_stop_loss(self, position: Position, stop_price: float) -> None:
        """Attach stop loss order to position.
        
        Args:
            position: Position to protect
            stop_price: Stop loss price
            
        Raises:
            OrderExecutionError: If stop loss attachment fails
        """
        logger.info(f"Attaching stop loss to position {position.id} at {stop_price}")

        try:
            # Determine order side (opposite of position)
            side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

            # Create stop loss order
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id=position.strategy_id,
                symbol=position.symbol,
                side=side,
                order_type=OrderType.STOP_LOSS,
                quantity=position.quantity,
                status=OrderStatus.PENDING,
                price=None,
                stop_price=stop_price,
                submitted_at=None,
                filled_at=None,
                filled_price=None,
                filled_quantity=None,
                etoro_order_id=None
            )

            # Submit stop loss order
            self._submit_order(order)

            # Update position
            position.stop_loss = stop_price

            logger.info(f"Stop loss attached to position {position.id}")

        except Exception as e:
            logger.error(f"Failed to attach stop loss to position {position.id}: {e}")
            raise OrderExecutionError(f"Failed to attach stop loss: {e}")

    def attach_take_profit(self, position: Position, target_price: float) -> None:
        """Attach take profit order to position.
        
        Args:
            position: Position to protect
            target_price: Take profit price
            
        Raises:
            OrderExecutionError: If take profit attachment fails
        """
        logger.info(f"Attaching take profit to position {position.id} at {target_price}")

        try:
            # Determine order side (opposite of position)
            side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

            # Create take profit order
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id=position.strategy_id,
                symbol=position.symbol,
                side=side,
                order_type=OrderType.TAKE_PROFIT,
                quantity=position.quantity,
                status=OrderStatus.PENDING,
                price=target_price,
                stop_price=None,
                submitted_at=None,
                filled_at=None,
                filled_price=None,
                filled_quantity=None,
                etoro_order_id=None
            )

            # Submit take profit order
            self._submit_order(order)

            # Update position
            position.take_profit = target_price

            logger.info(f"Take profit attached to position {position.id}")

        except Exception as e:
            logger.error(f"Failed to attach take profit to position {position.id}: {e}")
            raise OrderExecutionError(f"Failed to attach take profit: {e}")

    def close_position(self, position_id: str) -> Order:
        """Create market order to close position.
        
        Args:
            position_id: Position ID to close
            
        Returns:
            Close order
            
        Raises:
            OrderExecutionError: If position not found or close fails
        """
        position = self._positions.get(position_id)
        if position is None:
            raise OrderExecutionError(f"Position {position_id} not found")

        if position.closed_at is not None:
            raise OrderExecutionError(f"Position {position_id} is already closed")

        logger.info(f"Closing position {position_id}: {position.symbol} {position.side.value}")

        try:
            # Determine order side (opposite of position)
            side = OrderSide.SELL if position.side == PositionSide.LONG else OrderSide.BUY

            # Create close order
            order = Order(
                id=str(uuid.uuid4()),
                strategy_id=position.strategy_id,
                symbol=position.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                status=OrderStatus.PENDING,
                price=None,
                stop_price=None,
                submitted_at=None,
                filled_at=None,
                filled_price=None,
                filled_quantity=None,
                etoro_order_id=None
            )

            # Store and submit order
            self._orders[order.id] = order
            self._submit_order(order)

            return order

        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
            raise OrderExecutionError(f"Failed to close position: {e}")

    def close_all_positions(self) -> List[Order]:
        """Close all open positions (for kill switch).
        
        Returns:
            List of close orders
        """
        logger.info("Closing all open positions")

        close_orders = []
        for position in self._positions.values():
            if position.closed_at is None:
                try:
                    order = self.close_position(position.id)
                    close_orders.append(order)
                except OrderExecutionError as e:
                    logger.error(f"Failed to close position {position.id}: {e}")

        logger.info(f"Submitted {len(close_orders)} close orders")
        return close_orders
    
    def _increment_strategy_live_trade_count(self, strategy_id: str) -> None:
        """Increment live_trade_count for a strategy when an order is filled.
        
        Args:
            strategy_id: Strategy ID to increment count for
        """
        try:
            from src.models.database import get_database
            from src.models.orm import StrategyORM
            
            db = get_database()
            session = db.get_session()
            try:
                strategy_orm = session.query(StrategyORM).filter_by(id=strategy_id).first()
                if strategy_orm:
                    strategy_orm.live_trade_count += 1
                    session.commit()
                    logger.debug(f"Incremented live_trade_count for strategy {strategy_id} to {strategy_orm.live_trade_count}")
                else:
                    logger.warning(f"Strategy {strategy_id} not found, cannot increment live_trade_count")
            except Exception as e:
                logger.error(f"Failed to increment live_trade_count for strategy {strategy_id}: {e}")
                session.rollback()
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to get database session for incrementing live_trade_count: {e}")

    def handle_order_failure(self, order: Order, error: Exception, retry_count: int = 0) -> bool:
        """Log failure, retry if appropriate, notify user.
        
        Args:
            order: Failed order
            error: Exception that caused failure
            retry_count: Number of retry attempts made so far
            
        Returns:
            True if retry will be attempted, False otherwise
        """
        logger.error(f"Order {order.id} failed (attempt {retry_count + 1}): {error}")

        # Log detailed error information
        logger.error(
            f"Order failure details - "
            f"Order ID: {order.id}, "
            f"Symbol: {order.symbol}, "
            f"Side: {order.side.value}, "
            f"Type: {order.order_type.value}, "
            f"Quantity: {order.quantity}, "
            f"Error: {str(error)}"
        )

        # Determine if error is transient and retryable
        is_transient = self._is_transient_error(error)
        max_retries = 3
        should_retry = is_transient and retry_count < max_retries

        if should_retry:
            # Calculate exponential backoff delay
            delay = min(2 ** retry_count, 60)  # Cap at 60 seconds
            logger.info(f"Will retry order {order.id} after {delay} seconds (attempt {retry_count + 1}/{max_retries})")
            
            # Schedule retry (in production, this would use a task queue)
            # For now, we'll just log the intent
            time.sleep(delay)
            
            try:
                # Retry order submission
                self._submit_order(order)
                logger.info(f"Order {order.id} retry successful")
                return True
            except Exception as retry_error:
                logger.error(f"Order {order.id} retry failed: {retry_error}")
                # Recursively handle failure with incremented retry count
                return self.handle_order_failure(order, retry_error, retry_count + 1)
        else:
            # No more retries, mark as permanently failed
            order.status = OrderStatus.FAILED
            
            # Send user notification
            self._notify_user_order_failure(order, error, retry_count)
            
            logger.error(f"Order {order.id} permanently failed after {retry_count} retries")
            return False

    def _is_transient_error(self, error: Exception) -> bool:
        """Determine if error is transient and retryable.
        
        Args:
            error: Exception to check
            
        Returns:
            True if error is transient, False otherwise
        """
        # Transient errors that should be retried
        transient_indicators = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "unavailable",
            "rate limit",
            "503",
            "504",
        ]
        
        error_str = str(error).lower()
        return any(indicator in error_str for indicator in transient_indicators)

    def _notify_user_order_failure(self, order: Order, error: Exception, retry_count: int) -> None:
        """Send user notification about order failure.
        
        Args:
            order: Failed order
            error: Exception that caused failure
            retry_count: Number of retry attempts made
        """
        # In production, this would send notification via WebSocket to Dashboard
        # For now, we'll log a structured notification message
        notification = {
            "type": "ORDER_FAILURE",
            "severity": "ERROR",
            "timestamp": datetime.now().isoformat(),
            "order_id": order.id,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "error": str(error),
            "retry_count": retry_count,
            "message": f"Order failed: {order.side.value} {order.quantity} {order.symbol} - {str(error)}"
        }
        
        logger.warning(f"USER_NOTIFICATION: {notification}")

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order if found, None otherwise
        """
        return self._orders.get(order_id)

    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID.
        
        Args:
            position_id: Position ID
            
        Returns:
            Position if found, None otherwise
        """
        return self._positions.get(position_id)

    def get_all_orders(self) -> List[Order]:
        """Get all orders.
        
        Returns:
            List of all orders
        """
        return list(self._orders.values())

    def get_all_positions(self) -> List[Position]:
        """Get all positions.
        
        Returns:
            List of all positions
        """
        return list(self._positions.values())

    def get_open_positions(self) -> List[Position]:
        """Get all open positions.
        
        Returns:
            List of open positions
        """
        return [p for p in self._positions.values() if p.closed_at is None]

    def get_pending_orders(self) -> List[Order]:
        """Get all pending orders.
        
        Returns:
            List of pending orders
        """
        return [o for o in self._orders.values() if o.status == OrderStatus.PENDING]

    def get_remaining_quantity(self, order_id: str) -> float:
        """Get remaining unfilled quantity for an order.
        
        Args:
            order_id: Order ID
            
        Returns:
            Remaining quantity (original_quantity - filled_quantity)
            
        Raises:
            OrderExecutionError: If order not found
        """
        order = self._orders.get(order_id)
        if order is None:
            raise OrderExecutionError(f"Order {order_id} not found")
        
        filled_qty = order.filled_quantity or 0.0
        remaining = order.quantity - filled_qty
        
        return max(0.0, remaining)  # Ensure non-negative

    def process_queued_orders(self) -> int:
        """Process orders queued due to market closure.
        
        This method should be called periodically (e.g., every minute) by the trading engine
        or a background scheduler to automatically execute queued orders when their respective
        markets open. The method checks each queued order's market status and submits orders
        for which the market is now open.
        
        **Automatic Execution at Market Open:**
        To implement automatic execution, the trading engine should:
        1. Call this method on a regular schedule (recommended: every 1-5 minutes)
        2. Call this method when receiving market open notifications (if available)
        3. Call this method at known market open times (e.g., 9:30 AM ET for US stocks)
        
        **Example Integration:**
        ```python
        # In trading engine main loop
        while trading_active:
            # ... other trading logic ...
            
            # Process queued orders every minute
            if time_to_check_queue():
                processed = order_executor.process_queued_orders()
                if processed > 0:
                    logger.info(f"Processed {processed} queued orders at market open")
            
            time.sleep(60)  # Check every minute
        ```
        
        **Behavior:**
        - For each queued order, checks if the market is open for that asset class
        - Submits orders for open markets via eToro API
        - Orders that fail submission remain queued for retry
        - Orders for closed markets remain queued
        - Successfully submitted orders are removed from queue
        
        Returns:
            Number of orders successfully processed and submitted
        """
        if not self._queued_orders:
            return 0

        logger.info(f"Processing {len(self._queued_orders)} queued orders")

        processed = 0
        remaining = []

        for order in self._queued_orders:
            asset_class = self._determine_asset_class(order.symbol)
            if self.market_hours.is_market_open(asset_class):
                try:
                    self._submit_order(order)
                    processed += 1
                except OrderExecutionError as e:
                    logger.error(f"Failed to submit queued order {order.id}: {e}")
                    remaining.append(order)
            else:
                remaining.append(order)

        self._queued_orders = remaining
        logger.info(f"Processed {processed} queued orders, {len(remaining)} remaining")

        return processed

    def get_queued_orders_count(self) -> int:
        """Get count of queued orders waiting for market open.

        Returns:
            Number of orders in queue
        """
        return len(self._queued_orders)

    def get_queued_orders(self) -> List[Order]:
        """Get all queued orders.

        Returns:
            List of queued orders
        """
        return list(self._queued_orders)

    def cancel_order(self, order_id: str, reason: str) -> bool:
        """Cancel a pending order.
        
        Args:
            order_id: Order ID to cancel
            reason: Reason for cancellation
            
        Returns:
            True if cancellation successful, False otherwise
            
        Raises:
            OrderExecutionError: If order not found
        """
        order = self._orders.get(order_id)
        if order is None:
            raise OrderExecutionError(f"Order {order_id} not found")
        
        # Can only cancel pending orders
        if order.status != OrderStatus.PENDING:
            logger.warning(f"Cannot cancel order {order_id} with status {order.status.value}")
            return False
        
        logger.info(f"Cancelling order {order_id}: {reason}")
        
        try:
            # If order has eToro order ID, cancel via API
            if order.etoro_order_id:
                success = self.etoro_client.cancel_order(order.etoro_order_id)
                if success:
                    order.status = OrderStatus.CANCELLED
                    logger.info(f"Order {order_id} cancelled successfully via eToro API")
                    return True
                else:
                    logger.warning(f"eToro API returned success=False for order {order_id}")
                    return False
            else:
                # Order not yet submitted to eToro, just mark as cancelled
                order.status = OrderStatus.CANCELLED
                
                # Remove from queued orders if present
                self._queued_orders = [o for o in self._queued_orders if o.id != order_id]
                
                logger.info(f"Order {order_id} cancelled (not yet submitted to eToro)")
                return True
                
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

