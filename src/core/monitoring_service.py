"""
Monitoring service for order and position tracking.

This service runs 24/7 independently of the trading state (ACTIVE/PAUSED).
It ensures the database always has fresh data from eToro without blocking
the frontend or requiring API calls from the Orders endpoint.

Key responsibilities:
- Process pending orders (submit to eToro)
- Check submitted orders (update status from eToro)
- Sync positions (update prices and P&L from eToro)
- Check trailing stops (update stop-loss levels)
- Check fundamental exits (daily — earnings miss, revenue decline, sector rotation)

Architecture principle: Monitoring ≠ Trading Decisions
- MonitoringService: Always running, keeps database fresh
- TradingScheduler: Only runs when ACTIVE, generates signals and executes orders
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import yaml

from src.api.etoro_client import EToroAPIClient
from src.core.order_monitor import OrderMonitor
from src.models.database import Database

logger = logging.getLogger(__name__)


class MonitoringService:
    """
    Background service for monitoring orders and positions.
    
    Runs independently of trading state to ensure database is always fresh.
    """
    
    def __init__(
        self,
        etoro_client: EToroAPIClient,
        db: Optional[Database] = None,
        pending_orders_interval: int = 5,
        order_status_interval: int = 30,
        position_sync_interval: int = 60,
        trailing_stops_interval: int = 60
    ):
        """
        Initialize monitoring service.
        
        Args:
            etoro_client: eToro API client
            db: Database instance (creates new if not provided)
            pending_orders_interval: Seconds between pending order checks (default: 5s)
            order_status_interval: Seconds between order status checks (default: 30s)
            position_sync_interval: Seconds between position syncs (default: 60s)
            trailing_stops_interval: Seconds between trailing stop checks (default: 60s — aligned with position sync price updates)
        """
        self.etoro_client = etoro_client
        self.db = db or Database()
        self.order_monitor = OrderMonitor(etoro_client, self.db)
        
        # Configurable intervals
        self.pending_orders_interval = pending_orders_interval
        self.order_status_interval = order_status_interval
        self.position_sync_interval = position_sync_interval
        self.trailing_stops_interval = trailing_stops_interval
        
        # State tracking
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_pending_check: float = 0
        self._last_order_check: float = 0
        self._last_position_sync: float = 0
        self._last_trailing_check: float = 0
        import time as _time_init
        self._last_fundamental_check: float = _time_init.time()  # Skip first fundamental check on startup
        self._last_pending_closure_check: float = _time_init.time()  # Skip first pending closure check on startup
        
        # Load fundamental monitoring config
        self._fundamental_config = self._load_fundamental_config()
        self._fundamental_check_interval = self._fundamental_config.get(
            'check_interval_hours', 24
        ) * 3600  # Convert hours to seconds
        
        # Pending closure processing interval (same as position sync)
        self._pending_closure_interval = position_sync_interval  # 60s default
        
        # Stale order cleanup (runs daily alongside fundamental checks)
        self._last_stale_order_check: float = 0
        self._stale_order_config = self._load_stale_order_config()
        
        # Partial exit check (same interval as trailing stops)
        self._last_partial_exit_check: float = 0
        
        # Time-based exit check (daily — alongside fundamental exits)
        self._last_time_based_exit_check: float = 0
        
        # Daily sync job (data cleanup, performance feedback, daily summary)
        self._last_daily_sync: float = 0
        self._daily_sync_interval = 24 * 3600  # 24 hours
        
        # Trailing stop eToro update rate limiting
        # Track last eToro API update timestamp per position (in-memory, doesn't need to survive restarts)
        self._trailing_stop_last_etoro_update: Dict[str, float] = {}  # position_id -> timestamp
        self._trailing_stop_rate_limit_seconds: int = 300  # Max 1 update per position per 5 minutes
        
        # Scheduled autonomous cycle
        self._last_scheduled_cycle_check: float = 0
        self._scheduled_cycle_check_interval = 60  # Check every 60s if it's time to run
        self._last_scheduled_cycle_time: Optional[datetime] = None
        self._schedule_config = self._load_schedule_config()

        # Regime-change tracking — retire BACKTESTED strategies that are incompatible
        # with the new regime so they don't fire signals into the wrong market.
        # Checked every 30 minutes alongside strategy health/decay.
        self._last_known_regime: Optional[str] = None
        self._last_regime_check: float = 0
        self._regime_check_interval = 1800  # 30 minutes

        # Alert evaluation (every 60s)
        self._last_alert_check: float = 0
        self._alert_check_interval = 60
        
        # Hourly price data sync — pre-fetches market data into cache so signal
        # generation and manual cycles don't have to hit Yahoo Finance every time.
        # Runs every ~55 minutes (just before the :05 signal generation run).
        self._last_price_sync: float = 0  # Run on first loop iteration (in background thread)
        self._price_sync_interval = 3300  # 55 minutes
        self._price_sync_retry_interval = 300  # 5 minutes — retry after skip
        self._price_sync_completed = False  # Flag for manual sync status polling (Data Management page)
        self._background_sync_completed = False  # Flag for trading scheduler — only set by automatic background sync
        
        # 10-minute quick price update: fetches latest eToro quotes for active
        # strategy symbols and runs lightweight signal check
        self._last_quick_price_update: float = 0
        self._quick_price_interval = 600  # 10 minutes
        self._last_quick_update_result: Optional[dict] = None
        
        # Background threads for heavy data operations — never block the monitoring loop
        import threading as _bg_threading
        self._price_update_thread: Optional[_bg_threading.Thread] = None
        self._full_sync_thread: Optional[_bg_threading.Thread] = None
        
        # WebSocket manager for real-time price broadcasting
        from src.api.websocket_manager import get_websocket_manager
        self._ws_manager = get_websocket_manager()
        
        logger.info(
            f"MonitoringService initialized (pending: {pending_orders_interval}s, "
            f"orders: {order_status_interval}s, positions: {position_sync_interval}s, "
            f"trailing: {trailing_stops_interval}s, "
            f"fundamental: {self._fundamental_check_interval}s)"
        )
    
    def _sync_broadcast_market_data(self, symbol: str, price: float) -> None:
        """Broadcast a market data price tick via WebSocket from sync context (fire-and-forget)."""
        if not self._ws_manager:
            return
        try:
            import asyncio
            data = {
                "symbol": symbol,
                "price": price,
                "timestamp": datetime.now().isoformat(),
            }
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(
                    self._ws_manager.broadcast_market_data_update(symbol, data),
                    loop=loop,
                )
            except RuntimeError:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._ws_manager.broadcast_market_data_update(symbol, data)
                )
                loop.close()
        except Exception:
            pass  # Fire-and-forget — never block monitoring

    def _is_symbol_market_open(self, symbol: str) -> bool:
        """Check if the market is open for a given symbol.
        
        Returns True for crypto (24/7), True for forex on weekdays,
        True for stocks/ETFs during eToro extended hours (Mon-Fri 4AM-8PM ET).
        """
        try:
            import pytz
            from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX
            from src.utils.symbol_normalizer import normalize_symbol
            
            sym = normalize_symbol(symbol).upper()
            
            if sym in set(DEMO_ALLOWED_CRYPTO):
                return True  # 24/7
            
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            is_weekend = now_et.weekday() >= 5
            
            if sym in set(DEMO_ALLOWED_FOREX):
                return not is_weekend  # Mon-Fri 24h
            
            # Stocks, ETFs, indices, commodities: eToro extended hours
            return not is_weekend and 4 <= now_et.hour < 20
        except Exception:
            return True  # If we can't determine, don't block
    
    def _any_market_open(self) -> bool:
        """Check if ANY market is open (crypto is always open, so this always returns True).
        Used to decide if the monitoring loop should run at full speed or reduced."""
        return True  # Crypto is 24/7, so there's always something to monitor
    
    def _is_stock_market_open(self) -> bool:
        """Check if US stock market is open (eToro extended hours)."""
        try:
            import pytz
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            return now_et.weekday() < 5 and 4 <= now_et.hour < 20
        except Exception:
            return True
    
    async def start(self):
        """Start the monitoring service."""
        if self._running:
            logger.warning("MonitoringService already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("MonitoringService started - running 24/7 regardless of trading state")
    
    async def stop(self):
        """Stop the monitoring service."""
        if not self._running:
            logger.warning("MonitoringService not running")
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("MonitoringService stopped")
    
    async def _run_loop(self):
        """Main monitoring loop - runs continuously."""
        logger.info("MonitoringService loop started")
        
        # Use the fastest interval as the loop interval
        loop_interval = min(
            self.pending_orders_interval,
            self.order_status_interval,
            self.position_sync_interval,
            self.trailing_stops_interval
        )
        
        while self._running:
            try:
                await self._run_monitoring_cycle()
                
                # Wait for next interval
                await asyncio.sleep(loop_interval)
            
            except asyncio.CancelledError:
                logger.info("MonitoringService loop cancelled")
                break
            
            except Exception as e:
                logger.error(f"Error in MonitoringService loop: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(loop_interval)
    
    async def _run_monitoring_cycle(self):
        """
        Run one monitoring cycle.
        
        Checks different operations at different intervals:
        - Pending orders: Every 5s (immediate submission)
        - Order status: Every 30s (with caching)
        - Position sync: Every 60s (with caching)
        - Trailing stops: Every 60s (aligned with position sync — no point checking stale prices)
        """
        now = time.time()
        
        # Check if an autonomous cycle is running — pause non-essential operations
        # to avoid interfering (e.g., submitting orders mid-proposal stage)
        cycle_running = False
        try:
            from src.api.routers.strategies import _running_cycle_thread
            cycle_running = _running_cycle_thread is not None and _running_cycle_thread.is_alive()
        except ImportError:
            pass
        
        if cycle_running:
            # During autonomous cycle: only run alerts (trailing stops disabled — eToro
            # doesn't support modifying SL/TP on open positions via API)
            if now - self._last_alert_check >= self._alert_check_interval:
                try:
                    self._evaluate_alerts()
                    self._last_alert_check = now
                except Exception as e:
                    logger.error(f"Error evaluating alerts: {e}")
            
            return  # Skip all other monitoring operations
        
        # Process pending orders (fast path - immediate submission)
        if now - self._last_pending_check >= self.pending_orders_interval:
            try:
                pending_results = self.order_monitor.process_pending_orders()
                if pending_results["submitted"] > 0:
                    logger.info(f"Pending orders: {pending_results['submitted']} submitted")
                self._last_pending_check = now
            except Exception as e:
                logger.error(f"Error processing pending orders: {e}")
        
        # Check order status (medium path - with caching)
        if now - self._last_order_check >= self.order_status_interval:
            try:
                order_results = self.order_monitor.check_submitted_orders()
                if order_results["filled"] > 0 or order_results["cancelled"] > 0:
                    logger.info(
                        f"Order status: {order_results['filled']} filled, "
                        f"{order_results['cancelled']} cancelled"
                    )
                self._last_order_check = now
            except Exception as e:
                logger.error(f"Error checking order status: {e}")
        
        # Sync positions (medium path - with caching)
        if now - self._last_position_sync >= self.position_sync_interval:
            try:
                position_results = self.order_monitor.sync_positions()
                logger.debug(
                    f"Position sync: {position_results['updated']} updated, "
                    f"{position_results['created']} created"
                )
                self._last_position_sync = now
            except Exception as e:
                logger.error(f"Error syncing positions: {e}")
        
        # Check trailing stops (DB-only — eToro doesn't support SL modification)
        # Updates stop levels in DB and flags positions that breach their stop for closure.
        if now - self._last_trailing_check >= self.trailing_stops_interval:
            try:
                trailing_results = self._check_trailing_stops()
                if trailing_results["updated"] > 0 or trailing_results.get("breach_closures", 0) > 0:
                    logger.info(
                        f"Trailing stops: {trailing_results['updated']} updated in DB, "
                        f"{trailing_results.get('breach_closures', 0)} breach closures flagged"
                    )
                self._last_trailing_check = now
            except Exception as e:
                logger.error(f"Error checking trailing stops: {e}")

        # Bull market short closure: flag open equity shorts for closure when regime
        # is clearly bullish. Runs every 5 minutes (same as trailing stops).
        # This handles the case where shorts were opened before a regime shift.
        if now - self._last_trailing_check < 2:  # Run right after trailing stops
            try:
                self._close_shorts_in_bull_market()
            except Exception as e:
                logger.error(f"Error in bull market short closure check: {e}")
        
        # Position-level health checks (same interval as trailing stops)
        # Flags individual bad positions for closure — independent of strategy.
        if now - self._last_trailing_check < 2:  # Run right after trailing stops
            try:
                health_results = self._check_position_health_individual()
                flagged = health_results.get("flagged", 0)
                if flagged > 0:
                    logger.info(f"Position health: {flagged} positions flagged for closure")
            except Exception as e:
                logger.error(f"Error checking position health: {e}")
        
        # Check partial exits (same interval as trailing stops - every 5s, DB-only price check)
        if now - self._last_partial_exit_check >= self.trailing_stops_interval:
            try:
                partial_results = self._check_partial_exits()
                triggered = partial_results.get("triggered", 0)
                if triggered > 0:
                    logger.info(
                        f"Partial exits: {triggered} partial close orders submitted, "
                        f"{partial_results.get('failed', 0)} failed"
                    )
                self._last_partial_exit_check = now
            except Exception as e:
                logger.error(f"Error checking partial exits: {e}")
        
        # Check fundamental exits (daily - fundamentals don't change intraday)
        # Skip if autonomous cycle is running — both hit FMP and compete for GIL
        _cycle_active = False
        try:
            from src.api.routers.strategies import _running_cycle_thread
            if _running_cycle_thread and _running_cycle_thread.is_alive():
                _cycle_active = True
        except ImportError:
            pass
        
        if not _cycle_active and now - self._last_fundamental_check >= self._fundamental_check_interval:
            try:
                fundamental_results = self._check_fundamental_exits()
                flagged = fundamental_results.get("flagged", 0)
                if flagged > 0:
                    logger.info(f"Fundamental exits: {flagged} positions flagged for closure")
                else:
                    logger.debug(f"Fundamental exits: checked {fundamental_results.get('checked', 0)} positions, none flagged")
                self._last_fundamental_check = now
            except Exception as e:
                logger.error(f"Error checking fundamental exits: {e}")
        
        # Cleanup stale orders (daily - alongside fundamental check)
        if not _cycle_active and now - self._last_stale_order_check >= self._fundamental_check_interval:
            try:
                stale_results = self._cleanup_stale_orders()
                cancelled = stale_results.get("cancelled", 0)
                if cancelled > 0:
                    logger.info(f"Stale order cleanup: {cancelled} orders cancelled")
                self._last_stale_order_check = now
            except Exception as e:
                logger.error(f"Error cleaning up stale orders: {e}")
        
        # Check time-based exits for intraday strategies (every 5 min)
        # Intraday strategies have hold limits in hours (e.g., 24h), so checking once
        # per day (the old behavior) means missing the window by up to 24 hours.
        # Run frequently for intraday, keep daily for non-intraday.
        _intraday_exit_interval = 300  # 5 minutes
        if not _cycle_active and now - self._last_time_based_exit_check >= _intraday_exit_interval:
            try:
                time_exit_results = self._check_time_based_exits()
                flagged = time_exit_results.get("flagged", 0)
                if flagged > 0:
                    logger.info(f"Time-based exits: {flagged} positions flagged for closure (max hold exceeded)")
                else:
                    logger.debug(f"Time-based exits: checked {time_exit_results.get('checked', 0)} positions, none exceeded")
                self._last_time_based_exit_check = now
            except Exception as e:
                logger.error(f"Error checking time-based exits: {e}")
        
            # Demote idle DEMO strategies back to BACKTESTED
            try:
                self._demote_idle_strategies()
            except Exception as e:
                logger.error(f"Error demoting idle strategies: {e}")
            
            # Check live strategy health — retire consistent losers
            try:
                health_results = self._check_strategy_health()
                if health_results.get("retired", 0) > 0:
                    logger.info(
                        f"Strategy health: retired {health_results['retired']} "
                        f"underperforming strategies"
                    )
            except Exception as e:
                logger.error(f"Error checking strategy health: {e}")
            
            # Check strategy edge decay — retire expired edges
            try:
                decay_results = self._check_strategy_decay()
                if decay_results.get("retired", 0) > 0:
                    logger.info(
                        f"Strategy decay: retired {decay_results['retired']} "
                        f"expired-edge strategies"
                    )
            except Exception as e:
                logger.error(f"Error checking strategy decay: {e}")

            # Retire BACKTESTED strategies incompatible with current regime
            if now - self._last_regime_check >= self._regime_check_interval:
                try:
                    regime_results = self._retire_regime_incompatible_backtested()
                    self._last_regime_check = now
                except Exception as e:
                    logger.error(f"Error in regime-incompatible retirement: {e}")
        
        # Process pending closures (every 60s - auto-close positions flagged for closure)
        if now - self._last_pending_closure_check >= self._pending_closure_interval:
            try:
                closure_results = self._process_pending_closures()
                submitted = closure_results.get("submitted", 0)
                failed = closure_results.get("failed", 0)
                skipped = closure_results.get("skipped", 0)
                if submitted > 0 or failed > 0:
                    logger.info(
                        f"Pending closures: {submitted} close orders submitted, "
                        f"{failed} failed, {skipped} skipped (already attempted or max retries)"
                    )
                self._last_pending_closure_check = now
            except Exception as e:
                logger.error(f"Error processing pending closures: {e}")

            # Demote idle DEMO strategies (runs every 60s alongside pending closures)
            try:
                self._demote_idle_strategies()
            except Exception as e:
                logger.error(f"Error demoting idle strategies: {e}")

        # Daily sync job (runs once per day after market close)
        if now - self._last_daily_sync >= self._daily_sync_interval:
            try:
                self._run_daily_sync()
                self._last_daily_sync = now
            except Exception as e:
                logger.error(f"Error in daily sync: {e}")

        # Log circuit breaker states if any are non-CLOSED, and actively probe half-open breakers
        try:
            cb_states = self.etoro_client.get_circuit_breaker_states()
            open_breakers = {
                k: v for k, v in cb_states.items() if v.get("state") != "closed"
            }
            if open_breakers:
                # Only log every 60s to avoid spam (breakers are checked every 5s)
                if not hasattr(self, '_last_cb_log_time') or (now - self._last_cb_log_time) >= 60:
                    logger.warning(f"Circuit breaker states: {open_breakers}")
                    self._last_cb_log_time = now

                # Actively probe half-open breakers so they don't stay stuck forever.
                # A half_open breaker allows one request through — if nothing triggers
                # an order/position API call naturally, the breaker stays half_open
                # indefinitely. We probe by calling a lightweight read-only endpoint.
                for category, state_info in open_breakers.items():
                    if state_info.get("state") == "half_open":
                        try:
                            if category == "orders":
                                # Probe with a positions read (lightweight, read-only)
                                # This tests eToro API connectivity without side effects
                                self.etoro_client.get_positions()
                                # If it succeeded, manually close the orders breaker too
                                # since the underlying eToro API is reachable
                                self.etoro_client._record_success("orders")
                                logger.info(f"Circuit breaker [{category}]: probe succeeded via positions read — closing")
                            elif category == "positions":
                                self.etoro_client.get_positions()
                                # record_success is called inside get_positions already
                            elif category == "market_data":
                                # Probe with a simple market data call
                                self.etoro_client.get_market_data("AAPL")
                        except Exception as probe_err:
                            logger.debug(f"Circuit breaker [{category}] probe failed: {probe_err}")
        except Exception as e:
            logger.debug(f"Could not read circuit breaker states: {e}")

        # Check if it's time to run a scheduled autonomous cycle
        if now - self._last_scheduled_cycle_check >= self._scheduled_cycle_check_interval:
            try:
                self._check_scheduled_cycle()
                self._last_scheduled_cycle_check = now
            except Exception as e:
                logger.error(f"Error checking scheduled cycle: {e}")

        # Evaluate alert thresholds (every 60s alongside position sync)
        if now - self._last_alert_check >= self._alert_check_interval:
            try:
                alert_results = self._evaluate_alerts()
                triggered = alert_results.get("triggered", 0)
                if triggered > 0:
                    logger.info(f"Alerts: {triggered} alerts triggered")
                self._last_alert_check = now
            except Exception as e:
                logger.error(f"Error evaluating alerts: {e}")

        # 10-minute quick price update: fetch eToro quotes for active strategy symbols
        # and run lightweight signal check — runs in background thread to never block monitoring
        if now - self._last_quick_price_update >= self._quick_price_interval:
            # Only launch if previous thread finished (or never started)
            if self._price_update_thread is None or not self._price_update_thread.is_alive():
                if not cycle_running:
                    import threading as _t
                    self._price_update_thread = _t.Thread(
                        target=self._bg_quick_price_update,
                        name="bg-price-update",
                        daemon=True,
                    )
                    self._price_update_thread.start()
                self._last_quick_price_update = now
            else:
                logger.debug("Skipping quick price update — previous run still active")

        # Hourly price data sync — pre-warm cache for signal generation
        # Runs in background thread to never block monitoring
        _cycle_active_sync = False
        try:
            from src.api.routers.strategies import _running_cycle_thread
            if _running_cycle_thread and _running_cycle_thread.is_alive():
                _cycle_active_sync = True
        except ImportError:
            pass
        
        if now - self._last_price_sync >= self._price_sync_interval:
            if _cycle_active_sync:
                # Autonomous cycle running — retry sooner instead of waiting full interval
                logger.debug("Full price sync skipped — autonomous cycle running, will retry in 5m")
                self._last_price_sync = now - self._price_sync_interval + self._price_sync_retry_interval
            elif self._full_sync_thread is None or not self._full_sync_thread.is_alive():
                import threading as _t
                self._full_sync_thread = _t.Thread(
                    target=self._bg_full_price_sync,
                    name="bg-full-sync",
                    daemon=True,
                )
                self._full_sync_thread.start()
                self._last_price_sync = now
            else:
                logger.debug("Skipping full price sync — previous run still active")
    
    def _bg_quick_price_update(self) -> None:
        """Background thread wrapper for quick price update + signal generation.
        
        Runs _quick_price_update() in a daemon thread so the monitoring loop
        is never blocked. Respects the DB cycle lock and running cycle thread.
        """
        try:
            logger.info("[bg-price-update] Starting quick price update in background thread")
            self._quick_price_update()
        except Exception as e:
            logger.error(f"[bg-price-update] Background quick price update failed: {e}")

    def _bg_full_price_sync(self) -> None:
        """Background thread wrapper for full price data sync.
        
        Runs _sync_price_data() in a daemon thread so the monitoring loop
        is never blocked. Safe to run alongside the monitoring loop since it
        only writes to the price cache and historical_price_cache table.
        """
        try:
            logger.info("[bg-full-sync] Starting full price sync in background thread")
            self._sync_price_data()
            logger.info("[bg-full-sync] Full price sync completed")
        except Exception as e:
            logger.error(f"[bg-full-sync] Background full price sync failed: {e}")

    def _quick_price_update(self) -> None:
        """
        Fetch latest eToro quotes for active strategy symbols and run
        lightweight signal check. Runs every 10 minutes between hourly syncs.
        
        Flow:
        1. Get active strategy symbols from DB
        2. Fetch current price from eToro for each (fast — ~1s per symbol)
        3. Update the latest bar in the in-memory HistoricalDataCache
        4. Run signal generation for active strategies using the updated data
        """
        import time as _time
        t0 = _time.time()
        
        try:
            from src.models.orm import StrategyORM
            from src.models.enums import StrategyStatus
            from src.data.market_data_manager import get_historical_cache
            import json
            
            hist_cache = get_historical_cache()
            
            # Get active + backtested strategy symbols (both need fresh prices for signal gen)
            session = self.db.get_session()
            active_symbols = set()
            try:
                active = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE, StrategyStatus.BACKTESTED])
                ).all()
                for s in active:
                    if s.symbols:
                        try:
                            sym_list = json.loads(s.symbols) if isinstance(s.symbols, str) else s.symbols
                            if isinstance(sym_list, list):
                                active_symbols.update(sym_list)  # Full watchlist
                        except (json.JSONDecodeError, TypeError):
                            pass
            finally:
                session.close()
            
            if not active_symbols:
                logger.info("Quick price update: no active strategies — nothing to update")
                self._last_quick_update_result = {
                    "updated": 0,
                    "errors": 0,
                    "symbols_checked": 0,
                    "elapsed_s": 0,
                    "timestamp": datetime.now().isoformat(),
                    "skipped_reason": "no_active_strategies",
                }
                return
            
            # Per-symbol market hours check
            # eToro offers 24/5 trading on most instruments. Only skip weekends.
            import pytz
            try:
                from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                crypto_set = set(DEMO_ALLOWED_CRYPTO)
                et_tz = pytz.timezone('US/Eastern')
                now_et = datetime.now(et_tz)
                is_weekend = now_et.weekday() >= 5
            except Exception:
                crypto_set = set()
                is_weekend = False
            
            # Batch fetch all prices in a single eToro API call
            from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
            from src.models import MarketData, DataSource
            
            symbols_to_fetch = [s for s in active_symbols 
                               if s.upper() in crypto_set or not is_weekend]
            
            # Build instrument ID map for batch request
            sym_to_iid = {}
            for sym in symbols_to_fetch:
                iid = SYMBOL_TO_INSTRUMENT_ID.get(sym)
                if iid is not None:
                    sym_to_iid[sym] = iid
            
            # Fetch all prices in one call
            live_prices = {}
            if sym_to_iid:
                try:
                    ids_str = ",".join(str(iid) for iid in sym_to_iid.values())
                    response = self.etoro_client._session.get(
                        f"{self.etoro_client.PUBLIC_URL}/sapi/trade-real/rates?instrumentIds={ids_str}",
                        timeout=self.etoro_client.timeout,
                    )
                    if response.status_code == 200:
                        iid_to_sym = {iid: sym for sym, iid in sym_to_iid.items()}
                        for rate in response.json().get("Rates", []):
                            iid = rate.get("InstrumentID")
                            sym = iid_to_sym.get(iid)
                            if sym:
                                ask = float(rate.get("Ask", 0))
                                bid = float(rate.get("Bid", 0))
                                mid = (ask + bid) / 2 if ask > 0 and bid > 0 else ask or bid
                                if mid > 0:
                                    live_prices[sym] = mid
                    else:
                        logger.warning(f"[bg-price-update] Batch rates returned {response.status_code}")
                except Exception as exc:
                    logger.warning(f"[bg-price-update] Batch rates failed: {exc}")
            
            # Update cache with fetched prices
            updated = 0
            errors = 0
            now_dt = datetime.now()
            current_hour = now_dt.replace(minute=0, second=0, microsecond=0)
            
            for symbol, price in live_prices.items():
                try:
                    for interval in ['1h', '1d']:
                        cache_key = f"{symbol}:{interval}:{'25' if interval == '1h' else '120'}"
                        cached_data = hist_cache.get(cache_key)
                        if cached_data and len(cached_data) > 0:
                            last_bar = cached_data[-1]
                            last_bar_hour = last_bar.timestamp.replace(minute=0, second=0, microsecond=0) if last_bar.timestamp else None
                            
                            if interval == '1h' and last_bar_hour and current_hour > last_bar_hour:
                                new_bar = MarketData(
                                    symbol=last_bar.symbol, timestamp=current_hour,
                                    open=price, high=price, low=price, close=price,
                                    volume=0, source=last_bar.source,
                                )
                                cached_data.append(new_bar)
                                hist_cache.set(cache_key, cached_data)
                                try:
                                    from src.utils.symbol_mapper import normalize_symbol
                                    norm_sym = normalize_symbol(symbol)
                                    if hasattr(self, '_market_data') and self._market_data:
                                        self._market_data._save_historical_to_db(norm_sym, [new_bar], interval)
                                except Exception:
                                    pass
                            else:
                                updated_bar = MarketData(
                                    symbol=last_bar.symbol, timestamp=last_bar.timestamp,
                                    open=last_bar.open, high=max(last_bar.high, price),
                                    low=min(last_bar.low, price), close=price,
                                    volume=last_bar.volume, source=last_bar.source,
                                )
                                cached_data[-1] = updated_bar
                                hist_cache.set(cache_key, cached_data)
                                try:
                                    from src.utils.symbol_mapper import normalize_symbol
                                    norm_sym = normalize_symbol(symbol)
                                    if hasattr(self, '_market_data') and self._market_data:
                                        self._market_data._save_historical_to_db(norm_sym, [updated_bar], interval)
                                except Exception:
                                    pass
                    updated += 1
                    
                    # Broadcast price tick via WebSocket (fire-and-forget)
                    self._sync_broadcast_market_data(symbol, price)
                    
                except Exception as e:
                    logger.debug(f"Cache update failed for {symbol}: {e}")
                    errors += 1
            
            elapsed = _time.time() - t0
            
            self._last_quick_update_result = {
                "updated": updated,
                "errors": errors,
                "symbols_checked": len(active_symbols),
                "elapsed_s": round(elapsed, 1),
                "timestamp": datetime.now().isoformat(),
            }
            
            if updated > 0:
                logger.info(
                    f"Quick price update: {updated} symbols updated in {elapsed:.1f}s "
                    f"({errors} errors)"
                )
                
                # Run lightweight signal generation after price update
                # Skip if the trading scheduler ran signal generation recently (< 5 min ago)
                # to avoid duplicate signal runs showing up in the cycle log
                try:
                    import time as _sig_time
                    from src.core.trading_scheduler import get_trading_scheduler
                    scheduler = get_trading_scheduler()
                    if scheduler and hasattr(scheduler, 'run_signal_generation_sync'):
                        # Check if scheduler ran recently (including startup reconciliation)
                        last_run = getattr(scheduler, '_last_signal_check', 0)
                        seconds_since_last = _sig_time.time() - last_run if last_run else 0
                        
                        # Also skip if reconciliation hasn't completed yet (startup race)
                        reconciliation_done = getattr(scheduler, '_reconciliation_done', False)
                        
                        if not reconciliation_done:
                            logger.info("[bg-price-update] Skipping signal gen — startup reconciliation not complete")
                        elif seconds_since_last < 300:
                            logger.debug(
                                f"[bg-price-update] Skipping signal gen — scheduler ran {seconds_since_last:.0f}s ago"
                            )
                        else:
                            # Skip if manual cycle holds the DB lock
                            _skip_signal = False
                            try:
                                from src.api.routers.strategies import _db_cycle_lock
                                if not _db_cycle_lock.acquire(blocking=False):
                                    logger.info("Skipping quick signal gen — DB lock held by manual cycle")
                                    _skip_signal = True
                                else:
                                    _db_cycle_lock.release()  # Release immediately — just checking
                            except ImportError:
                                pass
                            
                            if not _skip_signal:
                                result = scheduler.run_signal_generation_sync()
                                signals = result.get('signals_coordinated', 0)
                                orders = result.get('orders_submitted', 0)
                                if signals > 0 or orders > 0:
                                    logger.info(
                                        f"[bg-price-update] Signal check: {signals} signals, {orders} orders"
                                    )
                            
                            # Cycle logger already called by trading_scheduler.run_signal_generation_sync()
                            # No need to log again here — was causing duplicate [SIGNAL-1H] entries
                except Exception as e:
                    logger.warning(f"[bg-price-update] Signal generation failed: {e}")
            
        except Exception as e:
            logger.error(f"Quick price update failed: {e}")

    def _sync_price_data(self) -> None:
        """
        Pre-fetch and cache market price data for all tradeable symbols.
        
        Tiered sync strategy:
        - Tier 1 (always): Crypto + forex — trade 24/7 or 24/5. Sync 1h + 1d.
        - Tier 2 (market hours only): Stocks, ETFs, indices, commodities — sync 1h + 1d
          during US market hours, 1d only outside hours.
        - Active strategy boost: symbols with active strategies get loaded into
          in-memory HistoricalDataCache for instant signal generation access.
        
        All data persisted to DB. Active strategy data also loaded into memory.
        """
        import time as _time
        t0 = _time.time()
        
        try:
            from src.core.tradeable_instruments import (
                DEMO_ALL_TRADEABLE, DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
            )
            from src.models.orm import StrategyORM
            from src.models.enums import StrategyStatus
            from src.data.market_data_manager import MarketDataManager, get_historical_cache
            import pytz
            import json
            
            crypto_set = set(DEMO_ALLOWED_CRYPTO)
            forex_set = set(DEMO_ALLOWED_FOREX)
            all_symbols = list(DEMO_ALL_TRADEABLE)
            hist_cache = get_historical_cache()
            
            # Determine market hours — eToro offers 24/5 on most instruments
            try:
                et_tz = pytz.timezone('US/Eastern')
                now_et = datetime.now(et_tz)
                is_weekend = now_et.weekday() >= 5
            except Exception:
                is_weekend = False
            
            # Get active + backtested strategy symbols for in-memory boost
            active_symbols = set()
            session = self.db.get_session()
            try:
                active = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE, StrategyStatus.BACKTESTED])
                ).all()
                for s in active:
                    if s.symbols:
                        try:
                            sym_list = json.loads(s.symbols) if isinstance(s.symbols, str) else s.symbols
                            if isinstance(sym_list, list):
                                active_symbols.update(sym_list)
                        except (json.JSONDecodeError, TypeError):
                            pass
            finally:
                session.close()
            
            # Initialize market data manager (singleton — shared across all components)
            if not hasattr(self, '_market_data') or self._market_data is None:
                import yaml
                from pathlib import Path
                config = {}
                config_path = Path("config/autonomous_trading.yaml")
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        config = yaml.safe_load(f) or {}
                self._market_data = MarketDataManager(self.etoro_client, config=config)
                # Register as the process-wide singleton so all other components share
                # the same cache instead of creating empty instances
                from src.data.market_data_manager import set_market_data_manager
                set_market_data_manager(self._market_data)
            md = self._market_data
            
            end = datetime.now()
            stats = {"1h": 0, "1d": 0, "errors": 0, "memory_loaded": 0, "db_cached": 0, "yahoo_batch": 0}
            
            # Phase 1: Check DB cache for each symbol, collect those needing Yahoo fetch
            need_yahoo_1d = []  # symbols that need fresh 1d data
            need_yahoo_1h = []  # symbols that need fresh 1h data
            
            from src.utils.symbol_mapper import to_yahoo_ticker, normalize_symbol
            from src.models import MarketData, DataSource
            
            for symbol in all_symbols:
                sym_upper = symbol.upper()
                is_crypto = sym_upper in crypto_set
                is_forex = sym_upper in forex_set
                is_always_on = is_crypto or is_forex
                is_active = symbol in active_symbols
                
                if not (is_always_on or not is_weekend):
                    continue  # Skip weekend-only symbols on weekends
                
                try:
                    # Check DB cache for 1d — use _get_historical_from_db directly
                    # to avoid falling through to Yahoo (Phase 2 handles that in batch).
                    start_1d = end - timedelta(days=220)
                    db_data_1d = md._get_historical_from_db(normalize_symbol(symbol), start_1d, end, "1d")
                    if db_data_1d and len(db_data_1d) > 10:
                        stats["1d"] += 1
                        stats["db_cached"] += 1
                        if is_active:
                            hist_cache.set(f"{symbol}:1d:120", db_data_1d)
                            stats["memory_loaded"] += 1
                    else:
                        need_yahoo_1d.append(symbol)
                except Exception as e:
                    logger.debug(f"DB cache check failed for {symbol} 1d: {e}")
                    need_yahoo_1d.append(symbol)
                
                try:
                    # For the full hourly sync, ALWAYS fetch fresh 1h data from Yahoo
                    # for crypto and active symbols. The DB cache may have stale bars
                    # from hours ago — the whole point of this sync is to refresh them.
                    # Daily bars are fine from DB (they only change once per day).
                    start_1h = end - timedelta(days=180)
                    if is_always_on or is_active:
                        # Force Yahoo fetch for crypto/forex/active symbols
                        need_yahoo_1h.append(symbol)
                    else:
                        # For inactive non-24/7 symbols, check DB directly (no Yahoo fallback)
                        db_data_1h = md._get_historical_from_db(normalize_symbol(symbol), start_1h, end, "1h")
                        if db_data_1h and len(db_data_1h) > 10:
                            stats["1h"] += 1
                            stats["db_cached"] += 1
                        else:
                            need_yahoo_1h.append(symbol)
                except Exception as e:
                    logger.debug(f"DB cache check failed for {symbol} 1h: {e}")
                    need_yahoo_1h.append(symbol)
            
            # Phase 2: Batch fetch from Yahoo Finance for symbols that missed DB cache
            import yfinance as yf
            
            # Initialize yfinance cache before batch download (thread-safe, once only)
            from src.data.market_data_manager import ensure_yfinance_cache
            ensure_yfinance_cache()
            
            for interval, need_list, start_dt, period_hint in [
                ("1d", need_yahoo_1d, end - timedelta(days=220), "220d"),
                ("1h", need_yahoo_1h, end - timedelta(days=180), "180d"),
            ]:
                if not need_list:
                    continue

                # Filter out symbols that only have reliable daily data
                # (e.g., LME metals like ZINC, ALUMINUM, PLATINUM)
                if interval != "1d":
                    from src.utils.symbol_mapper import DAILY_ONLY_SYMBOLS
                    need_list = [s for s in need_list if s.upper() not in DAILY_ONLY_SYMBOLS]
                    if not need_list:
                        continue
                
                # Convert to Yahoo tickers
                sym_to_yf = {sym: to_yahoo_ticker(sym) for sym in need_list}
                yf_tickers = list(set(sym_to_yf.values()))
                
                logger.info(f"[bg-full-sync] Batch Yahoo download: {len(yf_tickers)} symbols for {interval}")
                
                try:
                    batch_data = yf.download(
                        yf_tickers,
                        start=start_dt,
                        end=end,
                        interval=interval,
                        group_by='ticker',
                        progress=False,
                        threads=True,
                    )
                    
                    if batch_data.empty:
                        logger.warning(f"[bg-full-sync] Yahoo batch returned empty for {interval}")
                        continue
                    
                    # Parse batch response — structure depends on single vs multi ticker
                    yf_to_sym = {}
                    for sym, yf_t in sym_to_yf.items():
                        yf_to_sym.setdefault(yf_t, []).append(sym)
                    
                    is_multi = len(yf_tickers) > 1
                    
                    for yf_ticker in yf_tickers:
                        try:
                            if is_multi:
                                if yf_ticker not in batch_data.columns.get_level_values(0):
                                    continue
                                ticker_data = batch_data[yf_ticker].dropna(how='all')
                            else:
                                ticker_data = batch_data.dropna(how='all')
                            
                            if ticker_data.empty:
                                continue
                            
                            # Convert to MarketData objects for each of our symbols that map to this Yahoo ticker
                            for our_symbol in yf_to_sym.get(yf_ticker, []):
                                data_list = []
                                for ts, row in ticker_data.iterrows():
                                    try:
                                        o = float(row.get('Open', 0))
                                        h = float(row.get('High', 0))
                                        l = float(row.get('Low', 0))
                                        c = float(row.get('Close', 0))
                                        v = float(row.get('Volume', 0))
                                        if c > 0:
                                            data_list.append(MarketData(
                                                symbol=our_symbol,
                                                timestamp=ts.to_pydatetime().replace(tzinfo=None),
                                                open=o, high=h, low=l, close=c, volume=v,
                                                source=DataSource.YAHOO_FINANCE,
                                            ))
                                    except (ValueError, TypeError):
                                        continue
                                
                                if data_list:
                                    data_list.sort(key=lambda d: d.timestamp)
                                    norm_sym = normalize_symbol(our_symbol)
                                    md._save_historical_to_db(norm_sym, data_list, interval)
                                    
                                    if interval == "1d":
                                        stats["1d"] += 1
                                    else:
                                        stats["1h"] += 1
                                    stats["yahoo_batch"] += 1
                                    
                                    is_active = our_symbol in active_symbols
                                    if is_active:
                                        cache_key = f"{our_symbol}:{interval}:{'120' if interval == '1d' else '25'}"
                                        hist_cache.set(cache_key, data_list)
                                        stats["memory_loaded"] += 1
                        
                        except Exception as e:
                            logger.debug(f"[bg-full-sync] Failed to parse {yf_ticker}: {e}")
                            stats["errors"] += 1
                
                except Exception as e:
                    logger.warning(f"[bg-full-sync] Yahoo batch download failed for {interval}: {e}")
                    stats["errors"] += len(need_list)
            
            elapsed = _time.time() - t0
            logger.info(
                f"Price data sync complete: {stats['1d']} daily + {stats['1h']} hourly symbols "
                f"synced in {elapsed:.1f}s ({stats['db_cached']} from DB cache, "
                f"{stats['yahoo_batch']} from Yahoo batch, {stats['memory_loaded']} loaded to memory, "
                f"{stats['errors']} errors, {len(active_symbols)} active strategy symbols)"
            )
            
            # Signal to trading scheduler that fresh data is ready
            # Only the background automatic sync sets this flag — manual syncs don't
            self._background_sync_completed = True
            self._price_sync_completed = True

            # Trigger news sentiment sync after first price sync (populates DB on startup)
            if not getattr(self, '_news_sentiment_synced_once', False):
                try:
                    self._sync_news_sentiment()
                    self._news_sentiment_synced_once = True
                except Exception as _e:
                    logger.debug(f"News sentiment startup sync failed: {_e}")
            
        except Exception as e:
            logger.error(f"Price data sync failed: {e}")
            # Still signal completion so signal gen doesn't wait forever
            self._background_sync_completed = True
            self._price_sync_completed = True

    def _run_daily_sync(self) -> None:
        """
        Daily maintenance job — runs once per day.
        
        Consolidates all daily tasks:
        1. Data cleanup (retention policy)
        2. Performance feedback update
        3. Log daily summary
        
        Historical price sync and FMP cache warming are handled by their
        own schedules (DB-first caching in MarketDataManager and FMPCacheWarmer).
        Data quality validation is cached in DB with 24h TTL.
        """
        logger.info("=" * 60)
        logger.info("DAILY SYNC: Running daily maintenance tasks")
        logger.info("=" * 60)
        
        # 1. Data cleanup (retention policy)
        try:
            import yaml
            from pathlib import Path
            from src.models.database import cleanup_stale_data
            
            config_path = Path("config/autonomous_trading.yaml")
            cleanup_config = {}
            if config_path.exists():
                with open(config_path, 'r') as f:
                    cleanup_config = yaml.safe_load(f) or {}
            
            if cleanup_config.get('data_management', {}).get('cleanup_enabled', True):
                cleanup_results = cleanup_stale_data(cleanup_config)
                total_cleaned = sum(cleanup_results.values())
                if total_cleaned > 0:
                    logger.info(f"  Data cleanup: {total_cleaned} stale records removed")
                else:
                    logger.info("  Data cleanup: no stale records found")
        except Exception as e:
            logger.warning(f"  Data cleanup failed (non-critical): {e}")
        
        # 2. Update performance feedback from trade journal
        try:
            from src.analytics.trade_journal import TradeJournal
            journal = TradeJournal(self.db)
            feedback = journal.get_performance_feedback(lookback_days=60, min_trades=5)
            if feedback.get('has_sufficient_data'):
                logger.info(
                    f"  Performance feedback: {feedback.get('total_trades', 0)} trades analyzed, "
                    f"slippage avg: {feedback.get('slippage_analytics', {}).get('avg_slippage_pct', 0):.4%}"
                )
            else:
                logger.info("  Performance feedback: insufficient data for analysis")
        except Exception as e:
            logger.warning(f"  Performance feedback update failed (non-critical): {e}")
        
        # 3. Log daily summary
        try:
            from src.models.orm import StrategyORM, PositionORM, OrderORM
            from src.models.enums import StrategyStatus, OrderStatus
            
            session = self.db.get_session()
            try:
                active_count = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
                ).count()
                open_positions = session.query(PositionORM).filter(
                    PositionORM.closed_at.is_(None)
                ).count()
                pending_orders = session.query(OrderORM).filter(
                    OrderORM.status == OrderStatus.PENDING
                ).count()
                
                positions_note = ""
                if active_count == 0 and open_positions > 0:
                    positions_note = f" (orphaned from retired strategies)"
                
                logger.info(
                    f"  Daily summary: {active_count} active strategies, "
                    f"{open_positions} open positions{positions_note}, {pending_orders} pending orders"
                )
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"  Daily summary failed: {e}")
        
        logger.info("DAILY SYNC: Complete")
        logger.info("=" * 60)
        
        # 4. Save daily equity snapshot for accurate P&L period calculations
        try:
            self._save_equity_snapshot()
        except Exception as e:
            logger.warning(f"  Equity snapshot failed (non-critical): {e}")

        # 5. News sentiment background sync (priority queue, respects 100 req/day)
        try:
            self._sync_news_sentiment()
        except Exception as e:
            logger.warning(f"  News sentiment sync failed (non-critical): {e}")
    
    def _save_equity_snapshot(self) -> None:
        """Save end-of-day equity snapshot.
        
        Stores current equity, balance, unrealized P&L, and cumulative realized P&L
        so the overview page can compute accurate period P&L:
        - Today = current_equity - yesterday's snapshot equity
        - This Week = current_equity - last Sunday's snapshot equity
        - This Month = current_equity - last day of previous month's snapshot equity
        """
        from src.models.orm import EquitySnapshotORM, PositionORM, AccountInfoORM
        from sqlalchemy import func
        
        session = self.db.get_session()
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            # Get current account state
            account = session.query(AccountInfoORM).first()
            if not account:
                logger.warning("  Equity snapshot: no account info found")
                return
            
            equity = account.equity or account.balance
            balance = account.balance
            
            # Current unrealized P&L
            unrealized = sum(
                p.unrealized_pnl or 0
                for p in session.query(PositionORM).filter(
                    PositionORM.closed_at.is_(None)
                ).all()
            )
            
            # Cumulative realized P&L (all time)
            realized_cum = float(
                session.query(func.sum(PositionORM.realized_pnl)).filter(
                    PositionORM.closed_at.isnot(None)
                ).scalar() or 0
            )
            
            positions_count = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).count()
            
            # Upsert: update if today's snapshot exists, insert if not
            existing = session.query(EquitySnapshotORM).filter_by(date=today_str).first()
            if existing:
                existing.equity = equity
                existing.balance = balance
                existing.unrealized_pnl = unrealized
                existing.realized_pnl_cumulative = realized_cum
                existing.positions_count = positions_count
            else:
                snapshot = EquitySnapshotORM(
                    date=today_str,
                    equity=equity,
                    balance=balance,
                    unrealized_pnl=unrealized,
                    realized_pnl_cumulative=realized_cum,
                    positions_count=positions_count,
                    created_at=datetime.now(),
                )
                session.add(snapshot)
            
            session.commit()
            logger.info(
                f"  Equity snapshot saved: {today_str} equity=${equity:,.2f} "
                f"balance=${balance:,.2f} unrealized=${unrealized:,.2f} "
                f"realized_cum=${realized_cum:,.2f} positions={positions_count}"
            )
        except Exception as e:
            session.rollback()
            logger.warning(f"  Equity snapshot save failed: {e}")
        finally:
            session.close()
    
    def _check_trailing_stops(self) -> dict:
        """
        Check trailing stops for all open positions.

        Calculates new stop-loss values from DB data, updates the DB.
        eToro API does NOT support modifying SL/TP on open positions, so
        trailing stops are enforced DB-side: this method updates the stop
        level, and _check_stop_loss_breaches() (called separately) closes
        positions that breach their stop.

        Returns:
            Dictionary with counts of updated stops
        """

        session = self.db.get_session()

        try:
            from src.models.orm import PositionORM
            from src.models.dataclasses import Position

            # Get all open positions from database
            open_positions_orm = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).all()

            if not open_positions_orm:
                return {"updated": 0, "etoro_updated": 0, "etoro_rate_limited": 0}

            # Convert ORM to dataclass, skipping positions whose market is closed
            open_positions = []
            skipped_market_closed = 0
            for pos_orm in open_positions_orm:
                if not self._is_symbol_market_open(pos_orm.symbol):
                    skipped_market_closed += 1
                    continue
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

            # Capture old stop_loss values before the check
            old_stop_losses = {pos.id: pos.stop_loss for pos in open_positions}

            # Check trailing stops (calculates new stop_loss values on Position objects)
            # PositionManager handles the calculation; we handle eToro updates with rate limiting.
            self.order_monitor.position_manager.check_trailing_stops(open_positions, skip_etoro_update=True)

            # Update database with new stop-loss values and push to eToro with rate limiting
            updated_count = 0
            now = time.time()

            for pos in open_positions:
                pos_orm = session.query(PositionORM).filter_by(id=pos.id).first()
                if pos_orm and pos_orm.stop_loss != pos.stop_loss:
                    old_sl = pos_orm.stop_loss
                    pos_orm.stop_loss = pos.stop_loss
                    updated_count += 1
                    logger.debug(
                        f"Trailing stop updated (DB) for {pos.symbol}: "
                        f"{old_sl} -> {pos.stop_loss:.2f}"
                    )

            session.commit()

            # Check for stop-loss breaches — close positions where current price
            # has breached the DB stop-loss. This is the enforcement mechanism since
            # eToro API doesn't support modifying SL on open positions.
            breach_count = 0
            for pos in open_positions:
                if not pos.stop_loss or not pos.current_price:
                    continue
                pos_orm = session.query(PositionORM).filter_by(id=pos.id).first()
                if not pos_orm or pos_orm.pending_closure or pos_orm.closed_at:
                    continue
                side_str = str(pos_orm.side).upper() if pos_orm.side else 'LONG'
                is_long = 'LONG' in side_str or 'BUY' in side_str
                breached = False
                if is_long and pos.current_price <= pos.stop_loss:
                    breached = True
                elif not is_long and pos.current_price >= pos.stop_loss:
                    breached = True
                if breached:
                    pos_orm.pending_closure = True
                    pos_orm.closure_reason = (
                        f"Trailing stop breached: price {pos.current_price:.2f} "
                        f"{'<=' if is_long else '>='} stop {pos.stop_loss:.2f}"
                    )
                    breach_count += 1
                    logger.warning(
                        f"Stop-loss breach for {pos.symbol} ({pos.id}): "
                        f"price={pos.current_price:.2f}, stop={pos.stop_loss:.2f}, "
                        f"side={'LONG' if is_long else 'SHORT'}"
                    )
            if breach_count > 0:
                session.commit()
                logger.info(f"Flagged {breach_count} positions for closure (stop-loss breach)")

            return {
                "updated": updated_count,
                "breach_closures": breach_count,
            }

        except Exception as e:
            logger.error(f"Error checking trailing stops: {e}")
            session.rollback()
            return {"updated": 0, "breach_closures": 0, "error": str(e)}

        finally:
            session.close()

    def _check_position_health_individual(self) -> dict:
        """
        Evaluate each open position individually for risk violations.
        
        This is position-level risk management — independent of strategy.
        A position is flagged for closure if:
        
        1. Stop-loss gap: current price blew through SL (price < SL for longs,
           price > SL for shorts) — the stop didn't trigger on eToro.
        2. Max loss exceeded: position is losing more than 2x the configured
           stop-loss percentage — something is wrong.
        3. Stale underwater: position has been losing >5% for 7+ days with
           no recovery — dead money.
        
        Trailing stops and SL/TP handle normal exits. This catches the edge
        cases they miss.
        
        Returns:
            Dict with flagged/checked counts
        """
        result = {"checked": 0, "flagged": 0}
        
        session = self.db.get_session()
        try:
            from src.models.orm import PositionORM, StrategyORM
            
            open_positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).all()
            
            if not open_positions:
                return result
            
            for pos in open_positions:
                result["checked"] += 1
                
                if not pos.entry_price or pos.entry_price <= 0:
                    continue
                if not pos.current_price or pos.current_price <= 0:
                    continue
                
                invested = pos.invested_amount if pos.invested_amount and pos.invested_amount > 0 else abs(pos.quantity)
                if invested <= 0:
                    continue
                
                # Current P&L as percentage of invested
                pnl = pos.unrealized_pnl or 0
                pnl_pct = pnl / invested
                
                side_str = str(pos.side).upper() if pos.side else 'LONG'
                is_long = 'LONG' in side_str
                
                # Get strategy's configured SL% (if available)
                sl_pct = 0.05  # Default 5%
                try:
                    strat = session.query(StrategyORM).filter_by(id=pos.strategy_id).first()
                    if strat and strat.risk_params and isinstance(strat.risk_params, dict):
                        sl_pct = strat.risk_params.get('stop_loss_pct', 0.05)
                except Exception:
                    pass
                
                closure_reason = None
                
                # Check 1: Stop-loss gap — price blew through SL
                if pos.stop_loss and pos.stop_loss > 0:
                    if is_long and pos.current_price < pos.stop_loss * 0.98:  # 2% below SL
                        closure_reason = (
                            f"SL gap: price {pos.current_price:.2f} below SL {pos.stop_loss:.2f} "
                            f"(gap: {((pos.stop_loss - pos.current_price) / pos.stop_loss):.1%})"
                        )
                    elif not is_long and pos.current_price > pos.stop_loss * 1.02:  # 2% above SL
                        closure_reason = (
                            f"SL gap: price {pos.current_price:.2f} above SL {pos.stop_loss:.2f} "
                            f"(gap: {((pos.current_price - pos.stop_loss) / pos.stop_loss):.1%})"
                        )
                
                # Check 2: Max loss exceeded — losing more than 2x configured SL
                if not closure_reason and pnl_pct < -(sl_pct * 2):
                    closure_reason = (
                        f"Max loss exceeded: {pnl_pct:.1%} loss > {sl_pct * 2:.0%} limit "
                        f"(2x SL of {sl_pct:.0%})"
                    )
                
                # Check 3: Stale underwater — losing >5% for 7+ days
                if not closure_reason and pnl_pct < -0.05 and pos.opened_at:
                    age_days = (datetime.now() - pos.opened_at).days
                    if age_days >= 7:
                        closure_reason = (
                            f"Stale underwater: {pnl_pct:.1%} loss for {age_days} days "
                            f"(${pnl:.2f} on ${invested:.0f} invested)"
                        )
                
                if closure_reason:
                    if not pos.pending_closure:
                        pos.pending_closure = True
                        pos.closure_reason = closure_reason
                        result["flagged"] += 1
                        logger.warning(
                            f"[PositionHealth] Flagging {pos.symbol} (id={pos.id}): {closure_reason}"
                        )
            
            if result["flagged"] > 0:
                session.commit()
            
        except Exception as e:
            logger.error(f"Error in position health check: {e}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()
        
        return result

    def _check_partial_exits(self) -> dict:
        """
        Check open positions for partial exit opportunities.

        DISABLED: Depends on eToro position modification API which is not available.
        Re-enable once eToro API supports partial close / position updates.
        """
        return {"checked": 0, "triggered": 0, "failed": 0, "skipped": "disabled"}

        # --- Original implementation below (unreachable) ---
        # For each open position:
        # - Look up its strategy's risk config (from risk_params JSON or global RiskConfigORM)
        # - Check if partial exits are enabled
        # - Calculate current profit percentage from DB prices
        # - Check each partial exit level
        # - Skip levels already triggered (check partial_exits history)
        # - Submit partial close order for the configured percentage
        # - Record the partial exit in PositionORM.partial_exits JSON field

        # Returns:
        #     Dictionary with counts: checked, triggered, skipped, failed
        session = self.db.get_session()

        try:
            from src.models.orm import PositionORM, StrategyORM, RiskConfigORM, OrderORM
            from src.models.enums import (
                PositionSide, OrderSide, OrderType, OrderStatus, TradingMode,
            )
            import uuid
            import json as json_module

            # Get all open positions
            open_positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None)
            ).all()

            if not open_positions:
                return {"checked": 0, "triggered": 0, "skipped": 0, "failed": 0}

            # Load global risk config for partial exit settings
            global_risk_config = session.query(RiskConfigORM).filter(
                RiskConfigORM.mode == TradingMode.DEMO
            ).first()

            checked = 0
            triggered = 0
            skipped = 0
            failed = 0

            # Cache strategy risk_params lookups
            strategy_cache: dict = {}

            for pos in open_positions:
                try:
                    checked += 1

                    # Skip positions whose market is closed — price isn't moving
                    if not self._is_symbol_market_open(pos.symbol):
                        continue

                    # Get partial exit config: check strategy's risk_params first, fall back to global
                    if pos.strategy_id not in strategy_cache:
                        strategy = session.query(StrategyORM).filter_by(
                            id=pos.strategy_id
                        ).first()
                        if strategy and strategy.risk_params:
                            strategy_cache[pos.strategy_id] = strategy.risk_params
                        else:
                            strategy_cache[pos.strategy_id] = {}

                    risk_params = strategy_cache[pos.strategy_id]

                    # Check if partial exits are enabled (strategy-level or global)
                    partial_exit_enabled = risk_params.get("partial_exit_enabled", False)
                    partial_exit_levels = risk_params.get("partial_exit_levels", None)

                    # Fall back to global risk config if not set on strategy
                    if not partial_exit_enabled and global_risk_config:
                        partial_exit_enabled = bool(global_risk_config.partial_exit_enabled)
                        partial_exit_levels = global_risk_config.partial_exit_levels

                    if not partial_exit_enabled:
                        continue

                    if not partial_exit_levels:
                        continue

                    # Calculate profit percentage
                    if not pos.entry_price or pos.entry_price <= 0:
                        continue
                    if not pos.current_price or pos.current_price <= 0:
                        continue

                    if pos.side == PositionSide.LONG:
                        profit_pct = (pos.current_price - pos.entry_price) / pos.entry_price
                    else:  # SHORT
                        profit_pct = (pos.entry_price - pos.current_price) / pos.entry_price

                    # Get existing partial exits history
                    existing_exits = pos.partial_exits or []

                    for level in partial_exit_levels:
                        profit_threshold = level.get("profit_pct", 0.0)
                        exit_pct = level.get("exit_pct", 0.0)

                        # Validate level
                        if profit_threshold <= 0 or exit_pct <= 0 or exit_pct > 1.0:
                            continue

                        # Check if profit threshold is met
                        if profit_pct < profit_threshold:
                            continue

                        # Check if this level was already triggered
                        level_key = f"{profit_threshold:.4f}"
                        already_triggered = any(
                            ex.get("level_pct") == profit_threshold
                            or ex.get("profit_level") == level_key
                            for ex in existing_exits
                        )

                        if already_triggered:
                            skipped += 1
                            logger.debug(
                                f"Partial exit level {profit_threshold:.1%} already triggered "
                                f"for position {pos.id} ({pos.symbol})"
                            )
                            continue

                        # Calculate exit quantity (units) and dollar amount for eToro
                        exit_quantity = pos.quantity * exit_pct  # units
                        if exit_quantity <= 0:
                            continue
                        exit_amount = exit_quantity * pos.current_price  # dollars for eToro

                        # Submit partial close order
                        side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
                        order_id = str(uuid.uuid4())

                        order_orm = OrderORM(
                            id=order_id,
                            strategy_id=pos.strategy_id,
                            symbol=pos.symbol,
                            side=side,
                            order_type=OrderType.MARKET,
                            quantity=exit_amount,
                            status=OrderStatus.PENDING,
                            order_action='close',
                        )
                        session.add(order_orm)
                        session.flush()

                        try:
                            from src.api.etoro_client import EToroAPIError
                            from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID

                            # Use partial_close_position API — this reduces the existing
                            # position instead of opening a new opposite-side position.
                            instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(pos.symbol)
                            response = self.etoro_client.partial_close_position(
                                position_id=pos.etoro_position_id,
                                amount=exit_amount,
                                instrument_id=instrument_id,
                            )

                            order_orm.etoro_order_id = response.get("order_id")
                            order_orm.status = OrderStatus.PENDING
                            order_orm.submitted_at = datetime.now()

                            # Record partial exit in position history
                            partial_exit_record = {
                                "level_pct": profit_threshold,
                                "exit_pct": exit_pct,
                                "quantity": exit_quantity,
                                "price": pos.current_price,
                                "timestamp": datetime.now().isoformat(),
                                "order_id": order_id,
                                "profit_level": level_key,
                            }

                            updated_exits = list(existing_exits) + [partial_exit_record]
                            pos.partial_exits = updated_exits
                            # Also update existing_exits for subsequent level checks in this loop
                            existing_exits = updated_exits

                            # Reduce position quantity
                            pos.quantity = pos.quantity - exit_quantity

                            triggered += 1
                            logger.info(
                                f"Partial exit triggered for {pos.symbol} (position {pos.id}): "
                                f"profit={profit_pct:.2%}, level={profit_threshold:.1%}, "
                                f"exit_qty={exit_quantity:.4f} ({exit_pct:.0%}), "
                                f"price={pos.current_price:.2f}, order={order_id}"
                            )

                        except Exception as e:
                            order_orm.status = OrderStatus.FAILED
                            failed += 1
                            logger.error(
                                f"Failed to submit partial exit order for {pos.symbol} "
                                f"(position {pos.id}): {e}"
                            )

                except Exception as e:
                    logger.error(f"Error processing partial exits for position {pos.id}: {e}")
                    continue

            session.commit()

            return {
                "checked": checked,
                "triggered": triggered,
                "skipped": skipped,
                "failed": failed,
            }

        except Exception as e:
            logger.error(f"Error checking partial exits: {e}")
            session.rollback()
            return {"checked": 0, "triggered": 0, "skipped": 0, "failed": 0, "error": str(e)}

        finally:
            session.close()

    def _process_pending_closures(self) -> dict:
        """
        Auto-close positions flagged with pending_closure=True.

        For each position with pending_closure=True and closed_at IS NULL:
        - Skip if close_attempts >= 3 (max retries exhausted)
        - Skip if a close order was already submitted and is still active
        - Create a close order via OrderExecutor
        - Track close_order_id and close_attempts on the position
        - On failure, increment close_attempts with exponential backoff awareness
        - After 3 failures, log critical error but keep the flag

        Returns:
            Dict with 'submitted', 'failed', 'skipped', 'total' counts.
        """
        session = self.db.get_session()
        submitted = 0
        failed = 0
        skipped = 0
        max_attempts = 3

        try:
            from src.models.orm import PositionORM, OrderORM
            from src.models.enums import PositionSide, OrderStatus

            # Find all positions pending closure that are still open
            pending_positions = session.query(PositionORM).filter(
                PositionORM.pending_closure == True,
                PositionORM.closed_at.is_(None),
            ).all()

            if not pending_positions:
                return {"submitted": 0, "failed": 0, "skipped": 0, "total": 0}

            logger.info(f"Processing {len(pending_positions)} positions pending closure")

            for pos in pending_positions:
                # Skip if market is closed for this symbol — close order will fail
                if not self._is_symbol_market_open(pos.symbol):
                    skipped += 1
                    continue

                # Skip if max retries exhausted
                attempts = pos.close_attempts or 0
                if attempts >= max_attempts:
                    skipped += 1
                    continue

                # Skip if there's already an active close order (PENDING or SUBMITTED)
                if pos.close_order_id:
                    existing_order = session.query(OrderORM).filter_by(
                        id=pos.close_order_id
                    ).first()
                    if existing_order and existing_order.status == OrderStatus.PENDING:
                        skipped += 1
                        continue

                # Exponential backoff: skip if not enough time has passed since last attempt
                if attempts > 0:
                    # Backoff: 60s, 240s, 960s (1min, 4min, 16min)
                    backoff_seconds = 60 * (4 ** (attempts - 1))
                    # Use close_order submission time as reference for backoff
                    if pos.close_order_id:
                        last_order = session.query(OrderORM).filter_by(
                            id=pos.close_order_id
                        ).first()
                        if last_order and last_order.submitted_at:
                            elapsed = (datetime.now() - last_order.submitted_at).total_seconds()
                            if elapsed < backoff_seconds:
                                skipped += 1
                                continue

                # Create and submit close order
                try:
                    order_id = self._submit_close_order(pos, session)
                    if order_id:
                        pos.close_order_id = order_id
                        pos.close_attempts = attempts + 1
                        submitted += 1
                        logger.info(
                            f"Submitted close order {order_id} for position {pos.id} "
                            f"({pos.symbol}, attempt {attempts + 1}/{max_attempts})"
                        )
                    else:
                        pos.close_attempts = attempts + 1
                        failed += 1
                        if pos.close_attempts >= max_attempts:
                            logger.critical(
                                f"CRITICAL: Failed to close position {pos.id} ({pos.symbol}) "
                                f"after {max_attempts} attempts. Position remains open on eToro. "
                                f"Reason: {pos.closure_reason}"
                            )
                except Exception as e:
                    pos.close_attempts = attempts + 1
                    failed += 1
                    logger.error(
                        f"Error submitting close order for position {pos.id} "
                        f"({pos.symbol}, attempt {attempts + 1}/{max_attempts}): {e}"
                    )
                    if pos.close_attempts >= max_attempts:
                        logger.critical(
                            f"CRITICAL: Failed to close position {pos.id} ({pos.symbol}) "
                            f"after {max_attempts} attempts. Position remains open on eToro. "
                            f"Reason: {pos.closure_reason}"
                        )

            session.commit()
            return {
                "submitted": submitted,
                "failed": failed,
                "skipped": skipped,
                "total": len(pending_positions),
            }

        except Exception as e:
            logger.error(f"Error processing pending closures: {e}", exc_info=True)
            session.rollback()
            return {"submitted": submitted, "failed": failed, "skipped": skipped, "error": str(e)}
        finally:
            session.close()

    def _submit_close_order(self, pos, session) -> Optional[str]:
        """
        Close a position on eToro using the close_position API.

        Args:
            pos: PositionORM instance to close
            session: Active DB session

        Returns:
            Order ID string if closed successfully, None on failure.
        """
        import uuid
        from src.models.orm import OrderORM
        from src.models.enums import (
            PositionSide, OrderSide, OrderType, OrderStatus,
        )
        from src.api.etoro_client import EToroAPIError, CircuitBreakerOpen

        side = OrderSide.SELL if pos.side == PositionSide.LONG else OrderSide.BUY
        order_id = str(uuid.uuid4())

        # Create order record in DB for tracking
        # Use invested_amount (always dollars) for the order quantity.
        # pos.quantity is unreliable — for crypto it can be units, for stocks
        # it can be shares, and eToro sometimes returns garbage values.
        close_dollar_amount = getattr(pos, 'invested_amount', None) or 0
        if close_dollar_amount <= 0:
            # Fallback: estimate from current price × quantity, but cap at reasonable amount
            if pos.quantity and pos.current_price and pos.current_price > 0:
                estimated = abs(pos.quantity * pos.current_price)
                # Sanity check: no single position should be > 30% of a $500K portfolio
                if estimated > 150000:
                    logger.warning(
                        f"Close order for {pos.symbol}: estimated amount ${estimated:,.0f} "
                        f"looks wrong (qty={pos.quantity}, price={pos.current_price}). "
                        f"Using entry_price * quantity instead."
                    )
                    if pos.entry_price and pos.entry_price > 0:
                        estimated = abs(pos.quantity * pos.entry_price)
                    if estimated > 150000:
                        logger.error(
                            f"Close order for {pos.symbol}: still too large (${estimated:,.0f}). Skipping."
                        )
                        return None
                close_dollar_amount = estimated
            else:
                logger.error(f"Cannot determine close amount for {pos.symbol}: no invested_amount, quantity, or price")
                return None

        # Determine order action (close vs retirement) safely — pos may be
        # a detached ORM instance where attribute access triggers lazy loads.
        try:
            _closure_reason = str(getattr(pos, 'closure_reason', None) or '')
            _order_action = 'retirement' if 'retire' in _closure_reason.lower() else 'close'
        except Exception:
            _order_action = 'close'

        order_orm = OrderORM(
            id=order_id,
            strategy_id=pos.strategy_id,
            symbol=pos.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=close_dollar_amount,
            status=OrderStatus.PENDING,
            order_action=_order_action,
        )
        session.add(order_orm)
        session.flush()

        try:
            # Use close_position API — this actually closes the position on eToro
            # instead of place_order which creates a NEW opposite-side position
            # Look up instrument ID for the symbol (required for demo close endpoint)
            from src.utils.instrument_mappings import SYMBOL_TO_INSTRUMENT_ID
            instrument_id = SYMBOL_TO_INSTRUMENT_ID.get(pos.symbol)
            self.etoro_client.close_position(
                pos.etoro_position_id,
                instrument_id=instrument_id,
                amount=close_dollar_amount,
            )

            order_orm.status = OrderStatus.FILLED
            order_orm.submitted_at = datetime.now()
            order_orm.filled_at = datetime.now()

            # Mark position as closed in DB — compute realized P&L from price difference
            entry = pos.entry_price or 0
            current = pos.current_price or entry
            invested = getattr(pos, 'invested_amount', None) or 0
            # Fallback: use close_dollar_amount which was already sanitized above
            if invested <= 0:
                invested = close_dollar_amount
            if entry > 0 and invested > 0:
                side_str = str(pos.side).upper() if pos.side else 'LONG'
                if 'SHORT' in side_str or 'SELL' in side_str:
                    calculated_pnl = invested * (entry - current) / entry
                else:
                    calculated_pnl = invested * (current - entry) / entry
                pos.realized_pnl = (pos.realized_pnl or 0) + calculated_pnl
            else:
                pos.realized_pnl = (pos.realized_pnl or 0) + (pos.unrealized_pnl or 0)
            pos.unrealized_pnl = 0.0
            pos.closed_at = datetime.now()
            pos.pending_closure = False

            # Log to trade journal for performance feedback loop
            try:
                from src.analytics.trade_journal import TradeJournal
                journal = TradeJournal(self.db)
                side_str = str(pos.side).upper() if pos.side else 'LONG'
                is_long = 'LONG' in side_str or 'BUY' in side_str
                exit_reason = getattr(pos, 'closure_reason', None) or "pending_closure"
                
                # Retry journal writes to handle SQLite "database is locked" errors
                # when multiple close orders fire in rapid succession
                import time as _time
                for _attempt in range(3):
                    try:
                        journal.log_entry(
                            trade_id=str(pos.id),
                            strategy_id=pos.strategy_id or "unknown",
                            symbol=pos.symbol,
                            entry_time=pos.opened_at or pos.closed_at,
                            entry_price=pos.entry_price or 0,
                            entry_size=getattr(pos, 'invested_amount', None) or close_dollar_amount or 0,
                            entry_reason="autonomous_signal",
                            order_side="BUY" if is_long else "SELL",
                        )
                        journal.log_exit(
                            trade_id=str(pos.id),
                            exit_time=pos.closed_at,
                            exit_price=pos.current_price,
                            exit_reason=exit_reason,
                            symbol=pos.symbol,
                        )
                        break  # Success
                    except Exception as _retry_err:
                        if "locked" in str(_retry_err).lower() and _attempt < 2:
                            _time.sleep(0.5 * (2 ** _attempt))  # 0.5s, 1s backoff
                            continue
                        raise
            except Exception as je:
                logger.debug(f"Could not log exit to trade journal for {pos.symbol}: {je}")

            logger.info(
                f"Position {pos.id} ({pos.symbol}) closed on eToro "
                f"(etoro_position_id: {pos.etoro_position_id})"
            )
            return order_id

        except CircuitBreakerOpen:
            order_orm.status = OrderStatus.FAILED
            logger.warning(f"Circuit breaker open — cannot close position {pos.id} ({pos.symbol})")
            return None
        except EToroAPIError as e:
            order_orm.status = OrderStatus.FAILED
            error_msg = str(e).lower()
            # If position is already closed on eToro, mark as closed in DB
            if "not found" in error_msg or "404" in error_msg or "does not exist" in error_msg:
                entry = pos.entry_price or 0
                current = pos.current_price or entry
                invested = getattr(pos, 'invested_amount', None) or 0
                if invested <= 0:
                    invested = close_dollar_amount
                if entry > 0 and invested > 0:
                    side_str = str(pos.side).upper() if pos.side else 'LONG'
                    if 'SHORT' in side_str or 'SELL' in side_str:
                        calculated_pnl = invested * (entry - current) / entry
                    else:
                        calculated_pnl = invested * (current - entry) / entry
                    pos.realized_pnl = (pos.realized_pnl or 0) + calculated_pnl
                else:
                    pos.realized_pnl = (pos.realized_pnl or 0) + (pos.unrealized_pnl or 0)
                pos.unrealized_pnl = 0.0
                pos.closed_at = datetime.now()
                pos.pending_closure = False
                logger.info(f"Position {pos.id} ({pos.symbol}) already closed on eToro — marking closed in DB")
                return order_id
            logger.error(f"eToro API error closing position {pos.id}: {e}")
            return None
        except Exception as e:
            order_orm.status = OrderStatus.FAILED
            logger.error(f"Unexpected error closing position {pos.id}: {e}")
            return None

    def _close_shorts_in_bull_market(self) -> Dict:
        """
        Flag open equity SHORT positions for closure when the market regime is bullish.

        In trending_up / trending_up_weak / trending_up_strong regimes, holding equity
        shorts is fighting the tide. This method flags them for closure so the monitoring
        service's pending closure processor can close them on eToro.

        Only applies to equity shorts (stocks + ETFs). Forex, commodity, index, and
        crypto shorts have independent regime detection and are not affected.

        Returns:
            Dict with 'checked' and 'flagged' counts.
        """
        # Detect current equity regime
        bullish_regimes = {'trending_up', 'trending_up_weak', 'trending_up_strong'}
        current_regime = 'unknown'
        try:
            from src.strategy.market_analyzer import MarketStatisticsAnalyzer
            from src.data.market_data_manager import MarketDataManager
            import yaml as _yaml
            from pathlib import Path as _Path
            _cfg_path = _Path("config/autonomous_trading.yaml")
            _cfg = {}
            if _cfg_path.exists():
                with open(_cfg_path) as _f:
                    _cfg = _yaml.safe_load(_f) or {}
            _mdm = MarketDataManager(_cfg)
            _analyzer = MarketStatisticsAnalyzer(_mdm)
            _sub_regime, _, _, _ = _analyzer.detect_sub_regime()
            current_regime = _sub_regime.value.lower() if _sub_regime else 'unknown'
        except Exception as _e:
            logger.debug(f"Could not detect regime for bull market short check: {_e}")
            return {"checked": 0, "flagged": 0, "regime": "unknown"}

        if current_regime not in bullish_regimes:
            return {"checked": 0, "flagged": 0, "regime": current_regime}

        session = self.db.get_session()
        checked = 0
        flagged = 0

        try:
            from src.models.orm import PositionORM
            from src.core.tradeable_instruments import (
                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES,
            )
            _non_equity = set(DEMO_ALLOWED_CRYPTO) | set(DEMO_ALLOWED_FOREX) | \
                          set(DEMO_ALLOWED_COMMODITIES) | set(DEMO_ALLOWED_INDICES)

            # Find open SHORT positions that are equities
            open_shorts = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None),
                PositionORM.pending_closure == False,
                PositionORM.side == 'SHORT',
            ).all()

            for pos in open_shorts:
                sym = (pos.symbol or '').upper()
                if sym in _non_equity:
                    continue  # Skip non-equity shorts
                if pos.strategy_id in ("etoro_position", "manual", "external"):
                    continue  # Skip external positions

                checked += 1
                pos.pending_closure = True
                pos.closure_reason = (
                    f"Bull market regime gate: closing equity SHORT in {current_regime} regime"
                )
                flagged += 1
                logger.warning(
                    f"[BullMarketGate] Flagging {pos.symbol} SHORT (position {pos.id}) "
                    f"for closure — regime is {current_regime}"
                )

            if flagged > 0:
                session.commit()
                logger.info(
                    f"[BullMarketGate] {flagged}/{checked} equity shorts flagged for closure "
                    f"(regime: {current_regime})"
                )

            return {"checked": checked, "flagged": flagged, "regime": current_regime}

        except Exception as e:
            logger.error(f"Error in bull market short closure: {e}", exc_info=True)
            session.rollback()
            return {"checked": checked, "flagged": flagged, "error": str(e)}
        finally:
            session.close()

    def _load_fundamental_config(self) -> Dict:
        """Load fundamental monitoring config from autonomous_trading.yaml."""
        try:
            with open("config/autonomous_trading.yaml", "r") as f:
                config = yaml.safe_load(f) or {}
            return config.get("alpha_edge", {}).get("fundamental_monitoring", {})
        except Exception as e:
            logger.warning(f"Could not load fundamental monitoring config: {e}")
            return {}

    def _check_fundamental_exits(self) -> Dict:
        """
        Check open positions for fundamental changes that warrant early exit.

        Runs daily. For each open stock position, checks:
        1. Earnings miss: most recent earnings surprise < -5%
        2. Revenue decline: revenue growth turned negative
        3. Sector rotation: current regime no longer favors the position's sector

        Guards applied:
        - Regime stability: sector rotation exits only fire if the regime has been
          stable for ≥ 3 days (prevents whipsawing on single-day regime blips).
        - No exit at a loss for sector rotation: if the position is already losing,
          let the SL handle it — sector rotation is a forward-looking signal, not
          a reason to crystallize realized losses.
        - Earnings miss exits only fire if the position is profitable OR the loss
          is already severe (> 50% of SL distance consumed).

        Returns:
            Dict with 'checked' and 'flagged' counts.
        """
        config = self._fundamental_config
        if not config.get("enabled", True):
            logger.debug("Fundamental monitoring disabled")
            return {"checked": 0, "flagged": 0, "skipped_disabled": True}

        earnings_threshold = config.get("earnings_miss_threshold", -0.05)
        revenue_decline_exit = config.get("revenue_decline_exit", True)
        sector_rotation_exit = config.get("sector_rotation_exit", True)

        session = self.db.get_session()
        checked = 0
        flagged = 0

        try:
            from src.models.orm import PositionORM
            from src.risk.risk_manager import get_symbol_sector

            # Get all open, non-pending-closure positions
            open_positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None),
                PositionORM.pending_closure == False,
            ).all()

            if not open_positions:
                logger.debug("No open positions to check for fundamental exits")
                return {"checked": 0, "flagged": 0}

            # Lazy-load the FundamentalDataProvider (avoid import at module level)
            fundamental_provider = self._get_fundamental_provider()
            if fundamental_provider is None:
                logger.warning("FundamentalDataProvider unavailable — skipping fundamental exit checks")
                return {"checked": 0, "flagged": 0, "error": "provider_unavailable"}

            # Detect current regime for sector rotation check
            current_regime = None
            optimal_sectors: List[str] = []
            regime_stable = False  # Whether regime has been stable for ≥ 3 days
            if sector_rotation_exit:
                current_regime, optimal_sectors = self._get_regime_and_sectors()
                # Check regime stability: query regime_history for recent changes
                try:
                    from src.models.orm import RegimeHistoryORM
                    from datetime import timedelta
                    stability_window = datetime.utcnow() - timedelta(days=3)
                    recent_changes = session.query(RegimeHistoryORM).filter(
                        RegimeHistoryORM.detected_at >= stability_window,
                        RegimeHistoryORM.regime_changed == True,
                    ).count()
                    regime_stable = (recent_changes == 0)
                    if not regime_stable:
                        logger.info(
                            f"[FundamentalExit] Regime changed {recent_changes}x in last 3 days — "
                            f"suppressing sector rotation exits (regime not stable)"
                        )
                except Exception as _re:
                    # If we can't check stability, default to stable=True (don't suppress)
                    regime_stable = True
                    logger.debug(f"Could not check regime stability: {_re}")

            for pos in open_positions:
                symbol = pos.symbol

                # Skip positions from external/default strategies (not managed by us)
                if pos.strategy_id in ("etoro_position", "manual", "external"):
                    continue

                sector = get_symbol_sector(symbol)

                # Only check individual stocks — skip ETFs, forex, crypto, indices, commodities, REITs
                if sector in (
                    "Forex", "Crypto", "Indices", "Commodities",
                ) or sector.endswith("ETF"):
                    continue
                # Also skip if symbol is in the ETF list directly
                try:
                    from src.core.tradeable_instruments import DEMO_ALLOWED_ETFS
                    if symbol.upper() in set(DEMO_ALLOWED_ETFS):
                        continue
                except ImportError:
                    pass

                checked += 1
                exit_reasons: List[str] = []

                # Calculate position P&L percentage for profitability guards
                entry = pos.entry_price or 0
                current = pos.current_price or entry
                side_str = str(pos.side).upper() if pos.side else 'LONG'
                is_long = 'LONG' in side_str or 'BUY' in side_str
                if entry > 0:
                    pnl_pct = (current - entry) / entry if is_long else (entry - current) / entry
                else:
                    pnl_pct = 0.0
                is_profitable = pnl_pct > 0

                # How much of the SL distance has been consumed (0=at entry, 1=at stop)
                sl_consumed = 0.0
                if pos.stop_loss and entry > 0:
                    if is_long:
                        total_risk = entry - pos.stop_loss
                        current_loss = entry - current
                    else:
                        total_risk = pos.stop_loss - entry
                        current_loss = current - entry
                    if total_risk > 0 and current_loss > 0:
                        sl_consumed = current_loss / total_risk

                # --- Check 1: Earnings miss ---
                # Only exit on earnings miss if position is profitable OR loss is severe
                # (> 50% of SL consumed). If already losing but not near SL, let SL handle it.
                try:
                    surprise = fundamental_provider.calculate_earnings_surprise(symbol)
                    if surprise is not None and surprise < earnings_threshold:
                        if is_profitable or sl_consumed >= 0.5:
                            exit_reasons.append(
                                f"Earnings miss: surprise {surprise:.1%} < {earnings_threshold:.1%}"
                            )
                            logger.info(f"[FundamentalExit] {symbol}: earnings miss ({surprise:.1%}), "
                                       f"profitable={is_profitable}, sl_consumed={sl_consumed:.0%}")
                        else:
                            logger.debug(
                                f"[FundamentalExit] {symbol}: earnings miss ({surprise:.1%}) but "
                                f"position already losing ({pnl_pct:.1%}) and SL not near "
                                f"({sl_consumed:.0%} consumed) — letting SL handle it"
                            )
                except Exception as e:
                    logger.debug(f"Could not check earnings for {symbol}: {e}")

                # --- Check 2: Revenue decline ---
                if revenue_decline_exit:
                    try:
                        revenue_growth = fundamental_provider.get_revenue_growth(symbol)
                        if revenue_growth is not None and revenue_growth < 0:
                            exit_reasons.append(
                                f"Revenue decline: growth {revenue_growth:.1%}"
                            )
                            logger.info(f"[FundamentalExit] {symbol}: revenue decline ({revenue_growth:.1%})")
                    except Exception as e:
                        logger.debug(f"Could not check revenue for {symbol}: {e}")

                # --- Check 3: Sector rotation ---
                # Only fire if:
                # (a) regime has been stable for ≥ 3 days (no recent regime changes)
                # (b) position is currently profitable (don't crystallize losses)
                if sector_rotation_exit and current_regime and optimal_sectors and regime_stable:
                    try:
                        # Map the position's sector back to its ETF symbol
                        sector_to_etf = {
                            "Technology": "XLK", "Finance": "XLF", "Healthcare": "XLV",
                            "Energy": "XLE", "Industrials": "XLI", "Consumer": "XLY",
                            "Utilities": "XLU",
                        }
                        position_etf = sector_to_etf.get(sector)
                        if position_etf and position_etf not in optimal_sectors:
                            if is_profitable:
                                exit_reasons.append(
                                    f"Sector rotation: {sector} ({position_etf}) not in optimal sectors "
                                    f"for {current_regime} regime (optimal: {', '.join(optimal_sectors)})"
                                )
                                logger.info(
                                    f"[FundamentalExit] {symbol}: sector {sector} not favored "
                                    f"in {current_regime} regime (profitable={is_profitable:.1%})"
                                )
                            else:
                                logger.debug(
                                    f"[FundamentalExit] {symbol}: sector rotation would exit but "
                                    f"position is losing ({pnl_pct:.1%}) — letting SL handle it"
                                )
                    except Exception as e:
                        logger.debug(f"Could not check sector rotation for {symbol}: {e}")
                elif sector_rotation_exit and not regime_stable:
                    logger.debug(f"[FundamentalExit] {symbol}: sector rotation suppressed (regime unstable)")

                # Flag position for closure if any check failed
                if exit_reasons:
                    combined_reason = "Fundamental exit: " + "; ".join(exit_reasons)
                    pos.pending_closure = True
                    pos.closure_reason = combined_reason[:500]  # Truncate to fit column
                    flagged += 1
                    logger.warning(
                        f"[FundamentalExit] Flagged {symbol} (position {pos.id}) for closure: "
                        f"{combined_reason}"
                    )

            session.commit()
            logger.info(
                f"Fundamental exit check complete: {checked} positions checked, "
                f"{flagged} flagged for closure"
            )
            return {"checked": checked, "flagged": flagged}

        except Exception as e:
            logger.error(f"Error in fundamental exit check: {e}", exc_info=True)
            session.rollback()
            return {"checked": checked, "flagged": flagged, "error": str(e)}
        finally:
            session.close()

    def _check_time_based_exits(self) -> Dict:
        """
        Check open positions for max holding period exceedance.

        Runs daily. For each open position belonging to a non-Alpha-Edge strategy,
        checks if the hold time exceeds the configured max_holding_period_days.
        Positions that exceed the limit are flagged with pending_closure=True.

        Intraday strategies (metadata.intraday=True) use a shorter max holding period
        (default 5 days) since they're designed for hours, not weeks.

        Alpha Edge strategies are skipped — they have their own hold period logic.

        Returns:
            Dict with 'checked', 'flagged', and 'skipped_alpha_edge' counts.
        """
        # Load max holding period from config
        try:
            with open("config/autonomous_trading.yaml", "r") as f:
                config = yaml.safe_load(f) or {}
            max_days = config.get("position_management", {}).get("max_holding_period_days", 60)
            max_days_intraday = config.get("position_management", {}).get("max_holding_period_days_intraday", 5)
        except Exception as e:
            logger.warning(f"Could not load time-based exit config: {e}, using defaults")
            max_days = 60
            max_days_intraday = 5

        session = self.db.get_session()
        checked = 0
        flagged = 0
        skipped_alpha_edge = 0

        try:
            from src.models.orm import PositionORM, StrategyORM

            # Get all open, non-pending-closure positions
            open_positions = session.query(PositionORM).filter(
                PositionORM.closed_at.is_(None),
                PositionORM.pending_closure == False,
            ).all()

            if not open_positions:
                logger.debug("No open positions to check for time-based exits")
                return {"checked": 0, "flagged": 0, "skipped_alpha_edge": 0}

            now = datetime.utcnow()

            for pos in open_positions:
                # Look up the strategy to check if it's Alpha Edge
                strategy = session.query(StrategyORM).filter(
                    StrategyORM.id == pos.strategy_id
                ).first()

                if strategy:
                    metadata = strategy.strategy_metadata or {}
                    strategy_category = metadata.get("strategy_category", "")
                    if strategy_category == "alpha_edge":
                        skipped_alpha_edge += 1
                        continue

                checked += 1

                # Calculate hold time
                if pos.opened_at is None:
                    continue

                # For crypto (24/7), use calendar days.
                # For stocks/forex, use trading days (weekdays only) to avoid
                # penalizing positions for weekends when the market is closed.
                calendar_days = (now - pos.opened_at).days
                try:
                    from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                    sym = pos.symbol.upper() if pos.symbol else ''
                    if sym in set(DEMO_ALLOWED_CRYPTO):
                        hold_days = calendar_days
                    else:
                        # Count weekdays only (approximate trading days)
                        # For each full week, count 5 days. For partial weeks, count weekdays.
                        full_weeks = calendar_days // 7
                        remaining = calendar_days % 7
                        start_weekday = pos.opened_at.weekday()
                        weekend_days_in_remainder = sum(
                            1 for d in range(remaining)
                            if (start_weekday + d + 1) % 7 >= 5
                        )
                        hold_days = full_weeks * 5 + (remaining - weekend_days_in_remainder)
                except Exception:
                    hold_days = calendar_days  # Fallback to calendar days

                # Check strategy-specific hold_period_max (in bars/hours for intraday)
                is_intraday = False
                strategy_hold_max = None
                interval = "1d"
                if strategy:
                    metadata = strategy.strategy_metadata or {}
                    is_intraday = metadata.get("intraday", False)
                    interval = metadata.get("interval", "1d")

                    # Read hold_period_max from customized_parameters or default_parameters
                    params = metadata.get("customized_parameters") or metadata.get("default_parameters") or {}
                    strategy_hold_max = params.get("hold_period_max")

                if is_intraday and strategy_hold_max:
                    # For intraday strategies, hold_period_max is in HOURS (bars × interval)
                    # Convert position age to hours and compare
                    hold_hours = (now - pos.opened_at).total_seconds() / 3600
                    
                    # For non-crypto hourly strategies: extend to 48h if position is profitable.
                    # Stocks have overnight gaps, so 24h of wall-clock time = ~3h of actual trading.
                    # Cutting a winning intraday trade at 24h leaves money on the table.
                    # Losing positions still get cut at the original limit — or immediately
                    # if they've been losing for more than 50% of the hold limit.
                    effective_hold_max = strategy_hold_max
                    try:
                        from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                        sym = pos.symbol.upper() if pos.symbol else ''
                        is_crypto = sym in set(DEMO_ALLOWED_CRYPTO)
                        if not is_crypto and interval in ('1h', '2h'):
                            # Check if position is profitable
                            entry = pos.entry_price or 0
                            current = pos.current_price or entry
                            side_str = str(pos.side).upper() if pos.side else 'LONG'
                            if 'SHORT' in side_str or 'SELL' in side_str:
                                is_profitable = current < entry
                            else:
                                is_profitable = current > entry
                            if is_profitable and effective_hold_max < 48:
                                effective_hold_max = 48
                                logger.info(
                                    f"[TimeBasedExit] {pos.symbol}: profitable hourly position, "
                                    f"extending hold limit from {strategy_hold_max}h to 48h"
                                )
                            elif not is_profitable and hold_hours > effective_hold_max * 0.5:
                                # Losing position past 50% of hold limit — cut early only if
                                # the loss is meaningful (> 1% of invested). Positions at -0.1%
                                # are within spread/noise and shouldn't be cut early.
                                entry = pos.entry_price or 0
                                current = pos.current_price or entry
                                loss_pct = abs(current - entry) / entry if entry > 0 else 0
                                if loss_pct >= 0.01:  # At least 1% loss to trigger early cut
                                    effective_hold_max = effective_hold_max * 0.5
                                    logger.info(
                                        f"[TimeBasedExit] {pos.symbol}: losing hourly position "
                                        f"({loss_pct:.1%} loss) past 50% of hold limit — "
                                        f"closing early at {effective_hold_max:.0f}h"
                                    )
                    except Exception:
                        pass
                    
                    if hold_hours > effective_hold_max:
                        pos.pending_closure = True
                        pos.closure_reason = f"Intraday max hold exceeded ({hold_hours:.1f}h, limit: {effective_hold_max}h)"
                        flagged += 1
                        logger.warning(
                            f"[TimeBasedExit] Flagged {pos.symbol} (position {pos.id}) for closure: "
                            f"held {hold_hours:.1f}h, intraday max {strategy_hold_max}h (interval: {interval})"
                        )
                        continue  # Skip the daily check below
                elif is_intraday:
                    effective_max = max_days_intraday  # Fallback to config days
                else:
                    effective_max = max_days

                if hold_days > effective_max:
                    pos.pending_closure = True
                    label = "intraday" if is_intraday else "standard"
                    pos.closure_reason = f"Max holding period exceeded ({hold_days} days, {label} limit: {effective_max})"
                    flagged += 1
                    logger.warning(
                        f"[TimeBasedExit] Flagged {pos.symbol} (position {pos.id}) for closure: "
                        f"held {hold_days} days, {label} max {effective_max} days"
                    )

            session.commit()
            logger.info(
                f"Time-based exit check complete: {checked} positions checked, "
                f"{flagged} flagged, {skipped_alpha_edge} Alpha Edge skipped"
            )
            return {"checked": checked, "flagged": flagged, "skipped_alpha_edge": skipped_alpha_edge}

        except Exception as e:
            logger.error(f"Error in time-based exit check: {e}", exc_info=True)
            session.rollback()
            return {"checked": checked, "flagged": flagged, "skipped_alpha_edge": skipped_alpha_edge, "error": str(e)}
        finally:
            session.close()

    def _check_strategy_health(self) -> Dict:
        """
        Compute a health score (0-5) for each active strategy based on its CURRENT
        positions and realized trade history. Retire when score reaches 0.
        
        This evaluates the actual money — not backtest metrics, not win rate in isolation.
        A strategy might have 1 trade or 10. The score reflects what's happening NOW.
        
        Score logic (starts at 3 = neutral, adjusts up/down):
          +1  Total P&L (realized + unrealized) is positive
          +1  Expectancy is positive: (avg_win × wr) - (avg_loss × (1-wr)) > 0
          -1  Total P&L is negative and > 1% of position value
          -1  Every open position is underwater (all red)
          -1  Realized losses exceed 2% of total invested
          -1  Expectancy is clearly negative (enough closed trades to judge)
          +1  Has profitable open positions (some green)
        
        Clamped to 0-5. Score 0 triggers retirement.
        
        Returns:
            Dict with checked/retired/scores_updated counts
        """
        result = {"checked": 0, "retired": 0, "scores_updated": 0, "errors": []}
        
        try:
            from src.models.orm import StrategyORM, PositionORM
            from src.models.enums import StrategyStatus
            from sqlalchemy.orm.attributes import flag_modified
            
            session = self.db.get_session()
            try:
                active_strategies = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
                ).all()
                
                # Finalize pending retirements: strategies marked for retirement
                # whose positions have all closed naturally via SL/TP
                pending_retirement_strats = [
                    s for s in active_strategies
                    if isinstance(s.strategy_metadata, dict) and s.strategy_metadata.get('pending_retirement')
                ]
                for strat_orm in pending_retirement_strats:
                    open_count = session.query(PositionORM).filter(
                        PositionORM.strategy_id == strat_orm.id,
                        PositionORM.closed_at.is_(None)
                    ).count()
                    if open_count == 0:
                        meta = strat_orm.strategy_metadata
                        reason = meta.get('pending_retirement_reason', 'Pending retirement completed')
                        logger.info(
                            f"[StrategyHealth] Demoting {strat_orm.name} to BACKTESTED "
                            f"(all positions closed, TTL reset): {reason}"
                        )
                        # Demote to BACKTESTED with TTL — don't permanently retire.
                        # Market regimes rotate; a strategy that failed in trending_up
                        # may be excellent in ranging_low_vol. Keep it for re-evaluation.
                        strat_orm.status = StrategyStatus.BACKTESTED
                        strat_orm.retired_at = None
                        meta['activation_approved'] = False  # Must pass WF again
                        meta['demoted_from_active'] = True
                        meta['demoted_at'] = datetime.now().isoformat()
                        meta['demotion_reason'] = reason
                        meta['demotion_ttl_days'] = 14  # Will be cleaned up after 14 days if not re-activated
                        meta.pop('pending_retirement', None)
                        meta.pop('pending_retirement_reason', None)
                        meta.pop('pending_retirement_at', None)
                        meta.pop('retirement_reason', None)
                        meta.pop('retired_by', None)
                        strat_orm.strategy_metadata = meta
                        flag_modified(strat_orm, 'strategy_metadata')
                        result["retired"] += 1
                
                if not active_strategies:
                    return result
                
                # Load all positions in one query
                all_positions = session.query(PositionORM).filter(
                    PositionORM.strategy_id.isnot(None)
                ).all()
                
                strat_positions = {}
                for pos in all_positions:
                    sid = pos.strategy_id
                    if sid not in strat_positions:
                        strat_positions[sid] = {'closed': [], 'open': []}
                    if pos.closed_at:
                        strat_positions[sid]['closed'].append(pos)
                    else:
                        strat_positions[sid]['open'].append(pos)
                
                for strat_orm in active_strategies:
                    result["checked"] += 1
                    meta = strat_orm.strategy_metadata if isinstance(strat_orm.strategy_metadata, dict) else {}
                    
                    pos_data = strat_positions.get(strat_orm.id, {'closed': [], 'open': []})
                    closed = pos_data['closed']
                    open_pos = pos_data['open']
                    
                    total_realized = sum(p.realized_pnl or 0 for p in closed)
                    total_unrealized = sum(p.unrealized_pnl or 0 for p in open_pos)
                    total_pnl = total_realized + total_unrealized
                    # Total capital ever deployed = open positions + closed positions
                    # Using only open capital as denominator is wrong — a strategy that
                    # closed 5 trades ($10K total) and has 1 open ($1K) would show
                    # -50% when it's really -5%. Use all capital for fair comparison.
                    total_invested_open = sum(abs(p.invested_amount or p.quantity or 0) for p in open_pos)
                    total_invested_closed = sum(abs(p.invested_amount or p.quantity or 0) for p in closed)
                    total_invested = total_invested_open + total_invested_closed
                    if total_invested == 0:
                        total_invested = total_invested_open  # Fallback
                    
                    n_closed = len(closed)
                    n_open = len(open_pos)
                    n_total = n_closed + n_open
                    
                    # --- Start at 3 (neutral) ---
                    score = 3
                    details = {}
                    
                    if n_total == 0:
                        # No trades — no information to score. Don't fake a number.
                        # The UI should show "No data" instead of a misleading score.
                        score = None
                        details['reason'] = 'no_trades_no_score'
                        details['age_days'] = (datetime.now() - strat_orm.activated_at).days if strat_orm.activated_at else 0
                    else:
                        # P&L direction — use 3% threshold against total deployed capital
                        # (1% was too sensitive — normal position fluctuation triggers it)
                        if total_pnl > 0:
                            score += 1
                            details['pnl_positive'] = round(total_pnl, 2)
                        elif total_invested > 0 and total_pnl < -(total_invested * 0.03):
                            score -= 1
                            details['pnl_negative_material'] = round(total_pnl, 2)
                        
                        # Open positions health
                        if n_open > 0:
                            green = sum(1 for p in open_pos if (p.unrealized_pnl or 0) > 0)
                            red = sum(1 for p in open_pos if (p.unrealized_pnl or 0) < 0)
                            
                            if green > 0:
                                score += 1
                                details['has_green_positions'] = green
                            if red == n_open and n_open >= 1:
                                score -= 1
                                details['all_positions_red'] = red
                            
                            # Stop-loss proximity: how close are positions to getting stopped out?
                            # A position at 90%+ of its stop distance is in critical condition
                            sl_warnings = 0
                            sl_critical = 0
                            for p in open_pos:
                                if not p.stop_loss or not p.entry_price or p.entry_price == 0:
                                    continue
                                # Calculate how much of the stop distance has been consumed
                                side_str = str(p.side).upper() if p.side else ''
                                if 'LONG' in side_str or 'BUY' in side_str:
                                    total_risk = p.entry_price - p.stop_loss  # distance to stop
                                    current_loss = p.entry_price - (p.current_price or p.entry_price)
                                else:
                                    total_risk = p.stop_loss - p.entry_price
                                    current_loss = (p.current_price or p.entry_price) - p.entry_price
                                
                                if total_risk > 0 and current_loss > 0:
                                    sl_consumed = current_loss / total_risk  # 0.0 = at entry, 1.0 = at stop
                                    if sl_consumed >= 0.90:
                                        sl_critical += 1
                                    elif sl_consumed >= 0.70:
                                        sl_warnings += 1
                            
                            if sl_critical > 0:
                                score -= 1
                                details['positions_near_stop'] = sl_critical
                            if sl_warnings > 0 and sl_critical == 0:
                                # Warnings alone don't subtract, but we track them
                                details['positions_approaching_stop'] = sl_warnings
                        
                        # Realized loss severity — compare against TOTAL capital deployed
                        # (not just open capital, which can be tiny if most trades are closed)
                        if n_closed >= 1 and total_invested > 0 and total_realized < -(total_invested * 0.05):
                            score -= 1
                            details['realized_loss_severe'] = round(total_realized, 2)
                        
                        # Expectancy (only if we have enough closed trades to compute it)
                        # Require at least 5 closed trades before expectancy scoring.
                        # With fewer trades, a single bad trade can tank the score and
                        # trigger premature retirement. 5 trades gives a statistically
                        # meaningful sample while still catching genuinely broken strategies.
                        if n_closed >= 5:
                            wins = [p.realized_pnl for p in closed if (p.realized_pnl or 0) > 0]
                            losses = [abs(p.realized_pnl) for p in closed if (p.realized_pnl or 0) < 0]
                            avg_win = sum(wins) / len(wins) if wins else 0
                            avg_loss = sum(losses) / len(losses) if losses else 0
                            wr = len(wins) / n_closed
                            
                            expectancy = (avg_win * wr) - (avg_loss * (1 - wr))
                            details['expectancy'] = round(expectancy, 2)
                            details['win_rate'] = round(wr, 3)
                            details['avg_win'] = round(avg_win, 2)
                            details['avg_loss'] = round(avg_loss, 2)
                            
                            if expectancy > 0:
                                score += 1
                            elif expectancy < 0:
                                score -= 1
                    
                    # Clamp (None = no data, skip scoring)
                    if score is not None:
                        health_score = max(0, min(5, score))
                    else:
                        health_score = None
                    
                    details['total_pnl'] = round(total_pnl, 2)
                    details['total_realized'] = round(total_realized, 2)
                    details['total_unrealized'] = round(total_unrealized, 2)
                    details['closed_trades'] = n_closed
                    details['open_trades'] = n_open
                    details['updated_at'] = datetime.now().isoformat()
                    
                    # Persist
                    meta['health_score'] = health_score
                    meta['health_details'] = details
                    strat_orm.strategy_metadata = meta
                    flag_modified(strat_orm, 'strategy_metadata')
                    result["scores_updated"] += 1
                    
                    # Retire if score 0 (None = no data, don't retire)
                    # Also require minimum 5 closed trades before retirement to prevent
                    # premature retirement on a single bad trade.
                    min_trades_for_retirement = 5
                    if health_score is not None and health_score == 0 and n_closed >= min_trades_for_retirement:
                        retirement_reason = (
                            f"Health score 0: P&L ${total_pnl:,.2f}, "
                            f"{n_closed} closed, {n_open} open"
                        )
                        if 'expectancy' in details:
                            retirement_reason += f", expectancy ${details['expectancy']:,.2f}"
                        
                        if n_open > 0:
                            # Don't retire yet — let open positions close via SL/TP first
                            logger.info(
                                f"[StrategyHealth] {strat_orm.name} marked for pending retirement "
                                f"({n_open} open positions must close first): {retirement_reason}"
                            )
                            meta['pending_retirement'] = True
                            meta['pending_retirement_reason'] = retirement_reason
                            meta['pending_retirement_at'] = datetime.now().isoformat()
                            strat_orm.strategy_metadata = meta
                            flag_modified(strat_orm, 'strategy_metadata')
                            # Stop new signal generation by removing activation approval
                            meta.pop('activation_approved', None)
                        else:
                            # No open positions — demote to BACKTESTED (not permanently retired)
                            # Strategy gets a TTL window to prove itself again in the next cycle
                            logger.info(
                                f"[StrategyHealth] Demoting {strat_orm.name} to BACKTESTED "
                                f"(health=0, no open positions): {retirement_reason}"
                            )
                            strat_orm.status = StrategyStatus.BACKTESTED
                            strat_orm.retired_at = None
                            meta['activation_approved'] = False
                            meta['demoted_from_active'] = True
                            meta['demoted_at'] = datetime.now().isoformat()
                            meta['demotion_reason'] = retirement_reason
                            meta['demotion_ttl_days'] = 14
                            meta.pop('retirement_reason', None)
                            meta.pop('retired_by', None)
                            strat_orm.strategy_metadata = meta
                            flag_modified(strat_orm, 'strategy_metadata')
                            result["retired"] += 1
                    else:
                        logger.debug(
                            f"[StrategyHealth] {strat_orm.name}: health={health_score} "
                            f"pnl=${total_pnl:,.2f} ({n_open} open, {n_closed} closed)"
                        )
                
                session.commit()
                
                if result["retired"] > 0 or result["scores_updated"] > 0:
                    logger.info(
                        f"[StrategyHealth] Checked {result['checked']}, "
                        f"scored {result['scores_updated']}, retired {result['retired']}"
                    )
                    
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error in strategy health check: {e}", exc_info=True)
            result["errors"].append(str(e))
        
        return result

    def _check_strategy_decay(self) -> Dict:
        """
        Compute a decay score (countdown 10→0) for each active strategy.
        
        Measures whether the strategy's original backtest edge is still valid.
        Starts at 10 on activation, ticks down daily based on timeframe-aware
        degradation signals. When it hits 0, the edge is considered expired.
        
        Decay factors (each check subtracts from the score):
          - Regime mismatch: -2 (major shift) or -1 (minor drift)
          - Sharpe degradation: -1 to -3 based on how far below threshold
          - Drawdown breach: -2 if exceeding vol-adjusted threshold
          - Stop-loss ineffectiveness: -1 if hit rate > 60%, -2 if avg loss > Nx SL
          - Idle age: -1 per week with zero trades (strategy not firing)
        
        Timeframe-aware tick rates:
          - Daily/4H: thresholds from config, standard decay
          - 1H/2H: relaxed Sharpe/WR thresholds, faster idle decay
          - 15m/30m: most relaxed thresholds, fastest idle decay
        
        Returns:
            Dict with checked/retired/updated counts
        """
        result = {"checked": 0, "retired": 0, "updated": 0, "errors": []}
        
        try:
            from src.models.orm import StrategyORM, PositionORM
            from src.models.enums import StrategyStatus
            from sqlalchemy.orm.attributes import flag_modified
            import yaml
            from pathlib import Path
            
            # Load retirement thresholds from config
            config_ret = {}
            try:
                _rp = Path("config/autonomous_trading.yaml")
                if _rp.exists():
                    with open(_rp, 'r') as _rf:
                        _rc = yaml.safe_load(_rf) or {}
                        config_ret = _rc.get('retirement_thresholds', {})
            except Exception:
                pass
            
            config_max_sharpe = config_ret.get('max_sharpe', 0.2)
            config_min_wr = config_ret.get('min_win_rate', 0.35)
            config_max_dd = config_ret.get('max_drawdown', 0.31)
            
            # Detect current regime using the same MarketStatisticsAnalyzer path
            # that the rest of the system uses. The old MarketAnalyzer() instantiation
            # was silently failing (no market_data arg), leaving current_regime='unknown'
            # and making the entire regime mismatch penalty branch dead code.
            current_regime = 'unknown'
            try:
                from src.strategy.market_analyzer import MarketStatisticsAnalyzer
                from src.data.market_data_manager import get_market_data_manager
                _mdm = get_market_data_manager()
                if _mdm:
                    _analyzer = MarketStatisticsAnalyzer(_mdm)
                    sub_regime, _, _, _ = _analyzer.detect_sub_regime()
                    current_regime = sub_regime.value
                    logger.debug(f"[StrategyDecay] Current regime: {current_regime}")
            except Exception as _regime_err:
                logger.warning(f"[StrategyDecay] Could not detect regime: {_regime_err}")
            
            session = self.db.get_session()
            try:
                active_strategies = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
                ).all()
                
                if not active_strategies:
                    return result
                
                # Count live trades per strategy for idle check
                open_counts = {}
                pos_rows = session.query(PositionORM).filter(
                    PositionORM.strategy_id.isnot(None)
                ).all()
                for p in pos_rows:
                    sid = p.strategy_id
                    if sid not in open_counts:
                        open_counts[sid] = 0
                    open_counts[sid] += 1
                
                for strat_orm in active_strategies:
                    result["checked"] += 1
                    
                    meta = strat_orm.strategy_metadata if isinstance(strat_orm.strategy_metadata, dict) else {}
                    perf = strat_orm.performance or {}
                    
                    # Get or initialize decay score
                    decay_score = meta.get('decay_score')
                    if decay_score is None:
                        decay_score = 10  # Fresh strategy starts at 10
                    
                    # Detect interval for timeframe-aware thresholds
                    interval = (meta.get('interval') or '1d').lower()
                    
                    if interval in ['1h', '2h']:
                        sharpe_threshold = min(config_max_sharpe, 0.15)
                        wr_threshold = min(config_min_wr, 0.30)
                        idle_decay_per_week = 1.5  # Faster decay for intraday
                        avg_loss_multiplier = 3.5
                    elif interval in ['15m', '30m']:
                        sharpe_threshold = min(config_max_sharpe, 0.10)
                        wr_threshold = min(config_min_wr, 0.28)
                        idle_decay_per_week = 2.0  # Fastest decay
                        avg_loss_multiplier = 4.0
                    else:  # Daily, 4H
                        sharpe_threshold = config_max_sharpe
                        wr_threshold = config_min_wr
                        idle_decay_per_week = 1.0
                        avg_loss_multiplier = 3.0
                    
                    # --- Compute decay penalties ---
                    penalties = {}
                    
                    # 1. Regime mismatch
                    creation_regime = meta.get('macro_regime', '')
                    if creation_regime and current_regime != 'unknown' and creation_regime != current_regime:
                        is_major = (
                            ('trending_up' in creation_regime and 'trending_down' in current_regime) or
                            ('trending_down' in creation_regime and 'trending_up' in current_regime) or
                            ('ranging' in creation_regime and 'trending' in current_regime and 'strong' in current_regime)
                        )
                        if is_major:
                            penalties['regime_mismatch'] = 2.0
                        else:
                            penalties['regime_drift'] = 1.0
                    
                    # 2. Live P&L degradation (from ACTUAL positions, not stale backtest)
                    # The backtest Sharpe is frozen at activation time — a strategy with
                    # backtest Sharpe 1.5 that's been losing money for 3 weeks still shows 1.5.
                    # A PM would look at the live P&L, not the backtest.
                    strat_positions = [p for p in pos_rows if p.strategy_id == strat_orm.id]
                    live_pnl = sum((p.unrealized_pnl or 0) + (p.realized_pnl or 0) for p in strat_positions)
                    live_invested = sum(
                        (p.invested_amount if p.invested_amount and p.invested_amount > 0 else abs(p.quantity))
                        for p in strat_positions
                    ) if strat_positions else 0
                    
                    if live_invested > 0:
                        live_return_pct = live_pnl / live_invested
                        # Penalize if live return is negative
                        if live_return_pct < -0.10:  # Down >10%
                            penalties['live_pnl_severe'] = 3.0
                        elif live_return_pct < -0.05:  # Down >5%
                            penalties['live_pnl_negative'] = 2.0
                        elif live_return_pct < -0.02:  # Down >2%
                            penalties['live_pnl_warning'] = 1.0
                    
                    # 3. Drawdown from live positions (not backtest max_drawdown)
                    # Check if all positions for this strategy are underwater
                    if strat_positions:
                        underwater_count = sum(1 for p in strat_positions if (p.unrealized_pnl or 0) < 0)
                        if underwater_count == len(strat_positions) and len(strat_positions) >= 2:
                            penalties['all_positions_red'] = 2.0
                        elif underwater_count > len(strat_positions) * 0.7:
                            penalties['mostly_red'] = 1.0
                    
                    # 4. Stop-loss ineffectiveness from LIVE closed positions
                    # Check if losing positions are consistently breaching stop-loss levels
                    closed_strat_losers = [
                        p for p in strat_positions
                        if p.closed_at is not None and (p.realized_pnl or 0) < 0
                    ]
                    if len(closed_strat_losers) >= 3:
                        risk_params = strat_orm.risk_params or {}
                        sl_pct = risk_params.get('stop_loss_pct', 0)
                        if sl_pct > 0:
                            # Check how many losers lost more than 2x the stop-loss
                            severe_losses = 0
                            for p in closed_strat_losers:
                                invested = p.invested_amount if p.invested_amount and p.invested_amount > 0 else abs(p.quantity)
                                if invested > 0:
                                    loss_pct = abs(p.realized_pnl or 0) / invested
                                    if loss_pct > sl_pct * 2:
                                        severe_losses += 1
                            sl_breach_rate = severe_losses / len(closed_strat_losers)
                            if sl_breach_rate > 0.5:
                                penalties['stop_loss_ineffective'] = 2.0
                            elif sl_breach_rate > 0.3:
                                penalties['stop_loss_ineffective'] = 1.0
                    
                    # 5. Idle age (no trades)
                    total_positions = open_counts.get(strat_orm.id, 0)
                    if total_positions == 0 and strat_orm.activated_at:
                        age_days = (datetime.now() - strat_orm.activated_at).days
                        idle_weeks = age_days / 7.0
                        if idle_weeks >= 1:
                            penalties['idle'] = min(idle_weeks * idle_decay_per_week, 5.0)
                    
                    # 6. Win rate from live closed positions (not backtest)
                    closed_strat_positions = [
                        p for p in strat_positions if p.closed_at is not None
                    ]
                    if len(closed_strat_positions) >= 5:
                        live_wins = sum(1 for p in closed_strat_positions if (p.realized_pnl or 0) > 0)
                        live_wr = live_wins / len(closed_strat_positions)
                        if live_wr < wr_threshold:
                            penalties['live_win_rate_low'] = 1.0
                    
                    # 7. Factor premium compression (AE strategies only)
                    # For fundamental strategies, the real edge decay signal is whether
                    # the factor's cross-sectional spread is narrowing — not just whether
                    # the backtest Sharpe is low. If top-quintile and bottom-quintile
                    # stocks on this factor are converging, the premium is being arbitraged.
                    is_ae = meta.get('strategy_category') == 'alpha_edge'
                    if is_ae:
                        try:
                            factor_score = meta.get('factor_score', 0)
                            factor_details = meta.get('factor_details', {})
                            gate3 = factor_details.get('gate3', {})
                            spread = gate3.get('spread', 0)
                            
                            # If factor spread < 20 points (on 0-100 scale), the factor
                            # isn't discriminating well — premium is compressing
                            if spread > 0 and spread < 20:
                                penalties['factor_spread_narrow'] = 2.0
                            elif spread > 0 and spread < 30:
                                penalties['factor_spread_warning'] = 1.0
                            
                            # If the symbol is no longer in the right quintile for this factor,
                            # the thesis has weakened
                            if gate3.get('in_right_quintile') is False:
                                penalties['wrong_quintile'] = 1.5
                        except Exception:
                            pass  # Factor data not available, skip
                    
                    # --- Apply penalties as incremental decay ---
                    # Each check subtracts penalties from the CURRENT score (not from 10).
                    # This makes decay cumulative: a strategy that stays in a bad regime
                    # for multiple checks will gradually tick down to 0.
                    # Recovery: if no penalties this check, recover +1 (edge still valid).
                    total_penalty = sum(penalties.values())
                    
                    if total_penalty > 0:
                        # Scale penalty: full penalty would drain 10→0 in ~3 checks,
                        # so divide by 3 for gradual decay per check cycle
                        decay_step = min(total_penalty / 3.0, 3.0)
                        new_decay = decay_score - decay_step
                    else:
                        # No penalties — recover slowly (+0.5 per check, capped at 10)
                        new_decay = decay_score + 0.5
                    
                    decay_score = max(0, min(10, round(new_decay)))
                    
                    # --- Persist ---
                    meta['decay_score'] = decay_score
                    meta['decay_details'] = {
                        'penalties': {k: round(v, 2) for k, v in penalties.items()},
                        'total_penalty': round(total_penalty, 2),
                        'interval': interval,
                        'sharpe_threshold': sharpe_threshold,
                        'wr_threshold': wr_threshold,
                        'current_regime': current_regime,
                        'creation_regime': creation_regime,
                        'updated_at': datetime.now().isoformat(),
                    }
                    strat_orm.strategy_metadata = meta
                    flag_modified(strat_orm, 'strategy_metadata')
                    result["updated"] += 1
                    
                    # --- Retire if decay hits 0 and past probation ---
                    # Probation is timeframe-aware: a monthly rebalancing strategy
                    # (sector rotation, end-of-month) may not even have its first
                    # trade in 7 days. A PM wouldn't kill a monthly strategy after
                    # one week — they'd give it at least one full rebalancing cycle.
                    if decay_score == 0:
                        should_retire = True
                        if strat_orm.activated_at:
                            age_days = (datetime.now() - strat_orm.activated_at).days
                            
                            # Timeframe-aware probation periods
                            ae_type = meta.get('alpha_edge_type', '')
                            is_monthly = ae_type in (
                                'sector_rotation', 'sector_rotation_short',
                                'end_of_month_momentum', 'dividend_aristocrat',
                                'share_buyback',
                            )
                            is_weekly = ae_type in (
                                'pairs_trading', 'relative_value',
                            )
                            
                            if is_monthly or interval in ('1w', 'weekly'):
                                probation_days = 35  # ~5 weeks — at least one full rebalancing cycle
                            elif is_weekly or interval in ('4h',):
                                probation_days = 14  # 2 weeks
                            elif interval in ('1h', '2h', '15m', '30m'):
                                probation_days = 7   # 1 week — intraday should fire quickly
                            else:
                                probation_days = 7   # Daily: 1 week default
                            
                            # Halve probation when BOTH decay=0 AND health≤2 — doubly broken.
                            # No point protecting a strategy that's failing on both dimensions.
                            health_score_val = meta.get('health_score')
                            if health_score_val is not None and health_score_val <= 2:
                                probation_days = max(1, probation_days // 2)
                                logger.debug(
                                    f"[StrategyDecay] {strat_orm.name}: probation halved to {probation_days}d "
                                    f"(decay=0 AND health={health_score_val})"
                                )
                            
                            if age_days < probation_days:
                                should_retire = False
                        
                        if should_retire:
                            # Before retiring, check if the strategy is genuinely profitable.
                            # Require at least 2% return on deployed capital — not just $1 green.
                            # A strategy at +$5 on $6K deployed is noise, not a winner.
                            # This prevents the override from protecting every marginally green
                            # strategy during a regime change when capital needs to be recycled.
                            strat_positions = session.query(PositionORM).filter(
                                PositionORM.strategy_id == strat_orm.id
                            ).all()
                            if strat_positions:
                                live_pnl = sum(
                                    (p.realized_pnl or 0) + (p.unrealized_pnl or 0)
                                    for p in strat_positions
                                )
                                live_invested = sum(
                                    (p.invested_amount if p.invested_amount and p.invested_amount > 0 else abs(p.quantity or 0))
                                    for p in strat_positions
                                )
                                # Must be >2% return on deployed capital to qualify as a winner
                                winner_threshold = live_invested * 0.02
                                if live_pnl > winner_threshold:
                                    logger.info(
                                        f"[StrategyDecay] {strat_orm.name}: decay=0 but live P&L "
                                        f"is +${live_pnl:,.2f} ({live_pnl/live_invested:.1%} on ${live_invested:,.0f}) "
                                        f"— keeping genuine winner alive"
                                    )
                                    # Reset decay to 3 to give it more runway
                                    meta['decay_score'] = 3
                                    strat_orm.strategy_metadata = meta
                                    flag_modified(strat_orm, 'strategy_metadata')
                                    result["updated"] += 1
                                    should_retire = False
                                elif live_pnl > 0:
                                    logger.info(
                                        f"[StrategyDecay] {strat_orm.name}: decay=0, P&L +${live_pnl:,.2f} "
                                        f"({live_pnl/live_invested:.1%}) below 2% winner threshold — retiring"
                                    )
                        
                        if should_retire:
                            top_penalties = sorted(penalties.items(), key=lambda x: -x[1])[:3]
                            reason_parts = [f"{k}(-{v:.0f})" for k, v in top_penalties]
                            retirement_reason = f"Edge expired (decay=0): {', '.join(reason_parts)}"
                            
                            # Check if strategy has open positions
                            open_positions = session.query(PositionORM).filter(
                                PositionORM.strategy_id == strat_orm.id,
                                PositionORM.closed_at.is_(None)
                            ).all()
                            
                            if open_positions:
                                # Don't retire yet — let positions close via SL/TP first
                                logger.info(
                                    f"[StrategyDecay] {strat_orm.name} marked for pending retirement "
                                    f"({len(open_positions)} open positions must close first): {retirement_reason}"
                                )
                                meta['pending_retirement'] = True
                                meta['pending_retirement_reason'] = retirement_reason
                                meta['pending_retirement_at'] = datetime.now().isoformat()
                                meta.pop('activation_approved', None)
                                strat_orm.strategy_metadata = meta
                                flag_modified(strat_orm, 'strategy_metadata')
                            else:
                                # No open positions — demote to BACKTESTED (not permanently retired)
                                logger.info(
                                    f"[StrategyDecay] Demoting {strat_orm.name} to BACKTESTED "
                                    f"(decay=0, no open positions): {retirement_reason}"
                                )
                                strat_orm.status = StrategyStatus.BACKTESTED
                                strat_orm.retired_at = None
                                meta['activation_approved'] = False
                                meta['demoted_from_active'] = True
                                meta['demoted_at'] = datetime.now().isoformat()
                                meta['demotion_reason'] = retirement_reason
                                meta['demotion_ttl_days'] = 14
                                meta.pop('retirement_reason', None)
                                meta.pop('retired_by', None)
                                strat_orm.strategy_metadata = meta
                                flag_modified(strat_orm, 'strategy_metadata')
                                result["retired"] += 1
                        else:
                            logger.debug(
                                f"[StrategyDecay] {strat_orm.name}: decay=0 but in probation "
                                f"({age_days}d < {probation_days}d for {interval} interval)"
                            )
                    else:
                        logger.debug(
                            f"[StrategyDecay] {strat_orm.name}: decay={decay_score} "
                            f"penalties={penalties}"
                        )
                
                session.commit()
                
                if result["retired"] > 0 or result["updated"] > 0:
                    logger.info(
                        f"[StrategyDecay] Checked {result['checked']}, "
                        f"updated {result['updated']}, retired {result['retired']}"
                    )
                    
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error in strategy decay check: {e}", exc_info=True)
            result["errors"].append(str(e))
        
        return result

    def _retire_regime_incompatible_backtested(self) -> Dict:
        """
        Retire BACKTESTED strategies whose template is not valid for the current regime.

        When the market regime changes (e.g., ranging_low_vol → trending_up_weak),
        strategies built for the old regime should not be allowed to fire signals.
        They are demoted to RETIRED status so they don't clutter the BACKTESTED pool
        and don't accidentally get activated by the signal scanner.

        A strategy is regime-incompatible if its template_name is NOT in the set of
        templates that support the current regime (as defined by StrategyTemplateLibrary).

        Strategies with no template_name (legacy/manual) are left untouched.
        Strategies that are valid for BOTH old and new regime are left untouched.

        Returns:
            Dict with checked/retired counts
        """
        result = {"checked": 0, "retired": 0, "regime": "unknown", "errors": []}

        try:
            from src.models.orm import StrategyORM
            from src.models.enums import StrategyStatus
            from sqlalchemy.orm.attributes import flag_modified
            from src.strategy.strategy_templates import StrategyTemplateLibrary, MarketRegime
            from src.strategy.market_analyzer import MarketStatisticsAnalyzer
            from src.data.market_data_manager import get_market_data_manager

            # Detect current regime
            current_regime_str = 'unknown'
            try:
                _mdm = get_market_data_manager()
                if _mdm:
                    _analyzer = MarketStatisticsAnalyzer(_mdm)
                    sub_regime, confidence, _, _ = _analyzer.detect_sub_regime()
                    current_regime_str = sub_regime.value
            except Exception as _e:
                logger.warning(f"[RegimeRetire] Could not detect regime: {_e}")
                return result

            result["regime"] = current_regime_str

            # Only act on a known regime
            if current_regime_str == 'unknown':
                return result

            # Check if regime changed since last run
            regime_changed = (self._last_known_regime is not None and
                              self._last_known_regime != current_regime_str)
            self._last_known_regime = current_regime_str

            if not regime_changed:
                # No change — nothing to do
                logger.debug(f"[RegimeRetire] Regime unchanged ({current_regime_str}), skipping")
                return result

            logger.info(
                f"[RegimeRetire] Regime change detected: "
                f"{result.get('prev_regime', 'unknown')} → {current_regime_str} — "
                f"scanning BACKTESTED pool for incompatible strategies"
            )

            # Build set of template names valid for the current regime
            try:
                current_regime_enum = MarketRegime(current_regime_str)
            except ValueError:
                logger.warning(f"[RegimeRetire] Unknown regime enum value: {current_regime_str}")
                return result

            lib = StrategyTemplateLibrary()
            valid_templates = {t.name for t in lib.get_templates_for_regime(current_regime_enum)}

            # Also include parent regime templates (trending_up_weak → trending_up fallback)
            parent_regime_map = {
                'ranging_low_vol': 'ranging',
                'ranging_high_vol': 'ranging',
                'trending_up_strong': 'trending_up',
                'trending_up_weak': 'trending_up',
                'trending_down_strong': 'trending_down',
                'trending_down_weak': 'trending_down',
            }
            parent_name = parent_regime_map.get(current_regime_str)
            if parent_name:
                try:
                    parent_enum = MarketRegime(parent_name)
                    for t in lib.get_templates_for_regime(parent_enum):
                        valid_templates.add(t.name)
                except ValueError:
                    pass

            logger.info(
                f"[RegimeRetire] {len(valid_templates)} templates valid for {current_regime_str}"
            )

            session = self.db.get_session()
            try:
                backtested = session.query(StrategyORM).filter(
                    StrategyORM.status == StrategyStatus.BACKTESTED
                ).all()

                for strat_orm in backtested:
                    result["checked"] += 1
                    meta = strat_orm.strategy_metadata if isinstance(strat_orm.strategy_metadata, dict) else {}
                    template_name = meta.get('template_name')

                    # Skip strategies with no template_name (legacy/manual)
                    if not template_name:
                        continue

                    # Skip Alpha Edge strategies — they have their own regime logic
                    if meta.get('strategy_category') == 'alpha_edge':
                        continue

                    # Skip if template is valid for current regime
                    if template_name in valid_templates:
                        continue

                    # Template is not valid for current regime — retire it
                    reason = (
                        f"Regime change: template '{template_name}' is not valid for "
                        f"{current_regime_str} (was valid for previous regime)"
                    )
                    logger.info(f"[RegimeRetire] Retiring {strat_orm.name}: {reason}")

                    strat_orm.status = StrategyStatus.RETIRED
                    strat_orm.retired_at = datetime.now()
                    meta['activation_approved'] = False
                    meta['regime_retired'] = True
                    meta['regime_retirement_reason'] = reason
                    meta['regime_retired_at'] = datetime.now().isoformat()
                    meta['regime_retired_from'] = current_regime_str
                    strat_orm.strategy_metadata = meta
                    flag_modified(strat_orm, 'strategy_metadata')
                    result["retired"] += 1

                session.commit()

                if result["retired"] > 0:
                    logger.info(
                        f"[RegimeRetire] Regime change {current_regime_str}: "
                        f"checked {result['checked']}, retired {result['retired']} "
                        f"incompatible BACKTESTED strategies"
                    )
                else:
                    logger.info(
                        f"[RegimeRetire] Regime change {current_regime_str}: "
                        f"checked {result['checked']}, all compatible — nothing retired"
                    )

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[RegimeRetire] Error: {e}", exc_info=True)
            result["errors"].append(str(e))

        return result

    def _demote_idle_strategies(self) -> None:
        """
        Demote DEMO strategies with no open positions or pending orders back to BACKTESTED.

        Keeps activation_approved=True so they continue scanning for signals.
        Runs alongside the time-based exit check (every _fundamental_check_interval).
        
        Safety: Uses a fresh session with expire_on_commit=False and a raw SQL
        double-check to prevent false demotions from stale ORM cache. Also requires
        24h cooldown since last activation to avoid race conditions with position sync.
        """
        session = self.db.get_session()
        try:
            from src.models.orm import StrategyORM, PositionORM, OrderORM
            from src.models.enums import StrategyStatus, OrderStatus
            from sqlalchemy.orm.attributes import flag_modified
            from datetime import timedelta

            # Expire all cached ORM state to force fresh reads from DB
            session.expire_all()

            demo_strategies = session.query(StrategyORM).filter(
                StrategyORM.status == StrategyStatus.DEMO
            ).all()

            if not demo_strategies:
                return

            demoted = 0
            for s in demo_strategies:
                has_positions = session.query(PositionORM).filter(
                    PositionORM.strategy_id == s.id,
                    PositionORM.closed_at.is_(None)
                ).count() > 0

                has_pending = session.query(OrderORM).filter(
                    OrderORM.strategy_id == s.id,
                    OrderORM.status == OrderStatus.PENDING
                ).count() > 0

                # Also check for recently filled orders — the position may not have
                # synced from eToro yet (takes 30-60s). Don't demote if an order
                # was filled in the last 60 minutes (widened from 5 min for safety).
                has_recent_fill = False
                try:
                    recent_cutoff = datetime.now() - timedelta(minutes=60)
                    has_recent_fill = session.query(OrderORM).filter(
                        OrderORM.strategy_id == s.id,
                        OrderORM.status == OrderStatus.FILLED,
                        OrderORM.submitted_at >= recent_cutoff
                    ).count() > 0
                except Exception:
                    pass

                if not has_positions and not has_pending and not has_recent_fill:
                    # SAFETY DOUBLE-CHECK: raw SQL query on a fresh connection to
                    # avoid any ORM caching issues that caused false demotions.
                    try:
                        raw_count = session.execute(
                            session.bind.execute(
                                "SELECT COUNT(*) FROM positions WHERE strategy_id = ? AND closed_at IS NULL",
                                (s.id,)
                            ) if hasattr(session.bind, 'execute') else
                            __import__('sqlalchemy').text(
                                "SELECT COUNT(*) FROM positions WHERE strategy_id = :sid AND closed_at IS NULL"
                            ),
                            {"sid": s.id}
                        ).scalar()
                        if raw_count and raw_count > 0:
                            logger.warning(
                                f"ORM said no positions for {s.name} but raw SQL found {raw_count}! "
                                f"Skipping demotion (ORM cache stale)."
                            )
                            continue
                    except Exception as e:
                        # If raw check fails, err on the side of caution — don't demote
                        logger.warning(f"Raw SQL position check failed for {s.name}: {e} — skipping demotion")
                        continue

                    s.status = StrategyStatus.BACKTESTED
                    meta = s.strategy_metadata if isinstance(s.strategy_metadata, dict) else {}
                    meta['activation_approved'] = True
                    meta['demoted_at'] = datetime.now().isoformat()
                    meta['signal_cycles_without_trade'] = 0  # Reset TTL — was just actively trading
                    s.strategy_metadata = meta
                    flag_modified(s, 'strategy_metadata')
                    demoted += 1
                    logger.info(f"Demoted idle DEMO strategy to BACKTESTED: {s.name} (no open positions/pending orders)")

            session.commit()
            if demoted > 0:
                logger.info(f"Demoted {demoted} idle DEMO strategies to BACKTESTED")

            # --- Self-healing: promote BACKTESTED strategies that have open positions ---
            # If a strategy was falsely demoted (ORM cache, race condition, etc.),
            # promote it back to DEMO so monitoring/trailing stops keep working.
            session.expire_all()
            backtested_with_positions = session.query(StrategyORM).filter(
                StrategyORM.status == StrategyStatus.BACKTESTED
            ).all()

            promoted = 0
            for s in backtested_with_positions:
                has_open = session.query(PositionORM).filter(
                    PositionORM.strategy_id == s.id,
                    PositionORM.closed_at.is_(None)
                ).count() > 0

                if has_open:
                    s.status = StrategyStatus.DEMO
                    promoted += 1
                    logger.warning(
                        f"Re-promoted BACKTESTED strategy to DEMO: {s.name} "
                        f"(has open positions — was falsely demoted)"
                    )

            if promoted > 0:
                session.commit()
                logger.info(f"Re-promoted {promoted} BACKTESTED strategies with open positions to DEMO")

        except Exception as e:
            logger.error(f"Error in _demote_idle_strategies: {e}", exc_info=True)
            session.rollback()
        finally:
            session.close()

    def _get_fundamental_provider(self):
        """Lazy-load and return the shared FundamentalDataProvider singleton."""
        try:
            from src.data.fundamental_data_provider import get_fundamental_data_provider
            return get_fundamental_data_provider()
        except Exception as e:
            logger.error(f"Failed to get FundamentalDataProvider: {e}")
            return None

    def _sync_news_sentiment(self) -> None:
        """
        Background news sentiment sync — runs as part of daily sync.

        Priority queue (respects 100 req/day free tier):
          1. Symbols with open positions (protect existing trades)
          2. Active strategy symbols not yet in DB
          3. Stale symbols (TTL expired)

        Fetches up to 80 symbols per run (leaves 20 buffer for signal-time queuing).
        """
        try:
            from src.data.news_sentiment_provider import get_news_sentiment_provider
            provider = get_news_sentiment_provider()
            if provider is None:
                return

            from src.models.orm import PositionORM, StrategyORM
            from src.models.enums import StrategyStatus
            from src.core.tradeable_instruments import (
                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES,
                DEMO_ALLOWED_ETFS,
            )
            import json

            non_stock = (
                set(DEMO_ALLOWED_CRYPTO) | set(DEMO_ALLOWED_FOREX) |
                set(DEMO_ALLOWED_INDICES) | set(DEMO_ALLOWED_COMMODITIES) |
                set(DEMO_ALLOWED_ETFS)
            )

            session = self.db.get_session()
            try:
                # Priority 1: symbols with open positions
                open_syms = {
                    p.symbol for p in session.query(PositionORM).filter(
                        PositionORM.closed_at.is_(None)
                    ).all()
                    if p.symbol and p.symbol.upper() not in non_stock
                }

                # Priority 2: active strategy symbols
                active_syms = set()
                for s in session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
                ).all():
                    if s.symbols:
                        try:
                            syms = json.loads(s.symbols) if isinstance(s.symbols, str) else s.symbols
                            active_syms.update(
                                sym for sym in syms
                                if sym and sym.upper() not in non_stock
                            )
                        except Exception:
                            pass
            finally:
                session.close()

            # Build priority-ordered list, deduped
            queue = list(open_syms)
            for sym in active_syms:
                if sym not in open_syms:
                    queue.append(sym)

            # Only process symbols that need refresh
            to_fetch = [s for s in queue if provider.needs_refresh(s)]

            if not to_fetch:
                logger.info("[NewsSentiment] All symbols fresh — nothing to fetch")
                return

            # Cap at 80 to leave buffer
            to_fetch = to_fetch[:80]
            logger.info(f"[NewsSentiment] Syncing {len(to_fetch)} symbols "
                        f"({len(open_syms)} with positions, {len(active_syms)} active strategies)")

            fetched = 0
            for sym in to_fetch:
                score = provider.fetch_and_store(sym)
                if score is not None:
                    fetched += 1
                else:
                    break  # Rate limit hit — stop for today

            logger.info(f"[NewsSentiment] Sync complete: {fetched}/{len(to_fetch)} symbols updated")

        except Exception as e:
            logger.warning(f"[NewsSentiment] Sync error: {e}")

    def _get_regime_and_sectors(self) -> tuple:
        """
        Detect the current market regime and return optimal sector ETFs.

        Returns:
            Tuple of (regime_string, list_of_optimal_sector_etfs).
            Returns (None, []) on failure.
        """
        regime_sector_map = {
            'trending_up': ['XLK', 'XLY', 'XLF'],
            'trending_up_strong': ['XLK', 'XLY', 'XLF'],
            'trending_up_weak': ['XLK', 'XLV', 'XLI'],
            'trending_down': ['XLU', 'XLP', 'XLV'],
            'trending_down_strong': ['XLU', 'XLP', 'XLV'],
            'trending_down_weak': ['XLU', 'XLP', 'XLV'],
            'ranging': ['XLE', 'XLI', 'XLF'],
            'ranging_low_vol': ['XLK', 'XLF', 'XLI'],
            'ranging_high_vol': ['XLU', 'XLP', 'XLV'],
        }
        try:
            from src.data.market_data_manager import MarketDataManager
            from src.strategy.market_analyzer import MarketStatisticsAnalyzer

            mdm = MarketDataManager(etoro_client=self.etoro_client)
            analyzer = MarketStatisticsAnalyzer(mdm)
            regime_enum, _confidence, _quality, _metrics = analyzer.detect_sub_regime(symbols=["SPY"])
            regime_str = str(regime_enum).lower().replace("marketregime.", "")
            optimal = regime_sector_map.get(regime_str, ['XLK', 'XLF', 'XLI'])
            logger.debug(f"Current regime: {regime_str}, optimal sectors: {optimal}")
            return regime_str, optimal
        except Exception as e:
            logger.warning(f"Could not detect market regime for sector rotation exit: {e}")
            return None, []

    def _load_stale_order_config(self) -> Dict:
        """Load stale order cleanup configuration from YAML."""
        try:
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f) or {}
                order_mgmt = config.get('position_management', {}).get('order_management', {})
                return {
                    'enabled': order_mgmt.get('cancel_stale_orders', True),
                    'pending_timeout_hours': order_mgmt.get('stale_order_timeout_hours', order_mgmt.get('stale_order_timeout_hours_pending', 24)),
                }
        except Exception as e:
            logger.warning(f"Could not load stale order config: {e}")
        return {
            'enabled': True,
            'pending_timeout_hours': 24,
        }

    def _cleanup_stale_orders(self) -> Dict:
        """Cancel orders stuck in PENDING or SUBMITTED status beyond configured timeouts.

        PENDING orders older than 24h (configurable) are cancelled — market should have opened.
        SUBMITTED orders older than 48h (configurable) are cancelled — eToro should have responded.

        Returns:
            Dictionary with cleanup results including counts by status.
        """
        config = self._stale_order_config
        if not config.get('enabled', True):
            logger.debug("Stale order cleanup disabled in config")
            return {"skipped": True}

        pending_timeout = config.get('pending_timeout_hours', 24)

        logger.info(
            f"Running stale order cleanup "
            f"(PENDING timeout: {pending_timeout}h)"
        )

        try:
            results = self.order_monitor.cancel_stale_orders(
                pending_timeout_hours=pending_timeout,
            )

            cancelled = results.get('cancelled', 0)
            if cancelled > 0:
                logger.info(
                    f"Stale order cleanup: cancelled {cancelled} orders "
                    f"({results.get('cancelled_pending', 0)} PENDING)"
                )
            else:
                logger.debug("Stale order cleanup: no stale orders found")

            return results

        except Exception as e:
            logger.error(f"Error during stale order cleanup: {e}")
            return {"error": str(e)}

    def get_circuit_breaker_states(self) -> Dict[str, Dict]:
        """Return circuit breaker states from the eToro client (for dashboard/WebSocket)."""
        try:
            return self.etoro_client.get_circuit_breaker_states()
        except Exception as e:
            logger.error(f"Failed to get circuit breaker states: {e}")
            return {}

    def _load_schedule_config(self) -> Dict:
        """Load autonomous schedule config from YAML."""
        try:
            with open("config/autonomous_trading.yaml", "r") as f:
                config = yaml.safe_load(f)
            return config.get("autonomous_schedule", {
                "enabled": True,
                "frequency": "weekly",
                "day_of_week": "sunday",
                "hour": 2,
                "minute": 0,
            })
        except Exception as e:
            logger.warning(f"Could not load schedule config: {e}")
            return {"enabled": False}

    def _reload_schedule_config(self):
        """Reload schedule config from YAML (called when config is updated via API)."""
        self._schedule_config = self._load_schedule_config()
        logger.info(f"Schedule config reloaded: {self._schedule_config}")

    def _check_scheduled_cycle(self):
        """Check if it's time to run a scheduled autonomous cycle."""
        config = self._schedule_config
        if not config.get("enabled", False):
            return

        now = datetime.utcnow()
        target_hour = config.get("hour", 2)
        target_minute = config.get("minute", 0)
        frequency = config.get("frequency", "weekly")

        # Check if we're within the target time window (within 2 minutes)
        if now.hour != target_hour or abs(now.minute - target_minute) > 1:
            return

        # For weekly schedule, check day of week
        if frequency == "weekly":
            day_map = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }
            target_day = day_map.get(config.get("day_of_week", "sunday").lower(), 6)
            if now.weekday() != target_day:
                return

        # Prevent running more than once per window — check if we already ran today
        if self._last_scheduled_cycle_time:
            elapsed = (now - self._last_scheduled_cycle_time).total_seconds()
            if elapsed < 3600:  # Don't re-trigger within 1 hour
                return

        # Time to run!
        logger.info(f"[ScheduledCycle] Triggering scheduled autonomous cycle "
                     f"(frequency={frequency}, day={config.get('day_of_week')}, "
                     f"hour={target_hour}:{target_minute:02d})")
        self._last_scheduled_cycle_time = now

        try:
            from src.strategy.autonomous_strategy_manager import AutonomousStrategyManager
            manager = AutonomousStrategyManager()
            result = manager.run_full_cycle()
            logger.info(f"[ScheduledCycle] Completed: {result}")
        except Exception as e:
            logger.error(f"[ScheduledCycle] Failed: {e}", exc_info=True)

    def _evaluate_alerts(self) -> Dict:
        """
        Evaluate alert thresholds against current metrics and create AlertHistory entries.
        
        Checks:
        - Daily P&L thresholds (loss/gain)
        - Drawdown threshold
        - Individual position loss threshold
        - Margin utilization threshold
        
        Returns dict with triggered count.
        """
        from src.models.orm import AlertConfigORM, AlertHistoryORM, PositionORM, AccountInfoORM
        from sqlalchemy import func
        
        triggered = 0
        try:
            session = self.db.SessionLocal()
            try:
                config = session.query(AlertConfigORM).first()
                if not config:
                    return {"triggered": 0}
                
                # Get account info for P&L and margin checks
                account = session.query(AccountInfoORM).order_by(AccountInfoORM.updated_at.desc()).first()
                
                # Get open positions for position-level checks
                open_positions = session.query(PositionORM).filter(
                    PositionORM.closed_at.is_(None)
                ).all()
                
                # --- P&L Loss Alert ---
                if config.pnl_loss_enabled and account:
                    daily_pnl = getattr(account, 'daily_pnl', None) or 0
                    if daily_pnl < -abs(config.pnl_loss_threshold):
                        # Check if we already alerted today for this
                        existing = session.query(AlertHistoryORM).filter(
                            AlertHistoryORM.alert_type == "pnl_loss",
                            AlertHistoryORM.created_at >= datetime.now().replace(hour=0, minute=0, second=0),
                        ).first()
                        if not existing:
                            alert = AlertHistoryORM(
                                alert_type="pnl_loss",
                                severity="critical",
                                title="Daily P&L Loss Alert",
                                message=f"Daily P&L has dropped to ${daily_pnl:,.2f}, below your -${config.pnl_loss_threshold:,.2f} threshold.",
                                alert_metadata={"daily_pnl": daily_pnl, "threshold": config.pnl_loss_threshold},
                                link_page="/overview",
                            )
                            session.add(alert)
                            triggered += 1
                
                # --- P&L Gain Alert ---
                if config.pnl_gain_enabled and account:
                    daily_pnl = getattr(account, 'daily_pnl', None) or 0
                    if daily_pnl > abs(config.pnl_gain_threshold):
                        existing = session.query(AlertHistoryORM).filter(
                            AlertHistoryORM.alert_type == "pnl_gain",
                            AlertHistoryORM.created_at >= datetime.now().replace(hour=0, minute=0, second=0),
                        ).first()
                        if not existing:
                            alert = AlertHistoryORM(
                                alert_type="pnl_gain",
                                severity="info",
                                title="Daily P&L Gain Alert",
                                message=f"Daily P&L has reached +${daily_pnl:,.2f}, exceeding your +${config.pnl_gain_threshold:,.2f} target.",
                                alert_metadata={"daily_pnl": daily_pnl, "threshold": config.pnl_gain_threshold},
                                link_page="/overview",
                            )
                            session.add(alert)
                            triggered += 1
                
                # --- Drawdown Alert ---
                if config.drawdown_enabled and account:
                    balance = getattr(account, 'balance', None) or 0
                    stored_eq = getattr(account, 'equity', None) or 0
                    # If stored equity is stale (0 or same as balance), compute from open positions
                    if stored_eq and stored_eq != balance:
                        equity = stored_eq
                    else:
                        # Compute equity from balance + unrealized P&L of open positions
                        try:
                            unrealized_sum = session.query(func.sum(PositionORM.unrealized_pnl)).filter(
                                PositionORM.closed_at.is_(None)
                            ).scalar()
                            equity = balance + (float(unrealized_sum) if unrealized_sum else 0.0)
                        except Exception:
                            equity = balance
                    if balance > 0 and equity > 0:
                        drawdown_pct = ((balance - equity) / balance) * 100 if equity < balance else 0
                        if drawdown_pct > config.drawdown_threshold:
                            existing = session.query(AlertHistoryORM).filter(
                                AlertHistoryORM.alert_type == "drawdown",
                                AlertHistoryORM.created_at >= datetime.now().replace(hour=0, minute=0, second=0),
                            ).first()
                            if not existing:
                                alert = AlertHistoryORM(
                                    alert_type="drawdown",
                                    severity="warning",
                                    title="Drawdown Alert",
                                    message=f"Current drawdown is {drawdown_pct:.1f}%, exceeding your {config.drawdown_threshold:.1f}% threshold.",
                                    alert_metadata={"drawdown_pct": drawdown_pct, "threshold": config.drawdown_threshold},
                                    link_page="/risk",
                                )
                                session.add(alert)
                                triggered += 1
                
                # --- Position Loss Alert ---
                if config.position_loss_enabled and open_positions:
                    for pos in open_positions:
                        pnl_pct = 0
                        if pos.entry_price and pos.entry_price > 0 and pos.current_price:
                            if pos.side == "BUY":
                                pnl_pct = ((pos.current_price - pos.entry_price) / pos.entry_price) * 100
                            else:
                                pnl_pct = ((pos.entry_price - pos.current_price) / pos.entry_price) * 100
                        
                        if pnl_pct < -abs(config.position_loss_threshold):
                            # Only alert once per position per day
                            existing = session.query(AlertHistoryORM).filter(
                                AlertHistoryORM.alert_type == "position_loss",
                                AlertHistoryORM.created_at >= datetime.now().replace(hour=0, minute=0, second=0),
                                AlertHistoryORM.alert_metadata.contains(str(pos.id)) if pos.id else False,
                            ).first()
                            if not existing:
                                symbol = pos.symbol or "Unknown"
                                alert = AlertHistoryORM(
                                    alert_type="position_loss",
                                    severity="warning",
                                    title=f"Position Loss: {symbol}",
                                    message=f"{symbol} position is down {abs(pnl_pct):.1f}%, exceeding your {config.position_loss_threshold:.1f}% threshold.",
                                    alert_metadata={"position_id": pos.id, "symbol": symbol, "pnl_pct": pnl_pct},
                                    link_page="/portfolio",
                                )
                                session.add(alert)
                                triggered += 1
                
                if triggered > 0:
                    session.commit()
                    
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error evaluating alerts: {e}", exc_info=True)
        
        return {"triggered": triggered}


# Global instance
_monitoring_service: Optional[MonitoringService] = None


def get_monitoring_service() -> Optional[MonitoringService]:
    """Get the global monitoring service instance."""
    return _monitoring_service


def set_monitoring_service(service: MonitoringService):
    """Set the global monitoring service instance."""
    global _monitoring_service
    _monitoring_service = service
