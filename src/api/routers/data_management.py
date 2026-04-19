"""Data Management API — status, manual sync trigger, DB stats."""

import logging
import threading
import time as _time
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/data", tags=["data-management"])

# Track running sync state
_running_sync_thread: Optional[threading.Thread] = None
_last_sync_result: Optional[dict] = None
_sync_log_lines: List[str] = []
_sync_started_at: Optional[float] = None


class SyncStatusResponse(BaseModel):
    last_sync_at: Optional[str] = None
    last_sync_success: bool = False
    last_sync_duration_s: Optional[float] = None
    last_sync_stats: Optional[dict] = None
    sync_running: bool = False
    sync_interval_s: int = 3300
    db_stats: Optional[dict] = None
    sync_logs: Optional[list] = None
    sync_elapsed_s: Optional[float] = None
    quick_update: Optional[dict] = None


class SyncTriggerResponse(BaseModel):
    success: bool
    message: str


def _capture_log(msg: str):
    """Append a log line with timestamp."""
    global _sync_log_lines
    ts = datetime.now().strftime("%H:%M:%S")
    _sync_log_lines.append(f"[{ts}] {msg}")


@router.get("/sync/status", response_model=SyncStatusResponse)
async def get_data_sync_status():
    """Get current data sync status, last run info, and DB stats."""
    global _running_sync_thread, _last_sync_result, _sync_log_lines, _sync_started_at

    sync_running = _running_sync_thread is not None and _running_sync_thread.is_alive()

    # If sync is running, calculate elapsed time
    sync_elapsed = None
    if sync_running and _sync_started_at:
        sync_elapsed = round(_time.time() - _sync_started_at, 1)

    # Get monitoring service state for background sync info
    last_sync_at = None
    last_sync_success = False
    last_sync_duration = None
    sync_interval = 3300

    try:
        from src.core.monitoring_service import get_monitoring_service
        mon = get_monitoring_service()
        if mon:
            sync_interval = getattr(mon, '_price_sync_interval', 3300)
            last_ts = getattr(mon, '_last_price_sync', 0)
            if last_ts > 0:
                last_sync_at = datetime.fromtimestamp(last_ts).isoformat()
                last_sync_success = True
    except Exception as e:
        logger.debug(f"Could not read monitoring service state: {e}")

    # Manual sync result overrides background sync info
    if _last_sync_result:
        last_sync_at = _last_sync_result.get("completed_at", last_sync_at)
        last_sync_success = _last_sync_result.get("success", False)
        last_sync_duration = _last_sync_result.get("duration_s")

    db_stats = _get_db_stats()

    # Get quick price update status
    quick_update = None
    try:
        from src.core.monitoring_service import get_monitoring_service
        mon_qu = get_monitoring_service()
        if mon_qu and hasattr(mon_qu, '_last_quick_update_result'):
            quick_update = mon_qu._last_quick_update_result
    except Exception:
        pass

    return SyncStatusResponse(
        last_sync_at=last_sync_at,
        last_sync_success=last_sync_success,
        last_sync_duration_s=last_sync_duration,
        last_sync_stats=_last_sync_result.get("stats") if _last_sync_result else None,
        sync_running=sync_running,
        sync_interval_s=sync_interval,
        db_stats=db_stats,
        sync_logs=list(_sync_log_lines[-50:]),  # Last 50 lines
        sync_elapsed_s=sync_elapsed,
        quick_update=quick_update,
    )


@router.post("/sync/trigger", response_model=SyncTriggerResponse)
async def trigger_data_sync():
    """Manually trigger a full price data sync."""
    global _running_sync_thread, _last_sync_result, _sync_log_lines, _sync_started_at

    if _running_sync_thread and _running_sync_thread.is_alive():
        return SyncTriggerResponse(success=False, message="Sync already running")

    # Clear previous logs
    _sync_log_lines = []
    _sync_started_at = _time.time()

    def _run_sync():
        global _last_sync_result, _sync_started_at
        t0 = _time.time()
        _capture_log("Starting manual data sync...")

        try:
            from src.core.monitoring_service import get_monitoring_service
            mon = get_monitoring_service()

            if not mon:
                _capture_log("ERROR: Monitoring service not available")
                _last_sync_result = {
                    "success": False,
                    "completed_at": datetime.now().isoformat(),
                    "duration_s": 0,
                    "stats": {"message": "Monitoring service not available"},
                }
                return

            _capture_log(f"Monitoring service found, calling _sync_price_data()...")

            # Run the actual sync with detailed logging
            _run_sync_with_logging(mon)

        except Exception as e:
            elapsed = _time.time() - t0
            _capture_log(f"ERROR: Sync failed after {elapsed:.1f}s: {e}")
            import traceback
            _capture_log(traceback.format_exc()[-500:])
            _last_sync_result = {
                "success": False,
                "completed_at": datetime.now().isoformat(),
                "duration_s": round(elapsed, 1),
                "stats": {"message": str(e)},
            }
        finally:
            _sync_started_at = None

    _running_sync_thread = threading.Thread(target=_run_sync, daemon=True)
    _running_sync_thread.start()

    return SyncTriggerResponse(success=True, message="Data sync started")


# Track running quick update
_running_quick_thread: Optional[threading.Thread] = None


@router.post("/quick-update/trigger", response_model=SyncTriggerResponse)
async def trigger_quick_update():
    """Manually trigger a quick eToro price update + signal check."""
    global _running_quick_thread

    if _running_quick_thread and _running_quick_thread.is_alive():
        return SyncTriggerResponse(success=False, message="Quick update already running")

    def _run():
        try:
            from src.core.monitoring_service import get_monitoring_service
            mon = get_monitoring_service()
            if mon:
                mon._quick_price_update()
            else:
                logger.warning("Quick update: monitoring service not available")
        except Exception as e:
            logger.error(f"Quick update trigger failed: {e}")

    _running_quick_thread = threading.Thread(target=_run, daemon=True)
    _running_quick_thread.start()

    return SyncTriggerResponse(success=True, message="Quick price update started")


# ── FMP Fundamental Cache ─────────────────────────────────────────────────────

