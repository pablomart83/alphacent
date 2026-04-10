"""
Test Tiered Activation System.

This test verifies that the PortfolioManager correctly implements:
1. Tiered activation based on Sharpe ratio
2. Confidence scoring
3. Updated activation criteria (win_rate > 0.45, max_drawdown < 0.20, trades > 10)
4. Updated retirement criteria (Sharpe < 0.2, drawdown > 0.25, win_rate < 0.35)
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
from src.models.dataclasses import BacktestResults, Strategy
from src.models.enums import StrategyStatus, TradingMode
from src.strategy.portfolio_manager import PortfolioManager
from src.strategy.strategy_engine import StrategyEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_mock_strategy(name: str, sharpe: float, win_rate: float, 
                        max_drawdown: float, total_trades: int) -> tuple[Strategy, BacktestResults]:
    """Create a mock strategy with backtest results."""
    from src.models.dataclasses import RiskConfig
    import uuid
    
    strategy = Strategy(
        id=str(uuid.uuid4()),
        name=name,
        description=f"Test strategy with Sharpe {sharpe}",
        symbols=["SPY"],
        rules={
            "entry_conditions": ["RSI(14) < 30"],
            "exit_conditions": ["RSI(14) > 70"],
            "indicators": ["RSI"]
        },
        status=StrategyStatus.PROPOSED,
        risk_params=RiskConfig(),
        created_at=datetime.now(),
        metadata={}
    )
    
    backtest_results = BacktestResults(
        sharpe_ratio=sharpe,
        sortino_ratio=sharpe * 1.2,  # Approximate sortino
        total_return=sharpe * 0.1,  # Approximate return
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        total_trades=total_trades,
        avg_win=0.02,
        avg_loss=-0.01
    )
    
    return strategy, backtest_results


def test_tiered_activation():
    """Test the tiered activation system."""
    logger.info("=" * 80)
    logger.info("TESTING TIERED ACTIVATION SYSTEM")
    logger.info("=" * 80)
    
    try:
        # Initialize components
        logger.info("\n[1/6] Initializing components...")
        db = Database()
        config_manager = get_config()
        
        # Initialize eToro client (mock if credentials not available)
        try:
            credentials = config_manager.load_credentials(TradingMode.DEMO)
            etoro_client = EToroAPIClient(
                public_key=credentials['public_key'],
                user_key=credentials['user_key'],
                mode=TradingMode.DEMO
            )
        except Exception:
            from unittest.mock import Mock
            etoro_client = Mock()
        
        llm_service = LLMService()
        market_data = MarketDataManager(etoro_client=etoro_client)
        strategy_engine = StrategyEngine(llm_service=llm_service, market_data=market_data)
        portfolio_manager = PortfolioManager(strategy_engine=strategy_engine)
        
        logger.info("   ✓ Components initialized")
        
        # Test 1: Tier classification
        logger.info("\n[2/6] Testing tier classification...")
        
        test_cases = [
            (1.5, 1, 30.0, "Tier 1 (High Confidence)"),
            (1.0, 1, 30.0, "Tier 1 (High Confidence)"),
            (0.8, 2, 15.0, "Tier 2 (Medium Confidence)"),
            (0.5, 2, 15.0, "Tier 2 (Medium Confidence)"),
            (0.4, 3, 10.0, "Tier 3 (Low Confidence)"),
            (0.3, 3, 10.0, "Tier 3 (Low Confidence)"),
            (0.2, 0, 0.0, "Rejected"),
        ]
        
        for sharpe, expected_tier, expected_allocation, description in test_cases:
            _, backtest_results = create_mock_strategy(
                f"Test_{sharpe}", sharpe, 0.55, 0.10, 20
            )
            tier, max_allocation = portfolio_manager.get_activation_tier(backtest_results)
            
            assert tier == expected_tier, f"Expected tier {expected_tier}, got {tier} for Sharpe {sharpe}"
            assert max_allocation == expected_allocation, \
                f"Expected allocation {expected_allocation}%, got {max_allocation}% for Sharpe {sharpe}"
            
            logger.info(f"   ✓ Sharpe {sharpe:.1f}: {description} - Max {max_allocation:.0f}%")
        
        # Test 2: Confidence scoring
        logger.info("\n[3/6] Testing confidence scoring...")
        
        # High confidence: Good Sharpe, win rate, and trades
        strategy_high, results_high = create_mock_strategy(
            "High_Confidence", sharpe=1.2, win_rate=0.60, max_drawdown=0.08, total_trades=40
        )
        confidence_high = portfolio_manager.calculate_confidence_score(strategy_high, results_high)
        logger.info(f"   ✓ High confidence strategy: {confidence_high:.2f}")
        assert confidence_high >= 0.7, f"Expected high confidence >= 0.7, got {confidence_high:.2f}"
        
        # Medium confidence: Moderate metrics
        strategy_med, results_med = create_mock_strategy(
            "Medium_Confidence", sharpe=0.7, win_rate=0.50, max_drawdown=0.12, total_trades=20
        )
        confidence_med = portfolio_manager.calculate_confidence_score(strategy_med, results_med)
        logger.info(f"   ✓ Medium confidence strategy: {confidence_med:.2f}")
        assert 0.5 <= confidence_med < 0.9, f"Expected medium confidence 0.5-0.9, got {confidence_med:.2f}"
        
        # Low confidence: Weak metrics
        strategy_low, results_low = create_mock_strategy(
            "Low_Confidence", sharpe=0.35, win_rate=0.46, max_drawdown=0.18, total_trades=12
        )
        confidence_low = portfolio_manager.calculate_confidence_score(strategy_low, results_low)
        logger.info(f"   ✓ Low confidence strategy: {confidence_low:.2f}")
        assert confidence_low < 0.6, f"Expected low confidence < 0.6, got {confidence_low:.2f}"
        
        # Test 3: Activation criteria
        logger.info("\n[4/6] Testing activation criteria...")
        
        # Should pass: Sharpe 0.8, win_rate 0.50, drawdown 0.15, trades 15
        strategy_pass, results_pass = create_mock_strategy(
            "Should_Pass", sharpe=0.8, win_rate=0.50, max_drawdown=0.15, total_trades=15
        )
        should_activate = portfolio_manager.evaluate_for_activation(strategy_pass, results_pass)
        assert should_activate, "Strategy with Sharpe 0.8 should pass activation"
        logger.info("   ✓ Strategy with Sharpe 0.8, win_rate 0.50, drawdown 0.15, trades 15: PASSED")
        
        # Should fail: Sharpe too low (0.25)
        strategy_fail_sharpe, results_fail_sharpe = create_mock_strategy(
            "Fail_Sharpe", sharpe=0.25, win_rate=0.50, max_drawdown=0.15, total_trades=15
        )
        should_activate = portfolio_manager.evaluate_for_activation(strategy_fail_sharpe, results_fail_sharpe)
        assert not should_activate, "Strategy with Sharpe 0.25 should fail activation"
        logger.info("   ✓ Strategy with Sharpe 0.25: REJECTED (Sharpe < 0.3)")
        
        # Should fail: Win rate too low (0.40)
        strategy_fail_wr, results_fail_wr = create_mock_strategy(
            "Fail_WinRate", sharpe=0.8, win_rate=0.40, max_drawdown=0.15, total_trades=15
        )
        should_activate = portfolio_manager.evaluate_for_activation(strategy_fail_wr, results_fail_wr)
        assert not should_activate, "Strategy with win_rate 0.40 should fail activation"
        logger.info("   ✓ Strategy with win_rate 0.40: REJECTED (win_rate <= 0.45)")
        
        # Should fail: Drawdown too high (0.25)
        strategy_fail_dd, results_fail_dd = create_mock_strategy(
            "Fail_Drawdown", sharpe=0.8, win_rate=0.50, max_drawdown=0.25, total_trades=15
        )
        should_activate = portfolio_manager.evaluate_for_activation(strategy_fail_dd, results_fail_dd)
        assert not should_activate, "Strategy with drawdown 0.25 should fail activation"
        logger.info("   ✓ Strategy with drawdown 0.25: REJECTED (drawdown >= 0.20)")
        
        # Should fail: Too few trades (8)
        strategy_fail_trades, results_fail_trades = create_mock_strategy(
            "Fail_Trades", sharpe=0.8, win_rate=0.50, max_drawdown=0.15, total_trades=8
        )
        should_activate = portfolio_manager.evaluate_for_activation(strategy_fail_trades, results_fail_trades)
        assert not should_activate, "Strategy with 8 trades should fail activation"
        logger.info("   ✓ Strategy with 8 trades: REJECTED (trades <= 10)")
        
        # Test 4: Retirement criteria
        logger.info("\n[5/6] Testing retirement criteria...")
        
        # Create strategies with performance data
        from src.models.dataclasses import RiskConfig, PerformanceMetrics
        import uuid
        
        # Should retire: Sharpe < 0.2 with 35 trades
        strategy_retire_sharpe = Strategy(
            id=str(uuid.uuid4()),
            name="Retire_Sharpe",
            description="Should retire due to low Sharpe",
            symbols=["SPY"],
            rules={"entry_conditions": [], "exit_conditions": [], "indicators": []},
            status=StrategyStatus.DEMO,
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(
                sharpe_ratio=0.15,
                total_return=0.02,
                max_drawdown=0.10,
                win_rate=0.50,
                total_trades=35,
                avg_win=0.02,
                avg_loss=-0.01
            )
        )
        reason = portfolio_manager.check_retirement_triggers(strategy_retire_sharpe)
        assert reason is not None, "Strategy with Sharpe 0.15 (35 trades) should trigger retirement"
        assert "Sharpe ratio" in reason, f"Expected Sharpe ratio in reason, got: {reason}"
        logger.info(f"   ✓ Strategy with Sharpe 0.15 (35 trades): RETIRE - {reason}")
        
        # Should retire: Drawdown > 0.25
        strategy_retire_dd = Strategy(
            id=str(uuid.uuid4()),
            name="Retire_Drawdown",
            description="Should retire due to high drawdown",
            symbols=["SPY"],
            rules={"entry_conditions": [], "exit_conditions": [], "indicators": []},
            status=StrategyStatus.DEMO,
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(
                sharpe_ratio=0.5,
                total_return=0.05,
                max_drawdown=0.30,
                win_rate=0.50,
                total_trades=20,
                avg_win=0.02,
                avg_loss=-0.01
            )
        )
        reason = portfolio_manager.check_retirement_triggers(strategy_retire_dd)
        assert reason is not None, "Strategy with drawdown 0.30 should trigger retirement"
        assert "drawdown" in reason.lower(), f"Expected drawdown in reason, got: {reason}"
        logger.info(f"   ✓ Strategy with drawdown 0.30: RETIRE - {reason}")
        
        # Should retire: Win rate < 0.35 with 55 trades
        strategy_retire_wr = Strategy(
            id=str(uuid.uuid4()),
            name="Retire_WinRate",
            description="Should retire due to low win rate",
            symbols=["SPY"],
            rules={"entry_conditions": [], "exit_conditions": [], "indicators": []},
            status=StrategyStatus.DEMO,
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(
                sharpe_ratio=0.5,
                total_return=0.05,
                max_drawdown=0.10,
                win_rate=0.30,
                total_trades=55,
                avg_win=0.02,
                avg_loss=-0.01
            )
        )
        reason = portfolio_manager.check_retirement_triggers(strategy_retire_wr)
        assert reason is not None, "Strategy with win_rate 0.30 (55 trades) should trigger retirement"
        assert "Win rate" in reason, f"Expected Win rate in reason, got: {reason}"
        logger.info(f"   ✓ Strategy with win_rate 0.30 (55 trades): RETIRE - {reason}")
        
        # Should NOT retire: Good performance
        strategy_keep = Strategy(
            id=str(uuid.uuid4()),
            name="Keep_Strategy",
            description="Should not retire",
            symbols=["SPY"],
            rules={"entry_conditions": [], "exit_conditions": [], "indicators": []},
            status=StrategyStatus.DEMO,
            risk_params=RiskConfig(),
            created_at=datetime.now(),
            performance=PerformanceMetrics(
                sharpe_ratio=0.8,
                total_return=0.15,
                max_drawdown=0.12,
                win_rate=0.55,
                total_trades=40,
                avg_win=0.02,
                avg_loss=-0.01
            )
        )
        reason = portfolio_manager.check_retirement_triggers(strategy_keep)
        assert reason is None, "Strategy with good performance should not trigger retirement"
        logger.info("   ✓ Strategy with good performance: KEEP")
        
        # Test 5: Allocation calculation
        logger.info("\n[6/6] Testing allocation calculation...")
        
        # Test Tier 1 allocation (Sharpe 1.2, high confidence)
        logger.info("   Testing Tier 1 allocation...")
        # Note: We can't fully test auto_activate_strategy without database setup,
        # but we can verify the tier and confidence calculations
        tier, max_allocation = portfolio_manager.get_activation_tier(results_high)
        confidence = portfolio_manager.calculate_confidence_score(strategy_high, results_high)
        expected_base = max_allocation * confidence
        logger.info(f"   ✓ Tier 1: Max={max_allocation:.1f}%, Confidence={confidence:.2f}, Base={expected_base:.1f}%")
        assert tier == 1, f"Expected Tier 1, got {tier}"
        assert max_allocation == 30.0, f"Expected max 30%, got {max_allocation}%"
        
        # Test Tier 2 allocation (Sharpe 0.7, medium confidence)
        logger.info("   Testing Tier 2 allocation...")
        tier, max_allocation = portfolio_manager.get_activation_tier(results_med)
        confidence = portfolio_manager.calculate_confidence_score(strategy_med, results_med)
        expected_base = max_allocation * confidence
        logger.info(f"   ✓ Tier 2: Max={max_allocation:.1f}%, Confidence={confidence:.2f}, Base={expected_base:.1f}%")
        assert tier == 2, f"Expected Tier 2, got {tier}"
        assert max_allocation == 15.0, f"Expected max 15%, got {max_allocation}%"
        
        # Test Tier 3 allocation (Sharpe 0.35, low confidence)
        logger.info("   Testing Tier 3 allocation...")
        tier, max_allocation = portfolio_manager.get_activation_tier(results_low)
        confidence = portfolio_manager.calculate_confidence_score(strategy_low, results_low)
        expected_base = max_allocation * confidence
        logger.info(f"   ✓ Tier 3: Max={max_allocation:.1f}%, Confidence={confidence:.2f}, Base={expected_base:.1f}%")
        assert tier == 3, f"Expected Tier 3, got {tier}"
        assert max_allocation == 10.0, f"Expected max 10%, got {max_allocation}%"
        
        logger.info("\n" + "=" * 80)
        logger.info("TIERED ACTIVATION SYSTEM TEST COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        logger.info("\nTest Results Summary:")
        logger.info("  ✓ Tier classification: PASS")
        logger.info("  ✓ Confidence scoring: PASS")
        logger.info("  ✓ Activation criteria: PASS")
        logger.info("  ✓ Retirement criteria: PASS")
        logger.info("  ✓ Allocation calculation: PASS")
        
        logger.info("\nKey Improvements:")
        logger.info("  • Tiered activation: Sharpe > 0.3 can be activated (was > 1.5)")
        logger.info("  • Tier 1 (Sharpe > 1.0): max 30% allocation")
        logger.info("  • Tier 2 (Sharpe 0.5-1.0): max 15% allocation")
        logger.info("  • Tier 3 (Sharpe 0.3-0.5): max 10% allocation")
        logger.info("  • Activation: win_rate > 0.45, drawdown < 0.20, trades > 10")
        logger.info("  • Retirement: Sharpe < 0.2, drawdown > 0.25, win_rate < 0.35")
        logger.info("  • Confidence scoring: Sharpe, win rate, trades, walk-forward")
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ TEST FAILED: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    success = test_tiered_activation()
    sys.exit(0 if success else 1)
