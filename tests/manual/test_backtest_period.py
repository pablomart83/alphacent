"""
Quick test to verify backtest period configuration is updated to 365 days.
"""

import yaml
from pathlib import Path

def test_backtest_config():
    """Test that backtest configuration is updated to 365 days."""
    
    config_path = Path("config/autonomous_trading.yaml")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Check backtest configuration
    backtest_config = config.get("backtest", {})
    
    print("Backtest Configuration:")
    print(f"  Days: {backtest_config.get('days', 'NOT SET')}")
    print(f"  Warmup Days: {backtest_config.get('warmup_days', 'NOT SET')}")
    print(f"  Min Trades: {backtest_config.get('min_trades', 'NOT SET')}")
    
    # Check walk-forward configuration
    wf_config = backtest_config.get("walk_forward", {})
    print(f"\nWalk-Forward Configuration:")
    print(f"  Train Days: {wf_config.get('train_days', 'NOT SET')}")
    print(f"  Test Days: {wf_config.get('test_days', 'NOT SET')}")
    
    # Check data quality configuration
    dq_config = backtest_config.get("data_quality", {})
    print(f"\nData Quality Configuration:")
    print(f"  Min Days Required: {dq_config.get('min_days_required', 'NOT SET')}")
    print(f"  Fallback Days: {dq_config.get('fallback_days', 'NOT SET')}")
    
    # Check activation thresholds
    activation_config = config.get("activation_thresholds", {})
    print(f"\nActivation Thresholds:")
    print(f"  Min Trades: {activation_config.get('min_trades', 'NOT SET')}")
    
    # Verify values
    assert backtest_config.get('days') == 365, f"Expected 365 days, got {backtest_config.get('days')}"
    assert backtest_config.get('warmup_days') == 200, f"Expected 200 warmup days, got {backtest_config.get('warmup_days')}"
    assert backtest_config.get('min_trades') == 30, f"Expected 30 min trades, got {backtest_config.get('min_trades')}"
    assert wf_config.get('train_days') == 240, f"Expected 240 train days, got {wf_config.get('train_days')}"
    assert wf_config.get('test_days') == 120, f"Expected 120 test days, got {wf_config.get('test_days')}"
    assert dq_config.get('min_days_required') == 500, f"Expected 500 min days, got {dq_config.get('min_days_required')}"
    assert dq_config.get('fallback_days') == 180, f"Expected 180 fallback days, got {dq_config.get('fallback_days')}"
    assert activation_config.get('min_trades') == 30, f"Expected 30 min trades for activation, got {activation_config.get('min_trades')}"
    
    print("\n✓ All configuration values are correct!")
    print("\nSummary:")
    print("  • Backtest period increased from 90 to 365 days (1 year)")
    print("  • Warmup period increased from 60 to 200 days")
    print("  • Walk-forward train period: 240 days (8 months)")
    print("  • Walk-forward test period: 120 days (4 months)")
    print("  • Minimum trades requirement: 30 (2-3 trades/month)")
    print("  • Total data needed: 565 days (~1.5 years)")
    print("  • Data source: Yahoo Finance (unlimited history, free)")

if __name__ == "__main__":
    test_backtest_config()
