"""Load-time DSL linter for the strategy catalog.

Turns malformed DSL into a deploy-time error instead of a silent 0-trade backtest
(the historical ``EMA(10) > EMA(10)`` always-false class of bug). Two checks:

  1. Parseability — every executable condition must parse with the real
     ``TradingDSLParser`` (the same parser the engine uses at backtest time).
  2. Tautology — reject comparisons whose two operands are identical
     (``EMA(10) > EMA(10)``), which are always-false/true and generate 0 trades.

Alpha Edge templates (``metadata.strategy_category == 'alpha_edge'``) route to the
fundamental signal path, not the DSL parser — their conditions are human-readable
prose ("Earnings surprise > 5%") and are intentionally skipped.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Operators the DSL compares with. CROSSES_ABOVE/BELOW are directional and can
# legitimately share structure, so they are excluded from the tautology check.
_CMP = re.compile(r"\s(>=|<=|==|!=|>|<)\s")
_SPLIT = re.compile(r"\s+(?:AND|OR)\s+", re.IGNORECASE)


def _is_fundamental_prose(metadata: Optional[Dict[str, Any]]) -> bool:
    """Conditions that are NOT executed by the DSL parser.

    Two routes bypass the DSL parser at runtime:
      - ``strategy_category == 'alpha_edge'`` → fundamental signal path
        (``StrategyEngine._is_alpha_edge_strategy``).
      - ``alpha_edge_type`` set → a dedicated handler (earnings/calendar/quality)
        keyed off that type (``_get_alpha_edge_template_type``). These carry prose
        conditions ("Date is in last 3 trading days of month"), not DSL.
    """
    meta = metadata or {}
    if meta.get("strategy_category") == "alpha_edge":
        return True
    if meta.get("alpha_edge_type"):
        return True
    return False


def _tautology(condition: str) -> Optional[str]:
    """Detect ``X <op> X`` (identical operands) within each AND/OR clause."""
    for clause in _SPLIT.split(condition):
        m = _CMP.search(clause)
        if not m:
            continue
        lhs = clause[: m.start()].strip().strip("()")
        rhs = clause[m.end():].strip().strip("()")
        if lhs and lhs == rhs:
            return f"always-true/false comparison ({lhs} {m.group(1)} {rhs})"
    return None


_parser = None


def _get_parser():
    global _parser
    if _parser is None:
        from src.strategy.trading_dsl import TradingDSLParser
        _parser = TradingDSLParser()
    return _parser


def lint_condition(condition: str) -> Optional[str]:
    """Return an error string for a single executable condition, or None if valid."""
    if not isinstance(condition, str) or not condition.strip():
        return "empty condition"
    taut = _tautology(condition)
    if taut:
        return taut
    result = _get_parser().parse(condition)
    if not getattr(result, "success", False):
        return f"unparseable ({getattr(result, 'error', 'unknown error')})"
    return None


def lint_template_conditions(
    entry_conditions: List[str],
    exit_conditions: List[str],
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Lint all conditions of a template. Returns the first error, or None."""
    if _is_fundamental_prose(metadata):
        return None
    for label, conditions in (("entry", entry_conditions), ("exit", exit_conditions)):
        for cond in conditions or []:
            err = lint_condition(cond)
            if err:
                return f"{label} condition {cond!r}: {err}"
    return None
