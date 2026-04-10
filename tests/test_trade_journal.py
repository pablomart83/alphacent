"""Tests for TradeJournal class."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock

from src.analytics.trade_journal import TradeJournal, TradeJournalEntryORM
from src.models.database import Database


@pytest.fixture
def mock_database():
    """Create mock database."""
    db = Mock(spec=Database)
    session = MagicMock()
    db.get_session.return_value = session
    return db, session


@pytest.fixture
def trade_journal(mock_database):
    """Create TradeJournal instance."""
    db, _ = mock_database
    return TradeJournal(db)


@pytest.fixture
def sample_trade_entry():
    """Create sample trade entry."""
    return {
        "trade_id": "trade_001",
        "strategy_id": "strategy_001",
        "symbol": "AAPL",
        "entry_time": datetime.now(),
        "entry_price": 150.0,
        "entry_size": 100.0,
        "entry_reason": "Bullish momentum",
        "market_regime": "trending_up",
        "sector": "Technology",
        "conviction_score": 85.0,
        "ml_confidence": 0.75
    }


class TestTradeJournalLogging:
    """Test trade logging functionality."""

    def test_log_entry(self, trade_journal, mock_database, sample_trade_entry):
        """Test logging trade entry."""
        _, session = mock_database

        trade_journal.log_entry(**sample_trade_entry)

        # Verify session operations
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.close.assert_called_once()

        # Verify entry was created with correct data
        added_entry = session.add.call_args[0][0]
        assert added_entry.trade_id == "trade_001"
        assert added_entry.symbol == "AAPL"
        assert added_entry.entry_price == 150.0

    def test_log_exit(self, trade_journal, mock_database):
        """Test logging trade exit."""
        _, session = mock_database

        # Mock existing entry
        mock_entry = Mock(spec=TradeJournalEntryORM)
        mock_entry.entry_time = datetime.now() - timedelta(hours=24)
        mock_entry.entry_price = 150.0
        mock_entry.entry_size = 100.0
        session.query.return_value.filter_by.return_value.first.return_value = mock_entry

        exit_time = datetime.now()
        trade_journal.log_exit(
            trade_id="trade_001",
            exit_time=exit_time,
            exit_price=155.0,
            exit_reason="Take profit hit",
            max_adverse_excursion=-2.0,
            max_favorable_excursion=5.0
        )

        # Verify exit details were updated
        assert mock_entry.exit_time == exit_time
        assert mock_entry.exit_price == 155.0
        assert mock_entry.exit_reason == "Take profit hit"
        assert mock_entry.max_adverse_excursion == -2.0
        assert mock_entry.max_favorable_excursion == 5.0

        # Verify P&L was calculated
        assert mock_entry.pnl == 500.0  # (155 - 150) * 100
        assert mock_entry.pnl_percent == pytest.approx(3.33, rel=0.1)

        session.commit.assert_called_once()

    def test_update_mae_mfe(self, trade_journal, mock_database):
        """Test updating MAE/MFE for open trade."""
        _, session = mock_database

        # Mock existing entry
        mock_entry = Mock(spec=TradeJournalEntryORM)
        mock_entry.entry_price = 150.0
        mock_entry.entry_size = 100.0
        mock_entry.exit_time = None
        mock_entry.max_adverse_excursion = None
        mock_entry.max_favorable_excursion = None
        session.query.return_value.filter_by.return_value.first.return_value = mock_entry

        # Update with price below entry (adverse)
        trade_journal.update_mae_mfe("trade_001", 145.0)

        assert mock_entry.max_adverse_excursion == pytest.approx(-3.33, rel=0.1)
        session.commit.assert_called()

        # Update with price above entry (favorable)
        trade_journal.update_mae_mfe("trade_001", 160.0)

        assert mock_entry.max_favorable_excursion == pytest.approx(6.67, rel=0.1)


class TestTradeJournalQueries:
    """Test trade query functionality."""

    def test_get_trade(self, trade_journal, mock_database):
        """Test getting single trade."""
        _, session = mock_database

        # Mock entry
        mock_entry = Mock(spec=TradeJournalEntryORM)
        mock_entry.to_dict.return_value = {"trade_id": "trade_001", "symbol": "AAPL"}
        session.query.return_value.filter_by.return_value.first.return_value = mock_entry

        trade = trade_journal.get_trade("trade_001")

        assert trade is not None
        assert trade["trade_id"] == "trade_001"
        assert trade["symbol"] == "AAPL"

    def test_get_all_trades_with_filters(self, trade_journal, mock_database):
        """Test getting trades with filters."""
        _, session = mock_database

        # Mock query chain
        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()

        trades = trade_journal.get_all_trades(
            strategy_id="strategy_001",
            symbol="AAPL",
            start_date=start_date,
            end_date=end_date,
            closed_only=True
        )

        assert isinstance(trades, list)
        # Verify filters were applied
        assert mock_query.filter_by.called
        assert mock_query.filter.called

    def test_get_open_trades(self, trade_journal, mock_database):
        """Test getting open trades."""
        _, session = mock_database

        # Mock query
        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []

        trades = trade_journal.get_open_trades()

        assert isinstance(trades, list)
        mock_query.filter.assert_called_once()


class TestPerformanceAnalytics:
    """Test performance analytics functionality."""

    def test_calculate_win_rate(self, trade_journal, mock_database):
        """Test win rate calculation."""
        _, session = mock_database

        # Mock trades
        mock_trades = [
            Mock(pnl=100.0),  # Winner
            Mock(pnl=-50.0),  # Loser
            Mock(pnl=75.0),   # Winner
            Mock(pnl=-25.0),  # Loser
            Mock(pnl=150.0),  # Winner
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = mock_trades

        win_rate = trade_journal.calculate_win_rate()

        assert win_rate == 60.0  # 3 winners out of 5 trades

    def test_calculate_avg_winner_loser(self, trade_journal, mock_database):
        """Test average winner/loser calculation."""
        _, session = mock_database

        # Mock trades
        mock_trades = [
            Mock(pnl=100.0),
            Mock(pnl=-50.0),
            Mock(pnl=200.0),
            Mock(pnl=-75.0),
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = mock_trades

        result = trade_journal.calculate_avg_winner_loser()

        assert result["avg_winner"] == 150.0  # (100 + 200) / 2
        assert result["avg_loser"] == -62.5   # (-50 + -75) / 2

    def test_calculate_profit_factor(self, trade_journal, mock_database):
        """Test profit factor calculation."""
        _, session = mock_database

        # Mock trades
        mock_trades = [
            Mock(pnl=100.0),
            Mock(pnl=-50.0),
            Mock(pnl=200.0),
            Mock(pnl=-50.0),
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = mock_trades

        profit_factor = trade_journal.calculate_profit_factor()

        # Gross profit: 300, Gross loss: 100
        assert profit_factor == 3.0

    def test_calculate_avg_hold_time(self, trade_journal, mock_database):
        """Test average hold time calculation."""
        _, session = mock_database

        # Mock trades
        mock_trades = [
            Mock(hold_time_hours=24.0),
            Mock(hold_time_hours=48.0),
            Mock(hold_time_hours=36.0),
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.all.return_value = mock_trades

        avg_hold_time = trade_journal.calculate_avg_hold_time()

        assert avg_hold_time == 36.0  # (24 + 48 + 36) / 3


class TestPatternRecognition:
    """Test pattern recognition functionality."""

    def test_identify_best_patterns(self, trade_journal, mock_database):
        """Test identifying best patterns."""
        _, session = mock_database

        # Mock performance data
        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query

        # Mock trades for strategy grouping
        mock_trades = [
            Mock(
                strategy_id="strategy_001",
                pnl=100.0,
                market_regime="trending_up",
                sector="Technology",
                hold_time_hours=24.0
            )
        ] * 10  # 10 winning trades

        mock_query.all.return_value = mock_trades

        patterns = trade_journal.identify_best_patterns(min_trades=5)

        assert isinstance(patterns, list)
        # Should identify patterns with high win rates

    def test_identify_worst_patterns(self, trade_journal, mock_database):
        """Test identifying worst patterns."""
        _, session = mock_database

        # Mock performance data
        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query

        # Mock trades for strategy grouping
        mock_trades = [
            Mock(
                strategy_id="strategy_001",
                pnl=-50.0,
                market_regime="high_volatility",
                sector="Energy",
                hold_time_hours=12.0
            )
        ] * 10  # 10 losing trades

        mock_query.all.return_value = mock_trades

        patterns = trade_journal.identify_worst_patterns(min_trades=5)

        assert isinstance(patterns, list)
        # Should identify patterns with low win rates

    def test_generate_insights(self, trade_journal, mock_database):
        """Test generating insights."""
        _, session = mock_database

        # Mock query
        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        insights = trade_journal.generate_insights()

        assert "best_patterns" in insights
        assert "worst_patterns" in insights
        assert "recommendations" in insights
        assert isinstance(insights["recommendations"], list)


class TestReporting:
    """Test reporting functionality."""

    def test_generate_monthly_report(self, trade_journal, mock_database):
        """Test generating monthly report."""
        _, session = mock_database

        # Mock trades with proper attributes
        mock_entry1 = Mock()
        mock_entry1.pnl = 100.0
        mock_entry1.hold_time_hours = 24.0
        mock_entry1.strategy_id = "strategy_001"
        mock_entry1.market_regime = "trending_up"
        mock_entry1.sector = "Technology"
        mock_entry1.to_dict.return_value = {
            "trade_id": "trade_001",
            "pnl": 100.0,
            "hold_time_hours": 24.0
        }

        mock_entry2 = Mock()
        mock_entry2.pnl = -50.0
        mock_entry2.hold_time_hours = 12.0
        mock_entry2.strategy_id = "strategy_001"
        mock_entry2.market_regime = "trending_up"
        mock_entry2.sector = "Technology"
        mock_entry2.to_dict.return_value = {
            "trade_id": "trade_002",
            "pnl": -50.0,
            "hold_time_hours": 12.0
        }

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [mock_entry1, mock_entry2]

        report = trade_journal.generate_monthly_report(2024, 1)

        assert "period" in report
        assert "summary" in report
        assert report["summary"]["total_trades"] == 2

    def test_export_to_csv(self, trade_journal, mock_database, tmp_path):
        """Test exporting to CSV."""
        _, session = mock_database

        # Mock trades
        mock_entries = [
            Mock(to_dict=lambda: {
                "trade_id": "trade_001",
                "strategy_id": "strategy_001",
                "symbol": "AAPL",
                "entry_time": "2024-01-01T10:00:00",
                "entry_price": 150.0,
                "entry_size": 100.0,
                "entry_reason": "Bullish",
                "exit_time": "2024-01-02T10:00:00",
                "exit_price": 155.0,
                "exit_reason": "Take profit",
                "pnl": 500.0,
                "pnl_percent": 3.33,
                "hold_time_hours": 24.0,
                "max_adverse_excursion": -1.0,
                "max_favorable_excursion": 5.0,
                "entry_slippage": 0.1,
                "exit_slippage": 0.2,
                "market_regime": "trending_up",
                "sector": "Technology",
                "conviction_score": 85.0,
                "ml_confidence": 0.75
            })
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_entries

        # Export to temp file
        csv_path = tmp_path / "trades.csv"
        trade_journal.export_to_csv(str(csv_path))

        # Verify file was created
        assert csv_path.exists()

        # Verify CSV content
        with open(csv_path, 'r') as f:
            content = f.read()
            assert "trade_id" in content
            assert "trade_001" in content
            assert "AAPL" in content

    def test_get_equity_curve(self, trade_journal, mock_database):
        """Test equity curve calculation."""
        _, session = mock_database

        # Mock trades
        mock_entries = [
            Mock(to_dict=lambda: {
                "exit_time": "2024-01-01T10:00:00",
                "pnl": 100.0,
                "trade_id": "trade_001",
                "symbol": "AAPL"
            }),
            Mock(to_dict=lambda: {
                "exit_time": "2024-01-02T10:00:00",
                "pnl": -50.0,
                "trade_id": "trade_002",
                "symbol": "TSLA"
            }),
            Mock(to_dict=lambda: {
                "exit_time": "2024-01-03T10:00:00",
                "pnl": 75.0,
                "trade_id": "trade_003",
                "symbol": "MSFT"
            })
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_entries

        equity_curve = trade_journal.get_equity_curve()

        assert len(equity_curve) == 3
        assert equity_curve[0]["cumulative_pnl"] == 100.0
        assert equity_curve[1]["cumulative_pnl"] == 50.0
        assert equity_curve[2]["cumulative_pnl"] == 125.0

    def test_get_drawdown_curve(self, trade_journal, mock_database):
        """Test drawdown curve calculation."""
        _, session = mock_database

        # Mock trades with varying P&L
        mock_entries = [
            Mock(to_dict=lambda: {
                "exit_time": "2024-01-01T10:00:00",
                "pnl": 100.0,
                "trade_id": "trade_001",
                "symbol": "AAPL"
            }),
            Mock(to_dict=lambda: {
                "exit_time": "2024-01-02T10:00:00",
                "pnl": -150.0,  # Drawdown
                "trade_id": "trade_002",
                "symbol": "TSLA"
            }),
            Mock(to_dict=lambda: {
                "exit_time": "2024-01-03T10:00:00",
                "pnl": 200.0,  # Recovery
                "trade_id": "trade_003",
                "symbol": "MSFT"
            })
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_entries

        drawdown_curve = trade_journal.get_drawdown_curve()

        assert len(drawdown_curve) == 3
        # First trade sets peak
        assert drawdown_curve[0]["drawdown"] == 0.0
        # Second trade creates drawdown
        assert drawdown_curve[1]["drawdown"] > 0.0
        # Third trade recovers
        assert drawdown_curve[2]["drawdown"] == 0.0

    def test_get_win_loss_distribution(self, trade_journal, mock_database):
        """Test win/loss distribution."""
        _, session = mock_database

        # Mock trades
        mock_entries = [
            Mock(to_dict=lambda: {"pnl": 100.0}),
            Mock(to_dict=lambda: {"pnl": -50.0}),
            Mock(to_dict=lambda: {"pnl": 200.0}),
            Mock(to_dict=lambda: {"pnl": -75.0}),
            Mock(to_dict=lambda: {"pnl": 150.0}),
        ]

        mock_query = Mock()
        session.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = mock_entries

        distribution = trade_journal.get_win_loss_distribution()

        assert distribution["winner_count"] == 3
        assert distribution["loser_count"] == 2
        assert distribution["avg_winner"] == 150.0
        assert distribution["avg_loser"] == -62.5
        assert distribution["max_winner"] == 200.0
        assert distribution["max_loser"] == -75.0
