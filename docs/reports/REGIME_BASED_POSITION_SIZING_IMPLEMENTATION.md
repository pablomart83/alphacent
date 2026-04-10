# Market Regime-Based Position Sizing Implementation

## Overview

Implemented market regime-based position sizing that automatically adjusts position sizes based on current market conditions. This feature helps manage risk by reducing position sizes in volatile or choppy markets and increasing them in favorable trending conditions.

## Implementation Details

### 1. RiskConfig Updates (src/models/dataclasses.py)

Added two new fields to the `RiskConfig` dataclass:

- `regime_based_sizing_enabled: bool = False` - Feature flag to enable/disable regime-based sizing
- `regime_size_multipliers: Dict[str, float]` - Multipliers for different market regimes

Default multipliers:
```python
{
    "high_volatility": 0.5,   # Reduce size by 50% in high volatility
    "low_volatility": 1.0,    # Normal size in low volatility
    "trending": 1.2,          # Increase size by 20% in trending markets
    "ranging": 0.8            # Reduce size by 20% in ranging markets
}
```

### 2. RiskManager Updates (src/risk/risk_manager.py)

#### New Method: `calculate_regime_adjusted_size()`

This method:
1. Checks if regime-based sizing is enabled
2. Uses `MarketStatisticsAnalyzer` (via PortfolioManager) to detect current market regime
3. Maps the detailed regime to a multiplier category:
   - Regimes with "high_vol" or "volatile" → `high_volatility`
   - Regimes with "low_vol" → `low_volatility`
   - Regimes with "trending" → `trending`
   - Regimes with "ranging" → `ranging`
4. Applies the multiplier to the base position size
5. Logs the adjustment with detailed reasoning

#### Integration into `validate_signal()`

The regime adjustment is applied AFTER correlation adjustment in the signal validation flow:

```
Base Position Size
    ↓
Correlation Adjustment (if enabled)
    ↓
Regime Adjustment (if enabled)
    ↓
Final Position Size
```

This ensures both adjustments work together to optimize position sizing.

### 3. Comprehensive Unit Tests (tests/test_risk_manager.py)

Added 10 new tests in the `TestRegimeBasedPositionSizing` class:

1. **test_regime_based_sizing_disabled** - Verifies feature can be disabled
2. **test_regime_based_sizing_no_portfolio_manager** - Handles missing dependencies gracefully
3. **test_regime_based_sizing_high_volatility** - Tests 0.5x multiplier in high volatility
4. **test_regime_based_sizing_low_volatility** - Tests 1.0x multiplier in low volatility
5. **test_regime_based_sizing_trending** - Tests 1.2x multiplier in trending markets
6. **test_regime_based_sizing_ranging** - Tests 0.8x multiplier in ranging markets
7. **test_regime_based_sizing_custom_multipliers** - Tests custom multiplier configuration
8. **test_regime_based_sizing_error_handling** - Tests graceful error handling
9. **test_validate_signal_with_regime_adjustment** - Tests integration with signal validation
10. **test_regime_based_sizing_combined_with_correlation** - Tests both adjustments working together

All tests pass successfully (52/52 tests in test_risk_manager.py).

## Usage Example

### Configuration

Enable regime-based sizing in your risk configuration:

```python
risk_config = RiskConfig(
    max_position_size_pct=0.1,
    max_exposure_pct=0.8,
    regime_based_sizing_enabled=True,
    regime_size_multipliers={
        "high_volatility": 0.5,
        "low_volatility": 1.0,
        "trending": 1.2,
        "ranging": 0.8
    }
)
```

### Signal Validation

When validating a signal, pass the PortfolioManager instance:

```python
result = risk_manager.validate_signal(
    signal=trading_signal,
    account=account_info,
    positions=current_positions,
    strategy_allocation_pct=10.0,
    portfolio_manager=portfolio_manager  # Required for regime detection
)

# Check the adjustment in metadata
print(result.metadata['regime_adjustment'])
# Output: "Adjusted to 600.00 (from 1000.00) based on ranging_high_vol regime 
#          (multiplier: 0.5x, confidence: 0.85)"
```

