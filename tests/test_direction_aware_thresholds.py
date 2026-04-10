"""Tests for direction-aware walk-forward thresholds (Task 11.11.6).

Validates that walk-forward validation and activation evaluation use
regime-specific thresholds per direction to prevent systematic rejection
of LONG strategies in ranging markets.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestDirectionAwareThresholds:
    """Test the _get_direction_aware_thresholds helper in StrategyProposer."""

    def _make_proposer(self):
        """Create a minimal StrategyProposer with mocked dependencies."""
        with patch('src.strategy.strategy_proposer.MarketStatisticsAnalyzer'):
            with patch('src.strategy.strategy_proposer.StrategyPerformanceTracker'):
                with patch('src.strategy.strategy_proposer.StrategyTemplateLibrary'):
                    from src.strategy.strategy_proposer import StrategyProposer
                    proposer = StrategyProposer(llm_service=None, market_data=MagicMock())
                    return proposer

    def test_ranging_regime_relaxes_long_thresholds(self):
        """In ranging markets, LONG strategies should get relaxed thresholds."""
        from src.strategy.strategy_templates import MarketRegime
        proposer = self._make_proposer()
        
        thresholds = proposer._get_direction_aware_thresholds('LONG', MarketRegime.RANGING_LOW_VOL)
        
        assert thresholds['min_return'] == -0.02, "LONG min_return should be -2% in ranging"
        assert thresholds['min_sharpe'] == 0.15, "LONG min_sharpe should be 0.15 in ranging"
        assert thresholds['min_win_rate'] == 0.40, "LONG min_win_rate should be 40% in ranging"

    def test_ranging_regime_keeps_strict_short_thresholds(self):
        """In ranging markets, SHORT strategies should keep strict thresholds."""
        from src.strategy.strategy_templates import MarketRegime
        proposer = self._make_proposer()
        
        thresholds = proposer._get_direction_aware_thresholds('SHORT', MarketRegime.RANGING_LOW_VOL)
        
        assert thresholds['min_return'] == 0.0, "SHORT min_return should be 0% in ranging"
        assert thresholds['min_sharpe'] == 0.3, "SHORT min_sharpe should be 0.3 in ranging"
        assert thresholds['min_win_rate'] == 0.45, "SHORT min_win_rate should be 45% in ranging"

    def test_trending_up_relaxes_short_thresholds(self):
        """In trending-up markets, SHORT strategies should get relaxed thresholds."""
        from src.strategy.strategy_templates import MarketRegime
        proposer = self._make_proposer()
        
        thresholds = proposer._get_direction_aware_thresholds('SHORT', MarketRegime.TRENDING_UP)
        
        assert thresholds['min_return'] == -0.02
        assert thresholds['min_sharpe'] == 0.15
        assert thresholds['min_win_rate'] == 0.40

    def test_trending_down_relaxes_long_thresholds(self):
        """In trending-down markets, LONG strategies should get relaxed thresholds."""
        from src.strategy.strategy_templates import MarketRegime
        proposer = self._make_proposer()
        
        thresholds = proposer._get_direction_aware_thresholds('LONG', MarketRegime.TRENDING_DOWN)
        
        assert thresholds['min_return'] == -0.02
        assert thresholds['min_sharpe'] == 0.15

    def test_high_vol_relaxes_both_directions(self):
        """In high-vol markets, both directions should get slightly relaxed thresholds."""
        from src.strategy.strategy_templates import MarketRegime
        proposer = self._make_proposer()
        
        long_t = proposer._get_direction_aware_thresholds('LONG', MarketRegime.RANGING_HIGH_VOL)
        short_t = proposer._get_direction_aware_thresholds('SHORT', MarketRegime.RANGING_HIGH_VOL)
        
        # Both should be relaxed equally
        assert long_t['min_sharpe'] == short_t['min_sharpe'] == 0.2
        assert long_t['min_return'] == short_t['min_return'] == -0.01

    def test_detect_strategy_direction_from_metadata(self):
        """Direction detection should prefer metadata over rule inspection."""
        proposer = self._make_proposer()
        
        strategy = MagicMock()
        strategy.metadata = {'direction': 'SHORT'}
        strategy.rules = {}
        
        assert proposer._detect_strategy_direction(strategy) == 'SHORT'

    def test_detect_strategy_direction_from_rules_fallback(self):
        """Direction detection should fall back to rule inspection."""
        proposer = self._make_proposer()
        
        strategy = MagicMock()
        strategy.metadata = {}
        strategy.rules = {'entry_conditions': ['RSI > 70 (OVERBOUGHT)']}
        
        assert proposer._detect_strategy_direction(strategy) == 'SHORT'

    def test_detect_strategy_direction_defaults_long(self):
        """Direction detection should default to LONG."""
        proposer = self._make_proposer()
        
        strategy = MagicMock()
        strategy.metadata = {}
        strategy.rules = {'entry_conditions': ['RSI < 30']}
        
        assert proposer._detect_strategy_direction(strategy) == 'LONG'


class TestDirectionAwareActivation:
    """Test that evaluate_for_activation uses direction-aware thresholds."""

    def test_config_has_direction_aware_thresholds(self):
        """Verify the YAML config has the walk_forward_thresholds section."""
        import yaml
        config_path = Path("config/autonomous_trading.yaml")
        assert config_path.exists(), "Config file must exist"
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        da = config['backtest']['walk_forward']['direction_aware_thresholds']
        assert 'default' in da
        assert 'ranging' in da
        assert 'trending_up' in da
        assert 'trending_down' in da
        assert 'high_vol' in da
        
        # Verify ranging has per-direction overrides
        assert 'long' in da['ranging']
        assert 'short' in da['ranging']
        assert da['ranging']['long']['min_return'] == -0.02
        assert da['ranging']['short']['min_return'] == 0.0
