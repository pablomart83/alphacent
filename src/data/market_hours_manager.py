"""Market hours manager with exchange schedules and holiday handling."""

import logging
from datetime import datetime, time
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AssetClass(str, Enum):
    """Asset class types with different market hours."""
    STOCK = "STOCK"
    ETF = "ETF"
    CRYPTOCURRENCY = "CRYPTOCURRENCY"


class Exchange(str, Enum):
    """Supported exchanges."""
    NYSE = "NYSE"  # New York Stock Exchange
    NASDAQ = "NASDAQ"  # NASDAQ
    LSE = "LSE"  # London Stock Exchange
    CRYPTO = "CRYPTO"  # Cryptocurrency (24/7)


class MarketHours:
    """Market hours definition for an exchange."""

    def __init__(
        self,
        exchange: Exchange,
        open_time: time,
        close_time: time,
        timezone: str = "America/New_York",
        days_open: Optional[Set[int]] = None
    ):
        """Initialize market hours.
        
        Args:
            exchange: Exchange identifier
            open_time: Market open time
            close_time: Market close time
            timezone: Timezone for the exchange
            days_open: Set of weekday numbers (0=Monday, 6=Sunday) when market is open
        """
        self.exchange = exchange
        self.open_time = open_time
        self.close_time = close_time
        self.timezone = timezone
        # Default to Monday-Friday (0-4) if not specified
        self.days_open = days_open if days_open is not None else {0, 1, 2, 3, 4}


