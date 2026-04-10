"""Tests for regime-aware directional diversity quotas in strategy proposer.

Tests the _match_templates_to_symbols directional quota logic by extracting
the core algorithm into a testable function, avoiding heavy import chains.
"""
import pytest
import math
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class MockTemplate:
    name: str
    metadata: Optional[Dict] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.name)


def _get_direction(template) -> str:
    md = template.metadata or {}
    return md.get('direction', 'long').lower()


def _is_alpha_edge(template) -> bool:
    md = template.metadata or {}
    return md.get('strategy_category') == 'alpha_edge'


def apply_directional_quotas(
    all_pairs: List[Tuple[float, MockTemplate, str]],
    adjusted_count: int,
    min_long_pct: float,
    min_short_pct: float,
    max_per_template: int = 100,
    max_per_symbol: int = 100,
) -> List[Tuple[MockTemplate, str]]:
    """
    Extracted quota logic matching _match_templates_to_symbols implementation.
    """
    template_usage = {}
    symbol_usage = {}

    long_pairs = [(s, t, sym) for s, t, sym in all_pairs if _get_direction(t) == 'long' and not _is_alpha_edge(t)]
    short_pairs = [(s, t, sym) for s, t, sym in all_pairs if _get_direction(t) == 'short' and not _is_alpha_edge(t)]
    alpha_edge_pairs = [(s, t, sym) for s, t, sym in all_pairs if _is_alpha_edge(t)]

    dsl_count = adjusted_count
    min_long_count = max(1, int(math.ceil(dsl_count * min_long_pct)))
    min_short_count = max(1, int(math.ceil(dsl_count * min_short_pct)))

    def _pick_from_pool(pool, target_count, t_usage, s_usage):
        picked = []
        for score, template, symbol in pool:
            if len(picked) >= target_count:
                break
            if t_usage.get(template.name, 0) >= max_per_template:
                continue
            if s_usage.get(symbol, 0) >= max_per_symbol:
                continue
            t_usage[template.name] = t_usage.get(template.name, 0) + 1
            s_usage[symbol] = s_usage.get(symbol, 0) + 1
            picked.append((template, symbol))
        return picked

    assignments = _pick_from_pool(long_pairs, min_long_count, template_usage, symbol_usage)
    long_filled = len(assignments)

    short_assignments = _pick_from_pool(short_pairs, min_short_count, template_usage, symbol_usage)
    short_filled = len(short_assignments)
    assignments.extend(short_assignments)

    picked_set = set((id(t), s) for t, s in assignments)
    combined_remaining = [(sc, t, sym) for sc, t, sym in all_pairs
                          if (id(t), sym) not in picked_set and not _is_alpha_edge(t)]
    combined_remaining.sort(key=lambda x: -x[0])

    remaining_needed = max(0, dsl_count - len(assignments))
    remaining_assignments = _pick_from_pool(combined_remaining, remaining_needed, template_usage, symbol_usage)
    assignments.extend(remaining_assignments)

    ae_assignments = _pick_from_pool(alpha_edge_pairs, len(alpha_edge_pairs), template_usage, symbol_usage)
    assignments.extend(ae_assignments)

    return assignments


def _make_scored_pairs(long_templates, short_templates, ae_templates, symbols, short_bias=20):
    """Create scored (score, template, symbol) pairs with SHORT scoring higher."""
    pairs = []
    for t in long_templates:
        for s in symbols:
            score = 50 + random.uniform(-5, 5)
            pairs.append((score, t, s))
    for t in short_templates:
        for s in symbols:
            score = 50 + short_bias + random.uniform(-5, 5)  # SHORT scores higher
            pairs.append((score, t, s))
    for t in ae_templates:
        for s in symbols:
            score = 75 + random.uniform(-5, 5)
            pairs.append((score, t, s))
    pairs.sort(key=lambda x: -x[0])
    return pairs


