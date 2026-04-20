"""
Conviction Scorer - Scores trading signals based on evidence of profitability.

Philosophy: The best predictor of a profitable trade is a strategy that has
already proven it works on out-of-sample data. Walk-forward validation IS
the evidence. Everything else is secondary.

Scoring dimensions (0-100):
1. Walk-forward edge (0-40): OOS Sharpe, win rate, trade count, consistency
2. Signal quality (0-25): Confidence, risk management, indicator alignment
3. Regime fit (0-20): Strategy type vs current market regime
4. Asset tradability (0-15): Liquidity, spread cost, data quality

Only signals with conviction > threshold are traded.
"""

import logging
import math
from typing import Dict, Any, Optional
from dataclasses import dataclass
from src.models.dataclasses import Strategy, TradingSignal
from src.models.enums import SignalAction
from src.strategy.fundamental_filter import FundamentalFilter, FundamentalFilterReport

logger = logging.getLogger(__name__)


@dataclass
class ConvictionScore:
    """Conviction score breakdown."""
    total_score: float  # 0-100
    signal_strength_score: float  # legacy name kept for DB compatibility
    fundamental_score: float  # legacy name kept for DB compatibility
    regime_alignment_score: float  # legacy name kept for DB compatibility
    breakdown: Dict[str, Any]

    def passes_threshold(self, threshold: float) -> bool:
        """Check if score passes threshold."""
        return self.total_score >= threshold


