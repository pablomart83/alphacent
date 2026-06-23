"""
Meta-label trainer — the learn-from-trades engine (Tier 1, Path B).

Trains a per-asset-class meta-label model that predicts, for a *candidate
signal the strategy already wants to take*, the probability that the trade
will be COST-NET profitable. This is "meta-labeling" (López de Prado): the
primary model is the strategy/DSL signal; the secondary (meta) model decides
whether to act on it and how big.

Design contract (see trading-system-context.md + the Tier-1 brief):

- **Prove-first.** This module trains and self-validates with PURGED +
  EMBARGOED walk-forward CV. It writes per-asset-class models to
  `models/ml/meta_label_<asset_class>.pkl` plus a metrics record. It NEVER
  wires itself into the trading hot path — inference and the
  (filter, asset_class, account) state machine live elsewhere and only act in
  shadow/enforce once the shadow evidence bar is met.

- **Train/serve parity.** Feature construction is a single pure function
  (`build_feature_row`) used by BOTH training (context reconstructed from
  `trade_journal` + `trade_metadata`) and serving (context built from the live
  `TradingSignal` + conviction breakdown + market context). The exact feature
  order, categorical encodings and train-time medians (for imputation) are
  persisted inside the model artifact so serving cannot drift.

- **No leakage.** Every feature is knowable at decision time (entry). Realized
  outcomes (hold_time, exit_reason, pnl, MAE/MFE) are NEVER features — they
  only build the label. Purging removes train trades whose label window
  overlaps a test trade's; the embargo drops a tail after each test fold.

- **Unbiased training set.** Trains on ALL realized trades (PAPER never
  enforces, so the training sample is never self-selected by the filter).

The label is **cost-net profitable**: `pnl_percent/100 - round_trip_cost_pct`
> 0, with our own per-asset-class costs applied uniformly (so demo at-quote
fills are judged on the same honest cost basis as live).
"""

from __future__ import annotations

import json
import logging
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.core.symbol_registry import get_registry
from src.risk.sl_caps import is_leveraged_etf
from src.strategy.cost_model import round_trip_cost_pct

logger = logging.getLogger(__name__)

# Artifact / feature-spec version. Bump when FEATURE_ORDER or the encodings
# change so a stale serve-side artifact is detected rather than silently
# producing garbage.
#   ml1.0.0 — 22 decision-time features (conviction + breakdown + fundamentals)
#   ml1.1.0 — + 12 pre-entry price-history features (momentum/trend/vol/structure)
FEATURE_SPEC_VERSION = "ml1.1.0"

MODEL_DIR_DEFAULT = "models/ml"

# Minimum realized trades (with BOTH label classes present) before we will fit
# a model for an asset class. Below this the OOS estimate is noise — we leave
# the class without a model (disabled by construction).
MIN_CLASS_SAMPLES = 120
MIN_MINORITY_SAMPLES = 25  # need enough of the rarer class to learn anything

# ---------------------------------------------------------------------------
# Feature specification (train/serve parity)
# ---------------------------------------------------------------------------
# Fixed categorical encodings — persisted by reference (the code is the spec,
# pinned by FEATURE_SPEC_VERSION). Unknown values map to a neutral bucket.

_STRATEGY_TYPE_MAP = {
    "trend_following": 0,
    "momentum": 1,
    "breakout": 2,
    "mean_reversion": 3,
    "volatility": 4,
    "alpha_edge": 5,
}

_REGIME_FAMILY_MAP = {
    "trending_up": 0,
    "trending_down": 1,
    "ranging": 2,
    "high_volatility": 3,
}

_INTERVAL_MAP = {"1h": 0, "4h": 1, "1d": 2, "1w": 3}

# Ordered numeric feature names. The model is trained and served on a vector in
# exactly this order. Categorical features are pre-encoded to numerics above.
FEATURE_ORDER: List[str] = [
    "conviction_score",
    "cb_walkforward_edge",
    "cb_signal_quality",
    "cb_regime_fit",
    "cb_asset_tradability",
    "cb_fundamental_quality",
    "cb_news_sentiment",
    "cb_factor_exposure",
    "cb_carry_bias",
    "cb_crypto_cycle",
    "vix_level",
    "entry_persistence",
    "direction_long",
    "strategy_type_enc",
    "regime_enc",
    "interval_enc",
    "is_leveraged",
    "f_pe_ratio",
    "f_roe",
    "f_debt_to_equity",
    "f_revenue_growth",
    "f_earnings_surprise",
]

