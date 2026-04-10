# Task 6: Reduce Trading Frequency - Integration Guide

## Overview
Task 6 components are implemented but need to be integrated into the signal generation and order execution flow.

## Components Created

1. **ConvictionScorer** (`src/strategy/conviction_scorer.py`)
   - Scores signals 0-100 based on signal strength, fundamentals, and regime alignment
   - Requires: FundamentalFilter, MarketStatisticsAnalyzer (optional)

2. **TradeFrequencyLimiter** (`src/strategy/trade_frequency_limiter.py`)
   - Enforces monthly trade limits and minimum holding periods
   - Tracks rejected signals in database
   - Fixed: Now uses `opened_at` instead of `entry_time`

3. **TransactionCostTracker** (`src/strategy/transaction_cost_tracker.py`)
   - Calculates and tracks transaction costs
   - Compares costs between periods
   - Generates monthly reports

## Integration Steps

### Step 1: Database Migration

Add the `rejected_signals` table to the database:

```python
# Run this migration or add to your migration script
from src.models.database import get_database
from src.models.orm import Base, RejectedSignalORM

db = get_database()
# This will create the rejected_signals table
Base.metadata.create_all(db.engine, tables=[RejectedSignalORM.__table__])
```

### Step 2: Integrate into StrategyEngine.generate_signals()

Location: `src/strategy/strategy_engine.py`, line ~3145

Add after fundamental filtering (around line 3250):

```python
# Initialize conviction scorer and frequency limiter
from src.strategy.conviction_scorer import ConvictionScorer
from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter

conviction_scorer = ConvictionScorer(
    config=config,
    fundamental_filter=fundamental_filter if fundamental_config.get('enabled') else None,
    market_analyzer=self.market_analyzer if hasattr(self, 'market_analyzer') else None
)

frequency_limiter = TradeFrequencyLimiter(
    config=config,
    database=self.database
)

# Get min conviction threshold
min_conviction = alpha_edge_config.get('min_conviction_score', 70)
```

Then, when generating signals for each symbol, add filtering:

```python
# After creating a signal, before adding to signals list:
for signal in generated_signals:
    # Check frequency limits
    freq_check = frequency_limiter.check_signal_allowed(signal, strategy)
    if not freq_check.allowed:
        frequency_limiter.log_rejected_signal(signal, strategy, freq_check)
        logger.info(f"Signal rejected for {signal.symbol}: {freq_check.reason}")
        continue
    
    # Score conviction
    fundamental_report = None  # Get from fundamental_filter if available
    conviction = conviction_scorer.score_signal(signal, strategy, fundamental_report)
    
    # Check conviction threshold
    if not conviction.passes_threshold(min_conviction):
        logger.info(
            f"Signal rejected for {signal.symbol}: "
            f"conviction {conviction.total_score:.1f} < {min_conviction}"
        )
        continue
    
    # Add conviction score to signal metadata
    if not hasattr(signal, 'metadata'):
        signal.metadata = {}
    signal.metadata['conviction_score'] = conviction.total_score
    signal.metadata['conviction_breakdown'] = conviction.breakdown
    
    # Signal passed all filters
    signals.append(signal)
```

### Step 3: Integrate into Order Execution

Location: Order execution service (likely `src/execution/order_manager.py` or similar)

Add after order is filled:

```python
from src.strategy.trade_frequency_limiter import TradeFrequencyLimiter
from src.strategy.transaction_cost_tracker import TransactionCostTracker

# Initialize (do this once at service startup)
frequency_limiter = TradeFrequencyLimiter(config, database)
cost_tracker = TransactionCostTracker(config, database)

# When order is filled:
def on_order_filled(order):
    # Record trade for frequency tracking
    frequency_limiter.record_trade(
        strategy_id=order.strategy_id,
        symbol=order.symbol,
        timestamp=order.filled_at
    )
    
    # Cost tracking happens automatically via database queries
    # But you can log it explicitly:
    costs = cost_tracker.calculate_trade_cost(
        symbol=order.symbol,
        quantity=order.filled_quantity,
        price=order.expected_price,
        filled_price=order.filled_price
    )
    logger.info(f"Trade costs for {order.symbol}: ${costs['total']:.2f}")
```

### Step 4: Add API Endpoints (Optional)

For monitoring and reporting, add these endpoints:

```python
# In your API router (e.g., src/api/routes.py)

@app.get("/api/conviction-stats")
def get_conviction_stats():
    """Get conviction score statistics."""
    # Query signals with conviction scores
    # Return distribution, averages, etc.
    pass

@app.get("/api/frequency-stats/{strategy_id}")
def get_frequency_stats(strategy_id: str):
    """Get frequency statistics for a strategy."""
    limiter = TradeFrequencyLimiter(config, database)
    return limiter.get_strategy_stats(strategy_id)

@app.get("/api/transaction-costs/monthly/{year}/{month}")
def get_monthly_costs(year: int, month: int):
    """Get monthly transaction cost report."""
    tracker = TransactionCostTracker(config, database)
    return tracker.get_monthly_report(year, month)

@app.get("/api/rejected-signals")
def get_rejected_signals(limit: int = 100):
    """Get recently rejected signals."""
    # Query RejectedSignalORM
    pass
```

## Testing Integration

After integration, verify:

1. **Conviction Scoring Works**
   ```python
   # Check signal metadata has conviction scores
   signals = strategy_engine.generate_signals(strategy)
   for signal in signals:
       assert 'conviction_score' in signal.metadata
       assert 0 <= signal.metadata['conviction_score'] <= 100
   ```

2. **Frequency Limiting Works**
   ```python
   # Generate signals multiple times
   # Verify monthly limit is enforced
   limiter = TradeFrequencyLimiter(config, database)
   stats = limiter.get_strategy_stats(strategy_id)
   assert stats['trades_this_month'] <= stats['max_trades_per_month']
   ```

3. **Cost Tracking Works**
   ```python
   # After executing trades
   tracker = TransactionCostTracker(config, database)
   costs = tracker.get_period_costs()
   assert costs.trade_count > 0
   assert costs.total > 0
   ```

## Configuration

Ensure `config/autonomous_trading.yaml` has:

```yaml
alpha_edge:
  max_active_strategies: 10
  min_conviction_score: 70
  min_holding_period_days: 7
  max_trades_per_strategy_per_month: 4
```

## Expected Impact

After integration:
- **70%+ reduction in transaction costs** (fewer trades)
- **Higher win rate** (only high-conviction signals)
- **Better risk management** (frequency limits prevent overtrading)
- **Improved Sharpe ratio** (quality over quantity)

## Troubleshooting

### Issue: Conviction scores always neutral (50)
- Check that FundamentalFilter is initialized and passed to ConvictionScorer
- Check that MarketStatisticsAnalyzer is available for regime alignment

### Issue: All signals rejected by frequency limiter
- Check database has position records
- Verify `opened_at` timestamps are correct
- Check config values for limits

### Issue: Cost tracking shows $0
- Verify orders have `expected_price` and `filled_price` set
- Check that OrderORM records are being created
- Verify transaction cost config values

## Next Steps

1. Run database migration to add `rejected_signals` table
2. Integrate conviction scoring into `generate_signals()`
3. Integrate frequency limiting into `generate_signals()`
4. Integrate cost tracking into order execution
5. Add API endpoints for monitoring
6. Test with demo account
7. Monitor metrics and adjust thresholds as needed
