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
        signal_generation_interval: int = 0,  # 0 = read from autonomous_trading.yaml
    ):
        """
        Initialize trading scheduler.
        
        Args:
            signal_generation_interval: Seconds between signal generation runs (0 = read from YAML)
        """
        if signal_generation_interval == 0:
            try:
                import yaml
                from pathlib import Path
                _cfg_path = Path("config/autonomous_trading.yaml")
                if _cfg_path.exists():
                    with open(_cfg_path, 'r') as _f:
                        _cfg = yaml.safe_load(_f) or {}
                    signal_generation_interval = int(
                        _cfg.get('signal_generation', {}).get('interval_seconds', 3600)
                    )
                else:
                    signal_generation_interval = 3600
            except Exception:
                signal_generation_interval = 3600
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
        # Always initialise these so the TTL retirement loop never hits NameError
        # even if _coordinate_signals throws or is skipped (empty strategy list, etc.)
        _strategy_total_signals: dict = {}
        _template_dup_rejected: dict = {}

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
            
            # Filter:
            # - DEMO/LIVE are actively trading (produce exit signals + new entries)
            # - BACKTESTED with activation_approved=True are ready to trade (promoted on first fill)
            # - Exclude pending_retirement or superseded strategies regardless of status —
            #   they must not generate new entry signals. Existing positions close via SL/TP.
            def _is_eligible(s):
                meta = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
                if meta.get('pending_retirement') or meta.get('superseded'):
                    return False
                if s.status in (StrategyStatus.DEMO, StrategyStatus.LIVE):
                    return True
                if s.status == StrategyStatus.BACKTESTED and meta.get('activation_approved'):
                    return True
                return False

            active_strategies = [s for s in active_strategies if _is_eligible(s)]

            # If specific strategy IDs provided, filter to only those
            if strategy_ids:
                active_strategies = [s for s in active_strategies if s.id in strategy_ids]
                logger.info(f"Filtered to {len(active_strategies)} newly activated strategies (from {strategy_ids})")

            if not active_strategies:
                logger.debug("No active strategies found - skipping signal generation")
                return result

            logger.info(f"Found {len(active_strategies)} active strategies")

            # ── Interval-aware strategy filter ───────────────────────────────
            # The signal loop runs every ~55 minutes. Evaluating 4H and 1D
            # strategies on every loop iteration causes rapid entry/exit churn:
            # a 4H strategy's EMA crossover fires on the first 1H bar after
            # entry, then the exit condition fires 10 minutes later on the next
            # 1H bar — the position never has time to develop.
            #
            # Fix: only evaluate a strategy when the current UTC hour aligns
            # with a bar boundary for that strategy's interval.
            #   - 1H strategies: every loop run (bar boundary every hour)
            #   - 4H strategies: when UTC hour ∈ {0, 4, 8, 12, 16, 20}
            #   - 1D strategies: when UTC hour ∈ {0} (midnight UTC, once/day)
            #
            # Exception: strategies with an open position ALWAYS run so exit
            # signals fire promptly regardless of bar boundary. This prevents
            # a position from being stuck open past its exit condition.
            #
            # Exception: when strategy_ids is provided (autonomous cycle Stage 8
            # calling for newly activated strategies), skip the filter — those
            # strategies need their first signal immediately.
            #
            # Exception: 1H strategies always run (their bar boundary is every
            # hour, which aligns with the loop cadence).
            if not strategy_ids:
                _now_utc_hour = datetime.utcnow().hour
                # 4H bar boundaries: 00, 04, 08, 12, 16, 20 UTC
                _at_4h_boundary = (_now_utc_hour % 4 == 0)
                # 1D bar boundary: 00 UTC
                _at_1d_boundary = (_now_utc_hour == 0)

                # Build set of strategy IDs that have open positions (always run)
                _open_position_strategy_ids: set = set()
                try:
                    from src.models.orm import PositionORM as _PosORM
                    _open_pos_rows = session.query(_PosORM.strategy_id).filter(
                        _PosORM.closed_at.is_(None),
                        _PosORM.pending_closure == False,
                    ).all()
                    _open_position_strategy_ids = {r.strategy_id for r in _open_pos_rows}
                except Exception as _pos_err:
                    logger.debug(f"Could not fetch open position strategy IDs for interval filter: {_pos_err}")

                _pre_filter_count = len(active_strategies)
                _interval_skipped = 0
                _filtered_strategies = []
                for _s in active_strategies:
                    _strat_interval = "1d"
                    if _s.rules and isinstance(_s.rules, dict):
                        _strat_interval = _s.rules.get("interval", "1d")

                    # Always run if strategy has an open position (need exit signals)
                    if _s.id in _open_position_strategy_ids:
                        _filtered_strategies.append(_s)
                        continue

                    # 1H strategies: always run
                    if _strat_interval == "1h":
                        _filtered_strategies.append(_s)
                        continue

                    # 4H strategies: only at 4H bar boundaries
                    if _strat_interval == "4h":
                        if _at_4h_boundary:
                            _filtered_strategies.append(_s)
                        else:
                            _interval_skipped += 1
                        continue

                    # 1D strategies: only at daily bar boundary (00 UTC)
                    if _strat_interval == "1d":
                        if _at_1d_boundary:
                            _filtered_strategies.append(_s)
                        else:
                            _interval_skipped += 1
                        continue

                    # Unknown interval: run always (safe default)
                    _filtered_strategies.append(_s)

                active_strategies = _filtered_strategies
                if _interval_skipped > 0:
                    logger.info(
                        f"Interval filter: {_interval_skipped}/{_pre_filter_count} strategies "
                        f"skipped (not at bar boundary — UTC hour={_now_utc_hour}, "
                        f"4H_boundary={_at_4h_boundary}, 1D_boundary={_at_1d_boundary}). "
                        f"{len(active_strategies)} strategies will run."
                    )

            if not active_strategies:
                logger.debug("No strategies active for current bar boundary - skipping signal generation")
                return result

            # Market-hours filter — skip strategies whose primary symbol's
            # market is currently closed on eToro. Routes through the
            # symbol-aware MarketHoursManager so S&P/NDX stocks are correctly
            # treated as tradeable during the 24/5 overnight window.
            try:
                from src.data.market_hours_manager import (
                    get_market_hours_manager, AssetClass as _ACMH,
                )
                from src.core.tradeable_instruments import (
                    DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                    DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES,
                    DEMO_ALLOWED_ETFS,
                )
                _mhm_ts = get_market_hours_manager()

                filtered_strategies = []
                for s in active_strategies:
                    primary_symbol = s.symbols[0] if s.symbols else ''
                    sym_upper = primary_symbol.upper()
                    if not sym_upper:
                        # Strategies without symbols can't be filtered; let them through.
                        filtered_strategies.append(s)
                        continue

                    if sym_upper in set(DEMO_ALLOWED_CRYPTO):
                        _ac_ts = _ACMH.CRYPTOCURRENCY
                    elif sym_upper in set(DEMO_ALLOWED_FOREX):
                        _ac_ts = _ACMH.FOREX
                    elif sym_upper in set(DEMO_ALLOWED_INDICES):
                        _ac_ts = _ACMH.INDEX
                    elif sym_upper in set(DEMO_ALLOWED_COMMODITIES):
                        _ac_ts = _ACMH.COMMODITY
                    elif sym_upper in set(DEMO_ALLOWED_ETFS):
                        _ac_ts = _ACMH.ETF
                    else:
                        _ac_ts = _ACMH.STOCK

                    if _mhm_ts.is_market_open(_ac_ts, symbol=sym_upper):
                        filtered_strategies.append(s)
                    else:
                        logger.debug(
                            f"Skipping {s.name} ({sym_upper} / {_ac_ts.value}): market closed"
                        )

                skipped = len(active_strategies) - len(filtered_strategies)
                if skipped > 0:
                    logger.info(
                        f"Market hours filter: {skipped} strategies skipped "
                        f"(market closed), {len(filtered_strategies)} active"
                    )
                active_strategies = filtered_strategies
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

            # ── PRE-FLIGHT: Balance check ─────────────────────────────────────────
            # If available balance is below the minimum order size, skip all entry
            # signals immediately. Exit signals still run — they don't need balance.
            # This avoids running 40+ signals through the full pipeline only to have
            # every one rejected at the last step with eToro error 604.
            MINIMUM_ORDER_SIZE = 2000.0
            _available_balance = getattr(account_info, 'balance', 0) or 0
            try:
                from src.models.orm import AccountInfoORM
                _db_bal_sess = db.get_session()
                try:
                    _acct_row = _db_bal_sess.query(AccountInfoORM).order_by(
                        AccountInfoORM.updated_at.desc()
                    ).first()
                    if _acct_row and _acct_row.balance is not None:
                        _available_balance = float(_acct_row.balance)
                finally:
                    _db_bal_sess.close()
            except Exception:
                pass
            _skip_entries_balance = _available_balance < MINIMUM_ORDER_SIZE
            if _skip_entries_balance:
                logger.warning(
                    f"Pre-flight: balance ${_available_balance:.0f} < minimum ${MINIMUM_ORDER_SIZE:.0f} "
                    f"— skipping all ENTRY signals this cycle (EXIT signals will still run)"
                )

            # ── PRE-FLIGHT: Portfolio drawdown pause ──────────────────────────────
            # If total unrealized P&L is below -1.5% of equity, pause new LONG entries
            # from trend-following and momentum strategies. Mean reversion and
            # market-neutral can still trade — they're designed for pullbacks.
            # This is the circuit breaker that prevents adding to a losing book.
            DRAWDOWN_PAUSE_THRESHOLD = -0.015  # -1.5% of equity
            _account_equity = getattr(account_info, 'equity', None) or _available_balance
            _total_unrealized = sum(
                (p.unrealized_pnl or 0) for p in positions
            )
            _portfolio_drawdown_pct = _total_unrealized / _account_equity if _account_equity > 0 else 0
            _in_drawdown_pause = _portfolio_drawdown_pct < DRAWDOWN_PAUSE_THRESHOLD
            if _in_drawdown_pause:
                logger.warning(
                    f"Portfolio drawdown pause: unrealized P&L={_portfolio_drawdown_pct:.1%} of equity "
                    f"(threshold={DRAWDOWN_PAUSE_THRESHOLD:.1%}) — blocking trend/momentum LONG entries. "
                    f"Mean reversion and market-neutral still active."
                )

            # ── PRE-FLIGHT: Short-term pullback detection ─────────────────────────
            # Detect intra-regime pullbacks that the 20d/50d regime detector misses.
            # A 5-day correction of -2% doesn't move the 20d average enough to flip
            # the regime label, but it's still a signal to pause trend-following LONGs.
            _pullback_state = {"in_pullback": False, "severity": "none"}
            try:
                from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                _pullback_analyzer = MarketStatisticsAnalyzer(self._market_data)
                _pullback_state = _pullback_analyzer.detect_pullback_state()
                if _pullback_state.get("in_pullback"):
                    logger.warning(
                        f"Pullback gate: {_pullback_state['reason']}"
                    )
            except Exception as _pb_err:
                logger.debug(f"Pullback detection failed: {_pb_err}")

            # ── PRE-FLIGHT: Market Quality Score gate ─────────────────────────────
            # When market quality is low (<40, choppy/noisy), block new trend-following
            # and momentum LONG entries in the signal cycle — not just reduce their size.
            # Mean reversion, market-neutral, and SHORT entries still run.
            # The score is cached for 10 minutes so this is fast (no extra API calls).
            _mqs_grade = "normal"
            _mqs_score = 50.0
            _mqs_block_trend = False
            try:
                from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                _mqs_analyzer = MarketStatisticsAnalyzer(self._market_data)
                _mqs_result = _mqs_analyzer.get_market_quality_score()
                _mqs_score = _mqs_result.get("score", 50.0)
                _mqs_grade = _mqs_result.get("grade", "normal")
                if _mqs_grade == "low":
                    _mqs_block_trend = True
                    logger.warning(
                        f"Market quality gate: score={_mqs_score:.0f}/100 (low) — "
                        f"blocking trend/momentum LONG entries this cycle. "
                        f"Mean reversion and market-neutral still active."
                    )
                else:
                    logger.debug(f"Market quality: {_mqs_score:.0f}/100 ({_mqs_grade}) — no entry restrictions")
            except Exception as _mqs_err:
                logger.debug(f"Market quality gate check failed: {_mqs_err}")

            # Trend/momentum strategy types that should be paused during pullbacks
            _TREND_MOMENTUM_TYPES = {
                'trend_following', 'momentum', 'breakout',
                'trend', 'ema_crossover', 'macd_trend', 'adx_trend',
                'vwap_trend', 'ema_ribbon', 'atr_trend',
            }

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
            # Raw signals before conviction/frequency filtering (for accurate reporting)
            raw_signals = getattr(self._strategy_engine, '_last_batch_raw_signals', total_signals)
            result["signals_raw"] = raw_signals
            logger.info(
                f"Batch signal generation: {total_signals} signals from "
                f"{len(strategy_list)} strategies in {batch_time:.1f}s"
                + (f" ({raw_signals - total_signals} rejected by conviction/frequency filters)" if raw_signals > total_signals else "")
            )

            # Coordinate signals to avoid redundancy and check existing positions
            coordinated_results, _strategy_total_signals, _template_dup_rejected = self._coordinate_signals(
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
            
            # In-run dedup: track (strategy_id, symbol, direction) to prevent a single
            # strategy from opening multiple positions on the same symbol in one batch.
            # Keyed on strategy_id so different strategies can still trade the same symbol.
            orders_submitted_this_run = set()  # (strategy_id, normalized_symbol, direction)
            
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

                    # ── EXIT SIGNAL HANDLING ──────────────────────────────
                    # Exit signals close the strategy's open position for this symbol.
                    # They bypass risk validation and position sizing — the strategy's
                    # DSL exit conditions have fired, meaning the edge is gone.
                    from src.models.enums import SignalAction as _SignalAction
                    if signal.action in [_SignalAction.EXIT_LONG, _SignalAction.EXIT_SHORT]:
                        try:
                            from src.utils.symbol_normalizer import normalize_symbol as _norm_exit
                            _exit_sym = _norm_exit(signal.symbol)
                            _exit_side = PositionSide.LONG if signal.action == _SignalAction.EXIT_LONG else PositionSide.SHORT

                            # Find the open position for this strategy + symbol + side
                            pos_to_close = session.query(PositionORM).filter(
                                PositionORM.strategy_id == strategy.id,
                                PositionORM.symbol == signal.symbol,
                                PositionORM.side == _exit_side,
                                PositionORM.closed_at.is_(None),
                                PositionORM.pending_closure == False,
                            ).first()

                            if not pos_to_close:
                                logger.debug(
                                    f"Exit signal for {signal.symbol} but no open {_exit_side.value} "
                                    f"position found for strategy {strategy.name}"
                                )
                                continue

                            # Guard: low-confidence exit signals (< 0.40) should only fire
                            # on profitable positions. A weak signal on a losing trade just
                            # crystallizes the loss — let the SL handle it instead.
                            EXIT_CONFIDENCE_THRESHOLD = 0.40
                            if signal.confidence < EXIT_CONFIDENCE_THRESHOLD:
                                _entry = pos_to_close.entry_price or 0
                                _current = pos_to_close.current_price or _entry
                                _side_str = str(pos_to_close.side).upper() if pos_to_close.side else 'LONG'
                                _is_long_pos = 'LONG' in _side_str or 'BUY' in _side_str
                                _is_profitable = (_current > _entry) if _is_long_pos else (_current < _entry)
                                if not _is_profitable and _entry > 0:
                                    logger.info(
                                        f"Low-confidence exit signal ({signal.confidence:.2f} < {EXIT_CONFIDENCE_THRESHOLD}) "
                                        f"for losing {signal.symbol} position — letting SL handle it"
                                    )
                                    self._log_signal_decision(
                                        session=session,
                                        signal=signal,
                                        strategy_name=strategy.name,
                                        decision="REJECTED",
                                        rejection_reason=f"Low-confidence exit ({signal.confidence:.2f}) on losing position — SL will handle",
                                    )
                                    continue

                            # Mark position for closure with DSL exit reason
                            pos_to_close.pending_closure = True
                            exit_conditions = strategy.rules.get("exit_conditions", []) if strategy.rules else []
                            conditions_str = " AND ".join(exit_conditions[:3])  # Truncate for readability
                            pos_to_close.closure_reason = (
                                f"Strategy exit signal: {conditions_str} "
                                f"(confidence: {signal.confidence:.2f})"
                            )
                            session.commit()

                            logger.info(
                                f"✅ Exit signal processed: {strategy.name} → close {_exit_side.value} "
                                f"{signal.symbol} (position {pos_to_close.id[:8]}..., "
                                f"unrealized P&L: ${pos_to_close.unrealized_pnl:.2f})"
                            )

                            # ── PAIRS TRADING: Close hedge leg when primary exits ──────
                            _exit_meta = signal.metadata or {}
                            _exit_partner = _exit_meta.get("pair_partner")
                            _exit_pt_type = _exit_meta.get("template_type")
                            if _exit_partner and _exit_pt_type == "pairs_trading":
                                try:
                                    # Find the hedge leg position (opposite side, same strategy)
                                    _hedge_exit_side = PositionSide.SHORT if _exit_side == PositionSide.LONG else PositionSide.LONG
                                    _hedge_pos = session.query(PositionORM).filter(
                                        PositionORM.strategy_id == signal.strategy_id,
                                        PositionORM.symbol == _exit_partner,
                                        PositionORM.side == _hedge_exit_side,
                                        PositionORM.closed_at.is_(None),
                                        PositionORM.pending_closure == False,
                                    ).first()
                                    if _hedge_pos:
                                        _hedge_pos.pending_closure = True
                                        _hedge_pos.closure_reason = (
                                            f"Pairs Trading hedge exit: primary leg {signal.symbol} closed"
                                        )
                                        session.commit()
                                        logger.info(
                                            f"Pairs Trading hedge leg marked for closure: "
                                            f"{_exit_partner} {_hedge_exit_side.value} "
                                            f"(strategy: {strategy.name})"
                                        )
                                except Exception as _hedge_exit_err:
                                    logger.warning(f"Failed to close pairs hedge leg {_exit_partner}: {_hedge_exit_err}")

                            # Log the decision
                            self._log_signal_decision(
                                session=session,
                                signal=signal,
                                strategy_name=strategy.name,
                                decision="ACCEPTED",
                                rejection_reason=None,
                            )

                            orders_executed += 1

                        except Exception as e:
                            logger.error(f"Failed to process exit signal for {signal.symbol}: {e}")
                            session.rollback()
                        continue  # Skip the ENTRY logic below

                    # ── ENTRY SIGNAL HANDLING ─────────────────────────────
                    # In-run dedup: skip if this strategy already submitted an order for this symbol/direction
                    from src.utils.symbol_normalizer import normalize_symbol as _norm
                    _sig_sym = _norm(signal.symbol)
                    _sig_dir = "LONG" if signal.action in [_SignalAction.ENTER_LONG] else "SHORT"
                    if (strategy_id, _sig_sym, _sig_dir) in orders_submitted_this_run:
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

                    # ── PRE-FLIGHT GATES ──────────────────────────────────
                    # Balance gate: skip entries when no cash available
                    if _skip_entries_balance:
                        self._log_signal_decision(
                            session=session, signal=signal, strategy_name=strategy.name,
                            decision="REJECTED",
                            rejection_reason=f"Insufficient balance: ${_available_balance:.0f} < ${MINIMUM_ORDER_SIZE:.0f}",
                        )
                        signals_rejected += 1
                        continue

                    # Drawdown pause gate: block trend/momentum LONGs when portfolio is bleeding
                    if _in_drawdown_pause and _sig_dir == "LONG":
                        _strat_type = (strategy.metadata or {}).get('strategy_type', '') if strategy.metadata else ''
                        _strat_type_lower = str(_strat_type).lower().replace(' ', '_').replace('-', '_')
                        _is_trend_momentum = any(t in _strat_type_lower for t in _TREND_MOMENTUM_TYPES)
                        # Also check template name for trend/momentum keywords
                        _tmpl_name = (strategy.metadata or {}).get('template_name', '') if strategy.metadata else ''
                        _tmpl_lower = str(_tmpl_name).lower()
                        _is_trend_momentum = _is_trend_momentum or any(
                            kw in _tmpl_lower for kw in ['trend', 'momentum', 'breakout', 'ema ribbon', 'adx', 'vwap trend', 'atr dynamic']
                        )
                        if _is_trend_momentum:
                            self._log_signal_decision(
                                session=session, signal=signal, strategy_name=strategy.name,
                                decision="REJECTED",
                                rejection_reason=(
                                    f"Drawdown pause: portfolio unrealized={_portfolio_drawdown_pct:.1%} "
                                    f"— trend/momentum LONG blocked"
                                ),
                            )
                            signals_rejected += 1
                            continue

                    # Pullback gate: block trend/momentum LONGs during short-term pullbacks
                    if _pullback_state.get("in_pullback") and _sig_dir == "LONG":
                        _strat_type = (strategy.metadata or {}).get('strategy_type', '') if strategy.metadata else ''
                        _strat_type_lower = str(_strat_type).lower().replace(' ', '_').replace('-', '_')
                        _is_trend_momentum = any(t in _strat_type_lower for t in _TREND_MOMENTUM_TYPES)
                        _tmpl_name = (strategy.metadata or {}).get('template_name', '') if strategy.metadata else ''
                        _tmpl_lower = str(_tmpl_name).lower()
                        _is_trend_momentum = _is_trend_momentum or any(
                            kw in _tmpl_lower for kw in ['trend', 'momentum', 'breakout', 'ema ribbon', 'adx', 'vwap trend', 'atr dynamic']
                        )
                        # Severe pullbacks block all LONGs; mild/moderate only block trend/momentum
                        _severity = _pullback_state.get("severity", "none")
                        _block = _is_trend_momentum or _severity == "severe"
                        if _block:
                            self._log_signal_decision(
                                session=session, signal=signal, strategy_name=strategy.name,
                                decision="REJECTED",
                                rejection_reason=(
                                    f"Pullback gate ({_severity}): 5d={_pullback_state.get('change_5d', 0):.1%}, "
                                    f"RSI(5)={_pullback_state.get('rsi_5', 50):.0f} — "
                                    f"trend/momentum LONG blocked"
                                ),
                            )
                            signals_rejected += 1
                            continue

                    # Market quality gate: block trend/momentum LONGs when market is choppy
                    # Score < 40 (low grade) = ADX weak + high vol + inconsistent direction.
                    # Mean reversion, market-neutral, and SHORTs still run — they're designed
                    # for exactly these conditions. Only trend-following is paused.
                    if _mqs_block_trend and _sig_dir == "LONG":
                        _strat_type = (strategy.metadata or {}).get('strategy_type', '') if strategy.metadata else ''
                        _strat_type_lower = str(_strat_type).lower().replace(' ', '_').replace('-', '_')
                        _is_trend_momentum = any(t in _strat_type_lower for t in _TREND_MOMENTUM_TYPES)
                        _tmpl_name = (strategy.metadata or {}).get('template_name', '') if strategy.metadata else ''
                        _tmpl_lower = str(_tmpl_name).lower()
                        _is_trend_momentum = _is_trend_momentum or any(
                            kw in _tmpl_lower for kw in ['trend', 'momentum', 'breakout', 'ema ribbon', 'adx', 'vwap trend', 'atr dynamic']
                        )
                        if _is_trend_momentum:
                            self._log_signal_decision(
                                session=session, signal=signal, strategy_name=strategy.name,
                                decision="REJECTED",
                                rejection_reason=(
                                    f"Market quality gate: score={_mqs_score:.0f}/100 ({_mqs_grade}) — "
                                    f"choppy market, trend/momentum LONG blocked"
                                ),
                            )
                            signals_rejected += 1
                            continue
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
                    
                    # ── REGIME GATE: Block equity shorts in non-bearish markets ──
                    # Shorting individual stocks in a rising/ranging market is a losing
                    # game — you're fighting the tide. Only allow new SHORT entries when:
                    # (a) equity regime is clearly bearish (trending_down variants), OR
                    # (b) the specific symbol has strongly bearish news sentiment (< -0.5)
                    #     — bad news on a specific stock can justify a short even in a
                    #     rising market (earnings miss, scandal, guidance cut, etc.)
                    # Forex, commodity, and index shorts are allowed in all regimes.
                    if _sig_dir == "SHORT":
                        try:
                            from src.core.tradeable_instruments import (
                                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
                                DEMO_ALLOWED_ETFS,
                            )
                            _is_equity = (_sig_sym not in set(DEMO_ALLOWED_CRYPTO)
                                         and _sig_sym not in set(DEMO_ALLOWED_FOREX)
                                         and _sig_sym not in set(DEMO_ALLOWED_COMMODITIES)
                                         and _sig_sym not in set(DEMO_ALLOWED_INDICES))
                            if _is_equity:
                                _bearish_regimes = {'trending_down', 'trending_down_weak', 'trending_down_strong', 'high_volatility'}
                                _current_regime = 'unknown'
                                try:
                                    from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                                    _analyzer = MarketStatisticsAnalyzer(self._market_data)
                                    _sub_regime, _, _, _ = _analyzer.detect_sub_regime()
                                    _current_regime = _sub_regime.value.lower() if _sub_regime else 'unknown'
                                except Exception:
                                    pass
                                if _current_regime not in _bearish_regimes:
                                    # Check if symbol has strongly bearish news — override the regime gate
                                    _sentiment_override = False
                                    try:
                                        from src.data.news_sentiment_provider import get_news_sentiment_provider
                                        _sent_provider = get_news_sentiment_provider()
                                        if _sent_provider:
                                            _sent_score = _sent_provider.get_sentiment(_sig_sym)
                                            # Strongly bearish news (< -0.5) justifies shorting
                                            # even in a non-bearish market regime
                                            if _sent_score < -0.5:
                                                _sentiment_override = True
                                                logger.info(
                                                    f"Regime gate override: allowing {_sig_sym} SHORT "
                                                    f"despite {_current_regime} regime — "
                                                    f"news sentiment={_sent_score:.3f} (strongly bearish)"
                                                )
                                    except Exception:
                                        pass

                                    if not _sentiment_override:
                                        logger.info(
                                            f"Regime gate: blocking {_sig_sym} SHORT — equity regime "
                                            f"is '{_current_regime}' (not bearish). Only short equities "
                                            f"in trending_down/high_volatility regimes or on strongly bearish news."
                                        )
                                        self._log_signal_decision(
                                            session=session,
                                            signal=signal,
                                            strategy_name=strategy.name,
                                            decision="REJECTED",
                                            rejection_reason=f"Regime gate: equity SHORT blocked in {_current_regime} regime",
                                        )
                                        signals_rejected += 1
                                        continue
                        except Exception as _regime_err:
                            logger.debug(f"Regime gate check failed: {_regime_err}")

                    # ── SHORT CONCENTRATION LIMIT ──────────────────────────────────
                    # In non-bearish regimes, cap open equity shorts at 3 total.
                    # Correlated shorts amplify losses when the market moves against them.
                    # This prevents the April 13 scenario where 7 shorts were opened on
                    # the same day and all moved against us simultaneously.
                    if _sig_dir == "SHORT":
                        try:
                            from src.core.tradeable_instruments import (
                                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
                            )
                            _is_equity_short = (_sig_sym not in set(DEMO_ALLOWED_CRYPTO)
                                               and _sig_sym not in set(DEMO_ALLOWED_FOREX)
                                               and _sig_sym not in set(DEMO_ALLOWED_COMMODITIES)
                                               and _sig_sym not in set(DEMO_ALLOWED_INDICES))
                            if _is_equity_short:
                                _bearish_regimes = {'trending_down', 'trending_down_weak', 'trending_down_strong', 'high_volatility'}
                                _current_regime_for_conc = 'unknown'
                                try:
                                    from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                                    _analyzer2 = MarketStatisticsAnalyzer(self._market_data)
                                    _sub_regime2, _, _, _ = _analyzer2.detect_sub_regime()
                                    _current_regime_for_conc = _sub_regime2.value.lower() if _sub_regime2 else 'unknown'
                                except Exception:
                                    pass
                                if _current_regime_for_conc not in _bearish_regimes:
                                    # Count open equity shorts
                                    _open_equity_shorts = sum(
                                        1 for p in position_dataclasses
                                        if str(p.side).upper() in ('SHORT', 'SELL')
                                        and p.symbol.upper() not in set(DEMO_ALLOWED_CRYPTO)
                                        and p.symbol.upper() not in set(DEMO_ALLOWED_FOREX)
                                        and p.symbol.upper() not in set(DEMO_ALLOWED_COMMODITIES)
                                        and p.symbol.upper() not in set(DEMO_ALLOWED_INDICES)
                                        and p.closed_at is None
                                        and not getattr(p, 'pending_closure', False)
                                    )
                                    MAX_EQUITY_SHORTS_NON_BEARISH = 3
                                    if _open_equity_shorts >= MAX_EQUITY_SHORTS_NON_BEARISH:
                                        logger.info(
                                            f"Short concentration limit: blocking {_sig_sym} SHORT — "
                                            f"{_open_equity_shorts} equity shorts already open "
                                            f"(max {MAX_EQUITY_SHORTS_NON_BEARISH} in {_current_regime_for_conc} regime)"
                                        )
                                        self._log_signal_decision(
                                            session=session,
                                            signal=signal,
                                            strategy_name=strategy.name,
                                            decision="REJECTED",
                                            rejection_reason=f"Short concentration limit: {_open_equity_shorts} equity shorts open (max {MAX_EQUITY_SHORTS_NON_BEARISH} in non-bearish regime)",
                                        )
                                        signals_rejected += 1
                                        continue
                        except Exception as _conc_err:
                            logger.debug(f"Short concentration check failed: {_conc_err}")

                    # ── VIX PANIC FILTER: Block new LONG entries when VIX is spiking ──
                    # When VIX > 30 AND is >20% above its 10-day average, the market is
                    # in panic mode. New LONG entries in panic conditions have poor
                    # risk-adjusted returns — mean reversion is more likely than trend
                    # continuation. Wait for VIX to stabilize before entering new longs.
                    # Only applies to equity LONGs (not crypto, forex, commodities).
                    if _sig_dir == "LONG":
                        try:
                            from src.core.tradeable_instruments import (
                                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
                            )
                            _is_equity_long = (_sig_sym not in set(DEMO_ALLOWED_CRYPTO)
                                              and _sig_sym not in set(DEMO_ALLOWED_FOREX)
                                              and _sig_sym not in set(DEMO_ALLOWED_COMMODITIES)
                                              and _sig_sym not in set(DEMO_ALLOWED_INDICES))
                            if _is_equity_long:
                                from src.data.market_data_manager import get_market_data_manager
                                _mdm_vix = get_market_data_manager()
                                if _mdm_vix:
                                    from datetime import timedelta as _td_vix
                                    _vix_end = datetime.now()
                                    _vix_start = _vix_end - _td_vix(days=20)
                                    _vix_bars = _mdm_vix.get_historical_data("^VIX", _vix_start, _vix_end, interval="1d")
                                    if _vix_bars and len(_vix_bars) >= 5:
                                        _vix_closes = [b.close for b in _vix_bars if b.close]
                                        _vix_current = _vix_closes[-1]
                                        _vix_10d_avg = sum(_vix_closes[-10:]) / min(10, len(_vix_closes))
                                        if _vix_current > 30 and _vix_current > _vix_10d_avg * 1.20:
                                            logger.info(
                                                f"VIX panic filter: blocking {_sig_sym} LONG — "
                                                f"VIX={_vix_current:.1f} (>30 and {(_vix_current/_vix_10d_avg - 1)*100:.0f}% above 10d avg={_vix_10d_avg:.1f})"
                                            )
                                            self._log_signal_decision(
                                                session=session,
                                                signal=signal,
                                                strategy_name=strategy.name,
                                                decision="REJECTED",
                                                rejection_reason=f"VIX panic filter: VIX={_vix_current:.1f} (spiking, >30 and >20% above 10d avg)",
                                            )
                                            signals_rejected += 1
                                            continue
                        except Exception as _vix_err:
                            logger.debug(f"VIX panic filter check failed: {_vix_err}")

                    # ── YIELD CURVE INVERSION GATE: Suppress equity LONGs on inverted curve ──
                    # When the 2s10s spread (10Y - 2Y Treasury) is inverted (< 0), it signals
                    # recession risk. New equity LONG positions opened during inversion have
                    # historically underperformed. Gate: block new equity LONGs when 2s10s < -0.25%
                    # (sustained inversion, not just a brief dip).
                    # FRED data (T10Y2Y) is already available in our system.
                    if _sig_dir == "LONG":
                        try:
                            from src.core.tradeable_instruments import (
                                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
                                DEMO_ALLOWED_ETFS,
                            )
                            _is_equity_long2 = (_sig_sym not in set(DEMO_ALLOWED_CRYPTO)
                                               and _sig_sym not in set(DEMO_ALLOWED_FOREX)
                                               and _sig_sym not in set(DEMO_ALLOWED_COMMODITIES)
                                               and _sig_sym not in set(DEMO_ALLOWED_INDICES)
                                               and _sig_sym not in set(DEMO_ALLOWED_ETFS))
                            if _is_equity_long2:
                                from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                                _analyzer_yc = MarketStatisticsAnalyzer(self._market_data)
                                _macro = _analyzer_yc.get_market_context()
                                _yc_spread = None
                                if _macro and isinstance(_macro, dict):
                                    _fred_data = _macro.get("fred_data", {})
                                    _t10y2y = _fred_data.get("T10Y2Y")
                                    if _t10y2y is not None:
                                        _yc_spread = float(_t10y2y)
                                # Block if yield curve is deeply inverted (< -0.25%)
                                if _yc_spread is not None and _yc_spread < -0.25:
                                    logger.info(
                                        f"Yield curve gate: blocking {_sig_sym} LONG — "
                                        f"2s10s spread={_yc_spread:.2f}% (inverted, recession signal)"
                                    )
                                    self._log_signal_decision(
                                        session=session,
                                        signal=signal,
                                        strategy_name=strategy.name,
                                        decision="REJECTED",
                                        rejection_reason=f"Yield curve gate: 2s10s={_yc_spread:.2f}% (inverted)",
                                    )
                                    signals_rejected += 1
                                    continue
                        except Exception as _yc_err:
                            logger.debug(f"Yield curve gate check failed: {_yc_err}")

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
                                    elif 'trending_up' in regime_name:
                                        # In a bull market, size up longs and don't size up shorts
                                        # (shorts are already blocked by regime gate above)
                                        if _sig_dir == "LONG":
                                            multiplier = multipliers.get('trending_up_long', multipliers.get('trending', 1.25))
                                        else:
                                            multiplier = multipliers.get('trending', 1.0)
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
                                # Preserve signal metadata (market_regime, conviction_score,
                                # fundamentals, etc.) so async fill handlers can recover it
                                # when writing the trade_journal entry. Without this the
                                # market_regime column ends up NULL on 99.9% of rows.
                                order_metadata=(signal.metadata if isinstance(getattr(signal, 'metadata', None), dict) else None),
                            )
                            session.add(order_orm)
                            session.commit()
                            orders_executed += 1
                            
                            # Track this strategy+symbol+direction to prevent in-run duplicates
                            orders_submitted_this_run.add((strategy_id, _sig_sym, _sig_dir))
                            
                            # Track cumulative allocation
                            cumulative_allocated += validation_result.position_size

                            # ── PAIRS TRADING: Execute hedge leg ──────────────────────────
                            # If this signal is from a pairs trading strategy, immediately
                            # open the opposite leg on the partner symbol under the SAME
                            # strategy ID. Both legs are market-neutral together.
                            _pt_meta = signal.metadata or {}
                            _pt_partner = _pt_meta.get("pair_partner")
                            _pt_type = _pt_meta.get("template_type")
                            if _pt_partner and _pt_type == "pairs_trading":
                                try:
                                    from src.models.enums import SignalAction as _SA
                                    from src.models.dataclasses import TradingSignal as _TS

                                    # Hedge direction is opposite to primary leg
                                    if signal.action == _SA.ENTER_LONG:
                                        _hedge_action = _SA.ENTER_SHORT
                                        _hedge_dir = "SHORT"
                                    elif signal.action == _SA.ENTER_SHORT:
                                        _hedge_action = _SA.ENTER_LONG
                                        _hedge_dir = "LONG"
                                    else:
                                        _hedge_action = None

                                    if _hedge_action and (strategy_id, _pt_partner, _hedge_dir) not in orders_submitted_this_run:
                                        _hedge_signal = _TS(
                                            strategy_id=signal.strategy_id,
                                            symbol=_pt_partner,
                                            action=_hedge_action,
                                            confidence=signal.confidence,
                                            reasoning=f"Pairs Trading hedge leg: {_pt_partner} {_hedge_dir} (primary: {_sig_sym} {_sig_dir})",
                                            generated_at=datetime.now(),
                                            indicators=signal.indicators,
                                            metadata={
                                                **_pt_meta,
                                                "is_hedge_leg": True,
                                                "primary_symbol": _sig_sym,
                                                "pair_partner": _sig_sym,  # partner of hedge is the primary
                                            }
                                        )

                                        # Use same position size as primary leg
                                        _hedge_order = self._order_executor.execute_signal(
                                            signal=_hedge_signal,
                                            position_size=validation_result.position_size,
                                            stop_loss_pct=strategy.risk_params.stop_loss_pct,
                                            take_profit_pct=strategy.risk_params.take_profit_pct,
                                        )

                                        # Save hedge order to DB under same strategy
                                        _hedge_orm = OrderORM(
                                            id=_hedge_order.id,
                                            strategy_id=signal.strategy_id,
                                            symbol=_pt_partner,
                                            side=_hedge_order.side,
                                            order_type=_hedge_order.order_type,
                                            quantity=_hedge_order.quantity,
                                            status=_hedge_order.status,
                                            price=_hedge_order.price,
                                            stop_price=_hedge_order.stop_price,
                                            take_profit_price=_hedge_order.take_profit_price,
                                            submitted_at=_hedge_order.submitted_at or datetime.now(),
                                            filled_at=_hedge_order.filled_at,
                                            filled_price=_hedge_order.filled_price,
                                            filled_quantity=_hedge_order.filled_quantity,
                                            etoro_order_id=_hedge_order.etoro_order_id,
                                            expected_price=_hedge_order.expected_price,
                                            slippage=_hedge_order.slippage,
                                            fill_time_seconds=_hedge_order.fill_time_seconds,
                                            order_action='entry',
                                            # Preserve signal metadata so async fill handlers
                                            # populate trade_journal with template_name,
                                            # market_regime, etc. Same rationale as primary leg.
                                            order_metadata=(_hedge_signal.metadata if isinstance(getattr(_hedge_signal, 'metadata', None), dict) else None),
                                        )
                                        session.add(_hedge_orm)
                                        session.commit()

                                        orders_submitted_this_run.add((strategy_id, _pt_partner, _hedge_dir))
                                        cumulative_allocated += validation_result.position_size
                                        orders_executed += 1

                                        logger.info(
                                            f"Pairs Trading hedge leg executed: {_pt_partner} {_hedge_dir} "
                                            f"(strategy: {strategy.name}, primary: {_sig_sym} {_sig_dir})"
                                        )
                                except Exception as _hedge_err:
                                    logger.warning(f"Pairs Trading hedge leg failed for {_pt_partner}: {_hedge_err}")
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
                                    _t.sleep(3)  # eToro status endpoint has ~2-3s propagation delay after placement

                                    try:
                                        status_data = self._etoro_client.get_order_status(order.etoro_order_id)
                                    except Exception as _status_err:
                                        # 404 immediately after placement = propagation delay, not a real error
                                        # order_monitor will pick it up on next cycle
                                        logger.debug(f"Order {order.etoro_order_id} status not yet available (propagation delay): {_status_err}")
                                        status_data = None
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
                                            # Check if position already exists — match by eToro ID first,
                                            # then by strategy+symbol+side. Never match across strategies.
                                            from src.models.enums import OrderSide as OrderSideEnum
                                            pos_side = PositionSide.LONG if order.side == OrderSideEnum.BUY else PositionSide.SHORT
                                            
                                            # First: exact match by eToro position ID
                                            existing = session.query(PositionORM).filter(
                                                PositionORM.etoro_position_id == etoro_position_id,
                                            ).first()
                                            
                                            if not existing:
                                                # Second: match by strategy + symbol + side (same strategy only)
                                                existing = session.query(PositionORM).filter(
                                                    PositionORM.strategy_id == order.strategy_id,
                                                    PositionORM.symbol == order.symbol,
                                                    PositionORM.side == pos_side,
                                                    PositionORM.closed_at.is_(None),
                                                    PositionORM.etoro_position_id.is_(None),
                                                ).first()

                                            if existing:
                                                existing.etoro_position_id = etoro_position_id
                                                logger.info(f"Updated existing {order.symbol} position (strategy {order.strategy_id[:8]}) with eToro ID {etoro_position_id}")
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
                                                    invested_amount=order.quantity,  # order.quantity IS the dollar amount sent to eToro (/by-amount endpoint)
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
                            _emsg = str(e)
                            if "Market closed" in _emsg and "re-fire at next open" in _emsg:
                                logger.info(f"Signal deferred (market closed): {signal.symbol}")
                            else:
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

            # Exec-cycle summary line (2026-05-02 observability work).
            # Pulls recent decision-log aggregates so all gate-block / submit
            # counts are visible in one grep-able line, matching TSL cycle summaries.
            try:
                from src.models.database import get_database
                from src.models.orm import SignalDecisionORM
                from datetime import datetime as _dt, timedelta as _td
                from sqlalchemy import func as _sa_func
                _cutoff = _dt.now() - _td(minutes=10)
                _sess = get_database().get_session()
                try:
                    _rows = _sess.query(
                        SignalDecisionORM.stage,
                        _sa_func.count(SignalDecisionORM.id),
                    ).filter(SignalDecisionORM.timestamp >= _cutoff).group_by(SignalDecisionORM.stage).all()
                    _counts = {stg: int(n) for stg, n in _rows}
                finally:
                    _sess.close()
                logger.info(
                    "Exec cycle: "
                    f"proposed={_counts.get('proposed', 0)} "
                    f"wf_validated={_counts.get('wf_validated', 0)} "
                    f"wf_rejected={_counts.get('wf_rejected', 0)} "
                    f"gate_blocked={_counts.get('gate_blocked', 0)} "
                    f"order_submitted={_counts.get('order_submitted', 0)} "
                    f"orders_executed_this_run={orders_executed} "
                    f"rejected_this_run={signals_rejected}"
                )
            except Exception as _exec_err:
                logger.debug(f"Exec cycle summary failed (non-fatal): {_exec_err}")

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
                except Exception as _ttl_err:
                    logger.warning(f"Failed to load backtested_ttl_cycles from config: {_ttl_err}")

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

                    # ── Watchlist-trapped detection ──────────────────────────────────────
                    # If ALL of this strategy's signals this cycle were rejected as
                    # same-template duplicate, it's trapped — it only fires on symbols
                    # already occupied by the same template and can never trade.
                    # Retire immediately after 3 consecutive trapped cycles rather than
                    # waiting 48 cycles for the normal TTL.
                    total_this_cycle = _strategy_total_signals.get(sid, 0)
                    dup_this_cycle = _template_dup_rejected.get(sid, 0)
                    if total_this_cycle > 0 and dup_this_cycle == total_this_cycle:
                        # Every signal was a template-dup rejection
                        trapped_cycles = meta.get('template_trapped_cycles', 0) + 1
                        meta['template_trapped_cycles'] = trapped_cycles
                        s_orm.strategy_metadata = meta
                        if trapped_cycles >= 3:
                            s_orm.status = StrategyStatus.RETIRED
                            s_orm.retired_at = datetime.now()
                            expired_count += 1
                            logger.info(
                                f"  🚫 Retired BACKTESTED strategy {s_orm.name}: "
                                f"watchlist-trapped ({trapped_cycles} consecutive cycles "
                                f"with all signals rejected as same-template duplicate)"
                            )
                        continue
                    else:
                        # Not trapped this cycle — reset trapped counter
                        if meta.get('template_trapped_cycles', 0) > 0:
                            meta['template_trapped_cycles'] = 0
                            s_orm.strategy_metadata = meta

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

                # Build per-signal detail for cycle log
                _signal_details = []
                _order_details = []
                for _sid, _sigs in coordinated_results.items():
                    _strat = strategy_map.get(_sid, (None, None))[0]
                    _sname = _strat.name if _strat else _sid[:20]
                    for _sig in _sigs:
                        _signal_details.append({
                            'symbol': _sig.symbol,
                            'strategy': _sname,
                            'side': _sig.action.value if hasattr(_sig.action, 'value') else str(_sig.action),
                            'confidence': _sig.confidence,
                        })

                # Collect rejection reasons from result
                _rejection_details = []
                for _rej in result.get('coordination_rejections', []):
                    _rejection_details.append({
                        'symbol': _rej.get('symbol', '?'),
                        'strategy': _rej.get('strategy', '?'),
                        'reason': _rej.get('reason', '?'),
                    })

                get_cycle_logger().log_signal_cycle(
                    duration_seconds=duration,
                    strategies=result["active_strategies"],
                    signals=result["signals_coordinated"],
                    orders=orders_executed,
                    signal_details=_signal_details if _signal_details else None,
                    rejection_details=_rejection_details if _rejection_details else None,
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
        # Collect EXIT signals separately — they don't need coordination,
        # each strategy's exit is independent (close its own position)
        exit_signals = []  # [(strategy_id, signal, strategy_name)]

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
                elif signal.action in [SignalAction.EXIT_LONG, SignalAction.EXIT_SHORT]:
                    # Exit signals — collect for processing after entries
                    exit_signals.append((strategy_id, signal, strategy.name))
                    continue
                else:
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
        # Track strategies whose every signal was rejected as same-template duplicate.
        # These are "watchlist-trapped" — they only fire on occupied symbols and can never trade.
        _template_dup_rejected: dict = {}   # strategy_id -> count of template-dup rejections this cycle
        _strategy_total_signals: dict = {}  # strategy_id -> total signals this cycle
        symbol_limit_count = 0
        correlation_filtered_count = 0
        
        # Max strategies per symbol PER TIMEFRAME BUCKET (from risk config)
        # 1d BTC LONG, 4h BTC LONG, and 1h BTC LONG are different trades —
        # they capture different market dynamics and shouldn't compete for slots.
        # Buckets: "1d" (daily), "4h" (4-hour), "1h" (hourly/intraday)
        # Reduced from 5 to 2 — with larger positions ($5-10K each), having 5 strategies
        # on the same symbol in the same timeframe means $25-50K in one name.
        # 2 per timeframe (max 6 total across 1d/4h/1h) is the right limit for a
        # concentrated 40-60 position book.
        MAX_PER_SYMBOL_PER_TIMEFRAME = 2
        
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
            existing_positions_for_key = existing_positions_map.get(existing_key, [])
            
            # Build timeframe buckets for existing positions
            # Positions from strategies with interval_4h or intraday metadata go in their bucket
            existing_by_tf = {"1d": 0, "4h": 0, "1h": 0}
            for pos in existing_positions_for_key:
                tf = "1d"  # default
                if hasattr(pos, 'strategy_id') and pos.strategy_id:
                    strat_orm = strategy_map.get(pos.strategy_id, (None, None))
                    if strat_orm:
                        s, _ = strat_orm
                        if s and s.metadata:
                            if s.metadata.get('intraday') and not s.metadata.get('interval_4h'):
                                tf = "1h"
                            elif s.metadata.get('interval_4h'):
                                tf = "4h"
                existing_by_tf[tf] += 1
            
            # Group incoming signals by timeframe
            signals_by_tf = {"1d": [], "4h": [], "1h": []}
            for strategy_id, signal, strategy_name in signal_list:
                tf = "1d"
                strategy, _ = strategy_map.get(strategy_id, (None, None))
                if strategy and strategy.metadata:
                    if strategy.metadata.get('intraday') and not strategy.metadata.get('interval_4h'):
                        tf = "1h"
                    elif strategy.metadata.get('interval_4h'):
                        tf = "4h"
                signals_by_tf[tf].append((strategy_id, signal, strategy_name))
            
            # Process each timeframe bucket independently
            for tf, tf_signals in signals_by_tf.items():
                if not tf_signals:
                    continue
                
                existing_count = existing_by_tf.get(tf, 0)
                current_pending_count = pending_orders_per_symbol.get((normalized_symbol, direction), 0)
                # Approximate: split pending count proportionally (not perfect but avoids over-blocking)
                total_active = existing_count
                remaining_slots = MAX_PER_SYMBOL_PER_TIMEFRAME - total_active
                
                if remaining_slots <= 0:
                    for strategy_id, signal, strategy_name in tf_signals:
                        self._log_coordination_rejection(
                            signal=signal,
                            strategy_name=strategy_name,
                            rejection_reason=f"Symbol limit: {total_active} existing {direction} {tf} position(s) in {normalized_symbol} (max: {MAX_PER_SYMBOL_PER_TIMEFRAME})",
                        )
                    position_duplicate_count += len(tf_signals)
                    continue
                
                # Same-strategy dedup within this timeframe bucket.
                # Also dedup same-template-name: RSI Dip Buy V24 and RSI Dip Buy V120
                # are the same signal logic — only one should enter per symbol per cycle.
                existing_strategy_ids = set()
                existing_template_names = set()
                if existing_count > 0:
                    for pos in existing_positions_for_key:
                        if hasattr(pos, 'strategy_id') and pos.strategy_id:
                            existing_strategy_ids.add(pos.strategy_id)
                            # Also collect template names from existing positions
                            strat_tuple = strategy_map.get(pos.strategy_id, (None, None))
                            if strat_tuple[0] and strat_tuple[0].metadata:
                                tmpl = strat_tuple[0].metadata.get('template_name')
                                if tmpl:
                                    existing_template_names.add(tmpl)
                    
                    new_signals = []
                    for strategy_id, signal, strategy_name in tf_signals:
                        if strategy_id in existing_strategy_ids:
                            # Allow re-entry by the same strategy if the existing position
                            # is still within its SL range (loss < SL%). The signal fired
                            # again — the thesis is intact and we can scale in.
                            # Block only if the position is already at/near the SL boundary.
                            allow_reentry = False
                            for pos in existing_positions_for_key:
                                if not (hasattr(pos, 'strategy_id') and pos.strategy_id == strategy_id):
                                    continue
                                if not pos.entry_price or pos.entry_price <= 0:
                                    continue
                                if not pos.current_price or pos.current_price <= 0:
                                    continue
                                # Price-based loss (same as health check)
                                pos_side = str(getattr(pos, 'side', 'LONG')).upper()
                                if 'LONG' in pos_side or 'BUY' in pos_side:
                                    pos_loss = (pos.entry_price - pos.current_price) / pos.entry_price
                                else:
                                    pos_loss = (pos.current_price - pos.entry_price) / pos.entry_price
                                # Get SL% for this position — use the actual stop_loss on the position
                                # (set at order time with ATR floor), not the strategy's default.
                                # Fall back to strategy risk_params if position has no SL.
                                pos_sl_pct = 0.06  # default stock SL
                                if pos.stop_loss and pos.entry_price and pos.entry_price > 0:
                                    pos_sl_pct = abs(pos.entry_price - pos.stop_loss) / pos.entry_price
                                else:
                                    strat_tuple = strategy_map.get(strategy_id, (None, None))
                                    if strat_tuple[0] and hasattr(strat_tuple[0], 'risk_params') and strat_tuple[0].risk_params:
                                        rp = strat_tuple[0].risk_params
                                        # risk_params can be a dataclass or dict
                                        if hasattr(rp, 'stop_loss_pct'):
                                            pos_sl_pct = rp.stop_loss_pct or 0.06
                                        elif isinstance(rp, dict):
                                            pos_sl_pct = rp.get('stop_loss_pct', 0.06)

                                # Allow re-entry only if loss is less than 50% of SL distance.
                                # Rationale: if we're already 50%+ into the SL, the trade is
                                # failing — adding more doubles down into a losing position.
                                # At <50% consumed, it's normal noise and the thesis is intact.
                                sl_consumed = pos_loss / pos_sl_pct if pos_sl_pct > 0 else 1.0
                                if sl_consumed < 0.50:
                                    allow_reentry = True
                                    logger.debug(
                                        f"Re-entry allowed: {strategy_name} on {normalized_symbol} "
                                        f"(SL consumed {sl_consumed:.0%} < 50% — thesis intact)"
                                    )
                                else:
                                    logger.info(
                                        f"Re-entry blocked: {strategy_name} on {normalized_symbol} "
                                        f"(SL consumed {sl_consumed:.0%} ≥ 50% — position failing, "
                                        f"loss={pos_loss:.1%}, SL={pos_sl_pct:.1%})"
                                    )
                                break

                            if allow_reentry:
                                new_signals.append((strategy_id, signal, strategy_name))
                                logger.debug(
                                    f"Re-entry allowed: {strategy_name} on {normalized_symbol} "
                                    f"(existing position within SL range)"
                                )
                            else:
                                self._log_coordination_rejection(
                                    signal=signal,
                                    strategy_name=strategy_name,
                                    rejection_reason=f"Same-strategy duplicate: already has {direction} position in {normalized_symbol}",
                                )
                                position_duplicate_count += 1
                        else:
                            new_signals.append((strategy_id, signal, strategy_name))
                    
                    if not new_signals:
                        continue
                    tf_signals = new_signals

                # Same-template dedup within incoming signals (not yet in existing positions).
                # Prevents RSI Dip Buy V24 and RSI Dip Buy V120 both entering the same symbol
                # in the same cycle — they're the same logic, not independent alpha.
                # Also blocks new signals if an existing open position already uses the same template.
                # Keep only the highest-confidence signal per template name.
                seen_template_names: dict = {}  # template_name -> (strategy_id, signal, strategy_name)
                template_deduped = []
                for strategy_id, signal, strategy_name in tf_signals:
                    strat, _ = strategy_map.get(strategy_id, (None, None))
                    tmpl = (strat.metadata or {}).get('template_name') if strat and strat.metadata else None

                    # Block if an existing open position already uses this template on this symbol
                    if tmpl and existing_template_names and tmpl in existing_template_names:
                        self._log_coordination_rejection(
                            signal=signal,
                            strategy_name=strategy_name,
                            rejection_reason=f"Same-template duplicate: {tmpl} already has open position in {normalized_symbol}",
                        )
                        position_duplicate_count += 1
                        _template_dup_rejected[strategy_id] = _template_dup_rejected.get(strategy_id, 0) + 1
                        _strategy_total_signals[strategy_id] = _strategy_total_signals.get(strategy_id, 0) + 1
                        continue

                    if tmpl and tmpl in seen_template_names:
                        # Keep the higher-confidence one
                        existing_entry = seen_template_names[tmpl]
                        if signal.confidence > existing_entry[1].confidence:
                            self._log_coordination_rejection(
                                signal=existing_entry[1],
                                strategy_name=existing_entry[2],
                                rejection_reason=f"Same-template duplicate: {tmpl} already queued for {normalized_symbol} (lower confidence)",
                            )
                            _template_dup_rejected[existing_entry[0]] = _template_dup_rejected.get(existing_entry[0], 0) + 1
                            _strategy_total_signals[existing_entry[0]] = _strategy_total_signals.get(existing_entry[0], 0) + 1
                            seen_template_names[tmpl] = (strategy_id, signal, strategy_name)
                        else:
                            self._log_coordination_rejection(
                                signal=signal,
                                strategy_name=strategy_name,
                                rejection_reason=f"Same-template duplicate: {tmpl} already queued for {normalized_symbol} (lower confidence)",
                            )
                            _template_dup_rejected[strategy_id] = _template_dup_rejected.get(strategy_id, 0) + 1
                            _strategy_total_signals[strategy_id] = _strategy_total_signals.get(strategy_id, 0) + 1
                    else:
                        if tmpl:
                            seen_template_names[tmpl] = (strategy_id, signal, strategy_name)
                        _strategy_total_signals[strategy_id] = _strategy_total_signals.get(strategy_id, 0) + 1
                        template_deduped.append((strategy_id, signal, strategy_name))

                # Rebuild from seen_template_names to ensure we have the winners
                tf_signals = list(seen_template_names.values()) if seen_template_names else template_deduped
                if not tf_signals:
                    continue
                
                # Filter signals that already have pending orders
                # Same-strategy dedup only: a strategy can't double-order the same symbol/direction
                filtered_signals = []
                for strategy_id, signal, strategy_name in tf_signals:
                    pending_key = (strategy_id, normalized_symbol, direction)
                    if pending_key in pending_orders_map:
                        pending_count = len(pending_orders_map[pending_key])
                        logger.info(
                            f"Pending order check: {strategy_name} already has {pending_count} pending "
                            f"{direction} order(s) for {normalized_symbol}, filtering signal"
                        )
                        pending_order_duplicate_count += 1
                        continue
                    filtered_signals.append((strategy_id, signal, strategy_name))
                
                if not filtered_signals:
                    continue
                
                if len(filtered_signals) == 1:
                    strategy_id, signal, _ = filtered_signals[0]
                    if strategy_id not in coordinated_results:
                        coordinated_results[strategy_id] = []
                    coordinated_results[strategy_id].append(signal)
                else:
                    logger.info(
                        f"Signal coordination: {len(filtered_signals)} strategies want to trade {normalized_symbol} {direction} {tf} "
                        f"({remaining_slots} slot(s) available)"
                    )

                    # Sort by confidence (highest first)
                    filtered_signals.sort(key=lambda x: x[1].confidence, reverse=True)

                    # Keep top N signals based on remaining slots
                    slots_to_fill = min(remaining_slots, len(filtered_signals))
                    kept_signals = filtered_signals[:slots_to_fill]
                    dropped_signals = filtered_signals[slots_to_fill:]

                    for strategy_id, signal, strategy_name in kept_signals:
                        if strategy_id not in coordinated_results:
                            coordinated_results[strategy_id] = []
                        coordinated_results[strategy_id].append(signal)
                        logger.info(
                            f"  ✅ Kept: {strategy_name} (confidence={signal.confidence:.2f})"
                        )

                    for strategy_id, signal, strategy_name in dropped_signals:
                        logger.info(
                            f"  ❌ Filtered: {strategy_name} (confidence={signal.confidence:.2f}) "
                            f"- max {MAX_PER_SYMBOL_PER_TIMEFRAME} positions per symbol/{tf} reached"
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
                f"(would exceed max {MAX_PER_SYMBOL_PER_TIMEFRAME} strategies per symbol/timeframe)"
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

        # Add EXIT signals to coordinated results — they bypass coordination
        # because each strategy's exit is independent (close its own position)
        if exit_signals:
            logger.info(f"Exit signals: {len(exit_signals)} strategy exit signals to process")
            for strategy_id, signal, strategy_name in exit_signals:
                if strategy_id not in coordinated_results:
                    coordinated_results[strategy_id] = []
                coordinated_results[strategy_id].append(signal)
                logger.info(
                    f"  Exit signal: {strategy_name} → {signal.action.value} {signal.symbol} "
                    f"(confidence: {signal.confidence:.2f})"
                )

        return coordinated_results, _strategy_total_signals, _template_dup_rejected

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
        """Persist a signal decision (accepted/rejected) to the database and broadcast via WebSocket.

        Observability unification (2026-05-04):
          The AlphaCent observability layer had TWO parallel decision tables
          that did not know about each other:
            - `signal_decisions` (SignalDecisionORM) — the funnel, written
              by `decision_log.record_decision` from proposer, portfolio
              manager, and order executor.
            - `signal_decision_log` (SignalDecisionLogORM) — legacy, written
              ONLY by this function (and `_log_coordination_rejection`).
          Result: coordinator + validator rejections never appeared in the
          funnel. The UI, analytics endpoints, and diagnostic queries had
          to union the two tables OR miss half the decisions.

          Fix: dual-write. Every call here also emits a row to the unified
          `signal_decisions` table via `decision_log.record_decision`.
          The legacy write is kept for the audit trail / signals widget
          read compatibility until those readers are migrated (same commit).
          After a deprecation window the legacy write + table will be
          dropped.

          Mapping from legacy → unified:
            decision=ACCEPTED → stage='order_submitted', decision='accepted'
            decision=REJECTED → stage='gate_blocked',   decision='rejected'
        """
        # ─── Legacy write (kept temporarily — see docstring) ───────────────
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

        # ─── Unified write to the canonical funnel table ──────────────────
        # This is the table the rest of the system (proposer, WF, portfolio
        # manager, order executor, analytics) writes to. Without this second
        # write, coordinator/validator rejections were invisible to the
        # funnel — the screen your user sees was reconciling 3 tables that
        # didn't agree. See docstring for full context.
        try:
            from src.analytics.decision_log import record_decision

            action_val = signal.action.value if hasattr(signal.action, 'value') else str(signal.action)
            direction = (
                "long"
                if ('LONG' in action_val or 'BUY' in action_val)
                else "short"
                if ('SHORT' in action_val or 'SELL' in action_val)
                else None
            )
            # Decision taxonomy in the unified table:
            #   'gate_blocked'    — any block between signal emission and
            #                        order submission (coordination dedup,
            #                        symbol cap, risk validation failure)
            #   'order_submitted' — signal passed validation and made it
            #                        onto the order-submit queue
            # The unified funnel reader aggregates these plus the
            # upstream stages (proposed / wf_validated / activated /
            # signal_emitted / order_filled) for complete visibility.
            if str(decision).upper() == "ACCEPTED":
                unified_stage = "order_submitted"
                unified_decision = "accepted"
            else:
                unified_stage = "gate_blocked"
                unified_decision = "rejected"

            _template_name = None
            _confidence = None
            try:
                _confidence = float(signal.confidence) if signal.confidence is not None else None
            except (TypeError, ValueError):
                _confidence = None
            # Template name from signal metadata when available
            _sig_meta = getattr(signal, 'metadata', None)
            if isinstance(_sig_meta, dict):
                _template_name = _sig_meta.get('template_name')

            record_decision(
                stage=unified_stage,
                decision=unified_decision,
                strategy_id=signal.strategy_id,
                template=_template_name or strategy_name,
                symbol=signal.symbol,
                direction=direction,
                score=_confidence,
                reason=rejection_reason,
                metadata={
                    "strategy_name": strategy_name,
                    "confidence": _confidence,
                    "action": action_val,
                    "source": "trading_scheduler._log_signal_decision",
                },
            )
        except Exception as e:
            # Never raise — analytics writes must not break trading.
            logger.debug(f"Failed to mirror signal decision to unified funnel: {e}")

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
            from src.data.market_hours_manager import get_market_hours_manager
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
            # Prefer the shared singleton if already initialized by monitoring service
            from src.data.market_data_manager import get_market_data_manager
            _shared_mdm = get_market_data_manager()
            if _shared_mdm is not None:
                self._market_data = _shared_mdm
                logger.info("TradingScheduler: using shared MarketDataManager singleton")
            self._websocket_manager = get_websocket_manager()
            self._strategy_engine = StrategyEngine(None, self._market_data, self._websocket_manager)
            
            risk_config = config.load_risk_config(TradingMode.DEMO)
            self._risk_manager = RiskManager(risk_config)
            
            market_hours = get_market_hours_manager()
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