## Benefits

1. **Automatic Risk Management** - Position sizes automatically adjust to market conditions
2. **Reduced Drawdowns** - Smaller positions in volatile/choppy markets reduce risk
3. **Capture Trends** - Larger positions in trending markets maximize profit potential
4. **Configurable** - Multipliers can be customized based on trading style
5. **Transparent** - All adjustments are logged with detailed reasoning
6. **Composable** - Works seamlessly with correlation-based adjustments

## Market Regime Detection

The feature uses `MarketStatisticsAnalyzer.detect_sub_regime()` which analyzes:
- Price trends (20-day and 50-day moving averages)
- Volatility (ATR relative to price)
- Market data quality

Detected regimes include:
- `TRENDING_UP_STRONG` / `TRENDING_UP_WEAK`
- `TRENDING_DOWN_STRONG` / `TRENDING_DOWN_WEAK`
- `RANGING_LOW_VOL` / `RANGING_HIGH_VOL`
- Legacy: `TRENDING_UP`, `TRENDING_DOWN`, `RANGING`

## Configuration Best Practices

### Conservative Approach (Risk-Averse)
```python
regime_size_multipliers={
    "high_volatility": 0.3,  # Very small positions in volatility
    "low_volatility": 1.0,   # Normal size
    "trending": 1.1,         # Slightly larger in trends
    "ranging": 0.6           # Small positions in chop
}
```

### Aggressive Approach (Trend-Following)
```python
regime_size_multipliers={
    "high_volatility": 0.5,  # Moderate reduction
    "low_volatility": 1.2,   # Larger in calm markets
    "trending": 1.5,         # Much larger in trends
    "ranging": 0.7           # Moderate reduction in chop
}
```

### Balanced Approach (Default)
```python
regime_size_multipliers={
    "high_volatility": 0.5,  # 50% reduction
    "low_volatility": 1.0,   # No change
    "trending": 1.2,         # 20% increase
    "ranging": 0.8           # 20% reduction
}
```

## Logging

The feature provides detailed logging at INFO level:

```
INFO: Regime-based position sizing for AAPL: $1000.00 → $500.00 
      (regime: ranging_high_vol, multiplier: 0.5x). 
      Reason: Adjusted to 500.00 (from 1000.00) based on ranging_high_vol regime 
      (multiplier: 0.5x, confidence: 0.85)
```

## Error Handling

The implementation handles errors gracefully:
- If regime detection fails, returns base position size
- If PortfolioManager is not available, returns base position size
- If MarketAnalyzer is not available, returns base position size
- All errors are logged with detailed messages

## Testing

Run the tests:
```bash
python -m pytest tests/test_risk_manager.py::TestRegimeBasedPositionSizing -v
```

All 10 regime-based sizing tests pass, and all 52 risk manager tests pass.

## Next Steps

To use this feature in production:

1. Enable in configuration: Set `regime_based_sizing_enabled=True` in `config/autonomous_trading.yaml`
2. Customize multipliers: Adjust multipliers based on your risk tolerance
3. Monitor performance: Track how regime adjustments affect strategy performance
4. Iterate: Refine multipliers based on backtesting results

## Task Completion

✅ Added `regime_based_sizing_enabled` field to RiskConfig
✅ Added `regime_size_multipliers` field with default values
✅ Extended RiskManager.validate_signal() to adjust size based on regime
✅ Integrated MarketAnalyzer for regime detection
✅ Applied regime multiplier to base position size
✅ Added comprehensive logging
✅ Created 10 unit tests covering all scenarios
✅ All tests pass (52/52)
✅ No diagnostic issues

**Estimated time: 2-3 hours** ✅ Completed
