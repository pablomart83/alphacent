# Analytics Page Dead Data Bugfix Design

## Overview

All 6 analytics tabs display zero/empty data despite 30 FILLED orders and 95 positions in the database. The root cause is twofold: (1) analytics endpoints calculate P&L exclusively from `OrderORM.filled_price`, which is `None` for every order, and (2) the order fill flow never sets `filled_price` when transitioning orders to FILLED status. The fix rewires analytics endpoints to use `PositionORM` data (which has rich P&L from eToro sync) and backfills `filled_price` in both order fill paths.

## Glossary

- **Bug_Condition (C)**: Any analytics endpoint that computes P&L by checking `order.filled_price and order.filled_quantity` — since `filled_price` is always `None`, the guard evaluates to `False` and every order is skipped
- **Property (P)**: Analytics endpoints return populated metrics derived from `PositionORM` data (`entry_price`, `current_price`, `unrealized_pnl`, `realized_pnl`, `closed_at`)
- **Preservation**: Alpha Edge tab endpoints, Regime Analysis metadata queries, Trade Journal export, correlation matrix empty-state handling, position sync/reconciliation logic, and order monitor dedup logic must remain unchanged
- **`get_performance_analytics()`**: Endpoint in `src/api/routers/analytics.py` that builds equity curve and calculates Sharpe, Sortino, drawdown, win rate, profit factor from orders
- **`get_strategy_attribution()`**: Endpoint that calculates per-strategy P&L contribution from orders
- **`get_trade_analytics()`**: Endpoint that calculates win/loss distribution, avg win/loss, holding times from orders
- **`get_correlation_matrix()`**: Endpoint that computes strategy return correlations from orders
- **`check_submitted_orders()`**: Method in `src/core/order_monitor.py` that transitions orders to FILLED but never sets `filled_price`
- **`run_signal_generation_sync()`**: Method in `src/core/trading_scheduler.py` that creates positions immediately after fill but uses `order.filled_price or order.expected_price or 0` for `entry_price`

## Bug Details

### Fault Condition

The bug manifests when any analytics endpoint processes FILLED orders. Every endpoint guards P&L calculation with `if order.filled_price and order.filled_quantity`, but `filled_price` is `None` for all 30 FILLED orders. This causes every order to be skipped, producing zero metrics across all tabs.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type AnalyticsRequest (mode, period, endpoint_name)
  OUTPUT: boolean

  orders := query OrderORM WHERE status == FILLED AND filled_at >= start_date
  RETURN ANY order IN orders WHERE order.filled_price IS NULL
         AND endpoint_name IN ['performance', 'strategy-attribution', 'trade-analytics', 'correlation-matrix']
