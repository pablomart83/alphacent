# AlphaCent Trading Platform

A personal desktop autonomous trading platform for automating trading operations through Interactive Brokers.

## Project Structure

```
alphacent/
├── src/
│   ├── __init__.py
│   ├── main.py              # Main entry point
│   ├── database.py          # SQLite database management
│   ├── config.py            # Configuration management
│   └── logging_config.py    # Logging setup
├── tests/
│   ├── __init__.py
│   └── test_config_serialization.py  # Property-based tests
├── requirements.txt         # Python dependencies
├── setup.py                 # Package setup
└── README.md               # This file
```

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

3. Run tests:
```bash
pytest
```

4. Run the platform:
```bash
python -m src.main
```

## Features

- SQLite database with comprehensive schema
- Configuration management with JSON serialization
- Logging framework with multiple severity levels
- Property-based testing for correctness validation
- Advanced position management with trailing stops and partial exits
- Correlation-adjusted position sizing
- Regime-based position sizing (optional)
- Automated order cancellation for stale orders
- Real-time execution quality tracking

## Requirements

- Python 3.11+
- Interactive Brokers TWS or Gateway (for live trading)
- Ollama (for LLM-powered strategy generation)

## Position Management Configuration

AlphaCent includes advanced position management features that can be configured in `config/autonomous_trading.yaml` and `config/risk_config.json`.

### Trailing Stop-Loss

Automatically move stop-loss levels up as positions become profitable to protect gains.

**Configuration (`autonomous_trading.yaml`):**
```yaml
position_management:
  trailing_stops:
    enabled: true
    activation_pct: 0.05  # Start trailing after 5% profit
    distance_pct: 0.03    # Trail 3% below current price
```

**How it works:**
- When a position reaches 5% profit, the trailing stop activates
- The stop-loss automatically moves up to stay 3% below the current price
- If price drops 3% from the peak, the position exits with protected profit
- Only moves up, never down (protects gains but doesn't increase risk)

**Example:**
- Entry: $100
- Price rises to $105 (5% profit) → Trailing stop activates at $101.85 (3% below)
- Price rises to $110 → Stop moves to $106.70
- Price drops to $106.70 → Position exits with 6.7% profit instead of giving back gains

### Partial Exits

Take profits incrementally at predefined levels while letting the rest of the position run.

**Configuration (`autonomous_trading.yaml`):**
```yaml
position_management:
  partial_exits:
    enabled: true
    levels:
      - profit_pct: 0.05  # Take 50% profit at 5% gain
        exit_pct: 0.5
      - profit_pct: 0.10  # Take 25% more at 10% gain
        exit_pct: 0.25
```

**How it works:**
- At 5% profit, sell 50% of the position (lock in gains)
- At 10% profit, sell 25% more (75% total exited)
- Remaining 25% continues to run with trailing stop
- Each level only triggers once per position

**Example:**
- Entry: 100 shares at $100 ($10,000 position)
- Price hits $105 (5% profit) → Sell 50 shares, lock in $250 profit
- Price hits $110 (10% profit) → Sell 25 shares, lock in $250 more profit
- Remaining 25 shares continue with trailing stop

### Correlation-Adjusted Position Sizing

Automatically reduce position sizes when adding correlated positions to maintain diversification.

**Configuration (`autonomous_trading.yaml`):**
```yaml
position_management:
  correlation_adjustment:
    enabled: true
    threshold: 0.7        # Reduce size if correlation > 0.7
    reduction_factor: 0.5 # Reduce by 50% of correlation
```

**How it works:**
- Before opening a new position, check correlation with existing positions
- If correlation > 0.7, reduce the position size
- Formula: `adjusted_size = base_size * (1 - correlation * 0.5)`
- Prevents over-concentration in correlated assets

**Example:**
- Base position size: $1,000
- New signal for AAPL, already holding MSFT
- AAPL-MSFT correlation: 0.8 (high correlation)
- Adjusted size: $1,000 * (1 - 0.8 * 0.5) = $600
- Opens smaller position to maintain diversification

### Regime-Based Position Sizing

Adjust position sizes based on market volatility and regime (advanced feature, disabled by default).

**Configuration (`autonomous_trading.yaml`):**
```yaml
position_management:
  regime_based_sizing:
    enabled: false        # Disabled by default
    multipliers:
      high_volatility: 0.5  # Reduce size by 50% in high volatility
      low_volatility: 1.0   # Normal size in low volatility
      trending: 1.2         # Increase size by 20% in trending markets
      ranging: 0.8          # Reduce size by 20% in ranging markets
```

**How it works:**
- Analyzes current market regime (volatility and trend)
- Applies multiplier to base position size
- Reduces risk in volatile/uncertain conditions
- Increases exposure in favorable conditions

**Example:**
- Base position size: $1,000
- Market regime: High volatility
- Adjusted size: $1,000 * 0.5 = $500
- Protects capital during turbulent periods

### Order Management

Automatically cancel stale pending orders that haven't filled.

**Configuration (`autonomous_trading.yaml`):**
```yaml
position_management:
  order_management:
    cancel_stale_orders: true
    stale_order_hours: 24  # Cancel orders older than 24 hours
```

**How it works:**
- Monitors all pending orders
- Cancels orders that remain unfilled for more than 24 hours
- Prevents outdated orders from executing at stale prices
- Logs cancellation reason for review

### Risk Configuration

All position management features can also be configured in `config/risk_config.json` for environment-specific settings:

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

### Best Practices

1. **Start Conservative**: Use default settings initially, then adjust based on your risk tolerance
2. **Test in DEMO**: Always test configuration changes in DEMO mode before live trading
3. **Monitor Performance**: Track how each feature impacts your returns and adjust accordingly
4. **Trailing Stops**: Wider distance (5-7%) for volatile assets, tighter (2-3%) for stable assets
5. **Partial Exits**: More aggressive levels (3%, 6%, 9%) for scalping, wider (5%, 10%, 15%) for swing trading
6. **Correlation**: Lower threshold (0.6) for stricter diversification, higher (0.8) for more flexibility
7. **Regime Sizing**: Only enable after understanding your strategy's regime sensitivity

### Disabling Features

To disable any feature, set `enabled: false` in the configuration:

```yaml
position_management:
  trailing_stops:
    enabled: false  # Disables trailing stops
  partial_exits:
    enabled: false  # Disables partial exits
```

Or in `risk_config.json`:

```json
{
  "DEMO": {
    "trailing_stop_enabled": false,
    "partial_exit_enabled": false
  }
}
```