# Shared state for FMP cache warm progress
_fmp_cache_thread: Optional[threading.Thread] = None
_fmp_cache_progress: dict = {
    "running": False,
    "current": 0,
    "total": 0,
    "fetched": 0,
    "cached": 0,
    "failed": 0,
    "started_at": None,
    "completed_at": None,
    "elapsed_s": None,
    "last_warm_at": None,
    "coverage_pct": 0.0,
    "error": None,
}


def _compute_fmp_coverage() -> dict:
    """Compute FMP cache coverage stats from DB."""
    try:
        from src.models.database import get_database
        from src.models.orm import FundamentalDataORM
        from src.data.fmp_cache_warmer import FMPCacheWarmer
        from src.core.tradeable_instruments import get_tradeable_symbols
        from src.models.enums import TradingMode
        from datetime import datetime, timedelta

        all_symbols = get_tradeable_symbols(TradingMode.DEMO)
        stock_symbols = [s for s in all_symbols if s not in FMPCacheWarmer.SKIP_FUNDAMENTALS]
        total = len(stock_symbols)

        db = get_database()
        session = db.get_session()
        try:
            fresh_cutoff = datetime.now() - timedelta(days=7)
            fresh_count = session.query(FundamentalDataORM).filter(
                FundamentalDataORM.fetched_at >= fresh_cutoff
            ).count()
            any_count = session.query(FundamentalDataORM).count()
        finally:
            session.close()

        last_warm = FMPCacheWarmer.get_last_warm_timestamp()
        return {
            "total_symbols": total,
            "fresh_count": fresh_count,
            "any_count": any_count,
            "coverage_pct": round(fresh_count / total * 100, 1) if total > 0 else 0.0,
            "last_warm_at": last_warm.isoformat() if last_warm else None,
        }
    except Exception as e:
        logger.warning(f"Could not compute FMP coverage: {e}")
        return {"total_symbols": 0, "fresh_count": 0, "any_count": 0, "coverage_pct": 0.0, "last_warm_at": None}


@router.get("/fmp-cache/status")
async def get_fmp_cache_status():
    """Get FMP fundamental cache status and coverage."""
    global _fmp_cache_progress, _fmp_cache_thread
    coverage = _compute_fmp_coverage()
    # running = True if thread is alive OR progress dict says running
    # (handles the race between trigger response and thread startup)
    thread_alive = _fmp_cache_thread is not None and _fmp_cache_thread.is_alive()
    is_running = thread_alive or _fmp_cache_progress.get("running", False)
    return {
        **_fmp_cache_progress,
        **coverage,
        "running": is_running,
    }


@router.post("/fmp-cache/trigger", response_model=SyncTriggerResponse)
async def trigger_fmp_cache_warm():
    """Manually trigger FMP fundamental data cache warm."""
    global _fmp_cache_thread, _fmp_cache_progress

    if _fmp_cache_thread and _fmp_cache_thread.is_alive():
        # If thread has been running for more than 10 minutes, it's probably stuck
        started_at = _fmp_cache_progress.get("started_at")
        if started_at and (_time.time() - started_at) > 600:
            logger.warning("FMP cache warm thread appears stuck (>10min), allowing new trigger")
            # Don't kill the thread — just allow a new one to start
            # The old thread will eventually finish or timeout
        else:
            return SyncTriggerResponse(success=False, message="FMP cache warm already running")

    # Reset progress
    _fmp_cache_progress.update({
        "running": True,
        "current": 0,
        "total": 0,
        "fetched": 0,
        "cached": 0,
        "failed": 0,
        "started_at": _time.time(),
        "completed_at": None,
        "elapsed_s": None,
        "error": None,
    })

    def _run():
        global _fmp_cache_progress
        try:
            import yaml
            from pathlib import Path
            from src.data.fmp_cache_warmer import FMPCacheWarmer

            logger.info("FMP cache warm thread started")

            from src.core.config_loader import load_config
            config = load_config()

            logger.info(f"FMP cache warm: config loaded, FMP enabled={config.get('data_sources', {}).get('financial_modeling_prep', {}).get('enabled', False)}")

            # Force warm (bypass 24h timestamp check)
            warmer = FMPCacheWarmer(config)

            def _progress(current, total, warm_stats):
                _fmp_cache_progress.update({
                    "current": current,
                    "total": total,
                    "fetched": warm_stats.get("fundamentals_fetched", 0),
                    "cached": warm_stats.get("fundamentals_cached", 0),
                    "failed": warm_stats.get("fundamentals_failed", 0),
                    "elapsed_s": round(_time.time() - _fmp_cache_progress["started_at"], 1),
                })

            # Use 7-day TTL matching the coverage display — only fetch symbols
            # that are genuinely stale or missing. This means re-running 2-3 times
            # will progressively fill in only the symbols that failed previously,
            # without re-fetching symbols that were successfully cached this week.
            stats = warmer.warm_all_symbols(progress_callback=_progress, force_ttl_hours=168)

            elapsed = _time.time() - _fmp_cache_progress["started_at"]
            _fmp_cache_progress.update({
                "running": False,
                "current": stats.get("total_symbols", 0),
                "total": stats.get("total_symbols", 0),
                "fetched": stats.get("fundamentals_fetched", 0),
                "cached": stats.get("fundamentals_cached", 0),
                "failed": stats.get("fundamentals_failed", 0),
                "completed_at": _time.time(),
                "elapsed_s": round(elapsed, 1),
            })
            logger.info(f"Manual FMP cache warm complete in {elapsed:.1f}s: {stats}")

        except Exception as e:
            elapsed = _time.time() - (_fmp_cache_progress.get("started_at") or _time.time())
            _fmp_cache_progress.update({
                "running": False,
                "completed_at": _time.time(),
                "elapsed_s": round(elapsed, 1),
                "error": str(e)[:200],
            })
            logger.error(f"FMP cache warm failed: {e}", exc_info=True)

    _fmp_cache_thread = threading.Thread(target=_run, daemon=True, name="fmp-cache-warm")
    _fmp_cache_thread.start()

    return SyncTriggerResponse(success=True, message="FMP cache warm started")


