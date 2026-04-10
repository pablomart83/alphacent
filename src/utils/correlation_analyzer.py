"""Symbol correlation analysis for preventing redundant positions."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class CorrelationAnalyzer:
    """Analyzes price correlations between trading symbols."""
    
    def __init__(self, market_data_manager):
        """
        Initialize CorrelationAnalyzer.
        
        Args:
            market_data_manager: MarketDataManager instance for fetching historical data
        """
        self.market_data = market_data_manager
        self._correlation_cache = {}  # (symbol1, symbol2) -> (correlation, timestamp)
        self._failed_symbols = {}  # symbol -> timestamp (cache failed lookups to avoid retries)
        self._cache_ttl_days = 7  # Refresh weekly
        logger.info("CorrelationAnalyzer initialized")
    
    def get_correlation(self, symbol1: str, symbol2: str, lookback_days: int = 90) -> Optional[float]:
        """
        Get correlation coefficient between two symbols.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            lookback_days: Number of days to look back for correlation calculation
        
        Returns:
            Correlation coefficient (-1.0 to 1.0) or None if insufficient data
        """
        # Normalize symbol order for cache key
        cache_key = tuple(sorted([symbol1, symbol2]))
        
        # Check if either symbol has recently failed (avoid repeated lookups)
        for sym in [symbol1, symbol2]:
            if sym in self._failed_symbols:
                fail_time = self._failed_symbols[sym]
                age_hours = (datetime.now() - fail_time).total_seconds() / 3600
                if age_hours < 24:  # Cache failures for 24 hours
                    logger.debug(f"Skipping correlation for {symbol1} vs {symbol2}: {sym} failed recently")
                    return None
                else:
                    del self._failed_symbols[sym]  # Retry after 24h
        
        # Check cache
        if cache_key in self._correlation_cache:
            correlation, timestamp = self._correlation_cache[cache_key]
            age_days = (datetime.now() - timestamp).days
            
            if age_days < self._cache_ttl_days:
                logger.debug(f"Using cached correlation for {symbol1} vs {symbol2}: {correlation:.3f}")
                return correlation
        
        # Calculate correlation
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)
            
            # Fetch price data
            data1 = self.market_data.get_historical_data(symbol1, start_date, end_date, interval='1d')
            data2 = self.market_data.get_historical_data(symbol2, start_date, end_date, interval='1d')
            
            if data1 is None or data2 is None or len(data1) < 20 or len(data2) < 20:
                logger.warning(f"Insufficient data for correlation: {symbol1} vs {symbol2}")
                return None
            
            # Convert to DataFrames — handle both dict and object data
            def _to_df(data, symbol):
                if not data:
                    return None
                # If data is a list of objects with attributes (not dicts)
                if hasattr(data[0], 'timestamp') and hasattr(data[0], 'close'):
                    return pd.DataFrame([{
                        'date': d.timestamp,
                        'close': d.close
                    } for d in data])
                # If data is already dicts
                df = pd.DataFrame(data)
                # Normalize column name: timestamp -> date
                if 'timestamp' in df.columns and 'date' not in df.columns:
                    df = df.rename(columns={'timestamp': 'date'})
                return df
            
            df1 = _to_df(data1, symbol1)
            df2 = _to_df(data2, symbol2)
            
            if df1 is None or df2 is None:
                return None
            
            # Ensure we have date and close columns
            if 'date' not in df1.columns or 'close' not in df1.columns:
                logger.warning(f"Missing required columns in data for {symbol1}: {list(df1.columns)}")
                self._failed_symbols[symbol1] = datetime.now()
                return None
            if 'date' not in df2.columns or 'close' not in df2.columns:
                logger.warning(f"Missing required columns in data for {symbol2}: {list(df2.columns)}")
                self._failed_symbols[symbol2] = datetime.now()
                return None
            
            df1['date'] = pd.to_datetime(df1['date'])
            df2['date'] = pd.to_datetime(df2['date'])
            
            df1 = df1.set_index('date')
            df2 = df2.set_index('date')
            
            # Remove duplicate timestamps (DB cache can produce dupes)
            if df1.index.duplicated().any():
                df1 = df1[~df1.index.duplicated(keep='last')]
            if df2.index.duplicated().any():
                df2 = df2[~df2.index.duplicated(keep='last')]
            
            # Use closing prices
            prices = pd.DataFrame({
                symbol1: df1['close'],
                symbol2: df2['close']
            }).dropna()
            
            if len(prices) < 20:
                logger.warning(f"Insufficient aligned data for correlation: {symbol1} vs {symbol2} ({len(prices)} days)")
                return None
            
            # Calculate daily returns
            returns = prices.pct_change().dropna()
            
            # Calculate correlation
            correlation = returns[symbol1].corr(returns[symbol2])
            
            # Cache result
            self._correlation_cache[cache_key] = (correlation, datetime.now())
            
            logger.info(f"Calculated correlation {symbol1} vs {symbol2}: {correlation:.3f} ({len(returns)} days)")
            return correlation
            
        except Exception as e:
            logger.error(f"Failed to calculate correlation {symbol1} vs {symbol2}: {e}")
            # Cache the failure to avoid repeated lookups
            for sym in [symbol1, symbol2]:
                if 'No historical data' in str(e) or 'delisted' in str(e).lower() or sym in str(e):
                    self._failed_symbols[sym] = datetime.now()
                    logger.debug(f"Cached failed symbol: {sym}")
            return None
    
    def are_correlated(self, symbol1: str, symbol2: str, threshold: float = 0.8) -> bool:
        """
        Check if two symbols are highly correlated.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            threshold: Correlation threshold (default 0.8)
        
        Returns:
            True if symbols are correlated above threshold, False otherwise
        """
        correlation = self.get_correlation(symbol1, symbol2)
        
        if correlation is None:
            # If we can't calculate correlation, assume not correlated (fail open)
            logger.debug(f"Cannot determine correlation for {symbol1} vs {symbol2}, assuming not correlated")
            return False
        
        is_correlated = abs(correlation) >= threshold
        if is_correlated:
            logger.info(f"Symbols {symbol1} and {symbol2} are correlated: {correlation:.3f} >= {threshold:.3f}")
        
        return is_correlated
    
    def find_correlated_symbols(
        self, 
        symbol: str, 
        symbol_list: List[str], 
        threshold: float = 0.8
    ) -> List[Tuple[str, float]]:
        """
        Find all symbols in list that are correlated with given symbol.
        
        Args:
            symbol: Symbol to check correlations for
            symbol_list: List of symbols to check against
            threshold: Correlation threshold (default 0.8)
        
        Returns:
            List of tuples (symbol, correlation) for correlated symbols
        """
        correlated = []
        
        for other_symbol in symbol_list:
            if other_symbol == symbol:
                continue
            
            correlation = self.get_correlation(symbol, other_symbol)
            
            if correlation is not None and abs(correlation) >= threshold:
                correlated.append((other_symbol, correlation))
        
        if correlated:
            logger.info(
                f"Found {len(correlated)} correlated symbols for {symbol}: "
                f"{', '.join(f'{s}({c:.2f})' for s, c in correlated)}"
            )
        
        return correlated
    
    def clear_cache(self) -> None:
        """Clear the correlation cache."""
        self._correlation_cache.clear()
        logger.info("Correlation cache cleared")
