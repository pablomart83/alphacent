"""
Test Portfolio-Wide Risk Management Features.

Tests:
1. Portfolio stop-loss (10% total loss limit)
2. Daily loss limit (3% daily loss limit)
3. Exposure limits (total, per-symbol, per-strategy)
4. Correlation-based position sizing
"""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.api.etoro_client import EToroAPIClient
from src.core.config import get_config
from src.data.market_data_manager import MarketDataManager
from src.llm.llm_service import LLMService
from src.models.database import Database
from src.models.enums import TradingMode, PositionSide
from src.models.orm import PositionORM
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def initialize_test_components():
    """Initialize real components for testing (no mocks)."""
    db = Database()
    config_manager = get_config()
    
    # Initialize eToro client (real, not mock)
    try:
        credentials = config_manager.load_credentials(TradingMode.DEMO)
        etoro_client = EToroAPIClient(
            public_key=credentials['public_key'],
            user_key=credentials['user_key'],
            mode=TradingMode.DEMO
        )
    except Exception as e:
        logger.warning(f"Could not initialize eToro client: {e}")
        logger.info("Tests will continue without eToro client")
        # Create a minimal client that won't be used in these tests
        etoro_client = None
    
    # Initialize services
    llm_service = LLMService()
    market_data = MarketDataManager(etoro_client=etoro_client)
    
    # Initialize strategy engine
    strategy_engine = StrategyEngine(
        llm_service=llm_service,
        market_data=market_data
    )
    
    return db, strategy_engine


def test_portfolio_stop_loss():
    """Test Part 1: Portfolio stop-loss and daily loss limits."""
    logger.info("=" * 80)
    logger.info("TEST 1: Portfolio Stop-Loss and Daily Loss Limits")
    logger.info("=" * 80)
    
    try:
        # Initialize components
        logger.info("\n[1/5] Initializing components...")
        db, strategy_engine = initialize_test_components()
        
        # Initialize portfolio manager with custom limits
        portfolio_manager = PortfolioManager(
            strategy_engine=strategy_engine,
            portfolio_stop_loss_pct=0.10,  # 10% stop-loss
            daily_loss_limit_pct=0.03      # 3% daily limit
        )
        
        logger.info("   ✓ Components initialized")
        
        # Test 1: Set initial portfolio value
        logger.info("\n[2/5] Testing initial portfolio value setup...")
        initial_value = 100000.0
        portfolio_manager.set_initial_portfolio_value(initial_value)
        
        assert portfolio_manager.initial_portfolio_value == initial_value
        assert portfolio_manager.daily_start_value == initial_value
        assert portfolio_manager.daily_reset_date == datetime.now().date()
        logger.info(f"   ✓ Initial value set: ${initial_value:,.2f}")
        
        # Test 2: Check portfolio stop-loss NOT triggered (5% loss)
        logger.info("\n[3/5] Testing portfolio stop-loss NOT triggered (5% loss)...")
        # Don't reset daily tracking - keep it at $100k
        current_value = 95000.0  # 5% loss from initial, but still within 10% stop-loss
        should_pause, reason = portfolio_manager.check_portfolio_stop_loss(current_value)
        
        # Note: This will trigger daily loss limit (5% > 3%), but not portfolio stop-loss (5% < 10%)
        # For this test, we want to check that 5% loss doesn't trigger portfolio stop-loss
        # So we need to test with a value that's within daily limit
        portfolio_manager.set_initial_portfolio_value(100000.0)  # Reset
        current_value = 98000.0  # 2% loss - within both limits
        should_pause, reason = portfolio_manager.check_portfolio_stop_loss(current_value)
        
        assert not should_pause, "Should not pause with 2% loss"
        assert reason is None
        logger.info(f"   ✓ Trading allowed with 2% loss (${current_value:,.2f})")
        
        # Test 3: Check portfolio stop-loss TRIGGERED (12% loss)
        logger.info("\n[4/5] Testing portfolio stop-loss TRIGGERED (12% loss)...")
        current_value = 88000.0  # 12% loss
        should_pause, reason = portfolio_manager.check_portfolio_stop_loss(current_value)
        
        assert should_pause, "Should pause with 12% loss"
        assert reason is not None
        assert "Portfolio stop-loss triggered" in reason
        logger.info(f"   ✓ Stop-loss triggered: {reason}")
        
        # Test 4: Check daily loss limit TRIGGERED (4% daily loss)
        logger.info("\n[5/5] Testing daily loss limit TRIGGERED (4% daily loss)...")
        portfolio_manager.set_initial_portfolio_value(100000.0)  # Reset
        portfolio_manager.daily_start_value = 100000.0
        current_value = 96000.0  # 4% daily loss
        should_pause, reason = portfolio_manager.check_portfolio_stop_loss(current_value)
        
        assert should_pause, "Should pause with 4% daily loss"
        assert reason is not None
        assert "Daily loss limit triggered" in reason
        logger.info(f"   ✓ Daily limit triggered: {reason}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ TEST 1 PASSED: Portfolio Stop-Loss")
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST 1 FAILED: {e}", exc_info=True)
        return False