def _run_sync_with_logging(mon) -> None:
    """Run the price data sync with detailed per-symbol logging captured to _sync_log_lines."""
    global _last_sync_result
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

        _capture_log(f"Symbol universe: {len(all_symbols)} total ({len(crypto_set)} crypto, {len(forex_set)} forex)")

        # Market hours
        try:
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            is_weekend = now_et.weekday() >= 5
            is_market_hours = (
                not is_weekend and
                now_et.hour >= 9 and now_et.hour < 16 and
                (now_et.hour > 9 or now_et.minute >= 30)
            )
            _capture_log(f"Market hours: {'open' if is_market_hours else 'closed'} (weekend={is_weekend}, ET={now_et.strftime('%H:%M')})")
        except Exception:
            is_weekend = False
            is_market_hours = False

        # Active strategy symbols
        active_symbols = set()
        try:
            from src.models.database import get_database
            db = get_database()
            session = db.get_session()
            try:
                active = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
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
        except Exception as e:
            _capture_log(f"WARNING: Could not load active strategies: {e}")

        _capture_log(f"Active strategy symbols: {len(active_symbols)}")

        # Init market data manager — use singleton, don't create a new instance
        from src.data.market_data_manager import get_market_data_manager
        md = get_market_data_manager()
        if md is None:
            # Singleton not registered yet (shouldn't happen during normal operation)
            from src.core.config_loader import load_config as _lc_md
            md = MarketDataManager(mon.etoro_client, config=_lc_md())

        end = datetime.now()
        stats = {
            "1d_fetched": 0, "1d_cached": 0, "1d_skip": 0, "1d_err": 0,
            "1h_fetched": 0, "1h_cached": 0, "1h_skip": 0, "1h_err": 0,
            "memory": 0, "weekend_skip": 0,
        }

        from datetime import timedelta

        for i, symbol in enumerate(all_symbols):
            sym_upper = symbol.upper()
            is_crypto = sym_upper in crypto_set
            is_forex = sym_upper in forex_set
            is_always_on = is_crypto or is_forex
            is_active = symbol in active_symbols

            # 1d sync
            should_sync_1d = is_always_on or not is_weekend
            if not should_sync_1d:
                stats["weekend_skip"] += 1
            else:
                try:
                    start_1d = end - timedelta(days=220)
                    # Check if DB already has fresh data (avoid counting cache hits as "synced")
                    db_data = md._get_historical_from_db(symbol, start_1d, end, "1d")
                    if db_data and len(db_data) > 50:
                        stats["1d_cached"] += 1
                        data_1d = db_data
                    else:
                        data_1d = md.get_historical_data(symbol, start_1d, end, interval="1d", prefer_yahoo=True)
                        if data_1d:
                            stats["1d_fetched"] += 1
                        else:
                            stats["1d_skip"] += 1
                    if data_1d and is_active:
                        hist_cache.set(f"{symbol}:1d:120", data_1d)
                        stats["memory"] += 1
                except Exception as e:
                    stats["1d_err"] += 1
                    if i < 5 or is_crypto:
                        _capture_log(f"  1d ERROR {symbol}: {str(e)[:100]}")

            # 1h sync
            should_sync_1h = is_always_on or is_market_hours
            if should_sync_1h:
                try:
                    start_1h = end - timedelta(days=180)
                    # For 1h, check DB freshness (stale if latest bar > 2h old)
                    from src.utils.symbol_mapper import normalize_symbol
                    norm_symbol = normalize_symbol(symbol)
                    db_1h = md._get_historical_from_db(norm_symbol, start_1h, end, "1h")
                    # Check if DB data is fresh — latest bar should be within 2 hours
                    db_is_fresh = False
                    if db_1h and len(db_1h) > 20:
                        latest_bar = db_1h[-1]
                        latest_ts = latest_bar.timestamp if hasattr(latest_bar, 'timestamp') else getattr(latest_bar, 'date', None)
                        if latest_ts:
                            from datetime import timezone
                            if hasattr(latest_ts, 'tzinfo') and latest_ts.tzinfo:
                                latest_ts = latest_ts.replace(tzinfo=None)
                            age_hours = (end - latest_ts).total_seconds() / 3600
                            db_is_fresh = age_hours < 2.0
                    
                    if db_is_fresh:
                        stats["1h_cached"] += 1
                        data_1h = db_1h
                    else:
                        # DB data is stale — clear the DB cache entry so get_historical_data
                        # doesn't just return the same stale data. This forces a Yahoo fetch.
                        try:
                            from src.models.database import get_database
                            _db = get_database()
                            _sess = _db.get_session()
                            try:
                                from src.models.orm import HistoricalPriceCacheORM
                                _sess.query(HistoricalPriceCacheORM).filter(
                                    HistoricalPriceCacheORM.symbol == norm_symbol,
                                    HistoricalPriceCacheORM.interval == "1h"
                                ).delete()
                                _sess.commit()
                            finally:
                                _sess.close()
                        except Exception:
                            pass  # If cleanup fails, get_historical_data will still try Yahoo
                        
                        # Also clear in-memory cache for this symbol
                        for cache_key_pattern in [f"{symbol}:1h:", f"{norm_symbol}:1h:"]:
                            keys_to_remove = [k for k in list(hist_cache._cache.keys()) if cache_key_pattern in str(k)]
                            for k in keys_to_remove:
                                del hist_cache._cache[k]
                        
                        data_1h = md.get_historical_data(symbol, start_1h, end, interval="1h", prefer_yahoo=True)
                        if data_1h:
                            md._save_historical_to_db(norm_symbol, data_1h, "1h")
                            stats["1h_fetched"] += 1
                        else:
                            stats["1h_skip"] += 1
                    if data_1h and is_active:
                        hist_cache.set(f"{symbol}:1h:25", data_1h)
                        stats["memory"] += 1
                except Exception as e:
                    stats["1h_err"] += 1
                    if i < 5 or is_crypto:
                        _capture_log(f"  1h ERROR {symbol}: {str(e)[:100]}")

            # Progress every 20 symbols
            if (i + 1) % 20 == 0:
                elapsed = _time.time() - t0
                _capture_log(
                    f"Progress: {i+1}/{len(all_symbols)} in {elapsed:.0f}s — "
                    f"1d: {stats['1d_fetched']} fetched, {stats['1d_cached']} cached, {stats['1d_err']} err | "
                    f"1h: {stats['1h_fetched']} fetched, {stats['1h_cached']} cached, {stats['1h_err']} err"
                )

        elapsed = _time.time() - t0
        total_1d = stats['1d_fetched'] + stats['1d_cached']
        total_1h = stats['1h_fetched'] + stats['1h_cached']
        _capture_log(
            f"DONE in {elapsed:.1f}s — "
            f"1d: {stats['1d_fetched']} fetched + {stats['1d_cached']} from DB = {total_1d} | "
            f"1h: {stats['1h_fetched']} fetched + {stats['1h_cached']} from DB = {total_1h} | "
            f"{stats['memory']} loaded to memory | "
            f"{stats['weekend_skip']} weekend-skipped | "
            f"{stats['1d_err']+stats['1h_err']} errors"
        )

        # Signal to trading scheduler
        mon._price_sync_completed = True

        _last_sync_result = {
            "success": stats['1d_err'] + stats['1h_err'] < len(all_symbols) * 0.2,
            "completed_at": datetime.now().isoformat(),
            "duration_s": round(elapsed, 1),
            "stats": {
                "daily_fetched": stats["1d_fetched"],
                "daily_cached": stats["1d_cached"],
                "daily_errors": stats["1d_err"],
                "daily_skipped": stats["1d_skip"],
                "hourly_fetched": stats["1h_fetched"],
                "hourly_cached": stats["1h_cached"],
                "hourly_errors": stats["1h_err"],
                "hourly_skipped": stats["1h_skip"],
                "weekend_skipped": stats["weekend_skip"],
                "memory_loaded": stats["memory"],
                "total_symbols": len(all_symbols),
                "active_symbols": len(active_symbols),
                "duration_s": round(elapsed, 1),
            },
        }

    except Exception as e:
        elapsed = _time.time() - t0
        _capture_log(f"FATAL: {e}")
        import traceback
        _capture_log(traceback.format_exc()[-500:])
        _last_sync_result = {
            "success": False,
            "completed_at": datetime.now().isoformat(),
            "duration_s": round(elapsed, 1),
            "stats": {"message": str(e)},
        }


