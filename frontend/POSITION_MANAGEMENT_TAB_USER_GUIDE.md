# Position Management Tab - User Guide

## Quick Start

### How to Access
1. Click the **⚙ Settings** icon in the sidebar
2. Click the **🎯 Position Mgmt** tab (4th tab)
3. You'll see all position management settings

## What You'll See

### Tab Navigation
```
┌─────────────────────────────────────────────────────────────────┐
│ [Trading Mode] [API Config] [Risk Limits] [Position Mgmt] ...  │
│                                              ^^^^^^^^^^^^^^^^    │
│                                              Click here          │
└─────────────────────────────────────────────────────────────────┘
```

### Main Settings Card

```
┌─────────────────────────────────────────────────────────────────┐
│ 🎯 Position Management                                          │
│ Configure advanced position management features including       │
│ trailing stops, partial exits, and dynamic sizing               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌─ TRAILING STOPS ──────────────────────────────────────────┐  │
│ │                                                             │  │
│ │ Enable Trailing Stops                            [ON/OFF]  │  │
│ │ Automatically move stop-loss up as positions become         │  │
│ │ profitable                                                  │  │
│ │                                                             │  │
│ │ When enabled, you'll see:                                  │  │
│ │   Activation Profit (%)    [5.0]                           │  │
│ │   Start trailing after this profit level                   │  │
│ │                                                             │  │
│ │   Trailing Distance (%)    [3.0]                           │  │
│ │   Distance below current price                             │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌─ PARTIAL EXITS ───────────────────────────────────────────┐  │
│ │                                                             │  │
│ │ Enable Partial Exits                             [ON/OFF]  │  │
│ │ Take profits incrementally at predefined levels            │  │
│ │                                                             │  │
│ │ When enabled, you'll see:                                  │  │
│ │   Exit Levels                                              │  │
│ │   ┌─────────────────────────────────────────────────────┐ │  │
│ │   │ Profit Level (%)  [5.0]  Exit Size (%)  [50.0]     │ │  │
│ │   └─────────────────────────────────────────────────────┘ │  │
│ │   ┌─────────────────────────────────────────────────────┐ │  │
│ │   │ Profit Level (%)  [10.0] Exit Size (%)  [25.0]     │ │  │
│ │   └─────────────────────────────────────────────────────┘ │  │
│ │   Example: At 5% profit, exit 50% of position;            │  │
│ │   at 10% profit, exit 25% more                            │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌─ CORRELATION ADJUSTMENT ──────────────────────────────────┐  │
│ │                                                             │  │
│ │ Enable Correlation Adjustment                    [ON/OFF]  │  │
│ │ Reduce position sizes for correlated assets to maintain    │  │
│ │ diversification                                             │  │
│ │                                                             │  │
│ │ When enabled, you'll see:                                  │  │
│ │   Correlation Threshold    [0.70]                          │  │
│ │   Trigger adjustment when correlation exceeds this         │  │
│ │                                                             │  │
│ │   Reduction Factor         [0.50]                          │  │
│ │   Size reduction multiplier                                │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌─ REGIME-BASED SIZING (ADVANCED) ─────────────────────────┐  │
│ │                                                             │  │
│ │ Enable Regime-Based Sizing                       [ON/OFF]  │  │
│ │ Adjust position sizes based on market volatility and       │  │
│ │ regime (advanced)                                           │  │
│ │                                                             │  │
│ │ When enabled, you'll see:                                  │  │
│ │   Regime Multipliers                                       │  │
│ │   High Volatility  [0.5]  Low Volatility   [1.0]          │  │
│ │   Trending Market  [1.2]  Ranging Market   [0.8]          │  │
│ │   Multipliers adjust base position size                    │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌─ ORDER MANAGEMENT ────────────────────────────────────────┐  │
│ │                                                             │  │
│ │ Cancel Stale Orders                              [ON/OFF]  │  │
│ │ Automatically cancel pending orders that haven't filled    │  │
│ │                                                             │  │
│ │ When enabled, you'll see:                                  │  │
│ │   Stale Order Timeout (hours)  [24]                        │  │
│ │   Cancel orders older than this many hours                 │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌─ ⚠ WARNING ──────────────────────────────────────────────┐  │
│ │ Advanced Features                                           │  │
│ │ These settings directly impact trading behavior. Test       │  │
│ │ thoroughly in DEMO mode before enabling in LIVE mode.       │  │
│ │ Regime-based sizing is an advanced feature - only enable    │  │
│ │ after understanding your strategy's regime sensitivity.     │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ [Save Position Management Settings]  [Reset]                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## How to Use Each Feature

### 1. Trailing Stops

**What it does**: Automatically moves your stop-loss up as the price increases, protecting your profits.

**How to configure**:
1. Toggle "Enable Trailing Stops" to ON
2. Set "Activation Profit" (when to start trailing)
   - Example: 5% means start trailing after 5% profit
3. Set "Trailing Distance" (how far below peak)
   - Example: 3% means exit if price drops 3% from peak

**Example scenario**:
- You buy at $100
- Price rises to $105 (5% profit) → Trailing activates, stop at $101.85
- Price rises to $110 → Stop moves to $106.70
- Price drops to $106.70 → Position exits with 6.7% profit

**Recommended settings**:
- Conservative: 3% activation, 5% distance
- Moderate: 5% activation, 3% distance (default)
- Aggressive: 7% activation, 2% distance

### 2. Partial Exits

**What it does**: Takes profits incrementally at different levels while letting part of the position continue.

**How to configure**:
1. Toggle "Enable Partial Exits" to ON
2. Configure Level 1:
   - Profit Level: When to take first profit (e.g., 5%)
   - Exit Size: How much to exit (e.g., 50%)
3. Configure Level 2:
   - Profit Level: When to take second profit (e.g., 10%)
   - Exit Size: How much more to exit (e.g., 25%)

**Example scenario**:
- You buy 100 shares at $100 ($10,000 position)
- Price hits $105 (5% profit) → Sell 50 shares, lock in $250
- Price hits $110 (10% profit) → Sell 25 shares, lock in $250 more
- Remaining 25 shares continue with trailing stop

**Recommended settings**:
- Scalping: 3% → 50%, 6% → 30%
- Swing Trading: 5% → 50%, 10% → 25% (default)
- Position Trading: 10% → 30%, 20% → 30%

### 3. Correlation Adjustment

**What it does**: Reduces position size when adding correlated positions to maintain diversification.

**How to configure**:
1. Toggle "Enable Correlation Adjustment" to ON
2. Set "Correlation Threshold" (when to trigger)
   - Example: 0.7 means adjust if correlation > 70%
3. Set "Reduction Factor" (how much to reduce)
   - Example: 0.5 means reduce by 50% of correlation

**Example scenario**:
- Base position size: $1,000
- New signal for AAPL, already holding MSFT
- AAPL-MSFT correlation: 0.8 (80%)
- Adjusted size: $1,000 × (1 - 0.8 × 0.5) = $600

**Recommended settings**:
- Strict diversification: 0.6 threshold, 0.6 reduction
- Moderate: 0.7 threshold, 0.5 reduction (default)
- Relaxed: 0.8 threshold, 0.4 reduction

### 4. Regime-Based Sizing (Advanced)

**What it does**: Adjusts position sizes based on current market conditions (volatility and trend).

**How to configure**:
1. Toggle "Enable Regime-Based Sizing" to ON
2. Set multipliers for each regime:
   - High Volatility: Size in volatile markets (e.g., 0.5 = half size)
   - Low Volatility: Size in calm markets (e.g., 1.0 = normal)
   - Trending: Size in trending markets (e.g., 1.2 = 20% larger)
   - Ranging: Size in ranging markets (e.g., 0.8 = 20% smaller)

**Example scenario**:
- Base position size: $1,000
- Market regime: High volatility
- Adjusted size: $1,000 × 0.5 = $500

**Recommended settings**:
- Conservative: All 0.7-1.0 (never increase)
- Moderate: 0.5, 1.0, 1.2, 0.8 (default)
- Aggressive: 0.3, 1.0, 1.5, 0.7

**⚠️ Warning**: This is an advanced feature. Only enable after:
- Understanding how your strategies perform in different regimes
- Backtesting with regime-based sizing
- Testing in DEMO mode for at least 1 month

### 5. Order Management

**What it does**: Automatically cancels pending orders that haven't filled after a timeout.

**How to configure**:
1. Toggle "Cancel Stale Orders" to ON
2. Set "Stale Order Timeout" in hours
   - Example: 24 hours = cancel after 1 day

**Example scenario**:
- Order placed at 9:00 AM Monday
- Order still pending at 9:00 AM Tuesday (24 hours)
- System automatically cancels the order

**Recommended settings**:
- Day trading: 4 hours
- Swing trading: 24 hours (default)
- Position trading: 72 hours

## Saving Your Settings

### Step-by-Step
1. Make your changes in the form
2. Click "Save Position Management Settings" button
3. Wait for success message: "Position management settings saved successfully"
4. Settings are now active and will persist across restarts

### What Happens When You Save
1. Form validates all inputs
2. Converts percentages to decimals for backend
3. Calls API to update configuration
4. Backend saves to `config/risk_config.json`
5. Settings take effect immediately
6. Last updated timestamp refreshes

### If Save Fails
- Check your internet connection
- Verify you're logged in
- Check browser console for errors
- Try again or contact support

## Resetting to Defaults

### How to Reset
1. Click "Reset" button
2. Form restores default values
3. Review the defaults
4. Click "Save" if you want to keep defaults

### Default Values
- Trailing Stops: Enabled, 5% activation, 3% distance
- Partial Exits: Enabled, 50% at 5%, 25% at 10%
- Correlation Adjustment: Enabled, 0.7 threshold, 0.5 reduction
- Regime-Based Sizing: Disabled
- Stale Order Cancellation: Enabled, 24 hours

## Best Practices

### 1. Start Conservative
- Use default settings initially
- Enable one feature at a time
- Monitor impact on performance

### 2. Test in DEMO Mode
- Always test changes in DEMO mode first
- Run for at least 1 week before going live
- Compare performance with and without features

### 3. Monitor Results
- Track win rate, Sharpe ratio, max drawdown
- Review execution quality metrics
- Adjust based on observed behavior

### 4. Adjust Gradually
- Make small incremental changes
- Test each change thoroughly
- Document what works for your strategies

### 5. Advanced Features Last
- Master basic features first
- Only enable regime-based sizing after extensive testing
- Understand the math behind each feature

## Troubleshooting

### Settings Not Saving
- **Check**: Are you logged in?
- **Check**: Is trading mode set (DEMO/LIVE)?
- **Try**: Refresh page and try again
- **Try**: Check browser console for errors

### Features Not Working
- **Check**: Is the feature enabled (toggle ON)?
- **Check**: Are the parameters valid (within ranges)?
- **Check**: Did you click "Save" after changes?
- **Try**: Reset to defaults and reconfigure

### Unexpected Behavior
- **Check**: Review logs for error messages
- **Check**: Verify settings match your intent
- **Try**: Disable feature and test without it
- **Try**: Test in DEMO mode first

## Support

### Documentation
- `README.md` - Comprehensive guide with examples
- `POSITION_MANAGEMENT_CONFIG_GUIDE.md` - Quick reference
- This guide - User interface walkthrough

### Getting Help
1. Check documentation first
2. Test in DEMO mode
3. Review logs for errors
4. Contact support with specific details

## Summary

The Position Management tab gives you complete control over advanced trading features:

✅ **Trailing Stops** - Protect profits automatically
✅ **Partial Exits** - Take profits incrementally
✅ **Correlation Adjustment** - Maintain diversification
✅ **Regime-Based Sizing** - Adapt to market conditions
✅ **Order Management** - Clean up stale orders

All features are optional and can be enabled/disabled independently. Start with defaults, test in DEMO mode, and adjust based on your results.

Happy trading! 🚀
