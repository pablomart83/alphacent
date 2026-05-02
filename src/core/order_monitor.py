"""Order monitoring system to track and update order status from eToro.

eToro Order Status Codes (statusID):
Based on empirical observation from eToro Demo API testing.

Status 1: Pending/Submitted
    - Order received by eToro, awaiting processing
    
Status 2: Filled/Executed
    - Order successfully executed, position opened
    
Status 3: Executed/Completed
    - Order executed and converted into a position.
    - The response includes a "positions" array with the opened position(s).
    - IMPORTANT: Previously misidentified as "Cancelled". Empirical testing
      (order 329403751) confirmed status 3 with errorCode 0 and a positions
      array means the order was FILLED, not cancelled.
    
Status 4: Failed/Rejected OR Position Closed (context-dependent)
    - WITH errorCode != 0: Order FAILED/REJECTED (e.g., minimum size violation)
    - WITHOUT errorCode: Position closed (different context, not order status)
    - CRITICAL: Always check errorCode field first!
    
Status 7: Executed/Active
    - Position is open and active, errorCode 0 confirms success
    
Status 11: Pending Execution
    - Order submitted but queued for execution
    - Common for small orders or during high volume periods

Error Codes:
    720: Minimum order size violation (minimum $10 for most instruments)

See ETORO_STATUS_CODES_RESEARCH.md for complete documentation.

OPTIMIZATION: This module implements smart caching to reduce eToro API calls:
- Order status cached for 30 seconds
- Positions cached for 60 seconds
- Cache invalidated on state changes (order fills, cancellations)
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict

from sqlalchemy.orm import Session

from src.api.etoro_client import EToroAPIClient, EToroAPIError
from src.models.database import Database
from src.models.enums import OrderStatus, TradingMode
from src.models.orm import OrderORM, PositionORM

logger = logging.getLogger(__name__)


class OrderMonitor:
    """Monitors submitted orders and updates their status from eToro."""

    def __init__(self, etoro_client: EToroAPIClient, db: Optional[Database] = None):
        """Initialize order monitor.
        
        Args:
            etoro_client: eToro API client
            db: Database instance (creates new if not provided)
        """
        self.etoro_client = etoro_client
        self.db = db or Database()
        
        # Cache for order statuses with TTL
        self._order_status_cache = {}  # order_id -> (status_data, timestamp)
        self._cache_ttl = 30  # seconds - cache order status for 30s
        
        # Cache for positions with TTL
        self._positions_cache = None  # (positions_list, timestamp)
        self._positions_cache_ttl = 60  # seconds - cache positions for 60s
        
        # Track last full position sync time
        self._last_full_sync = 0  # timestamp of last full sync
        self._full_sync_interval = 60  # seconds - full sync every 60s (trailing stops need fresh prices)
        
        # Initialize position manager for trailing stops
        from src.execution.position_manager import PositionManager
        from src.models.dataclasses import RiskConfig
        
        # Load risk config from YAML config file, falling back to defaults
        self.risk_config = self._load_risk_config()
        self.position_manager = PositionManager(etoro_client, self.risk_config)
        
        # Track submission attempts per order to prevent infinite retries
        self._submission_attempts: dict = {}  # order_id -> attempt_count
        self._max_submission_attempts = 5
        
        # Consecutive miss counter for position closure safety.
        # A position must be missing from eToro for N consecutive syncs
        # before we close it in DB. Prevents API glitches/outages from
        # mass-closing real positions.
        #
        # Threshold logic:
        #   - New positions (<1h old): 10 misses (~10 min) — eToro propagation can be slow
        #   - Normal positions: 5 misses (~5 min) — enough to survive brief API hiccups
        #   - Long-held positions (>24h): 8 misses (~8 min) — extra caution, these are real
        #
        # You said you won't do manual operations, so any disappearance is either:
        #   (a) eToro SL/TP hit — price will confirm it
        #   (b) Brief API glitch — position reappears next sync
        #   (c) DEMO account reset — mass closure guard catches this
        self._position_miss_count: dict = {}  # etoro_position_id -> consecutive_misses
        self._miss_threshold = 5  # default: 5 consecutive misses (~5 min at 60s sync)

    def _load_risk_config(self):
        """Load risk config from YAML, falling back to dataclass defaults."""
        from src.models.dataclasses import RiskConfig
        try:
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f) or {}
                pm = config.get('position_management', {})
                ts = pm.get('trailing_stops', {})
                pe = pm.get('partial_exits', {})
                return RiskConfig(
                    trailing_stop_enabled=ts.get('enabled', False),
                    trailing_stop_activation_pct=ts.get('activation_pct', 0.05),
                    trailing_stop_distance_pct=ts.get('distance_pct', 0.03),
                    partial_exit_enabled=pe.get('enabled', False),
                )
        except Exception as e:
            logger.warning(f"Could not load risk config from YAML: {e}")
        return RiskConfig()
        
        # Permanent error patterns that should immediately fail an order
        self._permanent_error_patterns = [
            "not in the list of verified tradeable instruments",
            "not tradeable",
            "instrument not found",
            "symbol not available",
            "instrument is not available",
        ]
        
        logger.info("OrderMonitor initialized with caching (order TTL: 30s, position TTL: 60s, full sync: 5min)")

    def _get_order_status_cached(self, order_id: str) -> Optional[dict]:
        """Get order status with caching to reduce eToro API calls.
        
        Args:
            order_id: eToro order ID
            
        Returns:
            Order status data or None if not available
        """
        import time
        
        # Check cache first
        if order_id in self._order_status_cache:
            status_data, timestamp = self._order_status_cache[order_id]
            if time.time() - timestamp < self._cache_ttl:
                logger.debug(f"Order {order_id} status from cache (age: {time.time() - timestamp:.1f}s)")
                return status_data
        
        # Cache miss or expired - query eToro
        try:
            status_data = self.etoro_client.get_order_status(order_id)
            self._order_status_cache[order_id] = (status_data, time.time())
            logger.debug(f"Order {order_id} status from eToro API (cached for {self._cache_ttl}s)")
            return status_data
        except Exception as e:
            logger.error(f"Failed to get order status for {order_id}: {e}")
            return None
    
    def _get_positions_cached(self) -> List:
        """Get positions with caching to reduce eToro API calls.
        
        Returns:
            List of positions
        """
        import time
        
        # Check cache first
        if self._positions_cache is not None:
            positions_list, timestamp = self._positions_cache
            if time.time() - timestamp < self._positions_cache_ttl:
                logger.debug(f"Positions from cache (age: {time.time() - timestamp:.1f}s)")
                return positions_list
        
        # Cache miss or expired - query eToro
        try:
            positions_list = self.etoro_client.get_positions()
            self._positions_cache = (positions_list, time.time())
            logger.debug(f"Positions from eToro API (cached for {self._positions_cache_ttl}s)")
            return positions_list
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def invalidate_order_cache(self, order_id: str):
        """Invalidate cache for a specific order (e.g., after state change).
        
        Args:
            order_id: eToro order ID to invalidate
        """
        if order_id in self._order_status_cache:
            del self._order_status_cache[order_id]
            logger.debug(f"Invalidated cache for order {order_id}")
    
    def invalidate_positions_cache(self):
        """Invalidate positions cache (e.g., after order fill)."""
        self._positions_cache = None
        logger.debug("Invalidated positions cache")

    def _invalidate_all_caches(self):
        """Invalidate all caches (order status + positions).
        
        Used during reconciliation and any operation that requires
        a completely fresh view of eToro state.
        """
        self._order_status_cache.clear()
        self._positions_cache = None
        logger.info("Invalidated all caches (order status + positions)")

    def reconcile_on_startup(self) -> dict:
        """Reconcile DB state with eToro state on startup.

        Force-syncs all positions and orders from eToro immediately (bypassing cache),
        then compares DB state vs eToro state and resolves discrepancies:
        - Positions on eToro but not in DB → create DB records
        - Positions in DB but not on eToro → mark as closed
        - Orders in SUBMITTED state but not on eToro → mark as FAILED

        This MUST be called before signal generation is enabled to prevent
        duplicate signals for symbols that already have positions on eToro.

        Returns:
            Dictionary with reconciliation results
        """
        logger.info("=" * 60)
        logger.info("STARTUP RECONCILIATION: Syncing DB state with eToro")
        logger.info("=" * 60)

        results = {
            "positions_created": 0,
            "positions_closed": 0,
            "positions_updated": 0,
            "orders_failed": 0,
            "discrepancies": [],
        }

        # Invalidate all caches to force fresh data from eToro
        self._invalidate_all_caches()
        self._last_full_sync = 0

        session = self.db.get_session()

        try:
            # --- Step 1: Force-sync positions from eToro (bypass cache) ---
            logger.info("Step 1: Fetching all positions from eToro (bypass cache)...")
            try:
                etoro_positions = self.etoro_client.get_positions()
                logger.info(f"  Found {len(etoro_positions)} positions on eToro")
            except Exception as e:
                logger.error(f"  Failed to fetch positions from eToro: {e}")
                results["error"] = f"Failed to fetch positions: {e}"
                return results

            # Build lookup maps
            from src.utils.symbol_normalizer import normalize_symbol

            etoro_pos_by_id = {}
            for pos in etoro_positions:
                etoro_pos_by_id[pos.etoro_position_id] = pos

            # Get all open positions from DB
            db_open_positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).all()
            db_pos_by_etoro_id = {p.etoro_position_id: p for p in db_open_positions}

            logger.info(f"  Found {len(db_open_positions)} open positions in DB")

            # --- Step 1a: Positions on eToro but not in DB → create DB records ---
            # Also check ALL positions (including closed) to avoid duplicate key violations
            all_db_positions_by_etoro_id = {
                p.etoro_position_id: p
                for p in session.query(PositionORM).filter(
                    PositionORM.etoro_position_id.isnot(None)
                ).all()
            }

            for etoro_id, etoro_pos in etoro_pos_by_id.items():
                if etoro_id not in db_pos_by_etoro_id and etoro_id not in all_db_positions_by_etoro_id:
                    normalized_symbol = normalize_symbol(etoro_pos.symbol)

                    # Try to match to a recent order for strategy_id
                    matched_strategy_id = getattr(etoro_pos, 'strategy_id', 'etoro_position') or 'etoro_position'
                    try:
                        from src.models.enums import OrderSide
                        recent_cutoff = datetime.now() - timedelta(hours=24)
                        matching_orders = session.query(OrderORM).filter(
                            OrderORM.status == OrderStatus.FILLED,
                        ).order_by(OrderORM.filled_at.desc()).limit(50).all()

                        for order in matching_orders:
                            order_symbol = normalize_symbol(order.symbol)
                            if order_symbol == normalized_symbol:
                                matched_strategy_id = order.strategy_id
                                logger.info(f"  Matched orphan position {etoro_id} ({normalized_symbol}) to order strategy: {order.strategy_id}")
                                break
                    except Exception as e:
                        logger.warning(f"  Could not match position to order: {e}")

                    import uuid
                    new_pos = PositionORM(
                        id=str(uuid.uuid4()),
                        strategy_id=matched_strategy_id,
                        symbol=normalized_symbol,
                        side=etoro_pos.side,
                        quantity=etoro_pos.quantity,
                        entry_price=etoro_pos.entry_price,
                        current_price=etoro_pos.current_price,
                        unrealized_pnl=etoro_pos.unrealized_pnl,
                        realized_pnl=etoro_pos.realized_pnl,
                        opened_at=etoro_pos.opened_at,
                        etoro_position_id=etoro_pos.etoro_position_id,
                        stop_loss=etoro_pos.stop_loss,
                        take_profit=etoro_pos.take_profit,
                        closed_at=None,
                    )
                    session.add(new_pos)
                    results["positions_created"] += 1

                    discrepancy = f"CREATED: Position {normalized_symbol} (eToro ID: {etoro_id}) - existed on eToro but not in DB"
                    results["discrepancies"].append(discrepancy)
                    logger.warning(f"  {discrepancy}")

            # --- Step 1b: Positions in DB but not on eToro → mark as closed ---
            # SAFETY GUARD: If eToro returned 0 positions but DB has many open,
            # this is almost certainly an API failure — don't close anything.
            if len(etoro_positions) == 0 and len(db_open_positions) > 3:
                logger.warning(
                    f"SAFETY: eToro returned 0 positions but DB has {len(db_open_positions)} open. "
                    f"Likely API failure — skipping position closure during reconciliation."
                )
                discrepancy = f"SKIPPED: Would have closed {len(db_open_positions)} positions but eToro returned 0 (API failure?)"
                results["discrepancies"].append(discrepancy)
            else:
              for etoro_id, db_pos in db_pos_by_etoro_id.items():
                if etoro_id not in etoro_pos_by_id:
                    db_pos.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    # Calculate realized PnL from price difference
                    entry = db_pos.entry_price or 0
                    current = db_pos.current_price or entry
                    invested = db_pos.invested_amount or db_pos.quantity or 0
                    if entry > 0 and invested > 0:
                        side_str = str(db_pos.side).upper() if db_pos.side else 'LONG'
                        is_long = 'LONG' in side_str or 'BUY' in side_str
                        if not is_long:
                            db_pos.realized_pnl = invested * (entry - current) / entry
                        else:
                            db_pos.realized_pnl = invested * (current - entry) / entry
                    else:
                        db_pos.realized_pnl = db_pos.unrealized_pnl
                    db_pos.unrealized_pnl = 0.0
                    results["positions_closed"] += 1

                    # Infer closure reason from price vs SL/TP
                    closure_reason = "closed_on_etoro"
                    side_str = str(db_pos.side).upper() if db_pos.side else 'LONG'
                    is_long = 'LONG' in side_str or 'BUY' in side_str
                    sl = db_pos.stop_loss
                    tp = db_pos.take_profit

                    # Check 1: Was this position already flagged for closure by our system?
                    # (trailing stop breach, strategy exit signal, retirement, etc.)
                    if db_pos.closure_reason:
                        closure_reason = db_pos.closure_reason
                    elif db_pos.pending_closure:
                        closure_reason = "pending_closure (system-initiated)"
                    else:
                        # Check 2: Was there a recent exit order for this position?
                        try:
                            recent_exit = session.query(OrderORM).filter(
                                OrderORM.strategy_id == db_pos.strategy_id,
                                OrderORM.symbol == db_pos.symbol,
                                OrderORM.order_action == 'exit',
                                OrderORM.submitted_at >= datetime.now() - timedelta(hours=2)
                            ).order_by(OrderORM.submitted_at.desc()).first()
                            if recent_exit:
                                closure_reason = f"exit_signal (order {recent_exit.id[:8]})"
                        except Exception:
                            pass

                        # Check 3: Infer from price vs SL/TP
                        if closure_reason == "closed_on_etoro":
                            if is_long:
                                if tp and current >= tp * 0.995:
                                    closure_reason = f"take_profit_hit (TP={tp:.2f}, price={current:.2f})"
                                elif sl and current <= sl * 1.005:
                                    closure_reason = f"stop_loss_hit (SL={sl:.2f}, price={current:.2f})"
                                else:
                                    closure_reason = f"closed_on_etoro (price={current:.2f}, SL={sl}, TP={tp})"
                            else:
                                if tp and current <= tp * 1.005:
                                    closure_reason = f"take_profit_hit (TP={tp:.2f}, price={current:.2f})"
                                elif sl and current >= sl * 0.995:
                                    closure_reason = f"stop_loss_hit (SL={sl:.2f}, price={current:.2f})"
                                else:
                                    closure_reason = f"closed_on_etoro (price={current:.2f}, SL={sl}, TP={tp})"

                    db_pos.closure_reason = closure_reason

                    # Log to trade journal
                    try:
                        from src.analytics.trade_journal import TradeJournal
                        journal = TradeJournal(self.db)
                        journal.log_exit(
                            trade_id=str(db_pos.id),
                            exit_time=db_pos.closed_at,
                            exit_price=db_pos.current_price,
                            exit_reason=closure_reason,
                            symbol=db_pos.symbol,
                        )
                    except Exception as journal_err:
                        logger.debug(f"Could not log exit to trade journal for {db_pos.symbol}: {journal_err}")

                    discrepancy = f"CLOSED: {db_pos.symbol} (eToro ID: {etoro_id}) — {closure_reason}"
                    results["discrepancies"].append(discrepancy)
                    logger.warning(f"  {discrepancy}")

            # --- Step 1c: Update existing positions with fresh eToro data ---
            for etoro_id, db_pos in db_pos_by_etoro_id.items():
                if etoro_id in etoro_pos_by_id:
                    etoro_pos = etoro_pos_by_id[etoro_id]
                    db_pos.current_price = etoro_pos.current_price
                    db_pos.unrealized_pnl = etoro_pos.unrealized_pnl
                    
                    # Preserve trailing stop: eToro doesn't support modifying SL on
                    # open positions, so it always reports the original SL. Our trailing
                    # stop system ratchets the DB stop_loss up (for longs) or down (for
                    # shorts). Don't overwrite a better trailing stop with eToro's stale value.
                    etoro_sl = etoro_pos.stop_loss
                    db_sl = db_pos.stop_loss
                    if etoro_sl is not None and db_sl is not None:
                        side_str = str(db_pos.side).upper() if db_pos.side else 'LONG'
                        is_long = 'LONG' in side_str or 'BUY' in side_str
                        if is_long and db_sl > etoro_sl:
                            # DB has a higher (better) trailing stop for long — keep it
                            pass
                        elif not is_long and db_sl < etoro_sl:
                            # DB has a lower (better) trailing stop for short — keep it
                            pass
                        else:
                            db_pos.stop_loss = etoro_sl
                    elif etoro_sl is not None:
                        # No DB stop yet — use eToro's
                        db_pos.stop_loss = etoro_sl
                    # If etoro_sl is None but db_sl exists, keep db_sl (trailing stop set)
                    
                    db_pos.take_profit = etoro_pos.take_profit
                    # Fix symbol normalization if needed
                    normalized = normalize_symbol(etoro_pos.symbol)
                    if db_pos.symbol != normalized:
                        db_pos.symbol = normalized
                    results["positions_updated"] += 1

            # --- Step 2: Reconcile SUBMITTED orders ---
            logger.info("Step 2: Reconciling orders sent to eToro...")
            submitted_orders = session.query(OrderORM).filter(
                OrderORM.status == OrderStatus.PENDING,
                OrderORM.etoro_order_id.isnot(None)
            ).all()

            logger.info(f"  Found {len(submitted_orders)} orders sent to eToro in DB")

            for order in submitted_orders:
                if order.etoro_order_id:
                    # Check if order still exists on eToro
                    try:
                        status_data = self.etoro_client.get_order_status(order.etoro_order_id)
                        etoro_status = status_data.get("statusID") or status_data.get("status")
                        error_code = status_data.get("errorCode")

                        if error_code and error_code != 0:
                            # Order failed on eToro
                            order.status = OrderStatus.FAILED
                            results["orders_failed"] += 1
                            discrepancy = f"FAILED: Order {order.id} ({order.symbol}) - eToro error {error_code}"
                            results["discrepancies"].append(discrepancy)
                            logger.warning(f"  {discrepancy}")
                        elif etoro_status in [2, 3, 7]:
                            # Order was filled - let normal check_submitted_orders handle position creation
                            logger.info(f"  Order {order.id} ({order.symbol}) appears filled on eToro (status {etoro_status})")
                        else:
                            logger.debug(f"  Order {order.id} ({order.symbol}) still pending (status {etoro_status})")
                    except EToroAPIError:
                        # Cannot verify order status — 404 or CID mismatch after a
                        # session rotation. This does NOT mean the order is invalid.
                        # It may be a legitimately queued order waiting for market open.
                        # Leave it PENDING so check_submitted_orders keeps polling it
                        # on the normal cycle. cancel_stale_orders will handle it if
                        # it genuinely ages out (>24h with no fill).
                        logger.warning(
                            f"  Could not verify order {order.id} ({order.symbol}) "
                            f"eToro={order.etoro_order_id} — leaving PENDING "
                            f"(session/CID mismatch, not a reason to cancel)"
                        )
                else:
                    # SUBMITTED order with no eToro ID - likely stale from a crash
                    age = datetime.now() - (order.submitted_at or datetime.now())
                    if age.total_seconds() > 300:  # older than 5 minutes
                        order.status = OrderStatus.FAILED
                        results["orders_failed"] += 1
                        discrepancy = f"FAILED: Order {order.id} ({order.symbol}) - no eToro ID, age {age.total_seconds():.0f}s"
                        results["discrepancies"].append(discrepancy)
                        logger.warning(f"  {discrepancy}")

            session.commit()

            # Update sync timestamp so regular sync doesn't immediately re-run
            self._last_full_sync = time.time()

            # Cache the fresh positions
            self._positions_cache = (etoro_positions, time.time())

            # --- Summary ---
            logger.info("=" * 60)
            logger.info("STARTUP RECONCILIATION COMPLETE")
            logger.info(f"  Positions created: {results['positions_created']}")
            logger.info(f"  Positions closed:  {results['positions_closed']}")
            logger.info(f"  Positions updated: {results['positions_updated']}")
            logger.info(f"  Orders failed:     {results['orders_failed']}")
            if results["discrepancies"]:
                logger.info(f"  Total discrepancies resolved: {len(results['discrepancies'])}")
            else:
                logger.info("  No discrepancies found - DB and eToro are in sync")
            logger.info("=" * 60)

            return results

        except Exception as e:
            logger.error(f"Error during startup reconciliation: {e}", exc_info=True)
            session.rollback()
            results["error"] = str(e)
            return results

        finally:
            session.close()


    def process_pending_orders(self) -> dict:
        """Process pending orders and submit them to eToro.

        Includes:
        - Permanent instrument error detection (immediate FAILED)
        - Submission attempt tracking with max retry limit
        - One-time cleanup for known stale orders

        Returns:
            Dictionary with counts of processed orders
        """
        session = self.db.get_session()

        try:
            # Get pending orders that have NOT been submitted to eToro yet
            pending_orders = session.query(OrderORM).filter(
                OrderORM.status == OrderStatus.PENDING,
                OrderORM.etoro_order_id.is_(None)  # Only orders not yet submitted to eToro
            ).all()

            if not pending_orders:
                logger.debug("No pending orders to process")
                return {"checked": 0, "submitted": 0, "failed": 0}

            logger.info(f"Processing {len(pending_orders)} pending orders")

            submitted_count = 0
            failed_count = 0

            for order in pending_orders:
                order_id = str(order.id)

                # Check if max submission attempts exceeded
                attempts = self._submission_attempts.get(order_id, 0)
                if attempts >= self._max_submission_attempts:
                    logger.warning(
                        f"Order {order.id} ({order.symbol}) exceeded max submission attempts "
                        f"({self._max_submission_attempts}). Marking as FAILED."
                    )
                    order.status = OrderStatus.FAILED
                    failed_count += 1
                    # Clean up tracking
                    self._submission_attempts.pop(order_id, None)
                    continue

                try:
                    logger.info(f"Submitting order {order.id}: {order.side.value} {order.quantity} {order.symbol} (attempt {attempts + 1})")

                    # Submit to eToro
                    response = self.etoro_client.place_order(
                        symbol=order.symbol,
                        side=order.side,
                        order_type=order.order_type,
                        quantity=order.quantity,
                        price=order.price,
                        stop_price=order.stop_price,
                        take_profit_price=getattr(order, 'take_profit_price', None)
                    )

                    # Update order with eToro response
                    etoro_oid = response.get("order_id")
                    if etoro_oid:
                        order.etoro_order_id = str(etoro_oid)
                    else:
                        # eToro accepted the order but didn't return an ID
                        # (common for queued orders when market is closed)
                        # Use a placeholder so process_pending_orders won't resubmit
                        order.etoro_order_id = f"pending_{order.id}"
                        logger.warning(
                            f"Order {order.id} ({order.symbol}) accepted by eToro but no order ID returned. "
                            f"Using placeholder ID. Raw response: {response.get('raw_response', {}).get('orderForOpen', {})}"
                        )
                    order.status = OrderStatus.PENDING
                    order.submitted_at = datetime.now(timezone.utc).replace(tzinfo=None)

                    submitted_count += 1
                    # Reset attempts on success
                    self._submission_attempts.pop(order_id, None)
                    logger.info(f"Order {order.id} submitted successfully, eToro order ID: {order.etoro_order_id}")

                except Exception as e:
                    error_msg = str(e).lower()

                    # Check for permanent instrument errors — fail immediately
                    is_permanent_error = any(
                        pattern in error_msg for pattern in self._permanent_error_patterns
                    )

                    if is_permanent_error:
                        logger.error(
                            f"Order {order.id} ({order.symbol}) failed with permanent instrument error: {e}. "
                            f"Marking as FAILED immediately."
                        )
                        order.status = OrderStatus.FAILED
                        failed_count += 1
                        self._submission_attempts.pop(order_id, None)
                    else:
                        # Transient error — increment attempt counter
                        self._submission_attempts[order_id] = attempts + 1
                        logger.error(
                            f"Failed to submit order {order.id} (attempt {attempts + 1}/{self._max_submission_attempts}): {e}"
                        )
                        failed_count += 1

            # Commit all changes
            session.commit()

            result = {
                "checked": len(pending_orders),
                "submitted": submitted_count,
                "failed": failed_count
            }

            if submitted_count > 0:
                logger.info(f"Pending order processing complete: {result}")

            return result

        except Exception as e:
            logger.error(f"Error in process_pending_orders: {e}")
            session.rollback()
            return {"checked": 0, "submitted": 0, "failed": 0, "error": str(e)}

        finally:
            session.close()

    def check_submitted_orders(self) -> dict:
        """Check status of all submitted orders and update database.
        
        When an order is marked as FILLED, this method also creates or updates
        the corresponding position with the correct strategy_id from the order.
        
        Returns:
            Dictionary with counts of updated orders
        """
        session = self.db.get_session()
        
        try:
            # Get all pending orders that have been sent to eToro (have etoro_order_id)
            submitted_orders = session.query(OrderORM).filter(
                OrderORM.status == OrderStatus.PENDING,
                OrderORM.etoro_order_id.isnot(None)
            ).all()
            
            if not submitted_orders:
                logger.debug("No submitted orders to check")
                return {"checked": 0, "filled": 0, "cancelled": 0, "failed": 0}
            
            logger.info(f"Checking status of {len(submitted_orders)} submitted orders")
            
            filled_count = 0
            cancelled_count = 0
            failed_count = 0
            positions_created = 0
            
            # Get current positions from eToro to match orders (with caching)
            try:
                etoro_positions = self._get_positions_cached()
                # Map by etoro_position_id for quick lookup
                position_map = {pos.etoro_position_id: pos for pos in etoro_positions}
            except Exception as e:
                logger.error(f"Failed to fetch positions: {e}")
                etoro_positions = []
                position_map = {}
            
            for order in submitted_orders:
                try:
                    order_filled = False
                    etoro_position_id = None

                    # Skip placeholder IDs — these orders were accepted by eToro
                    # but we don't have a real order ID to check status
                    if order.etoro_order_id and order.etoro_order_id.startswith("pending_"):
                        logger.debug(f"Order {order.id} has placeholder eToro ID — checking positions for match")
                        # Try to find a matching position by symbol
                        from src.utils.symbol_normalizer import normalize_symbol
                        normalized_symbol = normalize_symbol(order.symbol)
                        for pos in etoro_positions:
                            if normalize_symbol(pos.symbol) == normalized_symbol:
                                # Found a position — order was filled
                                order.status = OrderStatus.FILLED
                                order.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
                                order.filled_quantity = order.quantity
                                order.filled_price = getattr(pos, 'entry_price', None) or getattr(pos, 'open_rate', None)
                                order.etoro_order_id = f"matched_{pos.etoro_position_id}"
                                filled_count += 1
                                self.invalidate_positions_cache()
                                logger.info(f"Order {order.id} with placeholder ID matched to position {pos.etoro_position_id}")
                                order_filled = True
                                etoro_position_id = str(pos.etoro_position_id)
                                break
                        if not order_filled:
                            # Still pending — market probably still closed
                            logger.debug(f"Order {order.id} ({order.symbol}) still pending (placeholder ID, no matching position)")
                        continue
                    
                    # If order has eToro order ID, check its status (with caching)
                    if order.etoro_order_id:
                        try:
                            status_data = self._get_order_status_cached(order.etoro_order_id)
                            
                            if not status_data:
                                # Failed to get status, skip this order
                                continue
                            
                            # Parse status from response
                            etoro_status = status_data.get("statusID") or status_data.get("status")
                            error_code = status_data.get("errorCode")
                            error_message = status_data.get("errorMessage")
                            
                            if etoro_status:
                                logger.debug(f"Order {order.id} (eToro: {order.etoro_order_id}) status: {etoro_status}, errorCode: {error_code}")
                                
                                # CRITICAL: Check for errors first
                                # Status 4 with errorCode != 0 means FAILED/REJECTED
                                if error_code and error_code != 0:
                                    logger.error(f"Order {order.id} failed with error {error_code}: {error_message}")
                                    order.status = OrderStatus.FAILED
                                    failed_count += 1
                                    # Invalidate order cache on state change
                                    self.invalidate_order_cache(order.etoro_order_id)
                                    continue
                                
                                # Update based on statusID
                                # Based on empirical observation from eToro Demo API:
                                # 1 = Pending/Submitted (order received, awaiting processing)
                                # 2 = Filled/Executed (order completed, position opened)
                                # 3 = Executed/Completed (order executed, positions array present)
                                # 4 = Failed/Rejected (when errorCode != 0) OR Position Closed (when errorCode == 0, different context)
                                # 7 = Executed/Active (position is open and active, errorCode 0 confirms success)
                                # 11 = Pending Execution (order submitted but queued for execution)
                                
                                # Status 3: Check if positions were opened (means FILLED, not cancelled)
                                has_positions = bool(status_data.get("positions"))
                                
                                if etoro_status in [2, 7, "filled", "FILLED", "executed", "EXECUTED"]:
                                    order.status = OrderStatus.FILLED
                                    order.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
                                    order.filled_quantity = order.quantity
                                    # Try to get filled_price from positions in status data
                                    status_positions = status_data.get("positions", [])
                                    if status_positions and isinstance(status_positions, list):
                                        order.filled_price = status_positions[0].get("open_rate") or status_positions[0].get("entry_price")
                                    order_filled = True
                                    filled_count += 1
                                    # Invalidate caches on state change
                                    self.invalidate_order_cache(order.etoro_order_id)
                                    self.invalidate_positions_cache()
                                    logger.info(f"Order {order.id} marked as FILLED (eToro status: {etoro_status})")
                                elif etoro_status in [3]:
                                    # Status 3 with positions array = order executed successfully
                                    if has_positions:
                                        order.status = OrderStatus.FILLED
                                        order.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
                                        order.filled_quantity = order.quantity
                                        # Get filled_price from positions data
                                        pos_list = status_data.get("positions", [])
                                        if pos_list and isinstance(pos_list, list):
                                            order.filled_price = pos_list[0].get("open_rate") or pos_list[0].get("entry_price")
                                        order_filled = True
                                        filled_count += 1
                                        # Invalidate caches on state change
                                        self.invalidate_order_cache(order.etoro_order_id)
                                        self.invalidate_positions_cache()
                                        # Extract position IDs from response
                                        positions_data = status_data.get("positions", [])
                                        if positions_data:
                                            etoro_position_id = str(positions_data[0].get("positionID"))
                                        pos_ids = [str(p.get("positionID")) for p in positions_data]
                                        logger.info(f"Order {order.id} marked as FILLED (eToro status 3 with positions: {pos_ids})")
                                    else:
                                        # Status 3 without positions = genuinely cancelled
                                        order.status = OrderStatus.CANCELLED
                                        cancelled_count += 1
                                        self.invalidate_order_cache(order.etoro_order_id)
                                        self.invalidate_positions_cache()
                                        logger.info(f"Order {order.id} marked as CANCELLED (eToro status 3, no positions)")
                                elif etoro_status in ["cancelled", "CANCELLED"]:
                                    order.status = OrderStatus.CANCELLED
                                    cancelled_count += 1
                                    self.invalidate_order_cache(order.etoro_order_id)
                                    self.invalidate_positions_cache()
                                    logger.info(f"Order {order.id} marked as CANCELLED")
                                elif etoro_status in [1, 11, "pending", "PENDING"]:
                                    # Order is still pending execution
                                    logger.debug(f"Order {order.id} still pending (status {etoro_status})")
                                elif etoro_status == 4:
                                    # Status 4 without error code - unclear meaning, log for investigation
                                    logger.warning(f"Order {order.id} has status 4 without error code - may indicate position closed")
                                else:
                                    # Unknown status - log for future documentation
                                    logger.warning(f"Order {order.id} has unknown status: {etoro_status}")
                        
                        except EToroAPIError as e:
                            # Order status endpoint might not be available
                            logger.debug(f"Could not get status for order {order.etoro_order_id}: {e}")
                    
                    # For orders without eToro ID, check if a position was created
                    # Market orders often execute immediately without returning an order ID
                    else:
                        # Check if this order is old (more than 10 seconds)
                        if order.submitted_at:
                            # Ensure both datetimes are timezone-naive for comparison
                            current_time = datetime.now(timezone.utc).replace(tzinfo=None)
                            submitted_at = order.submitted_at.replace(tzinfo=None) if order.submitted_at.tzinfo else order.submitted_at
                            age_seconds = (current_time - submitted_at).total_seconds()
                            
                            # If order is old and still no eToro ID, likely executed immediately
                            if age_seconds > 10:
                                logger.info(f"Order {order.id} is {age_seconds:.1f} seconds old with no eToro ID")
                                logger.info(f"Assuming market order executed immediately - marking as FILLED")
                                order.status = OrderStatus.FILLED
                                order.filled_at = datetime.now(timezone.utc).replace(tzinfo=None)
                                order.filled_quantity = order.quantity
                                order.filled_price = order.expected_price  # Best available price for assumed fills
                                order_filled = True
                                # Invalidate positions cache since we have a new position
                                self.invalidate_positions_cache()
                    
                    # CRITICAL FIX: When order is filled, create/update position with correct strategy_id
                    if order_filled:
                        # Calculate slippage and fill time
                        if order.expected_price and order.filled_price:
                            order.slippage = order.filled_price - order.expected_price
                            logger.debug(f"Order {order.id} slippage: {order.slippage:.4f}")
                        
                        if order.submitted_at and order.filled_at:
                            order.fill_time_seconds = (order.filled_at - order.submitted_at).total_seconds()
                            logger.debug(f"Order {order.id} fill time: {order.fill_time_seconds:.1f}s")
                        
                        # Try to find the corresponding eToro position with retry logic
                        etoro_pos = None
                        max_retries = 3
                        retry_delays = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s
                        
                        for attempt in range(max_retries):
                            if attempt > 0:
                                # Wait before retry
                                import time
                                delay = retry_delays[attempt - 1]
                                logger.info(f"Retrying position lookup for order {order.id} (attempt {attempt + 1}/{max_retries}) after {delay}s")
                                time.sleep(delay)
                                # Invalidate cache and fetch fresh positions
                                self.invalidate_positions_cache()
                                etoro_positions = self._get_positions_cached()
                                position_map = {pos.etoro_position_id: pos for pos in etoro_positions}
                        
                            # Import symbol normalizer for comparison
                            from src.utils.symbol_normalizer import normalize_symbol
                            normalized_order_symbol = normalize_symbol(order.symbol)
                            
                            # Method 1: Use etoro_position_id from status response
                            if etoro_position_id and etoro_position_id in position_map:
                                etoro_pos = position_map[etoro_position_id]
                                logger.info(f"Found eToro position {etoro_position_id} for order {order.id} (attempt {attempt + 1})")
                                break
                            
                            # Method 2: Match by symbol and recent timestamp (within 60 seconds)
                            if not etoro_pos:
                                for pos in etoro_positions:
                                    # Normalize both symbols for comparison
                                    normalized_pos_symbol = normalize_symbol(pos.symbol)
                                    
                                    if normalized_pos_symbol == normalized_order_symbol:
                                        # Check if position was opened recently (within 60 seconds of order fill)
                                        # Try multiple timestamp comparisons
                                        time_match = False
                                        
                                        # Normalize datetimes to timezone-naive for comparison
                                        def normalize_dt(dt):
                                            if dt is None:
                                                return None
                                            return dt.replace(tzinfo=None) if dt.tzinfo else dt
                                        
                                        filled_at_naive = normalize_dt(order.filled_at)
                                        submitted_at_naive = normalize_dt(order.submitted_at)
                                        opened_at_naive = normalize_dt(pos.opened_at)
                                        
                                        if filled_at_naive and opened_at_naive:
                                            time_diff = abs((filled_at_naive - opened_at_naive).total_seconds())
                                            if time_diff < 60:
                                                time_match = True
                                        elif submitted_at_naive and opened_at_naive:
                                            # Fallback: compare with submitted_at
                                            time_diff = abs((submitted_at_naive - opened_at_naive).total_seconds())
                                            if time_diff < 120:  # Allow 2 minutes for submitted orders
                                                time_match = True
                                        elif not pos.opened_at:
                                            # If position has no opened_at, assume it's recent
                                            time_match = True
                                        
                                        if time_match:
                                            etoro_pos = pos
                                            logger.info(f"Matched order {order.id} ({order.symbol}) to position {pos.etoro_position_id} ({pos.symbol}) by normalized symbol and timestamp (attempt {attempt + 1})")
                                            break
                            
                            # Method 3: Match by symbol and quantity (last resort)
                            if not etoro_pos:
                                for pos in etoro_positions:
                                    normalized_pos_symbol = normalize_symbol(pos.symbol)
                                    
                                    if normalized_pos_symbol == normalized_order_symbol:
                                        # Check if quantity matches (within 1% tolerance for rounding)
                                        if abs(pos.quantity - order.quantity) / order.quantity < 0.01:
                                            etoro_pos = pos
                                            logger.info(f"Matched order {order.id} ({order.symbol}) to position {pos.etoro_position_id} ({pos.symbol}) by normalized symbol and quantity (attempt {attempt + 1})")
                                            break
                            
                            # If found, break retry loop
                            if etoro_pos:
                                break
                        
                        # Create or update position in database
                        if etoro_pos:
                            # Backfill filled_price from matched position if not already set
                            if not order.filled_price and hasattr(etoro_pos, 'entry_price') and etoro_pos.entry_price:
                                order.filled_price = etoro_pos.entry_price
                            elif not order.filled_price and hasattr(etoro_pos, 'open_rate') and etoro_pos.open_rate:
                                order.filled_price = etoro_pos.open_rate
                            
                            # Check if position already exists in DB
                            existing_pos = session.query(PositionORM).filter_by(
                                etoro_position_id=etoro_pos.etoro_position_id
                            ).first()
                            
                            if existing_pos:
                                # Update strategy_id if it's the default "etoro_position"
                                if existing_pos.strategy_id == "etoro_position":
                                    existing_pos.strategy_id = order.strategy_id
                                    logger.info(f"Updated position {existing_pos.id} strategy_id from 'etoro_position' to '{order.strategy_id}'")
                                # Also update current prices
                                existing_pos.current_price = etoro_pos.current_price
                                existing_pos.unrealized_pnl = etoro_pos.unrealized_pnl
                            else:
                                # Before creating new position, check if one already exists for this symbol
                                existing_symbol_pos = session.query(PositionORM).filter(
                                    PositionORM.symbol == order.symbol,
                                    PositionORM.closed_at.is_(None)
                                ).first()

                                if existing_symbol_pos:
                                    # Update existing position instead of creating duplicate
                                    if existing_symbol_pos.strategy_id == "etoro_position":
                                        existing_symbol_pos.strategy_id = order.strategy_id
                                    existing_symbol_pos.etoro_position_id = etoro_pos.etoro_position_id
                                    existing_symbol_pos.current_price = etoro_pos.current_price
                                    existing_symbol_pos.unrealized_pnl = etoro_pos.unrealized_pnl
                                    logger.info(f"Updated existing position {existing_symbol_pos.id} for {order.symbol} instead of creating duplicate")
                                else:
                                    # STRONGER DEDUP: Check if ANY open position exists for this symbol+side
                                    # This prevents duplicates even when etoro_position_id doesn't match
                                    from src.models.enums import OrderSide as OrderSideEnum
                                    from src.models.enums import PositionSide
                                    pos_side = PositionSide.LONG if order.side == OrderSideEnum.BUY else PositionSide.SHORT
                                    existing_same_side = session.query(PositionORM).filter(
                                        PositionORM.symbol == order.symbol,
                                        PositionORM.side == pos_side,
                                        PositionORM.closed_at.is_(None),
                                    ).first()
                                    
                                    if existing_same_side:
                                        # Update existing position instead of creating duplicate
                                        existing_same_side.etoro_position_id = etoro_pos.etoro_position_id
                                        existing_same_side.current_price = etoro_pos.current_price
                                        existing_same_side.unrealized_pnl = etoro_pos.unrealized_pnl
                                        if existing_same_side.strategy_id == "etoro_position":
                                            existing_same_side.strategy_id = order.strategy_id
                                        logger.info(
                                            f"DEDUP: Updated existing {order.symbol} position {existing_same_side.id} "
                                            f"(etoro_id: {existing_same_side.etoro_position_id} → {etoro_pos.etoro_position_id}) "
                                            f"instead of creating duplicate"
                                        )
                                        positions_created += 1
                                    else:
                                        # Create new position with correct strategy_id
                                        import uuid
                                    
                                        new_pos = PositionORM(
                                            id=str(uuid.uuid4()),
                                            strategy_id=order.strategy_id,  # Use strategy_id from order
                                            symbol=order.symbol,  # ✅ Use our consistent symbol, not eToro's internal ID
                                            side=etoro_pos.side,
                                            quantity=etoro_pos.quantity,
                                            entry_price=etoro_pos.entry_price,
                                            current_price=etoro_pos.current_price,
                                            unrealized_pnl=etoro_pos.unrealized_pnl,
                                            realized_pnl=etoro_pos.realized_pnl,
                                            opened_at=etoro_pos.opened_at,
                                            etoro_position_id=etoro_pos.etoro_position_id,
                                            stop_loss=etoro_pos.stop_loss or order.stop_price,
                                            take_profit=etoro_pos.take_profit or order.take_profit_price,
                                            closed_at=None
                                        )
                                        session.add(new_pos)
                                        positions_created += 1
                                        logger.info(f"Created position {new_pos.id} for order {order.id} with strategy_id '{order.strategy_id}'")
                        else:
                            # Before warning, check if sync_positions already created/matched
                            # a position for this strategy+symbol — if so, this is a false alarm.
                            existing_for_strategy = session.query(PositionORM).filter(
                                PositionORM.strategy_id == order.strategy_id,
                                PositionORM.symbol == order.symbol,
                                PositionORM.closed_at.is_(None),
                            ).first()
                            if existing_for_strategy:
                                logger.info(
                                    f"Order {order.id} ({order.symbol}): eToro position not found in "
                                    f"live list but DB position {existing_for_strategy.id} already exists "
                                    f"(etoro_id: {existing_for_strategy.etoro_position_id}) — sync_positions handled it"
                                )
                            else:
                                logger.warning(f"Could not find eToro position for filled order {order.id} (symbol: {order.symbol})")
                        
                        # Log to trade journal for analytics tracking.
                        # Pull regime/conviction/fundamentals from the persisted order
                        # metadata so async fills still capture signal-time context.
                        try:
                            from src.analytics.trade_journal import TradeJournal
                            journal = TradeJournal(self.db)

                            _meta = order.order_metadata if isinstance(order.order_metadata, dict) else {}
                            _regime = _meta.get("market_regime")
                            _conviction = _meta.get("conviction_score")
                            _ml_conf = _meta.get("ml_confidence")
                            _fundamentals = _meta.get("fundamentals")
                            _sector = _meta.get("sector")

                            journal.log_entry(
                                trade_id=order.id,
                                strategy_id=order.strategy_id,
                                symbol=order.symbol,
                                entry_time=datetime.now(),
                                entry_price=order.filled_price or order.expected_price or 0,
                                entry_size=order.filled_quantity or order.quantity or 0,
                                entry_reason=f"Signal filled via eToro (order {order.etoro_order_id})",
                                entry_order_id=str(order.etoro_order_id) if order.etoro_order_id else None,
                                market_regime=_regime,
                                sector=_sector,
                                fundamentals=_fundamentals,
                                conviction_score=_conviction,
                                ml_confidence=_ml_conf,
                                expected_price=order.expected_price,
                                order_side=order.side.value if hasattr(order.side, 'value') else str(order.side),
                                metadata={
                                    "etoro_order_id": order.etoro_order_id,
                                    "fill_time_seconds": order.fill_time_seconds,
                                    "source": "order_monitor",
                                    **({k: v for k, v in _meta.items() if k not in ("market_regime", "conviction_score", "ml_confidence", "fundamentals", "sector")}),
                                },
                            )
                            logger.info(
                                f"Logged trade journal entry for order {order.id} ({order.symbol}) "
                                f"regime={_regime or 'unknown'} conviction={_conviction}"
                            )
                        except Exception as journal_err:
                            logger.warning(f"Could not log to trade journal for order {order.id}: {journal_err}")
                
                except Exception as e:
                    logger.error(f"Error checking order {order.id}: {e}")
                    failed_count += 1
            
            # Commit all changes
            session.commit()
            
            result = {
                "checked": len(submitted_orders),
                "filled": filled_count,
                "cancelled": cancelled_count,
                "failed": failed_count,
                "positions_created": positions_created
            }
            
            if filled_count > 0 or cancelled_count > 0:
                logger.info(f"Order status update complete: {result}")
            
            return result
        
        except Exception as e:
            logger.error(f"Error in check_submitted_orders: {e}")
            session.rollback()
            return {"checked": 0, "filled": 0, "cancelled": 0, "failed": 0, "error": str(e)}
        
        finally:
            session.close()

    def sync_positions(self, force: bool = False) -> dict:
        """Sync positions from eToro to database (with smart caching).
        
        Only performs full sync when:
        1. force=True (e.g., after order fills)
        2. More than 5 minutes since last full sync
        
        Syncs in both directions:
        - Updates/creates positions that exist on eToro
        - Closes positions that no longer exist on eToro
        
        Args:
            force: Force full sync regardless of cache
            
        Returns:
            Dictionary with counts of synced positions
        """
        import time
        
        # Check if we need a full sync
        time_since_sync = time.time() - self._last_full_sync
        needs_sync = force or time_since_sync >= self._full_sync_interval
        
        if not needs_sync:
            logger.debug(f"Skipping position sync (last sync {time_since_sync:.0f}s ago, next in {self._full_sync_interval - time_since_sync:.0f}s)")
            return {"total": 0, "updated": 0, "created": 0, "skipped": True}
        
        # Fetch eToro positions BEFORE opening DB session.
        # The API call can take 10-30s (network + enriching 125 positions with
        # live prices). Holding a DB session open during that time blocks all
        # other writers (signal generation, trade journal, monitoring).
        try:
            positions = self._get_positions_cached()
        except Exception as e:
            logger.error(f"Failed to fetch positions from eToro: {e}")
            return {"total": 0, "updated": 0, "created": 0, "error": str(e)}
        
        logger.info(f"Syncing {len(positions)} positions from eToro (forced={force})")
        
        session = self.db.get_session()
        
        try:
            
            updated_count = 0
            created_count = 0
            reopened_count = 0
            closed_count = 0
            
            # Import symbol normalizer
            from src.utils.symbol_normalizer import normalize_symbol
            
            # Build set of eToro position IDs for quick lookup — normalize to string
            # to avoid int/str mismatches between eToro API response and DB values.
            etoro_position_ids = {str(pos.etoro_position_id) for pos in positions}
            
            # Track price updates for WebSocket broadcasting after commit
            _price_updates: Dict[str, float] = {}
            
            # BATCH: Load ALL existing positions in ONE query instead of per-position lookups.
            # With 125 positions, this saves 124 round-trips to PostgreSQL.
            all_db_positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).all()
            db_by_etoro_id = {str(p.etoro_position_id): p for p in all_db_positions}
            db_by_id = {p.id: p for p in all_db_positions}
            # Index by (strategy_id, symbol, side) for strategy-match lookups
            db_by_strategy_symbol = {}
            for p in all_db_positions:
                side_str = str(p.side).upper() if p.side else 'LONG'
                key = (p.strategy_id, p.symbol, side_str)
                db_by_strategy_symbol[key] = p

            # Build a set of ALL etoro_position_ids (open AND closed) to prevent
            # UniqueViolation when trying to assign an ID already held by a closed row.
            all_etoro_ids_in_db: set = set(
                str(row[0]) for row in session.query(PositionORM.etoro_position_id)
                .filter(PositionORM.etoro_position_id.isnot(None)).all()
            )
            
            # Update/create positions that exist on eToro
            for pos in positions:
                # Normalize the symbol from eToro (e.g., ID_1017 -> GE)
                normalized_symbol = normalize_symbol(pos.symbol)
                
                # Check if position exists — use pre-loaded dict instead of per-query
                existing_pos = db_by_etoro_id.get(str(pos.etoro_position_id))
                
                if existing_pos:
                    # Update existing position - preserve strategy_id
                    # (eToro doesn't know about our strategy IDs, so don't overwrite)
                    # BUT update symbol to our normalized version
                    existing_pos.symbol = normalized_symbol  # Use normalized symbol, not eToro's ID
                    existing_pos.current_price = pos.current_price
                    existing_pos.unrealized_pnl = pos.unrealized_pnl
                    
                    # Track for WebSocket broadcast
                    if pos.current_price:
                        _price_updates[normalized_symbol] = pos.current_price
                    
                    # Preserve trailing stop: eToro doesn't support modifying SL on
                    # open positions, so it always reports the original SL. Our trailing
                    # stop system ratchets the DB stop_loss up (for longs) or down (for
                    # shorts). Don't overwrite a better trailing stop with eToro's stale value.
                    etoro_sl = pos.stop_loss
                    db_sl = existing_pos.stop_loss
                    if etoro_sl is not None and db_sl is not None:
                        side_str = str(existing_pos.side).upper() if existing_pos.side else 'LONG'
                        is_long = 'LONG' in side_str or 'BUY' in side_str
                        if is_long and db_sl > etoro_sl:
                            pass  # DB has better trailing stop for long — keep it
                        elif not is_long and db_sl < etoro_sl:
                            pass  # DB has better trailing stop for short — keep it
                        else:
                            existing_pos.stop_loss = etoro_sl
                    elif etoro_sl is not None:
                        existing_pos.stop_loss = etoro_sl
                    # If etoro_sl is None but db_sl exists, keep db_sl
                    
                    existing_pos.take_profit = pos.take_profit
                    
                    # Update invested_amount if available from eToro
                    if pos.invested_amount:
                        existing_pos.invested_amount = pos.invested_amount
                    
                    # CRITICAL: If position is marked as closed in DB but open on eToro, reopen it.
                    # BUT: only reopen if there's no closure_reason — a closure_reason means
                    # our system intentionally closed it (SL hit, race condition duplicate,
                    # strategy retired, time-based exit, etc.). In that case, the eToro position
                    # is still open because the close order hasn't filled yet — don't fight it.
                    if existing_pos.closed_at is not None:
                        if existing_pos.closure_reason:
                            logger.debug(
                                f"Position {existing_pos.id} ({normalized_symbol}) closed in DB "
                                f"with reason '{existing_pos.closure_reason}' — not reopening "
                                f"(close order pending on eToro)"
                            )
                        else:
                            logger.info(
                                f"Reopening position {existing_pos.id} ({normalized_symbol}) "
                                f"— eToro ID {pos.etoro_position_id} exists on eToro but was closed in DB"
                            )
                            existing_pos.closed_at = None
                            reopened_count += 1
                    
                    updated_count += 1
                    logger.debug(f"Updated position {existing_pos.id} (strategy: {existing_pos.strategy_id}, symbol: {normalized_symbol})")
                else:
                    # Try to match this new position to a recent order to get the correct strategy_id.
                    # CRITICAL: Match by eToro order ID first (most reliable), then by symbol+side+time.
                    # When multiple strategies trade the same symbol, symbol-only matching picks the wrong one.
                    matched_strategy_id = pos.strategy_id  # Default: "etoro_position"
                    matched_order_id = None
                    try:
                        from src.models.enums import OrderSide
                        
                        # First: try to match by eToro order ID if available on the position
                        etoro_pos_id = pos.etoro_position_id
                        
                        # Look for a recently filled order matching this symbol
                        recent_cutoff = datetime.now() - timedelta(hours=2)
                        matching_orders = session.query(OrderORM).filter(
                            OrderORM.status == OrderStatus.FILLED,
                            OrderORM.filled_at >= recent_cutoff
                        ).order_by(OrderORM.filled_at.desc()).all()
                        
                        for order in matching_orders:
                            order_symbol = normalize_symbol(order.symbol)
                            if order_symbol == normalized_symbol:
                                # Skip close orders — they shouldn't match new positions
                                if getattr(order, 'order_action', None) == 'close':
                                    continue
                                # Check if the order side matches the position side
                                order_is_buy = order.side == OrderSide.BUY
                                pos_is_long = pos.side.value == 'LONG' if hasattr(pos.side, 'value') else str(pos.side) == 'LONG'
                                
                                if (order_is_buy and pos_is_long) or (not order_is_buy and not pos_is_long):
                                    # Use pre-loaded dict instead of per-query
                                    pos_side_str = 'LONG' if pos_is_long else 'SHORT'
                                    already_has = db_by_strategy_symbol.get(
                                        (order.strategy_id, normalized_symbol, pos_side_str)
                                    )
                                
                                    if not already_has:
                                        matched_strategy_id = order.strategy_id
                                        matched_order_id = order.id
                                        logger.info(
                                            f"Matched new eToro position {pos.etoro_position_id} ({normalized_symbol}) "
                                            f"to order {order.id} (strategy: {order.strategy_id})"
                                        )
                                        break
                                    else:
                                        logger.debug(
                                            f"Skipping order {order.id} for {normalized_symbol} — "
                                            f"strategy {order.strategy_id} already has open position"
                                        )
                    except Exception as e:
                        logger.warning(f"Could not match position to order: {e}")
                    
                    from src.models.enums import PositionSide
                    existing_by_strategy = None
                    if matched_strategy_id and matched_strategy_id != pos.strategy_id:
                        pos_side_str = str(pos.side).upper() if pos.side else 'LONG'
                        if hasattr(pos.side, 'value'):
                            pos_side_str = pos.side.value.upper()
                        existing_by_strategy = db_by_strategy_symbol.get(
                            (matched_strategy_id, normalized_symbol, pos_side_str)
                        )
                    
                    if not existing_by_strategy:
                        # Also check for unattributed positions (strategy_id = "etoro_position")
                        pos_side_str = str(pos.side).upper() if pos.side else 'LONG'
                        if hasattr(pos.side, 'value'):
                            pos_side_str = pos.side.value.upper()
                        existing_by_strategy = db_by_strategy_symbol.get(
                            ("etoro_position", normalized_symbol, pos_side_str)
                        )

                    if existing_by_strategy:
                        # Position already exists for this strategy+symbol — update etoro_position_id
                        # BUT: only update if no other row (open or closed) already holds this eToro ID.
                        # If a closed duplicate holds it, skip the ID update to avoid UniqueViolation.
                        new_etoro_id = pos.etoro_position_id
                        id_already_taken = (
                            str(new_etoro_id) in all_etoro_ids_in_db
                            and str(new_etoro_id) != str(existing_by_strategy.etoro_position_id)
                        )
                        if id_already_taken:
                            logger.debug(
                                f"Skipping etoro_position_id update for {normalized_symbol} "
                                f"(id: {existing_by_strategy.id}) — ID {new_etoro_id} already held "
                                f"by another row (closed duplicate pending eToro close)"
                            )
                        else:
                            logger.info(
                                f"Position already exists for {normalized_symbol} (id: {existing_by_strategy.id}, "
                                f"strategy: {existing_by_strategy.strategy_id}). Updating etoro_position_id from "
                                f"'{existing_by_strategy.etoro_position_id}' to '{new_etoro_id}'"
                            )
                            existing_by_strategy.etoro_position_id = new_etoro_id
                        existing_by_strategy.current_price = pos.current_price
                        existing_by_strategy.unrealized_pnl = pos.unrealized_pnl
                        
                        # Preserve trailing stop (same logic as main sync path)
                        etoro_sl = pos.stop_loss
                        db_sl = existing_by_strategy.stop_loss
                        if etoro_sl is not None and db_sl is not None:
                            side_str = str(existing_by_strategy.side).upper() if existing_by_strategy.side else 'LONG'
                            is_long = 'LONG' in side_str or 'BUY' in side_str
                            if is_long and db_sl > etoro_sl:
                                pass
                            elif not is_long and db_sl < etoro_sl:
                                pass
                            else:
                                existing_by_strategy.stop_loss = etoro_sl
                        elif etoro_sl is not None:
                            existing_by_strategy.stop_loss = etoro_sl
                        
                        existing_by_strategy.take_profit = pos.take_profit
                        if pos.invested_amount:
                            existing_by_strategy.invested_amount = pos.invested_amount
                        updated_count += 1
                        continue  # Don't create a new position

                    # Create new position with matched strategy_id
                    # Safety check: verify no position with this ID already exists
                    # (can happen if etoro_position_id changed format between syncs)
                    existing_by_id = db_by_id.get(pos.id)
                    if existing_by_id:
                        logger.info(
                            f"Position {pos.id} ({normalized_symbol}) already exists in DB "
                            f"(etoro_id mismatch: DB={existing_by_id.etoro_position_id}, "
                            f"eToro={pos.etoro_position_id}). Updating instead of creating."
                        )
                        existing_by_id.etoro_position_id = pos.etoro_position_id
                        existing_by_id.current_price = pos.current_price
                        existing_by_id.unrealized_pnl = pos.unrealized_pnl
                        if pos.stop_loss is not None:
                            # Preserve trailing stop logic
                            db_sl = existing_by_id.stop_loss
                            if db_sl is not None:
                                side_str = str(existing_by_id.side).upper() if existing_by_id.side else 'LONG'
                                is_long = 'LONG' in side_str or 'BUY' in side_str
                                if not (is_long and db_sl > pos.stop_loss) and not (not is_long and db_sl < pos.stop_loss):
                                    existing_by_id.stop_loss = pos.stop_loss
                            else:
                                existing_by_id.stop_loss = pos.stop_loss
                        existing_by_id.take_profit = pos.take_profit
                        if pos.invested_amount:
                            existing_by_id.invested_amount = pos.invested_amount
                        updated_count += 1
                        continue

                    # Final safety: check if a CLOSED position with this etoro_position_id exists
                    # (the main lookup only checks open positions — a closed one causes UniqueViolation)
                    closed_dup = session.query(PositionORM).filter(
                        PositionORM.etoro_position_id == pos.etoro_position_id,
                        PositionORM.closed_at.isnot(None),
                    ).first()
                    if closed_dup:
                        # Reopen the closed position instead of creating a duplicate —
                        # BUT only if it was closed without a reason (sync artifact).
                        # If it has a closure_reason, our system intentionally closed it;
                        # the eToro position is still open because the close order is pending.
                        if closed_dup.closure_reason:
                            logger.debug(
                                f"Skipping reopen of {closed_dup.id} ({normalized_symbol}) — "
                                f"closed with reason '{closed_dup.closure_reason}' (close order pending)"
                            )
                            continue
                        logger.info(
                            f"Reopening closed position {closed_dup.id} ({normalized_symbol}) — "
                            f"eToro ID {pos.etoro_position_id} exists on eToro but was closed in DB"
                        )
                        closed_dup.closed_at = None
                        closed_dup.current_price = pos.current_price
                        closed_dup.unrealized_pnl = pos.unrealized_pnl
                        closed_dup.entry_price = pos.entry_price
                        if pos.stop_loss is not None:
                            closed_dup.stop_loss = pos.stop_loss
                        if pos.take_profit is not None:
                            closed_dup.take_profit = pos.take_profit
                        if pos.invested_amount:
                            closed_dup.invested_amount = pos.invested_amount
                        if matched_strategy_id and matched_strategy_id != 'etoro_position':
                            closed_dup.strategy_id = matched_strategy_id
                        updated_count += 1
                        continue

                    # SAFETY: Validate position side against strategy direction.
                    # If a strategy is "long" only, don't create a SHORT position for it.
                    # This prevents phantom positions from close-order race conditions
                    # (e.g., eToro interprets a close SELL as opening a new SHORT).
                    pos_side_str = pos.side.value.upper() if hasattr(pos.side, 'value') else str(pos.side).upper()
                    if matched_strategy_id and matched_strategy_id != 'etoro_position':
                        try:
                            from src.models.orm import StrategyORM as _StrategyORM_check
                            strategy_orm = session.query(_StrategyORM_check).filter_by(id=matched_strategy_id).first()
                            if strategy_orm and strategy_orm.strategy_metadata:
                                strategy_direction = (strategy_orm.strategy_metadata.get('direction', '') or '').lower()
                                if strategy_direction == 'long' and 'SHORT' in pos_side_str:
                                    logger.warning(
                                        f"REJECTED phantom position: {normalized_symbol} {pos_side_str} "
                                        f"from eToro ID {pos.etoro_position_id} — strategy "
                                        f"'{strategy_orm.name}' is direction=long. "
                                        f"Likely a close-order race condition. Skipping."
                                    )
                                    continue
                                elif strategy_direction == 'short' and 'LONG' in pos_side_str:
                                    logger.warning(
                                        f"REJECTED phantom position: {normalized_symbol} {pos_side_str} "
                                        f"from eToro ID {pos.etoro_position_id} — strategy "
                                        f"'{strategy_orm.name}' is direction=short. "
                                        f"Likely a close-order race condition. Skipping."
                                    )
                                    continue
                        except Exception as e:
                            logger.debug(f"Could not validate strategy direction for {matched_strategy_id}: {e}")

                    new_pos = PositionORM(
                        id=pos.id,
                        strategy_id=matched_strategy_id,
                        symbol=normalized_symbol,
                        side=pos.side,
                        quantity=pos.quantity,
                        entry_price=pos.entry_price,
                        current_price=pos.current_price,
                        unrealized_pnl=pos.unrealized_pnl,
                        realized_pnl=pos.realized_pnl,
                        opened_at=pos.opened_at,
                        etoro_position_id=pos.etoro_position_id,
                        stop_loss=pos.stop_loss,
                        take_profit=pos.take_profit,
                        closed_at=pos.closed_at,
                        invested_amount=pos.invested_amount,
                    )
                    session.add(new_pos)
                    created_count += 1
                    logger.info(f"Created new position from eToro: {normalized_symbol} {pos_side_str} (eToro ID: {pos.etoro_position_id})")
                    # Update in-memory dicts so subsequent iterations in this same sync
                    # cycle don't treat this newly created position as missing and try
                    # to create it again (or skip a different position that should be created).
                    db_by_etoro_id[str(pos.etoro_position_id)] = new_pos
                    db_by_strategy_symbol[(matched_strategy_id, normalized_symbol, pos_side_str)] = new_pos
                    all_etoro_ids_in_db.add(str(pos.etoro_position_id))
            
            # Close positions that are open in DB but no longer exist on eToro
            open_db_positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).all()
            
            # SAFETY GUARD: If eToro returned 0 positions but we have many open in DB,
            # this is almost certainly an API failure — don't even count misses.
            if len(positions) == 0 and len(open_db_positions) > 3:
                logger.warning(
                    f"SAFETY: eToro returned 0 positions but DB has {len(open_db_positions)} open. "
                    f"Likely API failure — skipping closure check entirely."
                )
            else:
                # Track which positions are present on eToro this sync
                seen_this_sync = set()
                
                for db_pos in open_db_positions:
                    pos_key = str(db_pos.etoro_position_id)
                    
                    if pos_key in etoro_position_ids:
                        # Position found on eToro — reset miss counter
                        self._position_miss_count.pop(pos_key, None)
                        seen_this_sync.add(pos_key)
                        continue
                    
                    # Position missing from eToro — increment miss counter
                    
                    # Skip very new positions (eToro propagation delay)
                    if db_pos.opened_at:
                        try:
                            opened_naive = db_pos.opened_at.replace(tzinfo=None) if db_pos.opened_at.tzinfo else db_pos.opened_at
                            age_seconds = (datetime.now().replace(tzinfo=None) - opened_naive).total_seconds()
                        except Exception:
                            age_seconds = 999
                        if age_seconds < 120:
                            continue
                    
                    misses = self._position_miss_count.get(pos_key, 0) + 1
                    self._position_miss_count[pos_key] = misses

                    # Dynamic threshold based on position age:
                    # - Very new (<1h): 10 misses — eToro propagation delay is real
                    # - Long-held (>24h): 8 misses — extra caution, these are established positions
                    # - Normal: 5 misses (default)
                    dynamic_threshold = self._miss_threshold
                    if db_pos.opened_at:
                        try:
                            opened_naive = db_pos.opened_at.replace(tzinfo=None) if db_pos.opened_at.tzinfo else db_pos.opened_at
                            age_hours = (datetime.now().replace(tzinfo=None) - opened_naive).total_seconds() / 3600
                            if age_hours < 1.0:
                                dynamic_threshold = 10  # Very new — wait longer
                            elif age_hours > 24.0:
                                dynamic_threshold = 8   # Long-held — extra caution
                        except Exception:
                            pass

                    if misses < dynamic_threshold:
                        logger.info(
                            f"Position {db_pos.symbol} (eToro: {pos_key}) missing from eToro "
                            f"({misses}/{dynamic_threshold} consecutive misses — not closing yet)"
                        )
                        continue
                    
                    # Position confirmed gone after N consecutive misses — close it
                    logger.warning(
                        f"Closing position {db_pos.id} ({db_pos.symbol}) — "
                        f"not found on eToro (etoro_id: {db_pos.etoro_position_id})"
                    )
                    db_pos.closed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    # Calculate realized PnL from price difference (not stale unrealized_pnl).
                    # unrealized_pnl may be stale if price enrichment hasn't run recently.
                    # Use: invested_amount * (close_price - entry_price) / entry_price for LONG
                    #      invested_amount * (entry_price - close_price) / entry_price for SHORT
                    entry = db_pos.entry_price or 0
                    current = db_pos.current_price or entry
                    invested = db_pos.invested_amount or db_pos.quantity or 0
                    if entry > 0 and invested > 0:
                        side_str = str(db_pos.side).upper() if db_pos.side else 'LONG'
                        if 'SHORT' in side_str or 'SELL' in side_str:
                            calculated_pnl = invested * (entry - current) / entry
                        else:
                            calculated_pnl = invested * (current - entry) / entry
                        db_pos.realized_pnl = calculated_pnl
                    else:
                        db_pos.realized_pnl = db_pos.unrealized_pnl or 0.0
                    db_pos.unrealized_pnl = 0.0
                    closed_count += 1
                    
                    # Determine exit reason by fetching the LIVE market price.
                    # The stale current_price from last sync can be minutes old.
                    # A fresh price tells us definitively whether SL/TP was breached.
                    sl = db_pos.stop_loss or 0
                    tp = db_pos.take_profit or 0
                    side_str = str(db_pos.side).upper() if db_pos.side else 'LONG'
                    is_long = 'LONG' in side_str or 'BUY' in side_str
                    exit_reason = "etoro_closed"
                    
                    # Fetch live price for this instrument
                    live_price = current  # fallback to last synced price
                    try:
                        md = self.etoro_client.get_market_data(db_pos.symbol)
                        if md and md.close and md.close > 0:
                            live_price = md.close
                            # Also update the close price on the position for accurate P&L
                            db_pos.current_price = live_price
                            if entry > 0 and invested > 0:
                                if 'SHORT' in side_str or 'SELL' in side_str:
                                    db_pos.realized_pnl = invested * (entry - live_price) / entry
                                else:
                                    db_pos.realized_pnl = invested * (live_price - entry) / entry
                            logger.info(
                                f"Fetched live price for closed {db_pos.symbol}: "
                                f"${live_price:.2f} (was ${current:.2f})"
                            )
                    except Exception as _price_err:
                        logger.debug(f"Could not fetch live price for {db_pos.symbol}: {_price_err}")
                    
                    # Determine reason from live price vs SL/TP.
                    # Three checks, in order of confidence:
                    # 1. Live price currently past SL/TP → definitive
                    # 2. P&L loss is within the SL range → SL fired, price bounced back
                    # 3. P&L gain is within the TP range → TP fired, price pulled back
                    if tp > 0:
                        if is_long and live_price >= tp:
                            exit_reason = "take_profit_hit"
                        elif not is_long and live_price <= tp:
                            exit_reason = "take_profit_hit"
                    if exit_reason == "etoro_closed" and sl > 0:
                        if is_long and live_price <= sl:
                            exit_reason = "stop_loss_hit"
                        elif not is_long and live_price >= sl:
                            exit_reason = "stop_loss_hit"
                    
                    # Check 2: P&L-based detection. If the position lost money and
                    # the loss % is within the SL distance, the SL almost certainly
                    # fired — the price just bounced back by the time we checked.
                    # e.g., SL at -5%, position closed at -4.4% → SL hit, price recovered slightly.
                    if exit_reason == "etoro_closed" and sl > 0 and entry > 0:
                        if is_long:
                            sl_pct = (entry - sl) / entry  # e.g., 0.05 for 5% SL
                            loss_pct = (entry - live_price) / entry  # positive when losing
                        else:
                            sl_pct = (sl - entry) / entry
                            loss_pct = (live_price - entry) / entry
                        # If we lost money and the loss is >= 50% of the SL distance, it's a SL hit
                        if loss_pct > 0 and sl_pct > 0 and loss_pct >= sl_pct * 0.5:
                            exit_reason = "stop_loss_hit"
                        # Similarly for TP
                        if exit_reason == "etoro_closed" and tp > 0:
                            if is_long:
                                tp_pct = (tp - entry) / entry
                                gain_pct = (live_price - entry) / entry
                            else:
                                tp_pct = (entry - tp) / entry
                                gain_pct = (entry - live_price) / entry
                            if gain_pct > 0 and tp_pct > 0 and gain_pct >= tp_pct * 0.5:
                                exit_reason = "take_profit_hit"
                    
                    db_pos.closure_reason = exit_reason.replace("_", " ").title()
                    
                    # Log to trade journal
                    try:
                        from src.analytics.trade_journal import TradeJournal
                        journal = TradeJournal(self.db)
                        
                        # Ensure entry exists in journal (may be missing for sync-created positions)
                        journal.log_entry(
                            trade_id=str(db_pos.id),
                            strategy_id=db_pos.strategy_id or "unknown",
                            symbol=db_pos.symbol,
                            entry_time=db_pos.opened_at or db_pos.closed_at,
                            entry_price=db_pos.entry_price or 0,
                            entry_size=db_pos.invested_amount or db_pos.quantity or 0,
                            entry_reason="autonomous_signal",
                            order_side="BUY" if is_long else "SELL",
                        )
                        journal.log_exit(
                            trade_id=str(db_pos.id),
                            exit_time=db_pos.closed_at,
                            exit_price=db_pos.current_price,
                            exit_reason=exit_reason,
                            symbol=db_pos.symbol,
                        )
                    except Exception as journal_err:
                        logger.debug(f"Could not log exit to trade journal for {db_pos.symbol}: {journal_err}")
                    
                    # If position had $0 P&L and was very recent, likely a phantom
                    # from an async eToro rejection. Fail the order and demote strategy.
                    is_phantom = (db_pos.realized_pnl == 0.0 and db_pos.opened_at and
                                  (datetime.now().replace(tzinfo=None) - 
                                   (db_pos.opened_at.replace(tzinfo=None) if db_pos.opened_at.tzinfo else db_pos.opened_at)
                                  ).total_seconds() < 600)  # Less than 10 minutes old
                    if is_phantom and db_pos.strategy_id:
                        try:
                            from src.models.enums import OrderStatus as _OrderStatus, StrategyStatus as _StrategyStatus
                            # Fail the associated order
                            recent_order = session.query(OrderORM).filter(
                                OrderORM.strategy_id == db_pos.strategy_id,
                                OrderORM.symbol == db_pos.symbol,
                                OrderORM.status == _OrderStatus.FILLED,
                            ).order_by(OrderORM.submitted_at.desc()).first()
                            if recent_order:
                                recent_order.status = _OrderStatus.FAILED
                                logger.warning(f"Marked order {recent_order.id} ({db_pos.symbol}) as FAILED — phantom position")
                            
                            # Demote strategy if it has no other real positions
                            from src.models.orm import StrategyORM
                            strategy = session.query(StrategyORM).filter(StrategyORM.id == db_pos.strategy_id).first()
                            if strategy and strategy.status == _StrategyStatus.DEMO:
                                other_open = session.query(PositionORM).filter(
                                    PositionORM.strategy_id == db_pos.strategy_id,
                                    PositionORM.closed_at.is_(None),
                                    PositionORM.id != db_pos.id,
                                ).count()
                                if other_open == 0:
                                    strategy.status = _StrategyStatus.BACKTESTED
                                    if isinstance(strategy.strategy_metadata, dict):
                                        strategy.strategy_metadata['activation_approved'] = True
                                    strategy.activated_at = None
                                    logger.warning(f"Demoted {strategy.name} DEMO → BACKTESTED (phantom position, will re-trigger)")
                        except Exception as cleanup_err:
                            logger.warning(f"Phantom cleanup error: {cleanup_err}")
                    
                    # Position closed — remove from miss counter
                    self._position_miss_count.pop(pos_key, None)
                
                # Clean up miss counter for positions no longer in DB
                active_keys = {p.etoro_position_id for p in open_db_positions}
                stale = [k for k in self._position_miss_count if k not in active_keys]
                for k in stale:
                    del self._position_miss_count[k]
            
            try:
                session.commit()
            except Exception as commit_err:
                session.rollback()
                if 'unique' in str(commit_err).lower():
                    logger.warning(f"UniqueViolation during position sync — will retry next cycle: {commit_err}")
                else:
                    raise
            
            # Update last sync time
            self._last_full_sync = time.time()
            
            # Broadcast price updates via WebSocket (fire-and-forget)
            if _price_updates:
                try:
                    import asyncio
                    from src.api.websocket_manager import get_websocket_manager
                    ws = get_websocket_manager()
                    if ws:
                        for sym, price in _price_updates.items():
                            data = {
                                "symbol": sym,
                                "price": price,
                                "timestamp": datetime.now().isoformat(),
                            }
                            try:
                                loop = asyncio.get_running_loop()
                                asyncio.ensure_future(
                                    ws.broadcast_market_data_update(sym, data), loop=loop
                                )
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                loop.run_until_complete(
                                    ws.broadcast_market_data_update(sym, data)
                                )
                                loop.close()
                except Exception:
                    pass  # Fire-and-forget — never block position sync
            
            result = {
                "total": len(positions),
                "updated": updated_count,
                "created": created_count,
                "reopened": reopened_count,
                "closed": closed_count
            }
            
            logger.info(f"Position sync complete: {result}")
            return result
        
        except Exception as e:
            logger.error(f"Error syncing positions: {e}")
            session.rollback()
            return {"total": 0, "updated": 0, "created": 0, "error": str(e)}
        
        finally:
            session.close()

    def run_monitoring_cycle(self) -> dict:
        """Run a complete monitoring cycle: process pending orders, check submitted orders, sync positions, and check trailing stops.
        
        Returns:
            Dictionary with results from all operations
        """
        logger.info("Running order monitoring cycle")
        
        pending_results = self.process_pending_orders()
        order_results = self.check_submitted_orders()
        
        # Only force position sync if orders were filled (new positions created)
        force_sync = order_results.get("filled", 0) > 0
        position_results = self.sync_positions(force=force_sync)
        
        # Check trailing stops for all open positions
        trailing_stop_results = {"updated": 0, "error": None}
        try:
            # Get all open positions from database
            session = self.db.get_session()
            try:
                open_positions_orm = session.query(PositionORM).filter(
                    PositionORM.closed_at.is_(None)
                ).all()
                
                # Convert ORM to dataclass
                from src.models.dataclasses import Position
                from src.models.enums import PositionSide
                
                open_positions = []
                for pos_orm in open_positions_orm:
                    pos = Position(
                        id=pos_orm.id,
                        strategy_id=pos_orm.strategy_id,
                        symbol=pos_orm.symbol,
                        side=pos_orm.side,
                        quantity=pos_orm.quantity,
                        entry_price=pos_orm.entry_price,
                        current_price=pos_orm.current_price,
                        unrealized_pnl=pos_orm.unrealized_pnl,
                        realized_pnl=pos_orm.realized_pnl,
                        opened_at=pos_orm.opened_at,
                        etoro_position_id=pos_orm.etoro_position_id,
                        stop_loss=pos_orm.stop_loss,
                        take_profit=pos_orm.take_profit,
                        closed_at=pos_orm.closed_at
                    )
                    open_positions.append(pos)
                
                # Check trailing stops
                self.position_manager.check_trailing_stops(open_positions)
                
                # Update database with new stop-loss values
                for pos in open_positions:
                    pos_orm = session.query(PositionORM).filter_by(id=pos.id).first()
                    if pos_orm and pos_orm.stop_loss != pos.stop_loss:
                        pos_orm.stop_loss = pos.stop_loss
                        trailing_stop_results["updated"] += 1
                
                session.commit()
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error checking trailing stops: {e}")
            trailing_stop_results["error"] = str(e)
        
        # Cancel stale orders
        cancellation_results = self.cancel_stale_orders()
        
        return {
            "pending": pending_results,
            "orders": order_results,
            "positions": position_results,
            "trailing_stops": trailing_stop_results,
            "cancellations": cancellation_results
        }

    def cancel_stale_orders(self, max_age_hours: int = 24, pending_timeout_hours: int = None, submitted_timeout_hours: int = None) -> dict:
        """Cancel orders that have been pending for too long.

        Market-hours-aware: orders submitted outside market hours (after 4pm ET,
        weekends) are legitimately queued for the next open. These are only
        cancelled after 72h (covers a full weekend + buffer), not the standard
        24h timeout. Orders submitted during market hours use the standard timeout.

        Args:
            max_age_hours: Default maximum age in hours (used if specific timeout not set)
            pending_timeout_hours: Timeout for PENDING orders (default: max_age_hours)
            submitted_timeout_hours: Deprecated, ignored (kept for backward compatibility)

        Returns:
            Dictionary with counts of cancelled orders
        """
        pending_timeout = pending_timeout_hours or max_age_hours
        # Orders submitted outside market hours get a longer grace period —
        # they're queued for the next open, not stuck.
        AFTER_HOURS_TIMEOUT = 72  # hours — covers full weekend

        session = self.db.get_session()

        try:
            from datetime import timedelta
            import pytz

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            pending_cutoff = now - timedelta(hours=pending_timeout)

            # Query all PENDING orders older than the standard timeout
            candidates = session.query(OrderORM).filter(
                OrderORM.status == OrderStatus.PENDING,
                OrderORM.submitted_at < pending_cutoff
            ).all()

            # Filter: skip orders submitted outside market hours unless they've
            # exceeded the extended after-hours timeout.
            stale_orders = []
            after_hours_cutoff = now - timedelta(hours=AFTER_HOURS_TIMEOUT)
            try:
                et_tz = pytz.timezone('US/Eastern')
            except Exception:
                et_tz = None

            for order in candidates:
                submitted_at = order.submitted_at.replace(tzinfo=None) if order.submitted_at and order.submitted_at.tzinfo else (order.submitted_at or now)
                age_hours = (now - submitted_at).total_seconds() / 3600

                # Determine if order was submitted during market hours
                submitted_during_market_hours = True
                if et_tz:
                    try:
                        submitted_et = submitted_at.replace(tzinfo=pytz.utc).astimezone(et_tz)
                        weekday = submitted_et.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
                        hour = submitted_et.hour + submitted_et.minute / 60.0
                        # Market hours: Mon-Fri 9:30am–4:00pm ET
                        is_weekday = weekday < 5
                        is_market_hours = is_weekday and 9.5 <= hour <= 16.0
                        submitted_during_market_hours = is_market_hours
                    except Exception:
                        pass  # assume market hours if check fails

                if submitted_during_market_hours:
                    # Standard timeout applies
                    stale_orders.append(order)
                elif submitted_at < after_hours_cutoff:
                    # After-hours order exceeded extended timeout — genuinely stuck
                    logger.info(
                        f"After-hours order {order.id} ({order.symbol}) aged out "
                        f"({age_hours:.1f}h > {AFTER_HOURS_TIMEOUT}h extended timeout)"
                    )
                    stale_orders.append(order)
                else:
                    logger.debug(
                        f"Skipping after-hours order {order.id} ({order.symbol}) "
                        f"age={age_hours:.1f}h — within {AFTER_HOURS_TIMEOUT}h grace period"
                    )

            if not stale_orders:
                logger.debug(f"No stale orders found (PENDING>{pending_timeout}h, after-hours grace applied)")
                return {"checked": len(candidates), "cancelled_pending": 0, "cancelled": 0, "failed": 0}

            logger.info(
                f"Found {len(stale_orders)} stale orders to cancel "
                f"({len(candidates)} candidates, {len(candidates)-len(stale_orders)} skipped as after-hours)"
            )

            cancelled_pending = 0
            failed_count = 0

            for order in stale_orders:
                try:
                    # Calculate order age
                    submitted_at = order.submitted_at.replace(tzinfo=None) if order.submitted_at.tzinfo else order.submitted_at
                    age_hours = (now - submitted_at).total_seconds() / 3600

                    reason = f"Stale order timeout (status: PENDING, age: {age_hours:.1f}h, limit: {pending_timeout}h)"

                    # Cancel via eToro API if order has eToro ID
                    if order.etoro_order_id:
                        try:
                            success = self.etoro_client.cancel_order(order.etoro_order_id)
                            if success:
                                order.status = OrderStatus.CANCELLED
                                cancelled_pending += 1
                                logger.info(
                                    f"Cancelled stale order {order.id} "
                                    f"(eToro: {order.etoro_order_id}, symbol: {order.symbol}, "
                                    f"strategy: {order.strategy_id}): {reason}"
                                )
                            else:
                                logger.warning(f"Failed to cancel stale order {order.id}: eToro API returned False")
                                failed_count += 1
                        except Exception as e:
                            logger.error(f"Failed to cancel stale order {order.id} via eToro API: {e}")
                            # Still mark as cancelled in our system
                            order.status = OrderStatus.CANCELLED
                            cancelled_pending += 1
                            logger.info(f"Marked stale order {order.id} as cancelled despite API error")
                    else:
                        # Order not yet submitted to eToro, just mark as cancelled
                        order.status = OrderStatus.CANCELLED
                        cancelled_pending += 1
                        logger.info(
                            f"Cancelled stale order {order.id} "
                            f"(symbol: {order.symbol}, strategy: {order.strategy_id}, "
                            f"not submitted to eToro): {reason}"
                        )

                except Exception as e:
                    logger.error(f"Error cancelling stale order {order.id}: {e}")
                    failed_count += 1

            # Commit all changes
            session.commit()

            total_cancelled = cancelled_pending
            result = {
                "checked": len(stale_orders),
                "cancelled_pending": cancelled_pending,
                "cancelled": total_cancelled,
                "failed": failed_count
            }

            if total_cancelled > 0:
                logger.info(f"Stale order cleanup complete: {result}")

            return result

        except Exception as e:
            logger.error(f"Error in cancel_stale_orders: {e}")
            session.rollback()
            return {"checked": 0, "cancelled_pending": 0, "cancelled_submitted": 0, "cancelled": 0, "failed": 0, "error": str(e)}

        finally:
            session.close()