class MarketHoursManager:
    """Manages market hours for different asset classes and exchanges."""

    # US market holidays for 2024-2026 (simplified - would need annual updates)
    US_HOLIDAYS = {
        # 2024
        datetime(2024, 1, 1),   # New Year's Day
        datetime(2024, 1, 15),  # MLK Day
        datetime(2024, 2, 19),  # Presidents Day
        datetime(2024, 3, 29),  # Good Friday
        datetime(2024, 5, 27),  # Memorial Day
        datetime(2024, 6, 19),  # Juneteenth
        datetime(2024, 7, 4),   # Independence Day
        datetime(2024, 9, 2),   # Labor Day
        datetime(2024, 11, 28), # Thanksgiving
        datetime(2024, 12, 25), # Christmas
        # 2025
        datetime(2025, 1, 1),   # New Year's Day
        datetime(2025, 1, 20),  # MLK Day
        datetime(2025, 2, 17),  # Presidents Day
        datetime(2025, 4, 18),  # Good Friday
        datetime(2025, 5, 26),  # Memorial Day
        datetime(2025, 6, 19),  # Juneteenth
        datetime(2025, 7, 4),   # Independence Day
        datetime(2025, 9, 1),   # Labor Day
        datetime(2025, 11, 27), # Thanksgiving
        datetime(2025, 12, 25), # Christmas
        # 2026
        datetime(2026, 1, 1),   # New Year's Day
        datetime(2026, 1, 19),  # MLK Day
        datetime(2026, 2, 16),  # Presidents Day
        datetime(2026, 4, 3),   # Good Friday
        datetime(2026, 5, 25),  # Memorial Day
        datetime(2026, 6, 19),  # Juneteenth
        datetime(2026, 7, 3),   # Independence Day (observed)
        datetime(2026, 9, 7),   # Labor Day
        datetime(2026, 11, 26), # Thanksgiving
        datetime(2026, 12, 25), # Christmas
    }

    # Early close days (day before major holidays, typically 1pm ET close)
    US_EARLY_CLOSE = {
        datetime(2024, 7, 3),   # Day before Independence Day
        datetime(2024, 11, 29), # Day after Thanksgiving
        datetime(2024, 12, 24), # Christmas Eve
        datetime(2025, 7, 3),   # Day before Independence Day
        datetime(2025, 11, 28), # Day after Thanksgiving
        datetime(2025, 12, 24), # Christmas Eve
        datetime(2026, 11, 27), # Day after Thanksgiving
        datetime(2026, 12, 24), # Christmas Eve
    }

    def __init__(self):
        """Initialize market hours manager with exchange schedules."""
        self.market_hours: Dict[Exchange, MarketHours] = {
            # US Stock Exchanges (9:30 AM - 4:00 PM ET, Monday-Friday)
            Exchange.NYSE: MarketHours(
                exchange=Exchange.NYSE,
                open_time=time(9, 30),
                close_time=time(16, 0),
                timezone="America/New_York"
            ),
            Exchange.NASDAQ: MarketHours(
                exchange=Exchange.NASDAQ,
                open_time=time(9, 30),
                close_time=time(16, 0),
                timezone="America/New_York"
            ),
            # London Stock Exchange (8:00 AM - 4:30 PM GMT, Monday-Friday)
            Exchange.LSE: MarketHours(
                exchange=Exchange.LSE,
                open_time=time(8, 0),
                close_time=time(16, 30),
                timezone="Europe/London"
            ),
            # Cryptocurrency (24/7)
            Exchange.CRYPTO: MarketHours(
                exchange=Exchange.CRYPTO,
                open_time=time(0, 0),
                close_time=time(23, 59),
                timezone="UTC",
                days_open={0, 1, 2, 3, 4, 5, 6}  # All days
            ),
        }

        # Map asset classes to exchanges
        self.asset_class_exchange: Dict[AssetClass, Exchange] = {
            AssetClass.STOCK: Exchange.NYSE,
            AssetClass.ETF: Exchange.NYSE,
            AssetClass.CRYPTOCURRENCY: Exchange.CRYPTO,
        }

        logger.info("Initialized MarketHoursManager with exchange schedules")

    def is_market_open(
        self,
        asset_class: AssetClass,
        check_time: Optional[datetime] = None,
        symbol: Optional[str] = None
    ) -> bool:
        """Check if market is open for given asset class.
        
        Args:
            asset_class: Asset class to check (STOCK, ETF, CRYPTOCURRENCY)
            check_time: Time to check (defaults to now)
            symbol: Optional symbol for exchange-specific logic
            
        Returns:
            True if market is open
        """
        if check_time is None:
            check_time = datetime.now()

        # Cryptocurrencies are always open (24/7)
        if asset_class == AssetClass.CRYPTOCURRENCY:
            logger.debug(f"Cryptocurrency market is always open")
            return True

        # Get exchange for asset class
        exchange = self.asset_class_exchange.get(asset_class)
        if exchange is None:
            logger.warning(f"Unknown asset class: {asset_class}, assuming closed")
            return False

        # Get market hours for exchange
        hours = self.market_hours.get(exchange)
        if hours is None:
            logger.warning(f"No market hours defined for {exchange}, assuming closed")
            return False

        # Check if it's a weekday the market is open
        weekday = check_time.weekday()
        if weekday not in hours.days_open:
            logger.debug(f"{exchange.value} closed on weekday {weekday}")
            return False

        # Check if it's a holiday (for US exchanges)
        if exchange in [Exchange.NYSE, Exchange.NASDAQ]:
            check_date = check_time.date()
            if datetime(check_date.year, check_date.month, check_date.day) in self.US_HOLIDAYS:
                logger.debug(f"{exchange.value} closed for holiday on {check_date}")
                return False

            # Check for early close
            if datetime(check_date.year, check_date.month, check_date.day) in self.US_EARLY_CLOSE:
                # Early close at 1:00 PM ET
                early_close_time = time(13, 0)
                current_time = check_time.time()
                
                if current_time >= early_close_time:
                    logger.debug(f"{exchange.value} closed for early close at {check_time}")
                    return False
                # Still check if before open time
                if current_time < hours.open_time:
                    logger.debug(f"{exchange.value} not yet open at {check_time}")
                    return False
                
                logger.debug(f"{exchange.value} open (early close day) at {check_time}")
                return True

        # Check if current time is within market hours
        current_time = check_time.time()
        is_open = hours.open_time <= current_time <= hours.close_time

        if is_open:
            logger.debug(f"{exchange.value} open at {check_time}")
        else:
            logger.debug(f"{exchange.value} closed at {check_time} (hours: {hours.open_time}-{hours.close_time})")

        return is_open

    def get_next_open_time(
        self,
        asset_class: AssetClass,
        from_time: Optional[datetime] = None
    ) -> datetime:
        """Get next market open time for asset class.
        
        Args:
            asset_class: Asset class to check
            from_time: Starting time (defaults to now)
            
        Returns:
            Next market open datetime
        """
        if from_time is None:
            from_time = datetime.now()

        # Cryptocurrencies are always open
        if asset_class == AssetClass.CRYPTOCURRENCY:
            return from_time

        # Get exchange for asset class
        exchange = self.asset_class_exchange.get(asset_class)
        if exchange is None:
            logger.warning(f"Unknown asset class: {asset_class}")
            return from_time

        # Get market hours
        hours = self.market_hours.get(exchange)
        if hours is None:
            logger.warning(f"No market hours defined for {exchange}")
            return from_time

        # Start checking from the next minute
        check_time = from_time
        max_days_ahead = 14  # Don't check more than 2 weeks ahead

        for _ in range(max_days_ahead * 24 * 60):  # Check every minute for up to 2 weeks
            if self.is_market_open(asset_class, check_time):
                logger.info(f"Next open time for {asset_class.value}: {check_time}")
                return check_time
            
            # Move to next minute
            from datetime import timedelta
            check_time += timedelta(minutes=1)

            # If we've moved to a new day and it's past midnight, jump to market open time
            if check_time.time() < time(1, 0) and check_time.weekday() in hours.days_open:
                check_time = check_time.replace(
                    hour=hours.open_time.hour,
                    minute=hours.open_time.minute,
                    second=0,
                    microsecond=0
                )

        # Fallback: return original time if we can't find next open
        logger.warning(f"Could not find next open time for {asset_class.value} within {max_days_ahead} days")
        return from_time

    def is_holiday(self, check_date: datetime, exchange: Exchange = Exchange.NYSE) -> bool:
        """Check if given date is a holiday for the exchange.
        
        Args:
            check_date: Date to check
            exchange: Exchange to check (defaults to NYSE)
            
        Returns:
            True if it's a holiday
        """
        # Only US exchanges have holiday tracking
        if exchange not in [Exchange.NYSE, Exchange.NASDAQ]:
            return False

        date_only = datetime(check_date.year, check_date.month, check_date.day)
        is_holiday = date_only in self.US_HOLIDAYS

        if is_holiday:
            logger.debug(f"{check_date.date()} is a holiday for {exchange.value}")

        return is_holiday

    def is_early_close(self, check_date: datetime, exchange: Exchange = Exchange.NYSE) -> bool:
        """Check if given date is an early close day for the exchange.
        
        Args:
            check_date: Date to check
            exchange: Exchange to check (defaults to NYSE)
            
        Returns:
            True if it's an early close day
        """
        # Only US exchanges have early close tracking
        if exchange not in [Exchange.NYSE, Exchange.NASDAQ]:
            return False

        date_only = datetime(check_date.year, check_date.month, check_date.day)
        is_early = date_only in self.US_EARLY_CLOSE

        if is_early:
            logger.debug(f"{check_date.date()} is an early close day for {exchange.value}")

        return is_early

    def get_market_hours(self, asset_class: AssetClass) -> Optional[MarketHours]:
        """Get market hours definition for asset class.
        
        Args:
            asset_class: Asset class to query
            
        Returns:
            MarketHours object or None if not found
        """
        exchange = self.asset_class_exchange.get(asset_class)
        if exchange is None:
            return None

        return self.market_hours.get(exchange)

    def get_exchange_for_symbol(self, symbol: str) -> Exchange:
        """Determine exchange for a given symbol.
        
        This is a simplified implementation. In production, you'd want
        a more sophisticated symbol-to-exchange mapping.
        
        Args:
            symbol: Instrument symbol
            
        Returns:
            Exchange for the symbol
        """
        # Cryptocurrency detection (simplified)
        crypto_indicators = ["BTC", "ETH", "USDT", "XRP", "ADA", "DOGE", "SOL", "-USD"]
        if any(indicator in symbol.upper() for indicator in crypto_indicators):
            return Exchange.CRYPTO

        # Default to NYSE for stocks/ETFs
        return Exchange.NYSE
