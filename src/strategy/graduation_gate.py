"""
Graduation Gate — backend logic for promoting (template, symbol) pairs to live trading.

Qualification criteria (all must pass):
  - paper_trades >= dynamic Sharpe-based threshold (improvement 1)
  - paper_sharpe >= 0.6 × wf_sharpe  (live performance tracks walk-forward)
  - paper_win_rate >= 0.45
  - paper_pnl > 0
  - wf_sharpe lower CI > 0 (improvement 3)
  - alpha vs SPY >= -5% (improvement 4, if benchmark_return provided)
  - DSR >= 0.95 (improvement 5, if n_trials provided)
  - Not already active in live_strategies
  - Not rejected in the last 14 days

Approval flow:
  1. CIO reviews the queue via GET /strategies/graduation-queue
  2. CIO approves via POST /strategies/{id}/graduate with optional overrides
  3. A live_strategies row is created — the HARD GATE is now open for that pair
  4. TradingScheduler checks live_strategies before every live fill (Sprint 5)

Rejection flow:
  - POST /strategies/{id}/reject-graduation records rejected_at
  - 14-day cooldown before the pair can re-appear in the queue
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Qualification thresholds ──────────────────────────────────────────────────

MIN_PAPER_TRADES = 20
MIN_QUALIFICATION_RATIO = 0.60   # paper_sharpe / wf_sharpe
MAX_QUALIFICATION_RATIO = 2.0    # paper_sharpe must not exceed 2× wf_sharpe
                                  # A ratio > 2 means the paper period was regime-lucky,
                                  # not a genuine edge confirmation. Graduating a strategy
                                  # with paper_sharpe 3× its WF sharpe is graduating the
                                  # regime, not the strategy.
MIN_PAPER_WIN_RATE = 0.55        # raised from 0.45 — 45% is too permissive for real money
MIN_PAPER_PNL = 0.0              # must be profitable
REJECTION_COOLDOWN_DAYS = 14

# ── P0-2 (Sprint B): statistical-power gates ──────────────────────────────────
# Two independent failures of the old gate let losing strategies reach LIVE
# (GOOGL 11% WR over 18 live trades, TXN 0% over 3, both bleeding real money):
#
#   1. min_trades had NO hard floor. `_get_min_trades_for_interval` used a dynamic
#      Sharpe formula `max(5, ceil((1.96/sharpe)^2))` as the PRIMARY path, which
#      collapses to 3–5 trades for paper_sharpe >= 1.0. A 5-trade sample is almost
#      no evidence. MIN_PAPER_TRADES is now enforced as a HARD FLOOR the dynamic
#      formula cannot undercut (config: graduation_gate.min_trades, currently 15).
#
#   2. The win-rate gate used the POINT estimate (win_rate >= floor). At small n a
#      point estimate has a wide CI, so a genuinely sub-floor strategy clears it by
#      luck; with ~300 candidates (multiple testing) several false positives are
#      expected. We now also require the WILSON LOWER BOUND of the win rate to clear
#      (type_floor − tolerance), i.e. we must be statistically confident the win rate
#      is not just a lucky small-sample draw. The bound is taken RELATIVE to the
#      strategy-type floor (not an absolute number) so legitimately low-WR
#      trend-following strategies — which the entire live book is — are not wrongly
#      blocked; only strategies whose lower bound collapses well below their own
#      type floor are rejected.
WR_CI_CONFIDENCE = 0.90          # confidence level for the win-rate lower bound
WR_CI_FLOOR_TOLERANCE = 0.10     # allowed gap below the type floor for the lower bound

# Override constants from YAML if graduation_gate section exists.
# This means Settings page changes take effect immediately (the PUT endpoint
# also patches the in-memory constants directly, but this covers the startup
# case where the YAML was already updated before the process started).
try:
    import yaml as _yaml
    from pathlib import Path as _Path
    _cfg_path = _Path("config/autonomous_trading.yaml")
    if _cfg_path.exists():
        with open(_cfg_path, "r") as _f:
            _cfg = _yaml.safe_load(_f) or {}
        _gg = _cfg.get("graduation_gate", {}) or {}
        if "min_trades" in _gg:
            MIN_PAPER_TRADES = int(_gg["min_trades"])
        if "min_win_rate_pct" in _gg:
            MIN_PAPER_WIN_RATE = float(_gg["min_win_rate_pct"]) / 100.0
        if "min_qualification_ratio" in _gg:
            MIN_QUALIFICATION_RATIO = float(_gg["min_qualification_ratio"])
        if "max_qualification_ratio_cap" in _gg:
            MAX_QUALIFICATION_RATIO = float(_gg["max_qualification_ratio_cap"])
        if "rejection_cooldown_days" in _gg:
            REJECTION_COOLDOWN_DAYS = int(_gg["rejection_cooldown_days"])
        if "wr_ci_confidence" in _gg:
            WR_CI_CONFIDENCE = float(_gg["wr_ci_confidence"])
        if "wr_ci_floor_tolerance" in _gg:
            WR_CI_FLOOR_TOLERANCE = float(_gg["wr_ci_floor_tolerance"])
except Exception:
    pass  # Fall back to hardcoded defaults — never crash at import time


def _wilson_lower_bound(successes: int, n: int, confidence: float = 0.90) -> float:
    """Wilson score interval lower bound for a binomial proportion.

    More accurate than the normal approximation at small n (which is exactly the
    regime the graduation gate operates in). Returns the lower bound of the
    `confidence`-level CI for the true success probability given `successes`
    out of `n` observations. Used to gate win-rate so a lucky small-sample draw
    above the floor does not graduate to live capital.
    """
    if n <= 0:
        return 0.0
    # z for a one-sided lower bound at the given confidence
    _z_table = {0.80: 0.8416, 0.85: 1.0364, 0.90: 1.2816, 0.95: 1.6449, 0.975: 1.96}
    # nearest tabulated z (keys are sparse; pick closest)
    z = _z_table.get(round(confidence, 3))
    if z is None:
        z = min(_z_table.items(), key=lambda kv: abs(kv[0] - confidence))[1]
    p_hat = successes / n
    denom = 1.0 + (z * z) / n
    center = (p_hat + (z * z) / (2 * n)) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1 - p_hat) / n) + (z * z) / (4 * n * n))
    return max(0.0, center - margin)


def _get_min_trades_for_interval(interval: Optional[str], paper_sharpe: Optional[float] = None, win_rate: Optional[float] = None) -> int:
    """
    Return interval-aware min_trades for graduation.

    Improvement 1 — Dynamic Sharpe-based threshold:
      dynamic_min = max(5, ceil((1.96 / paper_sharpe)²)), capped at 30.
      This is the primary threshold when paper_sharpe is known.

    P0-2 (Sprint B) — HARD FLOOR:
      The result is floored at MIN_PAPER_TRADES (config: graduation_gate.min_trades,
      currently 15) regardless of how low the dynamic formula or the YAML interval
      floor would go. Previously the dynamic formula governed alone and collapsed to
      3–5 trades for paper_sharpe >= 1.0 — i.e. a strategy could reach LIVE on 5 paper
      trades, which is almost no statistical evidence and is how losing strategies
      (GOOGL, TXN) reached real capital. The hard floor cannot be undercut by the
      dynamic formula OR the high-conviction exception.

    When paper_sharpe is None or <= 0, fall back to the YAML interval floor, also
    floored at MIN_PAPER_TRADES.

    High-conviction exception:
      If paper_sharpe ≥ 2.0 AND win_rate ≥ 0.70, reduce the dynamic value by 40%
      — but still floored at MIN_PAPER_TRADES (the floor wins).
    """
    # Dynamic Sharpe-based threshold — primary when Sharpe is known
    if paper_sharpe is not None and paper_sharpe > 0:
        dynamic_min = max(5, math.ceil((1.96 / paper_sharpe) ** 2))
        dynamic_min = min(dynamic_min, 30)  # cap at 30

        # High-conviction exception: strong Sharpe + high win rate → lower bar,
        # but never below the hard floor.
        if win_rate is not None and paper_sharpe >= 2.0 and win_rate >= 0.70:
            return max(MIN_PAPER_TRADES, int(dynamic_min * 0.60))

        return max(MIN_PAPER_TRADES, dynamic_min)

    # Fallback: YAML interval floor when Sharpe is unknown
    iv = (interval or "1d").lower()
    try:
        import time as _time
        import yaml as _y
        from pathlib import Path as _P
        # Cache the YAML read for 5 minutes — this function is called 66+ times per request
        _cache = getattr(_get_min_trades_for_interval, '_yaml_cache', None)
        if _cache and (_time.time() - _cache[0]) < 300:
            pt_gg = _cache[1]
        else:
            _p = _P("config/autonomous_trading.yaml")
            pt_gg = {}
            if _p.exists():
                with open(_p, "r") as _f:
                    _c = _y.safe_load(_f) or {}
                pt_gg = _c.get("paper_trading", {}).get("graduation_gate", {})
            _get_min_trades_for_interval._yaml_cache = (_time.time(), pt_gg)
        if iv in ("1h", "2h"):
            return max(MIN_PAPER_TRADES, int(pt_gg.get("min_trades_1h", 12)))
        elif iv == "4h":
            return max(MIN_PAPER_TRADES, int(pt_gg.get("min_trades_4h", 8)))
        else:
            return max(MIN_PAPER_TRADES, int(pt_gg.get("min_trades_1d", 5)))
    except Exception:
        pass

    # Hardcoded fallback (still floored at the hard minimum)
    if iv in ("1h", "2h"):
        return max(MIN_PAPER_TRADES, 12)
    elif iv == "4h":
        return max(MIN_PAPER_TRADES, 8)
    return max(MIN_PAPER_TRADES, 5)


def _get_min_sql_having_trades() -> int:
    """
    Return the minimum trades threshold for the graduation SQL HAVING clause.

    G-31: The SQL HAVING must use the LOWEST possible threshold so that all
    candidates reach is_qualified(), which applies the correct per-interval
    and Sharpe-based dynamic threshold.

    With improvement 1 (dynamic Sharpe-based threshold), the minimum is 5
    (the floor of the dynamic formula). Using a higher value here would filter
    out high-Sharpe strategies that legitimately need fewer trades.
    """
    return 5


def _get_min_avg_pnl_per_trade() -> float:
    """Return min avg P&L per trade from paper_trading.graduation_gate.min_avg_pnl_per_trade."""
    import time as _time
    _cache = getattr(_get_min_avg_pnl_per_trade, '_cache', None)
    if _cache and (_time.time() - _cache[0]) < 300:  # 5-min TTL
        return _cache[1]
    result = 0.0
    try:
        import yaml as _y
        from pathlib import Path as _P
        _p = _P("config/autonomous_trading.yaml")
        if _p.exists():
            with open(_p, "r") as _f:
                _c = _y.safe_load(_f) or {}
            result = float(_c.get("paper_trading", {}).get("graduation_gate", {}).get("min_avg_pnl_per_trade", 0.0))
    except Exception:
        pass
    _get_min_avg_pnl_per_trade._cache = (_time.time(), result)
    return result


def _get_regime_adjusted_max_ratio() -> float:
    """
    Return the regime-adjusted qualification ratio cap.

    Fix 1 (2026-05-18): A flat 2.0× cap blocks everything during a bull run
    because paper Sharpe is inflated for all LONG strategies simultaneously.
    The cap should be calibrated to what's actually surprising given the regime.

    Regime → cap:
      trending_up_strong:  3.5× (strong bull — outperformance vs WF is expected)
      trending_up / weak:  3.0×
      ranging / neutral:   2.0× (WF test period is a fair comparison)
      trending_down:       1.5× (bear — outperformance vs WF is suspicious)
      high_vol:            1.5× (volatile — same)
      unknown / fallback:  2.0×

    Reads the current regime from config/autonomous_trading.yaml (written by
    the trading scheduler every cycle) — no market data manager call needed.
    Result is cached for 10 minutes.
    """
    import time as _time
    _now = _time.time()
    _cache = getattr(_get_regime_adjusted_max_ratio, '_cache', None)
    if _cache and (_now - _cache[0]) < 600:  # 10-minute TTL
        return _cache[1]

    result = MAX_QUALIFICATION_RATIO  # fallback
    try:
        import yaml as _yaml
        from pathlib import Path as _Path
        _cfg_path = _Path("config/autonomous_trading.yaml")
        if _cfg_path.exists():
            with open(_cfg_path, "r") as _f:
                _cfg = _yaml.safe_load(_f) or {}
            _regime_name = (_cfg.get("market_regime", {}) or {}).get("current", "") or ""
            _regime_name = _regime_name.lower()
            if "trending_up_strong" in _regime_name:
                result = 3.5
            elif "trending_up" in _regime_name:
                result = 3.0
            elif "trending_down" in _regime_name or "high_vol" in _regime_name:
                result = 1.5
            else:
                result = 2.0
    except Exception:
        pass

    _get_regime_adjusted_max_ratio._cache = (_now, result)
    return result


def _get_strategy_type_win_rate_floor(strategy_type: Optional[str]) -> float:
    """
    Return the win rate floor appropriate for the strategy type.

    Fix 2 (2026-05-18): A flat 55% win rate floor is wrong for trend-following
    strategies, which make money on large winners with many small losses.
    The P&L and qualification ratio are the right gates for trend-following.
    Mean-reversion relies on high hit rate — 55% is appropriate there.

    strategy_type → floor:
      trend_following / momentum / breakout / ema_* / adx_* / atr_*: 45%
      mean_reversion / volatility / rsi_* / bb_* / stochastic:        55%
      everything else:                                                  50%
    """
    if not strategy_type:
        return MIN_PAPER_WIN_RATE

    st = strategy_type.lower()
    trend_types = {
        'trend_following', 'momentum', 'breakout', 'trend',
        'ema_crossover', 'macd_trend', 'adx_trend', 'vwap_trend',
        'ema_ribbon', 'atr_trend', 'sma_trend',
    }
    reversion_types = {
        'mean_reversion', 'volatility', 'rsi_dip', 'bb_midband',
        'stochastic', 'reversion', 'oscillator',
    }
    if any(t in st for t in trend_types):
        return 0.45
    if any(t in st for t in reversion_types):
        return 0.55
    return 0.50


# ── Improvement 5: Deflated Sharpe Ratio (Bailey & López de Prado 2014) ──────

def _inv_normal(p: float) -> float:
    """Inverse normal CDF — uses scipy if available, else rational approximation."""
    try:
        from scipy.stats import norm
        return float(norm.ppf(p))
    except ImportError:
        # Rational approximation (Abramowitz & Stegun)
        if p <= 0:
            return -8.0
        if p >= 1:
            return 8.0
        if p < 0.5:
            t = math.sqrt(-2 * math.log(p))
        else:
            t = math.sqrt(-2 * math.log(1 - p))
        c = [2.515517, 0.802853, 0.010328]
        d = [1.432788, 0.189269, 0.001308]
        num = c[0] + c[1] * t + c[2] * t * t
        den = 1 + d[0] * t + d[1] * t * t + d[2] * t * t * t
        result = t - num / den
        return -result if p < 0.5 else result


def _normal_cdf(x: float) -> float:
    """Standard normal CDF — uses scipy if available, else math.erf."""
    try:
        from scipy.stats import norm
        return float(norm.cdf(x))
    except ImportError:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def compute_dsr(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """
    Deflated Sharpe Ratio — adjusts observed Sharpe for multiple testing,
    sample length, skewness and kurtosis.

    Returns the probability that the true Sharpe > 0 after deflation.
    A DSR < 0.95 means the observed Sharpe is not statistically significant
    after accounting for the number of strategies tested.

    Reference: Bailey & López de Prado (2014), "The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting and Non-Normality".
    """
    if n_observations <= 1 or n_trials <= 0 or observed_sharpe <= 0:
        return 0.0

    # Expected maximum Sharpe from n_trials IID tests
    # Approximation: E[max SR] ≈ (1 - γ) * Φ⁻¹(1 - 1/n) + γ * Φ⁻¹(1 - 1/(n·e))
    euler_gamma = 0.5772156649
    p1 = max(1e-10, 1.0 - 1.0 / n_trials)
    p2 = max(1e-10, 1.0 - 1.0 / (n_trials * math.e))
    expected_max = (
        (1 - euler_gamma) * _inv_normal(p1)
        + euler_gamma * _inv_normal(p2)
    )

    # Sharpe ratio standard error with skewness/kurtosis correction
    sr_std = math.sqrt(
        (1 + (0.5 * observed_sharpe ** 2) - skewness * observed_sharpe
         + ((kurtosis - 3) / 4) * observed_sharpe ** 2)
        / (n_observations - 1)
    )

    # DSR: probability that true SR > 0 after accounting for selection bias
    z = (observed_sharpe - expected_max * sr_std) / sr_std
    return _normal_cdf(z)


def get_paper_stats_for_strategy(
    session: Session,
    strategy_id: str,
    symbol: str,
) -> Dict[str, Any]:
    """
    Compute paper trading stats for a (strategy_id, symbol) pair from trade_journal.

    Returns dict with: paper_trades, paper_sharpe, paper_win_rate, paper_total_pnl
    """
    from sqlalchemy import text

    row = session.execute(
        text("""
            SELECT
                COUNT(*)                                                AS trades,
                ROUND(
                    CASE WHEN STDDEV(pnl) > 0
                         THEN (AVG(pnl) / STDDEV(pnl)) * SQRT(252)
                         ELSE 0
                    END::numeric, 4
                )                                                       AS sharpe,
                ROUND(
                    100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0)::numeric, 2
                )                                                       AS win_rate_pct,
                ROUND(COALESCE(SUM(pnl), 0)::numeric, 2)               AS total_pnl
            FROM trade_journal
            WHERE strategy_id = :sid
              AND symbol       = :sym
              AND pnl IS NOT NULL
              AND account_type = 'demo'
              AND (exit_reason IS NULL OR exit_reason != 'etoro_closed')
        """),
        {"sid": strategy_id, "sym": symbol},
    ).fetchone()

    if not row or not row.trades:
        return {
            "paper_trades": 0,
            "paper_sharpe": None,
            "paper_win_rate": None,
            "paper_total_pnl": None,
        }

    return {
        "paper_trades": int(row.trades),
        "paper_sharpe": float(row.sharpe) if row.sharpe is not None else None,
        "paper_win_rate": float(row.win_rate_pct) / 100.0 if row.win_rate_pct is not None else None,
        "paper_total_pnl": float(row.total_pnl) if row.total_pnl is not None else None,
    }


def get_aggregated_paper_stats(
    session: Session,
    template_name: str,
    symbol: str,
) -> Dict[str, Any]:
    """
    Compute paper trading stats aggregated across ALL strategy versions for a
    (template_name, symbol) pair — the same cross-version view used by the
    graduation queue.  This is the correct denominator for the approval record
    because the queue qualifies pairs on aggregate history, not single-version.
    """
    from sqlalchemy import text

    row = session.execute(
        text("""
            SELECT
                COUNT(*)                                                AS trades,
                ROUND(
                    CASE WHEN STDDEV(tj.pnl) > 0
                         THEN (AVG(tj.pnl) / STDDEV(tj.pnl)) * SQRT(252)
                         ELSE 0
                    END::numeric, 4
                )                                                       AS sharpe,
                ROUND(
                    100.0 * SUM(CASE WHEN tj.pnl > 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0)::numeric, 2
                )                                                       AS win_rate_pct,
                ROUND(COALESCE(SUM(tj.pnl), 0)::numeric, 2)            AS total_pnl
            FROM trade_journal tj
            LEFT JOIN strategies s ON s.id = tj.strategy_id
            WHERE tj.pnl IS NOT NULL
              AND tj.account_type = 'demo'
                  AND (tj.exit_reason IS NULL OR tj.exit_reason != 'etoro_closed')
              AND tj.symbol = :sym
              AND COALESCE(
                    s.strategy_metadata->>'template_name',
                    REGEXP_REPLACE(s.name, ' V[0-9]+$', ''),
                    tj.trade_metadata->>'template_name'
                  ) = :tname
        """),
        {"tname": template_name, "sym": symbol},
    ).fetchone()

    if not row or not row.trades:
        return {
            "paper_trades": 0,
            "paper_sharpe": None,
            "paper_win_rate": None,
            "paper_total_pnl": None,
        }

    return {
        "paper_trades": int(row.trades),
        "paper_sharpe": float(row.sharpe) if row.sharpe is not None else None,
        "paper_win_rate": float(row.win_rate_pct) / 100.0 if row.win_rate_pct is not None else None,
        "paper_total_pnl": float(row.total_pnl) if row.total_pnl is not None else None,
    }


def _get_paper_flat_size() -> float:
    """Configured PAPER flat position size ($/trade), cached 5 min.

    The graduation alpha-vs-benchmark gate expresses paper P&L as a return on
    notional; notional = trades × flat_size. This MUST track the live config
    (paper_trading.flat_position_size). It was hardcoded at $5,000 and went stale
    when the flat size was cut to $1,000 (2026-06-15) — understating paper return
    5× and spuriously failing the −5% alpha gate in up markets (e.g. a qualifying
    SPY pair: 0.56% computed vs 2.78% real). Read from config, default $1,000.
    """
    try:
        import time as _time
        import yaml as _y
        from pathlib import Path as _P
        _cache = getattr(_get_paper_flat_size, "_cache", None)
        if _cache and (_time.time() - _cache[0]) < 300:
            return _cache[1]
        val = 1000.0
        _p = _P("config/autonomous_trading.yaml")
        if _p.exists():
            with open(_p, "r") as _f:
                _c = _y.safe_load(_f) or {}
            val = float(_c.get("paper_trading", {}).get("flat_position_size", 1000.0) or 1000.0)
        _get_paper_flat_size._cache = (_time.time(), val)
        return val
    except Exception:
        return 1000.0


def is_qualified(
    paper_stats: Dict[str, Any],
    wf_sharpe: Optional[float],
    interval: Optional[str] = None,
    strategy_type: Optional[str] = None,
    wf_test_trades: Optional[int] = None,
    benchmark_return: Optional[float] = None,
    n_trials: Optional[int] = None,
    _precomputed_max_ratio: Optional[float] = None,
    _precomputed_min_avg_pnl: Optional[float] = None,
) -> tuple[bool, List[str]]:
    """
    Check whether a (strategy, symbol) pair meets graduation criteria.

    Returns (qualified: bool, reasons: list[str])
    reasons is empty when qualified, contains failure reasons when not.

    Args:
        paper_stats: Dict with paper_trades, paper_sharpe, paper_win_rate, paper_total_pnl
        wf_sharpe: Walk-forward Sharpe from the representative strategy
        interval: Strategy interval ('1d', '4h', '1h') for interval-aware min_trades
        strategy_type: Strategy type string for type-aware win rate floor (Fix 2)
        wf_test_trades: Number of WF test-period trades — used for Sharpe CI gate (improvement 3)
        benchmark_return: SPY return over the paper period — used for alpha gate (improvement 4)
        n_trials: Number of distinct (template, symbol) pairs proposed in last 90d — used for DSR (improvement 5)
    """
    reasons = []

    trades = paper_stats.get("paper_trades", 0) or 0
    sharpe = paper_stats.get("paper_sharpe")
    win_rate = paper_stats.get("paper_win_rate")
    pnl = paper_stats.get("paper_total_pnl")

    # Interval-aware min_trades — improvement 1: Sharpe-based dynamic threshold
    # High-conviction exception: strong Sharpe + high win rate → lower bar
    min_trades = _get_min_trades_for_interval(interval, paper_sharpe=sharpe, win_rate=win_rate)
    if trades < min_trades:
        reasons.append(f"paper_trades={trades} < {min_trades} (interval={interval or '1d'})")

    if pnl is None or pnl <= MIN_PAPER_PNL:
        reasons.append(f"paper_pnl={pnl} not > 0")

    # Avg P&L per trade gate — prevents graduating strategies with technically
    # positive total P&L but near-zero per-trade expectancy
    min_avg_pnl = _precomputed_min_avg_pnl if _precomputed_min_avg_pnl is not None else _get_min_avg_pnl_per_trade()
    if trades > 0 and pnl is not None:
        avg_pnl_per_trade = pnl / trades
        if avg_pnl_per_trade <= min_avg_pnl:
            reasons.append(
                f"avg_pnl_per_trade=${avg_pnl_per_trade:.2f} not > ${min_avg_pnl:.2f}"
            )

    # Fix 2: strategy-type-aware win rate floor.
    effective_win_rate_floor = _get_strategy_type_win_rate_floor(strategy_type)
    if win_rate is None or win_rate < effective_win_rate_floor:
        reasons.append(
            f"paper_win_rate={win_rate:.1%} < {effective_win_rate_floor:.0%} "
            f"(floor for {strategy_type or 'unknown'} strategy type)"
        )

    # P0-2 (Sprint B): Wilson lower-bound win-rate gate — statistical-power guard.
    # The point-estimate floor above passes any strategy whose OBSERVED win rate
    # cleared the floor, even when that observation is a lucky small-sample draw.
    # With ~300 candidates (multiple testing) that admits false positives that then
    # bleed real money (GOOGL 11% WR / 18 live trades, TXN 0% / 3). Additionally
    # require the Wilson lower bound of the win rate to stay within
    # WR_CI_FLOOR_TOLERANCE of the type floor — i.e. we are WR_CI_CONFIDENCE-confident
    # the true win rate is not materially below the floor. The bound is taken
    # RELATIVE to the (low) strategy-type floor, so legitimately low-WR
    # trend-following strategies (the entire live book) are not blocked; only
    # observations whose lower bound collapses below floor−tolerance are rejected.
    if win_rate is not None and win_rate >= effective_win_rate_floor and trades and trades >= 1:
        _wins = int(round(win_rate * int(trades)))
        _wr_lb = _wilson_lower_bound(_wins, int(trades), confidence=WR_CI_CONFIDENCE)
        _wr_lb_floor = max(0.0, effective_win_rate_floor - WR_CI_FLOOR_TOLERANCE)
        if _wr_lb < _wr_lb_floor:
            reasons.append(
                f"win_rate_lower_bound={_wr_lb:.1%} < {_wr_lb_floor:.0%} "
                f"({_wins}/{int(trades)}={win_rate:.0%} clears the "
                f"{effective_win_rate_floor:.0%} floor only on a small sample — the "
                f"{WR_CI_CONFIDENCE:.0%} CI lower bound is below floor−"
                f"{WR_CI_FLOOR_TOLERANCE:.0%}; insufficient confidence the edge is real)"
            )

    if sharpe is None:
        reasons.append("paper_sharpe not computable (no trades with variance)")
    elif not wf_sharpe or wf_sharpe <= 0:
        # FAIL-CLOSED (2026-06-18): no usable WF Sharpe → we cannot validate the
        # paper-vs-WF qualification ratio, so we do NOT promote on real capital.
        # Previously a missing wf_sharpe silently SKIPPED the ratio gate (the pair
        # passed un-checked). The queue applies a per-template best-WF fallback
        # BEFORE this, so this only fires when neither the pair nor any sibling of
        # its template has a WF Sharpe at all — in which case the WF edge is
        # unestablished and the pair must not graduate.
        reasons.append(
            "wf_sharpe unavailable/<=0 — cannot validate paper-vs-WF qualification "
            "ratio (fail-closed; WF edge unestablished)"
        )
    else:
        ratio = sharpe / wf_sharpe
        # Fix 1: regime-adjusted max ratio cap.
        effective_max_ratio = _precomputed_max_ratio if _precomputed_max_ratio is not None else _get_regime_adjusted_max_ratio()
        if ratio < MIN_QUALIFICATION_RATIO:
            reasons.append(
                f"qualification_ratio={ratio:.2f} < {MIN_QUALIFICATION_RATIO} "
                f"(paper_sharpe={sharpe:.2f}, wf_sharpe={wf_sharpe:.2f})"
            )
        elif ratio > effective_max_ratio:
            reasons.append(
                f"qualification_ratio={ratio:.2f} > {effective_max_ratio:.1f} "
                f"(paper_sharpe={sharpe:.2f} is {ratio:.1f}× wf_sharpe={wf_sharpe:.2f} "
                f"— paper period was regime-lucky, not a genuine edge confirmation; "
                f"regime-adjusted cap={effective_max_ratio:.1f}×)"
            )

        # Improvement 7: structural-bias note — paper Sharpe is per-trade on the flat
        # paper size; wf_sharpe is vectorbt's vol-scaled per-bar figure, so the ratio
        # is not strictly apples-to-apples. Informational only — the proper fix
        # (consistent, cost-net Sharpe basis + one threshold re-baseline) is bundled
        # with the F1/F2 cost recalibration.
        logger.debug(
            f"Note: paper_sharpe={sharpe:.2f} (per-trade, flat paper size) vs "
            f"wf_sharpe={wf_sharpe:.2f} (vol-scaled) — qualification ratio "
            f"{ratio:.2f} has known structural bias"
        )

    # Improvement 3 — REMOVED (2026-06-18). The WF-Sharpe confidence-interval gate
    # (reject if `wf_sharpe - 1.96*sqrt((1 + 0.5*S^2)/n) <= 0`) was DEAD: it depends
    # on `wf_test_trades`, which is populated in 0/328 strategies, so it never fired.
    # It was also redundant with — and statistically WEAKER than — the upstream
    # WF-acceptance guards a pair has already passed before reaching graduation:
    #   (a) the Monte-Carlo bootstrap (p5 Sharpe >= 0.0 over 1000 resamples), a
    #       distribution-free significance test, vs this Lo(2002) closed form which
    #       assumes IID-normal returns (violated by skewed/fat-tailed trade P&L); and
    #       (b) the WF min-test-trade requirements (>=4 test trades / het gate).
    # Removed rather than wired so a real-money promotion path carries no dead,
    # weaker-duplicate safety theater. `wf_test_trades` is better surfaced as
    # informational metadata on the CIO graduation card than re-added as a hard gate.

    # Improvement 4: Alpha vs benchmark gate.
    # Reject if strategy underperformed SPY by more than 5% — clearly no alpha.
    if benchmark_return is not None and pnl is not None and trades > 0:
        # paper_return_pct: total P&L as a fraction of notional (flat size per trade).
        # Flat size is read from config (paper_trading.flat_position_size) — NOT
        # hardcoded — so this gate tracks the actual paper sizing (was a stale $5K
        # that understated return 5× after the 2026-06-15 cut to $1K).
        notional = trades * _get_paper_flat_size()
        paper_return_pct = pnl / notional if notional > 0 else None
        if paper_return_pct is not None:
            alpha = paper_return_pct - benchmark_return
            if alpha < -0.05:
                reasons.append(
                    f"alpha_vs_spy={alpha:.2%} < -5% "
                    f"(paper_return={paper_return_pct:.2%}, spy_return={benchmark_return:.2%})"
                )

    # Improvement 5: Deflated Sharpe Ratio gate.
    # DSR < 0.95 means the observed Sharpe is not statistically significant
    # after accounting for the number of strategies tested (multiple testing bias).
    # NOTE: This is currently informational only — with 7-15 paper trades and
    # 200+ trials, DSR will almost never reach 0.95. The gate is logged but
    # does NOT block graduation until we have sufficient paper trade history
    # (typically 30+ trades per strategy). The CIO sees DSR in the card.
    if n_trials is not None and sharpe is not None and sharpe > 0 and trades > 0:
        dsr = compute_dsr(sharpe, n_trials, trades)
        # Only enforce DSR gate when we have enough trades for it to be meaningful
        # (30+ trades gives the formula enough observations to be reliable)
        if trades >= 30 and dsr < 0.95:
            reasons.append(
                f"DSR={dsr:.2f} < 0.95 "
                f"(paper_sharpe={sharpe:.2f} not statistically significant "
                f"after {n_trials} trials)"
            )

    return len(reasons) == 0, reasons


def get_graduation_queue(session: Session) -> List[Dict[str, Any]]:
    """
    Return all (template_name, symbol) pairs that qualify for live trading.

    Groups by (template_name, symbol) across ALL strategy IDs — not just the
    currently-PAPER strategy. When a strategy retires and the same
    (template, symbol) pair is re-proposed, the new strategy_id gets a fresh
    UUID but the historical trade_journal rows from previous activations still
    count toward the graduation threshold. Grouping by strategy_id would reset
    the counter on every re-activation.

    Excludes:
    - Pairs already active in live_strategies (matched by template_name + symbol)
    - Pairs rejected in the last 14 days (matched by template_name + symbol)

    Performance: all per-candidate data (WF sharpe, SPY benchmark, correlation
    P&L series) is fetched in bulk SQL queries — no N+1 round-trips.
    Result is cached for 2 minutes (TTL_SECONDS) since it only changes when a
    paper trade closes or a graduation approval is recorded.
    """
    import time as _time
    _now = _time.time()
    _cache = getattr(get_graduation_queue, '_cache', None)
    if _cache and (_now - _cache[0]) < 120:  # 2-minute TTL
        return _cache[1]

    from src.models.orm import StrategyORM, GraduationApprovalORM, LiveStrategyORM
    from sqlalchemy import text

    # Active live pairs — exclude by (template_name, symbol)
    active_live = set(
        (row.template_name, row.symbol)
        for row in session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .all()
    )

    # Recently rejected pairs — exclude by (template_name, symbol)
    cooldown_cutoff = datetime.now() - timedelta(days=REJECTION_COOLDOWN_DAYS)
    recently_rejected = set(
        (row.template_name, row.symbol)
        for row in session.query(GraduationApprovalORM)
        .filter(
            GraduationApprovalORM.rejected_at.isnot(None),
            GraduationApprovalORM.rejected_at >= cooldown_cutoff,
        )
        .all()
    )

    # Single query: aggregate stats + representative strategy metadata + WF sharpe.
    # Pulls everything needed per candidate in one round-trip.
    # The wf_sharpe columns are extracted directly from strategy_metadata JSON
    # so we never need a per-candidate ORM fetch.
    candidates_raw = session.execute(
        text("""
            WITH pair_stats AS (
                SELECT
                    COALESCE(
                        s.strategy_metadata->>'template_name',
                        REGEXP_REPLACE(s.name, ' V[0-9]+$', ''),
                        tj.trade_metadata->>'template_name'
                    )                                                   AS template_name,
                    tj.symbol,
                    COUNT(*)                                            AS trades,
                    ROUND(
                        CASE WHEN STDDEV(tj.pnl) > 0
                             THEN (AVG(tj.pnl) / STDDEV(tj.pnl)) * SQRT(252)
                             ELSE 0
                        END::numeric, 4
                    )                                                   AS paper_sharpe,
                    ROUND(
                        100.0 * SUM(CASE WHEN tj.pnl > 0 THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)::numeric, 2
                    )                                                   AS win_rate_pct,
                    ROUND(COALESCE(SUM(tj.pnl), 0)::numeric, 2)        AS total_pnl,
                    ROUND(COALESCE(AVG(tj.pnl), 0)::numeric, 4)        AS avg_pnl,
                    COUNT(DISTINCT tj.strategy_id)                      AS strategy_versions,
                    MIN(tj.entry_time)                                  AS first_trade_at
                -- LEFT JOIN (not INNER): a (template, symbol) pair's trade history
                -- must survive deletion of old strategy VERSIONS. The BACKTESTED TTL
                -- deletes stale strategy rows, but their trade_journal rows persist —
                -- and the graduation gate is DESIGNED to count them across versions
                -- (see this function's docstring). An INNER JOIN silently dropped every
                -- orphaned-version trade (~63% of demo trades on 2026-06-18), so a pair
                -- that traded 18× across 3 versions could show as 5. We LEFT JOIN and
                -- recover the template from trade_metadata (verified 100% consistent with
                -- the strategies form) so deleted-version trades aggregate to their pair.
                FROM trade_journal tj
                LEFT JOIN strategies s ON s.id = tj.strategy_id
                WHERE tj.pnl IS NOT NULL
                  AND tj.account_type = 'demo'
                  AND (tj.exit_reason IS NULL OR tj.exit_reason != 'etoro_closed')
                  AND COALESCE(
                        s.strategy_metadata->>'template_name',
                        REGEXP_REPLACE(s.name, ' V[0-9]+$', ''),
                        tj.trade_metadata->>'template_name'
                      ) IS NOT NULL
                GROUP BY template_name, tj.symbol
                HAVING COUNT(*) >= :min_trades
            ),
            -- Representative SURVIVING strategy per (template, symbol), taken from the
            -- strategies table (NOT via trade_journal). The old version joined through
            -- trade_journal, so it could only pick a rep that had its OWN trades — but a
            -- re-proposed / retired-from-live pair's surviving version usually has NO new
            -- trades yet (all history is under now-deleted versions). That left such a
            -- pair with no representative and silently dropped it from the queue, so e.g.
            -- GOOGL (retired from live; 19 trades of aggregate history; a surviving
            -- BACKTESTED version with 0 trades of its own) could NEVER re-graduate even
            -- when fresh paper stats supported it. Selecting the rep from `strategies`
            -- (most-recent surviving version of that template holding that symbol) fixes
            -- re-graduation. symbols is unnested so multi-symbol strategies represent each
            -- of their symbols. retired-from-LIVE pairs are excluded later via active_live
            -- (retired_at IS NULL) — a retired live pair's source strategy reverts to
            -- PAPER/BACKTESTED (see live.retire_live_strategy) so it IS eligible here.
            latest_strategy AS (
                SELECT DISTINCT ON (
                    COALESCE(s.strategy_metadata->>'template_name', REGEXP_REPLACE(s.name, ' V[0-9]+$', '')),
                    sym.symbol
                )
                    COALESCE(
                        s.strategy_metadata->>'template_name',
                        REGEXP_REPLACE(s.name, ' V[0-9]+$', '')
                    )                                                   AS template_name,
                    sym.symbol                                          AS symbol,
                    s.id                                                AS strategy_id,
                    s.name                                              AS strategy_name,
                    COALESCE(
                        s.strategy_metadata->>'interval',
                        s.rules->>'interval'
                    )                                                   AS strategy_interval,
                    COALESCE(
                        s.strategy_metadata->>'template_type',
                        s.strategy_metadata->>'strategy_type'
                    )                                                   AS strategy_type,
                    -- WF sharpe pulled directly from JSON — eliminates per-candidate ORM fetch
                    COALESCE(
                        (s.strategy_metadata->>'wf_test_sharpe')::float,
                        (s.strategy_metadata->>'wf_sharpe')::float,
                        (s.strategy_metadata->>'walk_forward_sharpe')::float
                    )                                                   AS wf_sharpe,
                    (s.strategy_metadata->>'wf_test_trades')::int       AS wf_test_trades
                FROM strategies s
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    CASE WHEN jsonb_typeof(s.symbols::jsonb) = 'array'
                         THEN s.symbols::jsonb ELSE '[]'::jsonb END
                ) AS sym(symbol)
                WHERE s.status IN ('PAPER', 'BACKTESTED', 'LIVE')
                ORDER BY
                    COALESCE(s.strategy_metadata->>'template_name', REGEXP_REPLACE(s.name, ' V[0-9]+$', '')),
                    sym.symbol,
                    s.created_at DESC
            )
            SELECT
                ps.template_name,
                ps.symbol,
                ls.strategy_id  AS representative_strategy_id,
                ls.strategy_name,
                ls.strategy_interval,
                ls.strategy_type AS sql_strategy_type,
                ls.wf_sharpe,
                ls.wf_test_trades,
                ps.trades,
                ps.paper_sharpe,
                ps.win_rate_pct,
                ps.total_pnl,
                ps.avg_pnl,
                ps.strategy_versions,
                ps.first_trade_at
            FROM pair_stats ps
            JOIN latest_strategy ls
              ON ls.template_name = ps.template_name
             AND ls.symbol        = ps.symbol
        """),
        {"min_trades": _get_min_sql_having_trades()},
    ).fetchall()

    queue = []

    # ── Bulk query 1: best WF sharpe per template (fallback when SQL CTE returns NULL) ──
    # The main CTE already pulls wf_sharpe from the representative strategy's JSON.
    # This is a last-resort fallback for strategies where the JSON key is missing.
    best_wf_by_template: Dict[str, float] = {}
    try:
        _wf_rows = session.execute(
            text("""
                SELECT
                    COALESCE(
                        strategy_metadata->>'template_name',
                        REGEXP_REPLACE(name, ' V[0-9]+$', '')
                    )                                                   AS template_name,
                    MAX(
                        COALESCE(
                            (strategy_metadata->>'wf_test_sharpe')::float,
                            (strategy_metadata->>'wf_sharpe')::float,
                            (strategy_metadata->>'walk_forward_sharpe')::float,
                            0
                        )
                    )                                                   AS best_wf_sharpe
                FROM strategies
                WHERE strategy_metadata IS NOT NULL
                GROUP BY template_name
            """),
        ).fetchall()
        for r in _wf_rows:
            if r.template_name and r.best_wf_sharpe:
                v = float(r.best_wf_sharpe or 0)
                if v > best_wf_by_template.get(r.template_name, 0):
                    best_wf_by_template[r.template_name] = v
    except Exception:
        pass
    n_trials_global: Optional[int] = None
    try:
        _n_trials_row = session.execute(
            text("""
                SELECT COUNT(DISTINCT (
                    COALESCE(s.strategy_metadata->>'template_name', REGEXP_REPLACE(s.name, ' V[0-9]+$', '')),
                    sd.symbol
                )) AS n_trials
                FROM signal_decisions sd
                JOIN strategies s ON s.id = sd.strategy_id
                WHERE sd.stage = 'proposed'
                  AND sd.timestamp >= NOW() - INTERVAL '90 days'
            """),
        ).fetchone()
        if _n_trials_row and _n_trials_row.n_trials:
            n_trials_global = int(_n_trials_row.n_trials)
    except Exception as _nt_err:
        session.rollback()
        logger.debug(f"n_trials query failed: {_nt_err}")

    # Bulk query 3: SPY benchmark returns for all distinct first_trade_at dates.
    # One query instead of one per candidate. Maps date -> spy_return.
    spy_return_by_date: Dict[str, float] = {}
    try:
        _spy_dates = list({
            row.first_trade_at.date().isoformat()
            for row in candidates_raw
            if row.first_trade_at is not None
        })
        if _spy_dates:
            _spy_bulk = session.execute(
                text("""
                    SELECT
                        start_date,
                        -- PERIOD return (last close - first close)/first close over the
                        -- window, NOT peak-to-trough (MAX-MIN)/MIN. The old range form
                        -- overstated the benchmark (range >= |return|), making the alpha
                        -- gate reject pairs that did not actually underperform SPY.
                        ( (array_agg(close ORDER BY date DESC))[1]
                          - (array_agg(close ORDER BY date ASC))[1] )
                        / NULLIF((array_agg(close ORDER BY date ASC))[1], 0) AS spy_return
                    FROM (
                        SELECT
                            unnest(ARRAY[:dates]::date[]) AS start_date
                    ) dates
                    JOIN historical_price_cache hpc
                      ON hpc.symbol = 'SPY'
                     AND hpc.interval = '1d'
                     AND hpc.date >= dates.start_date
                    GROUP BY start_date
                """),
                {"dates": _spy_dates},
            ).fetchall()
            for r in _spy_bulk:
                if r.spy_return is not None:
                    spy_return_by_date[str(r.start_date)] = float(r.spy_return)
    except Exception as _spy_bulk_err:
        session.rollback()
        logger.debug(f"SPY bulk benchmark fetch failed: {_spy_bulk_err}")
    # Only fetched for candidates that pass is_qualified() — fetching all 1916
    # rows upfront to use 1 of them was the main remaining cold-call bottleneck.
    # We do a two-pass approach: first pass qualifies candidates, second pass
    # fetches P&L series only for the qualified set.
    candidate_pnl_by_pair: Dict[tuple, List[float]] = {}  # populated after qualification pass

    # ── Bulk query 5: live strategy P&L series for correlation ──
    live_pnl_series: Dict[tuple, Dict[str, Any]] = {}
    try:
        _live_rows = session.execute(
            text("""
                SELECT
                    ls.template_name,
                    ls.symbol,
                    tj.pnl
                FROM live_strategies ls
                JOIN trade_journal tj ON tj.strategy_id = ls.strategy_id
                WHERE ls.retired_at IS NULL
                  AND tj.pnl IS NOT NULL
                  AND tj.account_type = 'demo'
                  AND (tj.exit_reason IS NULL OR tj.exit_reason != 'etoro_closed')
                  AND tj.symbol = ls.symbol
                ORDER BY ls.template_name, ls.symbol, tj.entry_time
            """),
        ).fetchall()
        for r in _live_rows:
            key = (r.template_name, r.symbol)
            if key not in live_pnl_series:
                live_pnl_series[key] = {"template_name": r.template_name, "symbol": r.symbol, "pnl": []}
            live_pnl_series[key]["pnl"].append(float(r.pnl))
    except Exception as _live_corr_err:
        session.rollback()
        logger.debug(f"Live P&L series fetch failed: {_live_corr_err}")
    _effective_max_ratio = _get_regime_adjusted_max_ratio()

    # Pre-read YAML-backed values once — these helpers read the YAML file on
    # every call. With 66 candidates that's 66 file reads = ~4s of I/O.
    _min_avg_pnl = _get_min_avg_pnl_per_trade()

    # ── Pass 1: qualify candidates (no P&L series needed yet) ──
    qualified_candidates = []
    for row in candidates_raw:
        pair = (row.template_name, row.symbol)
        if pair in active_live or pair in recently_rejected:
            continue

        paper_stats = {
            "paper_trades": int(row.trades),
            "paper_sharpe": float(row.paper_sharpe) if row.paper_sharpe is not None else None,
            "paper_win_rate": float(row.win_rate_pct) / 100.0 if row.win_rate_pct is not None else None,
            "paper_total_pnl": float(row.total_pnl) if row.total_pnl is not None else None,
        }

        wf_sharpe: Optional[float] = float(row.wf_sharpe) if row.wf_sharpe is not None else None
        wf_test_trades: Optional[int] = int(row.wf_test_trades) if row.wf_test_trades is not None else None

        best_template_wf = best_wf_by_template.get(row.template_name, 0.0)
        if best_template_wf > 0 and not wf_sharpe:
            wf_sharpe = best_template_wf

        benchmark_return: Optional[float] = None
        if row.first_trade_at is not None:
            date_key = row.first_trade_at.date().isoformat()
            benchmark_return = spy_return_by_date.get(date_key)

        qualified, _ = is_qualified(
            paper_stats,
            wf_sharpe,
            interval=row.strategy_interval,
            strategy_type=row.sql_strategy_type,
            wf_test_trades=wf_test_trades,
            benchmark_return=benchmark_return,
            n_trials=n_trials_global,
            _precomputed_max_ratio=_effective_max_ratio,
            _precomputed_min_avg_pnl=_min_avg_pnl,
        )
        if qualified:
            qualified_candidates.append((row, paper_stats, wf_sharpe, wf_test_trades, benchmark_return))

    # ── Bulk query 4: P&L series only for qualified candidates ──
    # Typically 0-10 candidates qualify, so this is a tiny fetch.
    if qualified_candidates and live_pnl_series:
        qualified_pairs = [(r.template_name, r.symbol) for r, *_ in qualified_candidates]
        try:
            _cand_pnl_rows = session.execute(
                text("""
                    SELECT
                        COALESCE(
                            s.strategy_metadata->>'template_name',
                            REGEXP_REPLACE(s.name, ' V[0-9]+$', ''),
                            tj.trade_metadata->>'template_name'
                        )   AS template_name,
                        tj.symbol,
                        tj.pnl
                    FROM trade_journal tj
                    LEFT JOIN strategies s ON s.id = tj.strategy_id
                    WHERE tj.pnl IS NOT NULL
                      AND tj.account_type = 'demo'
                  AND (tj.exit_reason IS NULL OR tj.exit_reason != 'etoro_closed')
                      AND (
                          COALESCE(s.strategy_metadata->>'template_name', REGEXP_REPLACE(s.name, ' V[0-9]+$', ''), tj.trade_metadata->>'template_name'),
                          tj.symbol
                      ) = ANY(
                          SELECT (tname, sym)
                          FROM unnest(ARRAY[:tnames]::text[], ARRAY[:syms]::text[]) AS t(tname, sym)
                      )
                    ORDER BY template_name, tj.symbol, tj.entry_time
                """),
                {
                    "tnames": [p[0] for p in qualified_pairs],
                    "syms": [p[1] for p in qualified_pairs],
                },
            ).fetchall()
            for r in _cand_pnl_rows:
                key = (r.template_name, r.symbol)
                if key not in candidate_pnl_by_pair:
                    candidate_pnl_by_pair[key] = []
                candidate_pnl_by_pair[key].append(float(r.pnl))
        except Exception as _cand_pnl_err:
            session.rollback()
            logger.debug(f"Qualified candidate P&L fetch failed: {_cand_pnl_err}")

    # ── Pass 2: build queue entries for qualified candidates ──
    for row, paper_stats, wf_sharpe, wf_test_trades, benchmark_return in qualified_candidates:
        pair = (row.template_name, row.symbol)
        representative_id = row.representative_strategy_id
        strategy_interval = row.strategy_interval
        strategy_type = row.sql_strategy_type
        strategy_name = row.strategy_name or row.template_name

        ratio = None
        if wf_sharpe and wf_sharpe > 0 and paper_stats["paper_sharpe"] is not None:
            ratio = round(paper_stats["paper_sharpe"] / wf_sharpe, 3)

        avg_pnl_per_trade = float(row.avg_pnl) if row.avg_pnl is not None else None

        alpha_vs_spy: Optional[float] = None
        if benchmark_return is not None and paper_stats["paper_total_pnl"] is not None and paper_stats["paper_trades"] > 0:
            notional = paper_stats["paper_trades"] * _get_paper_flat_size()
            paper_return_pct = paper_stats["paper_total_pnl"] / notional if notional > 0 else None
            if paper_return_pct is not None:
                alpha_vs_spy = round(paper_return_pct - benchmark_return, 4)

        dsr: Optional[float] = None
        if n_trials_global is not None and paper_stats["paper_sharpe"] is not None and paper_stats["paper_sharpe"] > 0 and paper_stats["paper_trades"] > 0:
            dsr = round(compute_dsr(paper_stats["paper_sharpe"], n_trials_global, paper_stats["paper_trades"]), 4)

        correlation_with_live: List[Dict[str, Any]] = []
        candidate_pnl = candidate_pnl_by_pair.get(pair, [])
        for live_key, live_data in live_pnl_series.items():
            live_pnl = live_data["pnl"]
            n = min(len(candidate_pnl), len(live_pnl))
            if n < 5:
                corr = None
            else:
                a = candidate_pnl[:n]
                b = live_pnl[:n]
                mean_a = sum(a) / n
                mean_b = sum(b) / n
                cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
                std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
                std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b))
                corr = round(cov / (std_a * std_b), 4) if std_a > 0 and std_b > 0 else None
            correlation_with_live.append({
                "strategy_name": live_data["template_name"],
                "symbol": live_data["symbol"],
                "correlation": corr,
                "warning": corr is not None and corr > 0.65,
            })

        queue.append({
            "strategy_id": representative_id,
            "strategy_name": strategy_name,
            "template_name": row.template_name,
            "symbol": row.symbol,
            "paper_trades": paper_stats["paper_trades"],
            "paper_sharpe": paper_stats["paper_sharpe"],
            "paper_win_rate": paper_stats["paper_win_rate"],
            "paper_total_pnl": paper_stats["paper_total_pnl"],
            "avg_paper_pnl_per_trade": avg_pnl_per_trade,
            "wf_sharpe": wf_sharpe,
            "qualification_ratio": ratio,
            "strategy_versions": int(row.strategy_versions),
            "strategy_interval": strategy_interval,
            "first_paper_trade": row.first_trade_at.isoformat() if row.first_trade_at else None,
            "wf_test_trades": wf_test_trades,
            "benchmark_return": round(benchmark_return, 4) if benchmark_return is not None else None,
            "alpha_vs_spy": alpha_vs_spy,
            "dsr": dsr,
            "n_trials": n_trials_global,
            "correlation_with_live": correlation_with_live if correlation_with_live else None,
        })

    # Sort by qualification_ratio desc (best candidates first)
    queue.sort(key=lambda x: x.get("qualification_ratio") or 0, reverse=True)

    # Cache result for 2 minutes — invalidated by approve_graduation / reject_graduation
    get_graduation_queue._cache = (_time.time(), queue)
    return queue


def approve_graduation(
    session: Session,
    strategy_id: str,
    symbol: str,
    position_size: float,
    sl_pct: float,
    tp_pct: float,
    conviction_min: int,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Approve a (strategy, symbol) pair for live trading.

    Creates:
      1. A new StrategyORM row with status=LIVE, symbols=[symbol] — the live
         strategy is a separate entity from the source PAPER/BACKTESTED strategy.
         The source strategy is NOT mutated and continues generating DEMO trades.
      2. A graduation_approvals row recording the approval snapshot.
      3. A live_strategies row pointing at the new LIVE strategy_id.

    The new LIVE strategy carries over the template rules, risk params, and WF
    metadata from the source strategy, plus a `parent_strategy_id` reference so
    the full lineage is traceable.

    Returns the created live_strategies record as a dict.
    """
    import uuid
    import json
    from src.models.orm import StrategyORM, GraduationApprovalORM, LiveStrategyORM
    from src.models.enums import StrategyStatus

    source = session.query(StrategyORM).filter_by(id=strategy_id).first()
    if not source:
        raise ValueError(f"Strategy {strategy_id} not found")

    meta = source.strategy_metadata or {}
    template_name = meta.get("template_name") or source.name
    wf_sharpe = (
        meta.get("wf_test_sharpe")
        or meta.get("wf_sharpe")
        or meta.get("walk_forward_sharpe")
        or (source.backtest_results or {}).get("walk_forward_results", {}).get("test_sharpe")
    )

    # NEW-05: Validate that the proposed SL/TP are appropriate for the asset class.
    # The CIO can approve any SL, but if it exceeds the asset-class default by more
    # than 20% headroom, warn and cap it. This prevents stock-default SL (6%) being
    # applied to commodities (4% max) or forex (2% max).
    try:
        from src.core.tradeable_instruments import (
            DEMO_ALLOWED_COMMODITIES, DEMO_ALLOWED_FOREX,
            DEMO_ALLOWED_CRYPTO, DEMO_ALLOWED_INDICES, DEMO_ALLOWED_ETFS,
        )
        _sym_u = symbol.upper()
        _asset_sl_defaults = {
            "commodity": 0.04,
            "forex": 0.02,
            "crypto": 0.08,
            "index": 0.05,
            "etf": 0.06,
            "stock": 0.09,  # hard cap for stocks
        }
        if _sym_u in set(DEMO_ALLOWED_COMMODITIES):
            _asset_class_g = "commodity"
        elif _sym_u in set(DEMO_ALLOWED_FOREX):
            _asset_class_g = "forex"
        elif _sym_u in set(DEMO_ALLOWED_CRYPTO):
            _asset_class_g = "crypto"
        elif _sym_u in set(DEMO_ALLOWED_INDICES):
            _asset_class_g = "index"
        elif _sym_u in set(DEMO_ALLOWED_ETFS):
            _asset_class_g = "etf"
        else:
            _asset_class_g = "stock"

        _max_sl = _asset_sl_defaults.get(_asset_class_g, 0.09) * 1.20  # 20% headroom
        if sl_pct > _max_sl:
            logger.warning(
                f"[NEW-05] Graduation SL cap: {symbol} ({_asset_class_g}) — "
                f"proposed SL {sl_pct:.1%} > asset-class max {_max_sl:.1%}. "
                f"Capping at {_max_sl:.1%}."
            )
            sl_pct = round(_max_sl, 4)
            # Preserve R:R ratio
            _original_rr = tp_pct / sl_pct if sl_pct > 0 else 2.5
            tp_pct = round(sl_pct * _original_rr, 4)
    except Exception as _asc_err:
        logger.debug(f"Asset-class SL validation failed for {symbol}: {_asc_err}")

    # Aggregated cross-version paper stats for the approval snapshot.
    paper_stats = get_aggregated_paper_stats(session, template_name, symbol)
    if not paper_stats.get("paper_trades"):
        paper_stats = get_paper_stats_for_strategy(session, strategy_id, symbol)
    ratio = None
    if wf_sharpe and wf_sharpe > 0 and paper_stats["paper_sharpe"] is not None:
        ratio = round(paper_stats["paper_sharpe"] / wf_sharpe, 3)

    # Check not already active — scope to template+symbol, not strategy_id,
    # so re-graduation after retirement is caught correctly.
    existing = (
        session.query(LiveStrategyORM)
        .filter_by(template_name=template_name, symbol=symbol)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .first()
    )
    if existing:
        raise ValueError(f"({template_name}, {symbol}) is already active in live_strategies")

    now = datetime.now()

    # ── 1. Create the LIVE strategy row ──────────────────────────────────────
    # Inherits rules and risk params from the source strategy.
    # symbols is scoped to the single approved symbol — a live strategy trades
    # exactly one symbol, not the full paper watchlist.
    live_meta = dict(meta)  # copy source metadata
    live_meta["parent_strategy_id"] = strategy_id   # lineage reference
    live_meta["graduated_from"] = source.name
    live_meta["graduated_at"] = now.isoformat()
    live_meta["activation_approved"] = True
    # Override risk params with CIO-approved values
    live_meta["live_position_size"] = position_size
    live_meta["live_sl_pct"] = sl_pct
    live_meta["live_tp_pct"] = tp_pct
    live_meta["live_conviction_min"] = conviction_min

    # Build risk_params for the live strategy using CIO-approved SL/TP
    live_risk_params = dict(source.risk_params or {})
    live_risk_params["stop_loss_pct"] = sl_pct
    live_risk_params["take_profit_pct"] = tp_pct

    live_strategy_id = str(uuid.uuid4())
    live_strategy = StrategyORM(
        id=live_strategy_id,
        name=f"{template_name} {symbol} LIVE",
        description=f"Live strategy — graduated from {source.name} on {now.date()}",
        status=StrategyStatus.LIVE,
        rules=source.rules,
        symbols=json.dumps([symbol]) if isinstance(source.symbols, str) else [symbol],
        allocation_percent=source.allocation_percent or 0.0,
        risk_params=live_risk_params,
        created_at=now,
        activated_at=now,
        performance={"total_return": 0.0, "sharpe_ratio": 0.0, "sortino_ratio": 0.0,
                     "max_drawdown": 0.0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                     "total_trades": 0},
        reasoning=source.reasoning,
        backtest_results=source.backtest_results,
        strategy_metadata=live_meta,
    )
    session.add(live_strategy)

    # ── 2. Record approval snapshot ──────────────────────────────────────────
    approval = GraduationApprovalORM(
        strategy_id=live_strategy_id,   # points at the new LIVE strategy
        symbol=symbol,
        template_name=template_name,
        approved_at=now,
        notes=notes,
        position_size_override=position_size,
        sl_pct_override=sl_pct,
        tp_pct_override=tp_pct,
        conviction_min_override=conviction_min,
        paper_trades=paper_stats.get("paper_trades"),
        paper_sharpe=paper_stats.get("paper_sharpe"),
        paper_win_rate=paper_stats.get("paper_win_rate"),
        paper_total_pnl=paper_stats.get("paper_total_pnl"),
        wf_sharpe=wf_sharpe,
        qualification_ratio=ratio,
        created_at=now,
    )
    session.add(approval)
    session.flush()  # get approval.id

    # ── 3. Create live authorization row ─────────────────────────────────────
    live_row = LiveStrategyORM(
        graduation_id=approval.id,
        strategy_id=live_strategy_id,   # the new LIVE strategy, not the source
        template_name=template_name,
        symbol=symbol,
        activated_at=now,
        position_size=position_size,
        sl_pct=sl_pct,
        tp_pct=tp_pct,
        conviction_min=conviction_min,
    )
    session.add(live_row)
    session.commit()

    logger.info(
        f"GRADUATION APPROVED: ({template_name}, {symbol}) → "
        f"new LIVE strategy {live_strategy_id[:8]} | "
        f"source={strategy_id[:8]} (continues as PAPER/BACKTESTED) | "
        f"live_strategies id={live_row.id} "
        f"size=${position_size} sl={sl_pct*100:.1f}% tp={tp_pct*100:.1f}% "
        f"conviction_min={conviction_min}"
    )
    # Invalidate the graduation queue cache so the next request reflects the approval.
    get_graduation_queue._cache = None
    return live_row.to_dict()