def _get_db_stats() -> dict:
    """Get historical price cache DB statistics."""
    try:
        from src.models.database import get_database
        from sqlalchemy import text

        db = get_database()
        with db.engine.connect() as conn:
            total = conn.execute(text(
                "SELECT COUNT(*) FROM historical_price_cache"
            )).scalar() or 0

            by_interval = {}
            rows = conn.execute(text(
                "SELECT COALESCE(interval, '1d') as iv, COUNT(*) as cnt "
                "FROM historical_price_cache GROUP BY iv"
            )).fetchall()
            for row in rows:
                by_interval[row[0]] = row[1]

            symbols = conn.execute(text(
                "SELECT COUNT(DISTINCT symbol) FROM historical_price_cache"
            )).scalar() or 0

            latest = conn.execute(text(
                "SELECT MAX(date) FROM historical_price_cache"
            )).scalar()

            oldest = conn.execute(text(
                "SELECT MIN(date) FROM historical_price_cache"
            )).scalar()

            latest_1h = conn.execute(text(
                "SELECT symbol, MAX(date) as latest "
                "FROM historical_price_cache "
                "WHERE interval = '1h' "
                "GROUP BY symbol ORDER BY latest DESC LIMIT 5"
            )).fetchall()

            recent_1h = [{"symbol": r[0], "latest": str(r[1])} for r in latest_1h]

            return {
                "total_bars": total,
                "by_interval": by_interval,
                "unique_symbols": symbols,
                "latest_bar": str(latest) if latest else None,
                "oldest_bar": str(oldest) if oldest else None,
                "recent_1h_symbols": recent_1h,
            }
    except Exception as e:
        logger.debug(f"Could not get DB stats: {e}")
        return {"error": str(e)}


