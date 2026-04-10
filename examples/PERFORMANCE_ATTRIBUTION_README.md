# Performance Attribution and Benchmarking

This document describes the performance attribution and benchmarking features implemented in the AlphaCent trading platform.

## Features Implemented

### 1. Benchmark Comparison (`compare_to_benchmark`)

Compare strategy returns against market benchmarks like SPY (S&P 500) or BTC-USD (Bitcoin).

**Method Signature:**
```python
def compare_to_benchmark(
    self,
    strategy_id: str,
    benchmark_symbol: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None
) -> Dict[str, float]
```

**Returns:**
- `strategy_return`: Total return of the strategy
- `benchmark_return`: Total return of the benchmark
- `relative_performance`: Strategy return minus benchmark return
- `alpha`: Excess return over benchmark (adjusted for beta)
- `beta`: Strategy volatility relative to benchmark

**Example Usage:**
```python
# Compare strategy to S&P 500
result = strategy_engine.compare_to_benchmark("strategy-id", "SPY")
print(f"Strategy Return: {result['strategy_return']:.2%}")
print(f"Benchmark Return: {result['benchmark_return']:.2%}")
print(f"Alpha: {result['alpha']:.2%}")
print(f"Beta: {result['beta']:.2f}")
```

### 2. P&L Attribution (`attribute_pnl`)

Assign profit and loss to strategies, positions, or time periods to understand what's driving returns.

**Method Signature:**
```python
def attribute_pnl(
    self,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    group_by: str = "strategy"
) -> Dict[str, Dict[str, float]]
```

**Grouping Options:**
- `"strategy"`: Group by strategy to see which strategies are most profitable
- `"position"`: Group by individual positions to see top contributors
- `"time_period"`: Group by time (daily/weekly/monthly) to see performance trends

**Example Usage:**

#### By Strategy
```python
# See which strategies are contributing to returns
attribution = strategy_engine.attribute_pnl(
    start=datetime.now() - timedelta(days=30),
    end=datetime.now(),
    group_by="strategy"
)

for strategy_id, data in attribution.items():
    print(f"{data['name']}: ${data['pnl']:.2f} ({data['contribution_pct']:.1f}%)")
    print(f"  Trades: {data['trades']}, Win Rate: {data['winning_trades']/data['trades']:.1%}")
```

#### By Position
```python
# See which individual positions had the biggest impact
attribution = strategy_engine.attribute_pnl(
    start=datetime.now() - timedelta(days=30),
    end=datetime.now(),
    group_by="position"
)

# Sort by absolute P&L to see biggest winners and losers
sorted_positions = sorted(
    attribution.items(),
    key=lambda x: abs(x[1]["pnl"]),
    reverse=True
)

for pos_id, data in sorted_positions[:10]:
    print(f"{data['symbol']}: ${data['pnl']:.2f} ({data['contribution_pct']:.1f}%)")
```

#### By Time Period
```python
# See performance trends over time
attribution = strategy_engine.attribute_pnl(
    start=datetime.now() - timedelta(days=90),
    end=datetime.now(),
    group_by="time_period"
)

for period, data in attribution.items():
    print(f"{period}: ${data['pnl']:.2f}, {data['trades']} trades")
```

## Implementation Details

### Benchmark Comparison Algorithm

1. Fetches benchmark historical data from market data manager
2. Calculates benchmark return from start to end price
3. Retrieves strategy positions in the time period
4. Builds strategy equity curve from position P&L
5. Calculates daily returns for both strategy and benchmark
6. Computes beta using covariance/variance formula
7. Calculates alpha as: `strategy_return - (beta * benchmark_return)`

### P&L Attribution Algorithm

#### By Strategy
- Groups all positions by strategy_id
- Sums realized and unrealized P&L for each strategy
- Calculates contribution percentage relative to total P&L
- Tracks winning/losing trade counts

#### By Position
- Lists all individual positions with their P&L
- Calculates each position's contribution to total returns
- Includes position details (symbol, entry/exit prices, dates)
- Sorts by absolute P&L to highlight biggest impacts

#### By Time Period
- Groups positions by opening date
- Automatically selects granularity (daily/weekly/monthly) based on date range
- Aggregates P&L, trade counts, and active strategies per period
- Useful for identifying performance trends

## Testing

Comprehensive unit tests cover:
- Benchmark comparison with positions
- Benchmark comparison with no positions
- P&L attribution by strategy
- P&L attribution by position
- P&L attribution by time period
- Invalid parameter handling

Run tests:
```bash
python -m pytest tests/test_strategy_engine.py -k "compare_to_benchmark or attribute_pnl" -v
```

## Example Script

See `examples/performance_attribution_example.py` for a complete working example that demonstrates:
- Comparing multiple strategies to benchmarks
- Attributing P&L by strategy with win rates
- Finding top contributing positions
- Analyzing performance trends over time

Run the example:
```bash
python examples/performance_attribution_example.py
```

## Requirements Validated

This implementation validates the following requirements:

- **Requirement 13.3**: Compare strategy returns against relevant benchmarks (SPY, BTC)
- **Requirement 13.6**: Attribute P&L to specific strategies and positions

## Design Properties Validated

- **Property 26**: Benchmark comparison - Strategy returns are comparable against relevant benchmarks
- **Property 27**: P&L attribution - Profit/loss is correctly attributed to specific strategies and positions