def reject_graduation(
    session: Session,
    strategy_id: str,
    symbol: str,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reject a (strategy, symbol) pair with a 14-day cooldown.
    """
    from src.models.orm import StrategyORM, GraduationApprovalORM

    strategy = session.query(StrategyORM).filter_by(id=strategy_id).first()
    template_name = (strategy.strategy_metadata or {}).get("template_name") or (strategy.name if strategy else strategy_id)

    now = datetime.now()
    rejection = GraduationApprovalORM(
        strategy_id=strategy_id,
        symbol=symbol,
        template_name=template_name,
        rejected_at=now,
        notes=notes,
        created_at=now,
    )
    session.add(rejection)
    session.commit()

    logger.info(f"GRADUATION REJECTED: ({template_name}, {symbol}) — cooldown until {(now + timedelta(days=REJECTION_COOLDOWN_DAYS)).date()}")
    # Invalidate the graduation queue cache so the next request reflects the rejection.
    get_graduation_queue._cache = None
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "rejected_at": now.isoformat(),
        "cooldown_until": (now + timedelta(days=REJECTION_COOLDOWN_DAYS)).isoformat(),
        "notes": notes,
    }


def get_live_strategies(session: Session) -> List[Dict[str, Any]]:
    """Return all active live_strategies rows with paper stats for comparison."""
    from src.models.orm import LiveStrategyORM, StrategyORM, PositionORM

    rows = (
        session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .order_by(LiveStrategyORM.activated_at.desc())
        .all()
    )

    result = []
    for row in rows:
        d = row.to_dict()
        # Use cross-version aggregated stats (same as graduation queue) so the
        # paper Sharpe reflects the full (template, symbol) history, not just
        # the single strategy_id that happens to be the representative version.
        paper = get_aggregated_paper_stats(session, row.template_name, row.symbol)
        if not paper.get("paper_trades"):
            # Fallback: single-strategy stats if aggregation returns nothing
            paper = get_paper_stats_for_strategy(session, row.strategy_id, row.symbol)
        d["current_paper_sharpe"] = paper.get("paper_sharpe")
        d["current_paper_win_rate"] = paper.get("paper_win_rate")
        d["current_paper_pnl"] = paper.get("paper_total_pnl")
        d["current_paper_trades"] = paper.get("paper_trades")

        # Add unrealized P&L from open live positions so the UI shows current
        # exposure even before the first trade closes (live_trades=0 / live_pnl=0).
        try:
            open_pos = session.query(PositionORM).filter(
                PositionORM.strategy_id == row.strategy_id,
                PositionORM.account_type == 'live',
                PositionORM.closed_at.is_(None),
            ).all()
            d["open_position_count"] = len(open_pos)
            d["unrealized_pnl"] = round(
                sum(float(p.unrealized_pnl or 0) for p in open_pos), 2
            )
            d["open_position_entry"] = float(open_pos[0].entry_price) if open_pos else None
            d["open_position_current"] = float(open_pos[0].current_price) if open_pos else None
        except Exception:
            d["open_position_count"] = 0
            d["unrealized_pnl"] = 0.0
            d["open_position_entry"] = None
            d["open_position_current"] = None

        # Add last signal cycle outcome for this live strategy
        try:
            from src.models.orm import OrderORM, SignalDecisionORM
            from src.models.enums import OrderStatus

            # eToro status code labels
            _ETORO_STATUS = {
                1: "Pending",
                2: "Filled",
                3: "Executed",
                4: "Failed/Rejected",
                7: "Active",
                11: "Pending Execution",
            }

            # Check for pending orders first
            pending = session.query(OrderORM).filter(
                OrderORM.strategy_id == row.strategy_id,
                OrderORM.account_type == 'live',
                OrderORM.status == OrderStatus.PENDING,
            ).order_by(OrderORM.submitted_at.desc()).first()

            if pending:
                submitted_str = pending.submitted_at.strftime('%H:%M UTC') if pending.submitted_at else '—'
                age_mins = int((datetime.now() - pending.submitted_at).total_seconds() / 60) if pending.submitted_at else 0
                age_str = f"{age_mins}m" if age_mins < 60 else f"{age_mins // 60}h {age_mins % 60}m"

                # Try to get live eToro status for this order
                etoro_status_label = None
                etoro_units = None
                etoro_amount = None
                try:
                    if pending.etoro_order_id:
                        from src.data.market_data_manager import get_market_data_manager
                        from src.api.etoro_client import EToroAPIClient
                        from src.core.config import Configuration
                        from src.models.enums import TradingMode
                        cfg = Configuration()
                        creds = cfg.load_credentials(TradingMode.LIVE)
                        live_client = EToroAPIClient(
                            public_key=creds["public_key"],
                            user_key=creds["user_key"],
                            mode=TradingMode.LIVE,
                        )
                        order_data = live_client.get_order_status(str(pending.etoro_order_id))
                        status_id = order_data.get("statusID")
                        etoro_status_label = _ETORO_STATUS.get(status_id, f"Status {status_id}")
                        etoro_units = order_data.get("units")
                        etoro_amount = order_data.get("amount")
                except Exception:
                    pass  # fail-open — show basic info if eToro call fails

                d["last_signal_status"] = "order_pending"
                if etoro_status_label and etoro_units and etoro_amount:
                    d["last_signal_detail"] = (
                        f"eToro: {etoro_status_label} · "
                        f"${etoro_amount:.0f} · {etoro_units:.4f} units · "
                        f"submitted {submitted_str} ({age_str} ago)"
                    )
                else:
                    d["last_signal_detail"] = f"Order pending since {submitted_str} ({age_str} ago)"
                # Store structured data for richer UI
                d["pending_order"] = {
                    "order_id": str(pending.id),
                    "etoro_order_id": str(pending.etoro_order_id) if pending.etoro_order_id else None,
                    "submitted_at": pending.submitted_at.isoformat() if pending.submitted_at else None,
                    "quantity": float(pending.quantity) if pending.quantity else None,
                    "etoro_status": etoro_status_label,
                    "etoro_units": etoro_units,
                    "etoro_amount": etoro_amount,
                    "age_mins": age_mins,
                }
            else:
                # Get last signal_decisions row for this strategy
                last_sd = session.execute(
                    __import__('sqlalchemy').text("""
                        SELECT stage, decision, reason, score, timestamp
                        FROM signal_decisions
                        WHERE strategy_id = :sid
                        ORDER BY timestamp DESC LIMIT 1
                    """),
                    {"sid": row.strategy_id}
                ).fetchone()

                if last_sd:
                    age_mins = int((datetime.now() - last_sd.timestamp).total_seconds() / 60)
                    age_str = f"{age_mins}m ago" if age_mins < 60 else f"{age_mins // 60}h ago"
                    if last_sd.stage == "order_submitted":
                        d["last_signal_status"] = "order_submitted"
                        d["last_signal_detail"] = f"Order submitted {age_str}"
                    elif last_sd.stage == "signal_emitted" and last_sd.decision == "rejected":
                        reason = last_sd.reason or ""
                        if "conviction" in reason.lower():
                            d["last_signal_status"] = "blocked_conviction"
                            score = f" (score {last_sd.score:.1f})" if last_sd.score else ""
                            d["last_signal_detail"] = f"Blocked: conviction{score} {age_str}"
                        elif "frequency" in reason.lower():
                            d["last_signal_status"] = "blocked_frequency"
                            d["last_signal_detail"] = f"Blocked: frequency limit {age_str}"
                        else:
                            d["last_signal_status"] = "blocked"
                            d["last_signal_detail"] = f"Blocked: {reason[:40]} {age_str}"
                    elif last_sd.stage == "gate_blocked":
                        d["last_signal_status"] = "gate_blocked"
                        # Surface the ACTUAL block reason (was a bare "Gate blocked")
                        # so the CIO can see WHY without digging into signal_decisions —
                        # e.g. "Position would exceed max position size limit of 15.0%"
                        # (per-symbol concentration cap), conviction, VIX/trend gate, etc.
                        _gb_reason = (last_sd.reason or "").strip()
                        for _pfx in ("validate_signal: ", "validate_signal "):
                            if _gb_reason.lower().startswith(_pfx.lower()):
                                _gb_reason = _gb_reason[len(_pfx):].strip()
                                break
                        if _gb_reason:
                            d["last_signal_detail"] = f"Gate blocked: {_gb_reason[:110]} ({age_str})"
                        else:
                            d["last_signal_detail"] = f"Gate blocked {age_str}"
                    elif last_sd.stage == "signal_emitted":
                        d["last_signal_status"] = "signal_emitted"
                        d["last_signal_detail"] = f"Signal emitted {age_str}"
                    else:
                        d["last_signal_status"] = last_sd.stage
                        d["last_signal_detail"] = f"{last_sd.stage} {age_str}"
                else:
                    d["last_signal_status"] = "no_signal_yet"
                    d["last_signal_detail"] = "No signal generated yet"
        except Exception:
            d["last_signal_status"] = None
            d["last_signal_detail"] = None

        # Divergence: live_sharpe vs paper_sharpe
        if row.live_sharpe and paper.get("paper_sharpe") and paper["paper_sharpe"] > 0:
            d["divergence_pct"] = round(row.live_sharpe / paper["paper_sharpe"] * 100, 1)
        else:
            d["divergence_pct"] = None

        # Live trade history from trade_journal — gives closed trade breakdown,
        # win rate, avg P&L, last opened/closed, and individual trade rows.
        try:
            from sqlalchemy import text as _text
            live_tj = session.execute(
                _text("""
                    SELECT id, entry_price, exit_price, pnl, pnl_percent,
                           entry_time, exit_time, hold_time_hours, exit_reason
                    FROM trade_journal
                    WHERE strategy_id = :sid AND symbol = :sym
                      AND account_type = 'live'
                    ORDER BY entry_time DESC
                    LIMIT 20
                """),
                {"sid": row.strategy_id, "sym": row.symbol},
            ).fetchall()

            closed_trades = [t for t in live_tj if t.exit_time is not None]
            open_trades   = [t for t in live_tj if t.exit_time is None]

            wins   = [t for t in closed_trades if t.pnl is not None and t.pnl > 0]
            losses = [t for t in closed_trades if t.pnl is not None and t.pnl < 0]
            realized_pnl = sum(float(t.pnl) for t in closed_trades if t.pnl is not None)
            avg_pnl = realized_pnl / len(closed_trades) if closed_trades else None
            win_rate = len(wins) / len(closed_trades) * 100 if closed_trades else None
            best  = max((float(t.pnl) for t in closed_trades if t.pnl is not None), default=None)
            worst = min((float(t.pnl) for t in closed_trades if t.pnl is not None), default=None)
            avg_hold = (
                sum(float(t.hold_time_hours) for t in closed_trades if t.hold_time_hours is not None)
                / len([t for t in closed_trades if t.hold_time_hours is not None])
                if any(t.hold_time_hours for t in closed_trades) else None
            )
            last_opened = live_tj[0].entry_time.isoformat() if live_tj else None
            last_closed = (
                max((t.exit_time for t in closed_trades), default=None)
            )

            d["live_closed_trades"]  = len(closed_trades)
            d["live_open_trades"]    = len(open_trades)
            d["live_realized_pnl"]   = round(realized_pnl, 2)
            d["live_win_rate"]       = round(win_rate, 1) if win_rate is not None else None
            d["live_avg_pnl"]        = round(avg_pnl, 2) if avg_pnl is not None else None
            d["live_best_trade"]     = round(best, 2) if best is not None else None
            d["live_worst_trade"]    = round(worst, 2) if worst is not None else None
            d["live_avg_hold_hours"] = round(avg_hold, 1) if avg_hold is not None else None
            d["live_last_opened"]    = last_opened
            d["live_last_closed"]    = last_closed.isoformat() if last_closed else None
            d["live_trade_history"]  = [
                {
                    "id": str(t.id),
                    "entry_price": float(t.entry_price) if t.entry_price else None,
                    "exit_price":  float(t.exit_price)  if t.exit_price  else None,
                    "pnl":         float(t.pnl)          if t.pnl         else None,
                    "pnl_percent": float(t.pnl_percent)  if t.pnl_percent else None,
                    "entry_time":  t.entry_time.isoformat() if t.entry_time else None,
                    "exit_time":   t.exit_time.isoformat()  if t.exit_time  else None,
                    "hold_time_hours": float(t.hold_time_hours) if t.hold_time_hours else None,
                    "exit_reason": t.exit_reason,
                    "is_open":     t.exit_time is None,
                }
                for t in live_tj
            ]
        except Exception as _tj_err:
            logger.debug(f"Could not fetch live trade journal for {row.strategy_id}: {_tj_err}")
            d["live_closed_trades"]  = None
            d["live_open_trades"]    = None
            d["live_realized_pnl"]   = None
            d["live_win_rate"]       = None
            d["live_avg_pnl"]        = None
            d["live_best_trade"]     = None
            d["live_worst_trade"]    = None
            d["live_avg_hold_hours"] = None
            d["live_last_opened"]    = None
            d["live_last_closed"]    = None
            d["live_trade_history"]  = []

        result.append(d)

    return result


def get_live_approval(
    session: Session,
    strategy_id: str,
    symbol: str,
) -> Optional[Any]:
    """
    Return the active LiveStrategyORM row for (strategy_id, symbol), or None.

    Used by TradingScheduler to check whether a live fill is authorized.
    """
    from src.models.orm import LiveStrategyORM

    return (
        session.query(LiveStrategyORM)
        .filter_by(strategy_id=strategy_id, symbol=symbol)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .first()
    )


def get_all_live_approvals(session: Session) -> list:
    """
    Return all active LiveStrategyORM rows (retired_at IS NULL).

    Used by TradingScheduler's live-independent signal pass to iterate over
    every authorized (strategy, symbol) pair and fire live entries independently
    of the DEMO signal path.
    """
    from src.models.orm import LiveStrategyORM

    return (
        session.query(LiveStrategyORM)
        .filter(LiveStrategyORM.retired_at.is_(None))
        .all()
    )
