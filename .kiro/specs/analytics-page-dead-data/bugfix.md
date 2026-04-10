# Bugfix Requirements Document

## Introduction

The Analytics page is completely non-functional — all 6 tabs (Performance, Strategy Attribution, Trade Analytics, Regime Analysis, Alpha Edge, Trade Journal) display empty/zero data despite 30 FILLED orders and 95 positions existing in the database. This is caused by two interrelated defects:

1. All analytics endpoints in `src/api/routers/analytics.py` calculate P&L exclusively from `OrderORM.filled_price`, which is `None` for every order in the database, causing all orders to be skipped in every computation.
2. The order fill flow in `src/core/order_monitor.py` (`check_submitted_orders`) and `src/core/trading_scheduler.py` (immediate position creation) never sets `filled_price` on orders when they transition to FILLED status, even though eToro position data with `entry_price` is available at that point.

Meanwhile, `PositionORM` has rich P&L data (`entry_price`, `current_price`, `unrealized_pnl`, `realized_pnl`, `closed_at`) from eToro sync that the analytics endpoints completely ignore.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN any analytics endpoint (performance, strategy-attribution, trade-analytics, performance-stats) processes FILLED orders THEN the system skips all orders because the `if order.filled_price and order.filled_quantity` guard evaluates to False for every order (all 30 FILLED orders have `filled_price = None`)

1.2 WHEN the Performance tab is loaded THEN the system returns 0 equity curve points, 0.0% total return, 0.0 Sharpe ratio, 0.0 Sortino ratio, 0.0% max drawdown, 0.0% win rate, 0.0 profit factor, empty monthly returns, and empty returns distribution

1.3 WHEN the Strategy Attribution tab is loaded THEN the system returns an empty list of strategy attributions because no strategy accumulates any P&L (all orders skipped)

1.4 WHEN the Trade Analytics tab is loaded THEN the system returns 0 total trades, 0 wins, 0 losses, 0.0% win rate, 0.0 avg win/loss, 0.0 profit factor, and empty win/loss distribution

1.5 WHEN the correlation matrix endpoint processes strategy returns THEN the system computes empty return arrays for all strategies because no orders pass the `filled_price` check, resulting in 0.0 correlations and a meaningless diversification score

1.6 WHEN an order is filled via `check_submitted_orders` in `order_monitor.py` THEN the system sets `order.filled_at` and `order.filled_quantity` but never sets `order.filled_price`, leaving it as None

1.7 WHEN an order is filled via the immediate position creation path in `trading_scheduler.py` THEN the system sets `order_orm.filled_at` and `order_orm.filled_quantity` but sets `entry_price` to `order.filled_price or order.expected_price or 0` — since `filled_price` is always None, positions get `expected_price` or 0 as entry price, and the order itself remains with `filled_price = None`

1.8 WHEN the Trade Journal tab is loaded THEN the system returns trade data from `TradeJournal` which may have its own P&L calculations, but the analytics endpoints for performance-stats that feed the Performance tab still show zeros because they depend on the order-based P&L path

### Expected Behavior (Correct)

2.1 WHEN any analytics endpoint processes trading data THEN the system SHALL use `PositionORM` data (which has `entry_price`, `current_price`, `unrealized_pnl`, `realized_pnl` from eToro sync) as the primary data source for P&L calculations, using closed positions (`closed_at IS NOT NULL`) for realized metrics and open positions for unrealized metrics

2.2 WHEN the Performance tab is loaded THEN the system SHALL return a populated equity curve derived from position P&L data, with accurate total return, Sharpe ratio, Sortino ratio, max drawdown, win rate, profit factor, monthly returns, and returns distribution

2.3 WHEN the Strategy Attribution tab is loaded THEN the system SHALL return attribution data for each strategy based on the `realized_pnl` and `unrealized_pnl` of positions linked to that strategy via `strategy_id`

2.4 WHEN the Trade Analytics tab is loaded THEN the system SHALL return accurate trade counts, win/loss counts, win rate, average win/loss amounts, profit factor, and win/loss distribution derived from position-level P&L data

2.5 WHEN the correlation matrix endpoint processes strategy returns THEN the system SHALL compute meaningful return series from position P&L data grouped by strategy, producing accurate correlation values and diversification scores

2.6 WHEN an order is filled via `check_submitted_orders` THEN the system SHALL set `order.filled_price` to the `entry_price` from the matched eToro position (available via `etoro_pos.entry_price`) at the same time it sets `filled_at` and `filled_quantity`

2.7 WHEN an order is filled via the immediate position creation path in `trading_scheduler.py` THEN the system SHALL set `order_orm.filled_price` by querying the eToro position's entry price from the status response or matched position data, before committing the order to the database

2.8 WHEN the Trade Journal tab is loaded THEN the system SHALL display trade entries with accurate P&L data, and the performance-stats endpoint SHALL also reflect accurate metrics consistent with position-level data

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the Alpha Edge tab endpoints (fundamental-stats, ml-stats, conviction-distribution, template-performance) are loaded THEN the system SHALL CONTINUE TO query their respective log tables (`FundamentalFilterLogORM`, `MLFilterLogORM`, `ConvictionScoreLogORM`) and return data independently of order/position P&L calculations

3.2 WHEN the Regime Analysis endpoint processes strategy performance THEN the system SHALL CONTINUE TO derive regime data from `StrategyORM.rules` and `StrategyORM.performance` metadata fields

3.3 WHEN orders that already have a valid `filled_price` (future orders after the fix) are processed by analytics endpoints THEN the system SHALL CONTINUE TO include them in calculations without double-counting against position data

3.4 WHEN the trade journal export endpoint is called THEN the system SHALL CONTINUE TO export trade data to CSV format using the `TradeJournal` class

3.5 WHEN the correlation matrix endpoint finds fewer than 2 strategies with positions THEN the system SHALL CONTINUE TO return an empty matrix with 0.0 average correlation and 1.0 diversification score

3.6 WHEN `check_submitted_orders` creates or updates positions in the database THEN the system SHALL CONTINUE TO perform symbol normalization, deduplication checks, and strategy_id assignment as currently implemented

3.7 WHEN the startup reconciliation (`reconcile_on_startup`) syncs positions from eToro THEN the system SHALL CONTINUE TO create/close/update positions based on eToro state without being affected by the analytics data source changes