@router.get("/monitoring/status")
async def get_monitoring_status():
    """Get comprehensive status of all monitoring processes.
    
    Returns status for:
    - Main loop tasks (trailing stops, position sync, pending closures, alerts)
    - Background threads (quick price update, full price sync, signal generation)
    - Daily tasks (fundamental exits, stale order cleanup, performance feedback)
    """
    result = {
        "main_loop": {},
        "background": {},
        "daily": {},
        "system": {},
    }
    
    try:
        from src.core.monitoring_service import get_monitoring_service
        mon = get_monitoring_service()
        
        if not mon:
            return {"error": "Monitoring service not available"}
        
        now = datetime.now()
        
        def _age_str(ts):
            """Convert timestamp to human-readable age string."""
            if not ts:
                return "never"
            if isinstance(ts, (int, float)):
                if ts == 0:
                    return "never"
                dt = datetime.fromtimestamp(ts)
            else:
                dt = ts
            delta = (now - dt).total_seconds()
            if delta < 60:
                return f"{delta:.0f}s ago"
            elif delta < 3600:
                return f"{delta/60:.1f}m ago"
            else:
                return f"{delta/3600:.1f}h ago"
        
        def _ts_iso(ts):
            if not ts:
                return None
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts).isoformat() if ts > 0 else None
            return ts.isoformat() if hasattr(ts, 'isoformat') else str(ts)
        
        # === MAIN LOOP TASKS ===
        
        # Pending orders (every 5s)
        last_pending = getattr(mon, '_last_pending_check', 0)
        result["main_loop"]["pending_orders"] = {
            "name": "Process Pending Orders",
            "interval": f"{mon.pending_orders_interval}s",
            "last_run": _ts_iso(last_pending),
            "age": _age_str(last_pending),
            "status": "healthy" if last_pending and (now - datetime.fromtimestamp(last_pending)).total_seconds() < mon.pending_orders_interval * 3 else "stale",
        }
        
        # Order status (every 30s)
        last_order = getattr(mon, '_last_order_check', 0)
        result["main_loop"]["order_status"] = {
            "name": "Check Order Status (eToro)",
            "interval": f"{mon.order_status_interval}s",
            "last_run": _ts_iso(last_order),
            "age": _age_str(last_order),
            "status": "healthy" if last_order and (now - datetime.fromtimestamp(last_order)).total_seconds() < mon.order_status_interval * 3 else "stale",
        }
        
        # Position sync (every 60s)
        last_pos_sync = getattr(mon, '_last_position_sync', 0)
        result["main_loop"]["position_sync"] = {
            "name": "Position Sync (eToro)",
            "interval": f"{mon.position_sync_interval}s",
            "last_run": _ts_iso(last_pos_sync),
            "age": _age_str(last_pos_sync),
            "status": "healthy" if last_pos_sync and (now - datetime.fromtimestamp(last_pos_sync)).total_seconds() < mon.position_sync_interval * 3 else "stale",
        }
        
        # Trailing stops + partial exits (every 60s)
        last_trailing = getattr(mon, '_last_trailing_check', 0)
        result["main_loop"]["trailing_stops"] = {
            "name": "Trailing Stops + Partial Exits",
            "interval": f"{mon.trailing_stops_interval}s",
            "last_run": _ts_iso(last_trailing),
            "age": _age_str(last_trailing),
            "status": "healthy" if last_trailing and (now - datetime.fromtimestamp(last_trailing)).total_seconds() < mon.trailing_stops_interval * 3 else "stale",
        }
        
        # Pending closures (every 60s)
        last_closures = getattr(mon, '_last_pending_closure_check', 0)
        result["main_loop"]["pending_closures"] = {
            "name": "Pending Closures",
            "interval": f"{getattr(mon, '_pending_closure_interval', 60)}s",
            "last_run": _ts_iso(last_closures),
            "age": _age_str(last_closures),
        }
        
        # Alert evaluation (every 60s)
        last_alerts = getattr(mon, '_last_alert_check', 0)
        result["main_loop"]["alerts"] = {
            "name": "Alert Evaluation",
            "interval": f"{getattr(mon, '_alert_check_interval', 60)}s",
            "last_run": _ts_iso(last_alerts),
            "age": _age_str(last_alerts),
        }
        
        # === BACKGROUND THREADS ===
        
        # Quick price update (every 10m)
        quick_result = getattr(mon, '_last_quick_update_result', None)
        result["background"]["quick_price_update"] = {
            "name": "Quick Price Update (eToro)",
            "interval": "10m",
            "last_run": quick_result.get("timestamp") if quick_result else None,
            "age": _age_str(datetime.fromisoformat(quick_result["timestamp"])) if quick_result and quick_result.get("timestamp") else "never",
            "symbols_updated": quick_result.get("updated", 0) if quick_result else 0,
            "errors": quick_result.get("errors", 0) if quick_result else 0,
            "duration_s": quick_result.get("elapsed_s", 0) if quick_result else 0,
        }
        
        # Full price sync (every 55m)
        last_full_sync = getattr(mon, '_last_price_sync', 0)
        result["background"]["full_price_sync"] = {
            "name": "Full Price Sync (Yahoo)",
            "interval": "55m",
            "last_run": _ts_iso(last_full_sync),
            "age": _age_str(last_full_sync),
            "status": "healthy" if last_full_sync and (now - datetime.fromtimestamp(last_full_sync)).total_seconds() < 4200 else "stale",
        }
        
        # Signal generation
        try:
            from src.core.trading_scheduler import get_trading_scheduler
            scheduler = get_trading_scheduler()
            if scheduler:
                last_signal = getattr(scheduler, '_last_signal_check', 0)
                result["background"]["signal_generation"] = {
                    "name": "Signal Generation",
                    "interval": "~10m (after price update)",
                    "last_run": _ts_iso(last_signal),
                    "age": _age_str(last_signal),
                }
        except Exception:
            pass
        
        # === DAILY TASKS ===
        
        last_daily = getattr(mon, '_last_daily_sync', 0)
        result["daily"]["daily_maintenance"] = {
            "name": "Daily Maintenance",
            "interval": "24h",
            "last_run": _ts_iso(last_daily),
            "age": _age_str(last_daily),
        }
        
        last_fundamental = getattr(mon, '_last_fundamental_check', 0)
        result["daily"]["fundamental_exits"] = {
            "name": "Fundamental Exit Check",
            "interval": "24h",
            "last_run": _ts_iso(last_fundamental),
            "age": _age_str(last_fundamental),
        }
        
        last_stale_cleanup = getattr(mon, '_last_stale_order_cleanup', 0)
        result["daily"]["stale_order_cleanup"] = {
            "name": "Stale Order Cleanup",
            "interval": "24h",
            "last_run": _ts_iso(last_stale_cleanup),
            "age": _age_str(last_stale_cleanup),
        }
        
        last_time_exit = getattr(mon, '_last_time_based_exit_check', 0)
        result["daily"]["time_based_exits"] = {
            "name": "Time-Based Exit Check",
            "interval": "24h",
            "last_run": _ts_iso(last_time_exit),
            "age": _age_str(last_time_exit),
        }
        
        # === SYSTEM ===
        
        # FMP and FRED API status
        try:
            # FMP
            fmp_status = {"name": "FMP (Financial Modeling Prep)", "status": "unknown", "plan": "Starter (300/min)"}
            try:
                from src.data.fundamental_data_provider import get_fundamental_data_provider
                fdp = get_fundamental_data_provider()
                
                if not fdp:
                    # Fallback: show configured status from config_loader
                    from src.core.config_loader import load_config as _lc
                    _cfg = _lc()
                    fmp_key = _cfg.get('data_sources', {}).get('financial_modeling_prep', {}).get('api_key', '')
                    rate_limit = _cfg.get('data_sources', {}).get('financial_modeling_prep', {}).get('rate_limit', 300)
                    if fmp_key and fmp_key != 'REPLACE_VIA_SECRETS_MANAGER':
                        fmp_status.update({
                            "status": "configured",
                            "calls_today": 0,
                            "max_calls": rate_limit,
                            "usage_percent": 0,
                            "remaining": rate_limit,
                            "cache_size": 0,
                            "note": "Provider initializes on first signal generation cycle",
                        })
                    else:
                        fmp_status["status"] = "no_api_key"
                
                if fdp:
                    usage = fdp.get_api_usage()
                    fmp_usage = usage.get('fmp', {})
                    fmp_status.update({
                        "status": "circuit_breaker" if fmp_usage.get('circuit_breaker_active') else "healthy",
                        "calls_today": fmp_usage.get('calls_made', 0),       # calls in last 60s window
                        "max_calls": fmp_usage.get('max_calls', 300),
                        "usage_percent": round(fmp_usage.get('usage_percent', 0), 1),
                        "remaining": fmp_usage.get('calls_remaining', 0),
                        "cache_size": usage.get('cache_size', 0),             # total symbols in DB
                        "cache_fresh_7d": usage.get('cache_fresh_7d', 0),    # fresh within 7d
                        "cache_fresh_24h": usage.get('cache_fresh_24h', 0),  # fresh within 24h
                    })
                    if fmp_usage.get('circuit_breaker_reset_time'):
                        fmp_status["circuit_breaker_reset"] = fmp_usage['circuit_breaker_reset_time']
            except Exception as e:
                fmp_status["error"] = str(e)
            
            result["system"]["fmp"] = fmp_status
            
            # FRED
            fred_status = {"name": "FRED (Federal Reserve)", "status": "unknown"}
            try:
                import yaml
                from src.core.config_loader import load_config as _lc_fred
                _fred_cfg = _lc_fred()
                fred_config = _fred_cfg.get('data_sources', {}).get('fred', {})
                fred_enabled = fred_config.get('enabled', False)
                fred_status["enabled"] = fred_enabled
                fred_status["status"] = "configured" if fred_enabled else "disabled"
                if fred_enabled and fred_config.get('api_key') and fred_config['api_key'] != 'REPLACE_VIA_SECRETS_MANAGER':
                    fred_status["api_key_set"] = True

                # Get FRED health from market analyzer via singleton
                try:
                    from src.data.market_data_manager import get_market_data_manager
                    _mdm = get_market_data_manager()
                    if _mdm and hasattr(_mdm, 'market_analyzer'):
                        ma = _mdm.market_analyzer
                    else:
                        from src.core.trading_scheduler import get_trading_scheduler
                        sched = get_trading_scheduler()
                        ma = None
                        if sched and hasattr(sched, '_strategy_engine') and sched._strategy_engine:
                            ma = getattr(sched._strategy_engine, 'market_analyzer', None)
                    if ma:
                        fred_status["status"] = "healthy" if getattr(ma, 'fred_enabled', False) else "disabled"
                        last_context = getattr(ma, '_last_market_context_time', None)
                        if last_context:
                            fred_status["last_fetch"] = _ts_iso(last_context)
                            fred_status["last_fetch_age"] = _age_str(last_context)
                except Exception:
                    pass
            except Exception as e:
                fred_status["error"] = str(e)
            
            result["system"]["fred"] = fred_status
        except Exception:
            pass
        
        # eToro status — derive from monitoring service health
        try:
            etoro_status = {"name": "eToro", "status": "unknown"}
            etoro_client = getattr(mon, 'etoro_client', None)
            if etoro_client:
                etoro_status["status"] = "healthy"
                # Get rate limit info if available
                rate_info = getattr(etoro_client, '_rate_limit_remaining', None)
                if rate_info is not None:
                    etoro_status["rate_limit_remaining"] = rate_info
                avg_ms = getattr(etoro_client, '_avg_response_ms', None)
                if avg_ms is not None:
                    etoro_status["avg_response_ms"] = round(avg_ms, 0)
            else:
                etoro_status["status"] = "not_initialized"
            result["system"]["etoro"] = etoro_status
        except Exception:
            result["system"]["etoro"] = {"name": "eToro", "status": "unknown"}
        
        # Yahoo Finance status — derive from background price sync
        try:
            yahoo_status = {"name": "Yahoo Finance", "status": "unknown"}
            last_full_sync_ts = getattr(mon, '_last_price_sync', 0)
            if last_full_sync_ts and last_full_sync_ts > 0:
                yahoo_status["status"] = "healthy"
                yahoo_status["last_fetch"] = _ts_iso(last_full_sync_ts)
                yahoo_status["last_fetch_age"] = _age_str(last_full_sync_ts)
            else:
                yahoo_status["status"] = "idle"
            result["system"]["yahoo"] = yahoo_status
        except Exception:
            result["system"]["yahoo"] = {"name": "Yahoo Finance", "status": "unknown"}
        
        # Circuit breaker states
        try:
            cb_states = mon.get_circuit_breaker_states()
            result["system"]["circuit_breakers"] = cb_states
        except Exception:
            pass
        
        # Active strategy count
        try:
            from src.models.database import get_database
            from src.models.orm import StrategyORM, PositionORM
            from src.models.enums import StrategyStatus
            db = get_database()
            session = db.get_session()
            try:
                active = session.query(StrategyORM).filter(
                    StrategyORM.status.in_([StrategyStatus.DEMO, StrategyStatus.LIVE])
                ).count()
                backtested = session.query(StrategyORM).filter(
                    StrategyORM.status == StrategyStatus.BACKTESTED
                ).count()
                open_positions = session.query(PositionORM).filter(
                    PositionORM.closed_at.is_(None)
                ).count()
                result["system"]["strategies"] = {
                    "active_demo_live": active,
                    "backtested_scanning": backtested,
                    "open_positions": open_positions,
                }
            finally:
                session.close()
        except Exception:
            pass
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


