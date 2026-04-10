"""
Market Statistics Analyzer for data-driven strategy generation.

This module provides comprehensive market analysis using multiple data sources:
- Yahoo Finance (OHLCV data)
- Alpha Vantage (pre-calculated indicators, sector data)
- FRED (macro economic context - VIX, rates)
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import yaml
from alpha_vantage.techindicators import TechIndicators
from fredapi import Fred

from src.data.market_data_manager import MarketDataManager
from src.strategy.indicator_library import IndicatorLibrary

logger = logging.getLogger(__name__)


class MarketStatisticsAnalyzer:
    """
    Analyzes market statistics from multiple data sources to inform strategy generation.
    
    Features:
    - Multi-source data integration (Yahoo Finance, Alpha Vantage, FRED)
    - Intelligent caching with different TTLs per source
    - Rate limiting for API calls
    - Graceful fallback when external APIs unavailable
    """
    
    # Class-level cache shared across all instances
    _shared_cache: Dict[str, Tuple[datetime, any]] = {}
    
    # Class-level rate limiting shared across all instances
    _alpha_vantage_calls_today = 0
    _alpha_vantage_reset_date = datetime.now().date()
    
    def __init__(self, market_data_manager: MarketDataManager, config_path: str = "config/autonomous_trading.yaml"):
        """
        Initialize the market statistics analyzer.
        
        Args:
            market_data_manager: Manager for fetching market data
            config_path: Path to configuration file
        """
        self.market_data = market_data_manager
        self.indicator_lib = IndicatorLibrary()
        
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize data source clients
        self._init_alpha_vantage()
        self._init_fred()
        
        logger.info("MarketStatisticsAnalyzer initialized with multi-source data integration")
    
    def _init_alpha_vantage(self):
        """Initialize Alpha Vantage client if enabled."""
        av_config = self.config.get('data_sources', {}).get('alpha_vantage', {})
        self.alpha_vantage_enabled = av_config.get('enabled', False)
        
        if self.alpha_vantage_enabled:
            api_key = av_config.get('api_key')
            if api_key and api_key != "YOUR_FREE_KEY":
                try:
                    self.alpha_vantage_ti = TechIndicators(key=api_key, output_format='pandas')
                    self.alpha_vantage_rate_limit = av_config.get('rate_limit', 500)
                    self.alpha_vantage_cache_duration = av_config.get('cache_duration', 3600)
                    logger.info(f"Alpha Vantage enabled (rate limit: {self.alpha_vantage_rate_limit}/day)")
                except Exception as e:
                    logger.warning(f"Failed to initialize Alpha Vantage: {e}")
                    self.alpha_vantage_enabled = False
            else:
                logger.warning("Alpha Vantage API key not configured, disabling")
                self.alpha_vantage_enabled = False
        else:
            logger.info("Alpha Vantage disabled in configuration")
    
    def _init_fred(self):
        """Initialize FRED client if enabled."""
        fred_config = self.config.get('data_sources', {}).get('fred', {})
        self.fred_enabled = fred_config.get('enabled', False)
        
        if self.fred_enabled:
            api_key = fred_config.get('api_key')
            if api_key and api_key != "YOUR_FREE_KEY":
                try:
                    self.fred_client = Fred(api_key=api_key)
                    self.fred_cache_duration = fred_config.get('cache_duration', 86400)
                    logger.info("FRED API enabled for macro economic data")
                except Exception as e:
                    logger.warning(f"Failed to initialize FRED: {e}")
                    self.fred_enabled = False
            else:
                logger.warning("FRED API key not configured, disabling")
                self.fred_enabled = False
        else:
            logger.info("FRED API disabled in configuration")
    
    def _get_cached(self, key: str, ttl_seconds: int) -> Optional[any]:
        """
        Get cached value if not expired.
        
        Args:
            key: Cache key
            ttl_seconds: Time to live in seconds
            
        Returns:
            Cached value or None if expired/missing
        """
        if key in self._shared_cache:
            timestamp, value = self._shared_cache[key]
            age = (datetime.now() - timestamp).total_seconds()
            if age < ttl_seconds:
                logger.debug(f"Cache hit for {key} (age: {age:.0f}s)")
                return value
            else:
                logger.debug(f"Cache expired for {key} (age: {age:.0f}s)")
        return None
    
    def _set_cached(self, key: str, value: any):
        """Set cached value with current timestamp."""
        self._shared_cache[key] = (datetime.now(), value)
    
    def _check_alpha_vantage_rate_limit(self) -> bool:
        """
        Check if we can make an Alpha Vantage API call.
        
        Returns:
            True if call is allowed, False if rate limit reached
        """
        # Reset counter if new day
        today = datetime.now().date()
        if today != self._alpha_vantage_reset_date:
            MarketStatisticsAnalyzer._alpha_vantage_calls_today = 0
            MarketStatisticsAnalyzer._alpha_vantage_reset_date = today
        
        # Check limit
        if self._alpha_vantage_calls_today >= self.alpha_vantage_rate_limit:
            logger.warning(f"Alpha Vantage rate limit reached ({self.alpha_vantage_rate_limit}/day)")
            return False
        
        return True
    
    def _increment_alpha_vantage_calls(self):
        """Increment Alpha Vantage call counter."""
        MarketStatisticsAnalyzer._alpha_vantage_calls_today += 1
        remaining = self.alpha_vantage_rate_limit - self._alpha_vantage_calls_today
        if remaining < 50:
            logger.warning(f"Alpha Vantage calls remaining today: {remaining}")
    
    def analyze_symbol(self, symbol: str, period_days: int = 365) -> Dict:
        """
        Analyze a symbol and return comprehensive market statistics.
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            period_days: Number of days of historical data to analyze
            
        Returns:
            Dictionary containing:
            - volatility_metrics: ATR/price ratio, std dev, historical volatility
            - trend_metrics: 20d/50d price change, ADX, trend strength
            - mean_reversion_metrics: Hurst exponent, autocorrelation, mean reversion score
            - price_action: current price, 20d high/low, support/resistance
            - sector_info: sector name, relative strength (if available)
        """
        cache_key = f"analyze_symbol_{symbol}_{period_days}"
        cached = self._get_cached(cache_key, 3600)  # 1 hour cache
        if cached is not None:
            return cached
        
        logger.info(f"Analyzing symbol {symbol} with {period_days} days of data")
        
        # Fetch OHLCV data from Yahoo Finance (primary source)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days)
        
        try:
            historical_data = self.market_data.get_historical_data(
                symbol=symbol,
                start=start_date,
                end=end_date,
                prefer_yahoo=True  # Use Yahoo Finance consistently
            )
            
            if not historical_data or len(historical_data) < 20:
                logger.error(f"Insufficient data for {symbol}: {len(historical_data) if historical_data else 0} days")
                return self._get_default_analysis()
            
            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    'timestamp': data.timestamp,
                    'open': data.open,
                    'high': data.high,
                    'low': data.low,
                    'close': data.close,
                    'volume': data.volume
                }
                for data in historical_data
            ])
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Calculate all metrics
            analysis = {
                'symbol': symbol,
                'data_points': len(df),
                'volatility_metrics': self._calculate_volatility_metrics(symbol, df),
                'trend_metrics': self._calculate_trend_metrics(symbol, df),
                'mean_reversion_metrics': self._calculate_mean_reversion_metrics(df),
                'price_action': self._calculate_price_action(df),
                'volume_profile': self._calculate_volume_profile(df),
                'sector_info': self._get_sector_info(symbol)
            }
            
            self._set_cached(cache_key, analysis)
            logger.info(f"Analysis complete for {symbol}: {analysis['data_points']} days")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing {symbol}: {e}")
            return self._get_default_analysis()
    
    def _calculate_volatility_metrics(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Calculate volatility metrics from OHLCV data."""
        try:
            # Calculate returns
            df['returns'] = df['close'].pct_change()
            
            # Try Alpha Vantage ATR first
            atr_values = None
            if self.alpha_vantage_enabled and self._check_alpha_vantage_rate_limit():
                try:
                    atr_data, _ = self.alpha_vantage_ti.get_atr(symbol=symbol, interval='daily', time_period=14)
                    self._increment_alpha_vantage_calls()
                    if not atr_data.empty:
                        atr_values = atr_data['ATR'].iloc[0]
                        logger.debug(f"Got ATR from Alpha Vantage for {symbol}: {atr_values:.2f}")
                except Exception as e:
                    logger.debug(f"Alpha Vantage ATR failed for {symbol}: {e}")
            
            # Fallback: calculate ATR locally
            if atr_values is None:
                try:
                    atr_series = self.indicator_lib.calculate('ATR', df, period=14)
                    if isinstance(atr_series, pd.Series) and not atr_series.empty:
                        atr_values = atr_series.iloc[-1]
                    else:
                        atr_values = np.nan
                except Exception as e:
                    logger.debug(f"Local ATR calculation failed: {e}")
                    atr_values = np.nan
            
            current_price = df['close'].iloc[-1]
            atr_ratio = atr_values / current_price if not pd.isna(atr_values) and current_price > 0 else 0
            
            # Standard deviation of returns (daily volatility)
            std_dev = df['returns'].std()
            
            # Historical volatility (20-day rolling)
            df['rolling_std'] = df['returns'].rolling(window=20).std()
            hist_vol = df['rolling_std'].iloc[-1] * np.sqrt(252)  # Annualized
            
            # Use std_dev as the primary volatility metric (daily volatility)
            volatility = float(std_dev) if not pd.isna(std_dev) else 0.0
            
            return {
                'volatility': volatility,  # Primary volatility metric (daily)
                'atr_ratio': float(atr_ratio),
                'std_dev_returns': float(std_dev),
                'historical_volatility_20d': float(hist_vol) if not pd.isna(hist_vol) else 0.0,
                'current_atr': float(atr_values) if not pd.isna(atr_values) else 0.0
            }
        except Exception as e:
            logger.error(f"Error calculating volatility metrics: {e}")
            return {
                'volatility': 0.0,
                'atr_ratio': 0.0,
                'std_dev_returns': 0.0,
                'historical_volatility_20d': 0.0,
                'current_atr': 0.0
            }
    
    def _calculate_trend_metrics(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Calculate trend metrics from OHLCV data."""
        try:
            # 20d and 50d price change
            if len(df) >= 20:
                price_change_20d = (df['close'].iloc[-1] / df['close'].iloc[-20] - 1) * 100
            else:
                price_change_20d = 0.0
            
            if len(df) >= 50:
                price_change_50d = (df['close'].iloc[-1] / df['close'].iloc[-50] - 1) * 100
            else:
                price_change_50d = 0.0
            
            # Try Alpha Vantage ADX first
            adx_value = None
            if self.alpha_vantage_enabled and self._check_alpha_vantage_rate_limit():
                try:
                    adx_data, _ = self.alpha_vantage_ti.get_adx(symbol=symbol, interval='daily', time_period=14)
                    self._increment_alpha_vantage_calls()
                    if not adx_data.empty:
                        adx_value = adx_data['ADX'].iloc[0]
                        logger.debug(f"Got ADX from Alpha Vantage for {symbol}: {adx_value:.2f}")
                except Exception as e:
                    logger.debug(f"Alpha Vantage ADX failed for {symbol}: {e}")
            
            # Fallback: calculate ADX locally (simplified)
            if adx_value is None:
                # Simple trend strength based on price changes
                adx_value = min(abs(price_change_20d) * 2, 100)  # Rough approximation
            
            # Trend strength score (0-1)
            trend_strength = min(abs(price_change_20d) / 10, 1.0)  # 10% move = max strength
            
            return {
                'price_change_20d': float(price_change_20d),
                'price_change_50d': float(price_change_50d),
                'adx': float(adx_value) if not pd.isna(adx_value) else 0.0,
                'trend_strength': float(trend_strength)
            }
        except Exception as e:
            logger.error(f"Error calculating trend metrics: {e}")
            return {
                'price_change_20d': 0.0,
                'price_change_50d': 0.0,
                'adx': 0.0,
                'trend_strength': 0.0
            }
    
    def _calculate_mean_reversion_metrics(self, df: pd.DataFrame) -> Dict:
        """Calculate mean reversion metrics from OHLCV data."""
        try:
            # Hurst exponent (simplified calculation)
            prices = df['close'].values
            lags = range(2, min(20, len(prices) // 2))
            tau = [np.std(np.subtract(prices[lag:], prices[:-lag])) for lag in lags]
            
            if len(tau) > 0 and all(t > 0 for t in tau):
                poly = np.polyfit(np.log(lags), np.log(tau), 1)
                hurst = poly[0]
            else:
                hurst = 0.5  # Default (random walk)
            
            # Autocorrelation
            returns = df['close'].pct_change().dropna()
            if len(returns) > 5:
                autocorr_lag1 = returns.autocorr(lag=1)
                autocorr_lag5 = returns.autocorr(lag=5)
            else:
                autocorr_lag1 = 0.0
                autocorr_lag5 = 0.0
            
            # Mean reversion score (0-1, higher = more mean reverting)
            # Hurst < 0.5 indicates mean reversion
            mean_reversion_score = max(0, 1 - (hurst * 2))
            
            return {
                'hurst_exponent': float(hurst),
                'autocorr_lag1': float(autocorr_lag1) if not pd.isna(autocorr_lag1) else 0.0,
                'autocorr_lag5': float(autocorr_lag5) if not pd.isna(autocorr_lag5) else 0.0,
                'mean_reversion_score': float(mean_reversion_score)
            }
        except Exception as e:
            logger.error(f"Error calculating mean reversion metrics: {e}")
            return {
                'hurst_exponent': 0.5,
                'autocorr_lag1': 0.0,
                'autocorr_lag5': 0.0,
                'mean_reversion_score': 0.0
            }
    
    def _calculate_price_action(self, df: pd.DataFrame) -> Dict:
        """Calculate price action metrics from OHLCV data."""
        try:
            current_price = df['close'].iloc[-1]
            
            # 20-day high/low
            if len(df) >= 20:
                high_20d = df['high'].iloc[-20:].max()
                low_20d = df['low'].iloc[-20:].min()
            else:
                high_20d = df['high'].max()
                low_20d = df['low'].min()
            
            # Support/resistance (simplified)
            try:
                sr_dict = self.indicator_lib.calculate('SUPPORT_RESISTANCE', df)
                if isinstance(sr_dict, dict):
                    support = sr_dict.get('Support', pd.Series([low_20d] * len(df))).iloc[-1]
                    resistance = sr_dict.get('Resistance', pd.Series([high_20d] * len(df))).iloc[-1]
                else:
                    support = low_20d
                    resistance = high_20d
            except Exception as e:
                logger.debug(f"Error calculating support/resistance: {e}")
                support = low_20d
                resistance = high_20d
            
            return {
                'current_price': float(current_price),
                'high_20d': float(high_20d),
                'low_20d': float(low_20d),
                'support': float(support) if not pd.isna(support) else float(low_20d),
                'resistance': float(resistance) if not pd.isna(resistance) else float(high_20d)
            }
        except Exception as e:
            logger.error(f"Error calculating price action: {e}")
            return {
                'current_price': 0.0,
                'high_20d': 0.0,
                'low_20d': 0.0,
                'support': 0.0,
                'resistance': 0.0
            }

    def _calculate_volume_profile(self, df: pd.DataFrame) -> Dict:
        """Calculate volume profile metrics for template matching.
        
        Volume analysis helps match symbols to breakout/momentum templates:
        - High spike frequency → good for volume breakout strategies
        - Rising volume trend → good for momentum strategies
        - Low/declining volume → better for mean reversion (less noise)
        """
        try:
            vol = df['volume']
            if vol.isna().all() or (vol == 0).all():
                # Forex and some instruments have no volume data
                return {
                    'avg_volume_20d': 0.0,
                    'avg_volume_50d': 0.0,
                    'volume_trend': 0.0,
                    'current_vs_avg': 0.0,
                    'spike_frequency': 0.0,
                    'has_volume_data': False,
                }
            
            # Average volumes
            avg_20d = float(vol.iloc[-20:].mean()) if len(vol) >= 20 else float(vol.mean())
            avg_50d = float(vol.iloc[-50:].mean()) if len(vol) >= 50 else float(vol.mean())
            
            # Volume trend: ratio of recent 20d avg to older 50d avg
            # > 1.0 = increasing volume, < 1.0 = declining
            volume_trend = avg_20d / avg_50d if avg_50d > 0 else 1.0
            
            # Current volume vs 20d average
            current_vol = float(vol.iloc[-1])
            current_vs_avg = current_vol / avg_20d if avg_20d > 0 else 1.0
            
            # Spike frequency: % of days with volume > 2x average (last 60 days)
            recent = vol.iloc[-60:] if len(vol) >= 60 else vol
            avg_for_spike = recent.mean()
            spikes = (recent > avg_for_spike * 2.0).sum()
            spike_frequency = float(spikes / len(recent)) if len(recent) > 0 else 0.0
            
            return {
                'avg_volume_20d': avg_20d,
                'avg_volume_50d': avg_50d,
                'volume_trend': float(volume_trend),
                'current_vs_avg': float(current_vs_avg),
                'spike_frequency': float(spike_frequency),
                'has_volume_data': True,
            }
        except Exception as e:
            logger.debug(f"Error calculating volume profile: {e}")
            return {
                'avg_volume_20d': 0.0,
                'avg_volume_50d': 0.0,
                'volume_trend': 0.0,
                'current_vs_avg': 0.0,
                'spike_frequency': 0.0,
                'has_volume_data': False,
            }
    
    def _get_sector_info(self, symbol: str) -> Dict:
        """Get sector information (simplified - returns default for now)."""
        # Note: Alpha Vantage sector performance API is not available in the free tier
        # This is a placeholder for future enhancement
        return {'sector': 'Unknown', 'relative_strength': 0.0}
    
    def _get_default_analysis(self) -> Dict:
        """Return default analysis when data is unavailable."""
        return {
            'symbol': 'UNKNOWN',
            'data_points': 0,
            'volatility_metrics': {
                'atr_ratio': 0.0,
                'std_dev_returns': 0.0,
                'historical_volatility_20d': 0.0,
                'current_atr': 0.0
            },
            'trend_metrics': {
                'price_change_20d': 0.0,
                'price_change_50d': 0.0,
                'adx': 0.0,
                'trend_strength': 0.0
            },
            'mean_reversion_metrics': {
                'hurst_exponent': 0.5,
                'autocorr_lag1': 0.0,
                'autocorr_lag5': 0.0,
                'mean_reversion_score': 0.0
            },
            'price_action': {
                'current_price': 0.0,
                'high_20d': 0.0,
                'low_20d': 0.0,
                'support': 0.0,
                'resistance': 0.0
            },
            'sector_info': {
                'sector': 'Unknown',
                'relative_strength': 0.0
            }
        }

    def analyze_indicator_distributions(self, symbol: str, period_days: int = 365) -> Dict:
        """
        Analyze indicator distributions to understand typical ranges and current values.
        
        Args:
            symbol: Stock symbol
            period_days: Number of days to analyze
            
        Returns:
            Dictionary with distribution statistics for each indicator:
            - mean, std, min, max
            - pct_oversold: % of time in oversold zone (< 30)
            - pct_overbought: % of time in overbought zone (> 70)
            - avg_duration_oversold: average days in oversold
            - avg_duration_overbought: average days in overbought
            - current_value: current indicator value
            - current_percentile: where current value sits in distribution
        """
        cache_key = f"indicator_dist_{symbol}_{period_days}"
        cached = self._get_cached(cache_key, 3600)  # 1 hour cache
        if cached is not None:
            return cached
        
        logger.info(f"Analyzing indicator distributions for {symbol}")
        
        # Fetch OHLCV data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=period_days)
        
        try:
            historical_data = self.market_data.get_historical_data(
                symbol=symbol,
                start=start_date,
                end=end_date,
                prefer_yahoo=True  # Use Yahoo Finance consistently
            )
            
            if not historical_data or len(historical_data) < 20:
                logger.error(f"Insufficient data for {symbol}")
                return {}
            
            # Convert to DataFrame
            df = pd.DataFrame([
                {
                    'timestamp': data.timestamp,
                    'open': data.open,
                    'high': data.high,
                    'low': data.low,
                    'close': data.close,
                    'volume': data.volume
                }
                for data in historical_data
            ])
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Indicators to analyze
            indicators_to_analyze = ['RSI', 'STOCH']
            
            # Try Alpha Vantage first for pre-calculated indicators
            distributions = {}
            for indicator_name in indicators_to_analyze:
                dist = self._analyze_single_indicator(symbol, df, indicator_name)
                if dist:
                    distributions[indicator_name] = dist
            
            self._set_cached(cache_key, distributions)
            logger.info(f"Indicator distribution analysis complete for {symbol}: {len(distributions)} indicators")
            return distributions
            
        except Exception as e:
            logger.error(f"Error analyzing indicator distributions for {symbol}: {e}")
            return {}
    
    def _analyze_single_indicator(self, symbol: str, df: pd.DataFrame, indicator_name: str) -> Optional[Dict]:
        """Analyze distribution of a single indicator."""
        try:
            # Try Alpha Vantage first
            indicator_values = None
            
            if self.alpha_vantage_enabled and self._check_alpha_vantage_rate_limit():
                try:
                    if indicator_name == 'RSI':
                        data, _ = self.alpha_vantage_ti.get_rsi(symbol=symbol, interval='daily', time_period=14)
                        self._increment_alpha_vantage_calls()
                        if not data.empty:
                            indicator_values = data['RSI']
                            logger.debug(f"Got RSI from Alpha Vantage for {symbol}")
                    elif indicator_name == 'STOCH':
                        data, _ = self.alpha_vantage_ti.get_stoch(symbol=symbol, interval='daily')
                        self._increment_alpha_vantage_calls()
                        if not data.empty:
                            indicator_values = data['SlowK']
                            logger.debug(f"Got STOCH from Alpha Vantage for {symbol}")
                except Exception as e:
                    logger.debug(f"Alpha Vantage {indicator_name} failed for {symbol}: {e}")
            
            # Fallback: calculate locally
            if indicator_values is None:
                if indicator_name == 'STOCH':
                    result = self.indicator_lib.calculate(indicator_name, df, symbol=symbol, k_period=14, d_period=3)
                else:
                    result = self.indicator_lib.calculate(indicator_name, df, symbol=symbol, period=14)
                
                # Handle different return types
                if isinstance(result, tuple):
                    # STOCH returns (SlowK, SlowD)
                    indicator_values = result[0]
                elif isinstance(result, pd.Series):
                    indicator_values = result
                else:
                    logger.warning(f"Unexpected return type for {indicator_name}: {type(result)}")
                    return None
            
            if indicator_values is None or (isinstance(indicator_values, pd.Series) and indicator_values.empty):
                return None
            
            # Calculate distribution statistics
            values = indicator_values.dropna()
            if len(values) == 0:
                return None
            
            current_value = values.iloc[-1]
            
            # Basic statistics
            mean = values.mean()
            std = values.std()
            min_val = values.min()
            max_val = values.max()
            
            # Oversold/overbought analysis (for oscillators like RSI, STOCH)
            oversold_threshold = 30
            overbought_threshold = 70
            
            oversold_mask = values < oversold_threshold
            overbought_mask = values > overbought_threshold
            
            pct_oversold = (oversold_mask.sum() / len(values)) * 100
            pct_overbought = (overbought_mask.sum() / len(values)) * 100
            
            # Calculate average duration in zones
            avg_duration_oversold = self._calculate_avg_duration(oversold_mask)
            avg_duration_overbought = self._calculate_avg_duration(overbought_mask)
            
            # Current percentile
            current_percentile = (values < current_value).sum() / len(values) * 100
            
            return {
                'mean': float(mean),
                'std': float(std),
                'min': float(min_val),
                'max': float(max_val),
                'pct_oversold': float(pct_oversold),
                'pct_overbought': float(pct_overbought),
                'avg_duration_oversold': float(avg_duration_oversold),
                'avg_duration_overbought': float(avg_duration_overbought),
                'current_value': float(current_value),
                'current_percentile': float(current_percentile)
            }
        except Exception as e:
            logger.error(f"Error analyzing {indicator_name}: {e}")
            return None
    
    def _calculate_avg_duration(self, mask: pd.Series) -> float:
        """Calculate average duration of consecutive True values in a boolean mask."""
        if mask.sum() == 0:
            return 0.0
        
        # Find consecutive True sequences
        durations = []
        current_duration = 0
        
        for value in mask:
            if value:
                current_duration += 1
            else:
                if current_duration > 0:
                    durations.append(current_duration)
                    current_duration = 0
        
        # Don't forget the last sequence
        if current_duration > 0:
            durations.append(current_duration)
        
        return np.mean(durations) if durations else 0.0
    
    def get_market_context(self) -> Dict:
        """
        Get comprehensive macro market context from FRED.
        
        Returns:
            Dictionary containing:
            - vix: Current VIX level (market fear index)
            - treasury_10y: 10-year treasury yield (risk-free rate)
            - unemployment_rate: Current unemployment rate (labor market health)
            - fed_funds_rate: Federal funds rate (monetary policy stance)
            - inflation_rate: CPI inflation rate (price stability)
            - sp500_pe_ratio: S&P 500 P/E ratio (valuation metric)
            - risk_regime: 'risk_on', 'risk_off', or 'transitional'
            - macro_regime: Composite regime based on all indicators
            - last_updated: Timestamp of data
        """
        cache_key = "market_context"
        cached = self._get_cached(cache_key, self.fred_cache_duration)
        if cached is not None:
            return cached
        
        logger.info("Fetching comprehensive market context from FRED")
        
        if not self.fred_enabled:
            logger.warning("FRED API disabled, returning default market context")
            return self._get_default_market_context()
        
        try:
            # Fetch VIX (CBOE Volatility Index)
            vix_series = self.fred_client.get_series('VIXCLS', observation_start=datetime.now() - timedelta(days=7))
            vix = vix_series.iloc[-1] if not vix_series.empty else 20.0
            
            # Fetch 10-year treasury yield
            treasury_series = self.fred_client.get_series('DGS10', observation_start=datetime.now() - timedelta(days=7))
            treasury_10y = treasury_series.iloc[-1] if not treasury_series.empty else 4.0
            
            # Fetch unemployment rate (monthly data)
            unemployment_series = self.fred_client.get_series('UNRATE', observation_start=datetime.now() - timedelta(days=90))
            unemployment_rate = unemployment_series.iloc[-1] if not unemployment_series.empty else 4.0
            unemployment_trend = 'falling' if len(unemployment_series) >= 2 and unemployment_series.iloc[-1] < unemployment_series.iloc[-2] else 'rising'
            
            # Fetch Fed Funds Rate
            fed_funds_series = self.fred_client.get_series('FEDFUNDS', observation_start=datetime.now() - timedelta(days=90))
            fed_funds_rate = fed_funds_series.iloc[-1] if not fed_funds_series.empty else 5.0
            fed_stance = 'accommodative' if fed_funds_rate < 3.0 else 'tightening' if fed_funds_rate > 5.0 else 'neutral'
            
            # Fetch CPI inflation (year-over-year, monthly data)
            # Note: CPIAUCSL is the index, we need to calculate YoY change
            cpi_series = self.fred_client.get_series('CPIAUCSL', observation_start=datetime.now() - timedelta(days=400))
            if len(cpi_series) >= 12:
                # Calculate year-over-year inflation
                inflation_rate = ((cpi_series.iloc[-1] / cpi_series.iloc[-12]) - 1) * 100
            else:
                inflation_rate = 3.0  # Default
            
            # Fetch S&P 500 P/E Ratio (if available)
            try:
                pe_series = self.fred_client.get_series('MULTPL/SP500_PE_RATIO_MONTH', observation_start=datetime.now() - timedelta(days=90))
                sp500_pe_ratio = pe_series.iloc[-1] if not pe_series.empty else 20.0
            except:
                sp500_pe_ratio = 20.0
                logger.debug("S&P 500 P/E ratio not available, using default")
            
            # --- Expanded FRED macro data for regime conditioning ---
            # Yield curve slope: DGS10 - DGS2. Negative = recession signal.
            # ISM PMI: > 50 = expansion, < 50 = contraction.
            # High yield spread: credit stress indicator. Blowout = risk-off.
            # Trade-weighted dollar: strong dollar = headwind for commodities/EM.
            treasury_2y = 3.5  # default
            yield_curve_slope = 0.5  # default positive
            ism_pmi = 50.0  # default neutral
            hy_spread = 4.0  # default normal
            trade_weighted_dollar = 100.0  # default
            
            try:
                t2y_series = self.fred_client.get_series('DGS2', observation_start=datetime.now() - timedelta(days=7))
                if not t2y_series.empty:
                    treasury_2y = float(t2y_series.dropna().iloc[-1])
                    yield_curve_slope = float(treasury_10y) - treasury_2y
            except Exception as e:
                logger.debug(f"Could not fetch DGS2: {e}")
            
            try:
                # ISM Manufacturing PMI (NAPM series)
                pmi_series = self.fred_client.get_series('NAPM', observation_start=datetime.now() - timedelta(days=90))
                if not pmi_series.empty:
                    ism_pmi = float(pmi_series.dropna().iloc[-1])
            except Exception as e:
                logger.debug(f"Could not fetch ISM PMI: {e}")
            
            try:
                # ICE BofA High Yield OAS
                hy_series = self.fred_client.get_series('BAMLH0A0HYM2', observation_start=datetime.now() - timedelta(days=14))
                if not hy_series.empty:
                    hy_spread = float(hy_series.dropna().iloc[-1])
            except Exception as e:
                logger.debug(f"Could not fetch HY spread: {e}")
            
            try:
                # Trade-weighted US dollar index (broad)
                dxy_series = self.fred_client.get_series('DTWEXBGS', observation_start=datetime.now() - timedelta(days=14))
                if not dxy_series.empty:
                    trade_weighted_dollar = float(dxy_series.dropna().iloc[-1])
            except Exception as e:
                logger.debug(f"Could not fetch trade-weighted dollar: {e}")
            
            # Determine simple risk regime based on VIX
            if vix < 15:
                risk_regime = 'risk_on'
            elif vix > 25:
                risk_regime = 'risk_off'
            else:
                risk_regime = 'neutral'
            
            # Calculate composite macro regime
            macro_regime = self._calculate_macro_regime(
                vix, unemployment_trend, fed_stance, inflation_rate
            )
            
            # Also detect price-action sub-regime and include it
            # This gives downstream consumers both macro (FRED-based) and technical (price-based) views
            try:
                sub_regime, sub_confidence, _, sub_metrics = self.detect_sub_regime()
                sub_regime_str = sub_regime.value if hasattr(sub_regime, 'value') else str(sub_regime)
            except Exception:
                sub_regime_str = 'ranging'
                sub_confidence = 0.5
            
            context = {
                'vix': float(vix),
                'treasury_10y': float(treasury_10y),
                'treasury_2y': float(treasury_2y),
                'yield_curve_slope': float(yield_curve_slope),
                'ism_pmi': float(ism_pmi),
                'hy_spread': float(hy_spread),
                'trade_weighted_dollar': float(trade_weighted_dollar),
                'unemployment_rate': float(unemployment_rate),
                'unemployment_trend': unemployment_trend,
                'fed_funds_rate': float(fed_funds_rate),
                'fed_stance': fed_stance,
                'inflation_rate': float(inflation_rate),
                'sp500_pe_ratio': float(sp500_pe_ratio),
                'risk_regime': risk_regime,
                'macro_regime': macro_regime,
                'sub_regime': sub_regime_str,
                'sub_regime_confidence': sub_confidence,
                'last_updated': datetime.now().isoformat()
            }
            
            self._set_cached(cache_key, context)
            logger.info(
                f"Market context: VIX={vix:.1f}, Treasury={treasury_10y:.2f}%, "
                f"2Y={treasury_2y:.2f}%, Curve={yield_curve_slope:+.2f}%, "
                f"PMI={ism_pmi:.1f}, HY_Spread={hy_spread:.2f}%, "
                f"Unemployment={unemployment_rate:.1f}% ({unemployment_trend}), "
                f"Fed Funds={fed_funds_rate:.2f}% ({fed_stance}), "
                f"Inflation={inflation_rate:.1f}%, P/E={sp500_pe_ratio:.1f}, "
                f"Regime={risk_regime}, Macro={macro_regime}"
            )
            return context
            
        except Exception as e:
            logger.error(f"Error fetching market context from FRED: {e}")
            return self._get_default_market_context()
    
    def _calculate_macro_regime(
        self, vix: float, unemployment_trend: str, fed_stance: str, inflation_rate: float
    ) -> str:
        """
        Calculate composite macro regime based on multiple indicators.
        
        Args:
            vix: VIX level
            unemployment_trend: 'falling' or 'rising'
            fed_stance: 'accommodative', 'neutral', or 'tightening'
            inflation_rate: CPI inflation rate (%)
            
        Returns:
            'risk_on', 'risk_off', or 'transitional'
        """
        risk_on_signals = 0
        risk_off_signals = 0
        
        # VIX signals
        if vix < 15:
            risk_on_signals += 2  # Strong signal
        elif vix > 25:
            risk_off_signals += 2  # Strong signal
        
        # Unemployment signals
        if unemployment_trend == 'falling':
            risk_on_signals += 1
        else:
            risk_off_signals += 1
        
        # Fed stance signals
        if fed_stance == 'accommodative':
            risk_on_signals += 1
        elif fed_stance == 'tightening':
            risk_off_signals += 1
        
        # Inflation signals (high inflation is risk-off)
        if inflation_rate > 5.0:
            risk_off_signals += 1
        elif inflation_rate < 2.0:
            risk_on_signals += 1
        
        # Determine regime
        if risk_on_signals >= risk_off_signals + 2:
            return 'risk_on'
        elif risk_off_signals >= risk_on_signals + 2:
            return 'risk_off'
        else:
            return 'transitional'
    
    def _get_default_market_context(self) -> Dict:
        """Return default market context when FRED is unavailable."""
        return {
            'vix': 20.0,  # Neutral level
            'treasury_10y': 4.0,  # Approximate current level
            'treasury_2y': 3.5,
            'yield_curve_slope': 0.5,
            'ism_pmi': 50.0,
            'hy_spread': 4.0,
            'trade_weighted_dollar': 100.0,
            'unemployment_rate': 4.0,  # Approximate current level
            'unemployment_trend': 'stable',
            'fed_funds_rate': 5.0,  # Approximate current level
            'fed_stance': 'neutral',
            'inflation_rate': 3.0,  # Approximate current level
            'sp500_pe_ratio': 20.0,  # Historical average
            'risk_regime': 'neutral',
            'macro_regime': 'transitional',
            'last_updated': datetime.now().isoformat()
        }
    
    def clear_cache(self):
        """Clear all cached data. Useful for testing or forcing fresh data fetch."""
        MarketStatisticsAnalyzer._shared_cache.clear()
        logger.info("Shared cache cleared")
    
    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache size and oldest entry age
        """
        if not self._shared_cache:
            return {'size': 0, 'oldest_age_seconds': 0}
        
        now = datetime.now()
        ages = [(now - timestamp).total_seconds() for timestamp, _ in self._shared_cache.values()]
        
        return {
            'size': len(self._shared_cache),
            'oldest_age_seconds': max(ages) if ages else 0,
            'newest_age_seconds': min(ages) if ages else 0
        }
    
    def get_comprehensive_analysis(self, symbols: List[str], period_days: int = 365) -> Dict:
        """
        Get comprehensive analysis for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            period_days: Number of days to analyze
            
        Returns:
            Dictionary with:
            - market_context: Macro market context from FRED
            - symbol_analysis: Dict of symbol -> analysis
            - indicator_distributions: Dict of symbol -> indicator distributions
        """
        logger.info(f"Running comprehensive analysis for {len(symbols)} symbols")
        
        result = {
            'market_context': self.get_market_context(),
            'symbol_analysis': {},
            'indicator_distributions': {}
        }
        
        for symbol in symbols:
            try:
                result['symbol_analysis'][symbol] = self.analyze_symbol(symbol, period_days)
                result['indicator_distributions'][symbol] = self.analyze_indicator_distributions(symbol, period_days)
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                result['symbol_analysis'][symbol] = self._get_default_analysis()
                result['indicator_distributions'][symbol] = {}
        
        logger.info(f"Comprehensive analysis complete for {len(symbols)} symbols")
        return result
    def detect_sub_regime(self, symbols: List[str] = None) -> tuple:
        """
        Detect detailed market sub-regime based on trend strength and volatility.

        Sub-regimes:
        - TRENDING_UP_STRONG: Strong uptrend (20d > 5%, 50d > 10%)
        - TRENDING_UP_WEAK: Weak uptrend (20d 2-5%, 50d 5-10%)
        - TRENDING_DOWN_STRONG: Strong downtrend (20d < -5%, 50d < -10%)
        - TRENDING_DOWN_WEAK: Weak downtrend (20d -5% to -2%, 50d -10% to -5%)
        - RANGING_LOW_VOL: Sideways, low volatility (ATR/price < 2%)
        - RANGING_HIGH_VOL: Sideways, high volatility (ATR/price > 3%)

        Args:
            symbols: List of symbols to analyze (defaults to major indices)

        Returns:
            Tuple of (sub_regime, confidence, data_quality, metrics_dict)
        """
        from src.strategy.strategy_templates import MarketRegime

        if symbols is None:
            symbols = ["SPY", "QQQ", "DIA"]

        logger.info(f"Detecting sub-regime using symbols: {symbols}")

        try:
            # Load analysis period from config
            import yaml
            from pathlib import Path
            config_path = Path("config/autonomous_trading.yaml")
            analysis_period_days = 365  # Default to 1 year for sub-regime detection
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    # Use backtest days for market analysis (730 days = 2 years)
                    analysis_period_days = config.get('backtest', {}).get('days', 730)
            
            logger.info(f"Using {analysis_period_days} days of historical data for sub-regime detection")
            
            # Collect price changes and volatility metrics
            changes_20d = []
            changes_50d = []
            atr_ratios = []
            data_days = []

            end_date = datetime.now()
            start_date = end_date - timedelta(days=analysis_period_days)

            for symbol in symbols:
                try:
                    # Fetch historical data from Yahoo Finance
                    historical_data = self.market_data.get_historical_data(
                        symbol=symbol,
                        start=start_date,
                        end=end_date,
                        interval="1d",
                        prefer_yahoo=True  # Use Yahoo Finance consistently
                    )

                    days_available = len(historical_data)
                    data_days.append(days_available)

                    if days_available < 30:
                        logger.warning(f"Insufficient data for {symbol} ({days_available} days), skipping")
                        continue

                    # Convert to DataFrame for analysis
                    df = pd.DataFrame([
                        {
                            'timestamp': data.timestamp,
                            'open': data.open,
                            'high': data.high,
                            'low': data.low,
                            'close': data.close,
                            'volume': data.volume
                        }
                        for data in historical_data
                    ])
                    df = df.sort_values('timestamp').reset_index(drop=True)

                    # Calculate price changes
                    current_price = df['close'].iloc[-1]

                    if days_available >= 20:
                        price_20d_ago = df['close'].iloc[-20]
                        change_20d = (current_price - price_20d_ago) / price_20d_ago
                        changes_20d.append(change_20d)

                    if days_available >= 50:
                        price_50d_ago = df['close'].iloc[-50]
                        change_50d = (current_price - price_50d_ago) / price_50d_ago
                        changes_50d.append(change_50d)

                    # Calculate ATR/price ratio for volatility
                    if days_available >= 14:
                        # Calculate True Range
                        df['high_low'] = df['high'] - df['low']
                        df['high_close'] = abs(df['high'] - df['close'].shift(1))
                        df['low_close'] = abs(df['low'] - df['close'].shift(1))
                        df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)

                        # Calculate ATR (14-period)
                        atr = df['true_range'].rolling(window=14).mean().iloc[-1]
                        atr_ratio = atr / current_price
                        atr_ratios.append(atr_ratio)

                        logger.debug(f"{symbol}: 20d={change_20d:.2%}, 50d={change_50d:.2%}, ATR/price={atr_ratio:.2%}")

                except Exception as e:
                    logger.warning(f"Failed to analyze {symbol}: {e}")
                    continue

            # Determine data quality (updated thresholds for 2-year lookback)
            if data_days:
                avg_days = sum(data_days) / len(data_days)
                if avg_days >= 600:  # ~2 years
                    data_quality = "EXCELLENT"
                elif avg_days >= 365:  # ~1 year
                    data_quality = "GOOD"
                elif avg_days >= 180:  # ~6 months
                    data_quality = "FAIR"
                else:
                    data_quality = "POOR"
            else:
                data_quality = "POOR"
                logger.warning("No data available for any symbol")
                return MarketRegime.RANGING, 0.0, data_quality, {}

            # Calculate averages
            avg_change_20d = sum(changes_20d) / len(changes_20d) if changes_20d else 0
            avg_change_50d = sum(changes_50d) / len(changes_50d) if changes_50d else 0
            avg_atr_ratio = sum(atr_ratios) / len(atr_ratios) if atr_ratios else 0.02

            metrics = {
                'avg_change_20d': avg_change_20d,
                'avg_change_50d': avg_change_50d,
                'avg_atr_ratio': avg_atr_ratio,
                'data_quality': data_quality
            }

            logger.info(f"Sub-regime metrics: 20d={avg_change_20d:.2%}, 50d={avg_change_50d:.2%}, ATR/price={avg_atr_ratio:.2%}")

            # Detect sub-regime based on thresholds
            # Use a scoring approach instead of rigid bands to avoid gaps
            # where slow trends (20d=3%, 50d=3%) fall through to "ranging"
            confidence = 0.0

            # Calculate trend score: weighted combination of 20d and 50d changes
            # 20d is more recent (higher weight), 50d captures sustained moves
            trend_score = avg_change_20d * 0.6 + avg_change_50d * 0.4

            # Strong uptrend
            if trend_score > 0.04 and avg_change_20d > 0.03 and avg_change_50d > 0.05:
                sub_regime = MarketRegime.TRENDING_UP_STRONG
                confidence = min(0.5 + abs(trend_score) * 5, 1.0)
                logger.info(f"Detected: STRONG UPTREND (20d={avg_change_20d:.1%}, 50d={avg_change_50d:.1%}, score={trend_score:.3f})")

            # Weak uptrend (catches slow grinds higher that old thresholds missed)
            elif trend_score > 0.015 and avg_change_20d > 0.01:
                sub_regime = MarketRegime.TRENDING_UP_WEAK
                confidence = min(0.4 + abs(trend_score) * 5, 0.8)
                logger.info(f"Detected: WEAK UPTREND (20d={avg_change_20d:.1%}, 50d={avg_change_50d:.1%}, score={trend_score:.3f})")

            # Strong downtrend
            elif trend_score < -0.04 and avg_change_20d < -0.03 and avg_change_50d < -0.05:
                sub_regime = MarketRegime.TRENDING_DOWN_STRONG
                confidence = min(0.5 + abs(trend_score) * 5, 1.0)
                logger.info(f"Detected: STRONG DOWNTREND (20d={avg_change_20d:.1%}, 50d={avg_change_50d:.1%}, score={trend_score:.3f})")

            # Weak downtrend
            elif trend_score < -0.015 and avg_change_20d < -0.01:
                sub_regime = MarketRegime.TRENDING_DOWN_WEAK
                confidence = min(0.4 + abs(trend_score) * 5, 0.8)
                logger.info(f"Detected: WEAK DOWNTREND (20d={avg_change_20d:.1%}, 50d={avg_change_50d:.1%}, score={trend_score:.3f})")

            # Ranging — check volatility
            else:
                # Low volatility ranging — confidence scales with how low vol is
                if avg_atr_ratio < 0.02:
                    # Scale confidence: 0.5% ATR = very confident ranging, 1.9% = borderline
                    confidence = min(0.5 + (0.02 - avg_atr_ratio) * 25, 0.9)
                    sub_regime = MarketRegime.RANGING_LOW_VOL
                    logger.info(f"Detected: LOW VOLATILITY RANGING (ATR/price={avg_atr_ratio:.2%}, confidence={confidence:.0%})")

                # High volatility ranging
                elif avg_atr_ratio > 0.03:
                    confidence = min(0.5 + (avg_atr_ratio - 0.03) * 20, 0.9)
                    sub_regime = MarketRegime.RANGING_HIGH_VOL
                    logger.info(f"Detected: HIGH VOLATILITY RANGING (ATR/price={avg_atr_ratio:.2%}, confidence={confidence:.0%})")

                # Normal ranging
                else:
                    confidence = 0.5
                    sub_regime = MarketRegime.RANGING
                    logger.info(f"Detected: RANGING (ATR/price={avg_atr_ratio:.2%})")

            return sub_regime, confidence, data_quality, metrics

        except Exception as e:
            logger.error(f"Error detecting sub-regime: {e}")
            return MarketRegime.RANGING, 0.0, "POOR", {}

    def detect_regime_change(
        self,
        strategy_id: str,
        activation_regime: str,
        activation_metrics: Dict,
        symbols: List[str] = None
    ) -> Dict:
        """
        Detect if market regime has changed significantly since strategy activation.

        Compares current regime indicators to baseline at activation:
        - Volatility changes (ATR/price ratio)
        - Trend reversals (20d/50d price changes)
        - Correlation spikes

        Args:
            strategy_id: Strategy identifier
            activation_regime: Regime at strategy activation (e.g., "TRENDING_UP")
            activation_metrics: Metrics at activation (volatility, trend, etc.)
            symbols: Symbols to analyze (defaults to strategy symbols or major indices)

        Returns:
            Dict with:
                - regime_changed: bool
                - current_regime: str
                - change_type: str (volatility_spike, trend_reversal, correlation_spike, etc.)
                - change_magnitude: float (how much changed, e.g., 2.0 = doubled)
                - current_metrics: Dict
                - recommendation: str (reduce_positions, pause_strategy, retire_strategy)
        """
        logger.info(f"Detecting regime change for strategy {strategy_id}")
        logger.info(f"  Activation regime: {activation_regime}")
        logger.info(f"  Activation metrics: {activation_metrics}")

        try:
            # Get current regime and metrics
            current_regime, confidence, data_quality, current_metrics = self.detect_sub_regime(symbols)

            logger.info(f"  Current regime: {current_regime}")
            logger.info(f"  Current metrics: {current_metrics}")

            # Initialize result
            result = {
                'regime_changed': False,
                'current_regime': str(current_regime),
                'change_type': None,
                'change_magnitude': 0.0,
                'current_metrics': current_metrics,
                'activation_metrics': activation_metrics,
                'recommendation': None,
                'details': []
            }

            # Extract metrics for comparison
            activation_volatility = activation_metrics.get('avg_atr_ratio', 0.02)
            current_volatility = current_metrics.get('avg_atr_ratio', 0.02)

            activation_trend_20d = activation_metrics.get('avg_change_20d', 0.0)
            current_trend_20d = current_metrics.get('avg_change_20d', 0.0)

            activation_trend_50d = activation_metrics.get('avg_change_50d', 0.0)
            current_trend_50d = current_metrics.get('avg_change_50d', 0.0)

            # Check for volatility spike (>50% increase)
            if activation_volatility > 0:
                volatility_ratio = current_volatility / activation_volatility
                if volatility_ratio > 1.5:
                    result['regime_changed'] = True
                    result['change_type'] = 'volatility_spike'
                    result['change_magnitude'] = volatility_ratio
                    result['recommendation'] = 'reduce_positions'
                    result['details'].append(
                        f"Volatility increased {volatility_ratio:.1f}x "
                        f"(from {activation_volatility:.2%} to {current_volatility:.2%})"
                    )
                    logger.warning(f"  ⚠ Volatility spike detected: {volatility_ratio:.1f}x increase")

            # Check for trend reversal
            # Uptrend to downtrend
            if activation_trend_20d > 0.02 and current_trend_20d < -0.02:
                result['regime_changed'] = True
                result['change_type'] = 'trend_reversal_down'
                result['change_magnitude'] = abs(current_trend_20d - activation_trend_20d)
                result['recommendation'] = 'pause_strategy' if 'TRENDING_UP' in activation_regime else 'monitor'
                result['details'].append(
                    f"Trend reversed from up ({activation_trend_20d:.1%}) to down ({current_trend_20d:.1%})"
                )
                logger.warning(f"  ⚠ Trend reversal detected: uptrend → downtrend")

            # Downtrend to uptrend
            elif activation_trend_20d < -0.02 and current_trend_20d > 0.02:
                result['regime_changed'] = True
                result['change_type'] = 'trend_reversal_up'
                result['change_magnitude'] = abs(current_trend_20d - activation_trend_20d)
                result['recommendation'] = 'pause_strategy' if 'TRENDING_DOWN' in activation_regime else 'monitor'
                result['details'].append(
                    f"Trend reversed from down ({activation_trend_20d:.1%}) to up ({current_trend_20d:.1%})"
                )
                logger.warning(f"  ⚠ Trend reversal detected: downtrend → uptrend")

            # Trending to ranging
            elif abs(activation_trend_20d) > 0.03 and abs(current_trend_20d) < 0.02:
                result['regime_changed'] = True
                result['change_type'] = 'trend_to_ranging'
                result['change_magnitude'] = abs(activation_trend_20d - current_trend_20d)
                result['recommendation'] = 'retire_strategy' if 'TRENDING' in activation_regime else 'monitor'
                result['details'].append(
                    f"Market shifted from trending ({activation_trend_20d:.1%}) to ranging ({current_trend_20d:.1%})"
                )
                logger.warning(f"  ⚠ Regime shift: trending → ranging")

            # Ranging to trending
            elif abs(activation_trend_20d) < 0.02 and abs(current_trend_20d) > 0.03:
                result['regime_changed'] = True
                result['change_type'] = 'ranging_to_trend'
                result['change_magnitude'] = abs(current_trend_20d - activation_trend_20d)
                result['recommendation'] = 'retire_strategy' if 'RANGING' in activation_regime else 'monitor'
                result['details'].append(
                    f"Market shifted from ranging ({activation_trend_20d:.1%}) to trending ({current_trend_20d:.1%})"
                )
                logger.warning(f"  ⚠ Regime shift: ranging → trending")

            # Check for regime mismatch (strategy designed for different regime)
            if not result['regime_changed']:
                # Check if current regime is incompatible with activation regime
                if 'TRENDING_UP' in activation_regime and 'RANGING' in str(current_regime):
                    result['regime_changed'] = True
                    result['change_type'] = 'regime_mismatch'
                    result['change_magnitude'] = 1.0
                    result['recommendation'] = 'monitor'  # Will escalate to retire after 30 days
                    result['details'].append(
                        f"Strategy designed for {activation_regime} but market is {current_regime}"
                    )
                    logger.info(f"  ℹ Regime mismatch: {activation_regime} → {current_regime}")

                elif 'RANGING' in activation_regime and 'TRENDING' in str(current_regime):
                    result['regime_changed'] = True
                    result['change_type'] = 'regime_mismatch'
                    result['change_magnitude'] = 1.0
                    result['recommendation'] = 'monitor'  # Will escalate to retire after 30 days
                    result['details'].append(
                        f"Strategy designed for {activation_regime} but market is {current_regime}"
                    )
                    logger.info(f"  ℹ Regime mismatch: {activation_regime} → {current_regime}")

            # Log summary
            if result['regime_changed']:
                logger.warning(f"  ✗ Regime change detected: {result['change_type']}")
                logger.warning(f"  → Recommendation: {result['recommendation']}")
                for detail in result['details']:
                    logger.warning(f"    - {detail}")
            else:
                logger.info(f"  ✓ No significant regime change detected")

            return result

        except Exception as e:
            logger.error(f"Error detecting regime change: {e}")
            return {
                'regime_changed': False,
                'current_regime': 'UNKNOWN',
                'change_type': None,
                'change_magnitude': 0.0,
                'current_metrics': {},
                'activation_metrics': activation_metrics,
                'recommendation': None,
                'details': [f"Error: {str(e)}"]
            }