# Pre-entry price-history features (ml1.1.0). Computed from the ~60-bar OHLC
# window that ENDS at the entry bar (verified: last bar ≈ entry, no post-entry
# leakage). These describe the market structure the trade was entered into —
# momentum/trend/slope are SIGNED by trade direction (positive = the pre-entry
# move was favourable to the trade), while volatility/range/RSI are raw regime
# descriptors (the model also sees `direction_long`, so it can learn
# direction-specific behaviour of the raw ones). Every one is knowable at the
# entry decision, so there is no leakage.
PRICE_FEATURE_ORDER: List[str] = [
    "ph_n_bars",          # availability / sample-size signal (0 when no history)
    "ph_mom_5",           # signed return over last 5 bars
    "ph_mom_10",          # signed return over last 10 bars
    "ph_mom_20",          # signed return over last 20 bars
    "ph_dist_sma20",      # signed close-vs-SMA20 distance
    "ph_dist_sma50",      # signed close-vs-SMA50 distance
    "ph_sma_slope_10",    # signed slope of SMA10
    "ph_realized_vol_20", # stdev of last-20 close-to-close returns (unsigned)
    "ph_atr_pct_14",      # mean true-range / close over last 14 (unsigned)
    "ph_rsi_14",          # Wilder RSI(14) on closes (0-100, unsigned)
    "ph_range_pos_20",    # position in last-20 high/low range (0=low,1=high)
    "ph_gap_last",        # signed overnight gap into the entry bar
]

# The model trains and serves on conviction/fundamental features followed by
# the price-history block, in this exact concatenated order.
FEATURE_ORDER = FEATURE_ORDER + PRICE_FEATURE_ORDER


