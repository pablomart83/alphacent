"""
Test timeframe-aware overfitting detection in walk_forward_validate.

This test verifies that the walk_forward_validate function correctly applies
timeframe-aware degradation thresholds based on the strategy's interval.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
from src.strategy.strategy_engine import StrategyEngine
from src.models.dataclasses import Strategy, RiskConfig, BacktestResults


class TestTimeframeAwareOverfitting:
    """Test timeframe-aware overfitting detection."""
    
    def create_mock_strategy(self, interval='1d'):
        """Create a mock strategy with specified interval."""
        strategy = Mock(spec=Strategy)
        strategy.name = f"Test-{interval}"
        strategy.symbols = ["AAPL"]
        strategy.metadata = {'interval': interval}
        strategy.risk_config = RiskConfig()
        return strategy
    
    def create_mock_backtest_results(self, sharpe_ratio, total_return=0.1, total_trades=10):
        """Create mock backtest results."""
        results = Mock(spec=BacktestResults)
        results.sharpe_ratio = sharpe_ratio
        results.total_return = total_return
        results.total_trades = total_trades
        results.max_drawdown = 0.1
        results.win_rate = 0.5
        results.avg_win = 0.02
        results.avg_loss = -0.01
        results.metadata = {}
        return results
    
    @patch('src.strategy.strategy_engine.StrategyEngine.backtest_strategy')
    def test_hourly_strategy_uses_40_percent_threshold(self, mock_backtest):
        """Test that hourly strategies use 40% degradation threshold."""
        # Setup
        strategy_engine = StrategyEngine(Mock(), Mock())
        strategy = self.create_mock_strategy(interval='1h')
        
        # Train results: Sharpe 1.0
        # Test results: Sharpe 0.45 (45% of train, above 40% threshold)
        train_results = self.create_mock_backtest_results(sharpe_ratio=1.0)
        test_results = self.create_mock_backtest_results(sharpe_ratio=0.45)
        
        mock_backtest.side_effect = [train_results, test_results]
        
        # Execute with explicit train/test days to avoid data requirement issues
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        result = strategy_engine.walk_forward_validate(strategy, start, end, train_days=60, test_days=30)
        
        # Verify: Should NOT be overfitted (0.45 >= 1.0 * 0.4)
        assert result['is_overfitted'] == False, "Hourly strategy with 45% degradation should not be overfitted"
        assert result['test_sharpe'] == 0.45
        assert result['train_sharpe'] == 1.0
    
    @patch('src.strategy.strategy_engine.StrategyEngine.backtest_strategy')
    def test_hourly_strategy_below_40_percent_is_overfitted(self, mock_backtest):
        """Test that hourly strategies below 40% threshold are marked as overfitted."""
        # Setup
        strategy_engine = StrategyEngine(Mock(), Mock())
        strategy = self.create_mock_strategy(interval='1h')
        
        # Train results: Sharpe 1.0
        # Test results: Sharpe 0.35 (35% of train, below 40% threshold)
        train_results = self.create_mock_backtest_results(sharpe_ratio=1.0)
        test_results = self.create_mock_backtest_results(sharpe_ratio=0.35)
        
        mock_backtest.side_effect = [train_results, test_results]
        
        # Execute with explicit train/test days
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        result = strategy_engine.walk_forward_validate(strategy, start, end, train_days=60, test_days=30)
        
        # Verify: Should be overfitted (0.35 < 1.0 * 0.4)
        assert result['is_overfitted'] == True, "Hourly strategy with 35% degradation should be overfitted"
    
    @patch('src.strategy.strategy_engine.StrategyEngine.backtest_strategy')
    def test_intraday_strategy_uses_50_percent_threshold(self, mock_backtest):
        """Test that intraday strategies use 50% degradation threshold."""
        # Setup
        strategy_engine = StrategyEngine(Mock(), Mock())
        strategy = self.create_mock_strategy(interval='15m')
        
        # Train results: Sharpe 2.0
        # Test results: Sharpe 1.1 (55% of train, above 50% threshold)
        train_results = self.create_mock_backtest_results(sharpe_ratio=2.0)
        test_results = self.create_mock_backtest_results(sharpe_ratio=1.1)
        
        mock_backtest.side_effect = [train_results, test_results]
        
        # Execute with explicit train/test days
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        result = strategy_engine.walk_forward_validate(strategy, start, end, train_days=60, test_days=30)
        
        # Verify: Should NOT be overfitted (1.1 >= 2.0 * 0.5)
        assert result['is_overfitted'] == False, "Intraday strategy with 55% degradation should not be overfitted"
    
    @patch('src.strategy.strategy_engine.StrategyEngine.backtest_strategy')
    def test_intraday_strategy_below_50_percent_is_overfitted(self, mock_backtest):
        """Test that intraday strategies below 50% threshold are marked as overfitted."""
        # Setup
        strategy_engine = StrategyEngine(Mock(), Mock())
        strategy = self.create_mock_strategy(interval='30m')
        
        # Train results: Sharpe 2.0
        # Test results: Sharpe 0.9 (45% of train, below 50% threshold)
        train_results = self.create_mock_backtest_results(sharpe_ratio=2.0)
        test_results = self.create_mock_backtest_results(sharpe_ratio=0.9)
        
        mock_backtest.side_effect = [train_results, test_results]
        
        # Execute with explicit train/test days
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        result = strategy_engine.walk_forward_validate(strategy, start, end, train_days=60, test_days=30)
        
        # Verify: Should be overfitted (0.9 < 2.0 * 0.5)
        assert result['is_overfitted'] == True, "Intraday strategy with 45% degradation should be overfitted"
    
    @patch('src.strategy.strategy_engine.StrategyEngine.backtest_strategy')
    def test_daily_strategy_uses_30_percent_threshold(self, mock_backtest):
        """Test that daily strategies use 30% degradation threshold (existing behavior)."""
        # Setup
        strategy_engine = StrategyEngine(Mock(), Mock())
        strategy = self.create_mock_strategy(interval='1d')
        
        # Train results: Sharpe 1.0
        # Test results: Sharpe 0.35 (35% of train, above 30% threshold)
        train_results = self.create_mock_backtest_results(sharpe_ratio=1.0)
        test_results = self.create_mock_backtest_results(sharpe_ratio=0.35)
        
        mock_backtest.side_effect = [train_results, test_results]
        
        # Execute with explicit train/test days
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        result = strategy_engine.walk_forward_validate(strategy, start, end, train_days=60, test_days=30)
        
        # Verify: Should NOT be overfitted (0.35 >= 1.0 * 0.3)
        assert result['is_overfitted'] == False, "Daily strategy with 35% degradation should not be overfitted"
    
    @patch('src.strategy.strategy_engine.StrategyEngine.backtest_strategy')
    def test_daily_strategy_below_30_percent_is_overfitted(self, mock_backtest):
        """Test that daily strategies below 30% threshold are marked as overfitted."""
        # Setup
        strategy_engine = StrategyEngine(Mock(), Mock())
        strategy = self.create_mock_strategy(interval='1d')
        
        # Train results: Sharpe 1.0
        # Test results: Sharpe 0.25 (25% of train, below 30% threshold)
        train_results = self.create_mock_backtest_results(sharpe_ratio=1.0)
        test_results = self.create_mock_backtest_results(sharpe_ratio=0.25)
        
        mock_backtest.side_effect = [train_results, test_results]
        
        # Execute with explicit train/test days
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        result = strategy_engine.walk_forward_validate(strategy, start, end, train_days=60, test_days=30)
        
        # Verify: Should be overfitted (0.25 < 1.0 * 0.3)
        assert result['is_overfitted'] == True, "Daily strategy with 25% degradation should be overfitted"
    
    @patch('src.strategy.strategy_engine.StrategyEngine.backtest_strategy')
    def test_4h_strategy_uses_30_percent_threshold(self, mock_backtest):
        """Test that 4H strategies use 30% degradation threshold (preservation)."""
        # Setup
        strategy_engine = StrategyEngine(Mock(), Mock())
        strategy = self.create_mock_strategy(interval='4h')
        
        # Train results: Sharpe 1.0
        # Test results: Sharpe 0.35 (35% of train, above 30% threshold)
        train_results = self.create_mock_backtest_results(sharpe_ratio=1.0)
        test_results = self.create_mock_backtest_results(sharpe_ratio=0.35)
        
        mock_backtest.side_effect = [train_results, test_results]
        
        # Execute with explicit train/test days
        start = datetime(2023, 1, 1)
        end = datetime(2024, 1, 1)
        result = strategy_engine.walk_forward_validate(strategy, start, end, train_days=60, test_days=30)
        
        # Verify: Should NOT be overfitted (0.35 >= 1.0 * 0.3)
        assert result['is_overfitted'] == False, "4H strategy with 35% degradation should not be overfitted"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