END FUNCTION
```

### Examples

- **Performance tab**: User loads Performance tab → endpoint queries 30 FILLED orders → all skip the `if order.filled_price and order.filled_quantity` guard → returns 0.0% total return, 0.0 Sharpe, empty equity curve
- **Strategy Attribution tab**: User loads Strategy Attribution → endpoint iterates strategies, queries their orders → all orders skipped → returns empty attribution list
- **Trade Analytics tab**: User loads Trade Analytics → endpoint queries 30 FILLED orders → all skipped → returns 0 total trades, 0.0% win rate, 0.0 profit factor
- **Correlation Matrix**: Endpoint queries orders per strategy → all skipped → empty return arrays → 0.0 correlations, meaningless diversification score
- **Trade Journal tab**: Uses `TradeJournal` class which has its own P&L path, but `performance-stats` endpoint still shows zeros

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- Alpha Edge tab endpoints (`fundamental-stats`, `ml-stats`, `conviction-distribution`, `template-performance`) must continue querying their respective log tables (`FundamentalFilterLogORM`, `MLFilterLogORM`, `ConvictionScoreLogORM`)
- Regime Analysis endpoint must continue deriving regime data from `StrategyORM.rules` and `StrategyORM.performance` metadata
- Trade Journal export must continue using the `TradeJournal` class for CSV export
- Correlation matrix must continue returning empty matrix with 0.0 avg correlation and 1.0 diversification score when fewer than 2 strategies have positions
- `check_submitted_orders` must continue performing symbol normalization, dedup checks, and strategy_id assignment
- `reconcile_on_startup` must continue syncing positions from eToro without being affected by analytics data source changes
- Future orders that have valid `filled_price` must be included in calculations without double-counting against position data

**Scope:**
All inputs that do NOT involve the four order-based analytics endpoints (performance, strategy-attribution, trade-analytics, correlation-matrix) or the order fill paths should be completely unaffected by this fix. This includes:
- Alpha Edge tab queries
- Regime Analysis metadata queries
- Trade Journal operations
- Position sync and reconciliation
- Order submission and execution

## Hypothesized Root Cause

Based on the bug description and code analysis, the issues are:

1. **Missing `filled_price` Assignment in `check_submitted_orders()`**: When an order transitions to FILLED (lines setting `order.status = OrderStatus.FILLED`), the code sets `filled_at` and `filled_quantity` but never sets `filled_price`. The matched eToro position (`etoro_pos`) has `entry_price` available but it's never copied to `order.filled_price`.

2. **Missing `filled_price` Assignment in `run_signal_generation_sync()`**: The immediate position creation path sets `order_orm.filled_at` and `order_orm.filled_quantity` but never sets `order_orm.filled_price`. The eToro status response or matched position data has the entry price available.

3. **Analytics Endpoints Use Wrong Data Source**: All four analytics endpoints (`get_performance_analytics`, `get_strategy_attribution`, `get_trade_analytics`, `get_correlation_matrix`) query `OrderORM` and compute P&L from `filled_price * filled_quantity * 0.01` (a simplified placeholder formula). They completely ignore `PositionORM` which has accurate `entry_price`, `current_price`, `unrealized_pnl`, `realized_pnl`, and `closed_at` from eToro sync.

4. **Cascading Position Entry Price Issue**: In `trading_scheduler.py`, the immediate position creation uses `entry_price=order.filled_price or order.expected_price or 0`. Since `filled_price` is always `None`, positions get `expected_price` (or 0) as entry price instead of the actual eToro fill price.

## Correctness Properties

Property 1: Fault Condition - Analytics Endpoints Return Populated Data From Positions

_For any_ analytics request where FILLED orders exist in the database with `filled_price = None` but corresponding `PositionORM` records exist with valid `entry_price`, `current_price`, and P&L data, the fixed analytics endpoints SHALL return non-zero metrics (equity curve points, strategy attributions, trade counts, correlation values) derived from position-level data.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

Property 2: Preservation - Non-Analytics Endpoint Behavior

_For any_ request to Alpha Edge tab endpoints, Regime Analysis, Trade Journal export, or any non-analytics operation (position sync, order submission, reconciliation), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing functionality for these unaffected paths.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7**

Property 3: Fault Condition - Order Fill Sets filled_price

_For any_ order that transitions to FILLED status via `check_submitted_orders()` or `run_signal_generation_sync()`, the fixed code SHALL set `order.filled_price` to the `entry_price` from the matched eToro position data, ensuring future orders have valid P&L data.

**Validates: Requirements 2.6, 2.7**

Property 4: Preservation - Position Creation and Dedup Logic

_For any_ order fill event, the fixed code SHALL continue to perform symbol normalization, dedup checks, strategy_id assignment, and position creation exactly as before, with the only addition being the `filled_price` assignment.

**Validates: Requirements 3.6, 3.7**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/api/routers/analytics.py`

**Functions**: `get_performance_analytics`, `get_strategy_attribution`, `get_trade_analytics`, `get_correlation_matrix`

**Specific Changes**:
1. **Switch data source from OrderORM to PositionORM**: Replace order-based queries with position-based queries. Use `PositionORM` fields: `entry_price`, `current_price`, `unrealized_pnl`, `realized_pnl`, `closed_at`, `opened_at`, `strategy_id`, `symbol`, `side`.

2. **`get_performance_analytics`**: Query all positions (open + closed). For closed positions (`closed_at IS NOT NULL`), use `realized_pnl` as the trade P&L. For open positions, use `unrealized_pnl`. Build equity curve from position open/close timestamps. Calculate Sharpe, Sortino, drawdown, win rate, profit factor from position-level P&L.

3. **`get_strategy_attribution`**: Group positions by `strategy_id`. Sum `realized_pnl + unrealized_pnl` per strategy. Calculate contribution percentages and win rates from position data.

4. **`get_trade_analytics`**: Use closed positions as "completed trades". Calculate win/loss from `realized_pnl`. Use `opened_at` and `closed_at` for holding time. Build win/loss distribution from position P&L values.

5. **`get_correlation_matrix`**: Already queries `PositionORM` for strategy IDs but then falls back to `OrderORM` for return calculation. Fix the return calculation to use position P&L data instead of order `filled_price`.

---

**File**: `src/core/order_monitor.py`

**Function**: `check_submitted_orders`

