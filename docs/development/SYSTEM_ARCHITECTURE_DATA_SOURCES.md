# System Architecture: Data Sources and Trading Operations

## Overview
This document explains how the autonomous trading system uses different data sources for analysis vs. execution.

## Data Source Strategy

### Yahoo Finance (Market Data & Analysis)
**Used for:**
- Historical OHLCV data for backtesting
- Market regime analysis
- Strategy signal generation
- Performance benchmarking
- All technical indicator calculations

**Why Yahoo Finance:**
- Provides 10+ years of historical data
- Consistent data format across all symbols
- Free and reliable API
- Industry-standard adjusted prices (splits, dividends)

**Configuration:**
All `get_historical_data()` calls use `prefer_yahoo=True` to ensure consistency.

### eToro API (Trading Operations Only)
**Used for:**
- Account information
- Position management
- Order placement and execution
- Real-time portfolio tracking
- Trade execution and fills

**Why eToro for Trading Only:**
- eToro doesn't provide reliable historical OHLCV data
- eToro's `get_historical_data()` actually falls back to Yahoo Finance internally
- Real-time trading operations require eToro's authenticated API

## Critical Design Decision

### The Data Consistency Problem (FIXED)
**Previous Issue:**
- Backtesting used Yahoo Finance data (`prefer_yahoo=True`)
- Live signal generation used eToro data (`prefer_yahoo=False`)
- This created a training-testing mismatch
- Strategies optimized on Yahoo data failed on eToro data
- Result: Negative Sharpe ratios in live trading

**Current Solution:**
- ALL market data analysis uses Yahoo Finance (`prefer_yahoo=True`)
- Backtesting, signal generation, and validation all use the same data source
- eToro is used ONLY for trade execution
- This ensures strategies are tested on the same data they'll use in production

## Transaction Costs

### Current Configuration (config/autonomous_trading.yaml)
```yaml
transaction_costs:
  commission_per_share: 0.005      # $0.005 per share
  commission_percent: 0.001        # 0.1% commission
  slippage_percent: 0.0005         # 0.05% slippage
  spread_percent: 0.0002           # 0.02% spread
```

**Note:** These should be calibrated based on actual eToro execution costs. Monitor live trades and adjust accordingly.

## Files Modified

### Core Strategy Engine
- `src/strategy/strategy_engine.py`
  - `backtest_strategy()`: Uses `prefer_yahoo=True`
  - `generate_signals()`: Uses `prefer_yahoo=True`
  - `validate_strategy_signals()`: Uses `prefer_yahoo=True`
  - `compare_to_benchmark()`: Uses `prefer_yahoo=True`

### Market Analysis
- `src/strategy/market_analyzer.py`
  - `analyze_symbol()`: Uses `prefer_yahoo=True`
  - `analyze_indicator_distributions()`: Uses `prefer_yahoo=True`

### Strategy Proposer
- `src/strategy/strategy_proposer.py`
  - `analyze_market_conditions()`: Uses `prefer_yahoo=True`

### Configuration
- `config/autonomous_trading.yaml`
  - Updated `min_days_required` to 980 (Yahoo Finance provides extensive history)
  - Added comments explaining data source strategy

## Verification Steps

To verify the system is working correctly:

1. **Check logs for data source:**
   ```bash
   tail -f backend.log | grep "Yahoo Finance"
   ```
   You should see: "Fetching historical data for {symbol} from Yahoo Finance"

2. **Verify backtesting uses Yahoo:**
   - Run an autonomous cycle
   - Check that all backtest data fetches use Yahoo Finance
   - Confirm no eToro historical data calls

3. **Verify live signals use Yahoo:**
   - Activate a strategy
   - Check signal generation logs
   - Confirm Yahoo Finance is used for indicator calculations

4. **Verify eToro is used for trading:**
   - Place a test order
   - Check that eToro API is called for order placement
   - Confirm positions are fetched from eToro

## Expected Behavior

### Autonomous Cycle
1. Market regime analysis → Yahoo Finance data
2. Strategy proposal → Yahoo Finance data
3. Backtesting → Yahoo Finance data
4. Walk-forward validation → Yahoo Finance data
5. Strategy activation → eToro API (no data fetch)

### Live Trading
1. Signal generation → Yahoo Finance data
2. Order placement → eToro API
3. Position tracking → eToro API
4. Performance monitoring → eToro API + Yahoo Finance (for benchmarks)

## Troubleshooting

### Strategies still have negative Sharpe ratios
- Check that all `get_historical_data()` calls include `prefer_yahoo=True`
- Verify transaction costs match actual eToro fees
- Review strategy validation rules (may be too permissive)
- Check if market regime detection is accurate

### Data fetch errors
- Verify Yahoo Finance is accessible
- Check symbol mappings (e.g., "BTC" → "BTC-USD")
- Ensure sufficient historical data is available
- Review rate limiting settings

### eToro trading errors
- Verify API keys are correct
- Check account has sufficient balance
- Confirm trading mode (DEMO vs LIVE)
- Review eToro API rate limits

## Future Improvements

1. **Paper Trading Mode:**
   - Test strategies on eToro demo account with real data
   - Compare expected vs actual execution prices
   - Calibrate transaction cost models

2. **Data Source Validation:**
   - Add logging to track which data source is used for each operation
   - Implement data quality checks
   - Alert on data source mismatches

3. **Transaction Cost Calibration:**
   - Track actual eToro execution costs
   - Update config based on real trading data
   - Implement dynamic cost models based on market conditions

4. **Performance Attribution:**
   - Separate strategy alpha from execution costs
   - Track slippage and spread impact
   - Identify optimization opportunities
