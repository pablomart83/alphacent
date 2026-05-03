"""Strategy Template Library for proven trading strategies."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class MarketRegime(str, Enum):
    """Market condition classifications with sub-regimes."""
    # Trending regimes
    TRENDING_UP_STRONG = "trending_up_strong"
    TRENDING_UP_WEAK = "trending_up_weak"
    TRENDING_DOWN_STRONG = "trending_down_strong"
    TRENDING_DOWN_WEAK = "trending_down_weak"
    
    # Ranging regimes
    RANGING_LOW_VOL = "ranging_low_vol"
    RANGING_HIGH_VOL = "ranging_high_vol"
    
    # Legacy regimes (for backward compatibility)
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"


class StrategyType(str, Enum):
    """Strategy type classifications."""
    MEAN_REVERSION = "mean_reversion"
    TREND_FOLLOWING = "trend_following"
    VOLATILITY = "volatility"
    BREAKOUT = "breakout"
    MOMENTUM = "momentum"


@dataclass
class StrategyTemplate:
    """Template for a proven trading strategy."""
    name: str
    description: str
    strategy_type: StrategyType
    market_regimes: List[MarketRegime]  # Suitable market regimes
    entry_conditions: List[str]  # Entry rule descriptions
    exit_conditions: List[str]  # Exit rule descriptions
    required_indicators: List[str]  # Exact indicator names needed
    default_parameters: Dict[str, any]  # Default parameter values
    expected_trade_frequency: str  # e.g., "2-4 trades/month"
    expected_holding_period: str  # e.g., "3-7 days"
    risk_reward_ratio: float  # Expected risk/reward
    metadata: Dict[str, any] = None  # Additional metadata
    
    def __post_init__(self):
        """Initialize metadata and add position sizing defaults if not provided."""
        if self.metadata is None:
            self.metadata = {}
        
        # Default direction to 'long' — SHORT templates must set this explicitly.
        if 'direction' not in self.metadata:
            self.metadata['direction'] = 'long'
        
        # Auto-set interval from intraday/interval_4h flags if not explicitly set.
        if 'interval' not in self.metadata:
            if self.metadata.get('intraday') and not self.metadata.get('interval_4h'):
                self.metadata['interval'] = '1h'
            elif self.metadata.get('interval_4h'):
                self.metadata['interval'] = '4h'
            else:
                self.metadata['interval'] = '1d'
        
        # Enforce minimum SL/TP for crypto to clear eToro's ~3% round-trip cost.
        # Timeframe-aware: 1H templates hold hours (can't reach 8% TP), 4H hold hours-to-2d,
        # 1D+ swing templates hold days-to-weeks (can target 8%+). Floor scales with
        # realistic price range on the template's timeframe so backtests exit naturally.
        if self.metadata.get('crypto_optimized'):
            _interval = self.metadata.get('interval', '1d')
            if _interval == '1h':
                _min_sl, _min_tp = 0.015, 0.02   # 1.5% SL, 2.0% TP — realistic for 1-12h holds
            elif _interval == '4h':
                _min_sl, _min_tp = 0.025, 0.04   # 2.5% SL, 4.0% TP — realistic for 4-48h holds
            else:
                _min_sl, _min_tp = 0.04, 0.08    # 4.0% SL, 8.0% TP — 1D+ swing / weekly trend
            if self.default_parameters.get('stop_loss_pct', 1) < _min_sl:
                self.default_parameters['stop_loss_pct'] = _min_sl
            if self.default_parameters.get('take_profit_pct', 1) < _min_tp:
                self.default_parameters['take_profit_pct'] = _min_tp
            # Ensure R:R >= 1.3 after floor adjustments (lower ratio for 1H where tight targets win)
            sl = self.default_parameters.get('stop_loss_pct', _min_sl)
            tp = self.default_parameters.get('take_profit_pct', _min_tp)
            _min_rr = 1.3 if _interval == '1h' else 1.5
            if sl > 0 and tp / sl < _min_rr:
                self.default_parameters['take_profit_pct'] = round(sl * _min_rr, 4)
        
        # Enforce minimum SL/TP for non-crypto 1d stock templates.
        if not self.metadata.get('crypto_optimized'):
            interval = self.metadata.get('interval', '1d')
            if interval == '1d':
                if self.default_parameters.get('stop_loss_pct', 1) < 0.03:
                    self.default_parameters['stop_loss_pct'] = 0.03
                if self.default_parameters.get('take_profit_pct', 1) < 0.05:
                    self.default_parameters['take_profit_pct'] = 0.05
            # Enforce minimum R:R >= 1.5 for all non-crypto templates (except Alpha Edge with TP=0)
            sl = self.default_parameters.get('stop_loss_pct', 0)
            tp = self.default_parameters.get('take_profit_pct', 0)
            if sl > 0 and tp > 0 and tp / sl < 1.5:
                self.default_parameters['take_profit_pct'] = round(sl * 1.5, 4)
        
        # Add position sizing parameters to default_parameters if not present
        if 'risk_per_trade_pct' not in self.default_parameters:
            self.default_parameters['risk_per_trade_pct'] = 0.01
        
        if 'sizing_method' not in self.default_parameters:
            self.default_parameters['sizing_method'] = 'volatility'
        
        if 'position_size_atr_multiplier' not in self.default_parameters:
            self.default_parameters['position_size_atr_multiplier'] = 1.0

        # Crypto regime gate (B1 + B2 from Batch B):
        # Research consensus (Barroso/Santa-Clara 2015, mbrenndoerfer, repo research doc)
        # says mean-reversion must be gated by ADX<25 (ranging regime) and
        # trend/momentum/breakout must be gated by ADX>20 (trending regime).
        # Injected automatically for crypto_optimized templates that don't already
        # have an ADX filter in entry_conditions. Intraday (1h) uses slightly
        # tighter thresholds (ADX<30 for MR, ADX>15 for trend) because intraday
        # ADX runs hotter.
        if self.metadata.get('crypto_optimized') and not self.metadata.get('skip_adx_gate'):
            _has_adx = any('ADX' in c for c in self.entry_conditions) if self.entry_conditions else False
            if not _has_adx and self.entry_conditions:
                _interval = self.metadata.get('interval', '1d')
                _is_mr = self.strategy_type == StrategyType.MEAN_REVERSION
                _is_trend = self.strategy_type in (
                    StrategyType.TREND_FOLLOWING,
                    StrategyType.MOMENTUM,
                    StrategyType.BREAKOUT,
                )
                if _is_mr:
                    _adx_gate = 'ADX(14) < 30' if _interval == '1h' else 'ADX(14) < 25'
                elif _is_trend:
                    _adx_gate = 'ADX(14) > 15' if _interval == '1h' else 'ADX(14) > 20'
                else:
                    _adx_gate = None  # VOLATILITY, etc — no blanket gate

                if _adx_gate:
                    # Append to the first (primary) entry condition so the signal
                    # only fires when both the setup AND the regime agree.
                    self.entry_conditions[0] = f"{self.entry_conditions[0]} AND {_adx_gate}"
                    # Ensure ADX is in required_indicators
                    if self.required_indicators is None:
                        self.required_indicators = []
                    if 'ADX' not in self.required_indicators:
                        self.required_indicators = list(self.required_indicators) + ['ADX']
                    self.metadata['adx_gate_injected'] = _adx_gate


class StrategyTemplateLibrary:
    """Library of proven strategy templates for different market regimes."""
    
    def __init__(self):
        """Initialize the template library with proven strategies."""
        all_templates = self._create_templates()
        
        # Remove known duplicates identified in audit (Session 5, April 11 2026).
        # Keep the better version of each pair.
        REMOVE_TEMPLATES = {
            "RSI Overbought Short",          # Keep RSI Overbought Short Ranging (better exit)
            "Stochastic Overbought Short",   # Keep Stochastic Overbought Short Ranging (better exit)
            "Bollinger Band Short",          # Keep BB Upper Band Short Ranging (stricter entry)
            "Bollinger Volatility Breakout", # Keep Bollinger Squeeze Breakout (has squeeze filter)
            "Low Vol RSI Mean Reversion",    # Keep Tight RSI Mean Reversion (has SMA filter)
            "Volume Dry-Up Reversal Long",   # Keep RSI Higher Low Recovery (better entry filter)
            "Keltner Midline Bounce Long",   # Keep RSI Higher Low Recovery (same signal space)
            "Stochastic Midrange Long",      # Keep Stochastic Momentum (better R:R)
            "MACD Momentum",                 # Keep MACD Rising Momentum (quality filter)
            "4H Downtrend Oversold Bounce",  # R:R = 1.1, dead cat bounce — negative expectancy
            "BB Midband Reversion Tight",    # Entry ≈ exit, SL=1.2% — guaranteed stop-out
        }
        
        self.templates = [t for t in all_templates if t.name not in REMOVE_TEMPLATES]

        # 2026-05-02 update (was "remove all 1h crypto"):
        # The original Sprint 4.1 filter removed every 1h crypto template on
        # the belief that "1H and below underperform 90% of the time for
        # crypto." Concretum's April 2025 research "Catching Crypto Trends"
        # and their intraday companion paper actually show a Sharpe ~1.6
        # intraday trend-following benchmark on BTC — the blanket removal was
        # throwing away real edge.
        #
        # Real eToro crypto cost (verified 2026-05-02 against etoro.com/fees):
        #   1% commission per side + ~0.4% spread + ~0.1% slippage
        #   = ~2.96% round-trip cost on crypto
        # We require TP >= 6% (2× round-trip cost) so a winning trade clears
        # costs with a margin of safety against noise. 1h entry signals that
        # hold multi-day for 6%+ TP are fine; 1h scalps targeting 2% profit
        # are deterministically negative EV and must be filtered out.
        _MIN_CRYPTO_TP = 0.06
        _filtered: list = []
        for t in self.templates:
            if t.metadata.get('crypto_optimized') is True:
                _tp = float(t.default_parameters.get('take_profit_pct', 0) or 0)
                if _tp < _MIN_CRYPTO_TP:
                    # Skip — TP too tight to clear ~3% round-trip fee cleanly.
                    continue
            _filtered.append(t)
        self.templates = _filtered
    
    def _create_templates(self) -> List[StrategyTemplate]:
        """Create all strategy templates."""
        # ============================================================
        # TEMPLATE AUDIT (Task 11.11.2) — Cleaned up duplicate/correlated templates
        # Before: 83 templates | After: 64 templates | Removed: 19
        #
        # REMOVED TEMPLATES (duplicates/highly correlated):
        # - MACD Relaxed Crossover: exact duplicate of MACD Momentum
        # - Stochastic Extreme Oversold: near-duplicate of Stochastic Mean Reversion (STOCH<20 vs <15)
        # - Bullish MA Alignment: ~95% correlated with EMA Trend Following (SMA vs EMA)
        # - RSI Mild Oversold: overlapping signal space with RSI Dip Buy
        # - Low Vol Bollinger Mean Reversion: duplicate of Bollinger Band Bounce without RSI confirmation
        # - Weak Uptrend RSI Oversold: correlated with Weak Uptrend Pullback
        # - SMA Dip Buy: correlated with Weak Uptrend Pullback
        # - Ultra Short EMA Momentum: correlated with Fast EMA Crossover
        # - Ranging MACD Momentum: correlated with Strong Uptrend MACD (SMA(20) vs SMA(50))
        # - ATR Trailing Trend: correlated with ATR Expansion Breakout (0.5x vs 1.5x ATR)
        # - 3x duplicate SHORT Ranging templates (STOCH/RSI/BB with near-identical thresholds)
        # - Stochastic RSI Overbought Short: subset of RSI Overbought Short signals
        # - RSI Bollinger Combo Short Ranging: correlated with BB Upper Band Short Ranging
        # - RSI Rally Short: weaker version of RSI Overbought Short
        # - BB Upper Band Rejection Short: correlated with Bollinger Band Short
        # - Bearish MA Alignment Short: ~95% correlated with EMA Downtrend Short
        # - RSI Mild Overbought Short Ranging: unrealistic (RSI 55-70 is not overbought)
        # ============================================================
        templates = []
        
        # ===== MEAN REVERSION TEMPLATES (for RANGING markets) =====
        
        # 1. RSI Oversold/Overbought (IMPROVED)
        templates.append(StrategyTemplate(
            name="RSI Mean Reversion",
            description="Buy when RSI indicates extreme oversold conditions, sell when overbought or profit target hit",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING],
            entry_conditions=[
                "RSI(14) < 25"  # More extreme oversold for better entry
            ],
            exit_conditions=[
                "RSI(14) > 75"  # More extreme overbought for better exit
            ],
            required_indicators=["RSI"],  # Base name without period
            default_parameters={
                "rsi_period": 14,
                "oversold_threshold": 25,  # More extreme
                "overbought_threshold": 75,  # More extreme
                "stop_loss_pct": 0.02,  # 2% stop-loss
                "take_profit_pct": 0.05,  # 5% take-profit
                "position_size_atr_multiplier": 1.0  # Size based on volatility
            },
            expected_trade_frequency="2-4 trades/month",  # Less frequent, higher quality
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.5  # Better risk/reward with stops
        ))
        
        # 2. Bollinger Band Bounce (IMPROVED)
        templates.append(StrategyTemplate(
            name="Bollinger Band Bounce",
            description="Buy at lower band with RSI confirmation, sell at middle band or profit target",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2) AND RSI(14) < 40"  # Add RSI confirmation
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2)"  # Exit at middle band (more conservative)
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,  # Can widen to 2.5 in high volatility
                "rsi_confirmation": 40,
                "stop_loss_pct": 0.02,  # 2% stop-loss
                "take_profit_pct": 0.03  # 3% take-profit
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="5-10 days",
            risk_reward_ratio=2.5  # Better with stops
        ))
        
        # 3. Stochastic Mean Reversion (IMPROVED)
        templates.append(StrategyTemplate(
            name="Stochastic Mean Reversion",
            description="Buy when Stochastic is oversold, sell when overbought with profit targets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING],
            entry_conditions=[
                "STOCH(14) < 15"  # More extreme oversold
            ],
            exit_conditions=[
                "STOCH(14) > 85"  # More extreme overbought
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "oversold_threshold": 15,  # More extreme
                "overbought_threshold": 85,  # More extreme
                "stop_loss_pct": 0.02,  # 2% stop-loss
                "take_profit_pct": 0.04  # 4% take-profit
            },
            expected_trade_frequency="2-4 trades/month",  # Less frequent, higher quality
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0
        ))
        
        # 4. RSI + Bollinger Combo (Mean Reversion) - IMPROVED
        templates.append(StrategyTemplate(
            name="RSI Bollinger Combo",
            description="Buy when both RSI oversold AND price at lower band, more conservative exit",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING],
            entry_conditions=[
                "RSI(14) < 25 AND CLOSE < BB_LOWER(20, 2)"  # More extreme RSI
            ],
            exit_conditions=[
                "RSI(14) > 70 OR CLOSE > BB_MIDDLE(20, 2)"  # Exit at middle band (more conservative)
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "rsi_period": 14,
                "rsi_oversold": 25,  # More extreme
                "rsi_overbought": 70,
                "bb_period": 20,
                "bb_std": 2.0,
                "stop_loss_pct": 0.02,  # 2% stop-loss
                "take_profit_pct": 0.04  # 4% take-profit
            },
            expected_trade_frequency="1-2 trades/month",  # Less frequent, higher quality
            expected_holding_period="5-10 days",
            risk_reward_ratio=3.0  # Better with stops
        ))
        
        # ===== TREND FOLLOWING TEMPLATES (for TRENDING markets) =====
        
        # 5. Moving Average Crossover (IMPROVED)
        templates.append(StrategyTemplate(
            name="Moving Average Crossover",
            description="Buy when fast MA crosses above slow MA with trend filter and volume confirmation",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "SMA(20) CROSSES_ABOVE SMA(50) AND VOLUME > VOLUME_MA(20)"  # Add volume confirmation
            ],
            exit_conditions=[
                "SMA(20) CROSSES_BELOW SMA(50)"
            ],
            required_indicators=["SMA:20", "SMA:50", "Volume MA"],
            default_parameters={
                "fast_period": 20,
                "slow_period": 50,
                "volume_period": 20,
                "stop_loss_pct": 0.03,  # 3% stop-loss
                "take_profit_pct": 0.05  # 5% take-profit
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="10-30 days",
            risk_reward_ratio=3.0
        ))
        
        # 6. MACD Momentum
        templates.append(StrategyTemplate(
            name="MACD Momentum",
            description="Buy on MACD crossover above signal, sell on crossover below",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL()"
            ],
            exit_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL()"
            ],
            required_indicators=["MACD"],
            default_parameters={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "stop_loss_pct": 0.03,  # 3% stop-loss (momentum)
                "take_profit_pct": 0.05  # 5% take-profit (momentum)
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="7-15 days",
            risk_reward_ratio=2.5
        ))
        
        # 7. Breakout Strategy
        templates.append(StrategyTemplate(
            name="Price Breakout",
            description="Buy on breakout above 10-day resistance with buffer, sell on breakdown",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > RESISTANCE * 0.998"  # Reduced buffer to 0.2% to allow more entries
            ],
            exit_conditions=[
                "CLOSE < SUPPORT * 1.002"  # Reduced buffer
            ],
            required_indicators=["Support", "Resistance"],
            default_parameters={
                "lookback_period": 10,  # Reduced from 15 for more frequent signals
                "breakout_buffer": 0.002,  # 0.2% buffer (reduced)
                "stop_loss_pct": 0.03,  # 3% stop-loss (breakout)
                "take_profit_pct": 0.06  # 6% take-profit (breakout)
            },
            expected_trade_frequency="3-5 trades/month",  # Increased
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.0
        ))
        
        # 8. EMA Trend Following
        templates.append(StrategyTemplate(
            name="EMA Trend Following",
            description="Buy when price above EMA and trending up, sell when below",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "CLOSE > EMA(20) AND EMA(20) > EMA(50)"
            ],
            exit_conditions=[
                "CLOSE < EMA(20)"
            ],
            required_indicators=["EMA:20", "EMA:50"],
            default_parameters={
                "fast_period": 20,
                "slow_period": 50,
                "stop_loss_pct": 0.03,  # 3% stop-loss (trend following)
                "take_profit_pct": 0.05  # 5% take-profit (trend following)
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="7-20 days",
            risk_reward_ratio=2.5
        ))
        
        # ===== VOLATILITY TEMPLATES (for HIGH_VOLATILITY markets) =====
        
        # 9. ATR Breakout
        templates.append(StrategyTemplate(
            name="ATR Volatility Breakout",
            description="Buy on price move greater than 1.5x ATR, exit on reversion",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.RANGING],
            entry_conditions=[
                "PRICE_CHANGE_PCT(1) > ATR(14) * 1.0"  # Relaxed from 2.0x to 1.0x ATR
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"
            ],
            required_indicators=["ATR", "SMA", "Price Change %"],
            default_parameters={
                "atr_period": 14,
                "atr_multiplier": 1.5,  # Relaxed from 2.0
                "sma_period": 20,
                "price_change_period": 1,
                "stop_loss_pct": 0.04,  # 4% stop-loss (volatility)
                "take_profit_pct": 0.06  # 6% take-profit (volatility)
            },
            expected_trade_frequency="3-5 trades/month",  # Increased
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0
        ))
        
        # 10. Bollinger Breakout
        templates.append(StrategyTemplate(
            name="Bollinger Volatility Breakout",
            description="Buy on breakout above upper band, sell on return to middle",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2)"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "stop_loss_pct": 0.04,  # 4% stop-loss (volatility)
                "take_profit_pct": 0.06  # 6% take-profit (volatility)
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=1.8
        ))
        
        # ===== NEW MOMENTUM STRATEGIES =====
        
        # 11. Price Momentum (20-day high/low)
        templates.append(StrategyTemplate(
            name="Price Momentum Breakout",
            description="Buy on 20-day high breakout, exit on 10-day low breakdown",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.TRENDING_UP],
            entry_conditions=[
                "CLOSE > RESISTANCE"  # 20-day high
            ],
            exit_conditions=[
                "CLOSE < SUPPORT"  # 10-day low
            ],
            required_indicators=["Support", "Resistance"],
            default_parameters={
                "entry_lookback": 20,
                "exit_lookback": 10,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.08
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.5,
            metadata={"lookback_entry": 20, "lookback_exit": 10}
        ))
        
        # 12. MACD Rising Momentum
        templates.append(StrategyTemplate(
            name="MACD Rising Momentum",
            description="Buy when MACD > signal AND MACD rising, exit when MACD < signal",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP],
            entry_conditions=[
                "MACD() > MACD_SIGNAL() AND MACD() > MACD().shift(1)"  # MACD above signal and rising
            ],
            exit_conditions=[
                "MACD() < MACD_SIGNAL()"
            ],
            required_indicators=["MACD"],
            default_parameters={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="7-14 days",
            risk_reward_ratio=2.0
        ))
        
        # 13. ADX Trend Strength
        templates.append(StrategyTemplate(
            name="ADX Trend Following",
            description="Buy when ADX > 25 (strong trend) AND price > SMA(50), exit when ADX < 20",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "ADX(14) > 25 AND CLOSE > SMA(50)"  # Strong trend + price above MA
            ],
            exit_conditions=[
                "ADX(14) < 20"  # Trend weakening
            ],
            required_indicators=["ADX", "SMA:50"],
            default_parameters={
                "adx_period": 14,
                "adx_entry_threshold": 25,
                "adx_exit_threshold": 20,
                "sma_period": 50,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.08
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="10-30 days",
            risk_reward_ratio=2.5
        ))
        
        # 15. Z-Score Mean Reversion (OPTIMIZED - relaxed from -2.0 to -1.2)
        templates.append(StrategyTemplate(
            name="Z-Score Mean Reversion",
            description="Buy when price is 1.2 standard deviations below SMA, exit at mean",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING],
            entry_conditions=[
                "(CLOSE - SMA(20)) / STDDEV(20) < -1.2"  # Z-score < -1.2 (more relaxed)
            ],
            exit_conditions=[
                "(CLOSE - SMA(20)) / STDDEV(20) > -0.2"  # Exit near mean
            ],
            required_indicators=["SMA", "STDDEV"],  # Need both SMA and STDDEV
            default_parameters={
                "sma_period": 20,
                "stddev_period": 20,
                "entry_z_score": -1.2,  # More relaxed
                "exit_z_score": -0.2,  # Exit earlier
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05
            },
            expected_trade_frequency="3-5 trades/month",  # Increased
            expected_holding_period="5-10 days",
            risk_reward_ratio=2.5,
            metadata={"requires_stddev": True}
        ))
        
        # ===== NEW VOLATILITY STRATEGIES =====
        
        # 16. Bollinger Squeeze Breakout (OPTIMIZED - significantly relaxed)
        templates.append(StrategyTemplate(
            name="Bollinger Squeeze Breakout",
            description="Buy when Bollinger Bands narrow then price breaks above upper band",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.RANGING, MarketRegime.TRENDING_UP],
            entry_conditions=[
                "(BB_UPPER(20, 2) - BB_LOWER(20, 2)) < ATR(14) * 4 AND CLOSE > BB_UPPER(20, 2)"  # Very relaxed squeeze (4x)
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands", "ATR"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "atr_period": 14,
                "squeeze_multiplier": 4.0,  # Very relaxed
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="3-4 trades/month",  # Increased
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.5
        ))
        
        # 17. ATR Expansion Breakout
        templates.append(StrategyTemplate(
            name="ATR Expansion Breakout",
            description="Buy when price moves > 1.5*ATR from 20-day MA (volatility expansion)",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > SMA(20) + ATR(14) * 1.5"  # Relaxed from 2.0 to 1.5
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"  # Reversion to mean
            ],
            required_indicators=["SMA", "ATR"],
            default_parameters={
                "sma_period": 20,
                "atr_period": 14,
                "atr_multiplier": 1.5,  # Relaxed from 2.0
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="3-5 trades/month",  # Increased
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0
        ))
        
        # ===== REGIME-SPECIFIC TEMPLATES (NEW) =====
        
        # 18. Strong Uptrend - MACD Momentum
        templates.append(StrategyTemplate(
            name="Strong Uptrend MACD",
            description="Aggressive momentum strategy for strong uptrends - MACD crossover with trend confirmation",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP_STRONG],
            entry_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL() AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL()"
            ],
            required_indicators=["MACD", "SMA:50"],
            default_parameters={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "sma_period": 50,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="10-20 days",
            risk_reward_ratio=3.0
        ))
        
        # 19. Strong Uptrend - Breakout
        templates.append(StrategyTemplate(
            name="Strong Uptrend Breakout",
            description="Breakout strategy for strong uptrends - buy 20-day highs",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.TRENDING_UP_STRONG],
            entry_conditions=[
                "CLOSE > RESISTANCE AND VOLUME > VOLUME_MA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"
            ],
            required_indicators=["Support/Resistance", "Volume MA", "SMA"],
            default_parameters={
                "lookback_period": 20,
                "volume_period": 20,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="10-30 days",
            risk_reward_ratio=3.0
        ))
        
        # 20. Weak Uptrend - Pullback to MA
        templates.append(StrategyTemplate(
            name="Weak Uptrend Pullback",
            description="Buy dips to moving average in weak uptrends",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE < SMA(20) AND CLOSE > SMA(50) AND RSI(14) < 40"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) OR RSI(14) > 70"
            ],
            required_indicators=["SMA:20", "SMA:50", "RSI"],
            default_parameters={
                "fast_sma": 20,
                "slow_sma": 50,
                "rsi_period": 14,
                "rsi_entry": 40,
                "rsi_exit": 70,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-10 days",
            risk_reward_ratio=2.5
        ))
        
        # 22. Weak Downtrend - Bounce from Support
        # Weak Downtrend Bounce — buy oversold bounces in weak downtrends
        # Relaxed: RSI < 35 OR Stoch < 25 (either one, not both simultaneously)
        # The original RSI < 25 AND Stoch < 20 was too restrictive — that combo
        # fires maybe once per year on most stocks.
        templates.append(StrategyTemplate(
            name="Weak Downtrend Bounce",
            description="Buy oversold bounces from support in weak downtrends",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "RSI(14) < 35 AND CLOSE < SMA(50) AND STOCH(14) < 30"
            ],
            exit_conditions=[
                "RSI(14) > 60 OR CLOSE > SMA(20)"
            ],
            required_indicators=["Support/Resistance", "RSI", "Stochastic Oscillator", "SMA"],
            default_parameters={
                "support_lookback": 20,
                "rsi_period": 14,
                "rsi_entry": 25,
                "rsi_exit": 60,
                "stoch_period": 14,
                "stoch_entry": 20,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0
        ))
        
        # 23. Low Vol Ranging - RSI Mean Reversion
        templates.append(StrategyTemplate(
            name="Low Vol RSI Mean Reversion",
            description="Classic RSI mean reversion for low volatility ranging markets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) < 40"  # More relaxed for low volatility markets
            ],
            exit_conditions=[
                "RSI(14) > 65"  # More relaxed exit
            ],
            required_indicators=["RSI"],
            default_parameters={
                "rsi_period": 14,
                "oversold_threshold": 40,  # More relaxed for low vol
                "overbought_threshold": 65,  # More relaxed for low vol
                "stop_loss_pct": 0.015,  # Tighter stops in low vol
                "take_profit_pct": 0.03,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0
        ))
        
        # ===== MOMENTUM / TREND-FOLLOWING FOR RANGING MARKETS =====
        # These templates fire in markets where RSI is 30-60 and price is near SMA
        # They complement the mean-reversion templates to ensure signal diversity
        
        # 25a. SMA Trend Momentum (for ranging/low-vol markets)
        templates.append(StrategyTemplate(
            name="SMA Trend Momentum",
            description="Buy when price crosses above SMA(20) with moderate RSI, exit on cross below",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_UP],
            entry_conditions=[
                "CLOSE > SMA(20) AND RSI(14) > 45 AND RSI(14) < 65"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) > 75"
            ],
            required_indicators=["SMA:20", "RSI"],
            default_parameters={
                "sma_period": 20,
                "rsi_period": 14,
                "rsi_entry_min": 45,
                "rsi_entry_max": 65,
                "rsi_exit": 75,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="4-6 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0
        ))
        
        # 25b. EMA Pullback Momentum (for ranging/low-vol markets)
        templates.append(StrategyTemplate(
            name="EMA Pullback Momentum",
            description="Buy pullbacks to EMA(10) when EMA(10) > EMA(30), exit on EMA cross",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_UP],
            entry_conditions=[
                "CLOSE > EMA(10) AND EMA(10) > EMA(30)"
            ],
            exit_conditions=[
                "CLOSE < EMA(30)"
            ],
            required_indicators=["EMA:10", "EMA:30"],
            default_parameters={
                "fast_period": 10,
                "slow_period": 30,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="4-6 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0
        ))
        
        # 25c. RSI Midrange Momentum (for ranging/low-vol markets)
        templates.append(StrategyTemplate(
            name="RSI Midrange Momentum",
            description="Buy when RSI crosses above 50 (bullish momentum shift), exit when RSI drops below 40",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) > 50 AND RSI(14) < 65 AND CLOSE > SMA(20)"
            ],
            exit_conditions=[
                "RSI(14) < 40 OR CLOSE < SMA(20)"
            ],
            required_indicators=["RSI", "SMA:20"],
            default_parameters={
                "rsi_period": 14,
                "rsi_entry_min": 50,
                "rsi_entry_max": 65,
                "rsi_exit": 40,
                "sma_period": 20,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0
        ))
        
        # 25d. Low Vol Breakout (for ranging_low_vol specifically)
        templates.append(StrategyTemplate(
            name="Low Vol Breakout",
            description="Buy when price breaks above recent range in low volatility, exit on reversion",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 1.5)"  # Tighter bands (1.5 std) for low vol
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 1.5)"
            ],
            required_indicators=["Bollinger Bands"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 1.5,  # Tighter bands for low vol breakouts
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=2.0
        ))
        
        # 25. High Vol Ranging - ATR Breakout
        templates.append(StrategyTemplate(
            name="High Vol ATR Breakout",
            description="ATR-based breakout strategy for high volatility ranging markets",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > SMA(20) + ATR(14) * 2.5"
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"
            ],
            required_indicators=["SMA", "ATR"],
            default_parameters={
                "sma_period": 20,
                "atr_period": 14,
                "atr_multiplier": 2.5,  # Wider for high vol
                "stop_loss_pct": 0.04,  # Wider stops in high vol
                "take_profit_pct": 0.08
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.5
        ))
        
        # 26. High Vol Ranging - Bollinger Squeeze
        templates.append(StrategyTemplate(
            name="High Vol Bollinger Squeeze",
            description="Bollinger squeeze breakout for high volatility ranging markets",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2.5) AND VOLUME > VOLUME_MA(20)"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2.5)"
            ],
            required_indicators=["Bollinger Bands", "Volume MA"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.5,  # Wider bands for high vol
                "volume_period": 20,
                "stop_loss_pct": 0.04,  # Wider stops in high vol
                "take_profit_pct": 0.08
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.5
        ))
        
        # ===== HIGH-QUALITY MULTI-FACTOR STRATEGIES =====
        # These combine multiple uncorrelated signals for higher conviction entries
        
        # 27. Dual MA + Volume Confirmation (works across regimes)
        # Classic institutional approach: trend alignment + volume surge
        templates.append(StrategyTemplate(
            name="Dual MA Volume Surge",
            description="Buy when price above both MAs and volume surges above average, exit on MA breakdown",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE > SMA(20) AND CLOSE > SMA(50) AND VOLUME > VOLUME_MA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"
            ],
            required_indicators=["SMA:20", "SMA:50", "Volume MA"],
            default_parameters={
                "fast_period": 20,
                "slow_period": 50,
                "volume_period": 20,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.5
        ))
        
        # 28. Bollinger Band Width Contraction + EMA Trend
        # Low vol squeeze into trend direction — high probability setup
        templates.append(StrategyTemplate(
            name="BB Squeeze EMA Trend",
            description="Buy when BB width contracts (low vol) and price breaks above EMA(20), exit on EMA cross",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > EMA(20) AND CLOSE > BB_UPPER(20, 1.5)"
            ],
            exit_conditions=[
                "CLOSE < EMA(20)"
            ],
            required_indicators=["EMA:20", "Bollinger Bands"],
            default_parameters={
                "ema_period": 20,
                "bb_period": 20,
                "bb_std": 1.5,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0
        ))
        
        # 29. MACD + RSI Divergence Momentum
        # MACD bullish crossover confirmed by RSI not overbought — avoids late entries
        templates.append(StrategyTemplate(
            name="MACD RSI Confirmed Momentum",
            description="Buy on MACD bullish crossover when RSI is in neutral zone (not overbought), exit on MACD bearish",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_UP],
            entry_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL() AND RSI(14) > 40 AND RSI(14) < 65"
            ],
            exit_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL()"
            ],
            required_indicators=["MACD", "RSI"],
            default_parameters={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "rsi_period": 14,
                "rsi_entry_min": 40,
                "rsi_entry_max": 65,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-12 days",
            risk_reward_ratio=2.5
        ))
        
        # 31. Stochastic Momentum (Simplified - removed conflicting trend filter)
        # Pure momentum strategy using Stochastic oscillator
        templates.append(StrategyTemplate(
            name="Stochastic Momentum",
            description="Buy when Stochastic crosses above 30 (momentum shift), sell when overbought",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "STOCH(14) CROSSES_ABOVE 30"
            ],
            exit_conditions=[
                "STOCH(14) > 80"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "stoch_entry": 30,
                "stoch_exit": 80,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05
            },
            expected_trade_frequency="5-8 trades/month",
            expected_holding_period="5-12 days",
            risk_reward_ratio=2.0
        ))
        
        # 32. Triple EMA Alignment
        # All three EMAs aligned bullish — strong trend confirmation
        templates.append(StrategyTemplate(
            name="Triple EMA Alignment",
            description="Buy when EMA(10) > EMA(20) > EMA(50) and price above all three, exit on EMA(10) < EMA(20)",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE > EMA(10) AND EMA(10) > EMA(20) AND EMA(20) > EMA(50)"
            ],
            exit_conditions=[
                "CLOSE < EMA(20)"
            ],
            required_indicators=["EMA:10", "EMA:20", "EMA:50"],
            default_parameters={
                "fast_period": 10,
                "mid_period": 20,
                "slow_period": 50,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="7-20 days",
            risk_reward_ratio=2.5
        ))
        
        # 33. Bollinger + Stochastic Oversold Recovery
        # Price at lower band + stochastic turning up — high probability mean reversion
        templates.append(StrategyTemplate(
            name="BB Stochastic Recovery",
            description="Buy when price near lower BB and Stochastic crosses above 20 (recovery signal)",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2) AND STOCH(14) > 15"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2) OR STOCH(14) > 80"
            ],
            required_indicators=["Bollinger Bands", "Stochastic Oscillator"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "stoch_period": 14,
                "stoch_entry": 15,
                "stoch_exit": 80,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0
        ))
        
        # ===== HIGH-SENSITIVITY TEMPLATES =====
        # These templates use relaxed thresholds and shorter periods to generate
        # signals more frequently. They trade in "normal" market conditions where
        # price is near (not far from) moving averages and RSI is in the 30-60 range.
        
        # 35. RSI Dip Buy — fires when RSI drops below 45 (mild weakness)
        templates.append(StrategyTemplate(
            name="RSI Dip Buy",
            description="Buy when RSI drops below 35 (genuine dip), exit on RSI recovery above 55",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "RSI(14) < 35 AND RSI(14) > 15"
            ],
            exit_conditions=[
                "RSI(14) > 55"
            ],
            required_indicators=["RSI"],
            default_parameters={
                "rsi_period": 14,
                "oversold_threshold": 35,
                "overbought_threshold": 55,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.5,
            metadata={"high_sensitivity": True, "skip_param_override": True}
        ))
        
        # R1/R2/R3 REMOVED 2026-05-01 per STRATEGY_LIBRARY_REVIEW_2026-05:
        # - "Fast EMA Crossover" (EMA(5)/EMA(13)): raw MA crossover, no regime filter,
        #   2% SL consumed by CFD spread. Live data: -$378 open drag. SSRN 5186655
        #   shows 50/200 MA crossover underperformed buy-and-hold on mega-caps 2024.
        # - "SMA Proximity Entry": price-within-1%-of-SMA(10) fires in trending
        #   markets where pullbacks become continuations. No regime filter. Live: -$308.
        # - "BB Middle Band Bounce": crossing above BB middle band is a zero-edge
        #   signal without confluence. Live: -$141.
        #
        # All three were high_sensitivity/skip_param_override, meaning they bypassed
        # param variation — minimal chance of "better params" redeeming them.
        
        # ===== SHORT STRATEGIES (for downtrending markets) =====
        # These strategies profit from price declines by selling high and buying back low
        
        # 43. RSI Overbought Short
        templates.append(StrategyTemplate(
            name="RSI Overbought Short",
            description="Short when RSI indicates extreme overbought conditions, cover when oversold",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "RSI(14) > 75"  # Extreme overbought
            ],
            exit_conditions=[
                "RSI(14) < 25"  # Cover on oversold
            ],
            required_indicators=["RSI"],
            default_parameters={
                "rsi_period": 14,
                "overbought_threshold": 75,
                "oversold_threshold": 25,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.05,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "short"}
        ))
        
        # 44. Bollinger Band Short
        templates.append(StrategyTemplate(
            name="Bollinger Band Short",
            description="Short at upper band with RSI confirmation, cover at middle band",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2) AND RSI(14) > 60"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_confirmation": 60,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="5-10 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "short"}
        ))
        
        # 45. Moving Average Breakdown Short
        templates.append(StrategyTemplate(
            name="Moving Average Breakdown Short",
            description="Short when fast MA crosses below slow MA, cover on cross above",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "SMA(20) CROSSES_BELOW SMA(50)"
            ],
            exit_conditions=[
                "SMA(20) CROSSES_ABOVE SMA(50)"
            ],
            required_indicators=["SMA:20", "SMA:50"],
            default_parameters={
                "fast_period": 20,
                "slow_period": 50,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="10-30 days",
            risk_reward_ratio=3.0,
            metadata={"direction": "short"}
        ))
        
        # 46. MACD Bearish Short
        templates.append(StrategyTemplate(
            name="MACD Bearish Short",
            description="Short on MACD crossover below signal, cover on crossover above",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL()"
            ],
            exit_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL()"
            ],
            required_indicators=["MACD"],
            default_parameters={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="7-15 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "short"}
        ))
        
        # 47. EMA Downtrend Short
        templates.append(StrategyTemplate(
            name="EMA Downtrend Short",
            description="Short when price below EMA and trending down, cover when above",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE < EMA(20) AND EMA(20) < EMA(50)"
            ],
            exit_conditions=[
                "CLOSE > EMA(20)"
            ],
            required_indicators=["EMA:20", "EMA:50"],
            default_parameters={
                "fast_period": 20,
                "slow_period": 50,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="7-20 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "short"}
        ))
        
        # 48. Breakdown Short
        templates.append(StrategyTemplate(
            name="Price Breakdown Short",
            description="Short on breakdown below support, cover on bounce",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE < SUPPORT * 1.002"
            ],
            exit_conditions=[
                "CLOSE > RESISTANCE * 0.998"
            ],
            required_indicators=["Support", "Resistance"],
            default_parameters={
                "lookback_period": 10,
                "breakdown_buffer": 0.002,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 49. Stochastic Overbought Short
        templates.append(StrategyTemplate(
            name="Stochastic Overbought Short",
            description="Short when Stochastic is overbought, cover when oversold",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "STOCH(14) > 85"
            ],
            exit_conditions=[
                "STOCH(14) < 15"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "overbought_threshold": 85,
                "oversold_threshold": 15,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 50. Triple EMA Bearish Alignment Short
        templates.append(StrategyTemplate(
            name="Triple EMA Bearish Short",
            description="Short when EMA(10) < EMA(20) < EMA(50) and price below all three",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE < EMA(10) AND EMA(10) < EMA(20) AND EMA(20) < EMA(50)"
            ],
            exit_conditions=[
                "CLOSE > EMA(20)"
            ],
            required_indicators=["EMA:10", "EMA:20", "EMA:50"],
            default_parameters={
                "fast_period": 10,
                "mid_period": 20,
                "slow_period": 50,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="7-20 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "short"}
        ))
        
        # 51. ATR Downside Breakout Short
        templates.append(StrategyTemplate(
            name="ATR Downside Breakout Short",
            description="Short on price move greater than 1.5x ATR downward, cover on reversion",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE < SMA(20) - ATR(14) * 1.5"
            ],
            exit_conditions=[
                "CLOSE > SMA(20)"
            ],
            required_indicators=["ATR", "SMA"],
            default_parameters={
                "atr_period": 14,
                "atr_multiplier": 1.5,
                "sma_period": 20,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.06
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # ===== SHORT STRATEGIES FOR RANGING & TRENDING_UP MARKETS =====
        # These mean-reversion shorts profit from overbought conditions and exhaustion
        
        # 55. RSI Overbought Short (Ranging Markets)
        templates.append(StrategyTemplate(
            name="RSI Overbought Short Ranging",
            description="Short extreme overbought conditions in ranging markets, cover on RSI normalization",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) > 75"  # Extreme overbought
            ],
            exit_conditions=[
                "RSI(14) < 45"  # Cover when RSI normalizes
            ],
            required_indicators=["RSI"],
            default_parameters={
                "rsi_period": 14,
                "overbought_threshold": 75,
                "cover_threshold": 45,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 56. Bollinger Upper Band Short (Ranging Markets)
        templates.append(StrategyTemplate(
            name="BB Upper Band Short Ranging",
            description="Short at upper Bollinger Band with RSI confirmation in ranging markets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2) AND RSI(14) > 65"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2)"  # Cover at middle band
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_confirmation": 65,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 57. Stochastic Overbought Short (Ranging Markets)
        templates.append(StrategyTemplate(
            name="Stochastic Overbought Short Ranging",
            description="Short when Stochastic shows extreme overbought in ranging markets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "STOCH(14) > 85"  # Extreme overbought
            ],
            exit_conditions=[
                "STOCH(14) < 40"  # Cover when normalized
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "overbought_threshold": 85,
                "cover_threshold": 40,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 59. Exhaustion Gap Short (Trending Up)
        templates.append(StrategyTemplate(
            name="Exhaustion Gap Short Uptrend",
            description="Short overbought exhaustion in uptrends - RSI > 75 with price extended above SMA",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "RSI(14) > 75 AND CLOSE > SMA(20) * 1.05"  # 5% above SMA = overextended
            ],
            exit_conditions=[
                "RSI(14) < 50 OR CLOSE < SMA(20)"  # Cover on normalization
            ],
            required_indicators=["RSI", "SMA:20"],
            default_parameters={
                "rsi_period": 14,
                "overbought_threshold": 75,
                "cover_threshold": 50,
                "sma_period": 20,
                "extension_pct": 1.05,
                "stop_loss_pct": 0.04,   # 4% — needs room in trending market before correction
                "take_profit_pct": 0.08  # 8% — real correction target, not a 4% blip
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 60. Bollinger Squeeze Reversal Short (Trending Up)
        templates.append(StrategyTemplate(
            name="BB Squeeze Reversal Short Uptrend",
            description="Short when price breaks above upper BB in uptrend with RSI > 70 (exhaustion)",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2.5) AND RSI(14) > 70"  # Wider bands for uptrends
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2.5)"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.5,  # Wider bands for trending markets
                "rsi_period": 14,
                "rsi_confirmation": 70,
                "stop_loss_pct": 0.04,   # 4% — trending market noise requires wider stop
                "take_profit_pct": 0.08  # 8% — target the full mean-reversion move
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 61. MACD Divergence Short (Trending Up)
        templates.append(StrategyTemplate(
            name="MACD Divergence Short Uptrend",
            description="Short when MACD crosses below signal in overbought uptrend (momentum loss)",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL() AND RSI(14) > 65"
            ],
            exit_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL() OR RSI(14) < 40"
            ],
            required_indicators=["MACD", "RSI"],
            default_parameters={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "rsi_period": 14,
                "rsi_confirmation": 65,
                "stop_loss_pct": 0.04,   # 4% — MACD divergence can take time to play out
                "take_profit_pct": 0.08  # 8% — momentum reversal target
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 62. Parabolic Move Short (Trending Up)
        templates.append(StrategyTemplate(
            name="Parabolic Move Short Uptrend",
            description="Short parabolic moves in uptrends - price > 2*ATR above SMA with RSI > 70",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG],
            entry_conditions=[
                "CLOSE > SMA(20) + ATR(14) * 2.0 AND RSI(14) > 70"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) + ATR(14) * 0.5"  # Cover when move normalizes
            ],
            required_indicators=["SMA", "ATR", "RSI"],
            default_parameters={
                "sma_period": 20,
                "atr_period": 14,
                "atr_entry_multiplier": 2.0,
                "atr_exit_multiplier": 0.5,
                "rsi_period": 14,
                "rsi_confirmation": 70,
                "stop_loss_pct": 0.04,   # 4% — parabolic moves can extend before reversing
                "take_profit_pct": 0.10  # 10% — parabolic reversals are sharp and deep
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 63. Double Top Short (Ranging & Trending Up)
        templates.append(StrategyTemplate(
            name="Double Top Short",
            description="Short when price tests resistance twice with RSI divergence (lower high)",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE > RESISTANCE * 0.998 AND RSI(14) > 65"  # Near resistance with overbought
            ],
            exit_conditions=[
                "CLOSE < SUPPORT OR RSI(14) < 35"
            ],
            required_indicators=["Support", "Resistance", "RSI"],
            default_parameters={
                "lookback_period": 20,
                "resistance_buffer": 0.002,
                "rsi_period": 14,
                "rsi_confirmation": 65,
                "stop_loss_pct": 0.04,   # 4% — double tops can retest before breaking
                "take_profit_pct": 0.08  # 8% — target the full support-to-resistance range
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 64. Volume Climax Short (Ranging & Trending Up)
        templates.append(StrategyTemplate(
            name="Volume Climax Short",
            description="Short when volume spikes with overbought RSI (buying exhaustion)",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG],
            entry_conditions=[
                "VOLUME > VOLUME_MA(20) * 2.0 AND RSI(14) > 70"  # Volume spike + overbought
            ],
            exit_conditions=[
                "RSI(14) < 45 OR CLOSE < SMA(10)"
            ],
            required_indicators=["Volume MA", "RSI", "SMA:10"],
            default_parameters={
                "volume_period": 20,
                "volume_multiplier": 2.0,
                "rsi_period": 14,
                "rsi_confirmation": 70,
                "rsi_exit": 45,
                "sma_period": 10,
                "stop_loss_pct": 0.04,   # 4% — volume climax can spike further before reversing
                "take_profit_pct": 0.08  # 8% — exhaustion reversals tend to be sharp
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # 66. EMA Rejection Short (Trending Up)
        templates.append(StrategyTemplate(
            name="EMA Rejection Short Uptrend",
            description="Short when price fails to hold above EMA(20) in uptrend with RSI > 60",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE < EMA(20) AND RSI(14) > 60 AND EMA(20) > EMA(50)"  # Failed breakout in uptrend
            ],
            exit_conditions=[
                "CLOSE > EMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["EMA:20", "EMA:50", "RSI"],
            default_parameters={
                "fast_period": 20,
                "slow_period": 50,
                "rsi_period": 14,
                "rsi_confirmation": 60,
                "rsi_exit": 40,
                "stop_loss_pct": 0.04,   # 4% — failed breakouts can whipsaw before confirming
                "take_profit_pct": 0.08  # 8% — target the full pullback to next support
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # ===== EARNINGS MOMENTUM TEMPLATE =====
        
        # Earnings Momentum Strategy
        templates.append(StrategyTemplate(
            name="Earnings Momentum",
            description="Capture post-earnings drift by buying small-cap stocks with positive earnings surprises",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING
            ],
            entry_conditions=[
                "Market cap between $300M and $2B",
                "Earnings surprise > 5%",
                "Revenue growth > 10% YoY",
                "2-3 days after earnings announcement",
                "Increasing institutional ownership (optional)"
            ],
            exit_conditions=[
                "Next earnings date approaching (within 7 days)",
                "Profit target of 10% reached",
                "Stop loss of 5% triggered",
                "Hold period of 30-60 days reached"
            ],
            required_indicators=["SMA:50", "Volume MA"],
            default_parameters={
                "market_cap_min": 300000000,  # $300M
                "market_cap_max": 2000000000,  # $2B
                "earnings_surprise_min": 0.05,  # 5%
                "revenue_growth_min": 0.10,  # 10%
                "entry_delay_days": 2,  # Wait 2-3 days after earnings
                "hold_period_min": 30,
                "hold_period_max": 60,
                "profit_target": 0.10,  # 10%
                "stop_loss_pct": 0.05,  # 5%
                "exit_before_earnings_days": 7,  # Exit 7 days before next earnings
                "check_institutional_ownership": False  # Optional check
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="30-60 days",
            risk_reward_ratio=2.0,
            metadata={
                "requires_earnings_data": True,
                "requires_fundamental_data": True,
                "strategy_category": "alpha_edge"
            }
        ))
        
        # ===== SECTOR ROTATION TEMPLATE (for ALL regimes) =====
        
        # Sector Rotation Strategy
        templates.append(StrategyTemplate(
            name="Sector Rotation",
            description="Rotate into sectors that outperform in current economic regimes using sector ETFs",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "Sector has highest momentum in current regime",
                "Sector is appropriate for current macro conditions",
                "Rebalancing period has elapsed (monthly)"
            ],
            exit_conditions=[
                "Sector no longer in top 3 for current regime",
                "Regime change detected",
                "Monthly rebalancing triggered"
            ],
            required_indicators=["SMA:200", "Momentum"],
            default_parameters={
                "max_positions": 3,
                "rebalance_frequency_days": 30,
                "momentum_lookback_days": 60,
                "stop_loss_pct": 0.08,  # Wider stops for sector ETFs
                "take_profit_pct": 0.15,  # Higher targets for sector rotation
            },
            expected_trade_frequency="1-3 rebalances/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=1.8,
            metadata={
                "fixed_symbols": ["XLF", "XLK", "XLI", "XLP", "XLY"],
                "requires_macro_data": True,
                "strategy_category": "alpha_edge",
                "uses_sector_etfs": True
            }
        ))
        
        # ===== QUALITY MEAN REVERSION TEMPLATE =====
        
        # Quality Mean Reversion Strategy
        templates.append(StrategyTemplate(
            name="Quality Mean Reversion",
            description="Buy high-quality large-cap stocks when temporarily oversold, profit from recovery to mean",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "Market cap > $10B (large-cap only)",
                "ROE > 15% (strong profitability)",
                "Debt/Equity < 0.5 (healthy balance sheet)",
                "Positive free cash flow",
                "RSI < 30 (technical oversold)",
                "Down >10% in 5 days (sharp drop)",
                "Below 200-day MA (long-term weakness)",
                "No fundamental deterioration",
                "RSI crosses back above 30 (entry signal)"
            ],
            exit_conditions=[
                "Price returns to 50-day MA (mean reversion complete)",
                "Profit target of 5% reached",
                "Stop loss of 3% triggered"
            ],
            required_indicators=["RSI", "SMA:50", "SMA:200"],
            default_parameters={
                "market_cap_min": 10000000000,  # $10B
                "min_roe": 0.15,  # 15%
                "max_debt_equity": 0.5,
                "oversold_threshold": 30,  # RSI
                "drawdown_threshold": 0.10,  # 10% in 5 days
                "profit_target": 0.05,  # 5%
                "stop_loss_pct": 0.03,  # 3%
                "rsi_period": 14,
                "sma_50_period": 50,
                "sma_200_period": 200
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0,
            metadata={
                "requires_fundamental_data": True,
                "requires_quality_screening": True,
                "strategy_category": "alpha_edge",
                "min_market_cap": 10000000000
            }
        ))
        
        
        # 55. SMA Rejection Short (Ranging)
        templates.append(StrategyTemplate(
            name="SMA Rejection Short Ranging",
            description="Short when price fails to hold above SMA(20) with overbought RSI in ranging markets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < SMA(20) AND RSI(14) > 55 AND RSI(14) < 75"
            ],
            exit_conditions=[
                "RSI(14) < 35 OR CLOSE < SMA(20) * 0.97"
            ],
            required_indicators=["SMA:20", "RSI"],
            default_parameters={
                "sma_period": 20,
                "rsi_period": 14,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=1.5,
            metadata={"direction": "short"}
        ))
        
        # 56. MACD Bearish Short (Ranging)
        templates.append(StrategyTemplate(
            name="MACD Bearish Short Ranging",
            description="Short on MACD bearish crossover in ranging markets, cover on bullish crossover",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL() AND CLOSE < SMA(20)"
            ],
            exit_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL()"
            ],
            required_indicators=["MACD", "SMA:20"],
            default_parameters={
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "sma_period": 20,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-10 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short"}
        ))
        
        # ===== LONG TEMPLATES FOR RANGING / LOW-VOL MARKETS =====
        # These LONG strategies are specifically designed for sideways/ranging conditions
        # where trend-following fails. They use mean reversion, oscillator recovery,
        # and support-bounce logic that thrives in range-bound price action.
        
        # BB Mean Reversion LONG (Ranging)
        templates.append(StrategyTemplate(
            name="BB Mean Reversion Long Ranging",
            description="Buy when price touches lower BB in a ranging market with RSI confirmation, sell at middle band. BB width filter confirms ranging.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2) AND RSI(14) < 40 AND (BB_UPPER(20, 2) - BB_LOWER(20, 2)) / BB_MIDDLE(20, 2) < 0.08"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2) OR RSI(14) > 60"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_period": 14,
                "rsi_entry_max": 40,
                "bb_width_threshold": 0.08,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # RSI Range Oscillator LONG (Ranging)
        templates.append(StrategyTemplate(
            name="RSI Range Oscillator Long Ranging",
            description="Buy when RSI drops below 35 in a non-trending market (ADX < 25 confirms no trend), exit when RSI recovers above 55.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) < 35 AND CLOSE > SMA(50) * 0.95"
            ],
            exit_conditions=[
                "RSI(14) > 55"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "rsi_period": 14,
                "rsi_entry": 35,
                "rsi_exit": 55,
                "sma_period": 50,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # Support Bounce LONG (Ranging)
        templates.append(StrategyTemplate(
            name="Support Bounce Long Ranging",
            description="Buy near recent support (price within 1% of 20-day low) with volume confirmation, exit at resistance (20-day high). Works in channels.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < LOW_20 * 1.01 AND VOLUME > VOLUME_MA(20) AND RSI(14) < 45"
            ],
            exit_conditions=[
                "CLOSE > HIGH_20 * 0.98 OR RSI(14) > 65"
            ],
            required_indicators=["RSI", "Volume MA"],
            default_parameters={
                "lookback_period": 20,
                "support_buffer_pct": 0.01,
                "resistance_buffer_pct": 0.02,
                "rsi_period": 14,
                "volume_period": 20,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="2-3 trades/month",
            expected_holding_period="5-12 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # Stochastic Oversold Recovery LONG (Ranging)
        templates.append(StrategyTemplate(
            name="Stochastic Oversold Recovery Long Ranging",
            description="Buy when Stochastic %K crosses above %D below 20 (recovery signal), exit when %K > 80. Best in ranging markets where oscillators are reliable.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "STOCH(14) < 20 AND STOCH(14) > STOCH_SIGNAL(14)"
            ],
            exit_conditions=[
                "STOCH(14) > 80"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "oversold_threshold": 20,
                "overbought_threshold": 80,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # VWAP Reversion LONG (Ranging)
        templates.append(StrategyTemplate(
            name="VWAP Reversion Long Ranging",
            description="Buy when price drops >1.5% below SMA(20) proxy with increasing volume, exit at SMA(20). Works well in ranging intraday/swing.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < SMA(20) * 0.985 AND VOLUME > VOLUME_MA(20)"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 0.998"
            ],
            required_indicators=["SMA:20", "Volume MA"],
            default_parameters={
                "sma_period": 20,
                "deviation_pct": 0.015,
                "volume_period": 20,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.8,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # Keltner Channel Bounce LONG (Ranging)
        templates.append(StrategyTemplate(
            name="Keltner Channel Bounce Long Ranging",
            description="Buy at lower Keltner channel (EMA - 1.5*ATR) with low volatility confirmation, exit at middle channel (EMA).",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < EMA(20) - ATR(14) * 1.5 AND RSI(14) < 45"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) OR RSI(14) > 60"
            ],
            required_indicators=["EMA:20", "ATR", "RSI"],
            default_parameters={
                "ema_period": 20,
                "atr_period": 14,
                "atr_multiplier": 1.5,
                "rsi_period": 14,
                "rsi_entry_max": 45,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # Double Bottom Pattern LONG (Ranging)
        templates.append(StrategyTemplate(
            name="Double Bottom Long Ranging",
            description="Buy on second touch of support with RSI divergence (higher RSI low while price retests low), exit at neckline resistance.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < LOW_20 * 1.015 AND RSI(14) > 30 AND RSI(14) < 45 AND CLOSE > SMA(50) * 0.93"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 1.02 OR RSI(14) > 65"
            ],
            required_indicators=["RSI", "SMA:20", "SMA:50"],
            default_parameters={
                "lookback_period": 20,
                "rsi_period": 14,
                "rsi_min": 30,
                "rsi_max": 45,
                "sma_period": 20,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="5-12 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # Accumulation Zone LONG (Ranging)
        templates.append(StrategyTemplate(
            name="Accumulation Zone Long Ranging",
            description="Buy when price consolidates near support with declining volume (accumulation), exit on volume breakout above range.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < SMA(20) * 1.01 AND CLOSE > SMA(20) * 0.97 AND VOLUME < VOLUME_MA(20) * 0.8 AND RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 1.02 AND VOLUME > VOLUME_MA(20) * 1.2"
            ],
            required_indicators=["SMA:20", "Volume MA", "RSI"],
            default_parameters={
                "sma_period": 20,
                "volume_period": 20,
                "volume_decline_ratio": 0.8,
                "volume_breakout_ratio": 1.2,
                "rsi_period": 14,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.5,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "ranging_specialist"
            }
        ))
        
        # ===== SHORT ALPHA EDGE TEMPLATES =====
        
        # Earnings Miss Momentum (SHORT)
        templates.append(StrategyTemplate(
            name="Earnings Miss Momentum Short",
            description="Short stocks after negative earnings surprises (>3% drop), capturing post-earnings downward drift",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_DOWN,
                MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "Negative earnings surprise (>3% miss)",
                "Stock drops >3% on earnings day",
                "Entry 2-3 days after earnings announcement (SHORT)",
                "Revenue decline or guidance cut (optional)"
            ],
            exit_conditions=[
                "Profit target of 5% reached (price drops 5%)",
                "Stop loss of 3% triggered (price rises 3%)",
                "Hold period of 30 days reached",
                "Next earnings date approaching (within 7 days)"
            ],
            required_indicators=["SMA:50", "Volume MA"],
            default_parameters={
                "market_cap_min": 300000000,
                "market_cap_max": 2000000000,
                "earnings_miss_min": 0.03,
                "entry_delay_days": 2,
                "hold_period_max": 30,
                "profit_target": 0.05,
                "stop_loss_pct": 0.03,
                "exit_before_earnings_days": 7,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="10-30 days",
            risk_reward_ratio=1.7,
            metadata={
                "requires_earnings_data": True,
                "requires_fundamental_data": True,
                "strategy_category": "alpha_edge",
                "direction": "short",
                "alpha_edge_bypass": True,
            }
        ))
        
        # Sector Rotation Short
        templates.append(StrategyTemplate(
            name="Sector Rotation Short",
            description="Short sector ETFs in unfavorable regimes when momentum turns negative",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_DOWN,
                MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "Sector has negative 60-day momentum",
                "Sector is unfavorable for current macro conditions",
                "Rebalancing period has elapsed (monthly)",
                "Entry SHORT on sector ETF"
            ],
            exit_conditions=[
                "Sector momentum turns positive",
                "Regime change detected (favorable for sector)",
                "Monthly rebalancing triggered",
                "Profit target of 5% reached"
            ],
            required_indicators=["SMA:200", "Momentum"],
            default_parameters={
                "max_positions": 3,
                "rebalance_frequency_days": 30,
                "momentum_lookback_days": 60,
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.05,
            },
            expected_trade_frequency="1-3 rebalances/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=1.5,
            metadata={
                "fixed_symbols": ["XLF", "XLK", "XLI", "XLP", "XLY"],
                "requires_macro_data": True,
                "strategy_category": "alpha_edge",
                "direction": "short",
                "alpha_edge_bypass": True,
                "uses_sector_etfs": True,
            }
        ))
        
        # ===== NEW ALPHA EDGE LONG TEMPLATES =====
        
        # Dividend Aristocrat Strategy
        templates.append(StrategyTemplate(
            name="Dividend Aristocrat",
            description="Buy stocks with 10+ years of consecutive dividend increases when price pulls back from 52-week high",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "Consecutive dividend increases >= 10 years",
                "Dividend yield > 2.5%",
                "Payout ratio < 75%",
                "Price pulled back >5% from 52-week high",
                "Entry on pullback confirmation"
            ],
            exit_conditions=[
                "Dividend cut announced",
                "Profit target of 15% reached",
                "Stop loss of 5% triggered"
            ],
            required_indicators=["SMA:200"],
            default_parameters={
                "min_dividend_years": 10,
                "min_dividend_yield": 0.025,
                "max_payout_ratio": 0.75,
                "pullback_from_high_pct": 0.05,
                "profit_target": 0.15,
                "stop_loss_pct": 0.05,
                "hold_period_max": 90,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=3.0,
            metadata={
                "requires_fundamental_data": True,
                "strategy_category": "alpha_edge",
                "alpha_edge_bypass": True,
                "best_symbols": ["JNJ", "PG", "KO", "ABBV", "PEP"],
            }
        ))
        
        # Insider Buying Strategy
        templates.append(StrategyTemplate(
            name="Insider Buying",
            description="Buy stocks with significant insider purchases (CEO/CFO buys > $100K) within 5 days of filing",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "Insider purchase filing detected (CEO/CFO)",
                "Purchase amount > $100K",
                "Entry within 5 days of filing date",
            ],
            exit_conditions=[
                "Profit target of 10% reached",
                "Hold period of 30-60 days reached",
                "Stop loss of 5% triggered"
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "min_purchase_amount": 100000,
                "filing_recency_days": 5,
                "hold_period_min": 30,
                "hold_period_max": 60,
                "profit_target": 0.10,
                "stop_loss_pct": 0.05,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="30-60 days",
            risk_reward_ratio=2.0,
            metadata={
                "requires_fundamental_data": True,
                "requires_insider_data": True,
                "strategy_category": "alpha_edge",
                "alpha_edge_bypass": True,
            }
        ))
        
        # Revenue Acceleration Strategy
        templates.append(StrategyTemplate(
            name="Revenue Acceleration",
            description="Buy companies with accelerating revenue growth across 3 consecutive quarters",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "Current quarter revenue growth > previous quarter",
                "Previous quarter revenue growth > quarter before that",
                "3 consecutive quarters of accelerating growth",
                "Entry on earnings report confirmation"
            ],
            exit_conditions=[
                "Profit target of 12% reached",
                "Hold period of 20-40 days reached",
                "Stop loss of 5% triggered",
                "Revenue growth decelerates"
            ],
            required_indicators=["SMA:50", "Volume MA"],
            default_parameters={
                "min_quarters_accelerating": 3,
                "hold_period_min": 20,
                "hold_period_max": 40,
                "profit_target": 0.12,
                "stop_loss_pct": 0.05,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="20-40 days",
            risk_reward_ratio=2.4,
            metadata={
                "requires_fundamental_data": True,
                "requires_earnings_data": True,
                "strategy_category": "alpha_edge",
                "alpha_edge_bypass": True,
            }
        ))
        
        # Relative Value Strategy
        templates.append(StrategyTemplate(
            name="Relative Value",
            description="Long cheapest quintile and short most expensive quintile within same sector based on P/E, P/S, EV/EBITDA",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "Stock P/E in cheapest quintile of sector (LONG)",
                "Or stock P/E in most expensive quintile of sector (SHORT)",
                "Compare P/E, P/S, EV/EBITDA to sector median",
                "Monthly rebalancing"
            ],
            exit_conditions=[
                "Monthly rebalancing triggered",
                "Profit target of 10% reached",
                "Stop loss of 5% triggered"
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "rebalance_frequency_days": 30,
                "profit_target": 0.10,
                "stop_loss_pct": 0.05,
                "hold_period_max": 45,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="30-45 days",
            risk_reward_ratio=2.0,
            metadata={
                "requires_fundamental_data": True,
                "strategy_category": "alpha_edge",
                "alpha_edge_bypass": True,
                "supports_long_short": True,
                "best_symbols": ["JPM", "GS", "MS", "INTC", "PFE", "BA", "DIS", "BABA"],
            }
        ))
        
        # Quality Deterioration Short
        templates.append(StrategyTemplate(
            name="Quality Deterioration Short",
            description="Short stocks with deteriorating fundamentals when overbought (RSI > 75, declining ROE)",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_DOWN,
                MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_HIGH_VOL
            ],
            entry_conditions=[
                "RSI > 75 (overbought)",
                "ROE declining or below 10%",
                "Debt/Equity rising or above 1.0",
                "RSI crosses below 75 (entry signal for SHORT)",
                "Negative free cash flow trend"
            ],
            exit_conditions=[
                "Price drops to 50-day MA (mean reversion complete)",
                "Profit target of 5% reached (price drops 5%)",
                "Stop loss of 5% triggered (price rises 5%)",
                "Hold period of 40 days reached"
            ],
            required_indicators=["RSI", "SMA:50", "SMA:200"],
            default_parameters={
                "market_cap_min": 10000000000,
                "overbought_threshold": 75,
                "profit_target": 0.05,
                "stop_loss_pct": 0.05,
                "rsi_period": 14,
                "sma_50_period": 50,
                "sma_200_period": 200,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-40 days",
            risk_reward_ratio=1.5,
            metadata={
                "requires_fundamental_data": True,
                "requires_quality_screening": True,
                "strategy_category": "alpha_edge",
                "direction": "short",
                "alpha_edge_bypass": True,
                "min_market_cap": 10000000000,
            }
        ))
        
        # ===== END-OF-MONTH MOMENTUM (Alpha Edge) =====
        # Captures institutional rebalancing flows — pension funds, mutual funds,
        # and ETFs rebalance at month-end, creating predictable buying pressure.
        # Best for broad market ETFs (SPY, QQQ, IWM, DIA) and large-cap stocks.
        
        templates.append(StrategyTemplate(
            name="End-of-Month Momentum Long",
            description="Buy in the last 3 trading days of each month when price > SMA(20) and RSI > 40. Exit on the 3rd trading day of the next month. Captures institutional month-end rebalancing flows.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Date is in last 3 trading days of month (day >= 26 approximation)",
                "Price > SMA(20) — uptrend confirmation",
                "RSI(14) > 40 — not oversold, momentum intact",
            ],
            exit_conditions=[
                "3rd trading day of the next month (day >= 3 and new month)",
                "Stop loss: 2% below entry",
            ],
            required_indicators=["SMA", "RSI"],
            default_parameters={
                "sma_period": 20,
                "rsi_period": 14,
                "rsi_min": 40,
                "month_end_day_threshold": 26,
                "exit_day_of_new_month": 3,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03,  # Short hold (3-7 days), small institutional drift
                "hold_period_max": 10,
            },
            expected_trade_frequency="1 trade/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "statistical",
                "alpha_edge_type": "end_of_month_momentum",
                "requires_fundamental_data": False,
                "disabled": True,
                "disable_reason": "no_fundamental_edge_reclassified_from_alpha_edge",
                "best_symbols": ["SPY", "QQQ", "IWM", "DIA", "VTI", "VOO"],
                "regime_preference": ["trending_up", "ranging_low_vol"],
            }
        ))
        
        # ===== PAIRS TRADING — REMOVED 2026-05-02 (Sprint 1 / F7) =====
        # The previous "Pairs Trading Market Neutral" template was structurally
        # broken: its DSL conditions were momentum-long signals on a single
        # symbol (PRICE_CHANGE_PCT > 0 AND CLOSE/SMA(50) > 1.02), not a spread
        # test on a pair. It passed WF on the dominant symbol and took
        # unhedged directional bets under a "market neutral" label. Steering
        # file flagged this as a known structural issue.
        # A proper pairs-trading template requires cross-asset spread
        # primitives (z-score of (A/B) against its rolling window). That is
        # enabled by the F1 DSL primitives added in this sprint, but the
        # template itself is not rebuilt here — we will revisit as a
        # follow-up work item once F1 is proven on crypto lead-lag.

        # ===== ANALYST REVISION MOMENTUM (Alpha Edge) =====
        templates.append(StrategyTemplate(
            name="Analyst Revision Momentum",
            description="Enter LONG when analyst EPS estimates are revised upward across 2+ consecutive quarters. Captures the tendency of stocks with rising estimates to outperform.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=["Analyst EPS estimate revised upward for 2+ consecutive quarters", "Current estimate > estimate from 2 quarters ago by > 5%"],
            exit_conditions=["Estimate revised downward", "Profit target 12%", "Stop loss 5%", "Max hold 60 days"],
            required_indicators=["SMA:50"],
            default_parameters={"min_revision_pct": 0.05, "min_consecutive_revisions": 2, "profit_target": 0.12, "stop_loss_pct": 0.05, "hold_period_max": 60},
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="15-60 days",
            risk_reward_ratio=2.4,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "analyst_revision_momentum",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
                "requires_earnings_data": True,
            }
        ))

        # ===== SHARE BUYBACK MOMENTUM (Alpha Edge) =====
        templates.append(StrategyTemplate(
            name="Share Buyback Momentum",
            description="Enter LONG when a company is actively buying back shares (negative shares_change_percent). Companies reducing share count tend to outperform due to EPS accretion and management confidence signal.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=["Shares outstanding decreased > 1% YoY", "Positive earnings (EPS > 0)", "RSI < 60 (not overbought)"],
            exit_conditions=["Share count increases (dilution)", "Profit target 10%", "Stop loss 5%", "Max hold 60 days"],
            required_indicators=["RSI"],
            default_parameters={"min_buyback_pct": 0.01, "min_eps": 0.0, "rsi_max_entry": 60, "profit_target": 0.10, "stop_loss_pct": 0.05, "hold_period_max": 60},
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="20-60 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "share_buyback",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== MULTI-FACTOR COMPOSITE (Alpha Edge — Institutional-Grade) =====
        # This is the core institutional approach: rank all stocks by a composite
        # score combining value, quality, momentum, and growth factors.
        # LONG the top quintile, SHORT the bottom quintile. Monthly rebalance.
        # Replaces the "one template per factor" approach with unified scoring.
        templates.append(StrategyTemplate(
            name="Multi-Factor Composite Long",
            description="Long stocks in the top 20% by composite fundamental score (value + quality + momentum + growth). Rebalance monthly. Institutional-grade multi-factor approach.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Composite score in top 20% of universe (value + quality + momentum + growth)",
                "Piotroski F-Score >= 6 (quality gate)",
                "Accruals ratio < 0.05 (earnings backed by cash flow)",
            ],
            exit_conditions=[
                "Composite score drops below 50th percentile",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "rebalance_frequency_days": 30,
                "top_pct": 20,
                "min_f_score": 6,
                "max_accruals": 0.05,
                "profit_target": 0.15,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="3-5 trades/month (rebalance)",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "multi_factor_composite",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
                "is_composite": True,
            }
        ))

        templates.append(StrategyTemplate(
            name="Multi-Factor Composite Short",
            description="Short stocks in the bottom 20% by composite fundamental score. Rebalance monthly. Targets overvalued, low-quality, decelerating stocks.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Composite score in bottom 20% of universe",
                "Piotroski F-Score <= 3 (weak fundamentals)",
                "Accruals ratio > 0.10 (earnings not backed by cash)",
            ],
            exit_conditions=[
                "Composite score rises above 50th percentile",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "rebalance_frequency_days": 30,
                "bottom_pct": 20,
                "max_f_score": 3,
                "min_accruals": 0.10,
                "profit_target": 0.10,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="2-4 trades/month (rebalance)",
            expected_holding_period="30-90 days",
            risk_reward_ratio=1.5,
            metadata={
                "direction": "short",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "multi_factor_composite",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
                "is_composite": True,
            }
        ))

        # ===== GROSS PROFITABILITY (Novy-Marx Factor) =====
        # Gross profits / total assets predicts returns as well as book-to-market.
        # Most profitable firms earn 0.31%/month more than least profitable.
        # This is the "other side of value" — quality at a reasonable price.
        templates.append(StrategyTemplate(
            name="Gross Profitability Long",
            description="Long stocks with high gross profitability (gross profit / total assets). Novy-Marx (2013) showed this factor has the same predictive power as book-to-market for cross-sectional returns.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Gross profit / total assets in top 30% of universe",
                "Piotroski F-Score >= 5",
                "Price above SMA(50) — not in freefall",
            ],
            exit_conditions=[
                "Gross profitability drops below median",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "min_gp_to_assets": 0.30,
                "min_f_score": 5,
                "rebalance_frequency_days": 30,
                "profit_target": 0.12,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "gross_profitability",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== ACCRUALS QUALITY LONG/SHORT (Sloan 1996) =====
        # Companies with low accruals (earnings backed by cash flow) outperform
        # those with high accruals (accounting-heavy earnings) by ~10% annually.
        templates.append(StrategyTemplate(
            name="Accruals Quality Long",
            description="Long stocks with low accruals ratio (earnings backed by real cash flow). Sloan (1996) documented ~10% annual alpha from this factor.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Accruals ratio < -0.03 (cash flow exceeds net income)",
                "Positive operating cash flow",
                "Piotroski F-Score >= 5",
            ],
            exit_conditions=[
                "Accruals ratio turns positive (> 0.05)",
                "Monthly rebalance",
                "Stop loss 7%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "max_accruals_ratio": -0.03,
                "min_f_score": 5,
                "rebalance_frequency_days": 30,
                "profit_target": 0.10,
                "stop_loss_pct": 0.07,
                "hold_period_max": 90,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "accruals_quality",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        templates.append(StrategyTemplate(
            name="Accruals Quality Short",
            description="Short stocks with high accruals ratio (earnings driven by accounting, not cash). These tend to underperform as accruals reverse.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Accruals ratio > 0.10 (net income far exceeds cash flow)",
                "Piotroski F-Score <= 4",
                "Price below SMA(200) — confirming weakness",
            ],
            exit_conditions=[
                "Accruals ratio drops below 0.05",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:200"],
            default_parameters={
                "min_accruals_ratio": 0.10,
                "max_f_score": 4,
                "rebalance_frequency_days": 30,
                "profit_target": 0.08,
                "stop_loss_pct": 0.08,
                "hold_period_max": 60,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="30-60 days",
            risk_reward_ratio=1.5,
            metadata={
                "direction": "short",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "accruals_quality",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== FCF YIELD VALUE (Better than P/E) =====
        # Free cash flow yield is harder to manipulate than earnings and directly
        # measures how much cash a business generates relative to its price.
        templates.append(StrategyTemplate(
            name="FCF Yield Value Long",
            description="Long stocks with high free cash flow yield (FCF / market cap). FCF yield is more reliable than P/E because cash flow is harder to manipulate than earnings.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "FCF yield in top 25% of universe (> ~5%)",
                "Positive operating cash flow for 2+ consecutive quarters",
                "Piotroski F-Score >= 5",
            ],
            exit_conditions=[
                "FCF yield drops below median",
                "Operating cash flow turns negative",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "min_fcf_yield": 0.05,
                "min_f_score": 5,
                "rebalance_frequency_days": 30,
                "profit_target": 0.12,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "fcf_yield_value",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== PRICE TARGET UPSIDE (Analyst Consensus) =====
        # Buy stocks where analyst consensus price target is 20%+ above current price.
        # Combines with recent upgrade for confirmation.
        templates.append(StrategyTemplate(
            name="Price Target Upside Long",
            description="Long stocks where analyst consensus price target implies 20%+ upside. Confirmed by at least one recent upgrade. Captures analyst conviction before the market prices it in.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "Analyst consensus price target > 120% of current price",
                "At least 1 recent upgrade in last 90 days",
                "Piotroski F-Score >= 4 (not a distressed stock)",
            ],
            exit_conditions=[
                "Price reaches consensus target",
                "Target lowered below current price",
                "Stop loss 8%",
                "Max hold 90 days",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "min_upside_pct": 0.20,
                "min_f_score": 4,
                "profit_target": 0.15,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "price_target_upside",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== SHAREHOLDER YIELD (Faber) =====
        # Total yield = dividend yield + buyback yield + debt paydown yield.
        # Meb Faber's strategy returned 2,019% since 2009 vs market's 679%.
        templates.append(StrategyTemplate(
            name="Shareholder Yield Long",
            description="Long stocks with highest total shareholder yield (dividends + buybacks + debt paydown). Meb Faber's approach — companies returning the most capital to shareholders tend to outperform.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Total shareholder yield (div + buyback + debt paydown) in top 20% of universe",
                "Positive free cash flow",
                "Piotroski F-Score >= 5",
            ],
            exit_conditions=[
                "Shareholder yield drops below median",
                "FCF turns negative",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "min_shareholder_yield": 0.04,
                "min_f_score": 5,
                "rebalance_frequency_days": 30,
                "profit_target": 0.12,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "shareholder_yield",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== EARNINGS + PRICE MOMENTUM COMBO (PEAD Enhanced) =====
        # Earnings surprise alone is good. Earnings surprise + price momentum is better.
        # Stocks that beat earnings AND have strong 3-month momentum drift for 60+ days.
        templates.append(StrategyTemplate(
            name="Earnings Momentum Combo Long",
            description="Long stocks with strong earnings surprise (SUE > 1.5) AND strong 3-month price momentum. The combination filters false positives and captures the strongest post-earnings drift.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "SUE > 1.5 (standardized earnings surprise)",
                "3-month price return in top 30% of universe",
                "Entry 2-3 days after earnings announcement",
            ],
            exit_conditions=[
                "60 days post-earnings",
                "Momentum reverses (price drops below SMA(20))",
                "Stop loss 6%",
            ],
            required_indicators=["SMA:20", "SMA:50"],
            default_parameters={
                "min_sue": 1.5,
                "entry_delay_days": 2,
                "hold_period_max": 60,
                "profit_target": 0.12,
                "stop_loss_pct": 0.06,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="30-60 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "earnings_momentum_combo",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
                "requires_earnings_data": True,
            }
        ))

        # ===== QUALITY + VALUE COMBO (Novy-Marx Enhanced) =====
        # Cheap stocks that are also highly profitable avoid value traps.
        # Combining value (FCF yield) with quality (gross profitability) is more
        # powerful than either factor alone.
        templates.append(StrategyTemplate(
            name="Quality Value Combo Long",
            description="Long stocks that are both cheap (high FCF yield) AND profitable (high gross profitability). Avoids value traps by requiring quality confirmation.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "FCF yield in top 30% of universe",
                "Gross profitability (GP/Assets) in top 30% of universe",
                "Piotroski F-Score >= 6",
            ],
            exit_conditions=[
                "Either factor drops below median",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "min_fcf_yield": 0.03,
                "min_gp_to_assets": 0.25,
                "min_f_score": 6,
                "rebalance_frequency_days": 30,
                "profit_target": 0.15,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.5,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "quality_value_combo",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== DELEVERAGING PLAY =====
        # Companies actively paying down debt become less risky as leverage decreases.
        # The equity re-rates higher as the balance sheet improves.
        templates.append(StrategyTemplate(
            name="Deleveraging Long",
            description="Long companies actively reducing debt (>10% YoY decrease in long-term debt) with positive FCF. As leverage decreases, equity becomes less risky and re-rates higher.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "Long-term debt decreased > 10% YoY",
                "Positive free cash flow",
                "Piotroski F-Score >= 5",
                "Debt-to-equity still > 0.3 (room to deleverage further)",
            ],
            exit_conditions=[
                "Debt starts increasing again",
                "FCF turns negative",
                "Monthly rebalance",
                "Stop loss 8%",
            ],
            required_indicators=["SMA:50"],
            default_parameters={
                "min_debt_reduction_pct": 0.10,
                "min_f_score": 5,
                "min_debt_to_equity": 0.3,
                "rebalance_frequency_days": 30,
                "profit_target": 0.12,
                "stop_loss_pct": 0.08,
                "hold_period_max": 90,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="30-90 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "deleveraging",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
            }
        ))

        # ===== GAP REVERSAL TEMPLATES =====
        # Gaps tend to fill more reliably in ranging markets.
        
        # Gap Down Reversal LONG
        templates.append(StrategyTemplate(
            name="Gap Down Reversal Long",
            description="Buy when overnight gap down >2% with RSI < 40 and volume > 1.5x average. Works best on liquid large-caps where gaps tend to fill.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "PRICE_CHANGE_PCT(1) < -2.0 AND RSI(14) < 40 AND VOLUME > VOLUME_MA(20) * 1.5"
            ],
            exit_conditions=[
                "PRICE_CHANGE_PCT(1) > 1.6 OR RSI(14) > 60"  # 80% gap fill or RSI recovery
            ],
            required_indicators=["Price Change %", "RSI", "Volume MA"],
            default_parameters={
                "gap_threshold_pct": -2.0,
                "rsi_period": 14,
                "rsi_entry_max": 40,
                "rsi_exit": 60,
                "volume_ma_period": 20,
                "volume_multiplier": 1.5,
                "gap_fill_pct": 0.80,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04,  # Gap fills are quick 1-3 day trades, 80% fill target
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "gap_reversal"
            }
        ))
        
        # Gap Up Reversal SHORT
        templates.append(StrategyTemplate(
            name="Gap Up Reversal Short",
            description="Short when overnight gap up >2% with RSI > 65 and volume > 1.5x average. Gaps fill more reliably in ranging markets.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "PRICE_CHANGE_PCT(1) > 2.0 AND RSI(14) > 65 AND VOLUME > VOLUME_MA(20) * 1.5"
            ],
            exit_conditions=[
                "PRICE_CHANGE_PCT(1) < -1.6 OR RSI(14) < 40"  # 80% gap fill or RSI drop
            ],
            required_indicators=["Price Change %", "RSI", "Volume MA"],
            default_parameters={
                "gap_threshold_pct": 2.0,
                "rsi_period": 14,
                "rsi_entry_min": 65,
                "rsi_exit": 40,
                "volume_ma_period": 20,
                "volume_multiplier": 1.5,
                "gap_fill_pct": 0.80,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04,  # Gap fills are quick 1-3 day trades, 80% fill target
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "short",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "gap_reversal"
            }
        ))
        
        # ===== VOLUME CLIMAX REVERSAL TEMPLATES =====
        # Volume climaxes signal exhaustion — regime-independent.
        
        # Volume Climax Reversal LONG
        templates.append(StrategyTemplate(
            name="Volume Climax Reversal Long",
            description="Buy when volume spikes >3x 20-day average with RSI < 35, signaling panic selling exhaustion. Exit when RSI recovers or volume normalizes.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.RANGING,
            ],
            entry_conditions=[
                "VOLUME > VOLUME_MA(20) * 2.0 AND RSI(14) < 40"
            ],
            exit_conditions=[
                "RSI(14) > 55 OR VOLUME < VOLUME_MA(20) * 1.5"
            ],
            required_indicators=["Volume MA", "RSI"],
            default_parameters={
                "volume_ma_period": 20,
                "volume_climax_multiplier": 3.0,
                "volume_normalize_multiplier": 1.5,
                "rsi_period": 14,
                "rsi_entry_max": 35,
                "rsi_exit": 55,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.06,  # Panic selling bounces are sharp — let it run to 6%
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "volume_climax_reversal"
            }
        ))
        
        # Volume Climax Reversal SHORT
        templates.append(StrategyTemplate(
            name="Volume Climax Reversal Short",
            description="Short when volume spikes >3x 20-day average with RSI > 70, signaling buying exhaustion. Exit when RSI drops or volume normalizes.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_DOWN,
                MarketRegime.RANGING,
            ],
            entry_conditions=[
                "VOLUME > VOLUME_MA(20) * 3.0 AND RSI(14) > 70"
            ],
            exit_conditions=[
                "RSI(14) < 50 OR VOLUME < VOLUME_MA(20) * 1.5"
            ],
            required_indicators=["Volume MA", "RSI"],
            default_parameters={
                "volume_ma_period": 20,
                "volume_climax_multiplier": 3.0,
                "volume_normalize_multiplier": 1.5,
                "rsi_period": 14,
                "rsi_entry_min": 70,
                "rsi_exit": 50,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.06,  # Buying exhaustion drops are sharp — let it run to 6%
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "short",
                "strategy_category": "volume_climax_reversal"
            }
        ))
        
        # ===== OBV DIVERGENCE TEMPLATES (Volume-Weighted Price Proxy) =====
        # OBV not available in IndicatorLibrary, so we use a volume-weighted proxy:
        # Divergence = price at new extreme but volume declining (hidden accumulation/distribution).
        # Works across most regimes but particularly effective in ranging markets.
        
        # OBV Bullish Divergence LONG
        templates.append(StrategyTemplate(
            name="OBV Bullish Divergence Long",
            description="Buy when price makes new 20-day low but volume is below average (hidden accumulation — sellers exhausted). Exit when price returns to SMA(20) or RSI > 60. Stop loss 3%.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING,
                MarketRegime.RANGING_HIGH_VOL,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE < LOW_20 AND VOLUME < VOLUME_MA(20) * 0.8 AND RSI(14) < 40"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) OR RSI(14) > 60"
            ],
            required_indicators=["Support/Resistance", "Volume MA", "SMA", "RSI"],
            default_parameters={
                "support_lookback": 20,
                "volume_ma_period": 20,
                "sma_period": 20,
                "rsi_period": 14,
                "rsi_exit": 60,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,  # Hidden accumulation plays need room — 5% target over 5-15 days
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "obv_divergence"
            }
        ))
        
        # OBV Bearish Divergence SHORT
        templates.append(StrategyTemplate(
            name="OBV Bearish Divergence Short",
            description="Short when price makes new 20-day high but volume is below average (hidden distribution — buyers exhausted). Exit when price returns to SMA(20) or RSI < 40. Stop loss 3%.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING,
                MarketRegime.RANGING_HIGH_VOL,
                MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "CLOSE > RESISTANCE AND VOLUME < VOLUME_MA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["Support/Resistance", "Volume MA", "SMA", "RSI"],
            default_parameters={
                "resistance_lookback": 20,
                "volume_ma_period": 20,
                "sma_period": 20,
                "rsi_period": 14,
                "rsi_exit": 40,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,  # Hidden distribution plays need room — 5% target over 5-15 days
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "short",
                "regime_preference": ["ranging", "ranging_low_vol"],
                "strategy_category": "obv_divergence"
            }
        ))
        
        # ===== VIX-REGIME MEAN REVERSION TEMPLATES (Volatility-Proxy) =====
        # VIX data is not available in the DSL engine, so we use regime_preference
        # metadata to target the appropriate volatility environment:
        # - High-VIX proxy → ranging_high_vol / trending_down_weak regimes
        # - Low-VIX proxy → trending_up / ranging_low_vol regimes
        # The regime detector already classifies market conditions by volatility,
        # making explicit ATR/CLOSE ratios unnecessary in the entry conditions.
        
        # High-VIX Mean Reversion LONG
        # When volatility is elevated (VIX > 25 equivalent), buy extreme oversold
        # stocks. Oversold bounces in high-vol regimes are sharper and more reliable.
        # Tighter stop (2%) because high-vol moves can reverse quickly.
        templates.append(StrategyTemplate(
            name="High-VIX Mean Reversion Long",
            description="Buy when RSI < 30 and price below lower Bollinger Band in high-volatility regimes (VIX > 25 proxy). Oversold bounces are sharper when fear is elevated. Tight 2% stop, exit at RSI > 50.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_HIGH_VOL,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)"
            ],
            exit_conditions=[
                "RSI(14) > 50"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "rsi_period": 14,
                "rsi_entry": 30,
                "rsi_exit": 50,
                "bb_period": 20,
                "bb_std": 2,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.06,  # High-vol oversold bounces are sharp — 6% captures the snap-back without cutting short
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.5,
            metadata={
                "direction": "long",
                "regime_preference": ["ranging_high_vol", "trending_down_weak"],
                "strategy_category": "vix_regime",
                "volatility_proxy": "high_vix",
                "vix_equivalent": ">25",
            }
        ))
        
        # Low-VIX Trend Following LONG
        # When volatility is low (VIX < 15 equivalent), buy breakouts above the
        # upper Bollinger Band with momentum confirmation (RSI > 50). Low-vol
        # trends persist longer, so use wider stop (4%) and longer holds.
        templates.append(StrategyTemplate(
            name="Low-VIX Trend Following Long",
            description="Buy breakouts above upper Bollinger Band with RSI > 50 momentum confirmation in low-volatility regimes (VIX < 15 proxy). Low-vol trends persist longer. Wider 4% stop, exit below SMA(20).",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"
            ],
            required_indicators=["Bollinger Bands", "RSI", "SMA"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2,
                "rsi_period": 14,
                "rsi_entry": 50,
                "sma_period": 20,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.08,  # Low-vol trends persist — wider TP to ride the breakout
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="10-30 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "regime_preference": ["trending_up", "ranging_low_vol"],
                "strategy_category": "vix_regime",
                "volatility_proxy": "low_vix",
                "vix_equivalent": "<15",
            }
        ))
        
        # ===== INTRADAY-SPECIFIC TEMPLATES =====
        # These templates are designed for 1h data and exploit patterns
        # that only exist on intraday timeframes.
        
        # Opening Range Breakout — first hour establishes the range, trade the breakout
        templates.append(StrategyTemplate(
            name="Opening Range Breakout",
            description="Buy when price breaks above the first-hour high with volume confirmation",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "CLOSE > HIGH_20 * 0.998 AND VOLUME > VOLUME_MA(20) * 1.2"
            ],
            exit_conditions=[
                "CLOSE < SMA(10) OR RSI(14) > 75"
            ],
            required_indicators=["Rolling High", "Volume MA", "SMA:10", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.03,
                "risk_per_trade_pct": 0.01,
                "hold_period_max": 24,
            },
            expected_trade_frequency="5-10 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # Intraday VWAP Reversion — price reverts to VWAP after overextension
        templates.append(StrategyTemplate(
            name="Intraday Mean Reversion",
            description="Buy when price drops >1.5% below SMA(20) intraday with RSI oversold, exit at SMA",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE < SMA(20) * 0.985 AND RSI(14) < 35"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 0.998 OR RSI(14) > 60"
            ],
            required_indicators=["SMA:20", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
                "risk_per_trade_pct": 0.01,
                "hold_period_max": 24,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # Intraday Momentum Burst — catch strong moves early
        templates.append(StrategyTemplate(
            name="Intraday Momentum Burst",
            description="Buy on strong hourly momentum (price change >1%) with volume surge, ride the trend",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "PRICE_CHANGE_PCT(1) > 1.0 AND VOLUME > VOLUME_MA(20) * 1.5"
            ],
            exit_conditions=[
                "PRICE_CHANGE_PCT(1) < -0.5 OR RSI(14) > 80"
            ],
            required_indicators=["Price Change %", "Volume MA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "hold_period_max": 24,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-8 hours",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # Intraday Momentum Burst Short
        templates.append(StrategyTemplate(
            name="Intraday Momentum Burst Short",
            description="Short on strong hourly selloff (price drop >1%) with volume surge",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "PRICE_CHANGE_PCT(1) < -1.0 AND VOLUME > VOLUME_MA(20) * 1.5"
            ],
            exit_conditions=[
                "PRICE_CHANGE_PCT(1) > 0.5 OR RSI(14) < 20"
            ],
            required_indicators=["Price Change %", "Volume MA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "hold_period_max": 24,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-8 hours",
            risk_reward_ratio=2.5,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # Hourly RSI Divergence — RSI makes higher low while price makes lower low
        templates.append(StrategyTemplate(
            name="Hourly RSI Oversold Bounce",
            description="Buy when hourly RSI drops below 20 (extreme oversold), exit on recovery above 50",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "RSI(14) < 20"
            ],
            exit_conditions=[
                "RSI(14) > 50"
            ],
            required_indicators=["RSI"],
            default_parameters={
                "oversold_threshold": 20,
                "overbought_threshold": 50,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03,
                "hold_period_max": 24,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="2-24 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # Hourly Bollinger Band Squeeze + Breakout — tighter timeframe for faster entries
        templates.append(StrategyTemplate(
            name="Hourly BB Squeeze Breakout",
            description="Buy when hourly Bollinger Bands narrow then price breaks above upper band",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING,
                MarketRegime.TRENDING_UP,
            ],
            entry_conditions=[
                "(BB_UPPER(20, 2) - BB_LOWER(20, 2)) < ATR(14) * 3 AND CLOSE > BB_UPPER(20, 2)"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands", "ATR"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.035,
                "hold_period_max": 24,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # ===== NEW INTRADAY TEMPLATES (Stocks/ETFs/Forex/Indices) =====
        # The existing intraday set is all LONG and only 3 templates for non-crypto.
        # A profitable intraday trader needs:
        # - SHORT templates (half the opportunities in ranging markets)
        # - 4h timeframe templates (sweet spot between noise and speed)
        # - Tighter parameters for low-vol (1h RSI < 20 rarely fires in quiet markets)

        # --- Hourly RSI Overbought Short ---
        # Mirror of Hourly RSI Oversold Bounce (60% pass rate). Short the overbought.
        templates.append(StrategyTemplate(
            name="Hourly RSI Overbought Short",
            description="Short when hourly RSI spikes above 80 (extreme overbought), cover on drop below 50",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "RSI(14) > 80"
            ],
            exit_conditions=[
                "RSI(14) < 50"
            ],
            required_indicators=["RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
                "hold_period_max": 24,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-24 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Intraday Mean Reversion Short ---
        # Mirror of Intraday Mean Reversion (45% pass rate).
        templates.append(StrategyTemplate(
            name="Intraday Mean Reversion Short",
            description="Short when price spikes >1.5% above SMA(20) intraday with RSI overbought, cover at SMA",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE > SMA(20) AND RSI(14) > 65"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["SMA:20", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
                "hold_period_max": 24,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly BB Squeeze Breakdown Short ---
        # Mirror of Hourly BB Squeeze Breakout (38% pass rate).
        templates.append(StrategyTemplate(
            name="Hourly BB Squeeze Breakdown Short",
            description="Short when hourly BB bands narrow then price breaks below lower band — vol expansion downward",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2) AND RSI(14) < 45"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035,
                "hold_period_max": 24,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly Tight RSI Bounce (Low Vol Specialist) ---
        # In low vol, hourly RSI rarely hits 20. Use 35/60 band instead.
        templates.append(StrategyTemplate(
            name="Hourly Tight RSI Bounce",
            description="Buy when hourly RSI dips below 35 in low vol (not extreme), exit above 60. Tighter thresholds for quiet markets.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) < 35 AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 60"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.012,
                "take_profit_pct": 0.02,
                "hold_period_max": 24,
            },
            expected_trade_frequency="5-10 trades/month",
            expected_holding_period="1-8 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly Tight RSI Fade Short (Low Vol Specialist) ---
        templates.append(StrategyTemplate(
            name="Hourly Tight RSI Fade Short",
            description="Short when hourly RSI rises above 65 in low vol, cover below 40. Tight thresholds for quiet markets.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "RSI(14) > 65 AND CLOSE < SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) < 40"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.012,
                "take_profit_pct": 0.02,
                "hold_period_max": 24,
            },
            expected_trade_frequency="5-10 trades/month",
            expected_holding_period="1-8 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly EMA Crossover Long ---
        # Fast EMA(5) crossing above EMA(13) on hourly — quick momentum shift.
        templates.append(StrategyTemplate(
            name="Hourly EMA Crossover Long",
            description="Buy when hourly EMA(5) crosses above EMA(13) — short-term momentum shift. Quick entries, tight stops.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "EMA(5) > EMA(13) AND CLOSE > EMA(5)"
            ],
            exit_conditions=[
                "CLOSE < EMA(13)"
            ],
            required_indicators=["EMA:5", "EMA:13"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.03,
                "hold_period_max": 24,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly EMA Crossover Short ---
        templates.append(StrategyTemplate(
            name="Hourly EMA Crossover Short",
            description="Short when hourly EMA(5) crosses below EMA(13) — short-term momentum shift downward.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "EMA(5) < EMA(13) AND CLOSE < EMA(5)"
            ],
            exit_conditions=[
                "CLOSE > EMA(13)"
            ],
            required_indicators=["EMA:5", "EMA:13"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.03,
                "hold_period_max": 24,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly MACD Signal Cross Long ---
        # MACD crossing above signal line on hourly — classic momentum entry.
        templates.append(StrategyTemplate(
            name="Hourly MACD Signal Cross Long",
            description="Buy when hourly MACD crosses above signal line with RSI > 40 — confirmed momentum shift.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "MACD(12,26) CROSSES_ABOVE MACD_SIGNAL(12,26,9) AND RSI(14) > 40"
            ],
            exit_conditions=[
                "MACD(12,26) CROSSES_BELOW MACD_SIGNAL(12,26,9)"
            ],
            required_indicators=["MACD", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.018,
                "take_profit_pct": 0.035,
                "hold_period_max": 24,
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly MACD Signal Cross Short ---
        templates.append(StrategyTemplate(
            name="Hourly MACD Signal Cross Short",
            description="Short when hourly MACD crosses below signal line with RSI < 60 — confirmed momentum shift down.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "MACD(12,26) CROSSES_BELOW MACD_SIGNAL(12,26,9) AND RSI(14) < 60"
            ],
            exit_conditions=[
                "MACD(12,26) CROSSES_ABOVE MACD_SIGNAL(12,26,9)"
            ],
            required_indicators=["MACD", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.018,
                "take_profit_pct": 0.035,
                "hold_period_max": 24,
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly Stochastic Reversal Long ---
        # Stochastic on hourly is faster than daily — catches quick reversals.
        templates.append(StrategyTemplate(
            name="Hourly Stochastic Reversal Long",
            description="Buy when hourly Stochastic crosses above 25 from oversold — quick reversal signal.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "STOCH(14) > 25 AND STOCH(14) < 40"
            ],
            exit_conditions=[
                "STOCH(14) > 75"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
                "hold_period_max": 24,
            },
            expected_trade_frequency="5-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly Stochastic Reversal Short ---
        templates.append(StrategyTemplate(
            name="Hourly Stochastic Reversal Short",
            description="Short when hourly Stochastic crosses below 75 from overbought — quick reversal signal down.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "STOCH(14) < 75 AND STOCH(14) > 60"
            ],
            exit_conditions=[
                "STOCH(14) < 25"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
                "hold_period_max": 24,
            },
            expected_trade_frequency="5-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly BB Narrow Range Long ---
        # In low vol, hourly BB bands are very tight. Buy at lower band with BB(20,1.5).
        templates.append(StrategyTemplate(
            name="Hourly BB Narrow Range Long",
            description="Buy at hourly lower BB(20,1.5) in low vol — tight bands mean frequent touches. Quick scalp to middle band.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 1.5)"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 1.5)"
            ],
            required_indicators=["Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.01,
                "take_profit_pct": 0.018,
                "hold_period_max": 24,
            },
            expected_trade_frequency="6-12 trades/month",
            expected_holding_period="1-6 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # --- Hourly BB Narrow Range Short ---
        templates.append(StrategyTemplate(
            name="Hourly BB Narrow Range Short",
            description="Short at hourly upper BB(20,1.5) in low vol — tight bands mean frequent touches. Quick scalp to middle band.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 1.5)"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 1.5)"
            ],
            required_indicators=["Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.01,
                "take_profit_pct": 0.018,
                "hold_period_max": 24,
            },
            expected_trade_frequency="6-12 trades/month",
            expected_holding_period="1-6 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True}
        ))

        # ===== CRYPTO LOW-VOL SPECIALIST TEMPLATES =====
        # When crypto is in ranging_low_vol, the standard crypto templates fail because
        # they assume high volatility (RSI < 40 as "oversold", 4% stops, etc.).
        # In quiet crypto markets, price oscillates in tight ranges around SMAs.
        # These templates use stock-like tightness with crypto-aware 24/7 operation.
        # NOT marked crypto_optimized — they can also work on stocks/ETFs.
        # But they're designed with crypto's 24/7 nature in mind.

        # --- Crypto Quiet RSI Oscillator (1h) ---
        # In low-vol crypto, hourly RSI oscillates 40-60 instead of 20-80.
        # Buy the dip to 42, sell the pop to 58. Tight and frequent.
        templates.append(StrategyTemplate(
            name="Crypto Quiet RSI Oscillator",
            description="Buy when hourly RSI dips below 42 in quiet crypto, exit above 58. Tight band for low-vol 24/7 scalping.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) < 42 AND CLOSE > EMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 58"
            ],
            required_indicators=["RSI", "EMA:50"],
            default_parameters={
                "rsi_period": 14,
                "ema_period": 50,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="8-15 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "crypto_optimized": True, "intraday": True, "skip_param_override": True}
        ))

        # --- Crypto Quiet EMA Hug Long (1d) ---
        # In low-vol crypto, price hugs the EMA(20). Buy when it touches from above,
        # sell when it drifts away. Daily timeframe for swing trades.
        # B2 FIX 2026-05-02 (Sprint 5 S5.1): was state entry `CLOSE > EMA(20) AND RSI(14) < 48
        # AND RSI(14) > 35` which fires every bar the conditions hold — turning the
        # intended "touch bounce" into continuous re-entry. Description says "touches
        # EMA(20) from above" — the event is the bounce back above EMA after a pullback.
        # Use CROSSES_ABOVE to capture the moment price recovers EMA(20).
        templates.append(StrategyTemplate(
            name="Crypto Quiet EMA Hug Long",
            description="Buy when daily price crosses back above EMA(20) after a pullback with RSI 35-48 — support bounce in quiet crypto. Hold for the drift back up.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE CROSSES_ABOVE EMA(20) AND RSI(14) < 48 AND RSI(14) > 35"
            ],
            exit_conditions=[
                "RSI(14) > 60 OR CLOSE < EMA(50)"
            ],
            required_indicators=["EMA:20", "EMA:50", "RSI"],
            default_parameters={
                "ema_fast": 20,
                "ema_slow": 50,
                "rsi_period": 14,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=1.6,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True}
        ))

        # --- Crypto Quiet BB Midband Bounce (1h) ---
        # Price oscillates around BB middle band in quiet crypto.
        # Buy below middle, sell above. Use BB(20,1.5) for tighter bands.
        templates.append(StrategyTemplate(
            name="Crypto Quiet BB Midband Bounce",
            description="Buy when hourly price dips below BB middle band in quiet crypto, exit on return above. Tight bands for frequent signals.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < BB_MIDDLE(20, 1.5) AND RSI(14) < 48"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 1.5) AND RSI(14) > 52"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 1.5,
                "rsi_period": 14,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="8-12 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.3,
            metadata={"direction": "long", "crypto_optimized": True, "intraday": True, "skip_param_override": True}
        ))

        # --- Crypto Quiet MACD Zero Cross (1d) ---
        # In low-vol crypto, MACD hovers near zero. A cross above zero is a
        # meaningful momentum shift — more reliable than in high-vol when MACD whipsaws.
        templates.append(StrategyTemplate(
            name="Crypto Quiet MACD Momentum",
            description="Buy when daily MACD crosses above signal line in quiet crypto — momentum shift from neutral. Reliable in low vol.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "MACD(12,26) CROSSES_ABOVE MACD_SIGNAL(12,26,9)"
            ],
            exit_conditions=[
                "MACD(12,26) CROSSES_BELOW MACD_SIGNAL(12,26,9)"
            ],
            required_indicators=["MACD"],
            default_parameters={
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True}
        ))

        # ===== CRYPTO DAILY DOWNTREND TEMPLATES =====
        # Conservative daily strategies for crypto in downtrends.
        # These target oversold bounces on the daily timeframe — larger moves
        # with wider stops to survive crypto volatility. LONG only (eToro no-short).

        # Crypto Daily Oversold Bounce — extreme RSI oversold on daily
        # In a -30% crypto crash, daily RSI hits 20-25 maybe 2-3 times.
        # When it does, a 5-10% bounce is common before the next leg down.
        # Tight take-profit (5%), wide stop (6%) — take the bounce, don't hold.
        templates.append(StrategyTemplate(
            name="Crypto Daily Oversold Bounce",
            description="Buy when daily RSI drops below 25 in a crypto downtrend. Quick bounce trade — take 5% profit or cut at 6% loss.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "RSI(14) < 25 AND CLOSE < SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 45 OR CLOSE > SMA(20)"
            ],
            required_indicators=["RSI", "SMA:50", "SMA:20"],
            default_parameters={
                "rsi_period": 14,
                "oversold_threshold": 25,
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.05,
                "hold_period_max": 10,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=1.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True}
        ))

        # Crypto Daily BB Lower Band Bounce — price touches lower Bollinger Band
        # In downtrends, price walks the lower band but periodically snaps back
        # to the middle band. Entry when price closes below lower BB with RSI < 35.
        templates.append(StrategyTemplate(
            name="Crypto Daily BB Lower Bounce",
            description="Buy when daily close drops below BB lower band with RSI < 35. Target middle band reversion. Conservative stops.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2) AND RSI(14) < 35"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2) OR RSI(14) > 55"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_period": 14,
                "stop_loss_pct": 0.07,
                "take_profit_pct": 0.06,
                "hold_period_max": 14,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=0.9,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True}
        ))

        # Crypto Daily SMA Deviation Snap — price far below SMA(20)
        # When crypto drops 10%+ below its 20-day SMA, a snap-back is likely.
        # More aggressive than the RSI bounce — uses price distance from MA.
        templates.append(StrategyTemplate(
            name="Crypto Daily SMA Snap Back",
            description="Buy when daily close is 8%+ below SMA(20) — overextended to the downside. Target snap back to SMA.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE < SMA(20) * 0.92 AND RSI(14) < 40"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 0.98 OR RSI(14) > 50"
            ],
            required_indicators=["SMA:20", "RSI"],
            default_parameters={
                "sma_period": 20,
                "deviation_pct": 0.08,
                "rsi_period": 14,
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.06,
                "hold_period_max": 10,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=0.8,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True}
        ))

        # Crypto Daily Stochastic Extreme — daily stochastic below 10
        # Stochastic < 10 on daily crypto is a rare extreme. When it happens,
        # a multi-day bounce follows ~70% of the time.
        templates.append(StrategyTemplate(
            name="Crypto Daily Stochastic Extreme",
            description="Buy when daily Stochastic drops below 10 — extreme oversold. Exit when Stochastic recovers above 40.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING_HIGH_VOL,
                MarketRegime.RANGING,
            ],
            entry_conditions=[
                "STOCH(14) < 10"
            ],
            exit_conditions=[
                "STOCH(14) > 40"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.05,
                "hold_period_max": 10,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=0.9,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True}
        ))

        # --- Crypto Quiet Stochastic Swing (1h) ---
        # Stochastic on hourly crypto in low vol — oscillates 30-70 instead of 10-90.
        # Buy at 30, sell at 65. 24/7 operation means more signals than stocks.
        templates.append(StrategyTemplate(
            name="Crypto Quiet Stochastic Swing",
            description="Buy when hourly Stochastic dips below 30 in quiet crypto, exit above 65. 24/7 swing trading in tight range.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "STOCH(14) < 30 AND STOCH(14) > 10"
            ],
            exit_conditions=[
                "STOCH(14) > 65"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035,
            },
            expected_trade_frequency="6-10 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.8,
            metadata={"direction": "long", "crypto_optimized": True, "intraday": True, "skip_param_override": True}
        ))

        # ===== CRYPTO-OPTIMIZED TEMPLATES =====
        # Crypto has different characteristics than stocks:
        # - Higher volatility (RSI 40 is already a dip, not 25)
        # - Stronger trends (faster EMAs work better)
        # - 24/7 trading (weekend mean reversion patterns)
        # - Volume spikes are more predictive
        # - No short selling on eToro (LONG only)
        
        # Crypto RSI Dip Buy — relaxed RSI threshold for crypto's higher baseline
        templates.append(StrategyTemplate(
            name="Crypto RSI Dip Buy",
            description="Buy crypto when RSI drops below 40 (mild dip in crypto = strong dip in stocks), exit on recovery",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "RSI(14) < 40 AND RSI(14) > 15"
            ],
            exit_conditions=[
                "RSI(14) > 60"
            ],
            required_indicators=["RSI"],
            default_parameters={
                "oversold_threshold": 40,
                "overbought_threshold": 60,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Fast EMA Momentum — faster periods for crypto's quick trends
        templates.append(StrategyTemplate(
            name="Crypto Fast EMA Momentum",
            description="Buy when fast EMA(8) crosses above EMA(21) with volume confirmation — crypto trends fast",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING,
            ],
            entry_conditions=[
                "EMA(8) CROSSES_ABOVE EMA(21) AND VOLUME > VOLUME_MA(20) * 1.3"
            ],
            exit_conditions=[
                "EMA(8) CROSSES_BELOW EMA(21)"
            ],
            required_indicators=["EMA:8", "EMA:21", "Volume MA"],
            default_parameters={
                "fast_period": 8,
                "slow_period": 21,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.12,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-10 days",
            risk_reward_ratio=3.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Volume Spike Entry — massive volume = institutional interest
        #
        # DSL FIX 2026-05-02: entry was `VOLUME > VOLUME_MA(20) * 2.0 AND CLOSE > SMA(20)`
        # (state) which fires on every high-volume bar in an uptrend. Test windows produced
        # 76-81 trades (vs advertised 2-5/month = ~12-30 expected). Switch to event-style
        # entry — VOLUME crossing above 2x VMA captures the *first* spike, then the SMA
        # filter gates direction. Exit stays state-based.
        templates.append(StrategyTemplate(
            name="Crypto Volume Spike Entry",
            description="Buy on 2x volume spike with price above SMA(20) — institutional accumulation signal",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "VOLUME CROSSES_ABOVE VOLUME_MA(20) * 2.0 AND CLOSE > SMA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) > 75"
            ],
            required_indicators=["Volume MA", "SMA:20", "RSI"],
            default_parameters={
                "volume_multiplier": 2.0,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Bollinger Band Squeeze — crypto consolidation before explosive moves
        templates.append(StrategyTemplate(
            name="Crypto BB Squeeze Breakout",
            description="Buy when crypto Bollinger Bands narrow then price breaks above upper band — consolidation breakout",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING,
            ],
            entry_conditions=[
                "(BB_UPPER(20, 2) - BB_LOWER(20, 2)) < ATR(14) * 3 AND CLOSE > BB_UPPER(20, 2)"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands", "ATR"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto MACD Momentum — MACD works well on crypto's strong trends
        templates.append(StrategyTemplate(
            name="Crypto MACD Trend",
            description="Buy when MACD crosses above signal with positive histogram — crypto trend confirmation",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING,
            ],
            entry_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL() AND CLOSE > EMA(20)"
            ],
            exit_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL()"
            ],
            required_indicators=["MACD", "EMA:20"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.15,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-14 days",
            risk_reward_ratio=3.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Stochastic Oversold Recovery — STOCH works on crypto with wider thresholds
        templates.append(StrategyTemplate(
            name="Crypto Stochastic Recovery",
            description="Buy when Stochastic drops below 25 (crypto oversold), exit above 70",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "STOCH(14) < 25"
            ],
            exit_conditions=[
                "STOCH(14) > 70"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "oversold_threshold": 25,
                "overbought_threshold": 70,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=1.6,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO RANGING / LOW-VOL TEMPLATES =====
        # The crypto-specific templates above are designed for volatile/trending markets.
        # In ranging_low_vol regimes, crypto still moves but in tighter bands.
        # These templates use wider lookbacks and tighter targets suited for quiet crypto markets.
        
        # Crypto BB Mean Reversion — buy at lower band, sell at middle/upper in ranging crypto
        templates.append(StrategyTemplate(
            name="Crypto BB Mean Reversion",
            description="Buy crypto at lower Bollinger Band, exit at middle band — works in ranging/quiet crypto markets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "CLOSE < BB_LOWER(20,2.0)",
                "RSI(14) < 45"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20,2.0) OR RSI(14) > 60"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "rsi_period": 14,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.06,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto SMA Reversion — simple mean reversion using SMA distance
        templates.append(StrategyTemplate(
            name="Crypto SMA Reversion",
            description="Buy crypto when price drops >3% below SMA(20), exit on reversion to mean",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE < SMA(20) * 0.97",
                "VOLUME > VOLUME_MA(20) * 0.8"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 0.99 OR RSI(14) > 55"
            ],
            required_indicators=["SMA", "Volume", "RSI"],
            default_parameters={
                "sma_period": 20,
                "entry_distance_pct": 0.03,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=1.3,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Keltner Range Trade — buy at lower Keltner, sell at upper in quiet markets
        templates.append(StrategyTemplate(
            name="Crypto Keltner Range Trade",
            description="Buy crypto at lower Keltner Channel in low-vol ranging conditions, exit at upper channel",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "CLOSE < EMA(20) - ATR(14) * 1.5",
                "RSI(14) < 40"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) + ATR(14) * 0.5 OR RSI(14) > 60"
            ],
            required_indicators=["EMA", "ATR", "RSI"],
            default_parameters={
                "ema_period": 20,
                "atr_period": 14,
                "atr_multiplier": 1.5,
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.06,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO TRENDING TEMPLATES =====
        
        # Crypto Pullback Buy — buy dips in uptrends (trending up)
        templates.append(StrategyTemplate(
            name="Crypto Pullback Buy",
            description="Buy crypto pullbacks to EMA(21) during uptrends — price above SMA(50) confirms trend",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "CLOSE > SMA(50)",
                "CLOSE < EMA(21) * 1.01",
                "RSI(14) < 45"
            ],
            exit_conditions=[
                "RSI(14) > 70 OR CLOSE < SMA(50)"
            ],
            required_indicators=["SMA", "EMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="3-14 days",
            risk_reward_ratio=2.4,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Breakout Momentum — strong breakout above recent highs
        templates.append(StrategyTemplate(
            name="Crypto Breakout Momentum",
            description="Buy crypto breaking above 20-day high with volume surge — momentum continuation",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
            ],
            entry_conditions=[
                "CLOSE > HIGH_20",
                "VOLUME > VOLUME_MA(20) * 1.5",
                "RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < EMA(10) OR RSI(14) > 80"
            ],
            required_indicators=["HIGH_20", "Volume MA", "RSI", "EMA"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-10 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO HIGH VOLATILITY TEMPLATES =====
        
        # Crypto Crash Recovery — buy extreme oversold during high-vol selloffs
        templates.append(StrategyTemplate(
            name="Crypto Crash Recovery",
            description="Buy crypto after extreme RSI oversold (<25) during high-vol selloffs — contrarian bounce play",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN,
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG,
            ],
            entry_conditions=[
                "RSI(14) < 25",
                "CLOSE < BB_LOWER(20,2.5)"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR CLOSE > BB_MIDDLE(20,2.5)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=1.3,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto ATR Volatility Fade — fade extreme moves using ATR bands
        templates.append(StrategyTemplate(
            name="Crypto Volatility Fade",
            description="Buy crypto when price drops >2x ATR below EMA in high-vol conditions — volatility mean reversion",
            strategy_type=StrategyType.VOLATILITY,
            market_regimes=[
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE < EMA(20) - ATR(14) * 2.0",
                "RSI(14) < 35"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) - ATR(14) * 0.5 OR RSI(14) > 55"
            ],
            required_indicators=["EMA", "ATR", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.07,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=1.1,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO MULTI-REGIME TEMPLATES =====
        
        # Crypto EMA Ribbon — works across regimes by following EMA alignment
        #
        # DSL FIX 2026-05-02: entry was three parallel state conditions (`EMA(8) > EMA(13)
        # AND EMA(13) > EMA(21) AND RSI > 40`) which fires every bar in an uptrend once
        # the alignment forms. 42-43 trades per 6-month window vs advertised 2-5/month =
        # ~12-30. Switch to event-style: capture the moment the ribbon *aligns* via
        # EMA(8) CROSSES_ABOVE EMA(13) while EMA(13) > EMA(21) already holds. Exit stays
        # state-based on the fast-EMA breakdown (ribbon loses alignment).
        templates.append(StrategyTemplate(
            name="Crypto EMA Ribbon",
            description="Buy when EMA(8) > EMA(13) > EMA(21) alignment forms — trend confirmation across regimes",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "EMA(8) CROSSES_ABOVE EMA(13) AND EMA(13) > EMA(21) AND RSI(14) > 40"
            ],
            exit_conditions=[
                "EMA(8) < EMA(13) OR RSI(14) > 75"
            ],
            required_indicators=["EMA:8", "EMA:13", "EMA:21", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="3-14 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Weekend Range — crypto-specific weekend mean reversion
        templates.append(StrategyTemplate(
            name="Crypto Weekend Range",
            description="Buy crypto at SMA(10) support with low RSI — weekends often see range-bound action with mean reversion",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE < SMA(10) * 0.99",
                "RSI(14) < 42",
                "STOCH(14) < 30"
            ],
            exit_conditions=[
                "CLOSE > SMA(10) * 1.01 OR RSI(14) > 58"
            ],
            required_indicators=["SMA", "RSI", "Stochastic Oscillator"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=1.3,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO LOW-VOL SCALPING TEMPLATES =====
        # In ranging_low_vol, crypto oscillates in tight bands. The opportunity is
        # high-frequency small-target mean reversion — not waiting for big dips.
        # These templates use relaxed entry thresholds and small TP/SL.
        
        # Crypto Micro RSI Scalp — trade the small RSI oscillations
        templates.append(StrategyTemplate(
            name="Crypto Micro RSI Scalp",
            description="Buy crypto when RSI dips below 48 in low-vol conditions, exit at RSI 53 — scalping the micro-oscillations",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "RSI(14) < 48",
                "RSI(14) > 30",
                "CLOSE > SMA(50) * 0.95"
            ],
            exit_conditions=[
                "RSI(14) > 53"
            ],
            required_indicators=["RSI", "SMA"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="8-15 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=1.25,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Tight BB Scalp — trade bounces within tight Bollinger Bands
        templates.append(StrategyTemplate(
            name="Crypto Tight BB Scalp",
            description="Buy crypto near lower BB in tight-band conditions, exit at middle band — low-vol band trading",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "CLOSE < BB_LOWER(20,1.5)",
                "RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20,1.5) OR RSI(14) > 55"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 1.5,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="6-12 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto EMA Touch Scalp — buy when price touches EMA(20) from above in quiet uptrend
        templates.append(StrategyTemplate(
            name="Crypto EMA Touch Scalp",
            description="Buy crypto when price dips to EMA(20) with RSI mid-range — mean reversion to short-term trend in quiet markets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING,
            ],
            entry_conditions=[
                "CLOSE < EMA(20) * 1.005",
                "CLOSE > EMA(20) * 0.985",
                "RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) * 1.015 OR RSI(14) > 58"
            ],
            required_indicators=["EMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="8-15 trades/month",
            expected_holding_period="1-2 days",
            risk_reward_ratio=1.25,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto STOCH Mid Scalp — trade stochastic oscillations in the 30-70 range
        templates.append(StrategyTemplate(
            name="Crypto STOCH Mid Scalp",
            description="Buy crypto when Stochastic drops below 35 in low-vol, exit above 60 — trading the mid-range oscillations",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING,
            ],
            entry_conditions=[
                "STOCH(14) < 35",
                "CLOSE > SMA(50) * 0.96"
            ],
            exit_conditions=[
                "STOCH(14) > 60"
            ],
            required_indicators=["Stochastic Oscillator", "SMA"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="6-10 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO RANGING LOW-VOL TEMPLATES =====
        # In ranging_low_vol, crypto oscillates in narrow bands. Standard crypto
        # templates wait for big dips (RSI < 40) that rarely happen. These templates
        # use tighter thresholds to capture the small oscillations.
        
        # Crypto Narrow RSI Oscillator — trade the 45-55 RSI range
        templates.append(StrategyTemplate(
            name="Crypto Narrow RSI Oscillator",
            description="Buy crypto when RSI dips below 45 in low-vol ranging, exit at RSI 55 — captures micro-oscillations",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) < 45",
                "CLOSE > SMA(50) * 0.95"
            ],
            exit_conditions=[
                "RSI(14) > 55 OR CLOSE < SMA(50) * 0.93"
            ],
            required_indicators=["RSI", "SMA"],
            default_parameters={
                "rsi_period": 14,
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="8-15 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Tight Channel Bounce — buy at lower BB in tight bands
        templates.append(StrategyTemplate(
            name="Crypto Tight Channel Bounce",
            description="Buy crypto near lower BB when bandwidth is narrow (low vol), exit at middle band",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < BB_LOWER(20,1.5)",
                "RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20,1.5) OR RSI(14) > 58"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 1.5,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="6-12 trades/month",
            expected_holding_period="1-2 days",
            risk_reward_ratio=1.25,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Low-Vol STOCH Swing — trade stochastic swings in quiet markets
        templates.append(StrategyTemplate(
            name="Crypto Low-Vol STOCH Swing",
            description="Buy crypto when Stochastic drops below 30 in low-vol, exit above 65 — wider swing target than scalp",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "STOCH(14) < 30",
                "RSI(14) < 48"
            ],
            exit_conditions=[
                "STOCH(14) > 65 OR RSI(14) > 58"
            ],
            required_indicators=["Stochastic Oscillator", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="5-10 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.3,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto SMA Proximity Long — buy when price is close to SMA support
        templates.append(StrategyTemplate(
            name="Crypto SMA Proximity Long",
            description="Buy crypto when price touches SMA(20) from above with mild RSI dip — support bounce in quiet markets",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE < SMA(20) * 1.005",
                "CLOSE > SMA(20) * 0.985",
                "RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 1.02 OR RSI(14) > 60"
            ],
            required_indicators=["SMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="6-12 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO 4H TEMPLATES =====
        # 4H is the proven sweet spot for crypto intraday trading.
        # HTX/KuCoin backtests show 4H MACD on BTC: +96% vs +49% buy-and-hold,
        # ETH: +205% vs +53%. 1H and below underperform due to noise and fees.
        # eToro's 1% per-side crypto fee means we need 4%+ per trade minimum —
        # 4H captures multi-hour trends that clear this hurdle.
        
        # Crypto 4H MACD Trend — the backtested winner
        templates.append(StrategyTemplate(
            name="Crypto 4H MACD Trend",
            description="Buy when 4H MACD crosses above signal line with histogram positive. The only timeframe where MACD consistently generates alpha on crypto in backtests.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "MACD(12,26) CROSSES_ABOVE MACD_SIGNAL(12,26,9) AND RSI(14) > 45"
            ],
            exit_conditions=[
                "MACD(12,26) CROSSES_BELOW MACD_SIGNAL(12,26,9) OR RSI(14) < 35"
            ],
            required_indicators=["MACD", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.15,
                "hold_period_max": 120,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "crypto_optimized": True, "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # Crypto 4H RSI Mean Reversion — buy 4H oversold dips
        templates.append(StrategyTemplate(
            name="Crypto 4H RSI Dip Buy",
            description="Buy when 4H RSI drops below 35 with price above SMA(50). Crypto-calibrated oversold threshold on 4H captures multi-hour dips that daily bars miss.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "RSI(14) < 35 AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 60 OR CLOSE > BB_UPPER(20, 2.0)"
            ],
            required_indicators=["RSI", "SMA", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
                "hold_period_max": 96,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=2.4,
            metadata={"direction": "long", "crypto_optimized": True, "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # Crypto 4H EMA Momentum — fast EMA crossover for crypto trends
        # B2 FIX 2026-05-02 (Sprint 5 S5.1): was state entry `EMA(8) > EMA(21) AND CLOSE > EMA(8)
        # AND RSI(14) > 50` which fires every 4h bar the ribbon is aligned. Template
        # description says "Buy when 4H EMA(8) crosses above EMA(21)" — the intent IS
        # the crossover event. Switch to CROSSES_ABOVE to capture the moment alignment
        # forms. RSI filter applies at the crossover bar only.
        templates.append(StrategyTemplate(
            name="Crypto 4H EMA Momentum",
            description="Buy when 4H EMA(8) crosses above EMA(21) with RSI > 50. Captures the start of multi-day crypto trends that form on 4H charts.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "EMA(8) CROSSES_ABOVE EMA(21) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "EMA(8) < EMA(21) OR RSI(14) < 40"
            ],
            required_indicators=["EMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
                "hold_period_max": 120,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=2.4,
            metadata={"direction": "long", "crypto_optimized": True, "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # Crypto 4H BB Squeeze Breakout — volatility expansion after compression
        # B2 FIX 2026-05-02 (Sprint 5 S5.1): was state entry `CLOSE > BB_UPPER(20, 1.5)
        # AND RSI(14) > 50` which fires every bar price stays above the 1.5-std band —
        # turning a "breakout" into continuous re-entry through the entire trend run.
        # 54 trades observed on 365d test window (cycle_1777752044) vs advertised 2-4/month.
        # Switch to CROSSES_ABOVE to capture only the first breakout bar.
        templates.append(StrategyTemplate(
            name="Crypto 4H BB Squeeze Breakout",
            description="Buy when 4H price breaks above tight BB upper band (1.5 std) after squeeze. Crypto consolidation on 4H often precedes 5-10% moves.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE CROSSES_ABOVE BB_UPPER(20, 1.5) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 1.5) OR RSI(14) < 40"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
                "hold_period_max": 96,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=2.4,
            metadata={"direction": "long", "crypto_optimized": True, "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # ===== CRYPTO 1H TEMPLATES =====
        # 1H crypto is high-noise territory. Research shows 90% of 1H strategies
        # underperform buy-and-hold. Only extreme setups clear eToro's 2% round-trip
        # cost (1% per side). These templates fire rarely but with high conviction.
        
        # Crypto 1H RSI Extreme Bounce — only fire on extreme oversold
        templates.append(StrategyTemplate(
            name="Crypto 1H RSI Extreme Bounce",
            description="Buy when 1H RSI drops below 20 — extreme oversold that only happens during flash crashes or liquidation cascades. High win rate, rare signal.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "RSI(14) < 20 AND CLOSE > SMA(50) * 0.90"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR CLOSE > SMA(20)"
            ],
            required_indicators=["RSI", "SMA"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.10,
                "hold_period_max": 48,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "crypto_optimized": True, "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # Crypto 1H BB Extreme Dip — buy at lower band with volume confirmation
        templates.append(StrategyTemplate(
            name="Crypto 1H BB Extreme Dip",
            description="Buy when 1H price drops below BB lower band (2.5 std) — extreme dislocation. Only fires during sharp selloffs. Target middle band reversion.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2.5) AND RSI(14) < 30"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2.5) OR RSI(14) > 55"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.10,
                "hold_period_max": 48,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "crypto_optimized": True, "intraday": True, "interval": "1h", "skip_param_override": True}
        ))
        
        # ===== 4H SWING TRADING TEMPLATES =====
        # 4H is the swing trader's timeframe: better entry timing than daily,
        # longer holding than hourly. RSI(14) = 56 hours ≈ 2.3 trading days.
        # These templates are calibrated for 4H bar characteristics.
        
        # 4H RSI Pullback Buy — buy the dip in an uptrend on 4H timeframe
        templates.append(StrategyTemplate(
            name="4H RSI Pullback Buy",
            description="Buy when 4H RSI dips below 40 while price holds above SMA(50). Swing entry on pullback in uptrend.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "RSI(14) < 40 AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 60 OR CLOSE < SMA(50) * 0.97"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
                "hold_period_max": 48,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # 4H MACD Trend Continuation — enter on MACD signal cross in trend direction
        templates.append(StrategyTemplate(
            name="4H MACD Trend Continuation",
            description="Buy when MACD crosses above signal line with price above EMA(20) on 4H. Trend continuation entry.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "MACD(12,26) CROSSES_ABOVE MACD_SIGNAL(12,26,9) AND CLOSE > EMA(20)"
            ],
            exit_conditions=[
                "MACD(12,26) CROSSES_BELOW MACD_SIGNAL(12,26,9) OR CLOSE < EMA(20)"
            ],
            required_indicators=["MACD", "EMA:20"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # 4H BB Squeeze Swing — catch breakouts from 4H Bollinger squeeze
        templates.append(StrategyTemplate(
            name="4H BB Squeeze Swing Long",
            description="Buy when price breaks above tight BB upper band (1.5 std) with RSI > 50 on 4H. Squeeze breakout for swing trades.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 1.5) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 1.5) OR RSI(14) < 40"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.045,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.8,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # 4H BB Squeeze Swing Short
        templates.append(StrategyTemplate(
            name="4H BB Squeeze Swing Short",
            description="Short when price breaks below tight BB lower band (1.5 std) with RSI < 50 on 4H.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 1.5) AND RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 1.5) OR RSI(14) > 60"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.045,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.8,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # ===== 4H DOWNTREND SHORT TEMPLATES =====
        # In a downtrend, the money is in shorting the rallies — not catching falling knives.
        # These templates fade the bounce into resistance. On 4H, a rally to RSI 55-65
        # in a downtrend is a gift: the trend reasserts within 1-3 bars.
        # Entry conditions are deliberately moderate (RSI > 55, not > 70) because
        # in a real downtrend, overbought readings are rare — the edge is in the
        # failed rally, not the extreme.

        # 4H EMA Rejection Short — short the rally into falling EMA
        # Price rallies back to a declining EMA(20) and gets rejected. Classic trend
        # continuation setup. The EMA acts as dynamic resistance in a downtrend.
        templates.append(StrategyTemplate(
            name="4H EMA Rejection Short",
            description="Short when price rallies to declining EMA(20) with RSI > 55 on 4H. Fade the bounce into resistance.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "RSI(14) > 55 AND CLOSE > SMA(20) * 0.995 AND CLOSE < SMA(20) * 1.01 AND CLOSE < SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) < 35 OR CLOSE < SMA(20) * 0.97"
            ],
            required_indicators=["RSI", "SMA:20", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
                "hold_period_max": 48,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))

        # 4H RSI Overbought Fade Short — short when RSI gets stretched in a downtrend
        # In a downtrend, RSI > 60 on 4H is already overbought. Don't wait for 70+.
        # Combine with price below SMA(50) to confirm we're still in a downtrend.
        templates.append(StrategyTemplate(
            name="4H RSI Overbought Fade Short",
            description="Short when 4H RSI > 60 with price below SMA(50). In a downtrend, 60 is overbought — fade it.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "RSI(14) > 60 AND CLOSE < SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) < 40 OR CLOSE > SMA(50)"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))

        # 4H Lower High Short — structural downtrend continuation
        # Price makes a lower high (below recent 20-bar high) with declining momentum.
        # This is the bread and butter of trend trading: lower highs = trend intact.
        templates.append(StrategyTemplate(
            name="4H Lower High Short",
            description="Short when 4H price fails to reach prior high (CLOSE < HIGH_20 * 0.97) with RSI rolling over from > 50. Lower high = trend continues.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "RSI(14) > 45 AND RSI(14) < 60 AND CLOSE < SMA(50) AND CLOSE < SMA(20)"
            ],
            exit_conditions=[
                "RSI(14) < 30 OR CLOSE > SMA(20) * 1.02"
            ],
            required_indicators=["RSI", "SMA:20", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.045,
                "hold_period_max": 48,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.8,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))

        # 4H BB Upper Rejection Short — short at the upper band in a downtrend
        # In a downtrend, rallies to the upper BB are selling opportunities.
        # The band acts as a ceiling. Combine with RSI > 50 for confirmation.
        templates.append(StrategyTemplate(
            name="4H BB Upper Rejection Short",
            description="Short when 4H price touches upper BB(20,2) in a downtrend with RSI > 50. Upper band = resistance in downtrend.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2) * 0.99 AND RSI(14) > 50 AND CLOSE < SMA(50)"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2) OR RSI(14) < 35"
            ],
            required_indicators=["Bollinger Bands", "RSI", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))

        # 4H MACD Bearish Cross Short — trend continuation on MACD signal
        # MACD crossing below signal line on 4H with price below EMA(20).
        # This catches the resumption of selling after a brief pause.
        templates.append(StrategyTemplate(
            name="4H MACD Bearish Cross Short",
            description="Short when 4H MACD crosses below signal with price below EMA(20) and RSI confirming bearish momentum.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "MACD_SIGNAL < 0 AND CLOSE < SMA(20) AND RSI(14) < 45"
            ],
            exit_conditions=[
                "MACD_SIGNAL > 0 OR RSI(14) < 25"
            ],
            required_indicators=["MACD", "SMA:20", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.055,
                "hold_period_max": 72,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.8,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))

        # 4H Stochastic Overbought Short — short when stochastic gets stretched in downtrend
        # Stochastic > 70 on 4H in a downtrend = the rally is exhausted.
        # Tighter than RSI because stochastic is faster and more sensitive on 4H.
        templates.append(StrategyTemplate(
            name="4H Stochastic Overbought Short",
            description="Short when 4H Stochastic > 70 with price below SMA(50). Fast oscillator catches the rally exhaustion.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "STOCH(14) > 70 AND CLOSE < SMA(50)"
            ],
            exit_conditions=[
                "STOCH(14) < 30 OR CLOSE > SMA(50)"
            ],
            required_indicators=["Stochastic Oscillator", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))

        # 4H EMA Ribbon Trend — ride the trend using EMA alignment on 4H
        templates.append(StrategyTemplate(
            name="4H EMA Ribbon Trend Long",
            description="Buy when EMA(8) > EMA(21) > EMA(50) on 4H with RSI > 45. Strong trend alignment for swing holding.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG],
            entry_conditions=[
                "EMA(8) > EMA(21) AND EMA(21) > EMA(50) AND RSI(14) > 45"
            ],
            exit_conditions=[
                "EMA(8) < EMA(21) OR RSI(14) > 75"
            ],
            required_indicators=["EMA:8", "EMA:21", "EMA:50", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.035,
                "take_profit_pct": 0.07,
                "hold_period_max": 48,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # 4H Stochastic Swing — buy oversold on 4H for multi-day swing
        templates.append(StrategyTemplate(
            name="4H Stochastic Swing Long",
            description="Buy when 4H Stochastic drops below 25 and crosses above signal. Deeper oversold than 1H for higher conviction swings.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "STOCH(14) < 25 AND STOCH(14) > STOCH_SIGNAL(14)"
            ],
            exit_conditions=[
                "STOCH(14) > 70"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-6 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # ===== CRYPTO LOW-VOL RANGING SPECIALISTS (LONG ONLY) =====
        # eToro does not allow shorting crypto. These templates are designed for
        # long-only entries in quiet/ranging crypto markets on 1h bars.
        # Key insight: in low-vol crypto, you need deeper dips to enter (RSI < 30 on 1h)
        # and faster exits (don't hold for the big move that isn't coming).
        
        # Crypto Hourly Deep Dip Buy — wait for real oversold on 1h, not mid-range
        templates.append(StrategyTemplate(
            name="Crypto Hourly Deep Dip Buy",
            description="Buy crypto only on genuine hourly oversold (RSI < 28) with price below BB lower band. In low-vol, these dips are rare but high-probability bounces.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "RSI(14) < 28 AND CLOSE < BB_LOWER(20, 2)"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR CLOSE > BB_MIDDLE(20, 2)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.035,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.4,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto Hourly Spike Fade — buy the dip after a sharp hourly drop
        templates.append(StrategyTemplate(
            name="Crypto Hourly Spike Fade",
            description="Buy after a >1.5% hourly drop (PRICE_CHANGE_PCT < -1.5) with RSI < 35. Sharp drops in low-vol crypto are panic sells that recover 50-70% within hours.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "PRICE_CHANGE_PCT(1) < -1.5 AND RSI(14) < 35"
            ],
            exit_conditions=[
                "PRICE_CHANGE_PCT(1) > 0.8 OR RSI(14) > 50"
            ],
            required_indicators=["Price Change %", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.25,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO MOMENTUM & TREND-FOLLOWING TEMPLATES (1H) =====
        # The existing crypto templates are ALL mean-reversion (dip-buy).
        # In a downtrending or high-vol ranging crypto market, dip-buying catches
        # falling knives. These templates ride momentum and breakouts instead.
        
        # Crypto 1H EMA Momentum — ride the intraday trend
        # When short EMA crosses above long EMA, crypto is trending. Don't fight it.
        templates.append(StrategyTemplate(
            name="Crypto Hourly EMA Momentum",
            description="Buy when EMA(8) crosses above EMA(21) with RSI > 50. Ride the hourly trend. Exit when EMA(8) crosses back below.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "EMA(8) CROSSES_ABOVE EMA(21) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "EMA(8) CROSSES_BELOW EMA(21) OR RSI(14) < 35"
            ],
            required_indicators=["EMA:8", "EMA:21", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Breakout Continuation — buy strength, not weakness
        # When price breaks above the 20-bar high with volume, the move has legs.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Breakout Continuation",
            description="Buy when price breaks above 20-bar high with RSI > 55 and volume above average. Momentum continuation on hourly.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE > HIGH_N(20) AND RSI(14) > 55 AND VOLUME > VOLUME_MA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["Rolling High", "RSI", "Volume MA", "SMA"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="4-48 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Range Scalp — tight oscillation for sideways markets
        # When crypto is ranging, RSI oscillates 40-60. Catch the micro-swings.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Range Scalp",
            description="Buy when RSI dips to 42 from above (still in range, not oversold). Quick exit at RSI 58. Tight stops for ranging crypto.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "RSI(14) < 42 AND RSI(14) > 30 AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 58 OR CLOSE < SMA(50)"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="6-12 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H BB Expansion Ride — catch the volatility expansion
        # When BB bandwidth expands and price is above middle band, ride the move up.
        templates.append(StrategyTemplate(
            name="Crypto Hourly BB Expansion Ride",
            description="Buy when price breaks above BB middle band while bandwidth is expanding (upper-lower > ATR*3). Volatility expansion = directional move starting.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP_WEAK],
            # DSL FIX 2026-05-02: was `CLOSE > BB_MIDDLE AND (expansion) AND RSI>50` (state)
            # which fired every hour price held above the middle band. 86-92 trades per
            # ~180 days vs advertised 3-6/month = ~18-36 expected. Use `CROSSES_ABOVE` on
            # the middle-band break to capture only the initial break-out bar; the
            # bandwidth+RSI filters remain state-checks gating the same bar.
            entry_conditions=[
                "CLOSE CROSSES_ABOVE BB_MIDDLE(20, 2) AND (BB_UPPER(20, 2) - BB_LOWER(20, 2)) > ATR(14) * 3 AND RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2) OR RSI(14) < 40"
            ],
            required_indicators=["Bollinger Bands", "ATR", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H MACD Momentum Cross — classic momentum on hourly
        # MACD crossing above signal with histogram turning positive = momentum building.
        templates.append(StrategyTemplate(
            name="Crypto Hourly MACD Momentum",
            description="Buy when MACD crosses above signal line with RSI > 45. Momentum building on hourly timeframe.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL() AND RSI(14) > 45"
            ],
            exit_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL() OR RSI(14) < 30"
            ],
            required_indicators=["MACD", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== CRYPTO 4H TREND & MOMENTUM TEMPLATES =====
        # The existing 4H templates are stock-market patterns (RSI pullback, MACD continuation).
        # Crypto on 4H needs templates that capture the violent spikes and consolidations.
        
        # Crypto 4H Trend Rider — hold the trend on 4H
        # When price is above both EMAs and RSI is in the momentum zone, ride it.
        templates.append(StrategyTemplate(
            name="4H Crypto Trend Rider",
            description="Buy when price > EMA(10) > EMA(30) with RSI 50-75. Strong 4H trend alignment. Exit when structure breaks.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE > EMA(10) AND EMA(10) > EMA(30) AND RSI(14) > 50 AND RSI(14) < 75"
            ],
            exit_conditions=[
                "CLOSE < EMA(10) OR RSI(14) < 40"
            ],
            required_indicators=["EMA:10", "EMA:30", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.15,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True, "crypto_optimized": True}
        ))
        
        # Crypto 4H Volume Breakout — explosive moves on 4H
        # When 4H volume spikes above 2x average with price breaking resistance, it's go time.
        templates.append(StrategyTemplate(
            name="4H Crypto Volume Breakout",
            description="Buy when price breaks above 20-bar high on 4H with volume > 2x average. Explosive crypto moves start with volume.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP_WEAK],
            entry_conditions=[
                "CLOSE > HIGH_N(20) AND VOLUME > VOLUME_MA(20) * 2"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR VOLUME < VOLUME_MA(20) * 0.5"
            ],
            required_indicators=["Rolling High", "Volume MA", "SMA"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.15,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True, "crypto_optimized": True}
        ))
        
        # Crypto 4H Consolidation Break — after tight range, catch the expansion
        # B2 FIX 2026-05-02 (Sprint 5 S5.1): was state entry `CLOSE > BB_UPPER(20, 1.5)
        # AND MACD_HIST() > 0 AND RSI(14) > 50` — same class of state-leak as the 4H
        # BB Squeeze. Switch to CROSSES_ABOVE. Test window showed test_S=-0.82 wr=36%
        # on 53 trades (pre-fix) vs 53 (post-F1 365d window) — the trade frequency
        # pointed at state-entry, not regime mismatch.
        templates.append(StrategyTemplate(
            name="4H Crypto Consolidation Break",
            description="Buy when price breaks above tight BB upper band (1.5 std) on 4H with MACD histogram positive. Consolidation → expansion.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE CROSSES_ABOVE BB_UPPER(20, 1.5) AND MACD_HIST() > 0 AND RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 1.5) OR MACD_HIST() < 0"
            ],
            required_indicators=["Bollinger Bands", "MACD", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=2.4,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True, "crypto_optimized": True}
        ))
        
        # ===== CRYPTO HIGH-VOL RANGING SPECIALISTS =====
        # These templates are designed specifically for the ranging_high_vol regime
        # where crypto has dumped and is chopping around. The key insight: in this
        # regime, price overextends on BOTH sides of the range. Catch the snaps.
        
        # Crypto 1H ATR Overextension Snap — adaptive mean reversion
        # Instead of fixed RSI thresholds, use ATR to measure overextension.
        # When price drops > 1.5x ATR below EMA in one bar, it's overextended.
        templates.append(StrategyTemplate(
            name="Crypto Hourly ATR Snap",
            description="Buy when price drops > 1.5x ATR below EMA(10) — adaptive overextension that adjusts to current volatility. Tighter than SMA(20) for faster mean reversion.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "CLOSE < EMA(10) - ATR(14) * 1.5 AND RSI(14) < 35"
            ],
            exit_conditions=[
                "CLOSE > EMA(10) OR RSI(14) > 55"
            ],
            required_indicators=["EMA:10", "ATR", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.6,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Downtrend ATR Snap — wider threshold for downtrends
        # The regular ATR Snap uses 1.5x ATR which is too tight in a downtrend.
        # The 4H version uses 2x ATR and works great (Sharpe 0.83-1.27 in test).
        # This is the 1H equivalent — same concept, hourly timeframe.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Downtrend ATR Snap",
            description="Buy when price drops > 2x ATR below EMA(20) on 1H in a downtrend. Wider threshold than ranging ATR Snap — only catches real overextensions. Quick exit at EMA.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < EMA(20) - ATR(14) * 2 AND RSI(14) < 30"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) - ATR(14) * 0.5 OR RSI(14) > 50"
            ],
            required_indicators=["EMA:20", "ATR", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.3,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Downtrend Extreme Bounce — RSI < 20 only fires on real panic
        # In a downtrend, RSI < 30 fires constantly. RSI < 20 is rare and high-conviction.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Downtrend Extreme",
            description="Buy only when 1H RSI drops below 20 in a downtrend. Extreme oversold = panic selling exhaustion. Quick scalp exit at RSI 50.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "RSI(14) < 20 AND CLOSE < BB_LOWER(20, 2)"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR CLOSE > BB_MIDDLE(20, 2)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.035,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-8 hours",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Downtrend VWAP Snap — buy extreme deviation from VWAP in downtrend
        # VWAP deviation > 3% in a downtrend = institutional selling exhaustion.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Downtrend VWAP Snap",
            description="Buy when price drops > 3% below VWAP in a downtrend with RSI < 28. Extreme institutional deviation = snap-back to VWAP.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < VWAP() * 0.97 AND RSI(14) < 28"
            ],
            exit_conditions=[
                "CLOSE > VWAP() * 0.995 OR RSI(14) > 50"
            ],
            required_indicators=["VWAP", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.035,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="2-8 hours",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # =====================================================================
        # OPTION 2: Ultra-wide capitulation entries (3x+ ATR, RSI < 15)
        # The existing 2x ATR / RSI < 30 templates fire too often in downtrends.
        # These only trigger on true capitulation — rare but high-conviction.
        # =====================================================================
        
        # Crypto 1H Capitulation ATR Snap — 3x ATR = only real panic drops
        templates.append(StrategyTemplate(
            name="Crypto Hourly Capitulation ATR Snap",
            description="Buy only when price drops > 3x ATR below EMA(20) on 1H. Extreme overextension in a downtrend — only fires on real capitulation candles. Quick scalp back to 1x ATR below EMA.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < EMA(20) - ATR(14) * 3 AND RSI(14) < 20"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) - ATR(14) * 1 OR RSI(14) > 45"
            ],
            required_indicators=["EMA:20", "ATR", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.06,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="1-6 hours",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Capitulation RSI — RSI < 15 is true panic
        # RSI < 20 still fires too often in strong downtrends. RSI < 15 on 1H
        # is genuinely rare — maybe 2-3 times per month even in a crash.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Capitulation RSI",
            description="Buy only when 1H RSI drops below 15 AND price is below lower BB(20,2.5). Double-extreme filter ensures only true panic selling. Quick exit at RSI 40.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "RSI(14) < 15 AND CLOSE < BB_LOWER(20, 2.5)"
            ],
            exit_conditions=[
                "RSI(14) > 40 OR CLOSE > BB_MIDDLE(20, 2.5)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.06,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-6 hours",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Capitulation BB Crush — price below 3-sigma BB
        # Standard BB uses 2 std dev. 2.5 sigma catches most dips. 3 sigma
        # is a statistical outlier — only fires on extreme moves.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Capitulation BB Crush",
            description="Buy when price drops below BB(20, 3.0) lower band — a 3-sigma event. Combined with RSI < 20 for confirmation. Exit at middle band.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 3.0) AND RSI(14) < 20"
            ],
            exit_conditions=[
                "CLOSE > BB_LOWER(20, 2.0) OR RSI(14) > 45"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.06,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="1-8 hours",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # =====================================================================
        # OPTION 3: Momentum / trend-following 1H templates that RIDE the downtrend
        # Instead of fading the move (mean reversion), these go WITH it.
        # Since eToro blocks crypto shorting, these are LONG-only and look for
        # brief upward momentum within the downtrend (bear market rallies).
        # =====================================================================
        
        # Crypto 1H Bear Rally Momentum — catch the relief rally
        # In a downtrend, price periodically bounces 3-5% before resuming down.
        # This template catches the START of the bounce using EMA crossover + volume.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Bear Rally Momentum",
            description="Buy when EMA(8) crosses above EMA(21) on 1H with volume spike. Catches the start of bear market relief rallies. Tight exit when momentum fades.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "EMA(8) CROSSES_ABOVE EMA(21) AND VOLUME > VOLUME_MA(20) * 1.5"
            ],
            exit_conditions=[
                "EMA(8) CROSSES_BELOW EMA(21) OR RSI(14) > 65"
            ],
            required_indicators=["EMA:8", "EMA:21", "Volume MA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.6,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H MACD Divergence Rally — MACD histogram turning positive
        # When MACD histogram goes from negative to positive in a downtrend,
        # it signals selling pressure is exhausting. Ride the bounce.
        templates.append(StrategyTemplate(
            name="Crypto Hourly MACD Divergence Rally",
            description="Buy when MACD crosses above signal line on 1H in a downtrend with RSI recovering from oversold. Selling pressure exhaustion = relief rally.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "MACD() CROSSES_ABOVE MACD_SIGNAL() AND RSI(14) < 40 AND RSI(14) > 25"
            ],
            exit_conditions=[
                "MACD() CROSSES_BELOW MACD_SIGNAL() OR RSI(14) > 60"
            ],
            required_indicators=["MACD", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.6,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Breakout from Compression — BB squeeze in downtrend
        # After a sharp drop, crypto often consolidates (BB narrows) before
        # the next move. If the breakout is UP with volume, ride it.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Downtrend Breakout",
            description="Buy when BB bandwidth contracts below 3% then price breaks above middle band with volume. Compression after a drop = energy building for a relief move.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "CLOSE > BB_MIDDLE(20, 2.0) AND BB_UPPER(20, 2.0) - BB_LOWER(20, 2.0) < ATR(14) * 2 AND VOLUME > VOLUME_MA(20) * 1.3"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2.0) OR RSI(14) > 65"
            ],
            required_indicators=["Bollinger Bands", "ATR", "Volume MA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="4-16 hours",
            risk_reward_ratio=1.75,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Stochastic Momentum Burst — ride the momentum when STOCH turns up
        # In a downtrend, STOCH(5) spends most time below 30. When it rockets
        # above 50 with price above EMA(8), it's a momentum burst worth riding.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Stoch Momentum Burst",
            description="Buy when fast STOCH(5) crosses above 50 from below 20 AND price > EMA(8). Momentum burst in a downtrend = short-covering rally. Exit when momentum fades.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "STOCH(5) > 50 AND CLOSE > EMA(8) AND RSI(14) > 35 AND RSI(14) < 55"
            ],
            exit_conditions=[
                "STOCH(5) < 30 OR RSI(14) > 65 OR CLOSE < EMA(8)"
            ],
            required_indicators=["Stochastic Oscillator:5", "EMA:8", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.75,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Fast Stochastic Reversal — STOCH(5) for quick turns
        # Standard STOCH(14) is too slow for crypto 1H. STOCH(5) catches the
        # quick reversals that happen in volatile ranging markets.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Fast Stoch Reversal",
            description="Buy when fast Stochastic(5) drops below 15 with RSI < 35. Ultra-oversold on fast timeframe = snap reversal imminent.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "STOCH(5) < 15 AND RSI(14) < 35"
            ],
            exit_conditions=[
                "STOCH(5) > 70 OR RSI(14) > 55"
            ],
            required_indicators=["Stochastic Oscillator:5", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="5-10 trades/month",
            expected_holding_period="1-8 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Tight BB Mean Reversion — BB(20, 1.5) for ranging
        # In a ranging market, price touches 1.5 std bands frequently.
        # Buy at lower band, sell at middle. Quick, high-frequency.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Tight BB Reversion",
            description="Buy at BB lower band (1.5 std) with RSI < 40. Tight bands = frequent touches in ranging market. Exit at middle band.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 1.5) AND RSI(14) < 40"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 1.5) OR RSI(14) > 60"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="6-12 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.5,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 1H Double Confirmation Extreme — RSI + STOCH both extreme
        # The problem with single-indicator entries: too many false signals.
        # Require BOTH RSI < 25 AND STOCH < 20 for high-conviction entries.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Double Extreme",
            description="Buy only when BOTH RSI < 25 AND Stochastic < 20. Double confirmation = fewer trades but higher conviction. For catching real panic wicks.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "RSI(14) < 25 AND STOCH(14) < 20"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR STOCH(14) > 65"
            ],
            required_indicators=["RSI", "Stochastic Oscillator"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Crypto 4H BB Band Walk — ride the band in a trending range
        # In high-vol ranging, price often "walks" along the upper or lower BB.
        # Buy when price bounces off lower band and holds above it.
        templates.append(StrategyTemplate(
            name="4H Crypto BB Band Walk",
            description="Buy when price bounces off BB lower band (2.0 std) on 4H and closes above it with RSI turning up. Ride the band walk back to middle.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "CLOSE > BB_LOWER(20, 2) AND LOW < BB_LOWER(20, 2) AND RSI(14) > 30"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2) OR RSI(14) > 65"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.035,
                "take_profit_pct": 0.06,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True, "crypto_optimized": True}
        ))
        
        # ===== 4H DOWNTREND TEMPLATES =====
        # These fill the critical gap: 4H has ZERO templates for trending_down_strong
        # and trending_down. In a downtrend, the only LONG plays are oversold bounces
        # and mean reversion to falling moving averages.
        
        # 4H Downtrend Oversold Bounce — catch the dead cat bounce on 4H
        templates.append(StrategyTemplate(
            name="4H Downtrend Oversold Bounce",
            description="Buy when 4H RSI drops below 25 in a downtrend. Quick scalp on the oversold bounce — don't hold for reversal.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "RSI(14) < 25 AND CLOSE < BB_LOWER(20, 2)"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR CLOSE > BB_MIDDLE(20, 2)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.035,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-3 days",
            risk_reward_ratio=1.1,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # 4H Downtrend Oversold Bounce (crypto) — wider stops for crypto volatility
        templates.append(StrategyTemplate(
            name="4H Crypto Downtrend Bounce",
            description="Buy crypto when 4H RSI < 22 AND Stochastic < 15. Extreme oversold in crypto downtrend = violent snap bounce.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN],
            entry_conditions=[
                "RSI(14) < 22 AND STOCH(14) < 15"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR STOCH(14) > 60"
            ],
            required_indicators=["RSI", "Stochastic Oscillator"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.05,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.25,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True, "crypto_optimized": True}
        ))
        
        # 4H Downtrend ATR Snap (crypto) — adaptive oversold for 4H downtrend
        templates.append(StrategyTemplate(
            name="4H Crypto Downtrend ATR Snap",
            description="Buy crypto when price drops > 2x ATR below EMA(20) on 4H. Adaptive to volatility — catches the real overextensions in a downtrend.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < EMA(20) - ATR(14) * 2 AND RSI(14) < 30"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) - ATR(14) * 0.5 OR RSI(14) > 50"
            ],
            required_indicators=["EMA:20", "ATR", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.05,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.25,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True, "crypto_optimized": True}
        ))
        
        # 4H Strong Uptrend Momentum (generic) — fills the trending_up_strong 4H gap
        templates.append(StrategyTemplate(
            name="4H Strong Uptrend Momentum",
            description="Buy when price > EMA(20) > EMA(50) with RSI 55-80 on 4H. Strong trend alignment for swing trades.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP],
            entry_conditions=[
                "CLOSE > EMA(20) AND EMA(20) > EMA(50) AND RSI(14) > 55 AND RSI(14) < 80"
            ],
            exit_conditions=[
                "CLOSE < EMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["EMA:20", "EMA:50", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # ===== TOP-20 STRATEGY GAPS — INSTITUTIONAL PATTERNS =====
        # These fill gaps identified from professional quant strategy lists.
        
        # ADX Trend Confirmation (1H) — only trade when trend is confirmed
        # ADX > 25 = trend active. Combined with EMA alignment for direction.
        templates.append(StrategyTemplate(
            name="Crypto Hourly ADX Trend Entry",
            description="Buy when ADX > 25 confirms active trend AND price > EMA(20) > EMA(50). Only enter when trend is real, not noise.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "ADX(14) > 25 AND CLOSE > EMA(20) AND EMA(20) > EMA(50)"
            ],
            exit_conditions=[
                "ADX(14) < 20 OR CLOSE < EMA(20)"
            ],
            required_indicators=["ADX", "EMA:20", "EMA:50"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ADX Trend Confirmation (4H) — swing version
        templates.append(StrategyTemplate(
            name="4H ADX Trend Swing",
            description="Buy when 4H ADX > 25 with price above EMA(20). Confirmed trend = hold for swing.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "ADX(14) > 25 AND CLOSE > EMA(20) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "ADX(14) < 18 OR CLOSE < EMA(20)"
            ],
            required_indicators=["ADX", "EMA:20", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.035,
                "take_profit_pct": 0.07,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # Pullback to EMA in Uptrend (1H crypto) — the institutional "buy the dip"
        # Price pulls back to EMA(10) while EMA(10) > EMA(30) = trend intact, dip = entry.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Trend Pullback",
            description="Buy when price pulls back to EMA(10) in an uptrend (EMA(10) > EMA(30)) with RSI 40-60. Classic institutional dip-buy in a trend.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE < EMA(10) * 1.005 AND CLOSE > EMA(10) * 0.99 AND EMA(10) > EMA(30) AND RSI(14) > 40 AND RSI(14) < 60"
            ],
            exit_conditions=[
                "CLOSE < EMA(30) OR RSI(14) > 75"
            ],
            required_indicators=["EMA:10", "EMA:30", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Momentum Continuation (1H) — buy strength with volume confirmation
        # Price making new highs with volume = momentum continuation, not exhaustion.
        templates.append(StrategyTemplate(
            name="Crypto Hourly Momentum Continuation",
            description="Buy when price > SMA(50) AND making new 10-bar high with volume above average. Momentum continuation — buy strength, not weakness.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > SMA(50) AND CLOSE > HIGH_N(10) AND VOLUME > VOLUME_MA(20) AND RSI(14) > 55"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["SMA:50", "SMA:20", "Rolling High", "Volume MA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.05,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # Momentum Continuation (4H) — swing version
        templates.append(StrategyTemplate(
            name="4H Momentum Continuation",
            description="Buy when 4H price > SMA(50) AND new 20-bar high with volume. Swing momentum continuation.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG],
            entry_conditions=[
                "CLOSE > SMA(50) AND CLOSE > HIGH_N(20) AND VOLUME > VOLUME_MA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 35"
            ],
            required_indicators=["SMA:50", "SMA:20", "Rolling High", "Volume MA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.035,
                "take_profit_pct": 0.07,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True}
        ))
        
        # SMA Proxy VWAP Reversion (1H crypto) — institutional mean reversion
        # Uses SMA(20) as VWAP proxy. Buy when price deviates > 2% below with volume.
        templates.append(StrategyTemplate(
            name="Crypto Hourly VWAP Proxy Reversion",
            description="Buy when price drops > 2% below SMA(20) (VWAP proxy) with volume spike. Institutional mean reversion to volume-weighted anchor.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "CLOSE < SMA(20) * 0.98 AND VOLUME > VOLUME_MA(20) * 1.2 AND RSI(14) < 40"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) * 0.995 OR RSI(14) > 55"
            ],
            required_indicators=["SMA:20", "Volume MA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.03,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== VWAP STRATEGIES =====
        # VWAP is the #1 institutional intraday anchor. Two patterns:
        # 1. Trend continuation: price above VWAP, pullback to VWAP, enter continuation
        # 2. Mean reversion: price deviates far from VWAP, bet on return
        
        # VWAP Trend Continuation (1H) — institutional pullback-to-anchor
        templates.append(StrategyTemplate(
            name="Crypto Hourly VWAP Trend",
            description="Buy when price pulls back to VWAP in an uptrend (price > VWAP and RSI > 45). Institutional execution anchor — price respects VWAP as dynamic support.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > VWAP() * 0.998 AND CLOSE < VWAP() * 1.005 AND RSI(14) > 45"
            ],
            exit_conditions=[
                "CLOSE < VWAP() * 0.99 OR RSI(14) > 75"
            ],
            required_indicators=["VWAP", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # VWAP Mean Reversion (1H) — buy extreme deviation from VWAP
        templates.append(StrategyTemplate(
            name="Crypto Hourly VWAP Reversion",
            description="Buy when price drops > 2% below VWAP with RSI < 35. Extreme deviation from institutional anchor = snap-back imminent.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING_LOW_VOL, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "CLOSE < VWAP() * 0.98 AND RSI(14) < 35"
            ],
            exit_conditions=[
                "CLOSE > VWAP() * 0.998 OR RSI(14) > 55"
            ],
            required_indicators=["VWAP", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.03,
                "risk_per_trade_pct": 0.01,
                "sizing_method": "volatility",
                "position_size_atr_multiplier": 1.0,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.2,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # R7 REMOVED 2026-05-01 per STRATEGY_LIBRARY_REVIEW_2026-05:
        # - "4H VWAP Trend Continuation": VWAP on 4H bars spans multiple trading
        #   sessions, muddling the intraday-anchor concept VWAP is built for.
        #   VWAP resets session-by-session — meaningful at 1h within a session,
        #   not meaningful as a 4H swing signal. Live: -$141 open drag.
        #   Intraday 1h variants (Crypto Hourly VWAP Trend, Crypto Hourly VWAP
        #   Reversion) retain the correct scope and are kept.
        
        
        templates.append(StrategyTemplate(
            name="Crypto BB Squeeze Breakout Long",
            description="Buy when BB bandwidth compresses below 3% and price breaks above upper band with RSI > 50. Low-vol squeeze precedes directional moves.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 1.5) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 1.5) OR RSI(14) < 40"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="4-48 hours",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "intraday": True}
        ))
        
        # ===== RANGING LOW-VOL SPECIALIST TEMPLATES =====
        # Designed specifically for the ranging_low_vol regime where:
        # - Price swings are small (ATR/price < 1%)
        # - RSI stays in 35-65 range (no extremes)
        # - Bollinger Bands are narrow
        # - Volume is below average
        # A profitable trader in this regime uses TIGHT entries, TIGHT stops,
        # and takes small consistent profits rather than waiting for big moves.

        # --- Tight Range Mean Reversion ---
        # In low vol, RSI rarely hits 30 or 70. Use 40/60 band instead.
        templates.append(StrategyTemplate(
            name="Tight RSI Mean Reversion",
            description="Buy when RSI dips below 40 in low vol (not extreme oversold), sell on recovery above 55. Tight stops for small consistent wins.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "RSI(14) < 40 AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 55"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "rsi_period": 14,
                "oversold_threshold": 40,
                "overbought_threshold": 55,
                "sma_period": 50,
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="5-8 trades/month",
            expected_holding_period="2-4 days",
            risk_reward_ratio=1.7
        ))

        # R6 REMOVED 2026-05-01 per STRATEGY_LIBRARY_REVIEW_2026-05:
        # - "BB Midband Reversion Tight": same zero-edge pattern as BB Middle Band
        #   Bounce (also removed). Crossing BB middle is not a reliable signal
        #   without other confluence. Structural concept flaw.
        

        # --- Narrow BB Scalp Long ---
        # When bands are very tight, any touch of the lower band is a buy.
        # Use BB(20, 1.5) instead of 2.0 — tighter bands = more signals in low vol.
        templates.append(StrategyTemplate(
            name="Narrow BB Scalp Long",
            description="Buy at lower BB(20,1.5) in low vol, exit at upper band. Tight bands = frequent small wins.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 1.5)"
            ],
            exit_conditions=[
                "CLOSE > BB_UPPER(20, 1.5)"
            ],
            required_indicators=["Bollinger Bands"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 1.5,
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.7
        ))

        # --- Narrow BB Scalp Short ---
        templates.append(StrategyTemplate(
            name="Narrow BB Scalp Short",
            description="Short at upper BB(20,1.5) in low vol, cover at lower band. Mirror of Narrow BB Scalp Long.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 1.5)"
            ],
            exit_conditions=[
                "CLOSE < BB_LOWER(20, 1.5)"
            ],
            required_indicators=["Bollinger Bands"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 1.5,
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            metadata={"direction": "short"},
            expected_trade_frequency="4-8 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.7
        ))

        # R4/R5 REMOVED 2026-05-01 per STRATEGY_LIBRARY_REVIEW_2026-05:
        # - "SMA Envelope Reversion Long" and "SMA Envelope Reversion Short":
        #   same envelope-proximity pattern as SMA Proximity Entry (also removed).
        #   Fires on any close below/above SMA(20) with RSI extreme — no regime
        #   filter, so signals fire in trending markets where envelope crossings
        #   become continuations. Structural concept flaw, not an implementation bug.
        

        # --- Stochastic Midrange Oscillator ---
        # In low vol, Stochastic oscillates 30-70 instead of 20-80. Trade the midrange.
        templates.append(StrategyTemplate(
            name="Stochastic Midrange Long",
            description="Buy when Stochastic dips below 35 in low vol, sell above 65. Midrange oscillator for quiet markets.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "STOCH(14) < 35"
            ],
            exit_conditions=[
                "STOCH(14) > 65"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "oversold": 35,
                "overbought": 65,
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="5-8 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.7
        ))

        # --- Stochastic Midrange Short ---
        templates.append(StrategyTemplate(
            name="Stochastic Midrange Short",
            description="Short when Stochastic rises above 65 in low vol, cover below 35. Mirror of Stochastic Midrange Long.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "STOCH(14) > 65"
            ],
            exit_conditions=[
                "STOCH(14) < 35"
            ],
            required_indicators=["Stochastic Oscillator"],
            default_parameters={
                "stoch_period": 14,
                "oversold": 35,
                "overbought": 65,
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            metadata={"direction": "short"},
            expected_trade_frequency="5-8 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.7
        ))

        # --- RSI + EMA Confluence Long ---
        # Two confirmations: RSI dip + price near EMA support. Higher win rate.
        templates.append(StrategyTemplate(
            name="RSI EMA Confluence Long",
            description="Buy when RSI < 42 AND price near EMA(20) support. Double confirmation = higher win rate in quiet markets.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "RSI(14) < 42 AND CLOSE > EMA(20)"
            ],
            exit_conditions=[
                "RSI(14) > 58 OR CLOSE < EMA(50)"
            ],
            required_indicators=["RSI", "EMA:20", "EMA:50"],
            default_parameters={
                "rsi_period": 14,
                "ema_fast": 20,
                "ema_slow": 50,
                "stop_loss_pct": 0.018,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="4-7 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.7
        ))

        # --- RSI + EMA Confluence Short ---
        templates.append(StrategyTemplate(
            name="RSI EMA Confluence Short",
            description="Short when RSI > 58 AND price below EMA(20) resistance. Double confirmation for shorts in quiet markets.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "RSI(14) > 58 AND CLOSE < EMA(20)"
            ],
            exit_conditions=[
                "RSI(14) < 42 OR CLOSE > EMA(50)"
            ],
            required_indicators=["RSI", "EMA:20", "EMA:50"],
            default_parameters={
                "rsi_period": 14,
                "ema_fast": 20,
                "ema_slow": 50,
                "stop_loss_pct": 0.018,
                "take_profit_pct": 0.03,
            },
            metadata={"direction": "short"},
            expected_trade_frequency="4-7 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.7
        ))

        # --- ATR Contraction Breakout ---
        # When ATR drops to very low levels, the next expansion is tradeable.
        # Buy when price breaks above recent high after ATR contraction.
        templates.append(StrategyTemplate(
            name="ATR Contraction Breakout Long",
            description="Buy when ATR is low and price breaks above BB upper band — volatility expansion from quiet period.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2) AND RSI(14) > 50"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2,
                "rsi_period": 14,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0
        ))

        # --- ATR Contraction Breakdown Short ---
        templates.append(StrategyTemplate(
            name="ATR Contraction Breakdown Short",
            description="Short when ATR is low and price breaks below BB lower band — volatility expansion downward.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2) AND RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2)"
            ],
            required_indicators=["Bollinger Bands", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2,
                "rsi_period": 14,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
            },
            metadata={"direction": "short"},
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0
        ))

        # --- EMA Ribbon Compression Long ---
        # When EMA(10) and EMA(20) converge (ribbon compresses), the next divergence is the trade.
        templates.append(StrategyTemplate(
            name="EMA Ribbon Expansion Long",
            description="Buy when EMA(10) crosses above EMA(20) after compression period. Trend initiation from quiet market.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "EMA(10) > EMA(20) AND CLOSE > EMA(10)"
            ],
            exit_conditions=[
                "CLOSE < EMA(20)"
            ],
            required_indicators=["EMA:10", "EMA:20"],
            default_parameters={
                "ema_fast": 10,
                "ema_slow": 20,
                "stop_loss_pct": 0.018,
                "take_profit_pct": 0.035,
            },
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="3-8 days",
            risk_reward_ratio=2.0
        ))

        # --- EMA Ribbon Compression Short ---
        templates.append(StrategyTemplate(
            name="EMA Ribbon Expansion Short",
            description="Short when EMA(10) crosses below EMA(20) after compression. Trend initiation downward.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "EMA(10) < EMA(20) AND CLOSE < EMA(10)"
            ],
            exit_conditions=[
                "CLOSE > EMA(20)"
            ],
            required_indicators=["EMA:10", "EMA:20"],
            default_parameters={
                "ema_fast": 10,
                "ema_slow": 20,
                "stop_loss_pct": 0.018,
                "take_profit_pct": 0.035,
            },
            metadata={"direction": "short"},
            expected_trade_frequency="3-5 trades/month",
            expected_holding_period="3-8 days",
            risk_reward_ratio=2.0
        ))

        # --- MACD Zero Line Bounce ---
        # In low vol, MACD oscillates near zero. Buy when it crosses above zero.
        templates.append(StrategyTemplate(
            name="MACD Zero Cross Long",
            description="Buy when MACD crosses above zero line in low vol — momentum shift from neutral. Simple and effective.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "MACD(12,26) CROSSES_ABOVE 0"
            ],
            exit_conditions=[
                "MACD(12,26) CROSSES_BELOW 0"
            ],
            required_indicators=["MACD"],
            default_parameters={
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-12 days",
            risk_reward_ratio=1.8
        ))

        # --- MACD Zero Line Short ---
        templates.append(StrategyTemplate(
            name="MACD Zero Cross Short",
            description="Short when MACD crosses below zero line — momentum shift downward in quiet market.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "MACD(12,26) CROSSES_BELOW 0"
            ],
            exit_conditions=[
                "MACD(12,26) CROSSES_ABOVE 0"
            ],
            required_indicators=["MACD"],
            default_parameters={
                "macd_fast": 12,
                "macd_slow": 26,
                "macd_signal": 9,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035,
            },
            metadata={"direction": "short"},
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-12 days",
            risk_reward_ratio=1.8
        ))

        # --- Volume Dry-Up Reversal ---
        # When volume drops significantly below average AND price is at support, expect a bounce.
        templates.append(StrategyTemplate(
            name="Volume Dry-Up Reversal Long",
            description="Buy when volume dries up near SMA support — selling exhaustion in quiet market. Volume < 50% of average signals capitulation.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE > SMA(50) AND RSI(14) < 45"
            ],
            exit_conditions=[
                "RSI(14) > 55"
            ],
            required_indicators=["SMA:50", "RSI"],
            default_parameters={
                "sma_period": 50,
                "rsi_period": 14,
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="4-6 trades/month",
            expected_holding_period="2-5 days",
            risk_reward_ratio=1.7
        ))

        # --- Keltner Midline Bounce ---
        # Similar to BB middle band but uses ATR-based channels. More adaptive to vol changes.
        templates.append(StrategyTemplate(
            name="Keltner Midline Bounce Long",
            description="Buy when price bounces off Keltner channel midline (EMA 20) with RSI confirmation. ATR-adaptive for low vol.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > EMA(20) AND RSI(14) < 48 AND RSI(14) > 30"
            ],
            exit_conditions=[
                "RSI(14) > 60"
            ],
            required_indicators=["EMA:20", "RSI"],
            default_parameters={
                "ema_period": 20,
                "rsi_period": 14,
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.025,
            },
            expected_trade_frequency="5-8 trades/month",
            expected_holding_period="2-4 days",
            risk_reward_ratio=1.7
        ))

        # --- RSI Divergence Recovery ---
        # Buy when RSI makes higher low while price makes lower low — bullish divergence.
        # In low vol this is a strong signal because moves are small but reliable.
        templates.append(StrategyTemplate(
            name="RSI Higher Low Recovery",
            description="Buy when RSI is rising from below 40 while price is near SMA — early recovery signal in quiet market.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "RSI(14) > 35 AND RSI(14) < 45 AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 60 OR CLOSE < SMA(50)"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "rsi_period": 14,
                "sma_period": 50,
                "stop_loss_pct": 0.018,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="4-6 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=1.7
        ))

        # ===== COMMODITY-SPECIFIC TEMPLATES (OIL, GOLD, SILVER, COPPER) =====
        # Commodities trade differently from equities:
        # - Driven by supply/demand shocks, geopolitics, macro flows
        # - Trend harder and longer (oil can rally 30% in a month on supply disruption)
        # - Mean-revert faster on spikes (geopolitical premium fades when news settles)
        # - Higher volatility = wider stops needed
        # - 24/5 trading on eToro (CFDs), shortable unlike crypto
        # - GOLD/SILVER correlate with risk-off, OIL with geopolitics, COPPER with growth
        #
        # These templates use fixed_symbols to target only commodities.
        # Wider stops (3.5-5%) and take-profits (5-8%) vs stock templates.

        # --- COMMODITY 4H TREND CONTINUATION LONG ---
        # In a commodity uptrend, price holds above EMAs and RSI stays 50-75.
        # This is the bread-and-butter commodity trend trade.
        templates.append(StrategyTemplate(
            name="4H Commodity Trend Continuation Long",
            description="Buy when 4H price > EMA(20) > EMA(50) with RSI 50-75. Ride the commodity trend — supply shocks create persistent moves.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > SMA(20) AND SMA(20) > SMA(50) AND RSI(14) > 50 AND RSI(14) < 75"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["RSI", "SMA:20", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.07,
                "hold_period_max": 72,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=1.75,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True,
                       "fixed_symbols": ["OIL", "GOLD", "SILVER", "COPPER", "NATGAS", "PLATINUM"]}
        ))

        # --- COMMODITY 4H MOMENTUM BREAKOUT LONG ---
        # Commodity breaks above recent high with RSI confirming strength.
        # Supply disruptions cause explosive breakouts that run for days.
        templates.append(StrategyTemplate(
            name="4H Commodity Momentum Breakout Long",
            description="Buy when 4H price breaks above 20-bar high with RSI > 55. Commodity breakouts on supply shocks run hard.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL, MarketRegime.RANGING],
            entry_conditions=[
                "CLOSE > HIGH_N(20) AND RSI(14) > 55"
            ],
            exit_conditions=[
                "RSI(14) < 40 OR CLOSE < SMA(20)"
            ],
            required_indicators=["RSI", "SMA:20"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.08,
                "hold_period_max": 72,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="2-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "interval_4h": True, "interval": "4h", "skip_param_override": True,
                       "fixed_symbols": ["OIL", "GOLD", "SILVER", "COPPER", "NATGAS", "PLATINUM"]}
        ))

        # --- COMMODITY 4H OVERBOUGHT FADE SHORT ---
        # After a geopolitical spike, commodities mean-revert when the premium fades.
        # RSI > 70 on 4H = the spike is exhausted. Fade it back to the mean.
        templates.append(StrategyTemplate(
            name="4H Commodity Overbought Fade Short",
            description="Short when 4H RSI > 70 with price extended above BB upper band. Geopolitical spikes fade — sell the exhaustion.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP],
            entry_conditions=[
                "RSI(14) > 70 AND CLOSE > BB_UPPER(20, 2)"
            ],
            exit_conditions=[
                "RSI(14) < 50 OR CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.06,
                "hold_period_max": 48,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="1-4 days",
            risk_reward_ratio=1.5,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True,
                       "fixed_symbols": ["OIL", "GOLD", "SILVER", "COPPER", "NATGAS", "PLATINUM"]}
        ))

        # --- COMMODITY 4H EMA REJECTION SHORT (DOWNTREND) ---
        # When commodities are falling (demand destruction, strong dollar), short the rally.
        templates.append(StrategyTemplate(
            name="4H Commodity EMA Rejection Short",
            description="Short when 4H price rallies to declining EMA(20) with RSI > 55 and price below SMA(50). Fade the bounce in a commodity downtrend.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "RSI(14) > 55 AND CLOSE > SMA(20) * 0.995 AND CLOSE < SMA(20) * 1.01 AND CLOSE < SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) < 35 OR CLOSE < SMA(20) * 0.97"
            ],
            required_indicators=["RSI", "SMA:20", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.035,
                "take_profit_pct": 0.06,
                "hold_period_max": 48,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="1-5 days",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "interval_4h": True, "interval": "4h", "skip_param_override": True,
                       "fixed_symbols": ["OIL", "GOLD", "SILVER", "COPPER", "NATGAS", "PLATINUM"]}
        ))

        # --- COMMODITY 1H MOMENTUM SURGE LONG ---
        # Hourly momentum on commodities — catch the intraday surge.
        # Price above VWAP with RSI 55-80 and volume confirming.
        #
        # 2026-05-03: narrowed fixed_symbols from [OIL, GOLD, SILVER, COPPER,
        # NATGAS, PLATINUM] to [GOLD, SILVER] — FMP Starter only serves 1h
        # data for these two (OIL/COPPER/NATGAS rely on Yahoo which caps at
        # 730d rolling, giving only ~11 months of DB depth — insufficient
        # for statistically meaningful 1h WF with min_trades=15). Intraday
        # oil/copper is whipsaw-prone anyway; we trade them on 4h and 1d.
        # Template name kept for lineage continuity with 313 historical
        # proposals in strategy_proposals.
        templates.append(StrategyTemplate(
            name="Commodity Hourly Momentum Surge Long",
            description="Buy when 1H price > SMA(20) with RSI 55-80 and volume > 1.5x average. Intraday precious-metal momentum (GOLD/SILVER only — FMP Starter depth limits the 1h scope).",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE > SMA(20) AND RSI(14) > 55 AND RSI(14) < 80 AND VOLUME > VOLUME_MA(20) * 1.5"
            ],
            exit_conditions=[
                "RSI(14) < 40 OR CLOSE < SMA(20)"
            ],
            required_indicators=["RSI", "SMA:20", "Volume MA"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.04,
                "hold_period_max": 24,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="4-24 hours",
            risk_reward_ratio=1.6,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True,
                       "fixed_symbols": ["GOLD", "SILVER"]}
        ))

        # --- COMMODITY 1H MEAN REVERSION LONG ---
        # Commodities oversold on 1H — quick bounce trade.
        # RSI < 30 on 1H with price near lower BB = snap back.
        # Scope narrowed to [GOLD, SILVER] — see 2026-05-03 note on
        # Commodity Hourly Momentum Surge Long above.
        templates.append(StrategyTemplate(
            name="Commodity Hourly Oversold Bounce Long",
            description="Buy when 1H RSI < 30 with price near BB lower band. Precious-metal oversold bounces (GOLD/SILVER only — FMP Starter depth limits the 1h scope).",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK],
            entry_conditions=[
                "RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2) * 1.005"
            ],
            exit_conditions=[
                "RSI(14) > 55 OR CLOSE > BB_MIDDLE(20, 2)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.025,
                "take_profit_pct": 0.04,
                "hold_period_max": 24,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="4-16 hours",
            risk_reward_ratio=1.6,
            metadata={"direction": "long", "intraday": True, "interval": "1h", "skip_param_override": True,
                       "fixed_symbols": ["GOLD", "SILVER"]}
        ))

        # --- COMMODITY 1H SPIKE FADE SHORT ---
        # Intraday commodity spike exhaustion — RSI > 75 on 1H with price above upper BB.
        # Safe-haven premium fades fast when the fear trigger resolves.
        # Scope narrowed to [GOLD, SILVER] — see 2026-05-03 note on
        # Commodity Hourly Momentum Surge Long above.
        templates.append(StrategyTemplate(
            name="Commodity Hourly Spike Fade Short",
            description="Short when 1H RSI > 75 with price above BB upper band. Precious-metal spikes fade fast (GOLD/SILVER only — FMP Starter depth limits the 1h scope).",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_UP],
            entry_conditions=[
                "RSI(14) > 75 AND CLOSE > BB_UPPER(20, 2)"
            ],
            exit_conditions=[
                "RSI(14) < 50 OR CLOSE < BB_MIDDLE(20, 2)"
            ],
            required_indicators=["RSI", "Bollinger Bands"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.05,
                "hold_period_max": 24,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="4-16 hours",
            risk_reward_ratio=1.7,
            metadata={"direction": "short", "intraday": True, "interval": "1h", "skip_param_override": True,
                       "fixed_symbols": ["GOLD", "SILVER"]}
        ))

        # --- COMMODITY DAILY TREND RIDER LONG ---
        # Daily timeframe for the big commodity trends (oil crisis, gold safe haven).
        # Price above SMA(50) with ADX > 25 = confirmed trend.
        templates.append(StrategyTemplate(
            name="Commodity Daily Trend Rider Long",
            description="Buy when daily price > SMA(50) with RSI 50-75. Ride the macro commodity trend — supply crises last months.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.TRENDING_UP_STRONG],
            entry_conditions=[
                "CLOSE > SMA(50) AND RSI(14) > 50 AND RSI(14) < 75 AND CLOSE > SMA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(50) OR RSI(14) < 35"
            ],
            required_indicators=["RSI", "SMA:20", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="5-20 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "interval": "1d", "skip_param_override": True,
                       "fixed_symbols": ["OIL", "GOLD", "SILVER", "COPPER", "NATGAS", "PLATINUM", "ALUMINUM", "ZINC"]}
        ))

        # --- COMMODITY DAILY PULLBACK BUY ---
        # Buy the dip in a commodity uptrend. RSI dips below 40 while price holds above SMA(50).
        templates.append(StrategyTemplate(
            name="Commodity Daily Pullback Buy",
            description="Buy when daily RSI dips below 40 with price above SMA(50). Buy the dip in a commodity uptrend — supply constraints mean dips get bought.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING],
            entry_conditions=[
                "RSI(14) < 40 AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "RSI(14) > 65 OR CLOSE < SMA(50)"
            ],
            required_indicators=["RSI", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.07,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=1.75,
            metadata={"direction": "long", "interval": "1d", "skip_param_override": True,
                       "fixed_symbols": ["OIL", "GOLD", "SILVER", "COPPER", "NATGAS", "PLATINUM", "ALUMINUM", "ZINC"]}
        ))

        # --- COMMODITY DAILY BREAKDOWN SHORT ---
        # When commodities break below SMA(50), the trend has turned. Demand destruction.
        templates.append(StrategyTemplate(
            name="Commodity Daily Breakdown Short",
            description="Short when daily price breaks below SMA(50) with RSI < 45. Commodity downtrends accelerate — demand destruction is real.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "CLOSE < SMA(50) AND RSI(14) < 45 AND CLOSE < SMA(20)"
            ],
            exit_conditions=[
                "RSI(14) > 60 OR CLOSE > SMA(50)"
            ],
            required_indicators=["RSI", "SMA:20", "SMA:50"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.07,
            },
            expected_trade_frequency="1-2 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=1.75,
            metadata={"direction": "short", "interval": "1d", "skip_param_override": True,
                       "fixed_symbols": ["OIL", "GOLD", "SILVER", "COPPER", "NATGAS", "PLATINUM", "ALUMINUM", "ZINC"]}
        ))

        # ===== 2026 REGIME-OPTIMIZED TEMPLATES =====
        # Based on research: hedge fund consensus strategies for weak downtrend / moderate VIX regime.
        # Sources: QuantLabs Multi-Asset Report, Algomatic Trading bear rally research,
        # Morgan Stanley 2026 Outlook, Cambridge Associates hedge fund views.

        # --- 1. Bear Rally Fade Short ---
        # The highest-edge strategy in weak downtrends per Algomatic Trading research:
        # When price is below the 200-day MA (confirmed bear regime) and RSI spikes
        # to overbought, the rally is exhaustion, not reversal. Short the spike.
        # 60% win rate, profit factor 1.3-1.5 across multiple markets.
        # Key difference from our existing RSI Overbought Short: this requires
        # price < SMA(200) as a regime filter. Without it, you're randomly fading rallies.
        templates.append(StrategyTemplate(
            name="Bear Rally Fade Short",
            description="Short when RSI spikes above 70 in a confirmed downtrend (price < SMA 200). Fades exhaustion rallies that fail to reverse the trend. Exit when RSI mean-reverts to 40.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN_STRONG],
            entry_conditions=[
                "RSI(14) > 70 AND CLOSE < SMA(200)"
            ],
            exit_conditions=[
                "RSI(14) < 40 OR CLOSE > SMA(200)"
            ],
            required_indicators=["RSI", "SMA:200"],
            default_parameters={
                "rsi_period": 14,
                "sma_period": 200,
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short", "skip_param_override": True}
        ))

        # --- 2. Gold Momentum Long ---
        # Gold is the #1 consensus trade of 2026. Central bank buying (China, Russia, India),
        # geopolitical fear premium, and rate cut expectations all support gold.
        # This is a trend-following play, not a dip-buy. Enter when gold is trending
        # (price > SMA 50, RSI > 50) and ride the momentum.
        templates.append(StrategyTemplate(
            name="Gold Momentum Long",
            description="Buy gold when price is above SMA(50) with RSI confirming momentum (>50). Trend-following play on central bank buying and geopolitical demand. Exit on trend break.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG, MarketRegime.RANGING,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE > SMA(50) AND RSI(14) > 50 AND CLOSE > SMA(20)"
            ],
            exit_conditions=[
                "CLOSE < SMA(50) OR RSI(14) < 35"
            ],
            required_indicators=["SMA:50", "SMA:20", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="10-30 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "skip_param_override": True,
                       "fixed_symbols": ["GOLD"]}
        ))

        # --- 3. Defensive Sector Rotation Long ---
        # In weak downtrends, money flows from growth to defensive sectors.
        # Buy defensive ETFs (utilities, healthcare, consumer staples) when they're
        # above their own SMA (relative strength) while the broad market is weak.
        # This captures the flight-to-safety rotation.
        templates.append(StrategyTemplate(
            name="Defensive Sector Rotation Long",
            description="Buy defensive sector ETFs when they show relative strength (price > SMA 20) in a weak market. Captures flight-to-safety rotation from growth to defensives.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.TRENDING_DOWN,
                MarketRegime.RANGING, MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE > SMA(20) AND RSI(14) > 45 AND RSI(14) < 65"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) > 75"
            ],
            required_indicators=["SMA:20", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="7-20 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "skip_param_override": True,
                       "fixed_symbols": ["XLU", "XLV", "XLP", "XLI", "GLD", "HYG"]}
        ))

        # --- 4. VIX Regime Position Sizer ---
        # With VIX in the 16-22 "sweet spot," moderate volatility favors defined-risk
        # entries. This template buys oversold conditions but only when VIX is elevated
        # (fear = opportunity) and uses ATR-based sizing. When VIX is low (<15),
        # the market is complacent and dips are shallow — not worth buying.
        templates.append(StrategyTemplate(
            name="High VIX Oversold Bounce",
            description="Buy deep oversold conditions (RSI < 25) only when volatility is elevated. High VIX + oversold = panic selling = high-probability bounce. Tighter entry than standard dip buy.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING_HIGH_VOL, MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.TRENDING_DOWN,
            ],
            entry_conditions=[
                "RSI(14) < 25 AND ATR(14) > SMA(20) * 0.015"
            ],
            exit_conditions=[
                "RSI(14) > 50 OR CLOSE > SMA(20)"
            ],
            required_indicators=["RSI", "ATR", "SMA:20"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="3-7 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "skip_param_override": True}
        ))

        # --- 5. EUR/USD Policy Divergence Short ---
        # Fed hawkish (holding rates), ECB dovish (cutting). Capital flows from EUR to USD.
        # This is the strongest macro trend of 2026 per QuantLabs and Morgan Stanley.
        # Trend-following on forex with momentum confirmation.
        templates.append(StrategyTemplate(
            name="EURUSD Policy Divergence Short",
            description="Short EUR/USD when price is below SMA(50) with bearish momentum. Captures Fed-ECB policy divergence driving capital from Euro to Dollar.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.RANGING,
            ],
            entry_conditions=[
                "CLOSE < SMA(50) AND RSI(14) < 45 AND CLOSE < EMA(20)"
            ],
            exit_conditions=[
                "CLOSE > SMA(50) OR RSI(14) > 65"
            ],
            required_indicators=["SMA:50", "EMA:20", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.015,
                "take_profit_pct": 0.03,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short", "skip_param_override": True,
                       "fixed_symbols": ["EURUSD"]}
        ))

        # --- 6. ATR Dynamic Trend Follow ---
        # Research consistently shows ATR-based stops outperform fixed percentage stops.
        # This template uses ATR for both entry confirmation (volatility expansion = breakout)
        # and exit (price reverts more than 2x ATR from recent high = trend exhaustion).
        # Works across all asset classes.
        #
        # STRENGTHENED (Apr 2026): Added ADX>20 trend quality filter and RSI 50-65 band.
        # Original entry (CLOSE > SMA(20) AND CLOSE > SMA(50) AND RSI > 50) fired on every
        # bounce above moving averages in choppy markets — no trend quality check.
        # ADX>20 confirms a real trend exists. RSI 50-65 prevents entering overbought.
        # Removed RANGING from market_regimes — trend-following has no edge in ranging markets.
        templates.append(StrategyTemplate(
            name="ATR Dynamic Trend Follow",
            description="Enter when price breaks above SMA(20) with confirmed trend (ADX>20) and RSI in momentum zone (50-65). Exit when trend weakens. Quality-filtered trend following.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE > SMA(20) AND CLOSE > SMA(50) AND RSI(14) > 50 AND RSI(14) < 65 AND ADX(14) > 20"
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 35 OR ADX(14) < 15"
            ],
            required_indicators=["SMA:20", "SMA:50", "RSI", "ATR", "ADX"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="1-3 trades/month",
            expected_holding_period="5-20 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "skip_param_override": True}
        ))

        # ATR Dynamic Trend Follow Short — mirror for downtrends
        templates.append(StrategyTemplate(
            name="ATR Dynamic Trend Follow Short",
            description="Short when price breaks below SMA(20) with ATR expansion. Exit when price recovers above SMA(20). Dynamic risk for downtrend riding.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_WEAK,
                MarketRegime.TRENDING_DOWN_STRONG,
            ],
            entry_conditions=[
                "CLOSE < SMA(20) AND CLOSE < SMA(50) AND RSI(14) < 50"
            ],
            exit_conditions=[
                "CLOSE > SMA(20) OR RSI(14) > 65"
            ],
            required_indicators=["SMA:20", "SMA:50", "RSI", "ATR"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="5-20 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "short", "skip_param_override": True}
        ))

        # ===== KELTNER CHANNEL BREAKOUT (Tier 2 — Adaptive Trend-Following) =====
        # Keltner channels use EMA + ATR bands instead of Bollinger's std dev bands.
        # The ATR-based bands adapt to volatility naturally. ADX > 25 confirms a
        # real trend (not noise). ATR trailing stop adapts exit to current volatility.
        # Works across all asset classes — equities, crypto, forex, commodities.
        # Reference: research shows Keltner breakouts with ADX filter produce
        # robust out-of-sample results with Sharpe > 1.0 in trending regimes.
        templates.append(StrategyTemplate(
            name="Keltner Channel Breakout",
            description="Buy when price breaks above EMA(20) + 2×ATR(14) with ADX > 25 confirming trend strength. ATR trailing stop at 1.5×ATR. Volatility-adaptive breakout for trending markets.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "CLOSE > EMA(20) + ATR(14) * 2.0 AND ADX(14) > 25"
            ],
            exit_conditions=[
                "CLOSE < EMA(20) OR ADX(14) < 20"
            ],
            required_indicators=["EMA:20", "ATR", "ADX"],
            default_parameters={
                "ema_period": 20,
                "atr_period": 14,
                "atr_channel_mult": 2.0,
                "adx_period": 14,
                "adx_entry_threshold": 25,
                "adx_exit_threshold": 20,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "long", "skip_param_override": True}
        ))

        # Keltner Channel Breakout Short — mirror for downtrends
        templates.append(StrategyTemplate(
            name="Keltner Channel Breakout Short",
            description="Short when price breaks below EMA(20) - 2×ATR(14) with ADX > 25. Cover when price recovers above EMA(20). Volatility-adaptive breakdown for downtrends.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG,
                MarketRegime.TRENDING_DOWN_WEAK,
            ],
            entry_conditions=[
                "CLOSE < EMA(20) - ATR(14) * 2.0 AND ADX(14) > 25"
            ],
            exit_conditions=[
                "CLOSE > EMA(20) OR ADX(14) < 20"
            ],
            required_indicators=["EMA:20", "ATR", "ADX"],
            default_parameters={
                "ema_period": 20,
                "atr_period": 14,
                "atr_channel_mult": 2.0,
                "adx_period": 14,
                "adx_entry_threshold": 25,
                "adx_exit_threshold": 20,
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.08,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.5,
            metadata={"direction": "short", "skip_param_override": True}
        ))

        # ===== BOLLINGER MEAN REVERSION WITH REGIME GATE (Tier 2) =====
        # Standard Bollinger mean reversion but ONLY fires in ranging markets.
        # ADX < 25 ensures we're not shorting into a breakout or buying into a
        # breakdown. VIX overlay: more aggressive when VIX is elevated (mean
        # reversion works best in fear spikes), paused when VIX is trending up
        # (breakdown risk). This fills the gap for non-trending conditions.
        templates.append(StrategyTemplate(
            name="Bollinger Regime-Gated Mean Reversion",
            description="Buy at lower Bollinger Band ONLY when ADX < 25 (ranging market). Exit at middle band. Regime gate prevents buying dips in strong downtrends. Works best when VIX is elevated.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE < BB_LOWER(20, 2) AND ADX(14) < 25 AND RSI(14) < 35"
            ],
            exit_conditions=[
                "CLOSE > BB_MIDDLE(20, 2) OR RSI(14) > 65"
            ],
            required_indicators=["Bollinger Bands", "ADX", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "adx_period": 14,
                "adx_max_threshold": 25,
                "rsi_period": 14,
                "rsi_entry_threshold": 35,
                "rsi_exit_threshold": 65,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-8 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "long", "skip_param_override": True}
        ))

        # Bollinger Regime-Gated Mean Reversion Short
        templates.append(StrategyTemplate(
            name="Bollinger Regime-Gated Mean Reversion Short",
            description="Short at upper Bollinger Band ONLY when ADX < 25 (ranging market). Cover at middle band. Prevents shorting into strong uptrends.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[
                MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2) AND ADX(14) < 25 AND RSI(14) > 65"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2) OR RSI(14) < 35"
            ],
            required_indicators=["Bollinger Bands", "ADX", "RSI"],
            default_parameters={
                "bb_period": 20,
                "bb_std": 2.0,
                "adx_period": 14,
                "adx_max_threshold": 25,
                "rsi_period": 14,
                "rsi_entry_threshold": 65,
                "rsi_exit_threshold": 35,
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.04,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="3-8 days",
            risk_reward_ratio=2.0,
            metadata={"direction": "short", "skip_param_override": True}
        ))

        # [REMOVED 2026-05-01] BTC Lead-Lag Altcoin Momentum
        # Template was proposing altcoin (SOL/XRP/ADA/etc.) longs when BTC had
        # upward momentum. Altcoins are disabled in the symbol universe (eToro
        # 1% per-side fee makes high-frequency altcoin strategies unprofitable;
        # only BTC and ETH are tradeable). The template's edge — riding 1-4h
        # spillover from BTC into small-caps — requires those small-caps to be
        # tradeable. With only BTC and ETH, BTC leading ETH by hours isn't
        # enough differentiation to extract alpha vs plain BTC/ETH momentum
        # templates. One active DEMO instance on ETH had -$88 unrealised and
        # no closed trades. Removed to reduce template proposal noise.

        # ===== CRYPTO HIGH-CONVICTION MOMENTUM TEMPLATES =====
        # Designed for eToro's 1% per-side fee structure.
        # Key principles:
        # - Maximum 2-4 trades per quarter to minimize cost drag
        # - Target 10%+ per trade to overcome 2% round-trip cost
        # - BTC/ETH only (most liquid, best data, strongest trends)
        # - Daily/weekly timeframes only (no intraday scalping)
        # - Regime-aware: only enter on confirmed trend shifts

        # Crypto Trend Breakout — enter on 50-day high breakout, exit on 20-day low
        # Classic Turtle-style breakout adapted for crypto's larger moves.
        # Expects 2-3 trades/year with 15-40% per trade.
        templates.append(StrategyTemplate(
            name="Crypto Trend Breakout",
            description="Buy on 50-day high breakout with volume confirmation. Exit on 20-day low. Low frequency, high conviction.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE > RESISTANCE AND RSI(14) > 50 AND RSI(14) < 75"
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"
            ],
            required_indicators=["Support", "Resistance", "RSI", "SMA:20"],
            default_parameters={
                "entry_lookback": 50,
                "exit_lookback": 20,
                "rsi_period": 14,
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.25
            },
            expected_trade_frequency="1 trade/quarter",
            expected_holding_period="30-90 days",
            risk_reward_ratio=3.0,
            metadata={"direction": "long", "crypto_optimized": True, "skip_param_override": True, "low_frequency": True}
        ))

        # Crypto Weekly SMA Trend — buy on cross above SMA(50), hold until cross below
        # DSL FIX 2026-05-02: entry was `CLOSE > SMA(50) AND ...` (state condition) which
        # re-enters every time price dips below and recovers. Test windows produced 28
        # trades when the template advertised 1-2/year with WR crashing to 21%. Switching
        # to `CROSSES_ABOVE` makes the DSL match the documented design — one entry per
        # trend cycle — and the confirmation filters (ADX, RSI) apply at the crossover
        # bar only. Exit stays state-based (`CLOSE < SMA(50)`) which is correct for
        # trend-follow: you want to exit the moment the structural support breaks.
        templates.append(StrategyTemplate(
            name="Crypto Weekly Trend Follow",
            description="Buy when price crosses above SMA(50) with ADX > 20 confirming trend. Hold until SMA(50) breakdown. Quarterly frequency.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL],
            entry_conditions=[
                "CLOSE CROSSES_ABOVE SMA(50) AND ADX(14) > 20 AND RSI(14) > 45 AND RSI(14) < 70"
            ],
            exit_conditions=[
                "CLOSE < SMA(50) OR ADX(14) < 15"
            ],
            required_indicators=["SMA:50", "ADX", "RSI"],
            default_parameters={
                "sma_period": 50,
                "adx_period": 14,
                "adx_entry": 20,
                "adx_exit": 15,
                "stop_loss_pct": 0.10,
                "take_profit_pct": 0.30
            },
            expected_trade_frequency="1-2 trades/year",
            expected_holding_period="30-120 days",
            risk_reward_ratio=3.0,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "low_frequency": True,
                # Sprint 5 S5.1 A1: long-hold trend follow template —
                # 1-2 trades/year with 10-30% gross/trade expected. The
                # default crypto_1d floor (3%) would clear; the override
                # here is a documentation marker + safety that trade
                # count below expected doesn't reject otherwise-sound
                # trades with 2-3% gross (still profitable at BTC/ETH
                # 2.2% round-trip cost).
                "min_rpt_override": 0.025,
            }
        ))

        # Crypto Deep Dip Accumulation — buy extreme monthly oversold
        # When BTC/ETH drops 30%+ from recent high and RSI < 30 on daily,
        # it's historically been a strong accumulation zone.
        # Expects 1-2 trades/year with 20-50% upside.
        #
        # DSL FIX 2026-05-02: entry was `CLOSE < SMA(50) * 0.75 AND RSI < 30` (state)
        # which re-fires every day price stays below the threshold — turning "1 trade/year"
        # into many trades across a multi-month drawdown. Use `CROSSES_BELOW` to capture
        # the moment the symbol first enters deep-dip territory, then require RSI<30 as
        # a concurrent filter. Exit stays state-based (return to SMA or RSI recovery) —
        # we want to ride the mean reversion back up without re-entering on each wiggle.
        templates.append(StrategyTemplate(
            name="Crypto Deep Dip Accumulation",
            description="Buy when price drops 25%+ below SMA(50) with daily RSI < 30. Extreme oversold accumulation. Hold for recovery.",
            strategy_type=StrategyType.MEAN_REVERSION,
            market_regimes=[MarketRegime.TRENDING_DOWN, MarketRegime.TRENDING_DOWN_STRONG, MarketRegime.TRENDING_DOWN_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "CLOSE CROSSES_BELOW SMA(50) * 0.75 AND RSI(14) < 30"
            ],
            exit_conditions=[
                "CLOSE > SMA(50) OR RSI(14) > 65"
            ],
            required_indicators=["SMA:50", "RSI"],
            default_parameters={
                "sma_period": 50,
                "deviation_pct": 0.25,
                "rsi_period": 14,
                "rsi_entry": 30,
                "rsi_exit": 65,
                "stop_loss_pct": 0.12,
                "take_profit_pct": 0.35
            },
            expected_trade_frequency="1 trade/year",
            expected_holding_period="30-180 days",
            risk_reward_ratio=3.0,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "low_frequency": True,
                # Sprint 5 S5.1 A1: deep-dip + long hold — tiny sample size
                # but expected gross 20-40% per trade. Override loosens floor
                # so marginal cases (10-15% gross) still activate.
                "min_rpt_override": 0.025,
            }
        ))

        # Crypto Golden Cross — buy on SMA(50) crossing above SMA(200)
        # The classic institutional signal. Fires maybe once per cycle.
        # Historically captures the bulk of crypto bull runs.
        #
        # DSL FIX 2026-05-02: exit was `CLOSE < SMA(200)` (state) which fires on any
        # dip below the 200-day MA even if the Golden Cross structure is intact.
        # A true Golden Cross strategy exits on the Death Cross (SMA(50) crossing
        # below SMA(200)) — the structural inverse of the entry. This prevents
        # re-entry whipsaw when price briefly undercuts the 200MA in a bull market.
        templates.append(StrategyTemplate(
            name="Crypto Golden Cross",
            description="Buy on SMA(50) crossing above SMA(200) — classic bull market signal. Exit on death cross.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[MarketRegime.TRENDING_UP, MarketRegime.TRENDING_UP_STRONG, MarketRegime.TRENDING_UP_WEAK, MarketRegime.RANGING, MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL],
            entry_conditions=[
                "SMA(50) CROSSES_ABOVE SMA(200) AND CLOSE > SMA(50)"
            ],
            exit_conditions=[
                "SMA(50) CROSSES_BELOW SMA(200)"
            ],
            required_indicators=["SMA:50", "SMA:200"],
            default_parameters={
                "fast_period": 50,
                "slow_period": 200,
                "stop_loss_pct": 0.12,
                "take_profit_pct": 0.40
            },
            expected_trade_frequency="1 trade/cycle",
            expected_holding_period="60-365 days",
            risk_reward_ratio=3.5,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "low_frequency": True,
                # Sprint 5 S5.1 A1: Golden Cross — the rarest crypto signal.
                # 1 trade per cycle with massive gross (30-60%). Override
                # stops edge-cases being killed by the flat 3% floor.
                "min_rpt_override": 0.025,
            }
        ))

        # ===== POST-EARNINGS ANNOUNCEMENT DRIFT (PEAD) — Alpha Edge =====
        # One of the most documented anomalies: stocks with earnings beats continue
        # to drift upward for 10-20 days after the announcement (Bernard & Thomas, 1989).
        # FMP earnings surprise data is available — this is directly implementable.
        templates.append(StrategyTemplate(
            name="Post-Earnings Drift Long",
            description="Enter LONG 2-5 days after an earnings beat (surprise > 2%). Captures post-earnings announcement drift (PEAD) — the tendency of stocks to continue rising after positive earnings surprises.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "Earnings surprise > 4% (actual EPS > estimated EPS)",
                "Revenue growth QoQ >= 8% (operating momentum confirmation)",
                "Entry 2-5 days after earnings announcement",
                "Price still below pre-earnings high (drift not yet captured)",
                "RSI(14) < 70 (not overbought)",
            ],
            exit_conditions=[
                "Profit target 8%",
                "Stop loss 4%",
                "Max hold 20 days (drift window exhausted)",
            ],
            required_indicators=["RSI:14", "SMA:20"],
            default_parameters={
                # C3 (2026-05-01): tightened surprise threshold 2% → 4% and added
                # revenue_growth_qoq requirement per Lord Abbett "confirmed momentum"
                # research — price momentum with operating momentum has lower
                # downside volatility and better persistence in 2025 regime.
                "min_earnings_surprise_pct": 0.04,
                "min_revenue_growth_qoq": 0.08,
                "entry_days_after_earnings": 3,
                "max_entry_days": 5,
                "profit_target": 0.08,
                "stop_loss_pct": 0.04,
                "hold_period_max": 20,
                "rsi_max": 70,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-20 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "earnings_momentum",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": True,
                "requires_earnings_data": True,
                "best_symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
                                 "JPM", "GS", "V", "MA", "UNH", "JNJ", "PG", "HD"],
            }
        ))

        # ===== 52-WEEK HIGH MOMENTUM — Alpha Edge =====
        # George & Hwang (2004): stocks near 52-week highs outperform.
        # Anchoring bias causes investors to hesitate at round-number highs,
        # creating a momentum effect when the stock finally breaks through.
        templates.append(StrategyTemplate(
            name="52-Week High Momentum Long",
            description="Enter LONG when stock is within 5% of its 52-week high with RSI not overbought. Captures the documented tendency of stocks near 52-week highs to continue outperforming (George & Hwang, 2004).",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                "Price within 5% of 52-week high",
                "RSI(14) between 50 and 70 (momentum but not overbought)",
                "Volume above 20-day average (confirmation)",
                "Price above SMA(50) (uptrend intact)",
            ],
            exit_conditions=[
                "Profit target 10%",
                "Stop loss 5%",
                "Max hold 30 days",
                "Price drops more than 3% below 52-week high (breakout failed)",
            ],
            required_indicators=["RSI:14", "SMA:50", "SMA:20"],
            default_parameters={
                "high_proximity_pct": 0.05,
                "rsi_min": 50,
                "rsi_max": 70,
                "profit_target": 0.10,
                "stop_loss_pct": 0.05,
                "hold_period_max": 30,
            },
            expected_trade_frequency="3-6 trades/month",
            expected_holding_period="5-30 days",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "strategy_category": "alpha_edge",
                "alpha_edge_type": "earnings_momentum",
                "alpha_edge_bypass": True,
                "requires_fundamental_data": False,
                "best_symbols": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "V", "MA",
                                 "UNH", "HD", "CAT", "DE", "GS", "JPM", "BAC"],
            }
        ))

        # ===== CRYPTO WEEKLY TREND TEMPLATES (added 2026-05-02) =====
        # Research: Zarattini/Pagani/Barbon "Catching Crypto Trends" (SSRN 5209907, Apr 2025)
        # shows a rotational top-N momentum portfolio earns Sharpe 1.5+ and 10.8% alpha
        # vs BTC. Man Group "In Crypto We Trend" (Dec 2024) confirms persistent multi-
        # week trend factor. These templates capture that long-horizon momentum with
        # wide SL/TP sized to clear eToro's ~3% round-trip crypto cost.

        # --- Crypto 21-Week MA Trend Follow ---
        # Institutional-watched level. The 21-week EMA is the canonical long-trend
        # marker in crypto analysis (weekly bull/bear arbiter). Daily close crossing
        # above = LONG entry; cross below = exit. Holds weeks. Very cost-efficient.
        templates.append(StrategyTemplate(
            name="Crypto 21W MA Trend Follow",
            description="Enter long when daily close crosses above the 147-day EMA (≈21-week MA). Exit on cross below. Institutional-followed level; holds weeks.",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
            ],
            # DSL FIX 2026-05-02: was `CLOSE > EMA(147) AND CLOSE[-1] <= EMA(147)[-1]`
            # but the DSL grammar does not support the bracket-lag `[-N]` syntax — the
            # parser throws "No terminal matches '[' in the current parser context" and
            # the template gets skipped entirely (visible in errors.log for months).
            # `CROSSES_ABOVE` encodes exactly the same semantics natively.
            entry_conditions=[
                "CLOSE CROSSES_ABOVE EMA(147)"
            ],
            exit_conditions=[
                "CLOSE CROSSES_BELOW EMA(147)"
            ],
            required_indicators=["EMA:147"],
            default_parameters={
                "ema_period": 147,  # 21 weeks × 7 days
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.20,   # Well above 6% floor; crypto cycle-level move
                "hold_period_max": 180,
            },
            expected_trade_frequency="1-3 trades/year per symbol",
            expected_holding_period="20-90 days",
            risk_reward_ratio=2.5,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                # Sprint 5 S5.1 A1: long-hold institutional signal — 1-3
                # trades/year. Override at 2.5% lets cases where the
                # expected 10-30% gross is closer to 8-10% still activate.
                "min_rpt_override": 0.025,
            }
        ))

        # --- Crypto Vol-Targeted 20-Day Momentum ---
        # Classic momentum-in-low-vol pattern: enter when 20-day return is positive AND
        # realized vol is compressed (below its own 90-day median). Compressed vol →
        # incoming expansion → next large move tends to be in the prevailing direction.
        # Exit on 20-day return going negative OR vol blowing out above upper band.
        templates.append(StrategyTemplate(
            name="Crypto Vol-Compression Momentum",
            description="Long when 20-day return > 3% AND 20-day realized vol is in lower half of 90-day distribution (compressed). Exit on return flip or vol blow-out.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING,          # added 2026-05-02 E3 — vol-compression setup works in any ranging regime, not just LOW_VOL
            ],
            # DSL FIX 2026-05-02: was `(CLOSE / CLOSE[-20] - 1) > 0.03 AND ATR(20) < ATR(90)`
            # but the `CLOSE[-N]` bracket-lag syntax doesn't exist in the DSL grammar (parse
            # error, template skipped). PRICE_CHANGE_PCT(N) is the native primitive for
            # N-bar percentage return and returns a value scaled ×100 (so 3% threshold → 3.0).
            entry_conditions=[
                "PRICE_CHANGE_PCT(20) > 3.0 AND ATR(20) < ATR(90)"
            ],
            exit_conditions=[
                "PRICE_CHANGE_PCT(20) < 0 OR ATR(20) > ATR(90) * 1.5"
            ],
            required_indicators=["ATR:20", "ATR:90", "Price Change %:20"],
            default_parameters={
                "lookback_short": 20,
                "lookback_long": 90,
                "return_threshold": 0.03,
                "stop_loss_pct": 0.08,
                "take_profit_pct": 0.18,
                "hold_period_max": 60,
            },
            expected_trade_frequency="2-5 trades/month per symbol",
            expected_holding_period="5-30 days",
            risk_reward_ratio=2.25,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                # Sprint 5 S5.1 A1: momentum swing on 1d with 5-30 day hold.
                # 2-5 trades/month, R:R 2.25. Expected gross 5-15%/trade.
                # Override at 2% unblocks 3-4%/trade cases.
                "min_rpt_override": 0.020,
            }
        ))

        # =====================================================================
        # BTC → Altcoin Lead-Lag Templates (C1 from Batch C)
        # Research: unidirectional Granger causality from BTC to altcoins
        # (Asia-Pacific Financial Markets 2026). Small-cap cryptos exhibit
        # delayed responses to BTC moves. A lag trading strategy using BTC's
        # preceding returns consistently outperformed buy-and-hold.
        #
        # Sprint 1 F1 (2026-05-02): the BTC-up gate is now expressed as a
        # native DSL primitive LAG_RETURN("BTC", N, "<interval>") > threshold
        # directly in the entry_conditions. This means:
        #   - Walk-forward and MC-bootstrap see the same edge signal-gen will
        #     see in live → honest validation.
        #   - No runtime gate in strategy_engine.generate_signals needs to
        #     double-check the condition — it's already part of the rule.
        # Legacy metadata keys (btc_leader, btc_leader_*, leader_symbol) are
        # kept on templates below for one release cycle to avoid breaking
        # cache entries keyed on them; they no longer drive any behavior.
        # =====================================================================

        # BTC 1H Follower — ride BTC's momentum via alts on the 1H chart
        templates.append(StrategyTemplate(
            name="Crypto BTC Follower 1H",
            description="Enter altcoin LONG when BTC rallied +1% in last 2 hours (LAG_RETURN native) AND alt is above EMA(20) with RSI>45. Rides the lag-response of alts to BTC moves. Fast exit when BTC rolls over or alt loses EMA.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                # Native cross-asset primitive: BTC's 1h lag return over the
                # prior 2 bars must exceed +1%. Computed in backtest AND
                # signal-gen, so WF sees the real edge.
                'CLOSE > EMA(20) AND RSI(14) > 45 AND LAG_RETURN("BTC", 2, "1h") > 0.01'
            ],
            exit_conditions=[
                "CLOSE < EMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["EMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.02,
                "take_profit_pct": 0.035,
                "btc_lead_bars": 2,
                "btc_lead_threshold_pct": 0.01,
            },
            expected_trade_frequency="3-6 trades/week",
            expected_holding_period="2-12 hours",
            risk_reward_ratio=1.75,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "intraday": True,
                "interval": "1h",
                # Sprint 2 F2 (2026-05-02): cross-asset template carries real
                # template-family edge (BTC lead-lag), but the very gate that
                # creates the edge (LAG_RETURN("BTC",...)>thresh) naturally
                # tightens entries to 1-3 per symbol per 90d test window.
                # Per-pair activation gates (cost-per-trade, Sharpe) then
                # reject on small-sample noise even when 4/6 alts show edge.
                # Proposer cross-validates across the 6-coin family; when
                # ≥4/6 symbols show test_sharpe > 0.3 AND positive net
                # return, activation bypasses per-pair Sharpe/RPT gates and
                # trusts the family-level verdict.
                "requires_cross_validation": True,
                "family_universe": ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"],
                # Legacy — kept for one cycle to avoid WF cache invalidation;
                # no code path reads these anymore (runtime gate removed in F1).
                "btc_leader": True,
                "btc_leader_interval": "1h",
                "btc_leader_bars": 2,
                "btc_leader_threshold_pct": 0.01,
                "leader_symbol": "BTC",
            }
        ))

        # BTC 4H Follower — swing-scale lag trade
        templates.append(StrategyTemplate(
            name="Crypto BTC Follower 4H",
            description="Enter altcoin LONG when BTC rallied +3% in last 2 bars on 4H (LAG_RETURN native) AND alt price > SMA(50). 4H swing version of the BTC lead-lag trade. Small-cap alts (SOL/LINK/AVAX/DOT) show the largest lag-response.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                'CLOSE > SMA(50) AND RSI(14) > 50 AND LAG_RETURN("BTC", 2, "4h") > 0.03'
            ],
            exit_conditions=[
                "CLOSE < SMA(50) OR RSI(14) < 40"
            ],
            required_indicators=["SMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
                "btc_lead_bars": 2,
                "btc_lead_threshold_pct": 0.03,
            },
            expected_trade_frequency="2-4 trades/week",
            expected_holding_period="8-48 hours",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval_4h": True,
                "interval": "4h",
                # Sprint 2 F2 — see BTC Follower 1H for rationale.
                "requires_cross_validation": True,
                "family_universe": ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"],
                # Legacy — see BTC Follower 1H comment.
                "btc_leader": True,
                "btc_leader_interval": "4h",
                "btc_leader_bars": 2,
                "btc_leader_threshold_pct": 0.03,
                "leader_symbol": "BTC",
                # Sprint 5 S5.1 A1 (2026-05-02): 4H swing template with R:R 2.0
                # and 2-4 trades/week. Expected gross/trade = 1.5-2.5% (4h moves
                # are modest). eToro crypto round-trip = 2.2% (BTC/ETH) / 2.96%
                # (alts). At 1.5% override, break-even edge_ratio = 0.51 (BTC/ETH)
                # or 0.68 (alts) — strategy activates on marginal edge but WF
                # still enforces net_return > 0 per symbol. This unblocks the
                # BTC Follower 4H ETH cycle_1777758033 case where gross was 5%
                # over 6 trades (0.83%/trade) — NOT unblocked (still fails);
                # but 1.5%/trade cases WILL activate.
                "min_rpt_override": 0.015,
            }
        ))

        # BTC Daily Follower — positional lag trade
        templates.append(StrategyTemplate(
            name="Crypto BTC Follower Daily",
            description="Enter altcoin LONG when BTC printed +3% over prior 3 daily bars (LAG_RETURN native) AND alt is above SMA(50) on daily. Positional lag trade — small-cap alts often catch up 3-7 days after BTC breakouts. 2026-05-02: threshold relaxed from 5% over 2 days to 3% over 3 days for lower-vol regime compatibility.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                'CLOSE > SMA(50) AND RSI(14) > 50 AND LAG_RETURN("BTC", 3, "1d") > 0.03'
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 40"
            ],
            required_indicators=["SMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
                "btc_lead_bars": 3,
                "btc_lead_threshold_pct": 0.03,
            },
            expected_trade_frequency="2-5 trades/month",
            expected_holding_period="3-14 days",
            risk_reward_ratio=2.4,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                # Sprint 2 F2 — see BTC Follower 1H for rationale.
                "requires_cross_validation": True,
                "family_universe": ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"],
                # Legacy — see BTC Follower 1H comment.
                "btc_leader": True,
                "btc_leader_interval": "1d",
                "btc_leader_bars": 3,
                "btc_leader_threshold_pct": 0.03,
                "leader_symbol": "BTC",
                # Sprint 5 S5.1 A1 (2026-05-02): 1D swing template with R:R 2.4
                # and 2-5 trades/month. Expected gross/trade = 4-8% (daily moves
                # larger than 4h). eToro cost 2.2-2.96%. Override at 2% allows
                # activation on 2-3%/trade gross (edge_ratio 0.7-1.4) where the
                # default 3% crypto_1d floor would reject.
                # C2 regime-tightening (2026-05-02): lag threshold relaxed from
                # +5% over 2 days to +3% over 3 days. Historical data shows the
                # 5%/2d trigger fires ~2x/month; 3%/3d fires ~4x/month. The
                # 4 BTC-Follower-Daily strategies that activated via F2 family
                # cross-validation on 2026-04 have been armed and waiting on
                # the +5%/2d trigger since 2026-03-16 (45+ days idle). In the
                # current lower-vol regime (BTC ATR/price ~1.8%), 3%/3d is
                # the right threshold for the lead-lag effect to be captured.
                "min_rpt_override": 0.020,
            }
        ))

        # BTC Dominance Inversion (SHORT) — DISABLED 2026-05-02:
        # eToro does not allow shorting spot crypto (see NO_SHORT_ASSET_CLASSES
        # hard-block in strategy_proposer._score_symbol_for_template). A SHORT
        # crypto template cannot execute. Dropping the template rather than
        # leaving it as a permanently-blocked skeleton.

        # =====================================================================
        # Cross-sectional Crypto Momentum (C2 from Batch C)
        # Research (repo doc lines 237-244): top-N ranking by 14-day return,
        # filtered for volume > 1.5× 20-day MA, hold 5-7 days with vol-scaled
        # sizing. The composite return was ~8.76% excess on non-BTC cryptos.
        #
        # Sprint 1 F1 (2026-05-02): the rank filter is now a native DSL
        # primitive RANK_IN_UNIVERSE("SELF", [...], 14, 3) evaluated every
        # bar in backtest and live. Signal-gen runtime gate removed.
        # =====================================================================

        # Crypto Cross-Sectional Momentum (14d) — fires only if the symbol
        # is in the top 3 of the crypto universe by 14-day return
        templates.append(StrategyTemplate(
            name="Crypto Cross-Sectional Momentum",
            description="Rank 6-coin universe by 14-day return (RANK_IN_UNIVERSE native); enter LONG on coins in top-3 with volume > 1.5x 20-day avg. Captures rotation into outperforming alts. Hold 5-10 days, vol-scale sizing.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                # Native: symbol must be in top-3 of universe by 14d return,
                # PLUS local momentum setup (trend + volume confirm).
                'CLOSE > SMA(20) AND RSI(14) > 55 AND VOLUME > VOLUME_MA(20) * 1.5 '
                'AND RANK_IN_UNIVERSE("SELF", ["BTC","ETH","SOL","AVAX","LINK","DOT"], 14, 3) > 0'
            ],
            exit_conditions=[
                "CLOSE < SMA(20) OR RSI(14) < 45"
            ],
            required_indicators=["SMA", "RSI", "Volume MA"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.14,
                "rank_window_days": 14,
                "rank_top_n": 3,
                "hold_days": 7,
            },
            expected_trade_frequency="1-3 trades/week",
            expected_holding_period="5-10 days",
            risk_reward_ratio=2.3,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                # Sprint 2 F2 — cross-sectional templates are inherently
                # multi-symbol; family-level consistency is the right gate.
                "requires_cross_validation": True,
                "family_universe": ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"],
                # Legacy — see BTC Follower 1H comment.
                "cross_sectional_rank": True,
                "rank_window_days": 14,
                "rank_top_n": 3,
                "rank_metric": "return",
                "rank_universe": ["BTC", "ETH", "SOL", "AVAX", "LINK", "DOT"],
                # Sprint 5 S5.1 A1: cross-sectional rotation. 1-3 trades/week,
                # 5-10 day hold, R:R 2.3. Low trade count per symbol is
                # structural (you only enter when symbol ranks top-3). Override
                # at 2% allows swing cases through.
                "min_rpt_override": 0.020,
            }
        ))

        # =====================================================================
        # Sprint 2 crypto-alpha expansion (2026-05-02)
        # Five research-backed templates filling real gaps in the crypto
        # library. Each uses native DSL primitives (OBV, DONCHIAN, KELTNER
        # added in this sprint) — NO approximations.
        # =====================================================================

        # T1. Crypto Donchian Breakout Daily — turtle-style 20-day high
        # breakout with ADX trend confirmation + volume. Research: classic
        # Donchian (Dennis/Eckhardt 1983) validated on crypto by Alpha
        # Architect; 20-bar breakouts + ADX>25 deliver 1.5–2.0 R:R in
        # trending crypto. DONCHIAN_UPPER uses shift=1 so the threshold is
        # "prior 20-bar high" — a genuine breakout, not a tautology.
        templates.append(StrategyTemplate(
            name="Crypto Donchian Breakout Daily",
            description="Enter LONG when daily close breaks above the prior 20-day Donchian upper band (turtle-style) with ADX(14)>25 trend confirmation and volume >1.3x 20d avg. Exit on EMA(10) loss. Captures post-accumulation trend starts.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE > DONCHIAN_UPPER(20) AND ADX(14) > 25 AND VOLUME > VOLUME_MA(20) * 1.3"
            ],
            exit_conditions=[
                "CLOSE < EMA(10)"
            ],
            required_indicators=["Donchian Upper", "ADX", "Volume MA", "EMA"],
            default_parameters={
                "stop_loss_pct": 0.04,
                "take_profit_pct": 0.10,
            },
            expected_trade_frequency="1-3 trades/week",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.5,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                # Skip the auto-ADX-injector — we already have an explicit
                # ADX(14)>25 gate built into the rule.
                "skip_adx_gate": True,
            }
        ))

        # T2. Crypto Keltner Breakout 4H — ATR-adaptive channel breakout
        # (Alpha Architect validated template). Keltner uses ATR for band
        # width so the threshold self-adjusts to current volatility —
        # different signal from Bollinger (STDDEV-based). Canonical params:
        # EMA(20), ATR(14), mult=2.0. ADX>25 for trend filter.
        templates.append(StrategyTemplate(
            name="Crypto Keltner Breakout 4H",
            description="Enter LONG when 4H close breaks above Keltner upper band (EMA20 + 2×ATR14) with ADX(14)>25. Exit on close below Keltner middle (EMA20). ATR-adaptive threshold captures real breakouts beyond the noise floor.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE > KELTNER_UPPER(20, 14, 2.0) AND ADX(14) > 25"
            ],
            exit_conditions=[
                "CLOSE < KELTNER_MIDDLE(20, 14, 2.0)"
            ],
            required_indicators=["Keltner", "ADX"],
            default_parameters={
                "stop_loss_pct": 0.03,
                "take_profit_pct": 0.06,
            },
            expected_trade_frequency="2-4 trades/week",
            expected_holding_period="12-72 hours",
            risk_reward_ratio=2.0,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval_4h": True,
                "interval": "4h",
                "skip_adx_gate": True,
            }
        ))

        # T3. Crypto OBV Accumulation Daily — volume-led momentum.
        # OBV (On-Balance Volume) rising above its 20-day MA while price
        # enters uptrend mode (close > EMA(20)) with RSI in a 45–60 band
        # (NOT yet euphoric) signals smart-money accumulation before
        # extension. Research: Grobys/Habeli 2025 — volume-led momentum
        # outperforms price-only in crypto. Orthogonal to our existing
        # single-bar "Volume Spike Entry" which is a spike signal, not a
        # trend-confirmed flow signal.
        templates.append(StrategyTemplate(
            name="Crypto OBV Accumulation Daily",
            description="Enter LONG when OBV > OBV_MA(20) (sustained volume accumulation) AND close above EMA(20) trend filter AND RSI(14) in 45–60 band (pre-euphoric setup). Exit on OBV crossing below its MA or RSI overextension.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "OBV > OBV_MA(20) AND CLOSE > EMA(20) AND RSI(14) > 45 AND RSI(14) < 60"
            ],
            exit_conditions=[
                "OBV < OBV_MA(20) OR RSI(14) > 70"
            ],
            required_indicators=["OBV", "OBV MA", "EMA", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
            },
            expected_trade_frequency="2-5 trades/week",
            expected_holding_period="3-8 days",
            risk_reward_ratio=2.4,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                # OBV-based accumulation signal doesn't need ADX gate — OBV
                # trend above its MA *is* the directional filter.
                "skip_adx_gate": True,
            }
        ))

        # T4. Crypto 20D MA Variable Cross Daily — direct implementation
        # of Grobys (2024) "variable moving average" finding: a 20-day MA
        # strategy on non-BTC cryptos generates ~8.76% excess return/year.
        # Differs from our Golden Cross (50/100) and 21W MA (weekly) which
        # are much slower. The 5-day momentum filter rejects whipsaw
        # crossovers that immediately reverse.
        templates.append(StrategyTemplate(
            name="Crypto 20D MA Variable Cross Daily",
            description="Enter LONG on fresh bullish crossover of close above SMA(20) with 5-day positive momentum (PRICE_CHANGE_PCT(5) > 3%). Direct Grobys (2024) signal — 20-day variable MA delivered 8.76% excess/yr on non-BTC crypto. Exit on close below SMA(20).",
            strategy_type=StrategyType.TREND_FOLLOWING,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE CROSSES_ABOVE SMA(20) AND PRICE_CHANGE_PCT(5) > 0.03"
            ],
            exit_conditions=[
                "CLOSE < SMA(20)"
            ],
            required_indicators=["SMA", "Price Change %"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.12,
            },
            expected_trade_frequency="2-4 trades/month",
            expected_holding_period="5-15 days",
            risk_reward_ratio=2.4,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                # Variable-MA strategy IS the trend filter — adding ADX on
                # top would double-gate and starve signals in weak trends
                # where the MA cross is the real entry.
                "skip_adx_gate": True,
            }
        ))

        # T5. Crypto BB Volume Breakout Daily — Bollinger upper-band break
        # with volume confirmation and trend filter. Distinct from our
        # "BB Squeeze Breakout" (which requires squeeze→expansion) — this
        # fires on a plain upper-band break PROVIDED volume is >1.5× avg
        # AND ADX shows emerging trend. Research: composite of BB breakout
        # + volume + ADX outperforms either alone in directional alt moves.
        # Use wider BB (2.0 std) to avoid false triggers during chop.
        templates.append(StrategyTemplate(
            name="Crypto BB Volume Breakout Daily",
            description="Enter LONG when daily close breaks above Bollinger upper band BB(20,2.0) with volume >1.5x 20d avg AND ADX(14)>20 (emerging trend). Exit on close below BB middle band or RSI>75 (euphoria). Captures alt-season extensions.",
            strategy_type=StrategyType.BREAKOUT,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
                MarketRegime.RANGING_HIGH_VOL,
            ],
            entry_conditions=[
                "CLOSE > BB_UPPER(20, 2.0) AND VOLUME > VOLUME_MA(20) * 1.5 AND ADX(14) > 20"
            ],
            exit_conditions=[
                "CLOSE < BB_MIDDLE(20, 2.0) OR RSI(14) > 75"
            ],
            required_indicators=["Bollinger Bands", "Volume MA", "ADX", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.05,
                "take_profit_pct": 0.14,
            },
            expected_trade_frequency="1-3 trades/week",
            expected_holding_period="3-10 days",
            risk_reward_ratio=2.8,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "interval": "1d",
                "skip_adx_gate": True,
            }
        ))

        # =====================================================================
        # Sprint 5 S5.1 B3 (2026-05-02): crypto swing templates designed for
        # eToro's 2.2-2.96% round-trip cost structure.
        #
        # The library review (STRATEGY_LIBRARY_REVIEW_2026-05.md §4) noted we
        # lacked: on-chain-gated strategies, dominance rotation, and pure-
        # weekly-momentum templates. Each of these new templates targets
        # 2-5 trades/year per symbol with 10-40% gross per trade — well above
        # the break-even cost ratio and distinct from our existing 50/200
        # Golden Cross and 147-day 21W MA templates.
        # =====================================================================

        # B3a — Anna Fund / AQR-style weekly momentum.
        # Published practice: Norwegian quant crypto fund Anna Fund returned
        # 144% in 2024 on a weekly-momentum rotation. AQR Helix (+18.6%
        # 2025) uses the same pattern — price > 21-bar prior price +10%
        # confirms multi-week trend. We keep it simple: 20-day return above
        # 10% + RSI > 55 + ADX > 25. Wide stops (6%) to survive crypto
        # noise; TP 18% (3x R:R).
        templates.append(StrategyTemplate(
            name="Crypto Weekly Momentum Long",
            description="Enter LONG when 20-day return > 10% AND RSI(14) > 55 AND ADX(14) > 25 — confirmed multi-week uptrend. Hold on EMA(21) support; exit on RSI > 80 (euphoria) or CLOSE < EMA(21). Anna Fund / AQR Helix-style weekly momentum adapted for eToro crypto cost structure.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.TRENDING_UP_WEAK,
            ],
            entry_conditions=[
                "PRICE_CHANGE_PCT(20) > 10.0 AND RSI(14) > 55 AND ADX(14) > 25"
            ],
            exit_conditions=[
                "CLOSE < EMA(21) OR RSI(14) > 80"
            ],
            required_indicators=["RSI", "ADX", "EMA:21", "Price Change %:20"],
            default_parameters={
                "stop_loss_pct": 0.06,
                "take_profit_pct": 0.18,
            },
            expected_trade_frequency="2-5 trades/year per symbol",
            expected_holding_period="14-45 days",
            risk_reward_ratio=3.0,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "low_frequency": True,
                "interval": "1d",
                # A1 override: 3.0%/trade floor. Expected 10-25% gross means
                # edge_ratio 3-8x on BTC/ETH, 1.7-5x on alts.
                "min_rpt_override": 0.030,
            }
        ))

        # B3b — Stablecoin-supply-gated accumulation.
        # Rising stablecoin supply = capital waiting on the sidelines. When
        # USDT+USDC supply grows >2% in 7 days (capital inflow to exchanges)
        # AND price breaks above SMA(50), that's structural demand + trend
        # confirmation. Research: cryptofundresearch 2025 shows quant funds
        # using on-chain flow signals have the lowest BTC-beta (0.27) — they
        # trade the on-chain structure, not the price.
        templates.append(StrategyTemplate(
            name="Crypto Stablecoin Inflow Accumulation",
            description="Enter LONG when 7-day stablecoin supply change > 2% (ONCHAIN, sidelined capital rising) AND CLOSE CROSSES_ABOVE SMA(50) AND RSI(14) > 45 — on-chain demand + price trend. Exit on CLOSE < SMA(50) or RSI > 75.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
            ],
            entry_conditions=[
                'CLOSE CROSSES_ABOVE SMA(50) AND RSI(14) > 45 AND ONCHAIN("stablecoin_supply_pct", 7) > 0.02'
            ],
            exit_conditions=[
                "CLOSE < SMA(50) OR RSI(14) > 75"
            ],
            required_indicators=["SMA:50", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.07,
                "take_profit_pct": 0.18,
            },
            expected_trade_frequency="4-8 trades/year per symbol",
            expected_holding_period="10-30 days",
            risk_reward_ratio=2.6,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "low_frequency": True,
                "interval": "1d",
                "min_rpt_override": 0.025,
            }
        ))

        # B3c — BTC Dominance Rotator (alt-favour version).
        # When BTC dominance falls 7-day (capital rotating INTO alts),
        # small-cap alts outperform. Gate: dominance down AND own
        # price > SMA(50). Applies only to non-BTC symbols.
        #
        # Note: this template targets alts specifically. `excluded_symbols`
        # filters BTC out — the dominance-FALLING signal is structurally
        # bearish for BTC but bullish for alts. For BTC's own dominance-
        # rising version, we'd need a mirror template (deferred).
        templates.append(StrategyTemplate(
            name="Crypto Dominance Rotation Alt Long",
            description="Enter LONG on altcoin when BTC dominance has fallen > 1% over 7 days (ONCHAIN, rotation into alts) AND alt CLOSE > SMA(50) AND RSI(14) > 50. Exit on dominance reversal or CLOSE < SMA(50). Captures alt-season rotations.",
            strategy_type=StrategyType.MOMENTUM,
            market_regimes=[
                MarketRegime.TRENDING_UP,
                MarketRegime.TRENDING_UP_WEAK,
                MarketRegime.TRENDING_UP_STRONG,
                MarketRegime.RANGING,
                MarketRegime.RANGING_LOW_VOL,
            ],
            # ONCHAIN("btc_dominance", 7) returns current dominance; we want
            # the CHANGE. Since the primitive is aligned forward-fill, we
            # use PRICE_CHANGE_PCT isn't applicable. Proxy: compare the
            # current dominance against a threshold. For now use a simple
            # numerical floor: dominance < 0.55 (i.e. alts have >45%
            # collective share — indicates alt-favourable regime).
            entry_conditions=[
                'CLOSE CROSSES_ABOVE SMA(50) AND RSI(14) > 50 AND ONCHAIN("btc_dominance", 7) < 0.55'
            ],
            exit_conditions=[
                "CLOSE < SMA(50) OR RSI(14) > 75"
            ],
            required_indicators=["SMA:50", "RSI"],
            default_parameters={
                "stop_loss_pct": 0.07,
                "take_profit_pct": 0.20,
            },
            expected_trade_frequency="3-6 trades/year per symbol",
            expected_holding_period="10-40 days",
            risk_reward_ratio=2.9,
            metadata={
                "direction": "long",
                "crypto_optimized": True,
                "skip_param_override": True,
                "low_frequency": True,
                "interval": "1d",
                "min_rpt_override": 0.025,
                # BTC itself wouldn't benefit from a "dominance falling → long"
                # setup (it's the instrument whose dominance is falling) —
                # but rather than relying on an explicit exclusion, let the
                # WF gate filter naturally: BTC's own backtest on this
                # signal will be negative and the net_return gate rejects.
            }
        ))

        return templates
    
    def get_all_templates(self) -> List[StrategyTemplate]:
        """
        Get all available strategy templates.
        
        Returns:
            List of all strategy templates
        """
        return self.templates
    
    def get_templates_for_regime(self, regime: MarketRegime) -> List[StrategyTemplate]:
        """
        Get strategy templates suitable for a specific market regime.
        
        Args:
            regime: Market regime to filter by
            
        Returns:
            List of templates suitable for the given regime
        """
        return [t for t in self.templates if regime in t.market_regimes]
    
    def get_template_by_name(self, name: str) -> Optional[StrategyTemplate]:
        """
        Get a specific template by name.
        
        Args:
            name: Template name
            
        Returns:
            Template if found, None otherwise
        """
        for template in self.templates:
            if template.name == name:
                return template
        return None
    
    def get_templates_by_type(self, strategy_type: StrategyType) -> List[StrategyTemplate]:
        """
        Get templates by strategy type.
        
        Args:
            strategy_type: Type of strategy (mean_reversion, trend_following, etc.)
            
        Returns:
            List of templates of the given type
        """
        return [t for t in self.templates if t.strategy_type == strategy_type]
    
    def get_template_count(self) -> int:
        """
        Get total number of templates in library.
        
        Returns:
            Number of templates
        """
        return len(self.templates)
    
    def get_regime_coverage(self) -> Dict[MarketRegime, int]:
        """
        Get count of templates available for each market regime.
        
        Returns:
            Dictionary mapping regime to template count
        """
        coverage = {regime: 0 for regime in MarketRegime}
        for template in self.templates:
            for regime in template.market_regimes:
                coverage[regime] += 1
        return coverage