**Specific Changes**:
6. **Set `filled_price` from matched eToro position**: In the `if order_filled:` block (after the order is marked FILLED), when `etoro_pos` is found, add `order.filled_price = etoro_pos.entry_price`. This ensures future orders have valid P&L data.

7. **Set `filled_price` for placeholder ID matches**: In the `pending_` placeholder branch where orders are matched by symbol, also set `order.filled_price` from the matched position's entry price.

---

**File**: `src/core/trading_scheduler.py`

**Function**: `run_signal_generation_sync`

**Specific Changes**:
8. **Set `filled_price` on immediate fill**: When the order status check returns FILLED (status 2, 3, or 7), set `order_orm.filled_price` from the eToro position data. If positions are available in the status response, extract the entry price. Otherwise, use the matched position's entry price.

9. **Fix position `entry_price` fallback**: Change `entry_price=order.filled_price or order.expected_price or 0` to use the actual eToro position entry price when available, falling back to `order_orm.filled_price` (which will now be set).

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Fault Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that query the analytics endpoints with the current database state (30 FILLED orders, all with `filled_price=None`) and assert that the responses contain zero/empty data. Run these tests on the UNFIXED code to observe failures and understand the root cause.

**Test Cases**:
1. **Performance Analytics Zero Test**: Call `get_performance_analytics` → assert `total_return == 0.0`, `equity_curve` is empty (will fail on unfixed code — confirms bug)
2. **Strategy Attribution Empty Test**: Call `get_strategy_attribution` → assert returns empty list (will fail on unfixed code)
3. **Trade Analytics Zero Test**: Call `get_trade_analytics` → assert `total_trades == 0`, `win_rate == 0.0` (will fail on unfixed code)
4. **Correlation Matrix Empty Returns Test**: Call `get_correlation_matrix` → assert all strategy return arrays are empty (will fail on unfixed code)
5. **Order filled_price Null Test**: Query all FILLED orders → assert all have `filled_price IS NULL` (confirms root cause)

**Expected Counterexamples**:
- All analytics endpoints return zero/empty metrics despite 30 FILLED orders existing
- Root cause confirmed: `filled_price` is `None` for every FILLED order, causing the `if order.filled_price and order.filled_quantity` guard to skip all orders

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedAnalyticsEndpoint(input)
  ASSERT result.metrics ARE NOT all zeros
  ASSERT result.data_points > 0
  ASSERT result.values derived from PositionORM data
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain
- It catches edge cases that manual unit tests might miss
- It provides strong guarantees that behavior is unchanged for all non-buggy inputs

**Test Plan**: Observe behavior on UNFIXED code first for Alpha Edge endpoints, Regime Analysis, and Trade Journal operations, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Alpha Edge Endpoints Preservation**: Verify `fundamental-stats`, `ml-stats`, `conviction-distribution`, `template-performance` return identical results before and after fix
2. **Regime Analysis Preservation**: Verify regime analysis endpoint returns identical results before and after fix
3. **Trade Journal Export Preservation**: Verify CSV export produces identical output before and after fix
4. **Correlation Matrix Empty State Preservation**: Verify that with <2 strategies, the endpoint still returns empty matrix with 0.0 avg correlation and 1.0 diversification score
5. **Order Monitor Dedup Preservation**: Verify that `check_submitted_orders` still performs symbol normalization, dedup, and strategy_id assignment correctly

### Unit Tests

- Test that `get_performance_analytics` returns non-zero metrics when positions exist with P&L data
- Test that `get_strategy_attribution` groups positions by strategy and calculates correct contribution percentages
- Test that `get_trade_analytics` uses closed positions for win/loss and calculates correct holding times
- Test that `get_correlation_matrix` computes return series from position P&L data
- Test that `check_submitted_orders` sets `filled_price` from `etoro_pos.entry_price`
- Test that `run_signal_generation_sync` sets `filled_price` on immediate fill
- Test edge cases: no positions, all open positions (no closed), single strategy, zero P&L positions

### Property-Based Tests

- Generate random sets of `PositionORM` records with varying `entry_price`, `current_price`, `realized_pnl`, `unrealized_pnl`, `closed_at` values and verify analytics endpoints produce consistent, non-zero metrics
- Generate random order fill scenarios with eToro position data and verify `filled_price` is always set to `entry_price`
- Generate random mixes of open/closed positions and verify equity curve is monotonically timestamped and drawdown is non-negative

### Integration Tests

- Test full flow: create positions with P&L data → call all 4 analytics endpoints → verify populated responses
- Test that Trade Journal tab and Performance tab show consistent data after fix
- Test that fixing `filled_price` in order fill paths doesn't break position creation or dedup logic
