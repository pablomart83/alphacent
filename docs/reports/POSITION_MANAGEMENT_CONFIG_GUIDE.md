# Position Management Configuration Guide

This document provides a quick reference for configuring the advanced position management features in AlphaCent.

## Configuration Files

Position management features are configured in two files:
- `config/autonomous_trading.yaml` - Main configuration with detailed settings
- `config/risk_config.json` - Environment-specific risk parameters

## Quick Reference

### Feature Overview

| Feature | Default | Purpose | Risk Level |
|---------|---------|---------|------------|
| Trailing Stops | Enabled | Protect profits by moving stop-loss up | Low |
| Partial Exits | Enabled | Take incremental profits | Low |
| Correlation Adjustment | Enabled | Reduce size for correlated positions | Medium |
| Regime-Based Sizing | Disabled | Adjust size based on market conditions | High |
| Stale Order Cancellation | Enabled | Cancel unfilled orders after timeout | Low |

### Configuration Parameters

#### Trailing Stops
```yaml
trailing_stops:
  enabled: true
  activation_pct: 0.05    # Activate after 5% profit
  distance_pct: 0.03      # Trail 3% below peak
```

**Tuning Guidelines:**
- Conservative: `activation_pct: 0.03`, `distance_pct: 0.05` (activate early, wider trail)
- Aggressive: `activation_pct: 0.07`, `distance_pct: 0.02` (activate late, tighter trail)
- Volatile assets: Increase `distance_pct` to 0.05-0.07
- Stable assets: Decrease `distance_pct` to 0.02-0.03

#### Partial Exits
```yaml
partial_exits:
  enabled: true
  levels:
    - profit_pct: 0.05    # First exit at 5% profit
      exit_pct: 0.5       # Exit 50% of position
    - profit_pct: 0.10    # Second exit at 10% profit
      exit_pct: 0.25      # Exit 25% more (75% total)
```

**Tuning Guidelines:**
- Scalping: `[{0.03, 0.5}, {0.06, 0.3}]` - Take profits quickly
- Swing Trading: `[{0.05, 0.5}, {0.10, 0.25}]` - Default settings
- Position Trading: `[{0.10, 0.3}, {0.20, 0.3}]` - Let winners run longer
- Can add up to 5 levels for more granular exits

#### Correlation Adjustment
```yaml
correlation_adjustment:
  enabled: true
  threshold: 0.7          # Trigger when correlation > 0.7
  reduction_factor: 0.5   # Reduce by 50% of correlation
```

**Tuning Guidelines:**
- Strict diversification: `threshold: 0.6`, `reduction_factor: 0.6`
- Moderate diversification: `threshold: 0.7`, `reduction_factor: 0.5` (default)
- Relaxed diversification: `threshold: 0.8`, `reduction_factor: 0.4`
- Formula: `adjusted_size = base_size * (1 - correlation * reduction_factor)`

#### Regime-Based Sizing (Advanced)
```yaml
regime_based_sizing:
  enabled: false          # Disabled by default
  multipliers:
    high_volatility: 0.5  # Reduce size in high volatility
    low_volatility: 1.0   # Normal size in low volatility
    trending: 1.2         # Increase size in trends
    ranging: 0.8          # Reduce size in ranges
```

**Tuning Guidelines:**
- Conservative: All multipliers between 0.7-1.0 (never increase size)
- Moderate: `high_volatility: 0.5`, others 0.8-1.2 (default)
- Aggressive: `high_volatility: 0.3`, `trending: 1.5` (bigger swings)
- **Warning**: Only enable after backtesting with your strategies

#### Order Management
```yaml
order_management:
  cancel_stale_orders: true
  stale_order_hours: 24   # Cancel after 24 hours
```

**Tuning Guidelines:**
- Day trading: `stale_order_hours: 4` (cancel same day)
- Swing trading: `stale_order_hours: 24` (default)
- Position trading: `stale_order_hours: 72` (allow 3 days)

## Environment-Specific Configuration

Use `config/risk_config.json` to override settings per environment:

```json
{
  "DEMO": {
    "trailing_stop_enabled": true,
    "trailing_stop_activation_pct": 0.05,
    "trailing_stop_distance_pct": 0.03,
    "partial_exit_enabled": true,
    "partial_exit_levels": [
      {"profit_pct": 0.05, "exit_pct": 0.5},
      {"profit_pct": 0.10, "exit_pct": 0.25}
    ],
    "correlation_adjustment_enabled": true,
    "correlation_threshold": 0.7,
    "correlation_reduction_factor": 0.5,
    "regime_based_sizing_enabled": false,
    "regime_multipliers": {
      "high_volatility": 0.5,
      "low_volatility": 1.0,
      "trending": 1.2,
      "ranging": 0.8
    },
    "cancel_stale_orders": true,
    "stale_order_hours": 24
  }
}
```