def _bar_val(bar: Any, key: str) -> float:
    """Read an OHLC field from a dict bar (train: trade_metadata) or an object
    bar (serve: MarketData). Returns NaN when absent/unparseable."""
    if isinstance(bar, dict):
        v = bar.get(key)
    else:
        v = getattr(bar, key, None)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def build_price_features(price_history: Any, is_long: bool) -> Dict[str, float]:
    """Pure pre-entry price-structure features — the price half of train/serve
    parity. `price_history` is an oldest→newest list of OHLC bars ending at the
    entry bar (dicts at train time, MarketData objects at serve time). `is_long`
    signs the directional features so "favourable pre-entry move" is always
    positive regardless of LONG/SHORT.

    Defensive by construction: a missing/short history yields NaN for the
    features it can't compute (imputed to the train median downstream) while
    still reporting `ph_n_bars`, so the model can learn from missingness.
    """
    nan = float("nan")
    feats: Dict[str, float] = {name: nan for name in PRICE_FEATURE_ORDER}

    bars = price_history if isinstance(price_history, (list, tuple)) else []
    closes = [c for c in (_bar_val(b, "close") for b in bars) if not np.isnan(c)]
    feats["ph_n_bars"] = float(len(closes))
    if len(closes) < 3:
        return feats

    highs = [_bar_val(b, "high") for b in bars]
    lows = [_bar_val(b, "low") for b in bars]
    opens = [_bar_val(b, "open") for b in bars]
    c = np.array(closes, dtype=float)
    n = len(c)
    sign = 1.0 if is_long else -1.0

    def mom(k: int) -> float:
        if n > k and c[-1 - k] > 0:
            return sign * (c[-1] / c[-1 - k] - 1.0)
        return nan

    feats["ph_mom_5"] = mom(5)
    feats["ph_mom_10"] = mom(10)
    feats["ph_mom_20"] = mom(20)

    def dist_sma(k: int) -> float:
        if n >= k:
            sma = float(np.mean(c[-k:]))
            if sma > 0:
                return sign * (c[-1] / sma - 1.0)
        return nan

    feats["ph_dist_sma20"] = dist_sma(20)
    feats["ph_dist_sma50"] = dist_sma(50)

    # SMA10 slope: SMA10 now vs SMA10 five bars ago.
    if n >= 15:
        sma_now = float(np.mean(c[-10:]))
        sma_prev = float(np.mean(c[-15:-5]))
        if sma_prev > 0:
            feats["ph_sma_slope_10"] = sign * (sma_now / sma_prev - 1.0)

    # Realized vol: stdev of last-20 close-to-close returns (unsigned).
    if n >= 6:
        rets = np.diff(c[-21:]) / c[-21:-1] if n >= 21 else np.diff(c) / c[:-1]
        rets = rets[np.isfinite(rets)]
        if len(rets) >= 3:
            feats["ph_realized_vol_20"] = float(np.std(rets, ddof=1))

    # ATR%: mean true range over last 14 bars / last close (unsigned).
    if n >= 2:
        tr_list: List[float] = []
        for i in range(1, n):
            hi, lo, pc = highs[i], lows[i], closes[i - 1]
            if any(np.isnan(x) for x in (hi, lo, pc)):
                continue
            tr_list.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
        if tr_list and c[-1] > 0:
            atr = float(np.mean(tr_list[-14:]))
            feats["ph_atr_pct_14"] = atr / c[-1]

    # Wilder RSI(14) on closes (unsigned, 0-100).
    if n >= 15:
        diffs = np.diff(c[-15:])
        gains = np.clip(diffs, 0, None)
        losses = -np.clip(diffs, None, 0)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss == 0:
            feats["ph_rsi_14"] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            feats["ph_rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

    # Position in the last-20 high/low range (0=at low, 1=at high; unsigned).
    if n >= 5:
        win_high = [highs[i] for i in range(max(0, n - 20), n) if not np.isnan(highs[i])]
        win_low = [lows[i] for i in range(max(0, n - 20), n) if not np.isnan(lows[i])]
        if win_high and win_low:
            hi, lo = max(win_high), min(win_low)
            if hi > lo:
                feats["ph_range_pos_20"] = (c[-1] - lo) / (hi - lo)

    # Overnight gap into the entry bar: (open_last - close_prev)/close_prev, signed.
    if n >= 2 and not np.isnan(opens[-1]) and closes[-2] > 0:
        feats["ph_gap_last"] = sign * ((opens[-1] - closes[-2]) / closes[-2])

    return feats


def _regime_family(regime: Optional[str]) -> Optional[str]:
    if not regime:
        return None
    r = regime.lower()
    if "trending_up" in r or r in ("bull", "uptrend"):
        return "trending_up"
    if "trending_down" in r or r in ("bear", "downtrend"):
        return "trending_down"
    if "high_vol" in r or "volatil" in r:
        return "high_volatility"
    if "ranging" in r or "range" in r or "sideways" in r:
        return "ranging"
    return None


def asset_class_of(symbol: str) -> str:
    """Canonical asset-class bucket for the meta-label models.

    Uses the symbol registry (authoritative). Leveraged ETFs are still 'etfs'
    for the model bucket (their leverage is a *feature*, `is_leveraged`), so
    the ETF model learns leverage as a dimension rather than splitting the
    already-small sample.
    """
    try:
        ac = (get_registry().get_asset_class(symbol) or "unknown").lower()
    except Exception:
        ac = "unknown"
    return ac


def build_feature_row(ctx: Dict[str, Any]) -> Dict[str, float]:
    """Pure feature builder — the single source of train/serve parity.

    `ctx` is a flat dict with the keys below. Missing keys become NaN and are
    imputed (median) downstream; categorical misses map to a neutral bucket.
    This function performs NO IO and reads NO global mutable state, so the
    exact same vector is produced at train time (from trade_journal) and serve
    time (from a live signal).
    """

    def num(key: str) -> float:
        v = ctx.get(key)
        if v is None:
            return float("nan")
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    direction = (ctx.get("direction") or "").lower()
    strategy_type = (ctx.get("strategy_type") or "").lower()
    regime_fam = _regime_family(ctx.get("market_regime"))
    interval = (ctx.get("interval") or "1d").lower()

    row: Dict[str, float] = {
        "conviction_score": num("conviction_score"),
        "cb_walkforward_edge": num("cb_walkforward_edge"),
        "cb_signal_quality": num("cb_signal_quality"),
        "cb_regime_fit": num("cb_regime_fit"),
        "cb_asset_tradability": num("cb_asset_tradability"),
        "cb_fundamental_quality": num("cb_fundamental_quality"),
        "cb_news_sentiment": num("cb_news_sentiment"),
        "cb_factor_exposure": num("cb_factor_exposure"),
        "cb_carry_bias": num("cb_carry_bias"),
        "cb_crypto_cycle": num("cb_crypto_cycle"),
        "vix_level": num("vix_level"),
        "entry_persistence": num("entry_persistence"),
        "direction_long": 1.0 if direction in ("long", "buy", "enter_long") else 0.0,
        "strategy_type_enc": float(_STRATEGY_TYPE_MAP.get(strategy_type, -1)),
        "regime_enc": float(_REGIME_FAMILY_MAP.get(regime_fam, -1)),
        "interval_enc": float(_INTERVAL_MAP.get(interval, 2)),  # default daily
        "is_leveraged": 1.0 if is_leveraged_etf(ctx.get("symbol", "") or "") else 0.0,
        "f_pe_ratio": num("f_pe_ratio"),
        "f_roe": num("f_roe"),
        "f_debt_to_equity": num("f_debt_to_equity"),
        "f_revenue_growth": num("f_revenue_growth"),
        "f_earnings_surprise": num("f_earnings_surprise"),
    }

    # Pre-entry price-history block (ml1.1.0). Signed by trade direction.
    is_long = direction in ("long", "buy", "enter_long")
    row.update(build_price_features(ctx.get("price_history"), is_long))
    return row


def ctx_from_trade(row: Dict[str, Any]) -> Dict[str, Any]:
    """Reconstruct a decision-time feature context from a trade_journal row.

    `row` is a dict of trade_journal columns (already JSON-decoded
    trade_metadata under key 'trade_metadata'). Pulls ONLY decision-time data;
    realized outcomes are ignored here.
    """
    md = row.get("trade_metadata") or {}
    if isinstance(md, str):
        try:
            md = json.loads(md)
        except (ValueError, TypeError):
            md = {}

    cb = md.get("conviction_breakdown") or {}

    def cb_score(key: str) -> Optional[float]:
        node = cb.get(key)
        if isinstance(node, dict):
            return node.get("score")
        return None

    # vix lives in regime_fit.details.vix_level
    vix = None
    rf = cb.get("regime_fit")
    if isinstance(rf, dict):
        vix = (rf.get("details") or {}).get("vix_level")

    fund = md.get("fundamental_data") or {}
    # earnings_surprise is captured in the fundamental_quality_direction details
    earnings_surprise = None
    fqd = cb.get("fundamental_quality_direction")
    if isinstance(fqd, dict):
        earnings_surprise = (fqd.get("details") or {}).get("earnings_surprise")

    interval = _interval_from_template(md.get("template_name") or md.get("strategy_name") or "")

    return {
        "symbol": row.get("symbol"),
        "direction": md.get("direction") or row.get("side"),
        "strategy_type": md.get("strategy_type"),
        "market_regime": row.get("market_regime"),
        "interval": interval,
        "conviction_score": row.get("conviction_score"),
        "cb_walkforward_edge": cb_score("walkforward_edge"),
        "cb_signal_quality": cb_score("signal_quality"),
        "cb_regime_fit": cb_score("regime_fit"),
        "cb_asset_tradability": cb_score("asset_tradability"),
        "cb_fundamental_quality": cb_score("fundamental_quality") if cb_score("fundamental_quality") is not None else cb_score("fundamental_quality_direction"),
        "cb_news_sentiment": cb_score("news_sentiment"),
        "cb_factor_exposure": cb_score("factor_exposure"),
        "cb_carry_bias": cb_score("carry_bias"),
        "cb_crypto_cycle": cb_score("crypto_cycle"),
        "vix_level": vix,
        "entry_persistence": md.get("entry_persistence"),
        "f_pe_ratio": fund.get("pe_ratio"),
        "f_roe": fund.get("roe"),
        "f_debt_to_equity": fund.get("debt_to_equity"),
        "f_revenue_growth": fund.get("revenue_growth"),
        "f_earnings_surprise": earnings_surprise,
        "price_history": md.get("price_history"),
    }


def _interval_from_template(name: str) -> str:
    n = (name or "").lower()
    if "1h" in n or "hourly" in n:
        return "1h"
    if "4h" in n:
        return "4h"
    if "weekly" in n or "21w" in n or "1w" in n:
        return "1w"
    return "1d"


# ---------------------------------------------------------------------------
# Labels & samples
# ---------------------------------------------------------------------------

@dataclass
class Sample:
    """One realized trade as a training sample."""
    features: Dict[str, float]
    label: int                  # 1 = cost-net profitable
    asset_class: str
    entry_time: datetime
    exit_time: datetime
    symbol: str
    net_return: float           # cost-net fractional return (for economic backtest)
    account_type: str


def cost_net_return(row: Dict[str, Any], asset_class: str) -> Optional[float]:
    """Cost-net fractional return for a closed trade, our costs applied.

    `pnl_percent` is the realized gross % move; we subtract our own
    round-trip cost for the symbol/class so demo (at-quote) and live trades
    are judged on the same honest basis. Returns None if pnl_percent missing.
    """
    pnl_pct = row.get("pnl_percent")
    if pnl_pct is None:
        return None
    try:
        gross = float(pnl_pct) / 100.0
    except (TypeError, ValueError):
        return None
    interval = _interval_from_template(
        ((row.get("trade_metadata") or {}) if isinstance(row.get("trade_metadata"), dict) else {}).get("template_name", "")
    )
    rtc = round_trip_cost_pct(row.get("symbol", "") or "", interval, asset_class)
    return gross - rtc


def build_samples(rows: List[Dict[str, Any]]) -> List[Sample]:
    """Turn closed trade_journal rows into labeled samples (no leakage)."""
    samples: List[Sample] = []
    for row in rows:
        et = row.get("entry_time")
        xt = row.get("exit_time")
        if et is None or xt is None:
            continue
        ac = asset_class_of(row.get("symbol", "") or "")
        net = cost_net_return(row, ac)
        if net is None:
            continue
        ctx = ctx_from_trade(row)
        feats = build_feature_row(ctx)
        samples.append(
            Sample(
                features=feats,
                label=1 if net > 0 else 0,
                asset_class=ac,
                entry_time=et if isinstance(et, datetime) else _parse_dt(et),
                exit_time=xt if isinstance(xt, datetime) else _parse_dt(xt),
                symbol=row.get("symbol", "") or "",
                net_return=net,
                account_type=(row.get("account_type") or "demo"),
            )
        )
    return samples


def _parse_dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00").split("+")[0])


# ---------------------------------------------------------------------------
# Purged + embargoed walk-forward CV
# ---------------------------------------------------------------------------

@dataclass
class CVFold:
    train_idx: List[int]
    test_idx: List[int]


def purged_walkforward_folds(
    samples: List[Sample],
    n_folds: int = 5,
    embargo_frac: float = 0.02,
) -> List[CVFold]:
    """Expanding-window walk-forward folds with purge + embargo.

    Samples are ordered by entry_time. The timeline is split into `n_folds`
    contiguous test blocks. For each test block, the training set is all
    samples that ENTERED before the test block starts, MINUS any whose label
    window (entry_time→exit_time) overlaps the test block (purge), and MINUS an
    embargo tail of `embargo_frac` of the sample count immediately after the
    test block. This prevents look-ahead and label-window leakage (López de
    Prado, Advances in Financial ML, ch.7).
    """
    n = len(samples)
    if n < n_folds * 2:
        return []
    order = sorted(range(n), key=lambda i: samples[i].entry_time)
    block = n // (n_folds + 1)  # first block is the initial training seed
    embargo = max(1, int(n * embargo_frac))
    folds: List[CVFold] = []

    for k in range(1, n_folds + 1):
        test_start = k * block
        test_end = (k + 1) * block if k < n_folds else n
        test_positions = order[test_start:test_end]
        if not test_positions:
            continue
        test_idx = list(test_positions)
        test_entry_min = min(samples[i].entry_time for i in test_idx)
        test_exit_max = max(samples[i].exit_time for i in test_idx)

        # Candidate train = everything ordered before the test block.
        candidate = order[:test_start]
        # Embargo: drop the tail just before the test block as well as overlap.
        embargo_cutoff = test_entry_min
        train_idx: List[int] = []
        for i in candidate:
            s = samples[i]
            # Purge: a train trade whose label window overlaps the test window.
            if s.exit_time >= test_entry_min and s.entry_time <= test_exit_max:
                continue
            # Embargo: drop trades that exit within the embargo window before test.
            if (embargo_cutoff - s.exit_time).total_seconds() < 0:
                continue
            train_idx.append(i)
        # Apply count-based embargo on the most recent `embargo` train items.
        if embargo and len(train_idx) > embargo:
            train_idx = train_idx[: len(train_idx) - embargo]
        if train_idx:
            folds.append(CVFold(train_idx=train_idx, test_idx=test_idx))
    return folds


# ---------------------------------------------------------------------------
# Vectorization + imputation
# ---------------------------------------------------------------------------

def _matrix(samples: List[Sample], idx: List[int]) -> Tuple[np.ndarray, np.ndarray]:
    X = np.array(
        [[samples[i].features[name] for name in FEATURE_ORDER] for i in idx],
        dtype=float,
    )
    y = np.array([samples[i].label for i in idx], dtype=int)
    return X, y


def _fit_medians(X: np.ndarray) -> np.ndarray:
    """Column medians ignoring NaN; 0.0 for all-NaN columns."""
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    return med


def _impute(X: np.ndarray, medians: np.ndarray) -> np.ndarray:
    out = X.copy()
    inds = np.where(np.isnan(out))
    out[inds] = np.take(medians, inds[1])
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _precision_recall(y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[float, float, float]:
    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


def _auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    """ROC AUC via rank statistic (no sklearn dep, robust to ties)."""
    pos = scores[y_true == 1]
    neg = scores[y_true == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(scores)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    # average ranks for ties
    _, inv, counts = np.unique(scores, return_inverse=True, return_counts=True)
    sum_ranks = np.zeros(len(counts))
    np.add.at(sum_ranks, inv, ranks)
    avg_rank = sum_ranks / counts
    ranks = avg_rank[inv]
    r_pos = np.sum(ranks[y_true == 1])
    n_pos, n_neg = len(pos), len(neg)
    return (r_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def calibration_bins(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 10) -> List[Dict[str, float]]:
    """Reliability curve: predicted P(win) vs realized win-rate per bin."""
    bins = []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        mask = (proba >= lo) & (proba < hi if b < n_bins - 1 else proba <= hi)
        if not np.any(mask):
            continue
        bins.append({
            "bin_low": round(float(lo), 3),
            "bin_high": round(float(hi), 3),
            "predicted": round(float(np.mean(proba[mask])), 4),
            "realized": round(float(np.mean(y_true[mask])), 4),
            "count": int(np.sum(mask)),
        })
    return bins


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

@dataclass
class ClassResult:
    asset_class: str
    n_samples: int
    base_rate: float
    oos_precision: float
    oos_recall: float
    oos_f1: float
    oos_auc: float
    n_folds: int
    calibration: List[Dict[str, float]] = field(default_factory=list)
    feature_importance: Dict[str, float] = field(default_factory=dict)
    economic: Dict[str, Any] = field(default_factory=dict)
    trained: bool = False
    skip_reason: Optional[str] = None


class MetaLabelTrainer:
    """Fits + validates + persists per-asset-class meta-label models."""

    def __init__(self, model_dir: str = MODEL_DIR_DEFAULT, n_folds: int = 5):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.n_folds = n_folds

    # --- public API ---

    def cross_validate_class(self, samples: List[Sample]) -> ClassResult:
        """Purged-WF OOS evaluation for one asset class (no persistence)."""
        ac = samples[0].asset_class if samples else "unknown"
        n = len(samples)
        minority = min(sum(s.label for s in samples), n - sum(s.label for s in samples))
        base_rate = (sum(s.label for s in samples) / n) if n else 0.0
        if n < MIN_CLASS_SAMPLES or minority < MIN_MINORITY_SAMPLES:
            return ClassResult(
                asset_class=ac, n_samples=n, base_rate=round(base_rate, 4),
                oos_precision=0.0, oos_recall=0.0, oos_f1=0.0, oos_auc=float("nan"),
                n_folds=0, trained=False,
                skip_reason=f"insufficient data (n={n}, minority={minority}; "
                            f"need n≥{MIN_CLASS_SAMPLES}, minority≥{MIN_MINORITY_SAMPLES})",
            )

        folds = purged_walkforward_folds(samples, n_folds=self.n_folds)
        if not folds:
            return ClassResult(
                asset_class=ac, n_samples=n, base_rate=round(base_rate, 4),
                oos_precision=0.0, oos_recall=0.0, oos_f1=0.0, oos_auc=float("nan"),
                n_folds=0, trained=False, skip_reason="no valid CV folds",
            )

        all_y: List[int] = []
        all_pred: List[int] = []
        all_proba: List[float] = []
        oos_records: List[Tuple[int, float, float]] = []  # (label, proba, net_return)
        for fold in folds:
            Xtr, ytr = _matrix(samples, fold.train_idx)
            Xte, yte = _matrix(samples, fold.test_idx)
            if len(np.unique(ytr)) < 2:
                continue
            medians = _fit_medians(Xtr)
            Xtr, Xte = _impute(Xtr, medians), _impute(Xte, medians)
            model = self._new_model()
            model.fit(Xtr, ytr)
            proba = model.predict_proba(Xte)[:, 1]
            pred = (proba >= 0.5).astype(int)
            all_y.extend(yte.tolist())
            all_pred.extend(pred.tolist())
            all_proba.extend(proba.tolist())
            for j, i in enumerate(fold.test_idx):
                oos_records.append((int(yte[j]), float(proba[j]), samples[i].net_return))

        y_arr = np.array(all_y)
        pred_arr = np.array(all_pred)
        proba_arr = np.array(all_proba)
        precision, recall, f1 = _precision_recall(y_arr, pred_arr)
        auc = _auc(y_arr, proba_arr)
        econ = self._economic_backtest(oos_records, base_rate)

        return ClassResult(
            asset_class=ac,
            n_samples=n,
            base_rate=round(base_rate, 4),
            oos_precision=round(precision, 4),
            oos_recall=round(recall, 4),
            oos_f1=round(f1, 4),
            oos_auc=round(auc, 4) if not np.isnan(auc) else float("nan"),
            n_folds=len(folds),
            calibration=calibration_bins(y_arr, proba_arr),
            economic=econ,
            trained=False,
        )

    def fit_and_persist_class(self, samples: List[Sample]) -> ClassResult:
        """Run OOS CV, then (if it has data) fit a final full-sample model and persist."""
        result = self.cross_validate_class(samples)
        if result.skip_reason:
            logger.info("Meta-label %s SKIP: %s", result.asset_class, result.skip_reason)
            return result

        X, y = _matrix(samples, list(range(len(samples))))
        medians = _fit_medians(X)
        X = _impute(X, medians)
        model = self._new_model()
        model.fit(X, y)

        importance = {
            name: round(float(imp), 4)
            for name, imp in sorted(
                zip(FEATURE_ORDER, model.feature_importances_),
                key=lambda kv: kv[1], reverse=True,
            )
        }
        result.feature_importance = importance
        result.trained = True

        artifact = {
            "version": FEATURE_SPEC_VERSION,
            "asset_class": result.asset_class,
            "feature_order": FEATURE_ORDER,
            "medians": medians.tolist(),
            "model": model,
            "trained_at": datetime.utcnow().isoformat() + "Z",
            "n_samples": result.n_samples,
            "base_rate": result.base_rate,
            "oos_metrics": {
                "precision": result.oos_precision,
                "recall": result.oos_recall,
                "f1": result.oos_f1,
                "auc": result.oos_auc,
                "n_folds": result.n_folds,
            },
            "feature_importance": importance,
            "calibration": result.calibration,
            "economic": result.economic,
        }
        path = self.model_dir / f"meta_label_{result.asset_class}.pkl"
        with open(path, "wb") as f:
            pickle.dump(artifact, f)
        logger.info(
            "Meta-label %s TRAINED n=%d base=%.3f OOS p=%.3f r=%.3f f1=%.3f auc=%s -> %s",
            result.asset_class, result.n_samples, result.base_rate,
            result.oos_precision, result.oos_recall, result.oos_f1,
            result.oos_auc, path,
        )
        return result

    def _new_model(self):
        from sklearn.ensemble import RandomForestClassifier
        return RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_split=20,
            min_samples_leaf=10,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )

    def _economic_backtest(
        self, oos: List[Tuple[int, float, float]], base_rate: float,
    ) -> Dict[str, Any]:
        """Held-out economic comparison on OOS predictions, OUR costs already
        baked into net_return.

        Compares per-trade cost-net return of three policies on the OOS set:
          A) trade everything (the strategy as-is, no meta-filter)
          B) enforce: trade only when P(win) >= 0.5 (veto the rest)
          C) probability-sized: scale notional in [0.25, 1.0] by P(win)
        Reports avg net return per trade and total, plus coverage.
        """
        if not oos:
            return {}
        labels = np.array([r[0] for r in oos])
        proba = np.array([r[1] for r in oos])
        net = np.array([r[2] for r in oos])

        a_avg = float(np.mean(net))
        keep = proba >= 0.5
        b_avg = float(np.mean(net[keep])) if np.any(keep) else 0.0
        # probability sizing within caps
        size = np.clip(0.25 + 0.75 * (proba - 0.5) / 0.5, 0.25, 1.0)
        size = np.where(proba >= 0.5, size, 0.0)  # enforce-style: no negative-EV exposure
        c_weighted = float(np.sum(net * size) / np.sum(size)) if np.sum(size) > 0 else 0.0

        # what the filter BLOCKED (would-block cohort) vs PASSED
        blocked = ~keep
        return {
            "n_oos": int(len(oos)),
            "policy_A_trade_all_avg_net": round(a_avg, 5),
            "policy_B_enforce_avg_net": round(b_avg, 5),
            "policy_B_coverage": round(float(np.mean(keep)), 4),
            "policy_C_prob_sized_avg_net": round(c_weighted, 5),
            "blocked_cohort_avg_net": round(float(np.mean(net[blocked])), 5) if np.any(blocked) else None,
            "passed_cohort_avg_net": round(float(np.mean(net[keep])), 5) if np.any(keep) else None,
            "separation": (
                round(float(np.mean(net[keep]) - np.mean(net[blocked])), 5)
                if np.any(keep) and np.any(blocked) else None
            ),
        }


# ---------------------------------------------------------------------------
# Inference loader (used by the serve path; kept here for train/serve parity)
# ---------------------------------------------------------------------------

class MetaLabelModel:
    """A single loaded per-asset-class model for in-memory inference."""

    def __init__(self, artifact: Dict[str, Any]):
        self.version = artifact["version"]
        self.asset_class = artifact["asset_class"]
        self.feature_order = artifact["feature_order"]
        self.medians = np.array(artifact["medians"], dtype=float)
        self.model = artifact["model"]
        self.trained_at = artifact.get("trained_at")
        self.base_rate = artifact.get("base_rate")
        self.oos_metrics = artifact.get("oos_metrics", {})

    def predict_proba(self, ctx: Dict[str, Any]) -> float:
        """P(cost-net win) for one candidate signal context. Sub-ms."""
        row = build_feature_row(ctx)
        if self.feature_order != FEATURE_ORDER:
            raise ValueError(
                f"Feature-order drift for {self.asset_class}: artifact "
                f"{self.version} != code {FEATURE_SPEC_VERSION}"
            )
        x = np.array([[row[name] for name in self.feature_order]], dtype=float)
        inds = np.where(np.isnan(x))
        x[inds] = np.take(self.medians, inds[1])
        return float(self.model.predict_proba(x)[0, 1])


def load_model(asset_class: str, model_dir: str = MODEL_DIR_DEFAULT) -> Optional[MetaLabelModel]:
    """Load a persisted per-asset-class model, or None if absent/incompatible."""
    path = Path(model_dir) / f"meta_label_{asset_class}.pkl"
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            artifact = pickle.load(f)
        if artifact.get("version") != FEATURE_SPEC_VERSION:
            logger.warning(
                "Meta-label %s artifact version %s != code %s — refusing to load",
                asset_class, artifact.get("version"), FEATURE_SPEC_VERSION,
            )
            return None
        return MetaLabelModel(artifact)
    except Exception as e:  # never let a bad pickle break the caller
        logger.error("Failed to load meta-label model %s: %s", asset_class, e)
        return None