def test_exposure_limits():
    """Test Part 2: Exposure limits (total, per-symbol, per-strategy)."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Exposure Limits")
    logger.info("=" * 80)
    
    try:
        # Initialize components
        logger.info("\n[1/6] Initializing components...")
        db, strategy_engine = initialize_test_components()
        
        # Initialize portfolio manager
        portfolio_manager = PortfolioManager(
            strategy_engine=strategy_engine
        )
        
        logger.info("   ✓ Components initialized")
        
        # Create mock open positions in database
        logger.info("\n[2/6] Creating mock positions...")
        session = db.get_session()
        try:
            # Clear existing positions
            session.query(PositionORM).delete()
            session.commit()
            
            # Add position 1: SPY, $40,000 (40% of $100k portfolio)
            pos1 = PositionORM(
                id="pos_1",
                strategy_id="strategy_1",
                symbol="SPY",
                side=PositionSide.LONG,
                quantity=100,
                entry_price=400.0,  # $40,000 total
                current_price=400.0,  # Same as entry for simplicity
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                etoro_position_id="etoro_pos_1",
                opened_at=datetime.now()
            )
            session.add(pos1)
            
            # Add position 2: QQQ, $30,000 (30% of portfolio)
            pos2 = PositionORM(
                id="pos_2",
                strategy_id="strategy_1",
                symbol="QQQ",
                side=PositionSide.LONG,
                quantity=100,
                entry_price=300.0,  # $30,000 total
                current_price=300.0,  # Same as entry for simplicity
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                etoro_position_id="etoro_pos_2",
                opened_at=datetime.now()
            )
            session.add(pos2)
            
            session.commit()
            logger.info("   ✓ Created 2 mock positions (SPY: $40k, QQQ: $30k)")
            
        finally:
            session.close()
        
        portfolio_value = 100000.0
        
        # Test 1: Check current exposures
        logger.info("\n[3/6] Testing current exposure calculation...")
        exposures = portfolio_manager.get_current_exposures(portfolio_value)
        
        assert exposures['total_exposure'] == 70000.0, f"Expected $70k, got ${exposures['total_exposure']:,.2f}"
        assert exposures['total_exposure_pct'] == 0.70, f"Expected 70%, got {exposures['total_exposure_pct']:.0%}"
        assert exposures['symbol_exposure']['SPY'] == 40000.0
        assert exposures['symbol_exposure']['QQQ'] == 30000.0
        logger.info(f"   ✓ Current exposure: ${exposures['total_exposure']:,.2f} ({exposures['total_exposure_pct']:.0%})")
        
        # Test 2: Check total exposure limit (would exceed 100%)
        logger.info("\n[4/6] Testing total exposure limit (would exceed 100%)...")
        is_allowed, reason = portfolio_manager.check_exposure_limits(
            new_trade_symbol="AAPL",
            new_trade_value=35000.0,  # Would bring total to 105%
            new_trade_strategy_id="strategy_2",
            portfolio_value=portfolio_value
        )
        
        assert not is_allowed, "Should reject trade that exceeds 100% exposure"
        assert "Total exposure limit exceeded" in reason
        logger.info(f"   ✓ Trade rejected: {reason}")
        
        # Test 3: Check per-symbol exposure limit (would exceed 20%)
        logger.info("\n[5/6] Testing per-symbol exposure limit (would exceed 20%)...")
        is_allowed, reason = portfolio_manager.check_exposure_limits(
            new_trade_symbol="SPY",  # Already have $40k
            new_trade_value=5000.0,  # Would bring SPY to 45% (> 20% limit)
            new_trade_strategy_id="strategy_2",
            portfolio_value=portfolio_value
        )
        
        assert not is_allowed, "Should reject trade that exceeds 20% per-symbol limit"
        assert "Per-symbol exposure limit exceeded" in reason
        logger.info(f"   ✓ Trade rejected: {reason}")
        
        # Test 4: Check per-strategy exposure limit (would exceed 30%)
        logger.info("\n[6/6] Testing per-strategy exposure limit (would exceed 30%)...")
        is_allowed, reason = portfolio_manager.check_exposure_limits(
            new_trade_symbol="DIA",
            new_trade_value=5000.0,  # Would bring strategy_1 to 75% (> 30% limit)
            new_trade_strategy_id="strategy_1",  # Already has $70k
            portfolio_value=portfolio_value
        )
        
        assert not is_allowed, "Should reject trade that exceeds 30% per-strategy limit"
        assert "Per-strategy exposure limit exceeded" in reason
        logger.info(f"   ✓ Trade rejected: {reason}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ TEST 2 PASSED: Exposure Limits")
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST 2 FAILED: {e}", exc_info=True)
        return False


def test_correlation_based_position_sizing():
    """Test Part 3: Correlation-based position sizing."""
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Correlation-Based Position Sizing")
    logger.info("=" * 80)
    
    try:
        # Initialize components
        logger.info("\n[1/5] Initializing components...")
        db, strategy_engine = initialize_test_components()
        
        # Initialize portfolio manager
        portfolio_manager = PortfolioManager(
            strategy_engine=strategy_engine
        )
        
        logger.info("   ✓ Components initialized")
        
        # Create mock open positions
        logger.info("\n[2/5] Creating mock positions...")
        session = db.get_session()
        try:
            # Clear existing positions
            session.query(PositionORM).delete()
            session.commit()
            
            # Add 3 positions in SPY (same symbol = perfect correlation)
            for i in range(3):
                pos = PositionORM(
                    id=f"pos_{i+1}",
                    strategy_id=f"strategy_{i+1}",
                    symbol="SPY",
                    side=PositionSide.LONG,
                    quantity=100,
                    entry_price=400.0,
                    current_price=400.0,  # Same as entry for simplicity
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    etoro_position_id=f"etoro_pos_{i+1}",
                    opened_at=datetime.now()
                )
                session.add(pos)
            
            session.commit()
            logger.info("   ✓ Created 3 positions in SPY (highly correlated)")
            
        finally:
            session.close()
        
        # Test 1: Find correlated positions (same symbol)
        logger.info("\n[3/5] Testing correlated position detection...")
        correlated = portfolio_manager.get_correlated_positions(
            new_trade_symbol="SPY",
            new_trade_strategy_id="strategy_4",
            correlation_threshold=0.7
        )
        
        assert len(correlated) == 3, f"Expected 3 correlated positions, got {len(correlated)}"
        assert all(pos['symbol'] == 'SPY' for pos in correlated)
        assert all(pos['correlation'] == 1.0 for pos in correlated)
        logger.info(f"   ✓ Found {len(correlated)} correlated positions (all SPY)")
        
        # Test 2: Calculate adjusted position size (3+ correlated = 33%)
        logger.info("\n[4/5] Testing position size adjustment (3+ correlated)...")
        base_size = 10000.0
        adjusted_size, reason = portfolio_manager.calculate_correlation_adjusted_size(
            base_position_size=base_size,
            new_trade_symbol="SPY",
            new_trade_strategy_id="strategy_4",
            correlation_threshold=0.7
        )
        
        expected_size = base_size * 0.33  # 33% for 3+ correlated
        assert abs(adjusted_size - expected_size) < 1.0, f"Expected ${expected_size:,.2f}, got ${adjusted_size:,.2f}"
        assert "3 correlated position(s)" in reason
        logger.info(f"   ✓ Position size reduced: ${base_size:,.2f} → ${adjusted_size:,.2f} (33%)")
        logger.info(f"   Reason: {reason}")
        
        # Test 3: No correlation adjustment for different symbol
        logger.info("\n[5/5] Testing no adjustment for uncorrelated symbol...")
        adjusted_size, reason = portfolio_manager.calculate_correlation_adjusted_size(
            base_position_size=base_size,
            new_trade_symbol="AAPL",  # Different symbol
            new_trade_strategy_id="strategy_4",
            correlation_threshold=0.7
        )
        
        assert adjusted_size == base_size, f"Expected no adjustment, got ${adjusted_size:,.2f}"
        assert "No correlated positions" in reason
        logger.info(f"   ✓ No adjustment for AAPL: ${adjusted_size:,.2f}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ TEST 3 PASSED: Correlation-Based Position Sizing")
        logger.info("=" * 80)
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST 3 FAILED: {e}", exc_info=True)
        return False


def main():
    """Run all portfolio risk management tests."""
    logger.info("\n" + "=" * 80)
    logger.info("PORTFOLIO-WIDE RISK MANAGEMENT TEST SUITE")
    logger.info("=" * 80)
    
    results = {
        'portfolio_stop_loss': False,
        'exposure_limits': False,
        'correlation_sizing': False
    }
    
    # Run tests
    results['portfolio_stop_loss'] = test_portfolio_stop_loss()
    results['exposure_limits'] = test_exposure_limits()
    results['correlation_sizing'] = test_correlation_based_position_sizing()
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED!")
        logger.info("\nPortfolio-wide risk management features:")
        logger.info("  ✓ Portfolio stop-loss (10% limit)")
        logger.info("  ✓ Daily loss limit (3% limit)")
        logger.info("  ✓ Total exposure limit (100%)")
        logger.info("  ✓ Per-symbol exposure limit (20%)")
        logger.info("  ✓ Per-strategy exposure limit (30%)")
        logger.info("  ✓ Correlation-based position sizing")
    else:
        logger.error("\n❌ SOME TESTS FAILED")
    
    logger.info("=" * 80)
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