## Common Configuration Scenarios

### Conservative Trader
```yaml
position_management:
  trailing_stops:
    enabled: true
    activation_pct: 0.03    # Activate early
    distance_pct: 0.05      # Wide trail
  partial_exits:
    enabled: true
    levels:
      - profit_pct: 0.03
        exit_pct: 0.5
      - profit_pct: 0.06
        exit_pct: 0.3
  correlation_adjustment:
    enabled: true
    threshold: 0.6          # Strict diversification
    reduction_factor: 0.6
  regime_based_sizing:
    enabled: false
```

### Aggressive Trader
```yaml
position_management:
  trailing_stops:
    enabled: true
    activation_pct: 0.07    # Activate late
    distance_pct: 0.02      # Tight trail
  partial_exits:
    enabled: true
    levels:
      - profit_pct: 0.10
        exit_pct: 0.3
      - profit_pct: 0.20
        exit_pct: 0.3
  correlation_adjustment:
    enabled: true
    threshold: 0.8          # Relaxed diversification
    reduction_factor: 0.4
  regime_based_sizing:
    enabled: true
    multipliers:
      high_volatility: 0.3
      low_volatility: 1.0
      trending: 1.5
      ranging: 0.7
```

### Scalper
```yaml
position_management:
  trailing_stops:
    enabled: true
    activation_pct: 0.02
    distance_pct: 0.01
  partial_exits:
    enabled: true
    levels:
      - profit_pct: 0.02
        exit_pct: 0.5
      - profit_pct: 0.04
        exit_pct: 0.3
      - profit_pct: 0.06
        exit_pct: 0.2
  correlation_adjustment:
    enabled: false          # Allow correlated positions
  regime_based_sizing:
    enabled: false
  order_management:
    cancel_stale_orders: true
    stale_order_hours: 4    # Cancel quickly
```

## Testing Configuration Changes

1. **Backup current config**: `cp config/autonomous_trading.yaml config/autonomous_trading.yaml.backup`
2. **Make changes**: Edit the YAML file with your new settings
3. **Validate syntax**: `python -c "import yaml; yaml.safe_load(open('config/autonomous_trading.yaml'))"`
4. **Test in DEMO**: Run the system in DEMO mode for at least 1 week
5. **Monitor metrics**: Track win rate, Sharpe ratio, max drawdown
6. **Adjust as needed**: Fine-tune based on observed performance

## Troubleshooting

### Trailing stops not activating
- Check `activation_pct` is not too high
- Verify positions are reaching profit threshold
- Check logs for "Trailing stop activated" messages

### Partial exits not executing
- Verify `partial_exit_enabled: true`
- Check profit levels are being reached
- Ensure position size is large enough to split

### Correlation adjustment too aggressive
- Increase `threshold` (e.g., 0.7 → 0.8)
- Decrease `reduction_factor` (e.g., 0.5 → 0.4)
- Check correlation matrix in logs

### Regime sizing causing issues
- Disable feature: `enabled: false`
- Use more conservative multipliers (0.7-1.0 range)
- Verify regime detection is accurate

## Performance Impact

Expected impact on key metrics (based on backtesting):

| Feature | Win Rate | Sharpe Ratio | Max Drawdown | Profit Factor |
|---------|----------|--------------|--------------|---------------|
| Trailing Stops | +2-5% | +0.1-0.3 | -10-20% | +0.05-0.15 |
| Partial Exits | +3-7% | +0.2-0.4 | -5-15% | +0.10-0.20 |
| Correlation Adj | 0-2% | +0.1-0.2 | -5-10% | 0-0.05 |
| Regime Sizing | -2-5% | +0.2-0.5 | -15-30% | +0.10-0.25 |

**Note**: Actual results vary by strategy, market conditions, and parameter settings.

## Support

For questions or issues with configuration:
1. Check logs in `logs/` directory
2. Review implementation docs in `TRAILING_STOP_IMPLEMENTATION.md` and `PARTIAL_EXIT_IMPLEMENTATION.md`
3. Test with demo data before live trading
