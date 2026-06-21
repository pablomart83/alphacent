"""Strategy catalog loader, schema and normalization policy.

This module loads the declarative strategy catalog (``config/strategy_catalog/*.yaml``),
validates every record against a Pydantic schema, applies the normalization policy
(SL/TP floors, R:R enforcement, crypto ADX-gate injection, sizing defaults) and the
catalog-level enable/deprecate/fee-floor policy, and returns the effective list of
``StrategyTemplate`` objects.

Design (see STRATEGY_TEMPLATE_REDESIGN findings):
  - YAML stores the AUTHORED form of each template (what a quant writes).
  - ``NormalizationPolicy`` (in strategy_templates) turns authored -> effective.
  - The schema enforces structure and lints DSL at LOAD time, so a malformed
    condition is a deploy-time error, not a silent 0-trade backtest.
  - Identity is the template ``name`` (a DB foreign key across history) — never
    rename without a migration map.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.strategy.strategy_templates import (
    MarketRegime,
    StrategyTemplate,
    StrategyType,
)
from src.strategy.dsl_lint import lint_template_conditions

CATALOG_DIR = Path(__file__).resolve().parents[2] / "config" / "strategy_catalog"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
class TemplateSpec(BaseModel):
    """Schema for one authored catalog record. Validated at load time."""

    model_config = ConfigDict(extra="forbid")

    seq: int  # catalog ordering only — NOT template data, stripped before build
    name: str
    description: str
    strategy_type: StrategyType
    market_regimes: List[MarketRegime]
    entry_conditions: List[str] = Field(default_factory=list)
    exit_conditions: List[str] = Field(default_factory=list)
    required_indicators: List[str] = Field(default_factory=list)
    default_parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_trade_frequency: str
    expected_holding_period: str
    risk_reward_ratio: float
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # First-class provenance / lifecycle (Phase 3) — replaces REMOVE_TEMPLATES hack.
    enabled: bool = True
    deprecated_by: Optional[str] = None
    disabled_reason: Optional[str] = None
    research_citation: Optional[str] = None
    author: Optional[str] = None

    @model_validator(mode="after")
    def _lint_dsl(self) -> "TemplateSpec":
        """Load-time DSL lint. Fundamental-prose templates are skipped (see dsl_lint)."""
        err = lint_template_conditions(
            self.entry_conditions, self.exit_conditions, self.metadata
        )
        if err:
            raise ValueError(f"template '{self.name}': {err}")
        return self

    def to_template(self) -> StrategyTemplate:
        """Build a StrategyTemplate from the authored spec.

        ``StrategyTemplate.__post_init__`` applies the NormalizationPolicy, so the
        returned object is the EFFECTIVE (traded) form.
        """
        return StrategyTemplate(
            name=self.name,
            description=self.description,
            strategy_type=self.strategy_type,
            market_regimes=list(self.market_regimes),
            entry_conditions=list(self.entry_conditions),
            exit_conditions=list(self.exit_conditions),
            required_indicators=list(self.required_indicators),
            default_parameters=dict(self.default_parameters),
            expected_trade_frequency=self.expected_trade_frequency,
            expected_holding_period=self.expected_holding_period,
            risk_reward_ratio=self.risk_reward_ratio,
            metadata=dict(self.metadata),
        )


# ---------------------------------------------------------------------------
# Catalog-level policy (post-normalization culling)
# ---------------------------------------------------------------------------
# Crypto fee-floor policy: eToro crypto round-trip ~3% (1% commission/side + spread
# + slippage). A template whose EFFECTIVE take-profit is below this floor is
# deterministically negative-EV and is dropped at load. This used to be the inline
# ``_MIN_CRYPTO_TP`` filter in StrategyTemplateLibrary.__init__; it now lives here as
# a named, documented catalog policy applied AFTER normalization (floors first, then
# this gate decides survival).
_MIN_CRYPTO_TP = 0.06


def _passes_crypto_fee_floor(t: StrategyTemplate) -> bool:
    if (t.metadata or {}).get("crypto_optimized") is True:
        tp = float((t.default_parameters or {}).get("take_profit_pct", 0) or 0)
        return tp >= _MIN_CRYPTO_TP
    return True


# ---------------------------------------------------------------------------
# Crypto cost-STYLE / horizon policy (2026-06-20 crypto revamp).
#
# eToro Diamond crypto = 0.75%/side = ~1.5% round-trip. At that cost only
# LOW-FREQUENCY, LARGE-MOVE strategies can amortize the fee. The live cycle on
# 2026-06-20 proved the high-frequency mean-reversion catalog is structurally
# negative-EV here: every sampled mean-reversion/dip/capitulation template
# returned −1.5% to −10% cost-net per trade. Crypto's robust documented edge is
# TREND/MOMENTUM (Liu & Tsyvinski 2021; Liu/Tsyvinski/Wu 2022), held for weeks.
#
# Policy: a crypto_optimized template survives load only if it is
#   trend_following / momentum / breakout  AND  holds >= 24h (min expected hold).
# This drops (a) mean-reversion / volatility-fade (wrong style for trend-
# dominated crypto) and (b) sub-day scalps (can't clear the cost floor),
# regardless of bar interval. Non-crypto templates are untouched.
# ---------------------------------------------------------------------------
import re as _re

_CRYPTO_VIABLE_STYLES = {"trend_following", "momentum", "breakout"}
_CRYPTO_MIN_HOLD_HOURS = 24.0
# Deep-capitulation mean-reversion carve-out: a big-target, rare trade that can
# clear the ~1.5% round-trip (the one long-only edge in a crypto bear).
_CRYPTO_MR_MIN_TP = 0.20          # >= 20% take-profit
_CRYPTO_MR_MIN_HOLD_HOURS = 168.0  # >= 7-day hold (low frequency)


def _min_hold_hours(t: StrategyTemplate) -> Optional[float]:
    """Lower-bound expected holding period in hours, parsed from the authored
    `expected_holding_period` string (e.g. '4-24 hours', '2-7 days', '30-120
    days'). Returns None when unparseable."""
    s = (getattr(t, "expected_holding_period", "") or "").lower()
    m = _re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    val = float(m.group(1))
    if "hour" in s:
        return val
    if "day" in s:
        return val * 24.0
    if "week" in s:
        return val * 168.0
    if "month" in s:
        return val * 720.0
    return None


def _passes_crypto_cost_style(t: StrategyTemplate) -> bool:
    md = t.metadata or {}
    if md.get("crypto_optimized") is not True:
        return True  # non-crypto templates untouched
    try:
        stype = (t.strategy_type.value if hasattr(t.strategy_type, "value")
                 else str(t.strategy_type)).lower()
    except Exception:
        stype = ""
    mh = _min_hold_hours(t)
    if stype in _CRYPTO_VIABLE_STYLES:
        # Trend/momentum/breakout: must hold >= 24h to amortize the round-trip.
        if mh is not None and mh < _CRYPTO_MIN_HOLD_HOURS:
            return False
        return True
    # Mean-reversion / volatility-fade is the WRONG style for trend-dominated
    # crypto at high cost — high-frequency dip-scalping is a proven cost-loser
    # (-1.5% to -10%/trade). BUT a DEEP, LOW-FREQUENCY, LARGE-TARGET capitulation
    # buy can clear the ~1.5% round-trip BECAUSE the captured move is big and the
    # trade is rare — this is the one long-only edge available in a crypto bear
    # (buy the washout). Re-admit ONLY that case: TP >= 20% AND hold >= 7 days.
    tp = float((t.default_parameters or {}).get("take_profit_pct", 0) or 0)
    if tp >= _CRYPTO_MR_MIN_TP and mh is not None and mh >= _CRYPTO_MR_MIN_HOLD_HOURS:
        return True
    return False


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _read_specs(catalog_dir: Path) -> List[TemplateSpec]:
    specs: List[TemplateSpec] = []
    seen_seq: Dict[int, str] = {}
    seen_name: Dict[str, str] = {}
    files = sorted(catalog_dir.glob("*.yaml"))
    if not files:
        raise FileNotFoundError(f"No catalog files found in {catalog_dir}")
    for path in files:
        with open(path) as fh:
            raw = yaml.safe_load(fh) or []
        for record in raw:
            spec = TemplateSpec(**record)
            if spec.seq in seen_seq:
                raise ValueError(
                    f"Duplicate seq {spec.seq}: '{spec.name}' collides with "
                    f"'{seen_seq[spec.seq]}'"
                )
            if spec.name in seen_name:
                raise ValueError(
                    f"Duplicate template name '{spec.name}' in {path.name} "
                    f"(also in {seen_name[spec.name]})"
                )
            seen_seq[spec.seq] = spec.name
            seen_name[spec.name] = path.name
            specs.append(spec)
    return specs


@functools.lru_cache(maxsize=1)
def load_catalog() -> tuple:
    """Load, validate, normalize and cull the catalog. Cached (immutable tuple).

    Order is preserved via ``seq`` so ``get_all_templates()`` is unchanged.
    """
    specs = _read_specs(CATALOG_DIR)
    specs.sort(key=lambda s: s.seq)

    templates: List[StrategyTemplate] = []
    for spec in specs:
        if not spec.enabled:  # Phase 3: declarative deprecation (was REMOVE_TEMPLATES)
            continue
        template = spec.to_template()  # __post_init__ applies NormalizationPolicy
        if not _passes_crypto_fee_floor(template):  # crypto fee-floor policy
            continue
        if not _passes_crypto_cost_style(template):  # crypto cost-style/horizon policy
            continue
        templates.append(template)
    return tuple(templates)
