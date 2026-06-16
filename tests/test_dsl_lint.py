"""Unit tests for the load-time DSL linter (Phase 2 of the catalog redesign)."""
import pytest

from src.strategy.dsl_lint import lint_condition, lint_template_conditions


def test_valid_dsl_passes():
    assert lint_condition("CLOSE > EMA(20) AND RSI(14) < 30") is None
    assert lint_condition("SMA(20) CROSSES_ABOVE SMA(50)") is None


def test_tautology_always_false_is_caught():
    # The historical Triple-EMA bug: EMA(10) > EMA(10) is always false -> 0 trades.
    err = lint_condition("EMA(10) > EMA(10)")
    assert err is not None
    assert "always-true/false" in err


def test_tautology_inside_compound_clause_is_caught():
    err = lint_condition("RSI(14) < 30 AND EMA(10) > EMA(10)")
    assert err is not None
    assert "always-true/false" in err


def test_crossover_with_same_operand_is_not_flagged_as_tautology():
    # CROSSES_ABOVE is directional; identical operands are degenerate but not the
    # X<op>X comparison tautology we guard. It should still parse.
    assert lint_condition("CLOSE CROSSES_ABOVE SMA(20)") is None


def test_unparseable_dsl_is_caught():
    err = lint_condition("this is not valid dsl @@@")
    assert err is not None


def test_empty_condition_is_caught():
    assert lint_condition("") is not None


def test_fundamental_prose_is_skipped_for_alpha_edge():
    # Alpha Edge templates route to the fundamental path; their prose isn't DSL.
    meta = {"strategy_category": "alpha_edge"}
    assert lint_template_conditions(
        ["Earnings surprise > 5%", "Market cap between $300M and $2B"], [], meta
    ) is None


def test_fundamental_prose_is_skipped_for_alpha_edge_type():
    meta = {"strategy_category": "statistical", "alpha_edge_type": "end_of_month_momentum"}
    assert lint_template_conditions(
        ["Date is in last 3 trading days of month (day >= 26 approximation)"], [], meta
    ) is None


def test_dsl_template_with_bad_condition_is_flagged():
    meta = {"strategy_category": None}
    err = lint_template_conditions(["EMA(10) > EMA(10)"], [], meta)
    assert err is not None
    assert "entry condition" in err
