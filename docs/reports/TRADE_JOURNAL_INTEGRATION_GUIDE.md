# Trade Journal Integration Guide

## Overview
This guide explains how to integrate the Trade Journal into your trading system to log real trades automatically.

## Database Status
✅ Trade journal table exists and is ready for production use
✅ All sample data has been cleared
✅ Database is empty and ready for real trades

## Integration Points

### 1. Order Execution Integration

When an order is filled (entry), log it to the trade journal:

```python
from src.analytics.trade_journal import TradeJournal
from src.models.database import get_database
from datetime import datetime

# Initialize trade journal
db = get_database()
journal = TradeJournal(db)

# When an order is filled (BUY/LONG entry)
def on_order_filled(order, strategy, market_data):
    """Called when an order is filled."""
    
    # Generate unique trade ID
    trade_id = f"{strategy.id}_{order.symbol}_{order.id}"
    
    # Log the entry
    journal.log_entry(
        trade_id=trade_id,
        strategy_id=strategy.id,
        symbol=order.symbol,
        entry_time=order.filled_at or datetime.now(),
        entry_price=order.filled_price,
        entry_size=order.filled_quantity,
        entry_reason=f"Signal: {order.metadata.get('signal_type', 'unknown')}",
        entry_order_id=order.id,
        market_regime=market_data.get('regime'),  # From MarketStatisticsAnalyzer
        sector=market_data.get('sector'),
        conviction_score=order.metadata.get('conviction_score'),  # From ConvictionScorer
        ml_confidence=order.metadata.get('ml_confidence'),  # From MLSignalFilter
        metadata={
            'entry_conditions': order.metadata.get('entry_conditions'),
            'indicators': order.metadata.get('indicators'),
        }
    )
```

### 2. Position Close Integration

When a position is closed (exit), log the exit:

```python
def on_position_closed(position, exit_order, exit_reason):
    """Called when a position is closed."""
    
    # Reconstruct trade ID
    trade_id = f"{position.strategy_id}_{position.symbol}_{position.entry_order_id}"
    
    # Calculate MAE and MFE from position tracking
    mae = calculate_max_adverse_excursion(position)
    mfe = calculate_max_favorable_excursion(position)
    
    # Log the exit
    journal.log_exit(
        trade_id=trade_id,
        exit_time=exit_order.filled_at or datetime.now(),
        exit_price=exit_order.filled_price,
        exit_reason=exit_reason,  # "Target reached", "Stop loss", "Time exit", etc.
        exit_order_id=exit_order.id,
        max_adverse_excursion=mae,  # Percentage
        max_favorable_excursion=mfe,  # Percentage
        exit_slippage=calculate_slippage(exit_order)
    )
```

### 3. Real-time MAE/MFE Tracking

Update MAE/MFE as the trade progresses:

```python
def on_price_update(position, current_price):
    """Called on each price update for open positions."""
    
    # Reconstruct trade ID
    trade_id = f"{position.strategy_id}_{position.symbol}_{position.entry_order_id}"
    
    # Update MAE/MFE
    journal.update_mae_mfe(
        trade_id=trade_id,
        current_price=current_price
    )
```

## Helper Functions

### Calculate MAE/MFE

```python
def calculate_max_adverse_excursion(position):
    """Calculate the worst drawdown during the trade."""
    if not position.price_history:
        return 0.0
    
    entry_price = position.entry_price
    worst_price = min(position.price_history) if position.side == 'LONG' else max(position.price_history)
    
    mae_percent = ((worst_price - entry_price) / entry_price) * 100
    return mae_percent

def calculate_max_favorable_excursion(position):
    """Calculate the best profit during the trade."""
    if not position.price_history:
        return 0.0
    
    entry_price = position.entry_price
    best_price = max(position.price_history) if position.side == 'LONG' else min(position.price_history)
    
    mfe_percent = ((best_price - entry_price) / entry_price) * 100
    return mfe_percent

def calculate_slippage(order):
    """Calculate slippage between expected and actual fill price."""
    if not order.limit_price:
        return 0.0
    
    slippage = abs(order.filled_price - order.limit_price) / order.limit_price
    return slippage
```

## Integration Example: Complete Flow

