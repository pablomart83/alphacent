"""
Indicator Library for Technical Analysis

Provides 10 essential technical indicators with caching for performance optimization.
All calculations use pandas for efficient vectorized operations.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass
import hashlib
import json
import threading

logger = logging.getLogger(__name__)


@dataclass
class CacheKey:
    """Represents a cache key for indicator results."""
    symbol: str
    indicator: str
    params: str  # JSON string of parameters
    
    def __hash__(self):
        return hash((self.symbol, self.indicator, self.params))
    
    def __eq__(self, other):
        if not isinstance(other, CacheKey):
            return False
        return (self.symbol == other.symbol and 
                self.indicator == other.indicator and 
                self.params == other.params)


class IndicatorLibrary:
    """
    Comprehensive library of technical indicators with caching.
    
    Supports 10 essential indicators:
    - SMA (Simple Moving Average)
    - EMA (Exponential Moving Average)
    - RSI (Relative Strength Index)
    - MACD (Moving Average Convergence Divergence)
    - Bollinger Bands
    - ATR (Average True Range)
    - Volume MA
    - Price Change % (for momentum)
    - Support/Resistance (simple high/low)
    - Stochastic Oscillator
    """
    
    def __init__(self):
        """Initialize indicator library with empty cache."""
        self._cache: Dict[CacheKey, pd.Series] = {}
        self._cache_lock = threading.Lock()
        
    def calculate(self, indicator_name: str, data: pd.DataFrame, 
                  symbol: str = "UNKNOWN", **params) -> tuple[pd.Series, str]:
        """
        Calculate indicator on data with caching.
        
        Args:
            indicator_name: Name of indicator (e.g., "SMA", "RSI")
            data: OHLCV DataFrame with columns: open, high, low, close, volume
            symbol: Symbol identifier for caching
            **params: Indicator-specific parameters
            
        Returns:
            Tuple of (calculated indicator values as pandas Series, standardized key name)
            Key format: {INDICATOR}_{PERIOD} (e.g., "SMA_20", "RSI_14")
            
        Raises:
            ValueError: If indicator name is not recognized
        """
        # Create cache key
        params_str = json.dumps(params, sort_keys=True)
        cache_key = CacheKey(symbol=symbol, indicator=indicator_name, params=params_str)
        
        # Generate standardized indicator key name
        standardized_key = self._get_standardized_key(indicator_name, params)
        
        # Check cache (thread-safe)
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key], standardized_key
        
        # Calculate indicator (outside lock — this is the expensive part)
        indicator_method = self._get_indicator_method(indicator_name)
        result = indicator_method(data, **params)
        
        # Store in cache (thread-safe)
        with self._cache_lock:
            self._cache[cache_key] = result
        
        return result, standardized_key
    
    def _get_standardized_key(self, indicator_name: str, params: Dict[str, Any]) -> str:
        """
        Generate standardized key name for indicator.
        
        Format: {INDICATOR}_{PERIOD} (e.g., "SMA_20", "RSI_14")
        For indicators without period, use default parameter.
        
        Args:
            indicator_name: Name of indicator
            params: Indicator parameters
            
        Returns:
            Standardized key name
        """
        indicator_upper = indicator_name.upper()
        
        # Map indicator to its primary parameter
        if indicator_upper in ['SMA', 'EMA', 'RSI', 'ATR', 'VOLUME_MA', 'SUPPORT_RESISTANCE', 'ADX', 'STDDEV', 'VWAP']:
            period = params.get('period', self._get_default_period(indicator_upper))
            return f"{indicator_upper}_{period}"
        elif indicator_upper in ['STOCH', 'STOCH_SIGNAL']:
            # Stochastic uses k_period, not period
            period = params.get('k_period', params.get('period', self._get_default_period(indicator_upper)))
            return f"{indicator_upper}_{period}"
        elif indicator_upper in ['HIGH_N', 'LOW_N']:
            period = params.get('period', 20)
            # Return HIGH_20 / LOW_20 (not HIGH_N_20) to match DSL expectations
            prefix = indicator_upper.replace('_N', '')
            return f"{prefix}_{period}"
        elif indicator_upper == 'OBV':
            # OBV is cumulative — no period. Return bare key.
            return 'OBV'
        elif indicator_upper == 'OBV_MA':
            period = params.get('period', 20)
            return f"OBV_MA_{period}"
        elif indicator_upper in ['DONCHIAN_UPPER', 'DONCHIAN_LOWER']:
            period = params.get('period', 20)
            return f"{indicator_upper}_{period}"
        elif indicator_upper == 'KELTNER':
            # Multi-output indicator; keys will be KELTNER_UPPER_{ema}_{atr}_{mult},
            # _MIDDLE_, _LOWER_. Return the "family" prefix; the caller handles the
            # dict-return pattern (same as BBANDS / MACD).
            ema_p = params.get('ema_period', 20)
            atr_p = params.get('atr_period', 14)
            mult = params.get('mult', 2.0)
            return f"KELTNER_{ema_p}_{atr_p}_{float(mult)}"
        elif indicator_upper == 'MACD':
            fast = params.get('fast_period', 12)
            slow = params.get('slow_period', 26)
            signal = params.get('signal_period', 9)
            return f"MACD_{fast}_{slow}_{signal}"
        elif indicator_upper == 'BBANDS':
            period = params.get('period', 20)
            std_dev = params.get('std_dev', 2)
            return f"BBANDS_{period}_{std_dev}"
        elif indicator_upper == 'PRICE_CHANGE_PCT':
            period = params.get('period', 1)
            return f"PRICE_CHANGE_PCT_{period}"
        else:
            # Fallback for unknown indicators
            return indicator_upper
    
    def _get_default_period(self, indicator_name: str) -> int:
        """Get default period for an indicator."""
        defaults = {
            'SMA': 20,
            'EMA': 20,
            'RSI': 14,
            'ATR': 14,
            'VOLUME_MA': 20,
            'SUPPORT_RESISTANCE': 20,
            'STOCH': 14,
            'ADX': 14,
            'VWAP': 0,
        }
        return defaults.get(indicator_name, 20)
    
    def _get_indicator_method(self, indicator_name: str):
        """Get the calculation method for an indicator."""
        indicator_map = {
            'SMA': self._calculate_sma,
            'STDDEV': self._calculate_stddev,
            'EMA': self._calculate_ema,
            'RSI': self._calculate_rsi,
            'MACD': self._calculate_macd,
            'BBANDS': self._calculate_bollinger_bands,
            'ATR': self._calculate_atr,
            'VOLUME_MA': self._calculate_volume_ma,
            'PRICE_CHANGE_PCT': self._calculate_price_change_pct,
            'SUPPORT_RESISTANCE': self._calculate_support_resistance,
            'STOCH': self._calculate_stochastic,
            'STOCH_SIGNAL': self._calculate_stochastic_signal,
            'HIGH_N': self._calculate_rolling_high,
            'LOW_N': self._calculate_rolling_low,
            'ADX': self._calculate_adx,
            'VWAP': self._calculate_vwap,
            # Added 2026-05-02 Sprint 2 crypto-alpha templates — no approximations
            'OBV': self._calculate_obv,
            'OBV_MA': self._calculate_obv_ma,
            'DONCHIAN_UPPER': self._calculate_donchian_upper,
            'DONCHIAN_LOWER': self._calculate_donchian_lower,
            'KELTNER': self._calculate_keltner,
        }
        
        if indicator_name.upper() not in indicator_map:
            raise ValueError(f"Unknown indicator: {indicator_name}. "
                           f"Available: {list(indicator_map.keys())}")
        
        return indicator_map[indicator_name.upper()]
    
    def clear_cache(self, symbol: Optional[str] = None):
        """
        Clear indicator cache.
        
        Args:
            symbol: If provided, only clear cache for this symbol.
                   If None, clear entire cache.
        """
        with self._cache_lock:
            if symbol is None:
                self._cache.clear()
            else:
                keys_to_remove = [k for k in self._cache.keys() if k.symbol == symbol]
                for key in keys_to_remove:
                    del self._cache[key]
    
    def list_indicators(self) -> list:
        """Return list of available indicators."""
        return [
            'SMA', 'STDDEV', 'EMA', 'RSI', 'MACD', 'BBANDS', 'ATR',
            'VOLUME_MA', 'PRICE_CHANGE_PCT', 'SUPPORT_RESISTANCE', 'STOCH', 'ADX', 'VWAP',
            'OBV', 'OBV_MA', 'DONCHIAN_UPPER', 'DONCHIAN_LOWER', 'KELTNER',
        ]
    
    def get_indicator_info(self, name: str) -> Dict[str, Any]:
        """
        Get metadata about an indicator.
        
        Args:
            name: Indicator name
            
        Returns:
            Dictionary with description and parameters
        """
        info_map = {
            'SMA': {
                'description': 'Simple Moving Average',
                'parameters': {'period': 'int (default: 20)'}
            },
            'STDDEV': {
                'description': 'Standard Deviation',
                'parameters': {'period': 'int (default: 20)'}
            },
            'EMA': {
                'description': 'Exponential Moving Average',
                'parameters': {'period': 'int (default: 20)'}
            },
            'RSI': {
                'description': 'Relative Strength Index',
                'parameters': {'period': 'int (default: 14)'}
            },
            'MACD': {
                'description': 'Moving Average Convergence Divergence',
                'parameters': {
                    'fast_period': 'int (default: 12)',
                    'slow_period': 'int (default: 26)',
                    'signal_period': 'int (default: 9)'
                }
            },
            'BBANDS': {
                'description': 'Bollinger Bands',
                'parameters': {
                    'period': 'int (default: 20)',
                    'std_dev': 'float (default: 2.0)'
                }
            },
            'ATR': {
                'description': 'Average True Range',
                'parameters': {'period': 'int (default: 14)'}
            },
            'VOLUME_MA': {
                'description': 'Volume Moving Average',
                'parameters': {'period': 'int (default: 20)'}
            },
            'PRICE_CHANGE_PCT': {
                'description': 'Price Change Percentage',
                'parameters': {'period': 'int (default: 1)'}
            },
            'SUPPORT_RESISTANCE': {
                'description': 'Support and Resistance Levels',
                'parameters': {'period': 'int (default: 20)'}
            },
            'STOCH': {
                'description': 'Stochastic Oscillator',
                'parameters': {
                    'k_period': 'int (default: 14)',
                    'd_period': 'int (default: 3)'
                }
            },
            'ADX': {
                'description': 'Average Directional Index (trend strength)',
                'parameters': {'period': 'int (default: 14)'}
            }
        }
        
        return info_map.get(name.upper(), {'description': 'Unknown', 'parameters': {}})
    
    # ==================== Indicator Calculations ====================
    
    def _calculate_sma(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Simple Moving Average.
        
        Args:
            data: OHLCV DataFrame
            period: Number of periods for moving average
            
        Returns:
            SMA values
        """
        return data['close'].rolling(window=period).mean()

    def _calculate_stddev(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Standard Deviation of close prices.

        Args:
            data: OHLCV DataFrame
            period: Number of periods for standard deviation

        Returns:
            Standard deviation values
        """
        return data['close'].rolling(window=period).std()

    
    def _calculate_ema(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Exponential Moving Average.
        
        Args:
            data: OHLCV DataFrame
            period: Number of periods for moving average
            
        Returns:
            EMA values
        """
        return data['close'].ewm(span=period, adjust=False).mean()
    
    def _calculate_rsi(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index.
        
        Args:
            data: OHLCV DataFrame
            period: Number of periods for RSI calculation
            
        Returns:
            RSI values (0-100)
        """
        close = data['close']
        delta = close.diff()
        
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_macd(self, data: pd.DataFrame, 
                       fast_period: int = 12,
                       slow_period: int = 26,
                       signal_period: int = 9) -> Dict[str, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        Returns dict with MACD line, signal line, and histogram.
        
        Args:
            data: OHLCV DataFrame
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period
            
        Returns:
            Dict with keys: 'macd', 'signal', 'histogram'
        """
        close = data['close']
        fast_ema = close.ewm(span=fast_period, adjust=False).mean()
        slow_ema = close.ewm(span=slow_period, adjust=False).mean()
        
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def _calculate_bollinger_bands(self, data: pd.DataFrame,
                                   period: int = 20,
                                   std_dev: float = 2.0) -> Dict[str, pd.Series]:
        """
        Calculate Bollinger Bands (upper, middle, lower).
        
        Args:
            data: OHLCV DataFrame
            period: Number of periods for moving average
            std_dev: Number of standard deviations for bands
            
        Returns:
            Dictionary with 'upper', 'middle', 'lower' bands
        """
        close = data['close']
        middle_band = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper_band = middle_band + (std_dev * std)
        lower_band = middle_band - (std_dev * std)
        
        return {
            'upper': upper_band,
            'middle': middle_band,
            'lower': lower_band
        }
    
    def _calculate_atr(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range.
        
        Args:
            data: OHLCV DataFrame
            period: Number of periods for ATR calculation
            
        Returns:
            ATR values
        """
        high = data['high']
        low = data['low']
        close = data['close']
        
        # True Range calculation
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR is the moving average of True Range
        atr = true_range.rolling(window=period).mean()
        
        return atr
    
    def _calculate_volume_ma(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Volume Moving Average.
        
        Args:
            data: OHLCV DataFrame
            period: Number of periods for moving average
            
        Returns:
            Volume MA values
        """
        return data['volume'].rolling(window=period).mean()
    
    def _calculate_price_change_pct(self, data: pd.DataFrame, period: int = 1) -> pd.Series:
        """
        Calculate Price Change Percentage.
        
        Args:
            data: OHLCV DataFrame
            period: Number of periods to look back
            
        Returns:
            Price change percentage values
        """
        close = data['close']
        price_change_pct = ((close - close.shift(period)) / close.shift(period)) * 100
        
        return price_change_pct
    
    def _calculate_support_resistance(self, data: pd.DataFrame, period: int = 20) -> Dict[str, pd.Series]:
            """
            Calculate Support and Resistance levels using rolling window approach.

            Support = rolling minimum of low prices over period
            Resistance = rolling maximum of high prices over period

            Args:
                data: OHLCV DataFrame
                period: Number of periods for rolling high/low (default: 20)

            Returns:
                Dictionary with 'support' and 'resistance' levels
            """
            # Calculate support as rolling minimum of lows
            support = data['low'].rolling(window=period).min()

            # Calculate resistance as rolling maximum of highs
            resistance = data['high'].rolling(window=period).max()

            # Log support/resistance ranges for debugging
            valid_support = support.dropna()
            valid_resistance = resistance.dropna()

            if len(valid_support) > 0 and len(valid_resistance) > 0:
                logger.debug(
                    f"Support/Resistance calculated (period={period}): "
                    f"Support range ${valid_support.min():.2f}-${valid_support.max():.2f}, "
                    f"Resistance range ${valid_resistance.min():.2f}-${valid_resistance.max():.2f}, "
                    f"Valid values: {len(valid_support)}/{len(support)}"
                )

            return {
                'support': support,
                'resistance': resistance
            }
    
    def _calculate_stochastic(self, data: pd.DataFrame,
                             k_period: int = 14,
                             d_period: int = 3) -> pd.Series:
        """
        Calculate Stochastic Oscillator (%K).
        
        %K = (Current Close - Lowest Low) / (Highest High - Lowest Low) * 100
        
        Args:
            data: OHLCV DataFrame
            k_period: Number of periods for %K calculation
            d_period: Number of periods for %D smoothing (not returned)
            
        Returns:
            %K values (0-100)
        """
        close = data['close']
        low = data['low']
        high = data['high']
        
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        
        stoch_k = ((close - lowest_low) / (highest_high - lowest_low)) * 100
        
        return stoch_k
    
    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average Directional Index (ADX).
        
        ADX measures trend strength (0-100):
        - ADX < 20: Weak or no trend
        - ADX 20-25: Emerging trend
        - ADX 25-50: Strong trend
        - ADX > 50: Very strong trend
        
        Args:
            data: OHLCV DataFrame with high, low, close
            period: Number of periods for ADX calculation
            
        Returns:
            ADX values (0-100)
        """
        high = data['high']
        low = data['low']
        close = data['close']
        
        # Calculate True Range (TR)
        high_low = high - low
        high_close = (high - close.shift(1)).abs()
        low_close = (low - close.shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        # Calculate Directional Movement (+DM and -DM)
        high_diff = high - high.shift(1)
        low_diff = low.shift(1) - low
        
        plus_dm = pd.Series(0.0, index=data.index)
        minus_dm = pd.Series(0.0, index=data.index)
        
        plus_dm[high_diff > low_diff] = high_diff[high_diff > low_diff]
        plus_dm[plus_dm < 0] = 0
        
        minus_dm[low_diff > high_diff] = low_diff[low_diff > high_diff]
        minus_dm[minus_dm < 0] = 0
        
        # Smooth TR, +DM, -DM using Wilder's smoothing (exponential moving average)
        atr = tr.ewm(span=period, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
        minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
        
        # Calculate DX (Directional Index)
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        dx = dx.fillna(0)
        
        # Calculate ADX (smoothed DX)
        adx = dx.ewm(span=period, adjust=False).mean()
        
        return adx
    def _calculate_stochastic_signal(self, data: pd.DataFrame,
                                     k_period: int = 14,
                                     d_period: int = 3) -> pd.Series:
        """Calculate Stochastic %D (signal line) — SMA of %K."""
        stoch_k = self._calculate_stochastic(data, k_period=k_period, d_period=d_period)
        return stoch_k.rolling(window=d_period).mean()

    def _calculate_rolling_high(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate rolling highest high over N periods."""
        return data['high'].rolling(window=period).max()

    def _calculate_rolling_low(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate rolling lowest low over N periods."""
        return data['low'].rolling(window=period).min()

    def _calculate_vwap(self, data: pd.DataFrame, period: int = 0) -> pd.Series:
        """
        Calculate Volume Weighted Average Price (VWAP).
        
        VWAP = cumulative(typical_price × volume) / cumulative(volume)
        where typical_price = (high + low + close) / 3
        
        Resets daily (groups by date). For crypto (24/7), resets at midnight UTC.
        For stocks, resets at market open (first bar of each day).
        
        If period > 0, uses a rolling window instead of daily reset
        (useful for multi-day VWAP on higher timeframes).
        
        Args:
            data: OHLCV DataFrame with DatetimeIndex
            period: If 0, use daily reset VWAP. If > 0, use rolling window.
            
        Returns:
            VWAP values as pd.Series
        """
        typical_price = (data['high'] + data['low'] + data['close']) / 3.0
        tp_volume = typical_price * data['volume']
        
        if period > 0:
            # Rolling VWAP (no daily reset)
            cum_tp_vol = tp_volume.rolling(window=period).sum()
            cum_vol = data['volume'].rolling(window=period).sum()
            vwap = cum_tp_vol / cum_vol
        else:
            # Daily reset VWAP — group by date, cumulative within each day
            dates = data.index.date if hasattr(data.index, 'date') else data.index.map(lambda x: x.date() if hasattr(x, 'date') else x)
            cum_tp_vol = tp_volume.groupby(dates).cumsum()
            cum_vol = data['volume'].groupby(dates).cumsum()
            vwap = cum_tp_vol / cum_vol
        
        # Handle division by zero (no volume bars)
        vwap = vwap.replace([np.inf, -np.inf], np.nan).ffill()
        
        return vwap


    def _calculate_obv(self, data: pd.DataFrame, period: int = 0) -> pd.Series:
        """
        Calculate On-Balance Volume (OBV).

        OBV is a cumulative indicator: on each bar, add the volume if close
        went up relative to the previous bar, subtract it if close went down,
        unchanged if close was flat.

            OBV_t = OBV_{t-1} + sign(close_t - close_{t-1}) × volume_t

        `period` is ignored (OBV is cumulative and has no window). Included
        for signature consistency with the indicator library dispatcher.

        Args:
            data: OHLCV DataFrame. Must have 'close' and 'volume'.
            period: Ignored. Accepted for dispatcher compatibility.

        Returns:
            Cumulative OBV values as pd.Series aligned to data.index.
        """
        close_diff = data['close'].diff()
        signed_vol = np.where(
            close_diff > 0, data['volume'],
            np.where(close_diff < 0, -data['volume'], 0.0)
        )
        obv = pd.Series(signed_vol, index=data.index).cumsum()
        return obv

    def _calculate_obv_ma(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate the moving average of OBV.

        Used as a signal line — rising OBV > OBV_MA indicates accumulation;
        falling OBV < OBV_MA indicates distribution. OBV divergence vs price
        is expressed in the DSL as `OBV > OBV_MA(20) AND CLOSE < LOW_N(20)`
        (price new low, OBV not).

        Args:
            data: OHLCV DataFrame.
            period: Rolling window length (bars). Default 20.

        Returns:
            OBV rolling mean as pd.Series.
        """
        obv = self._calculate_obv(data)
        return obv.rolling(window=period).mean()

    def _calculate_donchian_upper(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Donchian Channel upper band.

        Canonical turtle-style definition: the highest HIGH over the prior N
        bars EXCLUDING the current bar (shift=1). This is the breakout
        threshold: a close above `DONCHIAN_UPPER(20)` means the current bar
        printed a higher high than any of the previous 20 bars.

        Difference from `HIGH_N(20)`: `HIGH_N` includes the current bar
        (no shift), so `close > HIGH_N(20)` is tautological once the high
        of the current bar reaches close. Donchian with shift=1 is the
        correct math for trend-breakout signals.

        Args:
            data: OHLCV DataFrame. Needs 'high'.
            period: Lookback bars. Default 20 (Donchian's original).

        Returns:
            pd.Series of the rolling max of HIGH over the prior N bars.
        """
        return data['high'].rolling(window=period).max().shift(1)

    def _calculate_donchian_lower(self, data: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Donchian Channel lower band.

        Mirror of `_calculate_donchian_upper`. Lowest LOW over the prior N
        bars excluding the current bar.

        Args:
            data: OHLCV DataFrame. Needs 'low'.
            period: Lookback bars. Default 20.

        Returns:
            pd.Series of the rolling min of LOW over the prior N bars.
        """
        return data['low'].rolling(window=period).min().shift(1)

    def _calculate_keltner(
        self,
        data: pd.DataFrame,
        ema_period: int = 20,
        atr_period: int = 14,
        mult: float = 2.0,
    ) -> Dict[str, pd.Series]:
        """
        Calculate Keltner Channels.

            KELTNER_MID    = EMA(close, ema_period)
            KELTNER_UPPER  = KELTNER_MID + mult × ATR(atr_period)
            KELTNER_LOWER  = KELTNER_MID - mult × ATR(atr_period)

        Keltner channels are conceptually similar to Bollinger Bands but use
        ATR (average true range) for width instead of standard deviation.
        This makes the channel adapt to the real trading range of the
        instrument rather than to close-price dispersion alone — catches
        real breakouts and squeezes in instruments with gappy bars (crypto
        overnight, commodities over weekend) more accurately than BB.

        Canonical parameters (Alpha Architect backtest): EMA(20), ATR(14),
        mult=2.0.

        Args:
            data: OHLCV DataFrame.
            ema_period: Moving-average period for the midline.
            atr_period: ATR period for band width.
            mult: ATR multiplier for band distance.

        Returns:
            Dict with keys 'upper', 'middle', 'lower', each a pd.Series.
        """
        middle = data['close'].ewm(span=ema_period, adjust=False).mean()
        atr = self._calculate_atr(data, period=atr_period)
        upper = middle + mult * atr
        lower = middle - mult * atr
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
        }