class TestDirectionalQuotas:

    def test_ranging_regime_enforces_balanced_quotas(self):
        """In ranging regime with 35%/35% quotas, both directions should be represented."""
        random.seed(42)
        long_templates = [MockTemplate(name=f"LONG_{i}", metadata={"direction": "long"}) for i in range(15)]
        short_templates = [MockTemplate(name=f"SHORT_{i}", metadata={"direction": "short"}) for i in range(15)]
        symbols = [f"SYM_{i}" for i in range(20)]

        pairs = _make_scored_pairs(long_templates, short_templates, [], symbols, short_bias=20)

        assignments = apply_directional_quotas(
            all_pairs=pairs,
            adjusted_count=20,
            min_long_pct=0.35,
            min_short_pct=0.35,
        )

        long_count = sum(1 for t, _ in assignments if _get_direction(t) == 'long')
        short_count = sum(1 for t, _ in assignments if _get_direction(t) == 'short')
        total = len(assignments)

        assert total == 20
        assert long_count >= 7, f"Expected at least 7 LONG (35% of 20), got {long_count}"
        assert short_count >= 7, f"Expected at least 7 SHORT (35% of 20), got {short_count}"

    def test_without_quotas_short_dominates(self):
        """Without quotas, SHORT should dominate when it scores higher."""
        random.seed(42)
        long_templates = [MockTemplate(name=f"LONG_{i}", metadata={"direction": "long"}) for i in range(15)]
        short_templates = [MockTemplate(name=f"SHORT_{i}", metadata={"direction": "short"}) for i in range(15)]
        symbols = [f"SYM_{i}" for i in range(20)]

        pairs = _make_scored_pairs(long_templates, short_templates, [], symbols, short_bias=20)

        # Just take top 20 by score (no quota enforcement)
        top_20 = pairs[:20]
        short_count = sum(1 for _, t, _ in top_20 if _get_direction(t) == 'short')

        # SHORT should dominate without quotas
        assert short_count > 15, f"Without quotas, SHORT should dominate, got {short_count}/20"

    def test_trending_up_favors_long(self):
        """In trending up regime, should have at least 50% LONG."""
        random.seed(42)
        long_templates = [MockTemplate(name=f"LONG_{i}", metadata={"direction": "long"}) for i in range(15)]
        short_templates = [MockTemplate(name=f"SHORT_{i}", metadata={"direction": "short"}) for i in range(15)]
        symbols = [f"SYM_{i}" for i in range(20)]

        pairs = _make_scored_pairs(long_templates, short_templates, [], symbols, short_bias=20)

        assignments = apply_directional_quotas(
            all_pairs=pairs,
            adjusted_count=20,
            min_long_pct=0.50,
            min_short_pct=0.20,
        )

        long_count = sum(1 for t, _ in assignments if _get_direction(t) == 'long')
        assert long_count >= 10, f"Expected at least 10 LONG (50% of 20), got {long_count}"

    def test_trending_down_favors_short(self):
        """In trending down regime, should have at least 50% SHORT."""
        random.seed(42)
        long_templates = [MockTemplate(name=f"LONG_{i}", metadata={"direction": "long"}) for i in range(15)]
        short_templates = [MockTemplate(name=f"SHORT_{i}", metadata={"direction": "short"}) for i in range(15)]
        symbols = [f"SYM_{i}" for i in range(20)]

        # In trending down, LONG might score higher (contrarian), but quotas enforce SHORT
        pairs = _make_scored_pairs(long_templates, short_templates, [], symbols, short_bias=-10)

        assignments = apply_directional_quotas(
            all_pairs=pairs,
            adjusted_count=20,
            min_long_pct=0.20,
            min_short_pct=0.50,
        )

        short_count = sum(1 for t, _ in assignments if _get_direction(t) == 'short')
        assert short_count >= 10, f"Expected at least 10 SHORT (50% of 20), got {short_count}"

    def test_alpha_edge_excluded_from_quotas(self):
        """Alpha Edge strategies should be added on top, not counted toward quotas."""
        random.seed(42)
        long_templates = [MockTemplate(name=f"LONG_{i}", metadata={"direction": "long"}) for i in range(10)]
        short_templates = [MockTemplate(name=f"SHORT_{i}", metadata={"direction": "short"}) for i in range(10)]
        ae_templates = [
            MockTemplate(name="Earnings_Momentum", metadata={"direction": "long", "strategy_category": "alpha_edge"}),
            MockTemplate(name="Sector_Rotation_Short", metadata={"direction": "short", "strategy_category": "alpha_edge"}),
        ]
        symbols = [f"SYM_{i}" for i in range(15)]

        pairs = _make_scored_pairs(long_templates, short_templates, ae_templates, symbols)

        assignments = apply_directional_quotas(
            all_pairs=pairs,
            adjusted_count=20,
            min_long_pct=0.35,
            min_short_pct=0.35,
        )

        ae_count = sum(1 for t, _ in assignments if _is_alpha_edge(t))
        dsl_count = sum(1 for t, _ in assignments if not _is_alpha_edge(t))

        assert ae_count >= 1, "Alpha Edge should be included"
        # DSL quotas should still be enforced
        dsl_long = sum(1 for t, _ in assignments if _get_direction(t) == 'long' and not _is_alpha_edge(t))
        dsl_short = sum(1 for t, _ in assignments if _get_direction(t) == 'short' and not _is_alpha_edge(t))
        assert dsl_long >= 7, f"DSL LONG should be at least 35% of 20, got {dsl_long}"
        assert dsl_short >= 7, f"DSL SHORT should be at least 35% of 20, got {dsl_short}"

    def test_small_count_still_has_both_directions(self):
        """Even with small counts (e.g., 4), should have at least 1 LONG and 1 SHORT."""
        random.seed(42)
        long_templates = [MockTemplate(name=f"LONG_{i}", metadata={"direction": "long"}) for i in range(5)]
        short_templates = [MockTemplate(name=f"SHORT_{i}", metadata={"direction": "short"}) for i in range(5)]
        symbols = [f"SYM_{i}" for i in range(5)]

        pairs = _make_scored_pairs(long_templates, short_templates, [], symbols, short_bias=30)

        assignments = apply_directional_quotas(
            all_pairs=pairs,
            adjusted_count=4,
            min_long_pct=0.35,
            min_short_pct=0.35,
        )

        long_count = sum(1 for t, _ in assignments if _get_direction(t) == 'long')
        short_count = sum(1 for t, _ in assignments if _get_direction(t) == 'short')

        assert long_count >= 1, "Should have at least 1 LONG even with small count"
        assert short_count >= 1, "Should have at least 1 SHORT even with small count"