# ============================================================================
# Data Quality Models (Req 19)
# ============================================================================

class DataQualityEntry(BaseModel):
    """Single symbol data quality entry."""
    symbol: str
    asset_class: str = "stock"
    quality_score: float = 0.0
    last_price_update: Optional[str] = None
    data_source: str = "yahoo"
    active_issues: int = 0
    staleness_seconds: float = 0.0
    # Fundamentals (FMP)
    fmp_score: Optional[float] = None        # 0-100, None = not applicable
    fmp_age_days: Optional[float] = None     # days since last FMP fetch
    fmp_has_data: bool = False
    # News sentiment (Marketaux)
    sentiment_score: Optional[float] = None  # -1.0 to +1.0, None = no data
    sentiment_age_hours: Optional[float] = None
    sentiment_label: Optional[str] = None    # bullish / bearish / neutral


class DataQualityResponse(BaseModel):
    """Data quality response — array of entries."""
    entries: List[DataQualityEntry] = []


@router.get("/quality", response_model=DataQualityResponse)
async def get_data_quality():
    """
    Get data quality scores for all tracked symbols.
    Includes price quality, FMP fundamentals coverage, and news sentiment.
    Fixes BTC/ETH score 0 by resolving BTCUSD/ETHUSD symbol mismatch.
    """
    from src.models.database import get_database
    from src.models.orm import DataQualityReportORM, FundamentalDataORM
    from sqlalchemy import text
    from src.data.fmp_cache_warmer import FMPCacheWarmer

    entries: List[DataQualityEntry] = []
    no_fundamentals = FMPCacheWarmer.SKIP_FUNDAMENTALS

    # Load symbol universe for asset class mapping
    asset_class_map: dict[str, str] = {}
    try:
        import yaml
        from pathlib import Path
        symbols_path = Path("config/symbols.yaml")
        if symbols_path.exists():
            with open(symbols_path) as f:
                sym_config = yaml.safe_load(f) or {}
            for ac, items in sym_config.items():
                if isinstance(items, list):
                    normalized = ac.rstrip("s") if ac.endswith("s") else ac
                    for item in items:
                        if isinstance(item, dict) and "symbol" in item:
                            asset_class_map[item["symbol"]] = normalized
    except Exception as e:
        logger.debug(f"Could not load symbols.yaml: {e}")

    try:
        db = get_database()
        session = db.get_session()
        try:
            now = datetime.now()

            # Quality reports (keyed by symbol, both BTC and BTCUSD forms)
            quality_reports: dict[str, DataQualityReportORM] = {}
            for r in session.query(DataQualityReportORM).all():
                existing = quality_reports.get(r.symbol)
                if not existing or (r.validated_at and existing.validated_at and r.validated_at > existing.validated_at):
                    quality_reports[r.symbol] = r

            # Latest price per symbol from historical_price_cache
            latest_prices: dict[str, datetime] = {}
            for row in session.execute(text(
                "SELECT symbol, MAX(fetched_at) FROM historical_price_cache GROUP BY symbol"
            )).fetchall():
                sym, ts = row[0], row[1]
                if ts:
                    latest_prices[sym] = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts))

            # FMP fundamentals: latest fetch per symbol
            fmp_data: dict[str, FundamentalDataORM] = {}
            for r in session.query(FundamentalDataORM).all():
                existing = fmp_data.get(r.symbol)
                if not existing or (r.fetched_at and existing.fetched_at and r.fetched_at > existing.fetched_at):
                    fmp_data[r.symbol] = r

            # News sentiment
            sentiment_data: dict[str, dict] = {}
            try:
                for row in session.execute(text(
                    "SELECT symbol, sentiment_score, fetched_at, ttl_hours FROM symbol_news_sentiment"
                )).fetchall():
                    sentiment_data[row[0]] = {"score": float(row[1]) if row[1] is not None else None,
                                              "fetched_at": row[2], "ttl_hours": row[3]}
            except Exception:
                pass

            all_symbols = set(quality_reports.keys()) | set(latest_prices.keys()) | set(asset_class_map.keys())

            for sym in sorted(all_symbols):
                # Resolve crypto symbol mismatch (BTC vs BTCUSD, ETH vs ETHUSD)
                alt = (sym + "USD") if (len(sym) <= 5 and not sym.endswith("USD") and not sym.endswith("D")) else sym.replace("USD", "")
                qr = quality_reports.get(sym) or quality_reports.get(alt)
                last_update = latest_prices.get(sym) or latest_prices.get(alt)

                # Price quality score
                quality_score = 50.0
                active_issues = 0
                if qr:
                    # Don't use score=0 from empty-data reports — use staleness fallback instead
                    quality_score = qr.quality_score if qr.quality_score > 0 else 50.0
                    active_issues = qr.issue_count
                if last_update:
                    staleness = (now - last_update).total_seconds()
                    if not qr:
                        quality_score = 95.0 if staleness < 3600 else 80.0 if staleness < 86400 else 60.0 if staleness < 604800 else 30.0

                staleness_seconds = max(0.0, (now - last_update).total_seconds()) if last_update else 0.0
                last_price_str = last_update.isoformat() if last_update else None

                # FMP fundamentals
                fmp_score = None
                fmp_age_days = None
                fmp_has_data = False
                if sym not in no_fundamentals:
                    fd = fmp_data.get(sym)
                    if fd and fd.fetched_at:
                        fmp_has_data = True
                        age_days = (now - fd.fetched_at).total_seconds() / 86400
                        fmp_age_days = round(age_days, 1)
                        fmp_score = round(max(0.0, 100.0 - (age_days / 30.0) * 100.0), 1)
                    else:
                        fmp_score = 0.0

                # News sentiment
                sentiment_score = None
                sentiment_age_hours = None
                sentiment_label = None
                sent = sentiment_data.get(sym)
                if sent and sent.get("score") is not None:
                    sentiment_score = round(sent["score"], 3)
                    fa = sent.get("fetched_at")
                    if fa:
                        if isinstance(fa, str):
                            try: fa = datetime.fromisoformat(fa)
                            except Exception: fa = None
                        if fa:
                            sentiment_age_hours = round((now - fa).total_seconds() / 3600, 1)
                    sentiment_label = "bullish" if sentiment_score > 0.15 else "bearish" if sentiment_score < -0.15 else "neutral"

                entries.append(DataQualityEntry(
                    symbol=sym,
                    asset_class=asset_class_map.get(sym, "stock"),
                    quality_score=round(quality_score, 1),
                    last_price_update=last_price_str,
                    data_source="yahoo",
                    active_issues=active_issues,
                    staleness_seconds=round(staleness_seconds, 1),
                    fmp_score=fmp_score,
                    fmp_age_days=fmp_age_days,
                    fmp_has_data=fmp_has_data,
                    sentiment_score=sentiment_score,
                    sentiment_age_hours=sentiment_age_hours,
                    sentiment_label=sentiment_label,
                ))
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error computing data quality: {e}")

    return DataQualityResponse(entries=entries)


