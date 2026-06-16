"""Strategy template dataclass, enums, normalization policy and catalog-backed library.

Template DEFINITIONS now live in ``config/strategy_catalog/*.yaml`` (declarative,
authored form) and are loaded by ``src.strategy.template_catalog``. This module keeps:

  - ``MarketRegime`` / ``StrategyType`` enums
  - the ``StrategyTemplate`` dataclass
  - ``NormalizationPolicy`` — the single, explicit, testable home for the policy that
    turns an AUTHORED template into the EFFECTIVE (traded) template: SL/TP floors, R:R
    enforcement, crypto ADX-gate injection and sizing defaults. It is applied from
    ``__post_init__`` so every construction path (catalog loader, parameter_optimizer)
    gets identical normalization.
  - ``StrategyTemplateLibrary`` — loads the catalog and exposes the historical API
    (``get_all_templates``, ``get_templates_for_regime``, ``get_template_by_name``,
    ``get_templates_by_type``, ``get_template_count``, ``get_regime_coverage``,
    ``.templates``).

History: this file was an 8,567-line module with 259 inline ``StrategyTemplate(...)``
calls plus load-time culling and policy buried in ``__post_init__``. The behaviour is
preserved byte-for-byte — see ``tests/test_template_catalog_roundtrip.py``.
"""

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
        """Normalize the authored template into its effective (traded) form.

        Delegates to ``NormalizationPolicy`` so the data-vs-policy split is explicit
        and the policy is unit-testable in isolation. Every construction path runs it.
        """
        if self.metadata is None:
            self.metadata = {}
        NormalizationPolicy().apply(self)


