"""Tests for Rejection Blacklist (Task 6).

Tests cover:
- 6.4.1 Test rejection counter increment
- 6.4.2 Test blacklist threshold enforcement (3 rejections → blacklisted)
- 6.4.3 Test cooldown expiry allows re-proposal
- 6.4.4 Test reset on successful activation
- 6.4.5 Test score returns 0.0 for blacklisted combinations
- 6.4.6 [PBT] Property test: save then load rejection blacklist produces same state (round-trip)
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proposer(tmp_path=None):
    """Create a minimal StrategyProposer with mocked dependencies."""
    with patch('src.strategy.strategy_proposer.MarketStatisticsAnalyzer'), \
         patch('src.strategy.strategy_proposer.StrategyPerformanceTracker'), \
         patch('src.strategy.strategy_proposer.StrategyTemplateLibrary'):
        from src.strategy.strategy_proposer import StrategyProposer
        proposer = StrategyProposer(llm_service=None, market_data=Mock())
    # Override file path to use temp directory if provided
    if tmp_path is not None:
        proposer._rejection_blacklist_path = str(tmp_path / ".rejection_blacklist.json")
        proposer._zero_trade_blacklist_path = str(tmp_path / ".zero_trade_blacklist.json")
    return proposer


# ---------------------------------------------------------------------------
# 6.4.1 — Test rejection counter increment
# ---------------------------------------------------------------------------

class TestRejectionCounterIncrement:

    def test_record_rejection_increments_counter(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        proposer.record_rejection("earnings_momentum", "AAPL")
        assert proposer._rejection_blacklist[("earnings_momentum", "AAPL")] == 1

    def test_record_rejection_increments_multiple_times(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        proposer.record_rejection("earnings_momentum", "AAPL")
        proposer.record_rejection("earnings_momentum", "AAPL")
        assert proposer._rejection_blacklist[("earnings_momentum", "AAPL")] == 2

    def test_record_rejection_updates_timestamp(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        proposer.record_rejection("earnings_momentum", "AAPL")
        ts = proposer._rejection_blacklist_timestamps[("earnings_momentum", "AAPL")]
        assert ts is not None
        # Should be a valid ISO timestamp
        datetime.fromisoformat(ts)

    def test_record_rejection_different_combos_independent(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        proposer.record_rejection("earnings_momentum", "AAPL")
        proposer.record_rejection("dividend_aristocrat", "JNJ")
        assert proposer._rejection_blacklist[("earnings_momentum", "AAPL")] == 1
        assert proposer._rejection_blacklist[("dividend_aristocrat", "JNJ")] == 1


# ---------------------------------------------------------------------------
# 6.4.2 — Test blacklist threshold enforcement (3 rejections → blacklisted)
# ---------------------------------------------------------------------------

class TestBlacklistThreshold:

    def test_not_blacklisted_below_threshold(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        proposer.record_rejection("earnings_momentum", "AAPL")
        proposer.record_rejection("earnings_momentum", "AAPL")
        assert not proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")

    def test_blacklisted_at_threshold(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        for _ in range(3):
            proposer.record_rejection("earnings_momentum", "AAPL")
        assert proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")

    def test_blacklisted_above_threshold(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        for _ in range(5):
            proposer.record_rejection("earnings_momentum", "AAPL")
        assert proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")

    def test_not_blacklisted_no_rejections(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        assert not proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")


# ---------------------------------------------------------------------------
# 6.4.3 — Test cooldown expiry allows re-proposal
# ---------------------------------------------------------------------------

class TestCooldownExpiry:

    def test_cooldown_expired_allows_reproposal(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        for _ in range(3):
            proposer.record_rejection("earnings_momentum", "AAPL")
        # Manually set timestamp to 31 days ago
        old_ts = (datetime.now() - timedelta(days=31)).isoformat()
        proposer._rejection_blacklist_timestamps[("earnings_momentum", "AAPL")] = old_ts
        assert not proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")

    def test_cooldown_not_expired_stays_blacklisted(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        for _ in range(3):
            proposer.record_rejection("earnings_momentum", "AAPL")
        # Manually set timestamp to 29 days ago (within cooldown)
        recent_ts = (datetime.now() - timedelta(days=29)).isoformat()
        proposer._rejection_blacklist_timestamps[("earnings_momentum", "AAPL")] = recent_ts
        assert proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")


# ---------------------------------------------------------------------------
# 6.4.4 — Test reset on successful activation
# ---------------------------------------------------------------------------

class TestResetOnActivation:

    def test_reset_clears_counter(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        for _ in range(3):
            proposer.record_rejection("earnings_momentum", "AAPL")
        assert proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")
        proposer.reset_rejection("earnings_momentum", "AAPL")
        assert not proposer.is_rejection_blacklisted("earnings_momentum", "AAPL")
        assert ("earnings_momentum", "AAPL") not in proposer._rejection_blacklist

    def test_reset_clears_timestamp(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        proposer.record_rejection("earnings_momentum", "AAPL")
        proposer.reset_rejection("earnings_momentum", "AAPL")
        assert ("earnings_momentum", "AAPL") not in proposer._rejection_blacklist_timestamps

    def test_reset_nonexistent_is_noop(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        # Should not raise
        proposer.reset_rejection("earnings_momentum", "AAPL")


# ---------------------------------------------------------------------------
# 6.4.5 — Test score returns 0.0 for blacklisted combinations
# ---------------------------------------------------------------------------

class TestScoreBlacklisted:

    def test_score_zero_for_blacklisted(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        for _ in range(3):
            proposer.record_rejection("earnings_momentum", "AAPL")

        template = Mock()
        template.name = "earnings_momentum"
        template.entry_conditions = ["RSI(14) < 30"]
        template.metadata = None
        template.strategy_type = Mock()
        template.strategy_type.value = "momentum"
        template.market_regimes = []

        score = proposer._score_symbol_for_template(
            template=template,
            symbol="AAPL",
            market_statistics={"AAPL": {"price_action": {"current_price": 150.0}, "trend_metrics": {}, "volatility_metrics": {}}},
            indicator_distributions={"AAPL": {"RSI": {"current_value": 25}}},
        )
        assert score == 0.0

    def test_score_nonzero_below_threshold(self, tmp_path):
        proposer = _make_proposer(tmp_path)
        proposer.record_rejection("earnings_momentum", "AAPL")
        proposer.record_rejection("earnings_momentum", "AAPL")

        template = Mock()
        template.name = "earnings_momentum"
        template.entry_conditions = ["RSI(14) < 30"]
        template.metadata = None
        template.strategy_type = Mock()
        template.strategy_type.value = "momentum"
        template.market_regimes = []

        score = proposer._score_symbol_for_template(
            template=template,
            symbol="AAPL",
            market_statistics={"AAPL": {"price_action": {"current_price": 150.0}, "trend_metrics": {}, "volatility_metrics": {}}},
            indicator_distributions={"AAPL": {"RSI": {"current_value": 25}}},
        )
        # Should not be 0.0 since below threshold
        assert score > 0.0


# ---------------------------------------------------------------------------
# 6.4.6 — [PBT] Property test: save then load produces same state (round-trip)
# **Validates: Requirements 6.5**
# ---------------------------------------------------------------------------

# Strategy for generating valid template names and symbols
template_names = st.sampled_from([
    "earnings_momentum", "dividend_aristocrat", "insider_buying",
    "quality_mean_reversion", "sector_rotation", "revenue_acceleration",
])
symbols = st.sampled_from([
    "AAPL", "MSFT", "GOOG", "AMZN", "TSLA", "JNJ", "JPM", "XOM",
])
rejection_counts = st.integers(min_value=1, max_value=20)

# Generate a list of (template, symbol, count) entries
blacklist_entries = st.lists(
    st.tuples(template_names, symbols, rejection_counts),
    min_size=0,
    max_size=10,
    unique_by=lambda x: (x[0], x[1]),  # unique template+symbol combos
)


class TestRejectionBlacklistRoundTrip:

    @given(entries=blacklist_entries)
    @settings(max_examples=50, deadline=5000)
    def test_save_then_load_produces_same_state(self, entries):
        """
        **Validates: Requirements 6.5**
        For any rejection blacklist state, save then load produces the same state.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_p = Path(tmp_dir)
            proposer = _make_proposer(tmp_p)

            # Populate the blacklist with generated entries
            now = datetime.now()
            for template, symbol, count in entries:
                key = (template, symbol)
                proposer._rejection_blacklist[key] = count
                proposer._rejection_blacklist_timestamps[key] = now.isoformat()

            # Save to disk
            proposer._save_rejection_blacklist_to_disk()

            # Create a fresh proposer and load from disk
            proposer2 = _make_proposer(tmp_p)
            proposer2._load_rejection_blacklist_from_disk()

            # Verify round-trip: same keys and counts
            assert set(proposer2._rejection_blacklist.keys()) == set(proposer._rejection_blacklist.keys())
            for key in proposer._rejection_blacklist:
                assert proposer2._rejection_blacklist[key] == proposer._rejection_blacklist[key]
                assert proposer2._rejection_blacklist_timestamps[key] == proposer._rejection_blacklist_timestamps[key]
