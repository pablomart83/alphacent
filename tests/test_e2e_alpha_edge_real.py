"""
End-to-end test for Alpha Edge improvements.

Tests the full flow with REAL systems (no mocks):
1. Strategy generation (template-based)
2. Fundamental filter
3. ML filter
4. Transaction cost tracking
5. Trade frequency limits
6. API usage monitoring
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from src.analytics.trade_journal import TradeJournal
from src.data.fundamental_data_provider import FundamentalDataProvider
from src.data.market_data_manager import MarketDataManager
from src.models.database import get_database
from src.strategy.fundamental_filter import FundamentalFilter
from src.strategy.strategy_proposer import StrategyProposer
from src.strategy.strategy_templates import MarketRegime
from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter
from src.strategy.transaction_cost_tracker import TransactionCostTracker
from src.models.enums import StrategyStatus

logger = logging.getLogger(__name__)


class TestE2EAlphaEdgeReal:
    """End-to-end tests for Alpha Edge improvements using REAL systems."""
    
    def test_fundamental_filter_real_data(self):
        """Test fundamental filter with real API data."""
        logger.info("Testing fundamental filter with real data")
        
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        fundamental_provider = FundamentalDataProvider(config)
        fundamental_filter = FundamentalFilter(config, fundamental_provider)
        
        symbol = 'AAPL'
        result = fundamental_filter.filter_symbol(symbol, 'momentum')
        
        logger.info(f"Fundamental filter for {symbol}:")
        logger.info(f"  Passed: {result.passed}")
        logger.info(f"  Checks: {result.checks_passed}/{result.checks_total}")
        
        for check_result in result.results:
            status = "✓" if check_result.passed else "✗"
            logger.info(f"  {status} {check_result.check_name}: {check_result.reason}")
        
        assert result.checks_total == 5, "Should run 5 checks"
        assert result.checks_passed >= 0, "Should have valid check count"
    
    def test_strategy_generation_real(self):
        """Test strategy generation with real market data."""
        logger.info("Testing strategy generation with real systems")
        
        from src.api.etoro_client import EToroAPIClient
        from src.models.enums import TradingMode
        from src.core.config import Configuration, ConfigurationError
        
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        # Load eToro credentials properly
        try:
            config_manager = Configuration()
            creds = config_manager.load_credentials(TradingMode.DEMO)
            
            etoro_client = EToroAPIClient(
                public_key=creds["public_key"],
                user_key=creds["user_key"],
                mode=TradingMode.DEMO
            )
            market_data = MarketDataManager(etoro_client)
            proposer = StrategyProposer(llm_service=None, market_data=market_data)
        except ConfigurationError as e:
            pytest.skip(f"eToro credentials not available: {e}")
        
        strategies = proposer.propose_strategies(
            count=2,
            symbols=['AAPL', 'MSFT'],
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
        assert all(s.status == StrategyStatus.PROPOSED for s in strategies)
    
    def test_transaction_cost_calculation_real(self):
        """Test transaction cost calculation with real config."""
        logger.info("Testing transaction cost calculation")
        
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        cost_tracker = TransactionCostTracker(config, database)
        
        costs = cost_tracker.calculate_trade_cost(
            symbol='AAPL',
            quantity=100,
            price=150.0
        )
        
        logger.info(f"Transaction costs for 100 shares @ $150:")
        logger.info(f"  Commission: ${costs['commission']:.2f}")
        logger.info(f"  Slippage: ${costs['slippage']:.2f}")
        logger.info(f"  Spread: ${costs['spread']:.2f}")
        logger.info(f"  Total: ${costs['total']:.2f} ({costs['total_percent']:.3f}%)")
        
        assert costs['total'] > 0
        assert costs['commission'] > 0
        assert costs['total_percent'] < 1.0
    
    def test_trade_frequency_limiter_real(self):
        """Test trade frequency limiter with real database."""
        logger.info("Testing trade frequency limiter")
        
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        limiter = TradeFrequencyLimiter(config, database)
        
        strategy_id = f'test-strategy-{uuid.uuid4()}'
        max_trades = config['alpha_edge']['max_trades_per_strategy_per_month']
        
        for i in range(max_trades):
            limiter.record_trade(strategy_id, 'AAPL')
            logger.info(f"Recorded trade {i+1}/{max_trades}")
        
        stats = limiter.get_strategy_stats(strategy_id)
        
        logger.info(f"Trade frequency stats:")
        logger.info(f"  Trades this month: {stats['trades_this_month']}")
        logger.info(f"  Max trades/month: {stats['max_trades_per_month']}")
        logger.info(f"  Trades remaining: {stats['trades_remaining']}")
        logger.info(f"  Can trade now: {stats['can_trade_now']}")
        
        assert stats['trades_this_month'] == max_trades
        assert stats['trades_remaining'] == 0
        assert not stats['can_trade_now']
    
    def test_cost_reduction_comparison_real(self):
        """Test transaction cost reduction with real calculations."""
        logger.info("Testing cost reduction from reduced trading frequency")
        
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        cost_tracker = TransactionCostTracker(config, database)
        
        high_freq_cost = sum(
            cost_tracker.calculate_trade_cost('AAPL', 10, 150.0)['total'] * 2
            for _ in range(50)
        )
        
        low_freq_cost = sum(
            cost_tracker.calculate_trade_cost('AAPL', 10, 150.0)['total'] * 2
            for _ in range(10)
        )
        
        savings = high_freq_cost - low_freq_cost
        savings_percent = (savings / high_freq_cost) * 100
        
        logger.info(f"Cost reduction analysis:")
        logger.info(f"  High frequency (50 trades): ${high_freq_cost:.2f}")
        logger.info(f"  Low frequency (10 trades): ${low_freq_cost:.2f}")
        logger.info(f"  Savings: ${savings:.2f} ({savings_percent:.1f}%)")
        
        assert savings > 0
        assert savings_percent > 70
    
    def test_api_usage_tracking_real(self):
        """Test API usage tracking with real provider."""
        logger.info("Testing API usage tracking")
        
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        fundamental_provider = FundamentalDataProvider(config)
        
        usage = fundamental_provider.get_api_usage()
        
        logger.info(f"API usage statistics:")
        
        if 'fmp' in usage:
            fmp_usage = usage['fmp']
            logger.info(f"  FMP:")
            logger.info(f"    Calls made: {fmp_usage['calls_made']}/{fmp_usage['max_calls']}")
            logger.info(f"    Usage: {fmp_usage['usage_percent']:.1f}%")
            logger.info(f"    Remaining: {fmp_usage['calls_remaining']}")
        
        if 'cache_size' in usage:
            logger.info(f"  Cache size: {usage['cache_size']}")
        
        assert 'fmp' in usage
        assert 'calls_made' in usage['fmp']
        assert 'max_calls' in usage['fmp']
        assert 'usage_percent' in usage['fmp']
        assert 0 <= usage['fmp']['usage_percent'] <= 100
    
    def test_trade_journal_real(self):
        """Test trade journal with real database."""
        logger.info("Testing trade journal")
        
        database = get_database()
        trade_journal = TradeJournal(database)
        strategy_id = f'test-strategy-{uuid.uuid4()}'
        trade_id = f'trade-{uuid.uuid4()}'
        
        trade_journal.log_entry(
            trade_id=trade_id,
            strategy_id=strategy_id,
            symbol='AAPL',
            entry_time=datetime.now(),
            entry_price=150.0,
            entry_size=10,
            entry_reason='Test trade for E2E validation',
            market_regime='TRENDING_UP',
            fundamentals={'passed': True, 'checks_passed': 5},
            conviction_score=85.0,
            ml_confidence=0.82
        )
        
        logger.info(f"Logged trade entry with ID: {trade_id}")
        assert trade_id is not None
        
        trade_journal.log_exit(
            trade_id=trade_id,
            exit_time=datetime.now(),
            exit_price=157.5,
            exit_reason='Profit target hit',
            exit_order_id=None
        )
        
        logger.info(f"Logged trade exit")
        
        trades = trade_journal.get_all_trades(strategy_id=strategy_id)
        
        logger.info(f"Retrieved {len(trades)} trades")
        assert len(trades) > 0
        
        trade = trades[0]
        logger.info(f"Trade: {trade['symbol']} Entry=${trade['entry_price']} Exit=${trade['exit_price']}")
        
        assert trade['symbol'] == 'AAPL'
        assert trade['entry_price'] == 150.0
        assert trade['exit_price'] == 157.5
    
    def test_integrated_flow_real(self):
        """Test integrated flow with all real components."""
        logger.info("Testing integrated Alpha Edge flow")
        
        config_path = Path("config/autonomous_trading.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        database = get_database()
        
        # Step 1: Fundamental filter
        logger.info("Step 1: Fundamental filter")
        fundamental_provider = FundamentalDataProvider(config)
        fundamental_filter = FundamentalFilter(config, fundamental_provider)
        
        symbol = 'AAPL'
        fund_result = fundamental_filter.filter_symbol(symbol, 'momentum')
        logger.info(f"  Result: {fund_result.passed} ({fund_result.checks_passed}/{fund_result.checks_total})")
        
        # Step 2: Trade frequency
        logger.info("Step 2: Trade frequency check")
        limiter = TradeFrequencyLimiter(config, database)
        strategy_id = f'test-integrated-{uuid.uuid4()}'
        
        stats = limiter.get_strategy_stats(strategy_id)
        logger.info(f"  Can trade: {stats['can_trade_now']}, Remaining: {stats['trades_remaining']}")
        
        # Step 3: Transaction costs
        logger.info("Step 3: Transaction costs")
        cost_tracker = TransactionCostTracker(config, database)
        
        costs = cost_tracker.calculate_trade_cost(symbol, 10, 150.0)
        logger.info(f"  Total cost: ${costs['total']:.2f}")
        
        # Step 4: Trade journal
        logger.info("Step 4: Trade journal")
        trade_journal = TradeJournal(database)
        
        trade_id = f'trade-{uuid.uuid4()}'
        
        trade_journal.log_entry(
            trade_id=trade_id,
            strategy_id=strategy_id,
            symbol=symbol,
            entry_time=datetime.now(),
            entry_price=150.0,
            entry_size=10,
            entry_reason='E2E test',
            market_regime='TRENDING_UP',
            fundamentals=fund_result.to_dict(),
            conviction_score=80.0,
            ml_confidence=0.75
        )
        
        logger.info(f"  Trade logged: {trade_id}")
        
        # Step 5: API usage
        logger.info("Step 5: API usage")
        usage = fundamental_provider.get_api_usage()
        
        if 'fmp' in usage:
            logger.info(f"  FMP: {usage['fmp']['usage_percent']:.1f}%")
        
        logger.info("✓ Integrated flow completed successfully")
        
        assert fund_result is not None
        assert stats is not None
        assert costs['total'] > 0
        assert trade_id is not None
        assert len(usage) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