# ============================================================================
# News Sentiment Cache (Marketaux)
# ============================================================================

_news_sentiment_thread: Optional[threading.Thread] = None
_news_sentiment_progress: dict = {
    "running": False, "current": 0, "total": 0,
    "fetched": 0, "failed": 0, "started_at": None,
    "completed_at": None, "elapsed_s": None, "error": None,
}


def _compute_sentiment_coverage() -> dict:
    """Compute Marketaux sentiment coverage stats from DB."""
    try:
        from src.models.database import get_database
        from sqlalchemy import text
        db = get_database()
        session = db.get_session()
        try:
            row = session.execute(text(
                "SELECT COUNT(*) as total, "
                "SUM(CASE WHEN fetched_at > NOW() - INTERVAL '24 hours' THEN 1 ELSE 0 END) as fresh_24h, "
                "SUM(CASE WHEN fetched_at > NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) as fresh_7d, "
                "SUM(CASE WHEN sentiment_score > 0.15 THEN 1 ELSE 0 END) as bullish_count, "
                "SUM(CASE WHEN sentiment_score < -0.15 THEN 1 ELSE 0 END) as bearish_count, "
                "SUM(CASE WHEN sentiment_score BETWEEN -0.15 AND 0.15 THEN 1 ELSE 0 END) as neutral_count, "
                "ROUND(AVG(sentiment_score)::numeric, 3) as avg_score "
                "FROM symbol_news_sentiment"
            )).fetchone()
            total_cached = row[0] if row else 0
            fresh_24h = row[1] if row else 0
            fresh_7d = row[2] if row else 0
            bullish_count = int(row[3] or 0)
            bearish_count = int(row[4] or 0)
            neutral_count = int(row[5] or 0)
            avg_score = float(row[6]) if row[6] is not None else 0.0
        finally:
            session.close()

        # Total applicable symbols (stocks only — ETFs/forex/crypto/indices don't have news)
        from src.data.news_sentiment_provider import get_news_sentiment_provider
        provider = get_news_sentiment_provider()
        requests_today = provider._requests_today if provider else 0
        requests_remaining = max(0, 95 - requests_today)

        # Estimate total applicable symbols
        from src.data.fmp_cache_warmer import FMPCacheWarmer
        from src.core.tradeable_instruments import get_tradeable_symbols
        from src.models.enums import TradingMode
        all_syms = get_tradeable_symbols(TradingMode.DEMO)
        applicable = [s for s in all_syms if s not in FMPCacheWarmer.SKIP_FUNDAMENTALS]
        total_applicable = len(applicable)

        return {
            "total_cached": total_cached,
            "fresh_24h": fresh_24h,
            "fresh_7d": fresh_7d,
            "total_applicable": total_applicable,
            "coverage_pct": round(total_cached / total_applicable * 100, 1) if total_applicable > 0 else 0.0,
            "requests_today": requests_today,
            "requests_remaining": requests_remaining,
            "score_distribution": {
                "bullish": bullish_count,
                "neutral": neutral_count,
                "bearish": bearish_count,
                "avg_score": avg_score,
            },
        }
    except Exception as e:
        logger.warning(f"Could not compute sentiment coverage: {e}")
        return {"total_cached": 0, "fresh_24h": 0, "fresh_7d": 0,
                "total_applicable": 0, "coverage_pct": 0.0,
                "requests_today": 0, "requests_remaining": 95,
                "score_distribution": {"bullish": 0, "neutral": 0, "bearish": 0, "avg_score": 0.0}}


