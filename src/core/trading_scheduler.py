"""
Trading scheduler for autonomous signal generation and execution.

Runs background tasks when system is in ACTIVE state.

OPTIMIZATION: Implements tiered scheduling to reduce eToro API calls:
- Fast cycle (5s): Trailing stop checks (database only, no API calls)
- Medium cycle (30s): Order status checks (with 30s cache)
- Medium cycle (60s): Position sync (with 60s cache)
- Slow cycle (300s): Signal generation (fetches historical data)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List

from src.core.system_state_manager import get_system_state_manager
from src.models.enums import SystemStateEnum, StrategyStatus

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Background scheduler for autonomous trading operations.
    
    Runs two types of cycles:
    - Fast cycle (every 5s): Order monitoring, position sync
    - Signal cycle (every 300s): Signal generation from strategies (fetches years of data)
    """
    
    def __init__(
        self,
        signal_generation_interval: int = 3600,  # 1 hour — matches default_interval: 1h data
    ):
        """
        Initialize trading scheduler.
        
        Args:
            signal_generation_interval: Seconds between signal generation runs (default 3600 = 1 hour)
        """
        self.signal_generation_interval = signal_generation_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_signal_check: float = 0  # timestamp of last signal generation
        
        # Cached components (initialized on first cycle)
        self._etoro_client = None
        self._market_data = None
        self._strategy_engine = None
        self._risk_manager = None
        self._order_executor = None
        self._websocket_manager = None
        self._components_initialized = False
        self._reconciliation_done = False  # Block signals until startup reconciliation completes
        
        logger.info(
            f"TradingScheduler initialized (signal generation: {signal_generation_interval}s) - "
            f"Monitoring handled by MonitoringService"
        )
    
    async def start(self):
        """Start the trading scheduler."""
        if self._running:
            logger.warning("Trading scheduler already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Trading scheduler started")
    
    async def stop(self):
        """Stop the trading scheduler."""
        if not self._running:
            logger.warning("Trading scheduler not running")
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Trading scheduler stopped")
    
    async def _run_loop(self):
        """Main scheduler loop.
        
        Runs signal generation once per hour, triggered by the monitoring
        service's background price sync completing. Manual syncs from the
        Data Management page do NOT trigger signal generation — only the
        automatic hourly background sync does.
        
        Flow each hour:
        1. MonitoringService._sync_price_data() runs automatically (~every 55 min)
        2. Sets _background_sync_completed = True (distinct from manual sync flag)
        3. This loop detects it and runs signal generation immediately
        4. Enforces minimum 55-minute gap between signal generation runs
        """
        import time as _time
        logger.info("Trading scheduler loop started")
        
        # Run reconciliation immediately on startup (no wait)
        if not self._reconciliation_done:
            try:
                state_manager = get_system_state_manager()
                current_state = state_manager.get_current_state()
                if current_state.state == SystemStateEnum.ACTIVE:
                    await self._run_trading_cycle()
            except Exception as e:
                logger.error(f"Startup reconciliation cycle failed: {e}", exc_info=True)
        
        last_signal_run = _time.time()  # Track when we last ran signal gen
        MIN_GAP_SECONDS = 3300  # 55 minutes minimum between runs
        
        while self._running:
            try:
                # Wait until the next hour boundary, checking for sync completion
                sync_detected = False
                max_wait = 4200  # 70 minutes max wait
                waited = 0
                
                while self._running and waited < max_wait:
                    # Enforce minimum gap — don't even check the flag if too soon
                    elapsed_since_last = _time.time() - last_signal_run
                    if elapsed_since_last < MIN_GAP_SECONDS:
                        remaining = MIN_GAP_SECONDS - elapsed_since_last
                        sleep_time = min(remaining, 30)
                        await asyncio.sleep(sleep_time)
                        waited += sleep_time
                        continue
                    
                    # Check if background sync completed (NOT manual sync)
                    try:
                        from src.core.monitoring_service import get_monitoring_service
                        mon = get_monitoring_service()
                        if mon and hasattr(mon, '_background_sync_completed') and mon._background_sync_completed:
                            mon._background_sync_completed = False
                            sync_detected = True
                            logger.info("Background price sync completed — running signal generation")
                            break
                    except Exception:
                        pass
                    
                    await asyncio.sleep(10)
                    waited += 10
                
                if not sync_detected and self._running:
                    # Fallback: run anyway if we've waited long enough
                    elapsed_since_last = _time.time() - last_signal_run
                    if elapsed_since_last >= MIN_GAP_SECONDS:
                        logger.warning(
                            f"No background sync detected after {waited:.0f}s — "
                            f"running signal generation anyway (last run {elapsed_since_last:.0f}s ago)"
                        )
                    else:
                        # Still too soon, loop back
                        continue
                
                if not self._running:
                    break
                
                # Check system state
                state_manager = get_system_state_manager()
                current_state = state_manager.get_current_state()
                
                if current_state.state == SystemStateEnum.ACTIVE:
                    await self._run_trading_cycle()
                    last_signal_run = _time.time()
                    logger.info(f"Signal generation complete — next run in ~{MIN_GAP_SECONDS // 60} min")
                else:
                    logger.debug(
                        f"Skipping trading cycle: system state is {current_state.state.value}"
                    )
            
            except asyncio.CancelledError:
                logger.info("Trading scheduler loop cancelled")
                break
            
            except Exception as e:
                logger.error(f"Error in trading scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(1800)

    def _sync_broadcast(self, message: dict):
        """Broadcast WebSocket message from sync context."""
        if not self._websocket_manager:
            return
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(self._websocket_manager.broadcast(message), loop=loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._websocket_manager.broadcast(message))
                loop.close()
        except Exception:
            pass

    def _sync_broadcast_call(self, coro_func, *args, **kwargs):
        """Call an async WebSocket broadcast method from sync context."""
        if not self._websocket_manager:
            return
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(coro_func(*args, **kwargs), loop=loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(coro_func(*args, **kwargs))
                loop.close()
        except Exception:
            pass

    def run_signal_generation_sync(self, strategy_ids: list = None, include_dynamic: bool = False) -> dict:
        """
        Run signal generation, coordination, validation, and order execution synchronously.

        This is the single source of truth for the signal-to-order pipeline.
        Called by both the 30-minute scheduler loop and the autonomous cycle's Stage 8.
        
        Args:
            strategy_ids: Optional list of strategy IDs to filter to
            include_dynamic: If True, scan dynamic symbol additions (manual cycle).
                           If False, only scan static watchlist (30-min loop).

        Returns dict with: signals_generated, signals_coordinated, signals_rejected,
        orders_submitted, active_strategies
        """
        result = {"signals_generated": 0, "signals_coordinated": 0, "signals_rejected": 0,
                  "orders_submitted": 0, "active_strategies": 0}

        if not self._components_initialized:
            logger.warning("Trading components not initialized — skipping signal generation")
            return result

        logger.info("Running signal generation cycle")

        from src.models.database import get_database
        from src.models.orm import StrategyORM, PositionORM, OrderORM
        from src.models.enums import OrderStatus
        from src.models.dataclasses import Position, PositionSide

        db = get_database()
        session = db.get_session()

        try:
            # Scan both DEMO/LIVE (actively trading) and BACKTESTED (validated, waiting for signal).
            # BACKTESTED strategies with activation_approved=True are ready to trade —
            # they'll be promoted to DEMO when they generate their first signal.
            active_strategies = session.query(StrategyORM).filter(
                StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE, StrategyStatus.BACKTESTED])
            ).all()
            
            # Filter BACKTESTED to only those approved for activation
            active_strategies = [
                s for s in active_strategies
                if s.status in (StrategyStatus.DEMO, StrategyStatus.LIVE)
                or (s.status == StrategyStatus.BACKTESTED 
                    and isinstance(s.strategy_metadata, dict) 
                    and s.strategy_metadata.get('activation_approved'))
            ]

            # If specific strategy IDs provided, filter to only those
            if strategy_ids:
                active_strategies = [s for s in active_strategies if s.id in strategy_ids]
                logger.info(f"Filtered to {len(active_strategies)} newly activated strategies (from {strategy_ids})")

            if not active_strategies:
                logger.debug("No active strategies found - skipping signal generation")
                return result

            logger.info(f"Found {len(active_strategies)} active strategies")

            # Market hours awareness: filter strategies by asset class based on current time
            # eToro offers 24/5 trading on most US stocks (extended hours).
            # Stocks/ETFs/Indices/Forex/Commodities: Mon-Fri (skip weekends)
            # Crypto: 24/7
            # If a specific instrument isn't available for extended hours,
            # eToro will reject the order and our order monitor handles it.
            from datetime import timezone
            import pytz
            try:
                et_tz = pytz.timezone('US/Eastern')
                now_et = datetime.now(et_tz)
                is_weekend = now_et.weekday() >= 5  # Saturday=5, Sunday=6
                
                filtered_strategies = []
                for s in active_strategies:
                    # Determine asset class from strategy symbols
                    primary_symbol = s.symbols[0] if s.symbols else ''
                    sym_upper = primary_symbol.upper()
                    
                    from src.core.tradeable_instruments import (
                        DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX
                    )
                    
                    if sym_upper in DEMO_ALLOWED_CRYPTO:
                        # Crypto: always scan (24/7)
                        filtered_strategies.append(s)
                    elif is_weekend:
                        # Everything else: skip weekends
                        logger.debug(f"Skipping {s.name} (weekend)")
                    else:
                        # Stocks, ETFs, indices, forex, commodities: 24/5 on eToro
                        filtered_strategies.append(s)
                
                skipped = len(active_strategies) - len(filtered_strategies)
                if skipped > 0:
                    logger.info(f"Market hours filter: {skipped} strategies skipped (market {'closed' if not is_market_hours else 'weekend'}), {len(filtered_strategies)} active")
                active_strategies = filtered_strategies
            except ImportError:
                logger.debug("pytz not available, skipping market hours filter")
            except Exception as e:
                logger.debug(f"Market hours filter skipped: {e}")
            
            if not active_strategies:
                logger.debug("No strategies active for current market hours - skipping signal generation")
                return result

            # Get account info for risk validation
            try:
                account_info = self._etoro_client.get_account_info()
            except Exception as e:
                logger.error(f"Failed to get account info: {e}")
                return result

            # Get current positions for risk validation
            positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None),
                PositionORM.pending_closure == False
            ).all()

            # Get pending orders, recently filled orders, AND recently failed orders
            # to prevent duplicates and stop retrying failed symbols
            from datetime import timedelta
            recent_cutoff = datetime.now() - timedelta(hours=6)  # 6 hour lookback — covers 4H strategy intervals
            failed_cutoff = datetime.now() - timedelta(hours=1)  # Don't retry failed orders for 1 hour
            
            pending_orders = session.query(OrderORM).filter(
                (OrderORM.status == OrderStatus.PENDING) |
                ((OrderORM.status == OrderStatus.FILLED) & (OrderORM.filled_at >= recent_cutoff)) |
                ((OrderORM.status == 'FAILED') & (OrderORM.submitted_at >= failed_cutoff))
            ).all()

            logger.info(f"Found {len(positions)} open positions and {len(pending_orders)} pending/recent orders")

            # Convert ORM positions to dataclass positions
            position_dataclasses = []
            for pos_orm in positions:
                pos_dc = Position(
                    id=pos_orm.id,
                    strategy_id=pos_orm.strategy_id,
                    symbol=pos_orm.symbol,
                    side=PositionSide(pos_orm.side),
                    quantity=pos_orm.quantity,
                    entry_price=pos_orm.entry_price,
                    current_price=pos_orm.current_price,
                    unrealized_pnl=pos_orm.unrealized_pnl,
                    realized_pnl=pos_orm.realized_pnl,
                    opened_at=pos_orm.opened_at,
                    etoro_position_id=pos_orm.etoro_position_id,
                    stop_loss=pos_orm.stop_loss,
                    take_profit=pos_orm.take_profit,
                    closed_at=pos_orm.closed_at,
                    pending_closure=getattr(pos_orm, 'pending_closure', False),
                )
                position_dataclasses.append(pos_dc)

            # Convert all ORM strategies to dataclasses
            import time as _time
            strategy_map = {}  # strategy_id -> (Strategy, StrategyORM)
            strategy_list = []
            for strategy_orm in active_strategies:
                try:
                    strategy = self._strategy_engine._orm_to_strategy(strategy_orm)
                    strategy_map[strategy.id] = (strategy, strategy_orm)
                    strategy_list.append(strategy)
                except Exception as e:
                    logger.error(f"Error converting strategy {strategy_orm.name}: {e}")
                    continue

            result["active_strategies"] = len(strategy_list)

            # Batch signal generation (fetches data once per symbol, shared across strategies)
            batch_start = _time.time()
            batch_results = self._strategy_engine.generate_signals_batch(strategy_list, include_dynamic=include_dynamic)
            batch_time = _time.time() - batch_start

            total_signals = sum(len(s) for s in batch_results.values())
            result["signals_generated"] = total_signals
            logger.info(
                f"Batch signal generation: {total_signals} signals from "
                f"{len(strategy_list)} strategies in {batch_time:.1f}s"
            )

            # Coordinate signals to avoid redundancy and check existing positions
            coordinated_results = self._coordinate_signals(
                batch_results,
                strategy_map,
                existing_positions=position_dataclasses,
                pending_orders=pending_orders,
                account=account_info,
            )
            coordinated_total = sum(len(s) for s in coordinated_results.values())
            result["signals_coordinated"] = coordinated_total

            if coordinated_total < total_signals:
                logger.info(
                    f"Signal coordination: {total_signals} → {coordinated_total} signals "
                    f"({total_signals - coordinated_total} redundant signals filtered)"
                )

            # Process coordinated signals: validate and execute
            orders_executed = 0
            signals_rejected = 0
            
            # Safety: cap max orders per signal generation run
            # With 2% allocation per order, 15 orders = 30% of account per run
            MAX_ORDERS_PER_RUN = 15
            
            # Track cumulative exposure to prevent over-allocation
            cumulative_allocated = 0.0
            account_equity_val = getattr(account_info, 'equity', None) or getattr(account_info, 'balance', 0)
            max_batch_exposure_pct = 0.40  # Max 40% of equity per signal generation run
            max_batch_amount = account_equity_val * max_batch_exposure_pct
            
            # In-run dedup: track (symbol, direction) pairs we've already submitted orders for
            # in THIS signal generation run. Prevents race condition where two strategies
            # both submit orders for the same symbol before either position is in DB.
            orders_submitted_this_run = set()  # (normalized_symbol, direction)
            
            for strategy_id, signals in coordinated_results.items():
                if not signals:
                    continue

                strategy, strategy_orm = strategy_map.get(strategy_id, (None, None))
                if not strategy:
                    continue

                logger.info(f"Processing {len(signals)} signals for {strategy.name}")

                # Broadcast signal generation events
                for signal in signals:
                    self._sync_broadcast_call(
                        self._websocket_manager.broadcast_signal_generated,
                        {
                            "strategy_id": signal.strategy_id,
                            "strategy_name": strategy.name,
                            "symbol": signal.symbol,
                            "action": signal.action.value,
                            "confidence": signal.confidence,
                            "reasoning": signal.reasoning,
                            "indicators": signal.indicators,
                            "timestamp": signal.generated_at.isoformat()
                        }
                    )

                # Validate and execute each signal
                for signal in signals:
                    logger.info(
                        f"Signal: {signal.action.value} {signal.symbol} "
                        f"(confidence: {signal.confidence:.2f}, reasoning: {signal.reasoning})"
                    )

                    # In-run dedup: skip if we already submitted an order for this symbol/direction
                    from src.utils.symbol_normalizer import normalize_symbol as _norm
                    from src.models.enums import SignalAction as _SignalAction
                    _sig_sym = _norm(signal.symbol)
                    _sig_dir = "LONG" if signal.action in [_SignalAction.ENTER_LONG] else "SHORT"
                    if (_sig_sym, _sig_dir) in orders_submitted_this_run:
                        logger.info(
                            f"Skipping {signal.symbol} {_sig_dir} — already submitted order "
                            f"for this symbol/direction in this run"
                        )
                        self._log_signal_decision(
                            session=session,
                            signal=signal,
                            strategy_name=strategy.name,
                            decision="REJECTED",
                            rejection_reason=f"In-run duplicate: order already submitted for {_sig_sym} {_sig_dir}",
                        )
                        signals_rejected += 1
                        continue

                    # Safety: stop if we've hit the max orders cap
                    if orders_executed >= MAX_ORDERS_PER_RUN:
                        logger.info(
                            f"Max orders per run reached ({MAX_ORDERS_PER_RUN}). "
                            f"Remaining signals deferred to next cycle."
                        )
                        signals_rejected += 1
                        continue
                    
                    # Safety: stop if cumulative allocation exceeds batch limit
                    if cumulative_allocated >= max_batch_amount:
                        logger.info(
                            f"Batch exposure limit reached (${cumulative_allocated:,.0f} / "
                            f"${max_batch_amount:,.0f}). Remaining signals deferred to next cycle."
                        )
                        signals_rejected += 1
                        continue
                    
                    # Validate signal through risk manager
                    validation_result = self._risk_manager.validate_signal(
                        signal=signal,
                        account=account_info,
                        positions=position_dataclasses,
                        strategy_allocation_pct=strategy.allocation_percent
                    )

                    # Broadcast signal validation result
                    self._sync_broadcast({
                        "type": "signal_validated",
                        "signal": {
                            "strategy_id": signal.strategy_id,
                            "strategy_name": strategy.name,
                            "symbol": signal.symbol,
                            "action": signal.action.value,
                            "confidence": signal.confidence
                        },
                        "validation": {
                            "is_valid": validation_result.is_valid,
                            "reason": validation_result.reason,
                            "position_size": validation_result.position_size if validation_result.is_valid else None
                        },
                        "timestamp": datetime.now().isoformat()
                    })

                    if validation_result.is_valid:
                        # Log accepted signal decision
                        self._log_signal_decision(
                            session=session,
                            signal=signal,
                            strategy_name=strategy.name,
                            decision="ACCEPTED",
                            rejection_reason=None,
                        )

                        logger.info(
                            f"Signal validated: {signal.symbol} {signal.action.value} "
                            f"size={validation_result.position_size:.2f}"
                        )

                        # Apply regime-based position sizing
                        try:
                            import yaml
                            from pathlib import Path
                            config_path = Path("config/autonomous_trading.yaml")
                            if config_path.exists():
                                with open(config_path, 'r') as f:
                                    sizing_config = yaml.safe_load(f)

                                regime_sizing = sizing_config.get('position_management', {}).get('regime_based_sizing', {})
                                if regime_sizing.get('enabled', False):
                                    from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                                    analyzer = MarketStatisticsAnalyzer(self._market_data)
                                    sub_regime, _, _, _ = analyzer.detect_sub_regime()

                                    multipliers = regime_sizing.get('multipliers', {})
                                    regime_name = sub_regime.value.lower()

                                    multiplier = 1.0
                                    if 'high' in regime_name and 'vol' in regime_name:
                                        multiplier = multipliers.get('high_volatility', 0.5)
                                    elif 'low' in regime_name and 'vol' in regime_name:
                                        multiplier = multipliers.get('low_volatility', 1.0)
                                    elif 'trending' in regime_name:
                                        multiplier = multipliers.get('trending', 1.2)
                                    elif 'ranging' in regime_name:
                                        multiplier = multipliers.get('ranging', 0.8)

                                    if multiplier != 1.0:
                                        original_size = validation_result.position_size
                                        validation_result.position_size = round(original_size * multiplier, 2)
                                        logger.info(
                                            f"Regime-based sizing: {sub_regime.value} → {multiplier}x "
                                            f"(${original_size:.2f} → ${validation_result.position_size:.2f})"
                                        )
                                    
                                    # Attach market regime to signal metadata for trade journal
                                    if hasattr(signal, 'metadata') and signal.metadata is not None:
                                        signal.metadata['market_regime'] = sub_regime.value
                                    elif hasattr(signal, 'metadata'):
                                        signal.metadata = {'market_regime': sub_regime.value}
                        except Exception as e:
                            logger.debug(f"Could not apply regime-based sizing: {e}")

                        # Ensure market_regime is in signal metadata (even if sizing is disabled)
                        if hasattr(signal, 'metadata') and signal.metadata is not None:
                            if 'market_regime' not in signal.metadata:
                                try:
                                    import yaml
                                    from pathlib import Path
                                    _cp = Path("config/autonomous_trading.yaml")
                                    if _cp.exists():
                                        with open(_cp, 'r') as _f:
                                            _cfg = yaml.safe_load(_f) or {}
                                        _regime = _cfg.get('market_regime', {}).get('current', 'unknown')
                                        signal.metadata['market_regime'] = _regime
                                except Exception:
                                    signal.metadata['market_regime'] = 'unknown'

                        # Execute validated signal through order executor
                        try:
                            order = self._order_executor.execute_signal(
                                signal=signal,
                                position_size=validation_result.position_size,
                                stop_loss_pct=strategy.risk_params.stop_loss_pct,
                                take_profit_pct=strategy.risk_params.take_profit_pct
                            )

                            logger.info(
                                f"Order executed: {order.id} - {order.side.value} "
                                f"{order.quantity} {order.symbol}"
                            )

                            # Broadcast order execution
                            self._sync_broadcast_call(
                                self._websocket_manager.broadcast_order_update,
                                {
                                    "id": order.id,
                                    "strategy_id": order.strategy_id,
                                    "strategy_name": strategy.name,
                                    "symbol": order.symbol,
                                    "side": order.side.value,
                                    "order_type": order.order_type.value,
                                    "quantity": order.quantity,
                                    "status": order.status.value,
                                    "price": order.price,
                                    "stop_price": order.stop_price,
                                    "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                                    "etoro_order_id": order.etoro_order_id
                                }
                            )

                            # Save order to database
                            order_orm = OrderORM(
                                id=order.id,
                                strategy_id=order.strategy_id,
                                symbol=order.symbol,
                                side=order.side,
                                order_type=order.order_type,
                                quantity=order.quantity,
                                status=order.status,
                                price=order.price,
                                stop_price=order.stop_price,
                                take_profit_price=order.take_profit_price,
                                submitted_at=order.submitted_at or datetime.now(),
                                filled_at=order.filled_at,
                                filled_price=order.filled_price,
                                filled_quantity=order.filled_quantity,
                                etoro_order_id=order.etoro_order_id,
                                expected_price=order.expected_price,
                                slippage=order.slippage,
                                fill_time_seconds=order.fill_time_seconds,
                                order_action='entry',
                            )
                            session.add(order_orm)
                            session.commit()
                            orders_executed += 1
                            
                            # Track this symbol/direction to prevent in-run duplicates
                            orders_submitted_this_run.add((_sig_sym, _sig_dir))
                            
                            # Track cumulative allocation
                            cumulative_allocated += validation_result.position_size

                            # Promote BACKTESTED → DEMO on first order
                            # Strategy proved it can trade — actual order placed on eToro
                            if strategy_orm.status == StrategyStatus.BACKTESTED:
                                strategy_orm.status = StrategyStatus.DEMO
                                strategy_orm.activated_at = datetime.now()
                                allocation = strategy.allocation_percent or 2.0
                                strategy_orm.allocation_percent = allocation
                                # Force SQLAlchemy to detect the change on JSON column
                                from sqlalchemy.orm.attributes import flag_modified
                                flag_modified(strategy_orm, 'strategy_metadata')
                                session.commit()
                                result.setdefault("promoted_to_demo", 0)
                                result["promoted_to_demo"] += 1
                                logger.info(
                                    f"  ✓ Promoted {strategy.name} from BACKTESTED → DEMO "
                                    f"(order executed, allocation: {allocation:.1f}%)"
                                )

                                # Broadcast strategy_update so frontend moves it
                                # from Backtested tab to Active tab in real time
                                # Include order/position counts so the frontend shows correct values
                                pending_orders = session.query(OrderORM).filter(
                                    OrderORM.strategy_id == strategy.id,
                                    OrderORM.status == OrderStatus.PENDING
                                ).count()
                                open_positions = session.query(PositionORM).filter(
                                    PositionORM.strategy_id == strategy.id,
                                    PositionORM.closed_at.is_(None),
                                    PositionORM.pending_closure == False
                                ).count()

                                perf = strategy_orm.performance if isinstance(strategy_orm.performance, dict) else {}
                                perf_with_counts = {**perf, "live_orders": pending_orders, "open_positions": open_positions}

                                self._sync_broadcast({
                                    "type": "strategy_update",
                                    "strategy": {
                                        "id": strategy.id,
                                        "name": strategy.name,
                                        "status": "DEMO",
                                        "activated_at": strategy_orm.activated_at.isoformat(),
                                        "allocation_percent": allocation,
                                        "symbols": strategy.symbols,
                                        "performance_metrics": perf_with_counts,
                                        "backtest_results": strategy_orm.backtest_results if isinstance(strategy_orm.backtest_results, dict) else {},
                                    }
                                })

                            # Adjust opposing position SL if needed
                            self._adjust_opposing_position_sl(session, order, signal)

                            # Immediately check if order is filled and create position
                            # Market orders on eToro fill instantly — don't wait for order monitor
                            if order.etoro_order_id:
                                try:
                                    import time as _t
                                    _t.sleep(1)  # Brief pause for eToro to process

                                    status_data = self._etoro_client.get_order_status(order.etoro_order_id)
                                    etoro_status = status_data.get("statusID") if status_data else None

                                    if etoro_status in [2, 3, 7]:
                                        # Order filled — update order status
                                        order_orm.status = OrderStatus.FILLED
                                        order_orm.filled_at = datetime.now()
                                        order_orm.filled_quantity = order.quantity

                                        # Get position from eToro and extract filled_price
                                        positions_data = status_data.get("positions", [])
                                        etoro_position_id = str(positions_data[0].get("positionID")) if positions_data else None
                                        if positions_data:
                                            order_orm.filled_price = positions_data[0].get("open_rate") or positions_data[0].get("entry_price") or order.expected_price

                                        if not etoro_position_id:
                                            # Fetch positions and match by symbol
                                            etoro_positions = self._etoro_client.get_positions()
                                            from src.utils.symbol_normalizer import normalize_symbol
                                            norm_symbol = normalize_symbol(order.symbol)
                                            for ep in etoro_positions:
                                                if normalize_symbol(ep.symbol) == norm_symbol:
                                                    etoro_position_id = ep.etoro_position_id
                                                    break

                                        if etoro_position_id:
                                            # Check if position already exists
                                            from src.models.enums import OrderSide as OrderSideEnum
                                            pos_side = PositionSide.LONG if order.side == OrderSideEnum.BUY else PositionSide.SHORT
                                            existing = session.query(PositionORM).filter(
                                                PositionORM.symbol == order.symbol,
                                                PositionORM.side == pos_side,
                                                PositionORM.closed_at.is_(None),
                                            ).first()

                                            if existing:
                                                existing.etoro_position_id = etoro_position_id
                                                logger.info(f"Updated existing {order.symbol} position with eToro ID {etoro_position_id}")
                                            else:
                                                import uuid as _uuid
                                                new_pos = PositionORM(
                                                    id=str(_uuid.uuid4()),
                                                    strategy_id=order.strategy_id,
                                                    symbol=order.symbol,
                                                    side=pos_side,
                                                    quantity=order.quantity,
                                                    entry_price=order_orm.filled_price or order.expected_price or 0,
                                                    current_price=order_orm.filled_price or order.expected_price or 0,
                                                    unrealized_pnl=0.0,
                                                    realized_pnl=0.0,
                                                    opened_at=datetime.now(),
                                                    etoro_position_id=etoro_position_id,
                                                    stop_loss=order.stop_price,
                                                    take_profit=order.take_profit_price,
                                                )
                                                session.add(new_pos)
                                                logger.info(f"Position created immediately: {order.symbol} {pos_side.value} (eToro: {etoro_position_id})")

                                        # Adjust opposing position's SL if needed
                                        self._adjust_opposing_position_sl(
                                            session=session,
                                            symbol=order.symbol,
                                            new_side=pos_side,
                                            new_tp=order.take_profit_price,
                                        )

                                        session.commit()

                                except Exception as pos_err:
                                    logger.debug(f"Immediate position creation skipped: {pos_err}")
                                    # Non-critical — order monitor will pick it up

                        except Exception as e:
                            logger.error(f"Failed to execute signal for {signal.symbol}: {e}")
                            # Count as rejected so the cycle summary is accurate
                            signals_rejected += 1
                            self._log_signal_decision(
                                session=session,
                                signal=signal,
                                strategy_name=strategy.name,
                                decision="REJECTED",
                                rejection_reason=f"Order execution failed: {str(e)[:200]}",
                            )
                            continue
                    else:
                        # Log rejected signal decision
                        self._log_signal_decision(
                            session=session,
                            signal=signal,
                            strategy_name=strategy.name,
                            decision="REJECTED",
                            rejection_reason=validation_result.reason,
                        )

                        logger.warning(
                            f"Signal rejected: {signal.symbol} {signal.action.value} - "
                            f"{validation_result.reason}"
                        )
                        signals_rejected += 1

            result["signals_rejected"] = signals_rejected
            result["orders_submitted"] = orders_executed

            logger.info("Signal generation cycle complete")

            # === BACKTESTED TTL: expire strategies that haven't traded ===
            # Only run TTL checks during full scans (30-min scheduler), not targeted runs
            # (manual cycle with specific strategy_ids). Targeted runs only scan a subset,
            # so incrementing the counter would be unfair to strategies not in the subset.
            if not strategy_ids:
                # Track which BACKTESTED strategies fired a signal this cycle
                promoted_ids = set()
                for strategy_id, signals in coordinated_results.items():
                    if signals:
                        strategy, strategy_orm = strategy_map.get(strategy_id, (None, None))
                        if strategy_orm and strategy_orm.status == StrategyStatus.DEMO:
                            # Was BACKTESTED, now DEMO — it fired
                            promoted_ids.add(strategy_id)

                # Load TTL config
                backtested_ttl_cycles = 48  # Default: ~24h at 30-min intervals
                hard_ttl_days = 3  # Hard wall-clock backstop
                try:
                    import yaml as _ttl_yaml
                    from pathlib import Path as _ttl_Path
                    _ttl_cp = _ttl_Path("config/autonomous_trading.yaml")
                    if _ttl_cp.exists():
                        with open(_ttl_cp, 'r') as _f:
                            _ttl_cfg = _ttl_yaml.safe_load(_f) or {}
                            backtested_ttl_cycles = _ttl_cfg.get('autonomous', {}).get('backtested_ttl_cycles', 48)
                except Exception:
                    pass

                # Increment cycle counter for BACKTESTED+approved strategies that didn't fire
                expired_count = 0
                for s_orm in active_strategies:
                    if s_orm.status != StrategyStatus.BACKTESTED:
                        continue
                    meta = s_orm.strategy_metadata if isinstance(s_orm.strategy_metadata, dict) else {}
                    if not meta.get('activation_approved'):
                        continue

                    sid = s_orm.id
                    if sid in promoted_ids:
                        # Fired and promoted — reset counter
                        meta['signal_cycles_without_trade'] = 0
                        s_orm.strategy_metadata = meta
                        continue

                    # Check if it generated a signal (even if rejected by risk)
                    had_signal = sid in coordinated_results and len(coordinated_results.get(sid, [])) > 0
                    if had_signal:
                        # Signal generated but order rejected — reset counter (strategy is trying)
                        meta['signal_cycles_without_trade'] = 0
                        s_orm.strategy_metadata = meta
                        continue

                    # No signal — increment counter
                    cycles = meta.get('signal_cycles_without_trade', 0) + 1
                    meta['signal_cycles_without_trade'] = cycles
                    s_orm.strategy_metadata = meta

                    # Interval-aware TTL: 4H strategies fire ~4-6x less often than 1H.
                    # A 4H mean-reversion strategy might legitimately go 3-5 days without
                    # a signal — that's normal, not a sign of a dead strategy.
                    # Multiply TTL by 3x for 4H, keep default for 1H/daily.
                    strat_interval = '1d'
                    if isinstance(meta, dict):
                        strat_interval = meta.get('interval', '1d')
                    if not strat_interval and s_orm.rules and isinstance(s_orm.rules, dict):
                        strat_interval = s_orm.rules.get('interval', '1d')
                    strat_interval = (strat_interval or '1d').lower()
                    
                    if strat_interval == '4h':
                        effective_ttl_cycles = backtested_ttl_cycles * 3
                        effective_hard_ttl_days = hard_ttl_days * 3  # 9 days instead of 3
                    elif strat_interval in ('1h', '2h'):
                        effective_ttl_cycles = backtested_ttl_cycles
                        effective_hard_ttl_days = hard_ttl_days
                    else:
                        # Daily strategies
                        effective_ttl_cycles = backtested_ttl_cycles
                        effective_hard_ttl_days = hard_ttl_days

                    # Check hard wall-clock backstop
                    # Use demoted_at if available (strategy was previously active and got
                    # demoted back to BACKTESTED). This prevents killing strategies that
                    # were just actively trading — they deserve a fresh TTL window.
                    demoted_at_str = meta.get('demoted_at')
                    if demoted_at_str:
                        try:
                            ttl_reference = datetime.fromisoformat(demoted_at_str)
                        except (ValueError, TypeError):
                            ttl_reference = s_orm.created_at
                    else:
                        ttl_reference = s_orm.created_at
                    
                    days_since_reference = (datetime.now() - ttl_reference).days if ttl_reference else 0

                    if cycles >= effective_ttl_cycles or days_since_reference >= effective_hard_ttl_days:
                        reason = f"TTL expired: {cycles} signal cycles without trade (limit={effective_ttl_cycles}, interval={strat_interval})" if cycles >= effective_ttl_cycles else f"Hard TTL: {days_since_reference} days since {'demotion' if demoted_at_str else 'creation'} (limit={effective_hard_ttl_days}d for {strat_interval})"
                        s_orm.status = StrategyStatus.RETIRED
                        s_orm.retired_at = datetime.now()
                        expired_count += 1
                        logger.info(f"  ⏰ Retired BACKTESTED strategy {s_orm.name}: {reason}")

                if expired_count > 0:
                    session.commit()
                    logger.info(f"Expired {expired_count} BACKTESTED strategies (TTL={backtested_ttl_cycles} cycles)")
                else:
                    session.commit()  # Save cycle counter updates

                result["backtested_expired"] = expired_count

            # Log to structured cycle log
            try:
                from src.core.cycle_logger import get_cycle_logger
                import time as _t2
                duration = _t2.time() - batch_start if 'batch_start' in dir() else 0
                get_cycle_logger().log_signal_cycle(
                    duration_seconds=duration,
                    strategies=result["active_strategies"],
                    signals=result["signals_coordinated"],
                    orders=orders_executed,
                )
            except Exception:
                pass

        finally:
            session.close()

        return result
    def _adjust_opposing_position_sl(self, session, order, signal):
        """
        When placing an opposing order on a symbol with an existing position,
        widen the existing position's SL so it doesn't get stopped out before
        the new opposing position reaches its TP.

        Example: MRNA LONG SL=49.43, new SHORT TP=48.38
        → LONG SL should move to 48.38 - buffer so both trades can play out.
        """
        from src.models.enums import SignalAction, PositionSide

        try:
            # Determine the new order's direction
            if signal.action in [SignalAction.ENTER_LONG]:
                opposing_side = PositionSide.SHORT
                new_side_label = "LONG"
            elif signal.action in [SignalAction.ENTER_SHORT]:
                opposing_side = PositionSide.LONG
                new_side_label = "SHORT"
            else:
                return

            # Find opposing open positions on the same symbol
            opposing_positions = session.query(PositionORM).filter(
                PositionORM.symbol == order.symbol,
                PositionORM.side == opposing_side,
                PositionORM.closed_at.is_(None),
                PositionORM.pending_closure == False,
            ).all()

            if not opposing_positions:
                return

            new_tp = order.take_profit_price
            if not new_tp:
                return

            for opp_pos in opposing_positions:
                if not opp_pos.stop_loss:
                    continue

                # Check if the opposing position's SL would be hit before our TP
                needs_adjustment = False
                buffer_pct = 0.005  # 0.5% buffer beyond TP
                new_sl = opp_pos.stop_loss

                if opposing_side == PositionSide.LONG:
                    # Opposing is LONG, new order is SHORT with TP below current price
                    # LONG's SL is below entry. If LONG SL > SHORT TP, LONG gets stopped before SHORT profits
                    if opp_pos.stop_loss > new_tp:
                        new_sl = new_tp * (1 - buffer_pct)
                        needs_adjustment = True
                elif opposing_side == PositionSide.SHORT:
                    # Opposing is SHORT, new order is LONG with TP above current price
                    # SHORT's SL is above entry. If SHORT SL < LONG TP, SHORT gets stopped before LONG profits
                    if opp_pos.stop_loss < new_tp:
                        new_sl = new_tp * (1 + buffer_pct)
                        needs_adjustment = True

                if needs_adjustment:
                    old_sl = opp_pos.stop_loss
                    opp_pos.stop_loss = round(new_sl, 4)
                    session.commit()

                    logger.info(
                        f"Opposing SL adjustment: {opp_pos.symbol} {opposing_side.value} "
                        f"SL {old_sl:.4f} → {new_sl:.4f} "
                        f"(widened to accommodate {new_side_label} TP={new_tp:.4f})"
                    )

                    # Push updated SL to eToro if client available
                    if self._etoro_client and opp_pos.etoro_position_id:
                        try:
                            from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
                            instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(opp_pos.symbol)
                            if instrument_id:
                                self._etoro_client.update_position_stop_loss(
                                    opp_pos.etoro_position_id,
                                    new_sl,
                                    instrument_id=instrument_id
                                )
                                logger.info(f"Pushed widened SL to eToro for {opp_pos.symbol} position {opp_pos.etoro_position_id}")
                        except Exception as e:
                            logger.warning(f"Failed to push widened SL to eToro: {e}")
        except Exception as e:
            logger.warning(f"Error adjusting opposing position SL: {e}")


    async def _run_trading_cycle(self):
        """
        Run one complete trading cycle.
        
        Focuses ONLY on signal generation, validation, and order execution
        for already-active strategies. Does NOT propose or validate new strategies.
        
        Architecture:
        - MonitoringService: 24/7 order/position monitoring + daily maintenance
        - TradingScheduler: Signal generation every 5 min for active strategies
        - Autonomous Cycle: Manual trigger only (via API/frontend) for new strategy research
        """
        try:
            # Initialize components once (cached for subsequent cycles)
            if not self._components_initialized:
                if not await self._initialize_components():
                    return
            
            # Run startup reconciliation ONCE before any signal generation
            if not self._reconciliation_done:
                try:
                    from src.core.order_monitor import OrderMonitor
                    from src.models.database import get_database
                    
                    db = get_database()
                    order_monitor = OrderMonitor(self._etoro_client, db)
                    reconciliation_result = order_monitor.reconcile_on_startup()
                    self._reconciliation_done = True
                    
                    if reconciliation_result.get("error"):
                        logger.error(f"Startup reconciliation had errors: {reconciliation_result['error']}")
                    else:
                        logger.info("Startup reconciliation complete - signal generation enabled")
                except Exception as e:
                    logger.error(f"Startup reconciliation failed: {e}", exc_info=True)
                    # Still mark as done to avoid blocking forever - positions will sync via normal 60s cycle
                    self._reconciliation_done = True
            
            import time
            now = time.time()
            
            # Skip if an autonomous cycle is currently running (it handles its own signal generation)
            try:
                from src.api.routers.strategies import _running_cycle_thread, _db_cycle_lock
                if _running_cycle_thread and _running_cycle_thread.is_alive():
                    logger.info("Skipping signal generation — autonomous cycle is running")
                    return
                # Try to acquire DB lock (non-blocking) — if manual cycle holds it, skip
                if not _db_cycle_lock.acquire(blocking=False):
                    logger.info("Skipping signal generation — DB lock held by manual cycle")
                    return
            except ImportError:
                _db_cycle_lock = None
            
            self._last_signal_check = now
            self._next_run_time = datetime.fromtimestamp(now + self.signal_generation_interval)
            
            # Clear stale intraday (1h/4h) data cache before each hourly signal run.
            # The latest 1h candle just closed — strategies need fresh data to evaluate
            # entry/exit conditions on the new candle. Daily data stays cached.
            # Only clears entries older than 50 min (keeps data from manual cycles that just ran).
            try:
                from src.data.market_data_manager import get_historical_cache
                hist_cache = get_historical_cache()
                cleared = hist_cache.clear_intraday()
            except Exception as e:
                logger.debug(f"Could not clear intraday cache: {e}")
            
            # Same for the in-memory cache on the market data manager
            try:
                if self._market_data and hasattr(self._market_data, '_historical_memory_cache'):
                    now_ts = datetime.now()
                    stale_keys = []
                    for k, v in list(self._market_data._historical_memory_cache.items()):
                        k_str = str(k)
                        if ':1h:' in k_str or ':4h:' in k_str:
                            # Memory cache entries are (data, timestamp) tuples or just data
                            if isinstance(v, tuple) and len(v) == 2:
                                _, cached_at = v
                                if hasattr(cached_at, 'total_seconds') or isinstance(cached_at, datetime):
                                    age = (now_ts - cached_at).total_seconds() if isinstance(cached_at, datetime) else 9999
                                    if age > 3000:
                                        stale_keys.append(k)
                            else:
                                stale_keys.append(k)  # No timestamp — clear to be safe
                    for k in stale_keys:
                        del self._market_data._historical_memory_cache[k]
            except Exception:
                pass
            
            result = self.run_signal_generation_sync()
            
            # Store last run metrics for system health dashboard
            self._signals_last_run = result.get("signals_generated", 0)
            self._orders_last_run = result.get("orders_submitted", 0)
            
            # Update system state with last signal time
            if result.get("signals_generated", 0) > 0:
                try:
                    from src.core.system_state_manager import get_system_state_manager
                    get_system_state_manager().record_signal_generated()
                except Exception:
                    pass
            
            # Release DB lock if we acquired it
            try:
                if _db_cycle_lock is not None:
                    _db_cycle_lock.release()
            except (RuntimeError, NameError):
                pass  # Lock wasn't acquired or variable doesn't exist
            
            # Emit pipeline stage complete (for when scheduler runs independently)
            try:
                await self._websocket_manager.broadcast_cycle_progress({
                    "stage": "order_submission",
                    "stage_label": "Signal Generation",
                    "status": "complete",
                    "progress_pct": 100,
                    "metrics": {
                        "signals_generated": result["signals_coordinated"],
                        "signals_rejected": result["signals_rejected"],
                        "orders_submitted": result["orders_submitted"],
                        "active_strategies": result["active_strategies"],
                    },
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as e:
                logger.debug(f"Could not emit pipeline stage event: {e}")
        
        except Exception as e:
            # Release DB lock on error
            try:
                if _db_cycle_lock is not None:
                    _db_cycle_lock.release()
            except (RuntimeError, NameError):
                pass
            logger.error(f"Error in trading cycle: {e}", exc_info=True)

    def _coordinate_signals(
        self,
        batch_results: Dict[str, List],
        strategy_map: Dict[str, tuple],
        existing_positions: List = None,
        pending_orders: List = None,
        account: 'AccountInfo' = None,
    ) -> Dict[str, List]:
        """
        Coordinate signals from multiple strategies to avoid redundancy.

        When multiple strategies generate signals for the same symbol:
        1. Check existing positions to avoid duplicate trades
        2. Check pending orders to avoid duplicate orders before they fill
        3. Group signals by symbol and direction
        4. Keep only the highest-confidence signal per symbol/direction
        5. Allow opposite directions (LONG + SHORT) on same symbol
        6. Check portfolio balance and filter/prioritize signals accordingly
        7. Log which signals were filtered out

        This prevents concentration risk and capital inefficiency from
        multiple strategies trading the same asset simultaneously.

        Args:
            batch_results: Dict mapping strategy_id -> list of signals
            strategy_map: Dict mapping strategy_id -> (Strategy, StrategyORM)
            existing_positions: List of current open positions
            pending_orders: List of pending/submitted orders

        Returns:
            Coordinated batch_results with redundant signals removed
        """
        from src.models.enums import SignalAction, PositionSide, OrderStatus
        from src.risk.risk_manager import EXTERNAL_POSITION_STRATEGY_IDS
        from src.utils.symbol_normalizer import normalize_symbol
        
        # Build map of existing positions by NORMALIZED symbol and side
        existing_positions_map = {}  # (normalized_symbol, side) -> [positions]
        # Also track which positions are intraday vs daily for interval-aware dedup
        intraday_position_keys = set()  # (normalized_symbol, side) keys that are intraday
        daily_position_keys = set()     # (normalized_symbol, side) keys that are daily
        if existing_positions:
            for pos in existing_positions:
                if pos.closed_at is not None:
                    continue
                
                # Include ALL positions (including external/synced) in the symbol-level
                # dedup map. External positions still represent real exposure on eToro
                # and must be counted to prevent duplicate orders.
                normalized_symbol = normalize_symbol(pos.symbol)
                key = (normalized_symbol, pos.side.value)
                if key not in existing_positions_map:
                    existing_positions_map[key] = []
                existing_positions_map[key].append(pos)
                
                # Track whether this position is intraday or daily
                # External positions default to daily
                if pos.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
                    daily_position_keys.add(key)
                    continue
                
                try:
                    from src.models.orm import StrategyORM
                    from src.models.database import get_database
                    db = get_database()
                    _sess = db.get_session()
                    try:
                        strat_orm = _sess.query(StrategyORM).filter_by(id=pos.strategy_id).first()
                        if strat_orm:
                            meta = strat_orm.strategy_metadata if isinstance(strat_orm.strategy_metadata, dict) else {}
                            if meta.get('intraday', False):
                                intraday_position_keys.add(key)
                            else:
                                daily_position_keys.add(key)
                    finally:
                        _sess.close()
                except Exception:
                    daily_position_keys.add(key)  # Default to daily if we can't determine
        
        # Build map of pending orders by (strategy_id, NORMALIZED symbol, side)
        pending_orders_map = {}  # (strategy_id, normalized_symbol, side) -> [orders]
        # Also track total pending orders per symbol (across all strategies)
        pending_orders_per_symbol = {}  # (normalized_symbol, side) -> count
        
        if pending_orders:
            for order in pending_orders:
                # Check PENDING, recently FILLED, and recently FAILED orders
                if order.status in (OrderStatus.PENDING, OrderStatus.FILLED) or str(order.status) == 'FAILED':
                    # Skip external strategy orders
                    if order.strategy_id in EXTERNAL_POSITION_STRATEGY_IDS:
                        continue
                    
                    # Map OrderSide to direction (BUY -> LONG, SELL -> SHORT)
                    from src.models.enums import OrderSide as OrderSideEnum
                    if order.side == OrderSideEnum.BUY:
                        direction = "LONG"
                    elif order.side == OrderSideEnum.SELL:
                        direction = "SHORT"
                    else:
                        continue  # Unknown side
                    
                    # Normalize symbol to handle GE vs ID_1017 vs 1017
                    normalized_symbol = normalize_symbol(order.symbol)
                    
                    # Track per-strategy pending orders
                    key = (order.strategy_id, normalized_symbol, direction)
                    if key not in pending_orders_map:
                        pending_orders_map[key] = []
                    pending_orders_map[key].append(order)
                    
                    # Track total pending orders per symbol (use normalized symbol)
                    symbol_key = (normalized_symbol, direction)
                    pending_orders_per_symbol[symbol_key] = pending_orders_per_symbol.get(symbol_key, 0) + 1
        
        # Group signals by NORMALIZED symbol and direction
        signals_by_symbol_direction = {}  # (normalized_symbol, direction) -> [(strategy_id, signal, strategy_name)]

        for strategy_id, signals in batch_results.items():
            strategy, _ = strategy_map.get(strategy_id, (None, None))
            if not strategy:
                continue

            for signal in signals:
                # Determine direction from signal action
                if signal.action in [SignalAction.ENTER_LONG]:
                    direction = "LONG"
                elif signal.action in [SignalAction.ENTER_SHORT]:
                    direction = "SHORT"
                else:
                    # Exit signals - don't coordinate these
                    continue
                
                # Normalize signal symbol to handle GE vs ID_1017 vs 1017
                normalized_symbol = normalize_symbol(signal.symbol)
                key = (normalized_symbol, direction)
                if key not in signals_by_symbol_direction:
                    signals_by_symbol_direction[key] = []
                signals_by_symbol_direction[key].append((strategy_id, signal, strategy.name))

        # Coordinate: filter based on existing positions, pending orders, symbol limits, correlation, and keep highest-confidence signal
        coordinated_results = {}
        filtered_count = 0
        position_duplicate_count = 0
        pending_order_duplicate_count = 0
        symbol_limit_count = 0
        correlation_filtered_count = 0
        
        # Max strategies per symbol (from risk config)
        MAX_STRATEGIES_PER_SYMBOL = 3
        
        # Correlation analyzer disabled — same-symbol dedup handles concentration risk.
        # The pairwise correlation calculations were running hundreds of times per cycle
        # without meaningful impact on signal selection (all correlations < 0.7 threshold).
        correlation_analyzer = None
        
        # Build map of active symbols by direction for correlation checking
        active_symbols_by_direction = {}  # direction -> [symbols]
        for (normalized_symbol, direction), positions in existing_positions_map.items():
            if direction not in active_symbols_by_direction:
                active_symbols_by_direction[direction] = []
            active_symbols_by_direction[direction].append(normalized_symbol)

        for (normalized_symbol, direction), signal_list in signals_by_symbol_direction.items():
            # Check if we already have a position in this normalized symbol/direction
            existing_key = (normalized_symbol, direction)
            if existing_key in existing_positions_map:
                # Interval-aware dedup: intraday and daily strategies are different timeframes.
                # An intraday BUY on NVDA (holds hours) should NOT block a daily BUY on NVDA (holds weeks).
                # Only block if the SAME timeframe category already has a position.
                existing_count = len(existing_positions_map[existing_key])
                
                # Determine if the incoming signals are intraday or daily
                # Check each signal's strategy metadata
                intraday_signals = []
                daily_signals = []
                for strategy_id, signal, strategy_name in signal_list:
                    strategy, _ = strategy_map.get(strategy_id, (None, None))
                    is_intraday_signal = False
                    if strategy and hasattr(strategy, 'metadata') and strategy.metadata:
                        is_intraday_signal = strategy.metadata.get('intraday', False)
                    if is_intraday_signal:
                        intraday_signals.append((strategy_id, signal, strategy_name))
                    else:
                        daily_signals.append((strategy_id, signal, strategy_name))
                
                # Block intraday signals only if intraday positions exist for this symbol/direction
                blocked_intraday = []
                passed_intraday = []
                if intraday_signals:
                    if existing_key in intraday_position_keys:
                        blocked_intraday = intraday_signals
                    else:
                        passed_intraday = intraday_signals
                
                # Block daily signals only if daily positions exist for this symbol/direction
                blocked_daily = []
                passed_daily = []
                if daily_signals:
                    if existing_key in daily_position_keys:
                        blocked_daily = daily_signals
                    else:
                        passed_daily = daily_signals
                
                # Log blocked signals
                for strategy_id, signal, strategy_name in blocked_intraday + blocked_daily:
                    self._log_coordination_rejection(
                        signal=signal,
                        strategy_name=strategy_name,
                        rejection_reason=f"Duplicate: {existing_count} existing {direction} position(s) in {normalized_symbol}",
                    )
                position_duplicate_count += len(blocked_intraday) + len(blocked_daily)
                
                # Continue with passed signals (different timeframe from existing positions)
                remaining_signals = passed_intraday + passed_daily
                if not remaining_signals:
                    continue
                # Replace signal_list with only the passed signals for downstream processing
                signal_list = remaining_signals
            
            # Correlation filter disabled — we only care about same-symbol dedup
            # Different correlated symbols (e.g., AAPL and MSFT) are allowed
            
            # Check symbol-level limit (across all strategies)
            symbol_key = (normalized_symbol, direction)
            current_pending_count = pending_orders_per_symbol.get(symbol_key, 0)
            current_position_count = len(existing_positions_map.get(existing_key, []))
            total_strategies_for_symbol = current_pending_count + current_position_count
            
            if total_strategies_for_symbol >= MAX_STRATEGIES_PER_SYMBOL:
                logger.warning(
                    f"Symbol limit reached: {total_strategies_for_symbol} strategies already trading {normalized_symbol} {direction} "
                    f"(max: {MAX_STRATEGIES_PER_SYMBOL}), filtering {len(signal_list)} new signal(s)"
                )
                symbol_limit_count += len(signal_list)
                continue  # Skip all signals for this symbol/direction
            
            # Filter signals that already have pending orders
            # Check BOTH same-strategy duplicates AND cross-strategy duplicates
            # for the same symbol/direction (prevents 2 strategies both ordering HYG LONG)
            filtered_signals = []
            for strategy_id, signal, strategy_name in signal_list:
                # Same-strategy dedup: this strategy already has a pending order
                pending_key = (strategy_id, normalized_symbol, direction)
                if pending_key in pending_orders_map:
                    pending_count = len(pending_orders_map[pending_key])
                    logger.info(
                        f"Pending order check: {strategy_name} already has {pending_count} pending "
                        f"{direction} order(s) for {normalized_symbol}, filtering signal"
                    )
                    pending_order_duplicate_count += 1
                    continue  # Skip this strategy's signal
                
                # Cross-strategy dedup: ANY strategy already has a pending order for this symbol/direction
                cross_strategy_pending = False
                for (pid, psym, pdir), orders in pending_orders_map.items():
                    if psym == normalized_symbol and pdir == direction and pid != strategy_id:
                        logger.info(
                            f"Cross-strategy pending order: {normalized_symbol} {direction} already has "
                            f"{len(orders)} pending order(s) from another strategy, filtering {strategy_name}"
                        )
                        cross_strategy_pending = True
                        pending_order_duplicate_count += 1
                        break
                if cross_strategy_pending:
                    continue
                
                filtered_signals.append((strategy_id, signal, strategy_name))
            
            # If all signals were filtered due to pending orders, continue to next symbol/direction
            if not filtered_signals:
                continue
            
            if len(filtered_signals) == 1:
                # Only one strategy trading this symbol/direction - no coordination needed
                strategy_id, signal, _ = filtered_signals[0]
                if strategy_id not in coordinated_results:
                    coordinated_results[strategy_id] = []
                coordinated_results[strategy_id].append(signal)
            else:
                # Multiple strategies want to trade this symbol/direction
                logger.info(
                    f"Signal coordination: {len(filtered_signals)} strategies want to trade {normalized_symbol} {direction}"
                )

                # Sort by confidence (highest first)
                filtered_signals.sort(key=lambda x: x[1].confidence, reverse=True)

                # Keep only the highest-confidence signal
                best_strategy_id, best_signal, best_strategy_name = filtered_signals[0]
                if best_strategy_id not in coordinated_results:
                    coordinated_results[best_strategy_id] = []
                coordinated_results[best_strategy_id].append(best_signal)

                logger.info(
                    f"  ✅ Kept: {best_strategy_name} (confidence={best_signal.confidence:.2f})"
                )

                # Log filtered signals
                for strategy_id, signal, strategy_name in filtered_signals[1:]:
                    logger.info(
                        f"  ❌ Filtered: {strategy_name} (confidence={signal.confidence:.2f}) "
                        f"- lower confidence than {best_strategy_name}"
                    )
                    filtered_count += 1

        if position_duplicate_count > 0:
            logger.info(
                f"Position duplicate filtering: {position_duplicate_count} signals filtered "
                f"(would duplicate existing positions)"
            )
        
        if correlation_filtered_count > 0:
            logger.info(
                f"Correlation filtering: {correlation_filtered_count} signals filtered "
                f"(would trade correlated symbols)"
            )
        
        if pending_order_duplicate_count > 0:
            logger.info(
                f"Pending order duplicate filtering: {pending_order_duplicate_count} signals filtered "
                f"(would duplicate pending orders)"
            )
        
        if symbol_limit_count > 0:
            logger.warning(
                f"Symbol limit filtering: {symbol_limit_count} signals filtered "
                f"(would exceed max {MAX_STRATEGIES_PER_SYMBOL} strategies per symbol)"
            )
        
        if filtered_count > 0:
            logger.info(
                f"Signal coordination complete: {filtered_count} redundant signals filtered"
            )

        # --- Portfolio balance: LOG only, do not filter ---
        # The only hard rule is: no duplicate (symbol, direction) positions.
        # That's already enforced by the position duplicate check above.
        # Sector/directional/strategy-type diversity is informational only.
        try:
            if self._risk_manager and account and existing_positions is not None:
                auto_positions = self._risk_manager._filter_autonomous_positions(existing_positions)
                if auto_positions:
                    long_count = sum(1 for p in auto_positions if p.side == PositionSide.LONG)
                    short_count = sum(1 for p in auto_positions if p.side == PositionSide.SHORT)
                    logger.info(
                        f"Portfolio snapshot: {len(auto_positions)} positions "
                        f"(long={long_count}, short={short_count})"
                    )
        except Exception as e:
            logger.debug(f"Portfolio snapshot failed: {e}")

        return coordinated_results

    def _adjust_opposing_position_sl(
        self,
        session,
        symbol: str,
        new_side,  # PositionSide
        new_tp: float = None,
    ):
        """
        When a new position is opened opposing an existing one on the same symbol,
        widen the existing position's SL so it doesn't get stopped out before the
        new position's TP is reached.

        Example: MRNA LONG SL=49.43, new SHORT TP=48.38
        → LONG SL should move to 48.38 - buffer so both trades can play out.
        """
        if not new_tp:
            return

        from src.models.enums import PositionSide

        # Determine the opposing side
        opposing_side = PositionSide.SHORT if new_side == PositionSide.LONG else PositionSide.LONG

        opposing_positions = session.query(PositionORM).filter(
            PositionORM.symbol == symbol,
            PositionORM.side == opposing_side,
            PositionORM.closed_at.is_(None),
            PositionORM.pending_closure == False,
        ).all()

        if not opposing_positions:
            return

        SL_BUFFER_PCT = 0.005  # 0.5% buffer beyond the new TP

        for pos in opposing_positions:
            if not pos.stop_loss:
                continue

            if opposing_side == PositionSide.LONG:
                # Existing LONG, new SHORT. SHORT TP is below entry → price drops.
                # LONG SL must be below SHORT TP to survive.
                required_sl = new_tp * (1 - SL_BUFFER_PCT)
                if pos.stop_loss > required_sl:
                    old_sl = pos.stop_loss
                    pos.stop_loss = round(required_sl, 5)
                    logger.info(
                        f"Opposing SL adjustment: {symbol} LONG SL widened "
                        f"{old_sl:.4f} → {pos.stop_loss:.4f} "
                        f"(new SHORT TP={new_tp:.4f}, buffer={SL_BUFFER_PCT*100}%)"
                    )
                    # Push to eToro if client available
                    try:
                        if self._etoro_client and pos.etoro_position_id:
                            self._etoro_client.update_position_stop_loss(
                                pos.etoro_position_id, pos.stop_loss
                            )
                            logger.info(f"Pushed widened SL to eToro for {symbol} LONG")
                    except Exception as e:
                        logger.warning(f"Failed to push SL to eToro: {e}")

            else:
                # Existing SHORT, new LONG. LONG TP is above entry → price rises.
                # SHORT SL must be above LONG TP to survive.
                required_sl = new_tp * (1 + SL_BUFFER_PCT)
                if pos.stop_loss < required_sl:
                    old_sl = pos.stop_loss
                    pos.stop_loss = round(required_sl, 5)
                    logger.info(
                        f"Opposing SL adjustment: {symbol} SHORT SL widened "
                        f"{old_sl:.4f} → {pos.stop_loss:.4f} "
                        f"(new LONG TP={new_tp:.4f}, buffer={SL_BUFFER_PCT*100}%)"
                    )
                    try:
                        if self._etoro_client and pos.etoro_position_id:
                            self._etoro_client.update_position_stop_loss(
                                pos.etoro_position_id, pos.stop_loss
                            )
                            logger.info(f"Pushed widened SL to eToro for {symbol} SHORT")
                    except Exception as e:
                        logger.warning(f"Failed to push SL to eToro: {e}")

    def _log_signal_decision(
        self,
        session,
        signal,
        strategy_name: str,
        decision: str,
        rejection_reason: str = None,
    ):
        """Persist a signal decision (accepted/rejected) to the database and broadcast via WebSocket."""
        try:
            from src.models.orm import SignalDecisionLogORM
            from src.models.enums import SignalAction
            import uuid

            # Determine side and signal_type from action
            action_val = signal.action.value if hasattr(signal.action, 'value') else str(signal.action)
            if 'LONG' in action_val or 'BUY' in action_val:
                side = 'BUY'
            else:
                side = 'SELL'

            if 'ENTER' in action_val or 'ENTRY' in action_val:
                signal_type = 'ENTRY'
            else:
                signal_type = 'EXIT'

            signal_id = getattr(signal, 'id', None) or str(uuid.uuid4())[:12]

            log_entry = SignalDecisionLogORM(
                signal_id=signal_id,
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                side=side,
                signal_type=signal_type,
                decision=decision,
                rejection_reason=rejection_reason,
                created_at=datetime.now(),
                metadata_json={
                    "strategy_name": strategy_name,
                    "confidence": signal.confidence,
                    "action": action_val,
                    "reasoning": getattr(signal, 'reasoning', None),
                },
            )
            session.add(log_entry)
            session.commit()

            # Broadcast via WebSocket
            if self._websocket_manager:
                import asyncio
                ws_data = log_entry.to_dict()
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(self._websocket_manager.broadcast({
                            "type": "signal_decision",
                            "data": ws_data,
                            "timestamp": datetime.now().isoformat(),
                        }))
                except Exception:
                    pass  # Non-critical

        except Exception as e:
            logger.debug(f"Failed to log signal decision: {e}")

    def _log_coordination_rejection(
        self,
        signal,
        strategy_name: str,
        rejection_reason: str,
    ):
        """Log a signal rejected during coordination (duplicate, portfolio balance, etc.)."""
        try:
            from src.models.database import get_database
            db = get_database()
            session = db.get_session()
            try:
                self._log_signal_decision(
                    session=session,
                    signal=signal,
                    strategy_name=strategy_name,
                    decision="REJECTED",
                    rejection_reason=rejection_reason,
                )
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"Failed to log coordination rejection: {e}")

    async def _initialize_components(self) -> bool:
        """Initialize and cache trading components. Returns True on success."""
        try:
            from src.strategy.strategy_engine import StrategyEngine
            from src.data.market_data_manager import MarketDataManager
            from src.risk.risk_manager import RiskManager
            from src.execution.order_executor import OrderExecutor
            from src.api.etoro_client import EToroAPIClient
            from src.data.market_hours_manager import MarketHoursManager
            from src.models.enums import TradingMode
            from src.core.config import get_config
            from src.api.websocket_manager import get_websocket_manager
            
            config = get_config()
            
            credentials = config.load_credentials(TradingMode.DEMO)
            self._etoro_client = EToroAPIClient(
                public_key=credentials["public_key"],
                user_key=credentials["user_key"],
                mode=TradingMode.DEMO
            )
            
            self._market_data = MarketDataManager(self._etoro_client)
            self._websocket_manager = get_websocket_manager()
            self._strategy_engine = StrategyEngine(None, self._market_data, self._websocket_manager)
            
            risk_config = config.load_risk_config(TradingMode.DEMO)
            self._risk_manager = RiskManager(risk_config)
            
            market_hours = MarketHoursManager()
            self._order_executor = OrderExecutor(self._etoro_client, market_hours)
            
            self._components_initialized = True
            logger.info("Trading scheduler components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize trading components: {e}", exc_info=True)
            return False


# Global scheduler instance
_scheduler: Optional[TradingScheduler] = None


def get_trading_scheduler() -> TradingScheduler:
    """
    Get or create global trading scheduler instance.
    
    Returns:
        TradingScheduler instance
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = TradingScheduler()
    return _scheduler
