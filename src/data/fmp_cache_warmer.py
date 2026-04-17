"""
FMP Cache Warmer - Pre-fetches fundamental data for all tradeable symbols.

Database-first strategy: checks DB cache age per symbol BEFORE calling API.
Only fetches from API if DB data is older than configured TTL.
Stores last warm timestamp in DB (not in-memory) so it survives restarts.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class FMPCacheWarmer:
    """Pre-fetches and caches FMP data for all tradeable symbols.
    
    Database-first approach:
    - Checks DB cache age per symbol before calling API
    - Only fetches from API if DB data is stale (older than TTL)
    - Logs cache hits vs API fetches for monitoring
    """

    # Symbols that don't have traditional fundamentals
    SKIP_FUNDAMENTALS = {
        'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'EURGBP',  # Forex
        'SPX500', 'NSDQ100', 'DJ30', 'UK100', 'GER40',  # Indices
        'GOLD', 'SILVER', 'OIL', 'COPPER', 'NATGAS', 'PLATINUM', 'ALUMINUM', 'ZINC',  # Commodities
        'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOT', 'LINK',  # Crypto
        'NEAR', 'LTC', 'BCH',
        'SPY', 'QQQ', 'IWM', 'DIA', 'GLD', 'SLV', 'VTI', 'VOO',  # Broad ETFs
        'TLT', 'HYG', 'UNG', 'USO',  # Bond/Commodity ETFs
        'XLE', 'XLF', 'XLK', 'XLU', 'XLV', 'XLI', 'XLP', 'XLY',  # Sector ETFs
        'XHB', 'XBI', 'ARKK', 'ITA', 'FXI',  # Thematic ETFs
    }

    def __init__(self, config: Dict):
        """Initialize with config containing FMP credentials."""
        self.config = config
        self._provider = None

        # Default TTLs (can be overridden by config)
        fmp_config = config.get('data_sources', {}).get('financial_modeling_prep', {})
        earnings_config = fmp_config.get('earnings_aware_cache', {})
        self._fundamentals_ttl = earnings_config.get('default_ttl', 604800)  # 7 days default
        self._earnings_ttl = earnings_config.get('earnings_calendar_ttl', 604800)  # 7 days

    def _get_provider(self):
        """Get a dedicated FundamentalDataProvider for cache warming.

        Uses its own instance (not the singleton) so the warmer has its own
        rate limiter and doesn't compete with signal generation for tokens.
        """
        if self._provider is None:
            from src.data.fundamental_data_provider import FundamentalDataProvider
            # Deliberately NOT using get_fundamental_data_provider() singleton here.
            # The warmer runs as a background task and should have its own rate limiter
            # so it doesn't starve signal generation of API tokens.
            self._provider = FundamentalDataProvider(self.config)
        return self._provider

    def _get_db_cache_age(self, symbol: str) -> Optional[float]:
        """Check how old the DB cache is for a symbol.
        
        Returns:
            Age in seconds, or None if no cached data exists.
        """
        from src.models.database import get_database
        from src.models.orm import FundamentalDataORM

        db = get_database()
        session = db.get_session()
        try:
            record = session.query(FundamentalDataORM).filter_by(symbol=symbol).first()
            if record and record.fetched_at:
                age = (datetime.now() - record.fetched_at).total_seconds()
                return age
            return None
        except Exception as e:
            logger.debug(f"Error checking DB cache age for {symbol}: {e}")
            return None
        finally:
            session.close()

    def warm_all_symbols(self, progress_callback=None, force_ttl_hours: int = None) -> Dict:
        """
        Fetch fundamental data for all tradeable symbols.

        Database-first: checks DB cache age per symbol, only calls API if stale.

        Args:
            progress_callback: Optional callable(current, total, stats_dict) called every 10 symbols
            force_ttl_hours: If set, override the default TTL with this value in hours.
                             Use 24 for manual refresh (re-fetch anything older than 24h).
                             Use None to use the configured default (7 days).

        Returns:
            Dict with warming statistics
        """
        from src.core.tradeable_instruments import get_tradeable_symbols
        from src.models.enums import TradingMode

        symbols = get_tradeable_symbols(TradingMode.DEMO)
        provider = self._get_provider()

        stock_symbols = [s for s in symbols if s not in self.SKIP_FUNDAMENTALS]
        skipped = len(symbols) - len(stock_symbols)

        # Override TTL if force_ttl_hours is set
        effective_ttl = (force_ttl_hours * 3600) if force_ttl_hours else self._fundamentals_ttl

        stats = {
            'total_symbols': len(stock_symbols),
            'fundamentals_fetched': 0,
            'fundamentals_cached': 0,
            'fundamentals_failed': 0,
            'earnings_fetched': 0,
            'earnings_cached': 0,
            'earnings_failed': 0,
            'started_at': datetime.now().isoformat(),
            'errors': []
        }

        logger.info(f"Starting FMP cache warming for {len(stock_symbols)} stock symbols ({skipped} non-stock skipped)")
        start_time = time.time()

        # Separate symbols into cached (skip) and stale (need API fetch)
        # so we can parallelize only the API-bound ones
        cached_symbols = []
        stale_symbols = []
        for symbol in stock_symbols:
            cache_age = self._get_db_cache_age(symbol)
            if cache_age is not None and cache_age < effective_ttl:
                cached_symbols.append(symbol)
                stats['fundamentals_cached'] += 1
            else:
                stale_symbols.append((symbol, cache_age))

        logger.info(
            f"Cache check: {len(cached_symbols)} fresh (skipping), "
            f"{len(stale_symbols)} stale/missing (fetching from API)"
        )

        # 8 concurrent workers — the token bucket in RateLimiter enforces 5 calls/sec
        # (300/min) across all workers, so they can't burst past the limit.
        # Each worker blocks on wait_for_token() when the bucket is empty.
        # Expected throughput: ~5 symbols/sec = ~46s for 232 symbols (full 300/min used).
        import threading
        _stats_lock = threading.Lock()
        completed_count = [0]

        def _warm_one_symbol(symbol, cache_age):
            result = {'fetched': False, 'earnings': False, 'error': None}
            try:
                data = provider.get_fundamental_data(symbol, use_cache=False)
                result['fetched'] = data is not None
            except Exception as e:
                result['error'] = str(e)

            try:
                earnings = provider.get_earnings_calendar(symbol)
                result['earnings'] = earnings is not None
            except Exception:
                pass

            try:
                if cache_age is None or cache_age >= self._fundamentals_ttl:
                    provider.get_historical_fundamentals(symbol, quarters=8)
            except Exception:
                pass

            with _stats_lock:
                if result['fetched']:
                    stats['fundamentals_fetched'] += 1
                elif result['error']:
                    stats['fundamentals_failed'] += 1
                    stats['errors'].append(f"{symbol}: {result['error']}")
                else:
                    stats['fundamentals_failed'] += 1
                if result['earnings']:
                    stats['earnings_fetched'] += 1

                completed_count[0] += 1
                total_done = completed_count[0] + len(cached_symbols)

                if completed_count[0] % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = completed_count[0] / elapsed if elapsed > 0 else 0
                    usage = provider.fmp_rate_limiter.get_usage()
                    logger.info(
                        f"Cache warming: {total_done}/{len(stock_symbols)} symbols "
                        f"({stats['fundamentals_fetched']} fetched, {stats['fundamentals_failed']} failed) "
                        f"in {elapsed:.1f}s @ {rate:.1f} sym/s | "
                        f"FMP: {usage['calls_made']}/{usage['max_calls']} calls "
                        f"({usage['tokens_available']:.0f} tokens)"
                    )

                if progress_callback and completed_count[0] % 5 == 0:
                    try:
                        progress_callback(total_done, len(stock_symbols), stats)
                    except Exception:
                        pass

        if stale_symbols:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(_warm_one_symbol, sym, ca) for sym, ca in stale_symbols]
                for f in as_completed(futures):
                    try:
                        f.result()
                    except Exception as e:
                        logger.debug(f"Cache warming thread error: {e}")

        elapsed = time.time() - start_time
        stats['elapsed_seconds'] = elapsed
        stats['completed_at'] = datetime.now().isoformat()

        # Store last warm timestamp in DB
        self._save_last_warm_timestamp()

        logger.info(
            f"FMP cache warming complete: {stats['fundamentals_fetched']} API fetched, "
            f"{stats['fundamentals_cached']} from DB cache, "
            f"{stats['fundamentals_failed']} failed, "
            f"{stats['earnings_fetched']} earnings "
            f"in {elapsed:.1f}s"
        )

        return stats

    def _save_last_warm_timestamp(self) -> None:
        """Save the last cache warm timestamp to DB (survives restarts)."""
        from src.models.database import get_database
        from src.models.orm import CacheMetadataORM

        db = get_database()
        session = db.get_session()
        try:
            key = "fmp_last_cache_warm"
            record = session.query(CacheMetadataORM).filter_by(key=key).first()
            now = datetime.now()
            if record:
                record.value = now.isoformat()
                record.updated_at = now
            else:
                record = CacheMetadataORM(key=key, value=now.isoformat(), updated_at=now)
                session.add(record)
            session.commit()
            logger.debug(f"Saved last cache warm timestamp to DB: {now.isoformat()}")
        except Exception as e:
            logger.warning(f"Failed to save last warm timestamp to DB: {e}")
            session.rollback()
        finally:
            session.close()

    @staticmethod
    def get_last_warm_timestamp() -> Optional[datetime]:
        """Get the last cache warm timestamp from DB.
        
        Returns:
            datetime of last warm, or None if never warmed.
        """
        from src.models.database import get_database
        from src.models.orm import CacheMetadataORM

        db = get_database()
        session = db.get_session()
        try:
            record = session.query(CacheMetadataORM).filter_by(key="fmp_last_cache_warm").first()
            if record and record.value:
                return datetime.fromisoformat(record.value)
            return None
        except Exception as e:
            logger.debug(f"Error reading last warm timestamp: {e}")
            return None
        finally:
            session.close()

    _sector_cache: Dict[str, str] = {}

    def get_sector_classifications(self) -> Dict[str, str]:
        """Fetch sector/industry for all symbols using FMP profile endpoint.
        
        Results are cached in-memory so repeated calls don't re-fetch.
        """
        if FMPCacheWarmer._sector_cache:
            logger.debug(f"Returning cached sector classifications for {len(FMPCacheWarmer._sector_cache)} symbols")
            return FMPCacheWarmer._sector_cache

        from src.core.tradeable_instruments import get_tradeable_symbols
        from src.models.enums import TradingMode

        symbols = get_tradeable_symbols(TradingMode.DEMO)
        provider = self._get_provider()
        sectors = {}

        for symbol in symbols:
            try:
                profile = provider._fmp_request("/profile", symbol=symbol)
                if profile and isinstance(profile, list) and len(profile) > 0:
                    sectors[symbol] = profile[0].get('sector', 'Unknown')
            except Exception as e:
                logger.debug(f"Could not get sector for {symbol}: {e}")

        logger.info(f"Fetched sector classifications for {len(sectors)}/{len(symbols)} symbols")
        FMPCacheWarmer._sector_cache = sectors
        return sectors

    def get_financial_ratios_batch(self) -> Dict[str, Dict]:
        """Fetch key financial ratios for all symbols."""
        from src.core.tradeable_instruments import get_tradeable_symbols
        from src.models.enums import TradingMode

        symbols = get_tradeable_symbols(TradingMode.DEMO)
        provider = self._get_provider()
        ratios = {}

        for symbol in symbols:
            try:
                data = provider.get_fundamental_data(symbol)
                if data:
                    ratios[symbol] = {
                        'pe_ratio': data.pe_ratio,
                        'roe': data.roe,
                        'debt_equity': data.debt_to_equity,
                        'revenue_growth': data.revenue_growth,
                        'market_cap': data.market_cap,
                    }
            except Exception as e:
                logger.debug(f"Could not get ratios for {symbol}: {e}")

        logger.info(f"Fetched financial ratios for {len(ratios)}/{len(symbols)} symbols")
        return ratios


def run_cache_warming():
    """Standalone function to run cache warming (can be called from scheduler or CLI)."""
    import yaml
    from pathlib import Path

    config_path = Path("config/autonomous_trading.yaml")
    if not config_path.exists():
        logger.error("Config file not found")
        return None

    with open(config_path) as f:
        config = yaml.safe_load(f)

    warmer = FMPCacheWarmer(config)
    return warmer.warm_all_symbols()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    stats = run_cache_warming()
    if stats:
        print(f"\nCache warming complete:")
        print(f"  API fetched: {stats['fundamentals_fetched']}/{stats['total_symbols']}")
        print(f"  From DB cache: {stats['fundamentals_cached']}")
        print(f"  Earnings: {stats['earnings_fetched']}")
        print(f"  Failed: {stats['fundamentals_failed']}")
        print(f"  Time: {stats['elapsed_seconds']:.1f}s")