@router.get("/news-sentiment/status")
async def get_news_sentiment_status():
    """Get Marketaux news sentiment cache status and coverage."""
    global _news_sentiment_thread, _news_sentiment_progress
    coverage = _compute_sentiment_coverage()
    thread_alive = _news_sentiment_thread is not None and _news_sentiment_thread.is_alive()
    is_running = thread_alive or _news_sentiment_progress.get("running", False)
    return {**_news_sentiment_progress, **coverage, "running": is_running}


@router.post("/news-sentiment/trigger", response_model=SyncTriggerResponse)
async def trigger_news_sentiment_sync():
    """Manually trigger news sentiment sync for all applicable symbols."""
    global _news_sentiment_thread, _news_sentiment_progress

    if _news_sentiment_thread and _news_sentiment_thread.is_alive():
        return SyncTriggerResponse(success=False, message="News sentiment sync already running")

    _news_sentiment_progress.update({
        "running": True, "current": 0, "total": 0,
        "fetched": 0, "failed": 0,
        "started_at": _time.time(), "completed_at": None,
        "elapsed_s": None, "error": None,
    })

    def _run():
        global _news_sentiment_progress
        try:
            from src.data.news_sentiment_provider import get_news_sentiment_provider
            from src.data.fmp_cache_warmer import FMPCacheWarmer
            from src.core.tradeable_instruments import get_tradeable_symbols
            from src.models.enums import TradingMode

            provider = get_news_sentiment_provider()
            if not provider:
                _news_sentiment_progress.update({"running": False, "error": "Provider not initialized"})
                return

            all_syms = get_tradeable_symbols(TradingMode.DEMO)
            applicable = [s for s in all_syms if s not in FMPCacheWarmer.SKIP_FUNDAMENTALS]
            to_fetch = [s for s in applicable if provider.needs_refresh(s)]

            _news_sentiment_progress["total"] = len(to_fetch)
            logger.info(f"Manual news sentiment sync: {len(to_fetch)} symbols to fetch")

            fetched = 0
            failed = 0
            for i, sym in enumerate(to_fetch):
                score = provider.fetch_and_store(sym)
                if score is not None:
                    fetched += 1
                else:
                    failed += 1
                    if not provider._check_rate_limit():
                        logger.info("News sentiment sync: rate limit reached, stopping")
                        break
                _news_sentiment_progress.update({
                    "current": i + 1,
                    "fetched": fetched,
                    "failed": failed,
                    "elapsed_s": round(_time.time() - _news_sentiment_progress["started_at"], 1),
                })

            elapsed = _time.time() - _news_sentiment_progress["started_at"]
            _news_sentiment_progress.update({
                "running": False, "current": fetched + failed,
                "fetched": fetched, "failed": failed,
                "completed_at": _time.time(), "elapsed_s": round(elapsed, 1),
            })
            logger.info(f"Manual news sentiment sync complete: {fetched} fetched, {failed} failed in {elapsed:.1f}s")

        except Exception as e:
            elapsed = _time.time() - (_news_sentiment_progress.get("started_at") or _time.time())
            _news_sentiment_progress.update({
                "running": False, "completed_at": _time.time(),
                "elapsed_s": round(elapsed, 1), "error": str(e)[:200],
            })
            logger.error(f"News sentiment sync failed: {e}", exc_info=True)

    _news_sentiment_thread = threading.Thread(target=_run, daemon=True, name="news-sentiment-sync")
    _news_sentiment_thread.start()
    return SyncTriggerResponse(success=True, message="News sentiment sync started")