class NormalizationPolicy:
    """Authored -> effective template transform.

    This is the policy that used to be inlined in ``StrategyTemplate.__post_init__``.
    It is intentionally NOT part of the stored catalog: the YAML holds the authored
    template; this layer applies the (policy) transformations at load time so the
    authored intent and the traded reality are both inspectable.

    Order is significant and preserved from the original implementation:
      1. direction default
      2. interval derivation
      3. crypto SL/TP floors + R:R
      4. non-crypto SL/TP floors + R:R
      5. sizing defaults
      6. crypto ADX regime-gate injection
    """

    def apply(self, t: "StrategyTemplate") -> "StrategyTemplate":
        if t.metadata is None:
            t.metadata = {}
        self._direction_default(t)
        self._interval_default(t)
        self._crypto_sl_tp_floors(t)
        self._noncrypto_sl_tp_floors(t)
        self._sizing_defaults(t)
        self._crypto_adx_gate(t)
        return t

    # -- 1. direction -------------------------------------------------------
    @staticmethod
    def _direction_default(t: "StrategyTemplate") -> None:
        # Default direction to 'long' — SHORT templates must set this explicitly.
        if 'direction' not in t.metadata:
            t.metadata['direction'] = 'long'

    # -- 2. interval --------------------------------------------------------
    @staticmethod
    def _interval_default(t: "StrategyTemplate") -> None:
        # Auto-set interval from intraday/interval_4h flags if not explicitly set.
        if 'interval' not in t.metadata:
            if t.metadata.get('intraday') and not t.metadata.get('interval_4h'):
                t.metadata['interval'] = '1h'
            elif t.metadata.get('interval_4h'):
                t.metadata['interval'] = '4h'
            else:
                t.metadata['interval'] = '1d'

    # -- 3. crypto SL/TP floors + R:R --------------------------------------
    @staticmethod
    def _crypto_sl_tp_floors(t: "StrategyTemplate") -> None:
        # Enforce minimum SL/TP for crypto to clear eToro's ~3% round-trip cost.
        # Timeframe-aware: 1H templates hold hours (can't reach 8% TP), 4H hold hours-to-2d,
        # 1D+ swing templates hold days-to-weeks (can target 8%+). Floor scales with
        # realistic price range on the template's timeframe so backtests exit naturally.
        if t.metadata.get('crypto_optimized'):
            _interval = t.metadata.get('interval', '1d')
            if _interval == '1h':
                _min_sl, _min_tp = 0.015, 0.02   # 1.5% SL, 2.0% TP — realistic for 1-12h holds
            elif _interval == '4h':
                _min_sl, _min_tp = 0.025, 0.04   # 2.5% SL, 4.0% TP — realistic for 4-48h holds
            else:
                _min_sl, _min_tp = 0.04, 0.08    # 4.0% SL, 8.0% TP — 1D+ swing / weekly trend
            if t.default_parameters.get('stop_loss_pct', 1) < _min_sl:
                t.default_parameters['stop_loss_pct'] = _min_sl
            if t.default_parameters.get('take_profit_pct', 1) < _min_tp:
                t.default_parameters['take_profit_pct'] = _min_tp
            # Ensure R:R >= 1.3 after floor adjustments (lower ratio for 1H where tight targets win)
            sl = t.default_parameters.get('stop_loss_pct', _min_sl)
            tp = t.default_parameters.get('take_profit_pct', _min_tp)
            _min_rr = 1.3 if _interval == '1h' else 1.5
            if sl > 0 and tp / sl < _min_rr:
                t.default_parameters['take_profit_pct'] = round(sl * _min_rr, 4)

    # -- 4. non-crypto SL/TP floors + R:R ----------------------------------
    @staticmethod
    def _noncrypto_sl_tp_floors(t: "StrategyTemplate") -> None:
        # Enforce minimum SL/TP for non-crypto 1d stock templates.
        if not t.metadata.get('crypto_optimized'):
            interval = t.metadata.get('interval', '1d')
            if interval == '1d':
                if t.default_parameters.get('stop_loss_pct', 1) < 0.03:
                    t.default_parameters['stop_loss_pct'] = 0.03
                if t.default_parameters.get('take_profit_pct', 1) < 0.05:
                    t.default_parameters['take_profit_pct'] = 0.05
            # Enforce minimum R:R >= 1.5 for all non-crypto templates (except Alpha Edge with TP=0)
            sl = t.default_parameters.get('stop_loss_pct', 0)
            tp = t.default_parameters.get('take_profit_pct', 0)
            if sl > 0 and tp > 0 and tp / sl < 1.5:
                t.default_parameters['take_profit_pct'] = round(sl * 1.5, 4)

    # -- 5. sizing defaults -------------------------------------------------
    @staticmethod
    def _sizing_defaults(t: "StrategyTemplate") -> None:
        # Add position sizing parameters to default_parameters if not present
        if 'risk_per_trade_pct' not in t.default_parameters:
            t.default_parameters['risk_per_trade_pct'] = 0.01
        if 'sizing_method' not in t.default_parameters:
            t.default_parameters['sizing_method'] = 'volatility'
        if 'position_size_atr_multiplier' not in t.default_parameters:
            t.default_parameters['position_size_atr_multiplier'] = 1.0

    # -- 6. crypto ADX regime gate -----------------------------------------
    @staticmethod
    def _crypto_adx_gate(t: "StrategyTemplate") -> None:
        # Crypto regime gate (B1 + B2 from Batch B):
        # Research consensus (Barroso/Santa-Clara 2015, mbrenndoerfer, repo research doc)
        # says mean-reversion must be gated by ADX<25 (ranging regime) and
        # trend/momentum/breakout must be gated by ADX>20 (trending regime).
        # Injected automatically for crypto_optimized templates that don't already
        # have an ADX filter in entry_conditions. Intraday (1h) uses slightly
        # tighter thresholds (ADX<30 for MR, ADX>15 for trend) because intraday
        # ADX runs hotter.
        if t.metadata.get('crypto_optimized') and not t.metadata.get('skip_adx_gate'):
            _has_adx = any('ADX' in c for c in t.entry_conditions) if t.entry_conditions else False
            if not _has_adx and t.entry_conditions:
                _interval = t.metadata.get('interval', '1d')
                _is_mr = t.strategy_type == StrategyType.MEAN_REVERSION
                _is_trend = t.strategy_type in (
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
                    t.entry_conditions[0] = f"{t.entry_conditions[0]} AND {_adx_gate}"
                    # Ensure ADX is in required_indicators
                    if t.required_indicators is None:
                        t.required_indicators = []
                    if 'ADX' not in t.required_indicators:
                        t.required_indicators = list(t.required_indicators) + ['ADX']
                    t.metadata['adx_gate_injected'] = _adx_gate


class StrategyTemplateLibrary:
    """Library of proven strategy templates, loaded from the declarative catalog."""

    def __init__(self):
        """Load the effective template set from ``config/strategy_catalog/*.yaml``.

        Definitions, normalization (NormalizationPolicy via __post_init__), DSL
        validation, ordering and enable/deprecate culling all happen in
        ``template_catalog.load_catalog``. Imported lazily to avoid an import cycle.
        """
        from src.strategy.template_catalog import load_catalog
        self.templates = list(load_catalog())

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

        Returns:
            List of templates suitable for the given regime
        """
        return [t for t in self.templates if regime in t.market_regimes]

    def get_template_by_name(self, name: str) -> Optional[StrategyTemplate]:
        """
        Get a specific template by name.

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
