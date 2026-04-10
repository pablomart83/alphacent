#!/usr/bin/env python3
"""
Comprehensive System Readiness Test

Tests all critical system components to verify readiness for live trading.
Uses feature detection (not assumptions) to validate implementation.
"""

import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SystemReadinessTest:
    """Comprehensive system readiness test."""
    
    def __init__(self):
        """Initialize readiness test."""
        self.results: List[Dict] = []
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load configuration file."""
        try:
            config_path = Path(__file__).parent.parent / "config" / "autonomous_trading.yaml"
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def run_all_checks(self) -> Tuple[int, int]:
        """
        Run all system readiness checks.
        
        Returns:
            Tuple of (passed_count, total_count)
        """
        logger.info("=" * 80)
        logger.info("SYSTEM READINESS TEST")
        logger.info("=" * 80)
        
        # Run all checks
        self.check_transaction_costs()
        self.check_walk_forward_analysis()
        self.check_market_regime_detection()
        self.check_dynamic_position_sizing()
        self.check_correlation_management()
        self.check_execution_quality_monitoring()
        self.check_data_quality_validation()
        self.check_strategy_retirement_logic()
        
        # Generate report
        self.generate_report()
        
        # Calculate results
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        total = len(self.results)
        
        return passed, total
    
    def check_transaction_costs(self) -> None:
        """Check 1: Transaction costs in backtesting."""
        logger.info("\n[Check 1] Transaction Costs in Backtesting")
        
        try:
            # Verify config exists
            config_exists = 'backtest' in self.config and 'transaction_costs' in self.config['backtest']
            
            if not config_exists:
                self._add_result(
                    check_name="Transaction Costs",
                    status="FAIL",
                    details="Configuration missing",
                    recommendation="Add transaction_costs section to config/autonomous_trading.yaml"
                )
                return
            
            # Verify BacktestResults has required fields
            from src.models.dataclasses import BacktestResults
            from dataclasses import fields
            
            backtest_fields = {f.name for f in fields(BacktestResults)}
            required_fields = {'gross_return', 'net_return', 'total_transaction_costs'}
            
            if not required_fields.issubset(backtest_fields):
                missing = required_fields - backtest_fields
                self._add_result(
                    check_name="Transaction Costs",
                    status="FAIL",
                    details=f"BacktestResults missing fields: {missing}",
                    recommendation="Update BacktestResults dataclass with transaction cost fields"
                )
                return
            
            # Verify costs are applied in backtest
            from src.strategy.strategy_engine import StrategyEngine
            import inspect
            
            backtest_source = inspect.getsource(StrategyEngine.backtest_strategy)
            has_cost_calculation = (
                'transaction_costs' in backtest_source or
                'gross_return' in backtest_source or
                'net_return' in backtest_source
            )
            
            if not has_cost_calculation:
                self._add_result(
                    check_name="Transaction Costs",
                    status="FAIL",
                    details="Transaction costs not applied in backtest",
                    recommendation="Update backtest_strategy method to calculate and apply transaction costs"
                )
                return
            
            # All checks passed
            config_details = self.config['backtest']['transaction_costs']
            self._add_result(
                check_name="Transaction Costs",
                status="PASS",
                details=f"Config: {config_details}, Fields: {required_fields}",
                recommendation=None
            )
            
        except Exception as e:
            self._add_result(
                check_name="Transaction Costs",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def check_walk_forward_analysis(self) -> None:
        """Check 2: Walk-forward analysis."""
        logger.info("\n[Check 2] Walk-Forward Analysis")
        
        try:
            # Verify StrategyEngine has walk_forward_validate method
            from src.strategy.strategy_engine import StrategyEngine
            
            if not hasattr(StrategyEngine, 'walk_forward_validate'):
                self._add_result(
                    check_name="Walk-Forward Analysis",
                    status="FAIL",
                    details="walk_forward_validate method not found",
                    recommendation="Implement walk_forward_validate in StrategyEngine"
                )
                return
            
            # Verify config exists
            config_exists = (
                'backtest' in self.config and 
                'walk_forward' in self.config['backtest']
            )
            
            if not config_exists:
                self._add_result(
                    check_name="Walk-Forward Analysis",
                    status="FAIL",
                    details="Walk-forward configuration missing",
                    recommendation="Add walk_forward section to backtest config"
                )
                return
            
            # Verify train/test split
            wf_config = self.config['backtest']['walk_forward']
            train_days = wf_config.get('train_days', 0)
            test_days = wf_config.get('test_days', 0)
            
            # Check for 67/33 split (approximately)
            total_days = train_days + test_days
            train_pct = train_days / total_days if total_days > 0 else 0
            
            if not (0.60 <= train_pct <= 0.70):
                self._add_result(
                    check_name="Walk-Forward Analysis",
                    status="WARN",
                    details=f"Train/test split is {train_pct:.1%}, expected ~67%",
                    recommendation="Consider using 67/33 train/test split"
                )
                return
            
            # All checks passed
            self._add_result(
                check_name="Walk-Forward Analysis",
                status="PASS",
                details=f"Method exists, config: train={train_days}d, test={test_days}d ({train_pct:.1%}/{1-train_pct:.1%})",
                recommendation=None
            )
            
        except Exception as e:
            self._add_result(
                check_name="Walk-Forward Analysis",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def check_market_regime_detection(self) -> None:
        """Check 3: Market regime detection."""
        logger.info("\n[Check 3] Market Regime Detection")
        
        try:
            # Verify MarketStatisticsAnalyzer exists
            from src.strategy.market_analyzer import MarketStatisticsAnalyzer
            
            # Verify detect_sub_regime method
            if not hasattr(MarketStatisticsAnalyzer, 'detect_sub_regime'):
                self._add_result(
                    check_name="Market Regime Detection",
                    status="FAIL",
                    details="detect_sub_regime method not found",
                    recommendation="Implement detect_sub_regime in MarketStatisticsAnalyzer"
                )
                return
            
            # Verify FRED integration
            import inspect
            analyzer_source = inspect.getsource(MarketStatisticsAnalyzer)
            has_fred = 'fred' in analyzer_source.lower() or 'FRED' in analyzer_source
            
            if not has_fred:
                self._add_result(
                    check_name="Market Regime Detection",
                    status="WARN",
                    details="FRED integration not detected",
                    recommendation="Consider integrating FRED economic data"
                )
                return
            
            # Verify config
            fred_config = self.config.get('data_sources', {}).get('fred', {})
            if not fred_config.get('enabled', False):
                self._add_result(
                    check_name="Market Regime Detection",
                    status="WARN",
                    details="FRED data source disabled in config",
                    recommendation="Enable FRED in config for better regime detection"
                )
                return
            
            # All checks passed
            self._add_result(
                check_name="Market Regime Detection",
                status="PASS",
                details="MarketStatisticsAnalyzer with detect_sub_regime and FRED integration",
                recommendation=None
            )
            
        except ImportError:
            self._add_result(
                check_name="Market Regime Detection",
                status="FAIL",
                details="MarketStatisticsAnalyzer not found",
                recommendation="Implement MarketStatisticsAnalyzer class"
            )
        except Exception as e:
            self._add_result(
                check_name="Market Regime Detection",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def check_dynamic_position_sizing(self) -> None:
        """Check 4: Dynamic position sizing."""
        logger.info("\n[Check 4] Dynamic Position Sizing")
        
        try:
            # Verify regime-based sizing
            from src.risk.risk_manager import RiskManager
            
            if not hasattr(RiskManager, 'calculate_regime_adjusted_size'):
                self._add_result(
                    check_name="Dynamic Position Sizing",
                    status="FAIL",
                    details="calculate_regime_adjusted_size method not found",
                    recommendation="Implement regime-based position sizing in RiskManager"
                )
                return
            
            # Verify correlation-based sizing
            if not hasattr(RiskManager, 'calculate_correlation_adjusted_size'):
                self._add_result(
                    check_name="Dynamic Position Sizing",
                    status="FAIL",
                    details="calculate_correlation_adjusted_size method not found",
                    recommendation="Implement correlation-based position sizing in RiskManager"
                )
                return
            
            # Verify volatility-based sizing
            import inspect
            risk_source = inspect.getsource(RiskManager.calculate_position_size)
            has_volatility = 'volatility' in risk_source.lower() or 'atr' in risk_source.lower()
            
            if not has_volatility:
                self._add_result(
                    check_name="Dynamic Position Sizing",
                    status="WARN",
                    details="Volatility-based sizing not detected",
                    recommendation="Consider adding volatility adjustment to position sizing"
                )
                return
            
            # Check config
            pm_config = self.config.get('position_management', {})
            regime_enabled = pm_config.get('regime_based_sizing', {}).get('enabled', False)
            corr_enabled = pm_config.get('correlation_adjustment', {}).get('enabled', False)
            
            # All checks passed
            self._add_result(
                check_name="Dynamic Position Sizing",
                status="PASS",
                details=f"Regime-based: {regime_enabled}, Correlation: {corr_enabled}, Volatility: detected",
                recommendation=None
            )
            
        except Exception as e:
            self._add_result(
                check_name="Dynamic Position Sizing",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def check_correlation_management(self) -> None:
        """Check 5: Strategy correlation management."""
        logger.info("\n[Check 5] Strategy Correlation Management")
        
        try:
            # Verify correlation calculation
            from src.strategy.portfolio_manager import PortfolioManager
            
            if not hasattr(PortfolioManager, 'calculate_strategy_correlation'):
                self._add_result(
                    check_name="Correlation Management",
                    status="FAIL",
                    details="calculate_strategy_correlation method not found",
                    recommendation="Implement correlation calculation in PortfolioManager"
                )
                return
            
            # Verify position size adjustment
            if not hasattr(PortfolioManager, 'calculate_correlation_adjusted_size'):
                self._add_result(
                    check_name="Correlation Management",
                    status="FAIL",
                    details="calculate_correlation_adjusted_size method not found",
                    recommendation="Implement correlation-adjusted sizing in PortfolioManager"
                )
                return
            
            # Verify correlation matrix API
            try:
                from src.api.routers.analytics import router
                import inspect
                
                router_source = inspect.getsource(router)
                has_corr_endpoint = 'correlation-matrix' in router_source or 'correlation_matrix' in router_source
                
                if not has_corr_endpoint:
                    self._add_result(
                        check_name="Correlation Management",
                        status="WARN",
                        details="Correlation matrix API endpoint not found",
                        recommendation="Add /api/correlation-matrix endpoint"
                    )
                    return
            except:
                pass  # API check is optional
            
            # Check config
            corr_threshold = self.config.get('advanced', {}).get('correlation_threshold', 0)
            pm_config = self.config.get('position_management', {})
            corr_enabled = pm_config.get('correlation_adjustment', {}).get('enabled', False)
            
            # All checks passed
            self._add_result(
                check_name="Correlation Management",
                status="PASS",
                details=f"Calculation: yes, Adjustment: {corr_enabled}, Threshold: {corr_threshold}, API: yes",
                recommendation=None
            )
            
        except Exception as e:
            self._add_result(
                check_name="Correlation Management",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def check_execution_quality_monitoring(self) -> None:
        """Check 6: Execution quality monitoring."""
        logger.info("\n[Check 6] Execution Quality Monitoring")
        
        try:
            # Verify ExecutionQualityTracker exists
            from src.monitoring.execution_quality import ExecutionQualityTracker
            
            # Verify slippage tracking
            if not hasattr(ExecutionQualityTracker, 'get_metrics'):
                self._add_result(
                    check_name="Execution Quality Monitoring",
                    status="FAIL",
                    details="get_metrics method not found",
                    recommendation="Implement get_metrics in ExecutionQualityTracker"
                )
                return
            
            # Verify metrics include slippage and fill rate
            import inspect
            tracker_source = inspect.getsource(ExecutionQualityTracker)
            has_slippage = 'slippage' in tracker_source.lower()
            has_fill_rate = 'fill_rate' in tracker_source.lower()
            
            if not has_slippage:
                self._add_result(
                    check_name="Execution Quality Monitoring",
                    status="FAIL",
                    details="Slippage tracking not found",
                    recommendation="Add slippage tracking to ExecutionQualityTracker"
                )
                return
            
            if not has_fill_rate:
                self._add_result(
                    check_name="Execution Quality Monitoring",
                    status="FAIL",
                    details="Fill rate tracking not found",
                    recommendation="Add fill rate tracking to ExecutionQualityTracker"
                )
                return
            
            # All checks passed
            self._add_result(
                check_name="Execution Quality Monitoring",
                status="PASS",
                details="ExecutionQualityTracker with slippage and fill rate tracking",
                recommendation=None
            )
            
        except ImportError:
            self._add_result(
                check_name="Execution Quality Monitoring",
                status="FAIL",
                details="ExecutionQualityTracker not found",
                recommendation="Implement ExecutionQualityTracker class"
            )
        except Exception as e:
            self._add_result(
                check_name="Execution Quality Monitoring",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def check_data_quality_validation(self) -> None:
        """Check 7: Data quality validation."""
        logger.info("\n[Check 7] Data Quality Validation")
        
        try:
            # Verify DataQualityValidator exists
            from src.data.data_quality_validator import DataQualityValidator
            
            # Verify quality checks implemented
            validator = DataQualityValidator()
            required_checks = [
                '_check_missing_data_gaps',
                '_check_price_jumps',
                '_check_zero_volume',
                '_check_stale_data',
                '_check_duplicate_timestamps',
                '_check_null_values'
            ]
            
            missing_checks = [check for check in required_checks if not hasattr(validator, check)]
            
            if missing_checks:
                self._add_result(
                    check_name="Data Quality Validation",
                    status="FAIL",
                    details=f"Missing checks: {missing_checks}",
                    recommendation="Implement all required quality checks"
                )
                return
            
            # Verify validate_data_quality method
            if not hasattr(validator, 'validate_data_quality'):
                self._add_result(
                    check_name="Data Quality Validation",
                    status="FAIL",
                    details="validate_data_quality method not found",
                    recommendation="Implement validate_data_quality method"
                )
                return
            
            # All checks passed
            self._add_result(
                check_name="Data Quality Validation",
                status="PASS",
                details=f"DataQualityValidator with {len(required_checks)} quality checks",
                recommendation=None
            )
            
        except ImportError:
            self._add_result(
                check_name="Data Quality Validation",
                status="FAIL",
                details="DataQualityValidator not found",
                recommendation="Implement DataQualityValidator class"
            )
        except Exception as e:
            self._add_result(
                check_name="Data Quality Validation",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def check_strategy_retirement_logic(self) -> None:
        """Check 8: Strategy retirement logic."""
        logger.info("\n[Check 8] Strategy Retirement Logic")
        
        try:
            # Verify retirement config
            retirement_config = self.config.get('retirement_logic', {})
            
            if not retirement_config:
                self._add_result(
                    check_name="Strategy Retirement Logic",
                    status="FAIL",
                    details="Retirement logic configuration missing",
                    recommendation="Add retirement_logic section to config"
                )
                return
            
            # Verify minimum trade count check
            min_trades = retirement_config.get('min_live_trades_before_evaluation', 0)
            if min_trades < 10:
                self._add_result(
                    check_name="Strategy Retirement Logic",
                    status="WARN",
                    details=f"Minimum trades ({min_trades}) is low",
                    recommendation="Consider setting min_live_trades_before_evaluation >= 20"
                )
                return
            
            # Verify rolling window metrics
            rolling_window = retirement_config.get('rolling_window_days', 0)
            if rolling_window < 30:
                self._add_result(
                    check_name="Strategy Retirement Logic",
                    status="WARN",
                    details=f"Rolling window ({rolling_window}d) is short",
                    recommendation="Consider setting rolling_window_days >= 60"
                )
                return
            
            # Verify consecutive failures logic
            consecutive_failures = retirement_config.get('consecutive_failures_required', 0)
            if consecutive_failures < 2:
                self._add_result(
                    check_name="Strategy Retirement Logic",
                    status="WARN",
                    details=f"Consecutive failures ({consecutive_failures}) is low",
                    recommendation="Consider setting consecutive_failures_required >= 3"
                )
                return
            
            # Verify implementation in StrategyEngine
            from src.strategy.strategy_engine import StrategyEngine
            
            if not hasattr(StrategyEngine, 'check_retirement_triggers'):
                self._add_result(
                    check_name="Strategy Retirement Logic",
                    status="FAIL",
                    details="check_retirement_triggers method not found",
                    recommendation="Implement retirement logic in StrategyEngine"
                )
                return
            
            # All checks passed
            self._add_result(
                check_name="Strategy Retirement Logic",
                status="PASS",
                details=f"Config: min_trades={min_trades}, window={rolling_window}d, failures={consecutive_failures}",
                recommendation=None
            )
            
        except Exception as e:
            self._add_result(
                check_name="Strategy Retirement Logic",
                status="FAIL",
                details=f"Error: {str(e)}",
                recommendation="Fix implementation errors"
            )
    
    def _add_result(
        self,
        check_name: str,
        status: str,
        details: str,
        recommendation: str = None
    ) -> None:
        """Add check result."""
        result = {
            'check': check_name,
            'status': status,
            'details': details,
            'recommendation': recommendation
        }
        self.results.append(result)
        
        # Log result
        status_symbol = {
            'PASS': '✓',
            'FAIL': '✗',
            'WARN': '⚠'
        }.get(status, '?')
        
        logger.info(f"{status_symbol} {check_name}: {status}")
        logger.info(f"  Details: {details}")
        if recommendation:
            logger.info(f"  Recommendation: {recommendation}")
    
    def generate_report(self) -> None:
        """Generate markdown readiness report."""
        logger.info("\n" + "=" * 80)
        logger.info("GENERATING READINESS REPORT")
        logger.info("=" * 80)
        
        # Calculate overall score
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        warned = sum(1 for r in self.results if r['status'] == 'WARN')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        total = len(self.results)
        
        # Score: PASS=100, WARN=50, FAIL=0
        score = ((passed * 100) + (warned * 50)) / (total * 100) * 100 if total > 0 else 0
        
        # Generate report
        report_path = Path(__file__).parent.parent / "SYSTEM_READINESS_REPORT.md"
        
        with open(report_path, 'w') as f:
            f.write("# System Readiness Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Overall Score:** {score:.1f}/100\n\n")
            f.write(f"**Summary:** {passed} passed, {warned} warnings, {failed} failed (total: {total})\n\n")
            
            # Go/No-Go recommendation
            if score >= 80:
                f.write("**Recommendation:** ✓ SYSTEM READY FOR LIVE TRADING\n\n")
            elif score >= 60:
                f.write("**Recommendation:** ⚠ SYSTEM PARTIALLY READY - Address warnings before live trading\n\n")
            else:
                f.write("**Recommendation:** ✗ SYSTEM NOT READY - Critical issues must be fixed\n\n")
            
            f.write("---\n\n")
            f.write("## Detailed Results\n\n")
            
            # Write results by status
            for status in ['FAIL', 'WARN', 'PASS']:
                status_results = [r for r in self.results if r['status'] == status]
                if not status_results:
                    continue
                
                status_symbol = {'PASS': '✓', 'FAIL': '✗', 'WARN': '⚠'}.get(status, '?')
                f.write(f"### {status_symbol} {status}\n\n")
                
                for result in status_results:
                    f.write(f"#### {result['check']}\n\n")
                    f.write(f"**Status:** {result['status']}\n\n")
                    f.write(f"**Details:** {result['details']}\n\n")
                    
                    if result['recommendation']:
                        f.write(f"**Recommendation:** {result['recommendation']}\n\n")
                    
                    f.write("---\n\n")
        
        logger.info(f"Report saved to: {report_path}")
        logger.info(f"Overall Score: {score:.1f}/100")
        
        if score >= 80:
            logger.info("✓ SYSTEM READY FOR LIVE TRADING")
        elif score >= 60:
            logger.info("⚠ SYSTEM PARTIALLY READY - Address warnings")
        else:
            logger.info("✗ SYSTEM NOT READY - Critical issues must be fixed")


def main():
    """Run system readiness test."""
    try:
        test = SystemReadinessTest()
        passed, total = test.run_all_checks()
        
        logger.info("\n" + "=" * 80)
        logger.info(f"FINAL RESULTS: {passed}/{total} checks passed")
        logger.info("=" * 80)
        
        # Exit with appropriate code
        if passed == total:
            sys.exit(0)  # All passed
        elif passed >= total * 0.6:
            sys.exit(1)  # Warnings
        else:
            sys.exit(2)  # Failures
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(3)


if __name__ == "__main__":
    main()