class ConvictionScorer:
    """
    Scores trading signals based on evidence of profitability.

    The core insight: these strategies already passed walk-forward validation.
    The conviction score should measure HOW STRONG that evidence is, not
    re-litigate whether the strategy is "good enough" with arbitrary checks.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        database: Any,
        fundamental_filter: Optional[FundamentalFilter] = None,
        market_analyzer: Optional[Any] = None
    ):
        self.config = config
        self.database = database
        self.fundamental_filter = fundamental_filter
        self.market_analyzer = market_analyzer

        alpha_edge_config = config.get('alpha_edge', {})
        self.min_conviction_score = alpha_edge_config.get('min_conviction_score', 70)

        logger.info(f"ConvictionScorer initialized - Min score: {self.min_conviction_score}")

    def score_signal(
        self,
        signal: TradingSignal,
        strategy: Strategy,
        fundamental_report: Optional[FundamentalFilterReport] = None
    ) -> ConvictionScore:
        """Score a trading signal based on evidence of profitability."""

        # 1. Walk-forward edge (max 40) — the strongest predictor
        wf_score = self._score_walkforward_edge(strategy)

        # 2. Signal quality (max 25) — confidence, risk mgmt, indicator alignment
        signal_score = self._score_signal_quality(signal, strategy)

        # 3. Regime fit (max 20) — does strategy type match current market?
        regime_score = self._score_regime_fit(strategy)

        # 4. Asset tradability (max 15) — liquidity, spread, data quality
        asset_score = self._score_asset_tradability(signal.symbol, fundamental_report)

        total_score = wf_score + signal_score + regime_score + asset_score

        # 5. Fundamental quality — direction-aware (±15 points)
        # LONG: strong fundamentals → bonus, weak → penalty
        # SHORT: weak fundamentals → bonus, strong → penalty (short the garbage)
        fundamental_quality_adj = self._score_fundamental_quality(signal, fundamental_report)
        total_score += fundamental_quality_adj

        # Carry bias adjustment for forex pairs (±5 points)
        # Positive carry = bonus for longs, penalty for shorts (and vice versa)
        carry_adjustment = self._score_carry_bias(signal)
        total_score += carry_adjustment

        # Crypto halving cycle adjustment (±5 points)
        # Boosts during accumulation/early bull, penalizes during distribution/bear
        crypto_cycle_adjustment = self._score_crypto_cycle(signal)
        total_score += crypto_cycle_adjustment

        # News sentiment adjustment (±8 points) — DB lookup only, never blocks
        # 0.0 when no data yet (neutral, trade proceeds normally)
        news_sentiment_adj = self._score_news_sentiment(signal)
        total_score += news_sentiment_adj

        # Factor exposure adjustment (±6 points) — regime-aware factor tilt
        # In ranging/low-vol: favor low-beta, high-quality (defensive)
        # In trending-up: favor high-momentum, high-beta (offensive)
        factor_adj = self._score_factor_exposure(signal, strategy)
        total_score += factor_adj

        # Normalize total score to 0-100 scale (3.4).
        # Theoretical max = 40+25+20+15+15+5+5+8+6 = 139.
        # Without normalization, the 60 threshold means ~43% of max — semantically misleading.
        # After normalization, 60 means "60% of maximum possible evidence".
        THEORETICAL_MAX = 139.0
        total_score = min(100.0, total_score * (100.0 / THEORETICAL_MAX))

        breakdown = {
            'walkforward_edge': {
                'score': wf_score,
                'max': 40,
                'details': self._get_wf_details(strategy)
            },
            'signal_quality': {
                'score': signal_score,
                'max': 25,
                'details': self._get_signal_details(signal, strategy)
            },
            'regime_fit': {
                'score': regime_score,
                'max': 20,
                'details': self._get_regime_details(strategy)
            },
            'asset_tradability': {
                'score': asset_score,
                'max': 15,
                'details': self._get_asset_details(signal.symbol)
            },
            'carry_bias': {
                'score': carry_adjustment,
                'max': 5,
                'details': self._get_carry_details(signal)
            },
            'fundamental_quality_direction': {
                'score': fundamental_quality_adj,
                'max': 15,
                'details': self._get_fundamental_quality_details(signal, fundamental_report)
            },
            'news_sentiment': {
                'score': news_sentiment_adj,
                'max': 8,
                'details': {'symbol': signal.symbol, 'raw_score': news_sentiment_adj / 8.0 if news_sentiment_adj != 0 else 0.0},
            },
            'factor_exposure': {
                'score': factor_adj,
                'max': 6,
                'details': {'symbol': signal.symbol},
            },
            # Legacy keys for backward compatibility with frontend/analytics
            'signal_strength': {
                'score': signal_score,
                'max': 25,
            },
            'fundamental_quality': {
                'score': asset_score,
                'max': 15,
            },
            'regime_alignment': {
                'score': regime_score,
                'max': 20,
            },
        }

        conviction = ConvictionScore(
            total_score=total_score,
            signal_strength_score=signal_score,
            fundamental_score=asset_score,
            regime_alignment_score=regime_score,
            breakdown=breakdown
        )

        logger.info(
            f"Conviction score for {signal.symbol}: {total_score:.1f}/100 "
            f"(wf_edge: {wf_score:.1f}, signal: {signal_score:.1f}, "
            f"regime: {regime_score:.1f}, asset: {asset_score:.1f}"
            f"{f', fundamental: {fundamental_quality_adj:+.1f}' if fundamental_quality_adj != 0 else ''}"
            f"{f', carry: {carry_adjustment:+.1f}' if carry_adjustment != 0 else ''}"
            f"{f', news: {news_sentiment_adj:+.1f}' if news_sentiment_adj != 0 else ''})"
        )

        self._log_conviction_score(signal, strategy, conviction)
        return conviction

    # ─── 1. WALK-FORWARD EDGE (max 40 points) ───────────────────────────
    def _score_walkforward_edge(self, strategy: Strategy) -> float:
        """
        Score based on walk-forward out-of-sample performance.

        This is the most important dimension. A strategy that produced
        Sharpe 3.0 on unseen data is far more trustworthy than one at 0.3.

        Breakdown:
        - OOS Sharpe ratio: 0-20 points (logarithmic — diminishing returns above 2.0)
        - Win rate quality: 0-8 points (>60% is strong, >50% is acceptable)
        - Trade count confidence: 0-7 points (more trades = more statistical significance)
        - Train/test consistency: 0-5 points (both positive = consistent edge)
        """
        meta = strategy.metadata or {}
        perf = strategy.backtest_results

        score = 0.0

        # --- OOS Sharpe (max 20) ---
        test_sharpe = meta.get('wf_test_sharpe', 0)
        if perf and hasattr(perf, 'sharpe_ratio'):
            test_sharpe = test_sharpe or perf.sharpe_ratio

        if test_sharpe and not (math.isinf(test_sharpe) or math.isnan(test_sharpe)):
            # Logarithmic scaling: Sharpe 0.5→8, 1.0→12, 2.0→17, 3.0→19, 5.0→20
            if test_sharpe > 0:
                sharpe_pts = min(20.0, 8.0 + 6.0 * math.log(1 + test_sharpe))
            else:
                sharpe_pts = max(0.0, 4.0 + test_sharpe * 4.0)  # Negative Sharpe → 0-4 pts
            score += sharpe_pts

        # --- Win rate quality (max 8) ---
        win_rate = None
        if perf and hasattr(perf, 'win_rate'):
            win_rate = perf.win_rate
        if win_rate is not None:
            if win_rate >= 0.65:
                score += 8.0
            elif win_rate >= 0.55:
                score += 6.0
            elif win_rate >= 0.48:
                score += 4.0
            elif win_rate >= 0.40:
                score += 2.0
            # Below 40% win rate: 0 points (need very high R:R to compensate)

        # --- Trade count confidence (max 7) ---
        total_trades = 0
        if perf and hasattr(perf, 'total_trades'):
            total_trades = perf.total_trades or 0
        if total_trades >= 15:
            score += 7.0  # High statistical confidence
        elif total_trades >= 8:
            score += 5.0
        elif total_trades >= 4:
            score += 3.0
        elif total_trades >= 2:
            score += 1.0

        # --- Train/test consistency (max 5) ---
        train_sharpe = meta.get('wf_train_sharpe', 0)
        if train_sharpe and test_sharpe:
            both_positive = train_sharpe > 0 and test_sharpe > 0
            if both_positive:
                # Both periods profitable — consistent edge
                ratio = min(test_sharpe, train_sharpe) / max(test_sharpe, train_sharpe) if max(test_sharpe, train_sharpe) > 0 else 0
                score += 2.0 + ratio * 3.0  # 2-5 points based on consistency
            elif test_sharpe > 0:
                # Test positive but train negative — edge emerged recently
                score += 1.0

        return min(40.0, score)

    # ─── 2. SIGNAL QUALITY (max 25 points) ──────────────────────────────
    def _score_signal_quality(self, signal: TradingSignal, strategy: Strategy) -> float:
        """
        Score the quality of the current signal.

        Breakdown:
        - Signal confidence (max 12): How strong is the technical trigger?
        - Risk management (max 8): SL/TP defined, reasonable R:R ratio
        - Indicator alignment (max 5): Multiple confirming conditions
        """
        score = 0.0

        # --- Signal confidence (max 12) ---
        if hasattr(signal, 'confidence') and signal.confidence:
            confidence = signal.confidence

            # Regime-adjust: low-vol signals are naturally weaker but still valid
            regime_multiplier = 1.0
            if self.market_analyzer:
                try:
                    sub_regime, _, _, _ = self.market_analyzer.detect_sub_regime()
                    regime_name = sub_regime.value if hasattr(sub_regime, 'value') else str(sub_regime)
                    if 'low_vol' in regime_name.lower():
                        regime_multiplier = 1.4
                    elif 'high_vol' in regime_name.lower():
                        regime_multiplier = 0.9
                except Exception:
                    pass

            adjusted = min(1.0, confidence * regime_multiplier)
            score += adjusted * 12.0

        # --- Risk management (max 8) ---
        has_sl = strategy.risk_params and strategy.risk_params.stop_loss_pct
        has_tp = strategy.risk_params and strategy.risk_params.take_profit_pct

        if has_sl and has_tp:
            score += 5.0
            # Bonus for good R:R ratio
            sl = strategy.risk_params.stop_loss_pct
            tp = strategy.risk_params.take_profit_pct
            if sl > 0:
                rr = tp / sl
                if rr >= 2.0:
                    score += 3.0  # Excellent R:R
                elif rr >= 1.5:
                    score += 2.0
                elif rr >= 1.0:
                    score += 1.0
        elif has_sl:
            score += 3.0  # At least has downside protection
        elif has_tp:
            score += 1.0

        # --- Indicator alignment (max 5) ---
        entry_conditions = strategy.rules.get('entry_conditions', []) if strategy.rules else []
        if len(entry_conditions) >= 3:
            score += 5.0
        elif len(entry_conditions) == 2:
            score += 3.0
        elif len(entry_conditions) == 1:
            score += 1.5

        return min(25.0, score)

    # ─── 3. REGIME FIT (max 20 points) ──────────────────────────────────
    def _score_regime_fit(self, strategy: Strategy) -> float:
        """
        Score how well the strategy type fits the current market regime.

        Key insight: a strategy that passed walk-forward IN the current regime
        already has regime validation baked in. This score is a secondary
        confirmation, not a veto.

        Strong match: 20, Neutral: 12, Weak: 5 (never 0 — WF already validated)
        """
        if not self.market_analyzer:
            return 10.0  # Neutral when we can't detect regime

        try:
            # Crypto strategies use BTC/ETH regime
            is_crypto = False
            if strategy.metadata:
                is_crypto = strategy.metadata.get('crypto_optimized', False)
            if not is_crypto and strategy.symbols:
                try:
                    from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
                    is_crypto = strategy.symbols[0].upper() in set(DEMO_ALLOWED_CRYPTO)
                except ImportError:
                    pass

            if is_crypto:
                sub_regime, _, _, _ = self.market_analyzer.detect_sub_regime(symbols=['BTC', 'ETH'])
            else:
                sub_regime, _, _, _ = self.market_analyzer.detect_sub_regime()

            regime_key = sub_regime.value.lower().replace(' ', '_') if hasattr(sub_regime, 'value') else 'unknown'

            # Detect strategy type
            strategy_type = self._detect_strategy_type(strategy)

            # Alignment map — which strategy types thrive in which regimes
            alignment = {
                'trending_up':          {'strong': ['trend_following', 'momentum', 'breakout'], 'neutral': ['mean_reversion']},
                'trending_up_strong':   {'strong': ['trend_following', 'momentum', 'breakout'], 'neutral': []},
                'trending_up_weak':     {'strong': ['trend_following', 'momentum'], 'neutral': ['breakout', 'mean_reversion']},
                'trending_down':        {'strong': ['mean_reversion', 'momentum'], 'neutral': ['trend_following', 'volatility']},
                'trending_down_strong': {'strong': ['mean_reversion', 'momentum'], 'neutral': ['volatility']},
                'trending_down_weak':   {'strong': ['mean_reversion', 'momentum'], 'neutral': ['trend_following', 'volatility', 'breakout']},
                'ranging':              {'strong': ['mean_reversion'], 'neutral': ['volatility', 'momentum']},
                'ranging_low_vol':      {'strong': ['mean_reversion', 'trend_following'], 'neutral': ['breakout', 'momentum']},
                'ranging_high_vol':     {'strong': ['mean_reversion', 'volatility'], 'neutral': ['momentum']},
                'high_volatility':      {'strong': ['mean_reversion', 'volatility'], 'neutral': ['momentum']},
                'low_volatility':       {'strong': ['trend_following', 'breakout'], 'neutral': ['momentum', 'mean_reversion']},
            }

            # Find best matching regime key (longest prefix match)
            regime_map = alignment.get(regime_key, {})
            if not regime_map:
                best_key, best_len = None, 0
                for key in alignment:
                    if regime_key.startswith(key) and len(key) > best_len:
                        best_key, best_len = key, len(key)
                if best_key:
                    regime_map = alignment[best_key]

            if strategy_type in regime_map.get('strong', []):
                return 20.0
            elif strategy_type in regime_map.get('neutral', []):
                return 12.0
            else:
                # "Weak" match — but WF already validated, so give 5 not 0
                return 5.0

        except Exception as e:
            logger.warning(f"Error scoring regime fit: {e}")
            return 10.0

    # ─── 4. ASSET TRADABILITY (max 15 points) ───────────────────────────
    def _score_asset_tradability(
        self,
        symbol: str,
        fundamental_report: Optional[FundamentalFilterReport]
    ) -> float:
        """
        Score how tradable the asset is — liquidity, spread cost, data quality.

        This replaces the old "fundamental quality" score. The key insight:
        fundamental analysis is irrelevant for walk-forward validated DSL strategies.
        What matters is whether we can EXECUTE the trade efficiently.

        - Tier 1 (15 pts): Ultra-liquid (SPY, QQQ, AAPL, BTC, ETH, major forex)
        - Tier 2 (13 pts): Very liquid (large-cap stocks, major ETFs, SOL, XRP)
        - Tier 3 (11 pts): Liquid (mid-cap stocks, sector ETFs, indices, commodities)
        - Tier 4 (9 pts): Moderate (small-cap, minor crypto, minor ETFs)
        - Tier 5 (7 pts): Thin (NEAR, niche symbols)

        Bonus: +2 pts if fundamental report passed (confirms quality for stocks)
        """
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES,
            DEMO_ALLOWED_ETFS,
        )
        sym = symbol.upper().split(':')[0]

        # --- Tier 1: Ultra-liquid (tightest spreads, deepest books) ---
        TIER_1 = {'SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
                   'BTC', 'ETH', 'EURUSD', 'GBPUSD', 'USDJPY', 'SPX500', 'NSDQ100'}
        if sym in TIER_1:
            score = 15.0
        # --- Tier 2: Very liquid ---
        elif sym in {'IWM', 'DIA', 'VTI', 'VOO', 'GLD', 'XLE', 'XLF', 'XLK',
                      'SOL', 'XRP', 'JPM', 'V', 'MA', 'NFLX', 'AMD', 'AVGO',
                      'DJ30', 'GER40', 'UK100', 'GOLD', 'OIL'}:
            score = 13.0
        # --- Tier 3: Liquid ---
        elif sym in set(DEMO_ALLOWED_ETFS):
            score = 12.0  # All ETFs are at least tier 3 — they're exchange-traded, liquid
        elif sym in set(DEMO_ALLOWED_FOREX):
            score = 13.0
        elif sym in set(DEMO_ALLOWED_INDICES):
            score = 12.0
        elif sym in set(DEMO_ALLOWED_COMMODITIES):
            score = 11.0
        elif sym in set(DEMO_ALLOWED_CRYPTO):
            # Crypto tiers by market cap
            CRYPTO_SCORES = {
                'BTC': 15.0, 'ETH': 15.0,
                'SOL': 13.0, 'XRP': 13.0, 'ADA': 11.0,
                'AVAX': 10.0, 'DOT': 10.0, 'LINK': 10.0, 'LTC': 11.0, 'BCH': 11.0,
                'NEAR': 8.0,
            }
            score = CRYPTO_SCORES.get(sym, 9.0)
        else:
            # Stocks — base 10, most are liquid enough
            score = 10.0

        # Fundamental quality bonus for stocks (max +2)
        # This is a BONUS, not a requirement. Walk-forward already validated the strategy.
        if fundamental_report and fundamental_report.fundamental_data:
            if fundamental_report.checks_total > 0:
                pass_ratio = fundamental_report.checks_passed / fundamental_report.checks_total
                if pass_ratio >= 0.6:
                    score += 2.0  # Strong fundamentals = slight edge
                elif pass_ratio >= 0.4:
                    score += 1.0

        return min(15.0, score)

    # ─── 5. FUNDAMENTAL QUALITY — DIRECTION-AWARE (±15 points) ──────────
    def _score_fundamental_quality(
        self,
        signal: TradingSignal,
        fundamental_report: Optional[FundamentalFilterReport] = None
    ) -> float:
        """
        Direction-aware fundamental quality scoring.

        LONG signals: strong fundamentals → up to +15, weak → down to -15
        SHORT signals: weak fundamentals → up to +15, strong → down to -15

        This is the key insight: don't short quality companies, don't buy garbage.
        A stock with earnings beats + revenue growth + insider buying is a great
        long but a terrible short. Conversely, earnings misses + revenue decline +
        insider selling = great short candidate.

        Only applies to stocks. Forex/crypto/commodities/indices/ETFs return 0.

        Signals used (each contributes ±3 points):
        - Earnings surprise (beat vs miss)
        - Revenue growth (growing vs declining)
        - Insider net buying (buying vs selling)
        - ROE quality (high vs low)
        - Share dilution (buyback vs dilution)
        """
        # Only applies to stocks
        sym = signal.symbol.upper().split(':')[0]
        try:
            from src.core.tradeable_instruments import (
                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES,
                DEMO_ALLOWED_ETFS,
            )
            non_stock = (
                set(DEMO_ALLOWED_CRYPTO) | set(DEMO_ALLOWED_FOREX) |
                set(DEMO_ALLOWED_INDICES) | set(DEMO_ALLOWED_COMMODITIES) |
                set(DEMO_ALLOWED_ETFS)
            )
            if sym in non_stock:
                return 0.0
        except ImportError:
            pass

        if not fundamental_report or not fundamental_report.fundamental_data:
            return 0.0

        fd = fundamental_report.fundamental_data
        is_long = signal.action in (SignalAction.ENTER_LONG,)

        # Raw fundamental quality score: positive = strong, negative = weak
        raw_score = 0.0

        # 1. Earnings surprise (±3)
        if fd.earnings_surprise is not None:
            if fd.earnings_surprise >= 0.05:
                raw_score += 3.0   # Beat by 5%+
            elif fd.earnings_surprise >= 0.01:
                raw_score += 1.5   # Slight beat
            elif fd.earnings_surprise <= -0.05:
                raw_score -= 3.0   # Missed by 5%+
            elif fd.earnings_surprise <= -0.01:
                raw_score -= 1.5   # Slight miss

        # 2. Revenue growth (±3)
        if fd.revenue_growth is not None:
            if fd.revenue_growth >= 0.10:
                raw_score += 3.0   # 10%+ growth
            elif fd.revenue_growth >= 0.03:
                raw_score += 1.5   # Moderate growth
            elif fd.revenue_growth <= -0.05:
                raw_score -= 3.0   # Revenue declining
            elif fd.revenue_growth <= -0.01:
                raw_score -= 1.5   # Slight decline

        # 3. Insider net buying (±3)
        if fd.insider_net_buying is not None:
            if fd.insider_net_buying >= 3:
                raw_score += 3.0   # Strong insider buying
            elif fd.insider_net_buying >= 1:
                raw_score += 1.5   # Some insider buying
            elif fd.insider_net_buying <= -3:
                raw_score -= 3.0   # Heavy insider selling
            elif fd.insider_net_buying <= -1:
                raw_score -= 1.5   # Some insider selling

        # 4. ROE quality (±3)
        if fd.roe is not None:
            if fd.roe >= 0.20:
                raw_score += 3.0   # Excellent ROE
            elif fd.roe >= 0.12:
                raw_score += 1.5   # Good ROE
            elif fd.roe <= 0.0:
                raw_score -= 3.0   # Negative ROE (losing money)
            elif fd.roe <= 0.05:
                raw_score -= 1.5   # Poor ROE

        # 5. Share dilution vs buyback (±3)
        if fd.shares_change_percent is not None:
            if fd.shares_change_percent <= -0.02:
                raw_score += 3.0   # Active buyback (2%+ reduction)
            elif fd.shares_change_percent <= -0.005:
                raw_score += 1.5   # Slight buyback
            elif fd.shares_change_percent >= 0.05:
                raw_score -= 3.0   # Heavy dilution (5%+)
            elif fd.shares_change_percent >= 0.02:
                raw_score -= 1.5   # Moderate dilution

        # Direction-aware: flip the sign for shorts
        # LONG + strong fundamentals (raw_score > 0) → positive conviction
        # SHORT + weak fundamentals (raw_score < 0) → positive conviction (good short)
        # LONG + weak fundamentals (raw_score < 0) → negative conviction (don't buy garbage)
        # SHORT + strong fundamentals (raw_score > 0) → negative conviction (don't short quality)
        if is_long:
            direction_score = raw_score
        else:
            direction_score = -raw_score

        # Clamp to ±15
        direction_score = max(-15.0, min(15.0, direction_score))

        if direction_score != 0:
            direction_label = "LONG" if is_long else "SHORT"
            quality_label = "strong" if raw_score > 0 else "weak" if raw_score < 0 else "neutral"
            logger.info(
                f"Fundamental quality for {sym} ({direction_label}): "
                f"raw={raw_score:+.1f} ({quality_label}), "
                f"direction_adjusted={direction_score:+.1f}"
            )

        return direction_score

    def _get_fundamental_quality_details(
        self,
        signal: TradingSignal,
        fundamental_report: Optional[FundamentalFilterReport] = None
    ) -> Dict[str, Any]:
        """Get fundamental quality details for breakdown logging."""
        if not fundamental_report or not fundamental_report.fundamental_data:
            return {'applicable': False, 'reason': 'no_data'}

        fd = fundamental_report.fundamental_data
        return {
            'applicable': True,
            'direction': signal.action.value,
            'earnings_surprise': fd.earnings_surprise,
            'revenue_growth': fd.revenue_growth,
            'insider_net_buying': fd.insider_net_buying,
            'roe': fd.roe,
            'shares_change_pct': fd.shares_change_percent,
        }

    # ─── FOREX CARRY BIAS ───────────────────────────────────────────────
    def _score_carry_bias(self, signal: TradingSignal) -> float:
        """
        Apply carry bias adjustment for forex pairs.

        If the signal direction aligns with positive carry (long the higher-yielding
        currency), add up to +5 points. If it fights carry, subtract up to -5 points.
        Non-forex signals return 0.

        The magnitude scales with the rate differential:
        - |diff| >= 3%: full ±5 points
        - |diff| >= 1%: ±3 points
        - |diff| < 1%: ±1 point
        """
        if not self.market_analyzer:
            return 0.0

        sym = signal.symbol.upper().split(':')[0]

        # Only applies to forex pairs
        from src.core.tradeable_instruments import DEMO_ALLOWED_FOREX
        if sym not in set(DEMO_ALLOWED_FOREX):
            return 0.0

        try:
            carry_data = self.market_analyzer.get_carry_rates()
            carry_diff = carry_data.get('carry', {}).get(sym)

            if carry_diff is None:
                return 0.0

            # Determine signal direction
            direction = getattr(signal, 'direction', None)
            if direction is None:
                direction = getattr(signal, 'side', None)
            if direction is None:
                return 0.0

            is_long = str(direction).lower() in ('long', 'buy')

            # Scale adjustment by magnitude of rate differential
            abs_diff = abs(carry_diff)
            if abs_diff >= 3.0:
                magnitude = 5.0
            elif abs_diff >= 1.0:
                magnitude = 3.0
            else:
                magnitude = 1.0

            # Positive carry_diff means base currency has higher rate
            # Long = buying base currency = earning carry if diff > 0
            if is_long and carry_diff > 0:
                return magnitude   # With carry
            elif is_long and carry_diff < 0:
                return -magnitude  # Against carry
            elif not is_long and carry_diff < 0:
                return magnitude   # Short + negative carry = with carry
            elif not is_long and carry_diff > 0:
                return -magnitude  # Short + positive carry = against carry

            return 0.0

        except Exception as e:
            logger.debug(f"Could not compute carry bias for {sym}: {e}")
            return 0.0

    def _get_carry_details(self, signal: TradingSignal) -> Dict[str, Any]:
        """Get carry bias details for breakdown logging."""
        sym = signal.symbol.upper().split(':')[0]
        from src.core.tradeable_instruments import DEMO_ALLOWED_FOREX
        if sym not in set(DEMO_ALLOWED_FOREX):
            return {'applicable': False}

        if not self.market_analyzer:
            return {'applicable': True, 'status': 'no_analyzer'}

        try:
            carry_data = self.market_analyzer.get_carry_rates()
            carry_diff = carry_data.get('carry', {}).get(sym)
            rates = carry_data.get('rates', {})

            # Get currencies for this pair
            pair_map = {
                'EURUSD': ('EUR', 'USD'), 'GBPUSD': ('GBP', 'USD'),
                'USDJPY': ('USD', 'JPY'), 'AUDUSD': ('AUD', 'USD'),
                'USDCAD': ('USD', 'CAD'), 'USDCHF': ('USD', 'CHF'),
            }
            base_ccy, quote_ccy = pair_map.get(sym, (None, None))

            return {
                'applicable': True,
                'pair': sym,
                'carry_differential': carry_diff,
                'base_rate': rates.get(base_ccy) if base_ccy else None,
                'quote_rate': rates.get(quote_ccy) if quote_ccy else None,
                'direction': str(getattr(signal, 'direction', getattr(signal, 'side', None))),
            }
        except Exception as e:
            return {'applicable': True, 'error': str(e)}

    def _score_crypto_cycle(self, signal: TradingSignal) -> float:
        """
        Apply crypto halving cycle adjustment for BTC/ETH signals.

        Boosts conviction during favorable cycle phases (accumulation, early bull),
        reduces it during unfavorable phases (distribution, early bear).
        Non-crypto signals return 0.

        Returns ±5 points max.
        """
        if not self.market_analyzer:
            return 0.0

        sym = signal.symbol.upper().split(':')[0]
        from src.core.tradeable_instruments import DEMO_ALLOWED_CRYPTO
        if sym not in set(DEMO_ALLOWED_CRYPTO):
            return 0.0

        try:
            cycle = self.market_analyzer.get_crypto_cycle_phase()
            recommendation = cycle.get('recommendation', 'hold')

            if recommendation == 'accumulate':
                return 5.0
            elif recommendation == 'hold':
                return 2.0
            elif recommendation == 'reduce':
                return -3.0
            elif recommendation == 'avoid':
                return -5.0
            return 0.0

        except Exception as e:
            logger.debug(f"Could not compute crypto cycle score: {e}")
            return 0.0

    # ─── STRATEGY TYPE DETECTION ────────────────────────────────────────
    def _detect_strategy_type(self, strategy: Strategy) -> str:
        """Detect strategy type from metadata or name."""
        if strategy.metadata:
            st = strategy.metadata.get('template_type') or strategy.metadata.get('strategy_type')
            if st:
                return st

        if hasattr(strategy, 'name') and strategy.name:
            name = strategy.name.lower()
            if any(kw in name for kw in ['mean reversion', 'rsi dip', 'bb mean', 'sma reversion',
                    'keltner', 'stochastic recovery', 'crash recovery', 'volatility fade',
                    'pullback', 'oversold', 'reversion', 'capitulation', 'dip buy',
                    'downtrend oversold', 'deep dip', 'proximity', 'bb middle',
                    'lower bounce', 'snap back', 'downtrend bounce']):
                return 'mean_reversion'
            elif any(kw in name for kw in ['trend', 'ema crossover', 'ema ribbon',
                    'momentum burst', 'sma trend', 'dual ma', 'macd divergence']):
                return 'trend_following'
            elif any(kw in name for kw in ['breakout', 'squeeze', 'volume spike',
                    'opening range', 'low vol breakout', 'downtrend breakout',
                    'volume climax']):
                return 'breakout'
            elif any(kw in name for kw in ['momentum', 'macd', 'stoch momentum']):
                return 'momentum'
            elif any(kw in name for kw in ['volatility', 'vix', 'atr']):
                return 'volatility'
            elif any(kw in name for kw in ['short', 'overbought', 'bearish',
                    'lower high', 'breakdown']):
                return 'mean_reversion'

        return 'unknown'

    # ─── DETAIL GETTERS (for breakdown logging) ─────────────────────────

    def _get_wf_details(self, strategy: Strategy) -> Dict[str, Any]:
        meta = strategy.metadata or {}
        perf = strategy.backtest_results
        return {
            'wf_test_sharpe': meta.get('wf_test_sharpe'),
            'wf_train_sharpe': meta.get('wf_train_sharpe'),
            'walk_forward_validated': meta.get('walk_forward_validated', False),
            'total_trades': perf.total_trades if perf and hasattr(perf, 'total_trades') else None,
            'win_rate': perf.win_rate if perf and hasattr(perf, 'win_rate') else None,
        }

    def _get_signal_details(self, signal: TradingSignal, strategy: Strategy) -> Dict[str, Any]:
        entry_conditions = strategy.rules.get('entry_conditions', []) if strategy.rules else []
        return {
            'entry_conditions_count': len(entry_conditions),
            'has_stop_loss': bool(strategy.risk_params and strategy.risk_params.stop_loss_pct),
            'has_profit_target': bool(strategy.risk_params and strategy.risk_params.take_profit_pct),
            'signal_confidence': getattr(signal, 'confidence', None),
        }

    # Legacy alias for backward compatibility
    def _get_signal_strength_details(self, signal: TradingSignal, strategy: Strategy) -> Dict[str, Any]:
        return self._get_signal_details(signal, strategy)

    def _get_regime_details(self, strategy: Strategy) -> Dict[str, Any]:
        if not self.market_analyzer:
            return {'status': 'no_analyzer'}
        try:
            market_context = self.market_analyzer.get_market_context()
            return {
                'current_regime': market_context.get('regime', 'unknown'),
                'strategy_type': self._detect_strategy_type(strategy),
                'vix_level': market_context.get('vix', None),
            }
        except Exception as e:
            return {'error': str(e)}

    def _get_asset_details(self, symbol: str) -> Dict[str, Any]:
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES,
            DEMO_ALLOWED_ETFS,
        )
        sym = symbol.upper().split(':')[0]
        if sym in set(DEMO_ALLOWED_CRYPTO):
            asset_class = 'crypto'
        elif sym in set(DEMO_ALLOWED_ETFS):
            asset_class = 'etf'
        elif sym in set(DEMO_ALLOWED_FOREX):
            asset_class = 'forex'
        elif sym in set(DEMO_ALLOWED_INDICES):
            asset_class = 'index'
        elif sym in set(DEMO_ALLOWED_COMMODITIES):
            asset_class = 'commodity'
        else:
            asset_class = 'stock'
        return {'symbol': sym, 'asset_class': asset_class}

    # Legacy alias
    def _get_fundamental_details(self, fundamental_report: Optional[FundamentalFilterReport]) -> Dict[str, Any]:
        if not fundamental_report:
            return {'status': 'no_data'}
        return {
            'checks_passed': fundamental_report.checks_passed,
            'checks_total': fundamental_report.checks_total,
            'passed': fundamental_report.passed,
            'results': [
                {'check': r.check_name, 'passed': r.passed, 'value': r.value}
                for r in fundamental_report.results
            ],
        }

    # ─── NEWS SENTIMENT (±8 points) ─────────────────────────────────────
    def _score_news_sentiment(self, signal: TradingSignal) -> float:
        """
        Direction-aware news sentiment adjustment from Marketaux.

        LONG + bullish news  → up to +8
        LONG + bearish news  → down to -8
        SHORT + bearish news → up to +8 (bad news = good short)
        SHORT + bullish news → down to -8 (don't short on good news)

        Returns 0.0 if no data — never blocks a trade.
        Only applies to stocks. ETFs/forex/crypto/indices/commodities return 0.
        """
        sym = signal.symbol.upper().split(':')[0]

        # Only stocks have meaningful per-ticker news sentiment
        try:
            from src.core.tradeable_instruments import (
                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                DEMO_ALLOWED_INDICES, DEMO_ALLOWED_COMMODITIES,
                DEMO_ALLOWED_ETFS,
            )
            non_stock = (
                set(DEMO_ALLOWED_CRYPTO) | set(DEMO_ALLOWED_FOREX) |
                set(DEMO_ALLOWED_INDICES) | set(DEMO_ALLOWED_COMMODITIES) |
                set(DEMO_ALLOWED_ETFS)
            )
            if sym in non_stock:
                return 0.0
        except ImportError:
            pass

        try:
            from src.data.news_sentiment_provider import get_news_sentiment_provider
            provider = get_news_sentiment_provider()
            if provider is None:
                return 0.0

            # Pure DB lookup — no API call at signal time
            raw_score = provider.get_sentiment(sym)  # -1.0 to +1.0, 0.0 = no data

            if raw_score == 0.0:
                # Queue for background fetch on next sync cycle
                return 0.0

            is_long = signal.action in (SignalAction.ENTER_LONG,)

            # Direction-aware: flip for shorts
            direction_score = raw_score if is_long else -raw_score

            # Scale to ±8 points — but dampen for small article counts.
            # Marketaux free tier returns max 3 articles. With 3 articles,
            # a single bad-news day gives -1.0 for a fundamentally strong company.
            # Dampen the impact proportionally to sample size:
            # 1-3 articles → max ±3 pts (unreliable sample)
            # 4-6 articles → max ±5 pts (moderate confidence)
            # 7+ articles  → max ±8 pts (full weight)
            try:
                article_count = provider.get_article_count(sym)
            except Exception:
                article_count = 3  # assume small sample if unknown

            if article_count <= 3:
                max_impact = 3.0
            elif article_count <= 6:
                max_impact = 5.0
            else:
                max_impact = 8.0

            adjusted = direction_score * max_impact
            adjusted = max(-max_impact, min(max_impact, adjusted))

            if abs(adjusted) >= 1.0:
                label = "bullish" if raw_score > 0 else "bearish"
                direction = "LONG" if is_long else "SHORT"
                logger.info(
                    f"[NewsSentiment] {sym} ({direction}): raw={raw_score:+.3f} ({label}) "
                    f"→ conviction {adjusted:+.1f}"
                )

            return adjusted

        except Exception as e:
            logger.debug(f"[NewsSentiment] Error scoring {sym}: {e}")
            return 0.0

    # ─── FACTOR EXPOSURE (±6 points) ────────────────────────────────────
    def _score_factor_exposure(self, signal: TradingSignal, strategy: Strategy) -> float:
        """
        Regime-aware factor tilt adjustment.

        In ranging/low-vol regimes: favor low-beta, high-quality (defensive factors).
        In trending-up regimes: favor high-momentum, high-beta (offensive factors).

        Uses FMP fundamental data: beta (market factor), pe_ratio (value proxy),
        revenue_growth (momentum proxy). Only applies to equity LONGs/SHORTs.

        Returns ±6 points.
        """
        try:
            from src.core.tradeable_instruments import (
                DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_FOREX,
                DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_INDICES, DEMO_ALLOWED_ETFS,
            )
            sym = signal.symbol.upper().split(':')[0]
            non_equity = (set(DEMO_ALLOWED_CRYPTO) | set(DEMO_ALLOWED_FOREX)
                         | set(DEMO_ALLOWED_COMMODITIES) | set(DEMO_ALLOWED_INDICES)
                         | set(DEMO_ALLOWED_ETFS))
            if sym in non_equity:
                return 0.0

            # Get current regime
            current_regime = 'unknown'
            if self.market_analyzer:
                try:
                    sub_regime, _, _, _ = self.market_analyzer.detect_sub_regime()
                    current_regime = sub_regime.value.lower() if sub_regime else 'unknown'
                except Exception:
                    pass

            # Get fundamental data for factor proxies
            from src.data.fundamental_data_provider import get_fundamental_data_provider
            provider = get_fundamental_data_provider()
            if not provider:
                return 0.0

            fd = provider.get_fundamental_data(sym)
            if not fd:
                return 0.0

            beta = getattr(fd, 'beta', None)
            pe_ratio = getattr(fd, 'pe_ratio', None)
            revenue_growth = getattr(fd, 'revenue_growth', None)

            is_long = signal.action in (SignalAction.ENTER_LONG,)
            adjustment = 0.0

            if current_regime in ('ranging_low_vol', 'ranging', 'ranging_high_vol'):
                # Defensive regime: reward low-beta, penalize high-beta for longs
                if beta is not None:
                    if is_long:
                        if beta < 0.8:
                            adjustment += 3.0   # Low-beta long in ranging = defensive, good
                        elif beta > 1.5:
                            adjustment -= 3.0   # High-beta long in ranging = risky
                    else:
                        if beta > 1.5:
                            adjustment += 2.0   # High-beta short in ranging = good short candidate
                        elif beta < 0.8:
                            adjustment -= 2.0   # Shorting defensive stocks in ranging = poor

            elif current_regime in ('trending_up', 'trending_up_weak', 'trending_up_strong'):
                # Offensive regime: reward high-momentum, high-beta for longs
                if beta is not None and is_long:
                    if beta > 1.3:
                        adjustment += 3.0   # High-beta long in uptrend = amplified gains
                    elif beta < 0.7:
                        adjustment -= 2.0   # Low-beta long in uptrend = underperforms

                # Revenue growth momentum factor
                if revenue_growth is not None and is_long:
                    if revenue_growth > 0.15:
                        adjustment += 3.0   # Strong revenue growth in uptrend = momentum
                    elif revenue_growth < 0.0:
                        adjustment -= 2.0   # Declining revenue in uptrend = weak

            # Value factor: extremely high P/E is a risk in any regime
            if pe_ratio is not None and pe_ratio > 60 and is_long:
                adjustment -= 2.0   # Overvalued — higher drawdown risk

            return max(-6.0, min(6.0, adjustment))

        except Exception as e:
            logger.debug(f"Factor exposure scoring failed for {signal.symbol}: {e}")
            return 0.0

    def _log_conviction_score(self, signal: TradingSignal, strategy: Strategy, conviction: ConvictionScore) -> None:
        """Log conviction score to database."""
        try:
            from src.models.orm import ConvictionScoreLogORM
            from datetime import datetime

            log_entry = ConvictionScoreLogORM(
                strategy_id=strategy.id,
                symbol=signal.symbol,
                signal_type=signal.action.value,
                conviction_score=conviction.total_score,
                signal_strength_score=conviction.signal_strength_score,
                fundamental_quality_score=conviction.fundamental_score,
                regime_alignment_score=conviction.regime_alignment_score,
                passed_threshold=conviction.passes_threshold(self.min_conviction_score),
                threshold=self.min_conviction_score,
                timestamp=datetime.now()
            )

            session = self.database.get_session()
            try:
                session.add(log_entry)
                session.commit()
            finally:
                session.close()

        except Exception as e:
            logger.error(f"Failed to log conviction score: {e}")