```python
class TradingSystem:
    def __init__(self):
        self.db = get_database()
        self.journal = TradeJournal(self.db)
        self.conviction_scorer = ConvictionScorer(config)
        self.ml_filter = MLSignalFilter(config, self.db)
        
    def execute_trade(self, strategy, signal):
        """Execute a trade based on a signal."""
        
        # Score conviction
        conviction = self.conviction_scorer.score_signal(signal)
        
        # Filter with ML
        ml_confidence = self.ml_filter.predict_signal_success(signal)
        
        if ml_confidence < 0.70:
            return  # Skip low confidence signals
        
        # Place order
        order = self.place_order(
            symbol=signal.symbol,
            side='BUY',
            quantity=signal.quantity,
            metadata={
                'signal_type': signal.type,
                'conviction_score': conviction,
                'ml_confidence': ml_confidence,
                'entry_conditions': signal.conditions,
                'indicators': signal.indicators,
            }
        )
        
        # Wait for fill
        if order.status == 'FILLED':
            # Log entry to trade journal
            trade_id = f"{strategy.id}_{order.symbol}_{order.id}"
            
            self.journal.log_entry(
                trade_id=trade_id,
                strategy_id=strategy.id,
                symbol=order.symbol,
                entry_time=order.filled_at,
                entry_price=order.filled_price,
                entry_size=order.filled_quantity,
                entry_reason=f"Signal: {signal.type}",
                entry_order_id=order.id,
                market_regime=self.get_current_regime(),
                sector=self.get_symbol_sector(order.symbol),
                conviction_score=conviction,
                ml_confidence=ml_confidence,
                metadata={
                    'entry_conditions': signal.conditions,
                    'indicators': signal.indicators,
                }
            )
            
            # Track position
            self.track_position(trade_id, order)
    
    def close_position(self, position, reason):
        """Close a position and log exit."""
        
        # Place exit order
        exit_order = self.place_order(
            symbol=position.symbol,
            side='SELL',
            quantity=position.quantity
        )
        
        if exit_order.status == 'FILLED':
            # Calculate MAE/MFE
            mae = calculate_max_adverse_excursion(position)
            mfe = calculate_max_favorable_excursion(position)
            
            # Log exit
            trade_id = f"{position.strategy_id}_{position.symbol}_{position.entry_order_id}"
            
            self.journal.log_exit(
                trade_id=trade_id,
                exit_time=exit_order.filled_at,
                exit_price=exit_order.filled_price,
                exit_reason=reason,
                exit_order_id=exit_order.id,
                max_adverse_excursion=mae,
                max_favorable_excursion=mfe,
                exit_slippage=calculate_slippage(exit_order)
            )
```

## Viewing Trade Journal Data

### Frontend
Navigate to: **Analytics → Trade Journal** tab

Features available:
- Filter by strategy, symbol, regime, outcome, date range
- Sort by any column
- View MAE vs MFE scatter plot
- See pattern recognition insights
- Export to CSV

### API Endpoints
- `GET /analytics/trade-journal` - Get all trades
- `GET /analytics/trade-journal/analytics` - Get analytics
- `GET /analytics/trade-journal/patterns` - Get patterns
- `GET /analytics/trade-journal/export` - Export CSV

### Programmatic Access

```python
from src.analytics.trade_journal import TradeJournal
from src.models.database import get_database

db = get_database()
journal = TradeJournal(db)

# Get all closed trades
trades = journal.get_all_trades(closed_only=True)

# Get trades for a specific strategy
strategy_trades = journal.get_all_trades(strategy_id="momentum_strategy_1")

# Calculate win rate
win_rate = journal.calculate_win_rate()

# Get performance by strategy
perf = journal.get_performance_by_strategy()

# Generate insights
insights = journal.generate_insights()
```

## Best Practices

1. **Always log entries immediately** when orders are filled
2. **Update MAE/MFE in real-time** for accurate tracking
3. **Log exits with detailed reasons** for better analysis
4. **Include market context** (regime, sector) for pattern recognition
5. **Store metadata** for debugging and analysis
6. **Use unique trade IDs** to avoid duplicates
7. **Handle errors gracefully** - don't let journal failures stop trading

## Monitoring

Check trade journal health:

```python
# Get open trades count
open_trades = journal.get_open_trades()
print(f"Open trades: {len(open_trades)}")

# Check for stale open trades (open > 30 days)
from datetime import datetime, timedelta
stale_threshold = datetime.now() - timedelta(days=30)
stale_trades = [t for t in open_trades if datetime.fromisoformat(t['entry_time']) < stale_threshold]
if stale_trades:
    print(f"Warning: {len(stale_trades)} stale open trades")
```

## Troubleshooting

### Trade not appearing in journal
- Check if `log_entry()` was called successfully
- Verify trade_id is unique
- Check database logs for errors

### MAE/MFE not updating
- Ensure `update_mae_mfe()` is called on price updates
- Verify trade_id matches the entry
- Check if trade is still open (exit_time is None)

### Export not working
- Check file permissions
- Verify date filters are valid
- Check backend logs for errors

## Production Checklist

- ✅ Sample data cleared
- ✅ Database table created
- ✅ API endpoints tested
- ✅ Frontend UI working
- ✅ Export functionality working
- ⬜ Integration with order execution system
- ⬜ Integration with position management system
- ⬜ Real-time MAE/MFE tracking implemented
- ⬜ Error handling and logging added
- ⬜ Monitoring alerts configured

## Next Steps

1. Integrate `journal.log_entry()` into your order execution flow
2. Integrate `journal.log_exit()` into your position close flow
3. Add `journal.update_mae_mfe()` to your price update handler
4. Test with a few manual trades
5. Monitor the Trade Journal tab to verify data is appearing correctly
6. Set up alerts for stale open trades
7. Review patterns and insights weekly to improve strategies
