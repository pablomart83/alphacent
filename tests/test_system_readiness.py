"""
Tests for system readiness validation.

This test suite validates that all critical system components are properly
implemented and configured for live trading.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.test_system_readiness import SystemReadinessTest


class TestSystemReadiness:
    """Test system readiness validation."""
    
    def test_readiness_test_runs(self):
        """Test that readiness test runs without errors."""
        test = SystemReadinessTest()
        passed, total = test.run_all_checks()
        
        # Should have 8 checks
        assert total == 8, f"Expected 8 checks, got {total}"
        
        # Should have results
        assert len(test.results) == 8, f"Expected 8 results, got {len(test.results)}"
    
    def test_transaction_costs_check(self):
        """Test transaction costs check."""
        test = SystemReadinessTest()
        test.check_transaction_costs()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Transaction Costs'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_walk_forward_check(self):
        """Test walk-forward analysis check."""
        test = SystemReadinessTest()
        test.check_walk_forward_analysis()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Walk-Forward Analysis'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_market_regime_check(self):
        """Test market regime detection check."""
        test = SystemReadinessTest()
        test.check_market_regime_detection()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Market Regime Detection'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_dynamic_position_sizing_check(self):
        """Test dynamic position sizing check."""
        test = SystemReadinessTest()
        test.check_dynamic_position_sizing()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Dynamic Position Sizing'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_correlation_management_check(self):
        """Test correlation management check."""
        test = SystemReadinessTest()
        test.check_correlation_management()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Correlation Management'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_execution_quality_check(self):
        """Test execution quality monitoring check."""
        test = SystemReadinessTest()
        test.check_execution_quality_monitoring()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Execution Quality Monitoring'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_data_quality_check(self):
        """Test data quality validation check."""
        test = SystemReadinessTest()
        test.check_data_quality_validation()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Data Quality Validation'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_retirement_logic_check(self):
        """Test strategy retirement logic check."""
        test = SystemReadinessTest()
        test.check_strategy_retirement_logic()
        
        assert len(test.results) == 1
        result = test.results[0]
        
        assert result['check'] == 'Strategy Retirement Logic'
        assert result['status'] in ['PASS', 'FAIL', 'WARN']
    
    def test_report_generation(self):
        """Test that report is generated."""
        test = SystemReadinessTest()
        test.run_all_checks()
        
        # Check that report file exists
        report_path = Path(__file__).parent.parent / "SYSTEM_READINESS_REPORT.md"
        assert report_path.exists(), "Report file should be generated"
        
        # Check report content
        content = report_path.read_text()
        assert "System Readiness Report" in content
        assert "Overall Score:" in content
        assert "Recommendation:" in content
    
    def test_critical_components_present(self):
        """Test that all critical components are present (should pass)."""
        test = SystemReadinessTest()
        passed, total = test.run_all_checks()
        
        # System should be mostly ready (at least 60% passed)
        pass_rate = passed / total if total > 0 else 0
        assert pass_rate >= 0.6, f"System readiness too low: {pass_rate:.1%}"
        
        # Check for critical failures
        critical_checks = [
            'Transaction Costs',
            'Data Quality Validation',
            'Strategy Retirement Logic'
        ]
        
        for result in test.results:
            if result['check'] in critical_checks:
                assert result['status'] != 'FAIL', \
                    f"Critical check '{result['check']}' failed: {result['details']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
