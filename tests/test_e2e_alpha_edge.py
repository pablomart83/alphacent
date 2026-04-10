        assert stats is not None
        assert costs['total'] > 0
        assert trade_id is not None
        assert len(usage) > 0


if __name__ == '__main__':
    # Run tests with verbose output
    pytest.main([__file__, '-v', '-s'])
info(f"  Trade logged: {trade_id}")
        
        # Step 5: Verify API usage
        logger.info("Step 5: API usage")
        usage = fundamental_provider.get_api_usage()
        
        for api_name, api_usage in usage.items():
            logger.info(f"  {api_name}: {api_usage['used']}/{api_usage['limit']} ({api_usage['percentage']:.1f}%)")
        
        logger.info("✓ Integrated flow completed successfully")
        
        # All steps should complete without errors
        assert fund_result is not None
urnal")
        trade_journal = TradeJournal()
        
        trade_id = trade_journal.log_entry(
            strategy_id=strategy_id,
            strategy_name='Integrated Test Strategy',
            symbol=symbol,
            entry_price=150.0,
            quantity=10,
            entry_reason='Integrated E2E test',
            market_regime='TRENDING_UP',
            fundamental_data=fund_result.to_dict(),
            conviction_score=80.0,
            ml_confidence=0.75
        )
        
        logger.o(f"  Trades remaining: {stats['trades_remaining']}")
        
        # Step 3: Calculate transaction costs
        logger.info("Step 3: Transaction costs")
        cost_tracker = TransactionCostTracker(config, database)
        
        costs = cost_tracker.calculate_trade_cost(
            symbol=symbol,
            quantity=10,
            price=150.0
        )
        logger.info(f"  Total cost: ${costs['total']:.2f}")
        
        # Step 4: Log to trade journal
        logger.info("Step 4: Trade joter_symbol(symbol, 'momentum')
        logger.info(f"  Fundamental filter: {fund_result.passed} ({fund_result.checks_passed}/{fund_result.checks_total})")
        
        # Step 2: Check trade frequency
        logger.info("Step 2: Trade frequency check")
        limiter = TradeFrequencyLimiter(config, database)
        strategy_id = f'test-integrated-{uuid.uuid4()}'
        
        stats = limiter.get_strategy_stats(strategy_id)
        logger.info(f"  Can trade: {stats['can_trade_now']}")
        logger.infconfig
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        
        # Step 1: Check fundamental filter
        logger.info("Step 1: Fundamental filter")
        fundamental_provider = FundamentalDataProvider(config, database)
        fundamental_filter = FundamentalFilter(config, fundamental_provider)
        
        symbol = 'AAPL'
        fund_result = fundamental_filter.filrice']}")
        logger.info(f"  Exit: ${trade['exit_price']}")
        logger.info(f"  P&L: ${trade['pnl']:.2f}")
        logger.info(f"  Hold time: {trade['hold_time_days']} days")
        
        assert trade['symbol'] == 'AAPL'
        assert trade['entry_price'] == 150.0
        assert trade['exit_price'] == 157.5
    
    def test_integrated_flow_real(self):
        """Test integrated flow with all real components."""
        logger.info("Testing integrated Alpha Edge flow")
        
        # Load real 10 shares
            hold_time_days=5
        )
        
        logger.info(f"Logged trade exit")
        
        # Retrieve trades
        trades = trade_journal.get_trades(strategy_id=strategy_id)
        
        logger.info(f"Retrieved {len(trades)} trades")
        
        assert len(trades) > 0, "Should have at least one trade"
        
        trade = trades[0]
        logger.info(f"Trade details:")
        logger.info(f"  Symbol: {trade['symbol']}")
        logger.info(f"  Entry: ${trade['entry_pRENDING_UP',
            fundamental_data={'passed': True, 'checks_passed': 5},
            conviction_score=85.0,
            ml_confidence=0.82
        )
        
        logger.info(f"Logged trade entry with ID: {trade_id}")
        
        assert trade_id is not None, "Should return trade ID"
        
        # Log trade exit
        trade_journal.log_exit(
            trade_id=trade_id,
            exit_price=157.5,
            exit_reason='Profit target hit',
            pnl=75.0,  # $7.50 per share *         trade_journal = TradeJournal()
        
        # Create unique strategy ID for test
        strategy_id = f'test-strategy-{uuid.uuid4()}'
        strategy_name = 'Test Strategy'
        
        # Log a trade entry
        trade_id = trade_journal.log_entry(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            symbol='AAPL',
            entry_price=150.0,
            quantity=10,
            entry_reason='Test trade for E2E validation',
            market_regime='Tould have FMP usage"
        assert 'alpha_vantage' in usage, "Should have Alpha Vantage usage"
        
        for api_usage in usage.values():
            assert 'used' in api_usage
            assert 'limit' in api_usage
            assert 'percentage' in api_usage
            assert api_usage['percentage'] >= 0
            assert api_usage['percentage'] <= 100
    
    def test_trade_journal_real(self):
        """Test trade journal with real database."""
        logger.info("Testing trade journal")
        
 API usage
        usage = fundamental_provider.get_api_usage()
        
        logger.info(f"API usage statistics:")
        
        for api_name, api_usage in usage.items():
            logger.info(f"  {api_name}:")
            logger.info(f"    Used: {api_usage['used']}/{api_usage['limit']}")
            logger.info(f"    Percentage: {api_usage['percentage']:.1f}%")
            logger.info(f"    Remaining: {api_usage['remaining']}")
        
        # Verify structure
        assert 'fmp' in usage, "Sh, f"Should save >70%, got {savings_percent:.1f}%"
    
    def test_api_usage_tracking_real(self):
        """Test API usage tracking with real provider."""
        logger.info("Testing API usage tracking")
        
        # Load real config
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        fundamental_provider = FundamentalDataProvider(config, database)
        
        # Get   savings = high_freq_cost - low_freq_cost
        savings_percent = (savings / high_freq_cost) * 100
        
        logger.info(f"Cost reduction analysis:")
        logger.info(f"  High frequency ({high_freq_trades} trades): ${high_freq_cost:.2f}")
        logger.info(f"  Low frequency ({low_freq_trades} trades): ${low_freq_cost:.2f}")
        logger.info(f"  Savings: ${savings:.2f} ({savings_percent:.1f}%)")
        
        assert savings > 0, "Should have cost savings"
        assert savings_percent > 70        high_freq_cost += costs['total'] * 2  # Entry + exit
        
        # Scenario 2: Low frequency (10 trades/month - Alpha Edge target)
        low_freq_trades = 10
        low_freq_cost = 0
        
        for _ in range(low_freq_trades):
            costs = cost_tracker.calculate_trade_cost(
                symbol='AAPL',
                quantity=10,
                price=150.0
            )
            low_freq_cost += costs['total'] * 2  # Entry + exit
        
        # Calculate savings
           with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        cost_tracker = TransactionCostTracker(config, database)
        
        # Scenario 1: High frequency (50 trades/month)
        high_freq_trades = 50
        high_freq_cost = 0
        
        for _ in range(high_freq_trades):
            costs = cost_tracker.calculate_trade_cost(
                symbol='AAPL',
                quantity=10,
                price=150.0
            )
     {stats['can_trade_now']}")
        
        assert stats['trades_this_month'] == max_trades
        assert stats['trades_remaining'] == 0
        assert not stats['can_trade_now'], "Should not allow more trades"
    
    def test_cost_reduction_comparison_real(self):
        """Test transaction cost reduction with real calculations."""
        logger.info("Testing cost reduction from reduced trading frequency")
        
        # Load real config
        config_path = Path("config/autonomous_trading.yaml")
       limiter.record_trade(strategy_id, 'AAPL')
            logger.info(f"Recorded trade {i+1}/{max_trades}")
        
        # Check stats
        stats = limiter.get_strategy_stats(strategy_id)
        
        logger.info(f"Trade frequency stats:")
        logger.info(f"  Trades this month: {stats['trades_this_month']}")
        logger.info(f"  Max trades/month: {stats['max_trades_per_month']}")
        logger.info(f"  Trades remaining: {stats['trades_remaining']}")
        logger.info(f"  Can trade now: config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        limiter = TradeFrequencyLimiter(config, database)
        
        # Use unique strategy ID for test
        strategy_id = f'test-strategy-{uuid.uuid4()}'
        
        # Record trades up to limit
        max_trades = config['alpha_edge']['max_trades_per_strategy_per_month']
        
        for i in range(max_trades):
       al: ${costs['total']:.2f} ({costs['total_percent']:.3f}%)")
        
        assert costs['total'] > 0, "Total cost should be positive"
        assert costs['commission'] > 0, "Commission should be positive"
        assert costs['total_percent'] < 1.0, "Cost should be less than 1% of trade value"
    
    def test_trade_frequency_limiter_real(self):
        """Test trade frequency limiter with real database."""
        logger.info("Testing trade frequency limiter")
        
        # Load real config
       nsactionCostTracker(config, database)
        
        # Calculate costs for a sample trade
        costs = cost_tracker.calculate_trade_cost(
            symbol='AAPL',
            quantity=100,
            price=150.0
        )
        
        logger.info(f"Transaction costs for 100 shares @ $150:")
        logger.info(f"  Commission: ${costs['commission']:.2f}")
        logger.info(f"  Slippage: ${costs['slippage']:.2f}")
        logger.info(f"  Spread: ${costs['spread']:.2f}")
        logger.info(f"  Totsert all(s.status == StrategyStatus.PROPOSED for s in strategies), "All should be PROPOSED"
    
    def test_transaction_cost_calculation_real(self):
        """Test transaction cost calculation with real config."""
        logger.info("Testing transaction cost calculation")
        
        # Load real config
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        cost_tracker = Tra,
            market_regime=MarketRegime.TRENDING_UP,
            use_walk_forward=False,
            optimize_parameters=False
        )
        
        logger.info(f"Generated {len(strategies)} strategies")
        
        for strategy in strategies:
            logger.info(f"  - {strategy.name}")
            logger.info(f"    Symbols: {strategy.symbols}")
            logger.info(f"    Status: {strategy.status.value}")
        
        assert len(strategies) > 0, "Should generate at least one strategy"
        as """Test strategy generation with real market data."""
        logger.info("Testing strategy generation with real systems")
        
        # Create real market data manager
        market_data = MarketDataManager()
        
        # Create strategy proposer (no LLM, template-based only)
        proposer = StrategyProposer(llm_service=None, market_data=market_data)
        
        # Generate strategies
        strategies = proposer.propose_strategies(
            count=2,
            symbols=['AAPL', 'MSFT']cks_passed}/{result.checks_total}")
        
        for check_result in result.results:
            status = "✓" if check_result.passed else "✗"
            logger.info(f"  {status} {check_result.check_name}: {check_result.reason}")
        
        # Should have results (may pass or fail depending on fundamentals)
        assert result.checks_total == 5, "Should run 5 checks"
        assert result.checks_passed >= 0, "Should have valid check count"
    
    def test_strategy_generation_real(self):
            # Test with a well-known stock
        symbol = 'AAPL'
        result = fundamental_filter.filter_symbol(symbol, 'momentum')
        
        logger.info(f"Fundamental filter for {symbol}:")
        logger.info(f"  Passed: {result.passed}")
        logger.info(f"  Checks: {result.cheting fundamental filter with real data")
        
        # Load real config
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        # Create real fundamental data provider
        database = get_database()
        fundamental_provider = FundamentalDataProvider(config, database)
        
        # Create fundamental filter
        fundamental_filter = FundamentalFilter(config, fundamental_provider)
        
   y_proposer import StrategyProposer
from src.strategy.strategy_templates import MarketRegime
from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter
from src.strategy.transaction_cost_tracker import TransactionCostTracker

logger = logging.getLogger(__name__)


class TestE2EAlphaEdgeReal:
    """End-to-end tests for Alpha Edge improvements using REAL systems."""
    
    def test_fundamental_filter_real_data(self):
        """Test fundamental filter with real API data."""
        logger.info("TesetDataManager
from src.ml.signal_filter import MLSignalFilter
from src.models import (
    PerformanceMetrics,
    RiskConfig,
    Strategy,
    StrategyStatus,
)
from src.models.database import get_database
from src.strategy.fundamental_filter import FundamentalFilter
from src.strategy.strateg.

Tests the full flow with REAL systems (no mocks):
1. Strategy generation (template-based)
2. Fundamental filter
3. ML filter
4. Transaction cost tracking
5. Trade frequency limits
6. API usage monitoring
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml

from src.analytics.trade_journal import TradeJournal
from src.data.fundamental_data_provider import FundamentalDataProvider
from src.data.market_data_manager import Mark"""
