"""Example usage of MarketDataManager and MarketHoursManager."""

import logging
from datetime import datetime, timedelta

from src.api.etoro_client import EToroAPIClient
from src.data import MarketDataManager, MarketHoursManager
from src.data.market_hours_manager import AssetClass
from src.models import TradingMode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Demonstrate market data and market hours functionality."""
    
    # Initialize components
    logger.info("Initializing AlphaCent market data components...")
    
    # Create eToro client (demo mode)
    etoro_client = EToroAPIClient(
        public_key="demo_public_key",
        user_key="demo_user_key",
        mode=TradingMode.DEMO
    )
    
    # Create market data manager with 60-second cache
    market_data_manager = MarketDataManager(etoro_client, cache_ttl=60)
    
    # Create market hours manager
    market_hours_manager = MarketHoursManager()
    
    # Example 1: Check if markets are open
    logger.info("\n=== Example 1: Market Hours ===")
    
    symbols = {
        "AAPL": AssetClass.STOCK,
        "SPY": AssetClass.ETF,
        "BTC-USD": AssetClass.CRYPTOCURRENCY
    }
    
    for symbol, asset_class in symbols.items():
        is_open = market_hours_manager.is_market_open(asset_class)
        status = "OPEN" if is_open else "CLOSED"
        logger.info(f"{symbol} ({asset_class.value}) market is {status}")
        
        if not is_open:
            next_open = market_hours_manager.get_next_open_time(asset_class)
            logger.info(f"  Next open time: {next_open}")
    
    # Example 2: Fetch real-time quotes (with fallback)
    logger.info("\n=== Example 2: Real-Time Quotes ===")
    
    try:
        # This will try eToro first, then fall back to Yahoo Finance
        quote = market_data_manager.get_quote("AAPL")
        logger.info(f"AAPL Quote:")
        logger.info(f"  Price: ${quote.close:.2f}")
        logger.info(f"  High: ${quote.high:.2f}")
        logger.info(f"  Low: ${quote.low:.2f}")
        logger.info(f"  Volume: {quote.volume:,.0f}")
        logger.info(f"  Source: {quote.source.value}")
        logger.info(f"  Timestamp: {quote.timestamp}")
    except Exception as e:
        logger.error(f"Failed to fetch quote: {e}")
    
    # Example 3: Fetch historical data
    logger.info("\n=== Example 3: Historical Data ===")
    
    try:
        end = datetime.now()
        start = end - timedelta(days=7)
        
        historical_data = market_data_manager.get_historical_data(
            "AAPL",
            start,
            end,
            interval="1d"
        )
        
        logger.info(f"Retrieved {len(historical_data)} days of historical data for AAPL")
        
        if historical_data:
            latest = historical_data[-1]
            logger.info(f"Latest data point:")
            logger.info(f"  Date: {latest.timestamp.date()}")
            logger.info(f"  Close: ${latest.close:.2f}")
            logger.info(f"  Source: {latest.source.value}")
    except Exception as e:
        logger.error(f"Failed to fetch historical data: {e}")
    
    # Example 4: Cache demonstration
    logger.info("\n=== Example 4: Cache Performance ===")
    
    try:
        import time
        
        # First call - will fetch from API
        start_time = time.time()
        quote1 = market_data_manager.get_quote("GOOGL")
        time1 = time.time() - start_time
        logger.info(f"First call (API): {time1:.3f}s")
        
        # Second call - will use cache
        start_time = time.time()
        quote2 = market_data_manager.get_quote("GOOGL")
        time2 = time.time() - start_time
        logger.info(f"Second call (cache): {time2:.3f}s")
        logger.info(f"Cache speedup: {time1/time2:.1f}x faster")
        
        # Verify same data
        assert quote1.close == quote2.close
        logger.info("Cache data matches API data ✓")
    except Exception as e:
        logger.error(f"Cache demonstration failed: {e}")
    
    # Example 5: Market hours edge cases
    logger.info("\n=== Example 5: Market Hours Edge Cases ===")
    
    # Check holiday
    new_years = datetime(2025, 1, 1)
    is_holiday = market_hours_manager.is_holiday(new_years)
    logger.info(f"New Year's Day 2025 is a holiday: {is_holiday}")
    
    # Check early close
    black_friday = datetime(2024, 11, 29)
    is_early = market_hours_manager.is_early_close(black_friday)
    logger.info(f"Day after Thanksgiving 2024 is early close: {is_early}")
    
    # Cryptocurrency is always open
    weekend = datetime(2024, 1, 20, 3, 0)  # Saturday 3am
    crypto_open = market_hours_manager.is_market_open(AssetClass.CRYPTOCURRENCY, weekend)
    logger.info(f"Crypto market open on Saturday 3am: {crypto_open}")
    
    logger.info("\n=== Examples Complete ===")


if __name__ == "__main__":
    main()
