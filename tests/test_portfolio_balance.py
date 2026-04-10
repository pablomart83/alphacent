"""Tests for portfolio-level hedging (check_portfolio_balance, signal balance helpers)."""

import pytest
from datetime import datetime

from src.risk.risk_manager import (
    RiskManager,
    PortfolioBalanceReport,
    get_symbol_sector,
    SYMBOL_SECTOR_MAP,
)
from src.models import (
    AccountInfo,
    Position,
    RiskConfig,
    TradingSignal,
    SignalAction,
    PositionSide,
    TradingMode,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def risk_config():
    return RiskConfig(
        max_position_size_pct=0.10,
        max_exposure_pct=0.80,
        max_daily_loss_pct=0.03,
        max_drawdown_pct=0.10,
        position_risk_pct=0.01,
    )


@pytest.fixture
def risk_manager(risk_config):
    return RiskManager(risk_config)


@pytest.fixture
def account():
    return AccountInfo(
        account_id="test",
        mode=TradingMode.DEMO,
        balance=100_000.0,
        buying_power=80_000.0,
        margin_used=20_000.0,
        margin_available=80_000.0,
        daily_pnl=0.0,
        total_pnl=0.0,
        positions_count=0,
        updated_at=datetime.now(),
    )


def _make_position(symbol, side, quantity=10.0, entry_price=100.0, current_price=100.0, strategy_id="strat_1"):
    return Position(
        id=f"pos_{symbol}_{side.value}",
        strategy_id=strategy_id,
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        current_price=current_price,
        unrealized_pnl=0.0,
        realized_pnl=0.0,
        opened_at=datetime.now(),
        etoro_position_id=f"etoro_{symbol}",
        closed_at=None,
    )


def _make_signal(symbol, action=SignalAction.ENTER_LONG, confidence=0.8):
    return TradingSignal(
        strategy_id="strat_test",
        symbol=symbol,
        action=action,
        confidence=confidence,
        reasoning="test",
        generated_at=datetime.now(),
    )


# ---------------------------------------------------------------------------
# get_symbol_sector tests
# ---------------------------------------------------------------------------

class TestGetSymbolSector:
    def test_known_stock(self):
        assert get_symbol_sector("AAPL") == "Technology"
        assert get_symbol_sector("JPM") == "Finance"
        assert get_symbol_sector("XOM") == "Energy"

    def test_etf_sector(self):
        assert get_symbol_sector("XLE") == "Energy"
        assert get_symbol_sector("XLV") == "Healthcare"
        assert get_symbol_sector("SPY") == "Broad Market ETF"

    def test_crypto(self):
        assert get_symbol_sector("BTC") == "Crypto"

    def test_forex(self):
        assert get_symbol_sector("EURUSD") == "Forex"

    def test_unknown_symbol(self):
        assert get_symbol_sector("ZZZZZ") == "Unknown"

    def test_case_insensitive(self):
        assert get_symbol_sector("aapl") == "Technology"


# ---------------------------------------------------------------------------
# check_portfolio_balance tests
# ---------------------------------------------------------------------------

class TestCheckPortfolioBalance:
    def test_empty_portfolio_is_balanced(self, risk_manager, account):
        report = risk_manager.check_portfolio_balance([], account)
        assert report.is_balanced is True
        assert report.total_exposure == 0.0

    def test_single_position_balanced(self, risk_manager, account):
        positions = [_make_position("AAPL", PositionSide.LONG)]
        report = risk_manager.check_portfolio_balance(positions, account)
        # Single position = 100% in one sector, which exceeds 40%
        assert report.is_balanced is False
        assert "Technology" in report.sector_exposures

    def test_diversified_portfolio_balanced(self, risk_manager, account):
        """Portfolio spread across 4 sectors at 25% each should be balanced."""
        positions = [
            _make_position("AAPL", PositionSide.LONG, quantity=25.0, current_price=100.0),
            _make_position("JPM", PositionSide.LONG, quantity=25.0, current_price=100.0),
            _make_position("XOM", PositionSide.LONG, quantity=25.0, current_price=100.0),
            _make_position("LLY", PositionSide.SHORT, quantity=25.0, current_price=100.0),
        ]
        report = risk_manager.check_portfolio_balance(
            positions, account,
            strategy_types=["trend_following", "mean_reversion"],
        )
        # Each sector at 25%, long=75% > 60% → directional violation
        # But sector-wise all are ≤ 40%
        assert report.sector_exposures["Technology"] == pytest.approx(0.25, abs=0.01)

    def test_sector_concentration_violation(self, risk_manager, account):
        """All positions in tech should trigger sector violation."""
        positions = [
            _make_position("AAPL", PositionSide.LONG, quantity=10.0, current_price=100.0),
            _make_position("MSFT", PositionSide.LONG, quantity=10.0, current_price=100.0),
            _make_position("GOOGL", PositionSide.LONG, quantity=10.0, current_price=100.0),
        ]
        report = risk_manager.check_portfolio_balance(positions, account)
        assert report.is_balanced is False
        assert any("Technology" in v for v in report.violations)

    def test_directional_imbalance_long(self, risk_manager, account):
        """All long positions should trigger directional violation at 60% threshold."""
        positions = [
            _make_position("AAPL", PositionSide.LONG),
            _make_position("JPM", PositionSide.LONG),
            _make_position("XOM", PositionSide.LONG),
        ]
        report = risk_manager.check_portfolio_balance(positions, account)
        assert report.long_pct == pytest.approx(1.0, abs=0.01)
        assert any("Long exposure" in v for v in report.violations)

    def test_directional_imbalance_short(self, risk_manager, account):
        positions = [
            _make_position("AAPL", PositionSide.SHORT),
            _make_position("JPM", PositionSide.SHORT),
            _make_position("XOM", PositionSide.SHORT),
        ]
        report = risk_manager.check_portfolio_balance(positions, account)
        assert report.short_pct == pytest.approx(1.0, abs=0.01)
        assert any("Short exposure" in v for v in report.violations)

    def test_strategy_type_diversity_violation(self, risk_manager, account):
        """Only 1 strategy type with enough positions should trigger violation."""
        positions = [
            _make_position("AAPL", PositionSide.LONG),
            _make_position("JPM", PositionSide.SHORT),
        ]
        report = risk_manager.check_portfolio_balance(
            positions, account,
            strategy_types=["trend_following"],
            min_strategy_types=2,
        )
        assert any("strategy type" in v for v in report.violations)

    def test_strategy_type_diversity_ok(self, risk_manager, account):
        positions = [
            _make_position("AAPL", PositionSide.LONG),
            _make_position("JPM", PositionSide.SHORT),
        ]
        report = risk_manager.check_portfolio_balance(
            positions, account,
            strategy_types=["trend_following", "mean_reversion"],
            min_strategy_types=2,
        )
        assert not any("strategy type" in v for v in report.violations)

    def test_external_positions_excluded(self, risk_manager, account):
        """Positions from external strategies should be excluded."""
        positions = [
            _make_position("AAPL", PositionSide.LONG, strategy_id="etoro_position"),
        ]
        report = risk_manager.check_portfolio_balance(positions, account)
        assert report.is_balanced is True
        assert report.total_exposure == 0.0


# ---------------------------------------------------------------------------
# would_signal_improve_balance tests
# ---------------------------------------------------------------------------

class TestWouldSignalImproveBalance:
    def test_balanced_portfolio_any_signal_ok(self, risk_manager):
        report = PortfolioBalanceReport(is_balanced=True)
        signal = _make_signal("AAPL", SignalAction.ENTER_LONG)
        assert risk_manager.would_signal_improve_balance(signal, report) is True

    def test_long_heavy_short_signal_improves(self, risk_manager):
        report = PortfolioBalanceReport(
            is_balanced=False,
            violations=["Long exposure 80.0% exceeds max 60%"],
            long_pct=0.80,
            short_pct=0.20,
        )
        short_signal = _make_signal("AAPL", SignalAction.ENTER_SHORT)
        assert risk_manager.would_signal_improve_balance(short_signal, report) is True

    def test_long_heavy_long_signal_does_not_improve(self, risk_manager):
        report = PortfolioBalanceReport(
            is_balanced=False,
            violations=["Long exposure 80.0% exceeds max 60%"],
            long_pct=0.80,
            short_pct=0.20,
        )
        long_signal = _make_signal("AAPL", SignalAction.ENTER_LONG)
        assert risk_manager.would_signal_improve_balance(long_signal, report) is False

    def test_sector_overexposed_different_sector_improves(self, risk_manager):
        report = PortfolioBalanceReport(
            is_balanced=False,
            violations=["Sector 'Technology' exposure 50.0% exceeds max 40%"],
            sector_exposures={"Technology": 0.50},
        )
        # JPM is Finance, not Technology
        signal = _make_signal("JPM", SignalAction.ENTER_LONG)
        assert risk_manager.would_signal_improve_balance(signal, report) is True


# ---------------------------------------------------------------------------
# would_signal_worsen_balance tests
# ---------------------------------------------------------------------------

class TestWouldSignalWorsenBalance:
    def test_balanced_portfolio_never_worsens(self, risk_manager):
        report = PortfolioBalanceReport(is_balanced=True)
        signal = _make_signal("AAPL", SignalAction.ENTER_LONG)
        worsens, _ = risk_manager.would_signal_worsen_balance(signal, report)
        assert worsens is False

    def test_adding_to_overexposed_sector_worsens(self, risk_manager):
        report = PortfolioBalanceReport(
            is_balanced=False,
            violations=["Sector 'Technology' exposure 50.0% exceeds max 40%"],
            sector_exposures={"Technology": 0.50},
            long_pct=0.50,
            short_pct=0.50,
        )
        signal = _make_signal("MSFT", SignalAction.ENTER_LONG)  # MSFT is Technology
        worsens, reason = risk_manager.would_signal_worsen_balance(signal, report)
        assert worsens is True
        assert "Technology" in reason

    def test_adding_long_when_long_heavy_worsens(self, risk_manager):
        report = PortfolioBalanceReport(
            is_balanced=False,
            violations=["Long exposure 70.0% exceeds max 60%"],
            sector_exposures={},
            long_pct=0.70,
            short_pct=0.30,
        )
        signal = _make_signal("JPM", SignalAction.ENTER_LONG)
        worsens, reason = risk_manager.would_signal_worsen_balance(signal, report)
        assert worsens is True
        assert "long" in reason.lower()

    def test_adding_short_when_long_heavy_does_not_worsen(self, risk_manager):
        report = PortfolioBalanceReport(
            is_balanced=False,
            violations=["Long exposure 70.0% exceeds max 60%"],
            sector_exposures={},
            long_pct=0.70,
            short_pct=0.30,
        )
        signal = _make_signal("JPM", SignalAction.ENTER_SHORT)
        worsens, _ = risk_manager.would_signal_worsen_balance(signal, report)
        assert worsens is False

    def test_different_sector_does_not_worsen(self, risk_manager):
        report = PortfolioBalanceReport(
            is_balanced=False,
            violations=["Sector 'Technology' exposure 50.0% exceeds max 40%"],
            sector_exposures={"Technology": 0.50},
            long_pct=0.50,
            short_pct=0.50,
        )
        signal = _make_signal("XOM", SignalAction.ENTER_LONG)  # XOM is Energy
        worsens, _ = risk_manager.would_signal_worsen_balance(signal, report)
        assert worsens is False
