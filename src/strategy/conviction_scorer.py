"""
Conviction Scorer - Scores trading signals based on evidence of profitability.

Philosophy: The best predictor of a profitable trade is a strategy that has
already proven it works on out-of-sample data. Walk-forward validation IS
the evidence. Everything else is secondary.

Two distinct scoring paths based on strategy engine:

DSL (indicator-based) scoring dimensions (0-100):
1. Walk-forward edge (0-40): OOS Sharpe × trade-count confidence, win rate, consistency
2. Signal quality (0-25): Signal persistence (bars in condition) + R:R quality
3. Regime fit (0-20): Strategy type vs current market regime
4. Asset tradability (0-15): Liquidity, spread cost, data quality
   Theoretical max DSL = 40+25+20+15+5+5+1 = 111 (no fundamentals, no factor exposure)

Alpha Edge (fundamental-based) scoring dimensions (0-100):
1-4. Same as DSL
5. Fundamental quality direction (±15): earnings/revenue/insider/ROE/buyback
6. Factor exposure (±6): beta/PE/revenue-growth regime tilt
   Theoretical max AE = 40+25+20+15+15+5+5+1+6 = 132

Rationale for split: DSL strategies are validated on price/indicator data.
Adding fundamental overlays creates mixed signals — a quality company can still
have a bad technical entry, and a weak company can still have a valid breakout.
Alpha Edge strategies ARE the fundamental signal; conviction should amplify it.

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
        """Check if score passes threshold. Uses 0.05 epsilon for float rounding."""
        return self.total_score >= threshold - 0.05


class ConvictionScorer:
    """
    Scores trading signals based on evidence of profitability.

    The core insight: these strategies already passed walk-forward validation.
    The conviction score should measure HOW STRONG that evidence is, not
    re-litigate whether the strategy is "good enough" with arbitrary checks.

    Two paths:
    - DSL strategies: pure quantitative evidence (WF edge, signal persistence, regime, liquidity)
    - Alpha Edge strategies: same base + fundamental quality + factor exposure
    """

    # Theoretical max raw scores per path (used for normalization)
    # DSL:  WF(40) + Signal(25) + Regime(20) + Asset(15) + Carry(5) + Crypto(5) + News(1) = 111
    # AE:   DSL(111) + Fundamental(15) + Factor(6) = 132
    _THEORETICAL_MAX_DSL = 111.0
    _THEORETICAL_MAX_AE  = 132.0

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
        self.min_conviction_score = alpha_edge_config.get('min_conviction_score', 65)

        logger.info(f"ConvictionScorer initialized - Min score: {self.min_conviction_score}")

    def score_signal(
        self,
        signal: TradingSignal,
        strategy: Strategy,
        fundamental_report: Optional[FundamentalFilterReport] = None
    ) -> ConvictionScore:
        """Score a trading signal based on evidence of profitability.

        Routes through two distinct paths:
        - DSL strategies: quantitative evidence only (no fundamentals, no factor exposure)
        - Alpha Edge strategies: quantitative + fundamental + factor exposure

        The split is intentional. DSL edge lives in the price indicators; adding
        fundamental overlays introduces noise (a quality company can still have a
        bad technical entry). Alpha Edge edge IS the fundamental signal.
        """
        is_alpha_edge = (
            hasattr(strategy, 'metadata') and
            isinstance(strategy.metadata, dict) and
            strategy.metadata.get('strategy_category') == 'alpha_edge'
        )

        # ── Components shared by both paths ──────────────────────────────

        # 1. Walk-forward edge (max 40) — the strongest predictor
        wf_score = self._score_walkforward_edge(strategy)

        # 2. Signal quality (max 25)
        #    DSL:  signal persistence (bars in condition) + R:R quality
        #    AE:   confidence-based (genuine quality measure) + R:R quality
        signal_score = self._score_signal_quality(signal, strategy)

        # 3. Regime fit (max 20) — strategy type vs current market
        regime_score = self._score_regime_fit(strategy)

        # 4. Asset tradability (max 15) — liquidity, spread, data quality
        asset_score = self._score_asset_tradability(signal.symbol, fundamental_report)

        total_score = wf_score + signal_score + regime_score + asset_score

        # Carry bias (±5) — forex only
        carry_adjustment = self._score_carry_bias(signal)
        total_score += carry_adjustment

        # Crypto halving cycle (±5) — crypto only
        crypto_cycle_adjustment = self._score_crypto_cycle(signal)
        total_score += crypto_cycle_adjustment

        # News sentiment (±1) — stocks only, tiebreaker
        news_sentiment_adj = self._score_news_sentiment(signal)
        total_score += news_sentiment_adj

        # ── Alpha Edge only: fundamental + factor ────────────────────────
        fundamental_quality_adj = 0.0
        factor_adj = 0.0

        if is_alpha_edge:
            # Fundamental quality direction (±15): earnings/revenue/insider/ROE/buyback
            # LONG + strong fundamentals → bonus; SHORT + weak fundamentals → bonus
            fundamental_quality_adj = self._score_fundamental_quality(signal, fundamental_report)
            total_score += fundamental_quality_adj

            # Factor exposure (±6): beta/PE/revenue-growth regime tilt
            factor_adj = self._score_factor_exposure(signal, strategy)
            total_score += factor_adj

        # ── Normalize to 0-100 ───────────────────────────────────────────
        # Different theoretical maxima per path so the threshold means the same
        # thing regardless of which engine generated the signal.
        # DSL max:  40+25+20+15+5+5+1 = 111
        # AE max:   40+25+20+15+15+5+5+1+6 = 132
        theoretical_max = self._THEORETICAL_MAX_AE if is_alpha_edge else self._THEORETICAL_MAX_DSL
        total_score = min(100.0, total_score * (100.0 / theoretical_max))

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
                'max': 1,
                'details': {'symbol': signal.symbol, 'raw_score': news_sentiment_adj / 1.0 if news_sentiment_adj != 0 else 0.0},
            },
            'factor_exposure': {
                'score': factor_adj,
                'max': 6,
                'details': {'symbol': signal.symbol},
            },
            'scoring_path': 'alpha_edge' if is_alpha_edge else 'dsl',
            'theoretical_max': theoretical_max,
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

        path_label = "AE" if is_alpha_edge else "DSL"
        logger.info(
            f"Conviction score [{path_label}] for {signal.symbol}: {total_score:.1f}/100 "
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
        - OOS Sharpe × trade-count confidence: 0-20 points
          Multiplicative: Sharpe 3.9 on 4 trades scores the same as Sharpe 1.5
          on 15 trades. High Sharpe on few trades is noise, not edge.
        - Win rate quality: 0-8 points (>60% is strong, >50% is acceptable)
        - Train/test consistency: 0-5 points (both positive = consistent edge)
        - WF degradation penalty: 0 to -7 points
          Extreme test-over-train outperformance (degradation < -100%) is a
          red flag for regime luck. The strategy object stores this as
          wf_performance_degradation (negative = test beat train).

        Total max: 20 + 8 + 5 + 7 (trade count additive bonus) = 40
        """
        meta = strategy.metadata or {}
        perf = strategy.backtest_results

        score = 0.0

        # --- OOS Sharpe × trade-count confidence (max 20) ---
        # Multiplicative: confidence = sqrt(min(trades, 15) / 15)
        # At 4 trades: 0.516x  |  At 8 trades: 0.730x  |  At 15+ trades: 1.0x
        # This prevents a Sharpe 3.9 on 4 trades from outscore Sharpe 2.5 on 20 trades.
        test_sharpe = meta.get('wf_test_sharpe', 0)
        if perf and hasattr(perf, 'sharpe_ratio'):
            test_sharpe = test_sharpe or perf.sharpe_ratio

        total_trades = 0
        if perf and hasattr(perf, 'total_trades'):
            total_trades = perf.total_trades or 0

        trade_confidence = min(1.0, math.sqrt(max(0, total_trades) / 15.0)) if total_trades > 0 else 0.0

        if test_sharpe and not (math.isinf(test_sharpe) or math.isnan(test_sharpe)):
            # Logarithmic scaling: Sharpe 0.5→8, 1.0→12, 2.0→17, 3.0→19, 5.0→20
            if test_sharpe > 0:
                sharpe_pts = min(20.0, 8.0 + 6.0 * math.log(1 + test_sharpe))
            else:
                sharpe_pts = max(0.0, 4.0 + test_sharpe * 4.0)
            # Apply trade-count confidence multiplier
            score += sharpe_pts * trade_confidence

        # --- Trade count additive bonus (max 7) ---
        # Separate from the multiplicative confidence above — rewards strategies
        # that have been tested on many trades regardless of Sharpe magnitude.
        if total_trades >= 15:
            score += 7.0
        elif total_trades >= 8:
            score += 5.0
        elif total_trades >= 4:
            score += 3.0
        elif total_trades >= 2:
            score += 1.0

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

        # --- Train/test consistency (max 5) ---
        train_sharpe = meta.get('wf_train_sharpe', 0)
        if train_sharpe and test_sharpe:
            both_positive = train_sharpe > 0 and test_sharpe > 0
            if both_positive:
                ratio = min(test_sharpe, train_sharpe) / max(test_sharpe, train_sharpe) if max(test_sharpe, train_sharpe) > 0 else 0
                score += 2.0 + ratio * 3.0  # 2-5 points based on consistency
            elif test_sharpe > 0:
                score += 1.0  # Test positive but train negative — edge emerged recently

        # --- WF degradation penalty (0 to -7) ---
        # wf_performance_degradation is stored as a percentage, e.g. -371 means
        # test Sharpe was 371% higher than train Sharpe — extreme regime luck.
        # Penalty only fires when degradation is severe (< -100%) AND test_sharpe
        # is high (otherwise the strategy already scored low on Sharpe).
        # This catches the FDX pattern: WF 3.9 on 4 trades, train 0.62 → test 3.9.
        degradation = meta.get('wf_performance_degradation')
        if degradation is not None and test_sharpe and test_sharpe > 0:
            try:
                deg = float(degradation)
                if deg < -200:
                    score -= 7.0  # Extreme: test Sharpe 3x+ above train
                elif deg < -100:
                    score -= 4.0  # Significant: test Sharpe 2x+ above train
                elif deg < -50:
                    score -= 2.0  # Moderate: test Sharpe 1.5x above train
            except (TypeError, ValueError):
                pass

        return min(40.0, max(0.0, score))

    # ─── 2. SIGNAL QUALITY (max 25 points) ──────────────────────────────
    def _score_signal_quality(self, signal: TradingSignal, strategy: Strategy) -> float:
        """
        Score the quality of the current signal.

        Two paths based on strategy engine:

        DSL path (indicator-based):
        - Signal persistence (0-15): how many consecutive bars have entry conditions
          been true? Computed by strategy_engine and stored in signal.metadata.
          For trend-following: more bars = stronger trend confirmation.
          For mean-reversion: 1-3 bars = fresh oversold entry (best); 6+ = stuck.
          This replaces the old confidence sub-component which was near-constant
          (DSL confidence is a parser artifact, not a quality measure).
        - R:R quality (0-10): stop-loss and take-profit ratio. Weighted higher
          than before since it's the only sub-component with real variance.

        Alpha Edge path (fundamental-based):
        - Signal confidence (0-15): genuine quality measure from the fundamental
          scoring pipeline (analyst revision count, earnings surprise magnitude, etc.)
        - R:R quality (0-10): same as DSL.

        Max: 25 points either path.
        """
        is_alpha_edge = (
            hasattr(strategy, 'metadata') and
            isinstance(strategy.metadata, dict) and
            strategy.metadata.get('strategy_category') == 'alpha_edge'
        )

        score = 0.0

        if is_alpha_edge:
            # ── Alpha Edge: confidence is a genuine quality measure ──────
            if hasattr(signal, 'confidence') and signal.confidence:
                score += min(1.0, signal.confidence) * 15.0
        else:
            # ── DSL: use signal persistence (bars in condition) ──────────
            # entry_persistence is stored by strategy_engine in signal.metadata.
            # It counts how many of the last 10 bars had the entry condition true.
            # Strategy type determines whether persistence is good or bad:
            #   Trend-following/breakout: more bars = stronger trend = higher score
            #   Mean-reversion: 1-3 bars = fresh oversold (best); 6+ = stuck (bad)
            persistence = 0
            strategy_type = self._detect_strategy_type(strategy)
            try:
                meta = getattr(signal, 'metadata', None) or {}
                persistence = int(meta.get('entry_persistence', 0))
            except (TypeError, ValueError):
                persistence = 0

            is_mean_reversion = 'mean_reversion' in strategy_type

            if is_mean_reversion:
                # Fresh oversold/overbought = best entry
                # 1 bar  → 12 pts (just fired, cleanest entry)
                # 2-3    → 15 pts (confirmed, still fresh)
                # 4-5    → 8 pts  (getting stale)
                # 6+     → 3 pts  (stuck — dangerous)
                if persistence <= 1:
                    score += 12.0
                elif persistence <= 3:
                    score += 15.0
                elif persistence <= 5:
                    score += 8.0
                else:
                    score += 3.0
            else:
                # Trend-following / breakout / momentum: persistence = confirmation
                # 1 bar  → 5 pts  (could be noise)
                # 2-3    → 9 pts  (trend establishing)
                # 4-6    → 12 pts (confirmed trend)
                # 7-8    → 14 pts (strong trend)
                # 9-10   → 15 pts (very strong trend)
                if persistence <= 1:
                    score += 5.0
                elif persistence <= 3:
                    score += 9.0
                elif persistence <= 6:
                    score += 12.0
                elif persistence <= 8:
                    score += 14.0
                else:
                    score += 15.0

            # Fallback: if persistence not available, use a neutral 8 pts
            # (same as old DSL baseline) so existing strategies aren't penalised
            # during the transition period before all signals carry the field.
            if persistence == 0 and not meta.get('entry_persistence'):
                score = 8.0

        # ── R:R quality (0-10) — both paths ─────────────────────────────
        # Weighted higher than before (was max 8, now max 10) since it's the
        # only sub-component with real variance across strategies.
        has_sl = strategy.risk_params and strategy.risk_params.stop_loss_pct
        has_tp = strategy.risk_params and strategy.risk_params.take_profit_pct

        if has_sl and has_tp:
            sl = strategy.risk_params.stop_loss_pct
            tp = strategy.risk_params.take_profit_pct
            if sl > 0:
                rr = tp / sl
                if rr >= 2.5:
                    score += 10.0  # Excellent R:R
                elif rr >= 2.0:
                    score += 8.0
                elif rr >= 1.5:
                    score += 5.0
                elif rr >= 1.0:
                    score += 2.0
                # R:R < 1.0: 0 pts (losing proposition even at 50% WR)
        elif has_sl:
            score += 3.0  # At least has downside protection

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

            # Detect strategy type and direction
            strategy_type = self._detect_strategy_type(strategy)
            direction = (strategy.metadata or {}).get('direction', 'long').lower() if strategy.metadata else 'long'

            # Direction-aware override: uptrend-specific SHORT strategies (exhaustion,
            # parabolic, BB squeeze, EMA rejection, MACD divergence, volume climax) are
            # mean_reversion or volatility typed but are the CORRECT tool in trending_up —
            # they're the hedge waiting for the correction. Give them a strong regime score.
            if direction == 'short' and 'trending_up' in regime_key:
                if strategy_type in ['mean_reversion', 'volatility', 'trend_following']:
                    return 20.0  # Uptrend exhaustion shorts are perfectly regime-aligned

            # Alignment map — which strategy types thrive in which regimes
            alignment = {
                'trending_up':          {'strong': ['trend_following', 'momentum', 'breakout'], 'neutral': ['mean_reversion']},
                'trending_up_strong':   {'strong': ['trend_following', 'momentum', 'breakout'], 'neutral': []},
                'trending_up_weak':     {'strong': ['trend_following', 'momentum', 'breakout'], 'neutral': ['mean_reversion']},
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
                score = 20.0
            elif strategy_type in regime_map.get('neutral', []):
                score = 12.0
            else:
                # "Weak" match — but WF already validated, so give 5 not 0
                score = 5.0

            # C2 (2026-05-01): Momentum Crash Circuit Breaker.
            # Steelman: Byun & Jeon (SSRN 2900073) documented momentum crashes during
            # market rebounds — 52-week-high momentum strategies get hit hardest when
            # oversold names rally off a drawdown. Combined with the general "raw
            # momentum is crowded" evidence from the 2025 H1 quant unwind, we want
            # to dial down momentum LONG conviction when the market has sold off
            # AND vol is spiking (rebound window). We don't veto — WF already
            # validated — we just reduce the regime component.
            #
            # Trigger: SPY 5-day return < -3% AND VIX 1-day change > +10%.
            # Target: momentum/trend_following/breakout LONG strategies.
            # Action: subtract 10 points from regime_fit (capped at floor=5 to
            # match the existing "weak match" floor).
            direction = (strategy.metadata or {}).get('direction', 'long').lower() if strategy.metadata else 'long'
            if direction == 'long' and strategy_type in ('momentum', 'trend_following', 'breakout'):
                try:
                    crash_signal = self._check_momentum_crash_regime()
                    if crash_signal:
                        reduction = 10.0
                        new_score = max(5.0, score - reduction)
                        if new_score < score:
                            logger.info(
                                f"C2 momentum crash circuit breaker fired for "
                                f"{strategy.name}: regime_fit {score:.1f} → {new_score:.1f} "
                                f"({crash_signal})"
                            )
                            score = new_score
                except Exception as _c2_err:
                    # Never block a valid score on circuit-breaker failure
                    logger.debug(f"C2 circuit breaker check failed: {_c2_err}")

            return score

        except Exception as e:
            logger.warning(f"Error scoring regime fit: {e}")
            return 10.0

    # ─── C2 HELPER: Momentum Crash Circuit Breaker ─────────────────────
    def _check_momentum_crash_regime(self) -> Optional[str]:
        """Detect the post-drawdown rebound window where raw momentum crashes.

        Returns a short reason string when triggered, None otherwise.

        Trigger conditions (BOTH must be true):
          1. SPY 5-day return < -3% (market has sold off)
          2. VIX 1-day change > +10% (fear spiking — rebound setup)

        Cached for 5 minutes to avoid repeated MarketData fetches within
        a signal-generation cycle. Fail-open — any error returns None
        (i.e. no circuit breaker fires).
        """
        import time as _t
        now = _t.time()
        cache = getattr(self, '_c2_crash_cache', None)
        if cache and (now - cache[0] < 300):  # 5min TTL
            return cache[1]

        try:
            from datetime import datetime, timedelta
            if not self.market_analyzer or not hasattr(self.market_analyzer, 'market_data'):
                return None

            md = self.market_analyzer.market_data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=10)

            # SPY 5-day return
            spy_bars = md.get_historical_data(
                symbol="SPY",
                start=start_date,
                end=end_date,
                interval="1d",
                prefer_yahoo=True,
            )
            if not spy_bars or len(spy_bars) < 6:
                return None
            spy_now = spy_bars[-1].close
            spy_5d_ago = spy_bars[-6].close
            if not spy_now or not spy_5d_ago or spy_5d_ago <= 0:
                return None
            spy_5d_return = (spy_now - spy_5d_ago) / spy_5d_ago

            # VIX 1-day change
            vix_bars = md.get_historical_data(
                symbol="^VIX",
                start=start_date,
                end=end_date,
                interval="1d",
                prefer_yahoo=True,
            )
            if not vix_bars or len(vix_bars) < 2:
                return None
            vix_now = vix_bars[-1].close
            vix_prev = vix_bars[-2].close
            if not vix_now or not vix_prev or vix_prev <= 0:
                return None
            vix_1d_change = (vix_now - vix_prev) / vix_prev

            if spy_5d_return < -0.03 and vix_1d_change > 0.10:
                reason = f"SPY_5d={spy_5d_return*100:.1f}%, VIX_1d={vix_1d_change*100:+.1f}%"
                self._c2_crash_cache = (now, reason)
                return reason

            # Negative result is also cacheable
            self._c2_crash_cache = (now, None)
            return None

        except Exception as e:
            logger.debug(f"C2 crash regime check error: {e}")
            return None

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
            # ETFs: raised from 12 → 13. Live data: 64.6% win rate, +$64 avg P&L.
            # Exchange-traded, tight spreads, deep liquidity — deserve Tier 2 treatment.
            score = 13.0
        elif sym in set(DEMO_ALLOWED_FOREX):
            score = 13.0
        elif sym in set(DEMO_ALLOWED_INDICES):
            # Indices: raised from 12 → 14. Live data: 85.7% win rate, +$142 avg P&L.
            # CFDs on major indices (DJ30, GER40, UK100) have extremely tight spreads
            # on eToro and the highest live win rate of any asset class.
            score = 14.0
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

        Alpha Edge only. DSL strategies return 0.0 — their edge is in price
        indicators, not balance sheets. Adding fundamental overlays to DSL
        creates noise: a quality company can still have a bad technical entry.

        LONG signals: strong fundamentals → up to +15, weak → down to -15
        SHORT signals: weak fundamentals → up to +15, strong → down to -15

        Signals used (each contributes ±3 points):
        - Earnings surprise (beat vs miss)
        - Revenue growth (growing vs declining)
        - Insider net buying (buying vs selling)
        - ROE quality (high vs low)
        - Share dilution (buyback vs dilution)
        """
        # Only applies to Alpha Edge strategies
        is_alpha_edge = (
            hasattr(signal, 'metadata') and
            isinstance(getattr(signal, 'metadata', None), dict) and
            False  # checked in score_signal; this is defence-in-depth
        )
        # Defence-in-depth: also check strategy category via fundamental_report presence
        # score_signal only calls this for AE, but if called directly, guard here too.
        # We use fundamental_report as the proxy — it's only populated for AE.
        # For DSL, fundamental_report is None (no fundamental filter runs).
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
                raw_score += 3.0
            elif fd.earnings_surprise >= 0.01:
                raw_score += 1.5
            elif fd.earnings_surprise <= -0.05:
                raw_score -= 3.0
            elif fd.earnings_surprise <= -0.01:
                raw_score -= 1.5

        # 2. Revenue growth (±3)
        if fd.revenue_growth is not None:
            if fd.revenue_growth >= 0.10:
                raw_score += 3.0
            elif fd.revenue_growth >= 0.03:
                raw_score += 1.5
            elif fd.revenue_growth <= -0.05:
                raw_score -= 3.0
            elif fd.revenue_growth <= -0.01:
                raw_score -= 1.5

        # 3. Insider net buying (±3)
        if fd.insider_net_buying is not None:
            if fd.insider_net_buying >= 3:
                raw_score += 3.0
            elif fd.insider_net_buying >= 1:
                raw_score += 1.5
            elif fd.insider_net_buying <= -3:
                raw_score -= 3.0
            elif fd.insider_net_buying <= -1:
                raw_score -= 1.5

        # 4. ROE quality (±3)
        if fd.roe is not None:
            if fd.roe >= 0.20:
                raw_score += 3.0
            elif fd.roe >= 0.12:
                raw_score += 1.5
            elif fd.roe <= 0.0:
                raw_score -= 3.0
            elif fd.roe <= 0.05:
                raw_score -= 1.5

        # 5. Share dilution vs buyback (±3)
        if fd.shares_change_percent is not None:
            if fd.shares_change_percent <= -0.02:
                raw_score += 3.0
            elif fd.shares_change_percent <= -0.005:
                raw_score += 1.5
            elif fd.shares_change_percent >= 0.05:
                raw_score -= 3.0
            elif fd.shares_change_percent >= 0.02:
                raw_score -= 1.5

        # Direction-aware: flip the sign for shorts
        if is_long:
            direction_score = raw_score
        else:
            direction_score = -raw_score

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
        total_trades = perf.total_trades if perf and hasattr(perf, 'total_trades') else None
        trade_confidence = round(min(1.0, math.sqrt(max(0, total_trades or 0) / 15.0)), 3) if total_trades else 0.0
        return {
            'wf_test_sharpe': meta.get('wf_test_sharpe'),
            'wf_train_sharpe': meta.get('wf_train_sharpe'),
            'wf_performance_degradation': meta.get('wf_performance_degradation'),
            'walk_forward_validated': meta.get('walk_forward_validated', False),
            'total_trades': total_trades,
            'win_rate': perf.win_rate if perf and hasattr(perf, 'win_rate') else None,
            'trade_confidence_factor': trade_confidence,
        }

    def _get_signal_details(self, signal: TradingSignal, strategy: Strategy) -> Dict[str, Any]:
        entry_conditions = strategy.rules.get('entry_conditions', []) if strategy.rules else []
        meta = getattr(signal, 'metadata', None) or {}
        return {
            'entry_conditions_count': len(entry_conditions),
            'has_stop_loss': bool(strategy.risk_params and strategy.risk_params.stop_loss_pct),
            'has_profit_target': bool(strategy.risk_params and strategy.risk_params.take_profit_pct),
            'signal_confidence': getattr(signal, 'confidence', None),
            'entry_persistence': meta.get('entry_persistence'),
            'strategy_type': self._detect_strategy_type(strategy),
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

            # Scale to ±1 point max.
            # Marketaux free tier returns 3 articles per symbol — too small a sample
            # to justify strong conviction impact. Empirically: bearish news trades
            # avg +$7 (45% WR) vs neutral +$51 (54% WR) — directionally valid but
            # weak signal. Use as a tiebreaker only.
            adjusted = direction_score * 1.0
            adjusted = max(-1.0, min(1.0, adjusted))

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

    # ─── FACTOR EXPOSURE (±6 points) — Alpha Edge only ──────────────────
    def _score_factor_exposure(self, signal: TradingSignal, strategy: Strategy) -> float:
        """
        Regime-aware factor tilt adjustment. Alpha Edge only.

        DSL strategies return 0.0 — beta and P/E are not relevant to a price-based
        EMA crossover or Keltner breakout strategy. The factor data would add noise.

        For Alpha Edge: in ranging/low-vol regimes favor low-beta (defensive);
        in trending-up regimes favor high-beta, high-revenue-growth (offensive).

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
                if beta is not None:
                    if is_long:
                        if beta < 0.8:
                            adjustment += 3.0
                        elif beta > 1.5:
                            adjustment -= 3.0
                    else:
                        if beta > 1.5:
                            adjustment += 2.0
                        elif beta < 0.8:
                            adjustment -= 2.0

            elif current_regime in ('trending_up', 'trending_up_weak', 'trending_up_strong'):
                if beta is not None and is_long:
                    if beta > 1.3:
                        adjustment += 3.0
                    elif beta < 0.7:
                        adjustment -= 2.0
                if revenue_growth is not None and is_long:
                    if revenue_growth > 0.15:
                        adjustment += 3.0
                    elif revenue_growth < 0.0:
                        adjustment -= 2.0

            if pe_ratio is not None and pe_ratio > 60 and is_long:
                adjustment -= 2.0

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
