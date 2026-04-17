"""
Cross-Sectional Fundamental Ranker — Institutional-Grade Multi-Factor Scoring.

Instead of evaluating each stock in isolation against absolute thresholds,
this module ranks all stocks in the universe against each other using
percentile-based scoring across 4 orthogonal factor dimensions:

1. Value: FCF yield + earnings yield + book-to-price
2. Quality: Piotroski F-Score + inverse accruals ratio
3. Momentum: 12-month price return minus 1-month return
4. Growth: SUE (Standardized Unexpected Earnings) + revenue acceleration

Each stock gets a composite score (0-100) that combines all 4 factors.
The top quintile (80-100) are LONG candidates, bottom quintile (0-20) are SHORT.

This is how AQR, Two Sigma, and D.E. Shaw approach fundamental analysis —
not with individual factor templates but with composite cross-sectional ranking.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


class FundamentalRanker:
    """
    Cross-sectional fundamental ranking engine.

    Ranks all stock symbols in the universe by a composite score
    combining value, quality, momentum, and growth factors.
    Results are cached for the duration of a proposal cycle.
    """

    # Regime-dependent factor weights.
    # In risk-off / downtrending markets, capital preservation factors (quality, value)
    # should dominate. In risk-on / uptrending markets, return-seeking factors
    # (momentum, growth) should dominate. This is how multi-billion-dollar
    # systematic funds (AQR, Two Sigma) tilt their factor exposures.
    #
    # The weights are calibrated to academic factor return data:
    # - Quality premium is most persistent across regimes (~30bp/month)
    # - Value premium is strongest in recoveries and risk-off (mean-reversion)
    # - Momentum premium is strongest in trending markets, crashes in reversals
    # - Growth premium is strongest in expansions, weakest in contractions
    REGIME_WEIGHTS: Dict[str, Dict[str, float]] = {
        # Trending up: momentum and growth lead, quality as ballast
        "trending_up_strong":   {"value": 0.10, "quality": 0.20, "momentum": 0.35, "growth": 0.35},
        "trending_up_weak":     {"value": 0.15, "quality": 0.25, "momentum": 0.30, "growth": 0.30},
        # Trending down: quality and value protect capital, momentum crashes
        "trending_down_strong": {"value": 0.30, "quality": 0.40, "momentum": 0.05, "growth": 0.25},
        "trending_down_weak":   {"value": 0.25, "quality": 0.35, "momentum": 0.10, "growth": 0.30},
        # Ranging / low vol: balanced, slight quality tilt
        "ranging_narrow":       {"value": 0.25, "quality": 0.30, "momentum": 0.20, "growth": 0.25},
        "ranging_wide":         {"value": 0.25, "quality": 0.30, "momentum": 0.20, "growth": 0.25},
        # High volatility: defensive — quality and value dominate
        "high_volatility":      {"value": 0.30, "quality": 0.35, "momentum": 0.10, "growth": 0.25},
        # Transitional: equal weight (no conviction on direction)
        "transitional":         {"value": 0.25, "quality": 0.25, "momentum": 0.25, "growth": 0.25},
    }

    def __init__(self, fundamental_data_provider=None, market_data_manager=None):
        self._provider = fundamental_data_provider
        self._market_data = market_data_manager
        self._cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._cache_ts: float = 0
        self._cache_ttl: float = 7200  # 2 hours

    def _ensure_provider(self):
        if self._provider is None:
            from src.data.fundamental_data_provider import get_fundamental_data_provider
            self._provider = get_fundamental_data_provider()

    def _get_regime_weights(self) -> Dict[str, float]:
        """
        Determine factor weights based on current market regime.
        
        Detects the sub-regime via MarketStatisticsAnalyzer and maps it to
        the REGIME_WEIGHTS table. Falls back to balanced weights if detection
        fails. This ensures the ranker tilts toward defensive factors in
        downtrends and offensive factors in uptrends — the way a PM would
        adjust factor exposure at a systematic fund.
        
        Returns:
            Dict with value/quality/momentum/growth weights summing to 1.0
        """
        default_weights = {"value": 0.25, "quality": 0.30, "momentum": 0.20, "growth": 0.25}
        try:
            from src.strategy.market_analyzer import MarketStatisticsAnalyzer
            if self._market_data is None:
                return default_weights
            analyzer = MarketStatisticsAnalyzer(self._market_data)
            sub_regime, _, _, _ = analyzer.detect_sub_regime()
            regime_key = sub_regime.value.lower() if hasattr(sub_regime, 'value') else str(sub_regime).lower()
            
            # Try exact match first, then fuzzy match on key substrings
            weights = self.REGIME_WEIGHTS.get(regime_key)
            if weights is None:
                for rk, rw in self.REGIME_WEIGHTS.items():
                    if rk in regime_key or regime_key in rk:
                        weights = rw
                        break
            
            if weights is None:
                weights = default_weights
            
            logger.info(
                f"FundamentalRanker: regime={regime_key}, factor weights: "
                f"V={weights['value']:.0%} Q={weights['quality']:.0%} "
                f"M={weights['momentum']:.0%} G={weights['growth']:.0%}"
            )
            return weights
        except Exception as e:
            logger.debug(f"FundamentalRanker: could not detect regime for weights: {e}")
            return default_weights

    def rank_universe(
        self,
        symbols: List[str],
        market_statistics: Dict[str, Dict] = None,
        weights: Dict[str, float] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Rank all symbols by composite fundamental score.

        Args:
            symbols: List of stock symbols to rank
            market_statistics: Optional pre-computed market stats (for momentum)
            weights: Optional factor weights (default: equal)

        Returns:
            Dict mapping symbol to {composite_score, value_rank, quality_rank,
            momentum_rank, growth_rank, raw_metrics}
        """
        # Check cache
        if self._cache and (time.time() - self._cache_ts) < self._cache_ttl:
            # Return cached if symbols haven't changed
            if set(self._cache.keys()) == set(symbols):
                return self._cache

        self._ensure_provider()

        # Regime-dependent factor weights: detect current market regime and tilt
        # factor exposures accordingly. Caller can override with explicit weights.
        if weights is None:
            weights = self._get_regime_weights()
        w = weights

        # Step 1: Gather raw metrics for all symbols (parallelized — DB I/O bound)
        raw_data: Dict[str, Dict[str, Any]] = {}
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        def _gather_one(sym):
            return sym, self._gather_metrics(sym, market_statistics)
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(_gather_one, sym): sym for sym in symbols}
            for future in as_completed(futures):
                sym, metrics = future.result()
                if metrics:
                    raw_data[sym] = metrics

        if len(raw_data) < 5:
            logger.warning(f"FundamentalRanker: only {len(raw_data)} symbols with data, need >= 5 for ranking")
            return {}

        # Step 2: Compute percentile ranks for each factor
        value_scores = self._percentile_rank(raw_data, "value_composite")
        quality_scores = self._percentile_rank(raw_data, "quality_composite")
        momentum_scores = self._percentile_rank(raw_data, "momentum_composite")
        growth_scores = self._percentile_rank(raw_data, "growth_composite")

        # Step 3: Compute weighted composite score
        result: Dict[str, Dict[str, Any]] = {}
        for symbol in raw_data:
            v = value_scores.get(symbol, 50.0)
            q = quality_scores.get(symbol, 50.0)
            m = momentum_scores.get(symbol, 50.0)
            g = growth_scores.get(symbol, 50.0)

            composite = (
                w["value"] * v +
                w["quality"] * q +
                w["momentum"] * m +
                w["growth"] * g
            )

            result[symbol] = {
                "composite_score": round(composite, 1),
                "value_rank": round(v, 1),
                "quality_rank": round(q, 1),
                "momentum_rank": round(m, 1),
                "growth_rank": round(g, 1),
                "raw_metrics": raw_data[symbol],
            }

        # Cache results
        self._cache = result
        self._cache_ts = time.time()

        ranked = sorted(result.items(), key=lambda x: x[1]["composite_score"], reverse=True)
        top5 = [(s, r["composite_score"]) for s, r in ranked[:5]]
        bot5 = [(s, r["composite_score"]) for s, r in ranked[-5:]]
        logger.info(
            f"FundamentalRanker: ranked {len(result)} symbols. "
            f"Top 5: {top5}, Bottom 5: {bot5}"
        )

        return result

    def _gather_metrics(
        self, symbol: str, market_statistics: Dict = None
    ) -> Optional[Dict[str, Any]]:
        """Gather raw factor metrics for a single symbol."""
        try:
            quarters = self._provider.get_historical_fundamentals(symbol, quarters=8)
            if not quarters or len(quarters) < 2:
                return None

            latest = quarters[-1]  # Most recent quarter (list is chronological)
            prev = quarters[-2] if len(quarters) >= 2 else {}

            # ---- Value composite ----
            fcf_yield = latest.get("fcf_yield")
            pe = latest.get("pe_ratio")
            earnings_yield = (1.0 / pe) if pe and pe > 0 else None

            # Intangibles-adjusted book value: capitalize R&D (33% depreciation for
            # tech, 20% for pharma) and 30% of SGA (15% depreciation) into book value.
            # This corrects the ~12% earnings understatement that distorts traditional
            # value metrics for knowledge-intensive firms (Lev & Srivastava 2019).
            adjusted_pb_yield = None  # inverse of adjusted P/B (higher = cheaper)
            mkt_cap = latest.get("market_cap")
            book_value = latest.get("total_stockholders_equity")
            if mkt_cap and mkt_cap > 0 and book_value is not None:
                # Accumulate R&D and SGA capital from recent quarters
                knowledge_capital = 0
                org_capital = 0
                for i, q in enumerate(quarters):
                    rd = q.get("rd_expense") or 0
                    sga = q.get("sga_expense") or 0
                    age = len(quarters) - 1 - i  # quarters ago
                    # R&D: 33% annual depreciation → ~8.25% per quarter
                    if rd > 0:
                        knowledge_capital += rd * ((1 - 0.0825) ** age)
                    # Organizational capital: 30% of SGA, 15% annual depreciation → ~3.75%/quarter
                    if sga > 0:
                        org_capital += 0.3 * sga * ((1 - 0.0375) ** age)
                adjusted_book = book_value + knowledge_capital + org_capital
                if adjusted_book > 0:
                    adjusted_pb_yield = adjusted_book / mkt_cap  # Higher = cheaper

            value_components = [v for v in [fcf_yield, earnings_yield, adjusted_pb_yield] if v is not None]
            value_composite = sum(value_components) / len(value_components) if value_components else None

            # ---- Quality composite ----
            f_score = latest.get("piotroski_f_score")
            accruals = latest.get("accruals_ratio")
            # Inverse accruals: lower accruals = higher quality, normalize to 0-9 scale
            inv_accruals_score = None
            if accruals is not None:
                # Map accruals from [-0.2, 0.2] to [9, 0] (lower accruals = higher score)
                inv_accruals_score = max(0, min(9, 4.5 - accruals * 22.5))

            quality_components = [v for v in [f_score, inv_accruals_score] if v is not None]
            quality_composite = sum(quality_components) / len(quality_components) if quality_components else None

            # ---- Momentum composite ----
            momentum_composite = None
            if market_statistics and symbol in market_statistics:
                stats = market_statistics[symbol]
                trend = stats.get("trend_metrics", {})
                # Use trend strength as momentum proxy (already computed from price data)
                momentum_composite = trend.get("trend_strength", 0)
            # Fallback: use revenue growth trend as fundamental momentum
            if momentum_composite is None:
                rev_growths = [q.get("revenue_growth") for q in quarters[-4:] if q.get("revenue_growth") is not None]
                if rev_growths:
                    momentum_composite = sum(rev_growths) / len(rev_growths)

            # ---- Growth composite ----
            sue = latest.get("sue")
            rev_growth = latest.get("revenue_growth")
            prev_rev_growth = prev.get("revenue_growth") if prev else None
            # Revenue acceleration: current growth > previous growth
            rev_accel = None
            if rev_growth is not None and prev_rev_growth is not None:
                rev_accel = rev_growth - prev_rev_growth  # Positive = accelerating

            growth_components = [v for v in [sue, rev_accel] if v is not None]
            growth_composite = sum(growth_components) / len(growth_components) if growth_components else None

            return {
                "value_composite": value_composite,
                "quality_composite": quality_composite,
                "momentum_composite": momentum_composite,
                "growth_composite": growth_composite,
                # Raw metrics for debugging / template use
                "fcf_yield": fcf_yield,
                "pe_ratio": pe,
                "piotroski_f_score": f_score,
                "accruals_ratio": accruals,
                "sue": sue,
                "revenue_growth": rev_growth,
                "revenue_acceleration": rev_accel,
                "earnings_surprise": latest.get("earnings_surprise"),
                "roe": latest.get("roe"),
                "debt_to_equity": latest.get("debt_to_equity"),
                "dividend_yield": latest.get("dividend_yield"),
                "market_cap": latest.get("market_cap"),
                "institutional_ownership": None,  # Populated separately if needed
            }

        except Exception as e:
            logger.debug(f"FundamentalRanker: could not gather metrics for {symbol}: {e}")
            return None

    def _percentile_rank(
        self, data: Dict[str, Dict], field: str
    ) -> Dict[str, float]:
        """
        Compute percentile rank (0-100) for a field across all symbols.
        Higher value = higher percentile. Symbols with None get 50 (neutral).
        """
        values = []
        for symbol, metrics in data.items():
            val = metrics.get(field)
            if val is not None:
                values.append((symbol, val))

        if not values:
            return {s: 50.0 for s in data}

        # Sort ascending (lowest value = lowest percentile)
        values.sort(key=lambda x: x[1])
        n = len(values)

        ranks = {}
        for i, (symbol, _) in enumerate(values):
            ranks[symbol] = (i / max(n - 1, 1)) * 100.0

        # Assign 50 to symbols with no data
        for symbol in data:
            if symbol not in ranks:
                ranks[symbol] = 50.0

        return ranks

    def get_long_candidates(
        self, rankings: Dict[str, Dict], top_pct: float = 20.0
    ) -> List[Tuple[str, float]]:
        """Get symbols in the top percentile by composite score."""
        threshold = 100.0 - top_pct
        candidates = [
            (sym, r["composite_score"])
            for sym, r in rankings.items()
            if r["composite_score"] >= threshold
        ]
        return sorted(candidates, key=lambda x: x[1], reverse=True)

    def get_short_candidates(
        self, rankings: Dict[str, Dict], bottom_pct: float = 20.0
    ) -> List[Tuple[str, float]]:
        """Get symbols in the bottom percentile by composite score."""
        candidates = [
            (sym, r["composite_score"])
            for sym, r in rankings.items()
            if r["composite_score"] <= bottom_pct
        ]
        return sorted(candidates, key=lambda x: x[1])
