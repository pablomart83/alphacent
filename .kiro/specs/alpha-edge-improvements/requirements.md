# Requirements Document

## Introduction

The AlphaCent autonomous trading system uses "Alpha Edge" (AE) strategies that leverage FMP fundamental data for trading signals. Of the 12 AE template types, several are broken (producing S=0.00, wr=0% in backtests), others misuse FMP data (fake earnings surprise, no real insider data), and the proposal cycle wastes slots re-proposing strategies that are always rejected. This feature fixes the broken backtests, integrates missing FMP endpoints, adds a rejection blacklist, and improves symbol scoring for AE templates.

## Glossary

- **Strategy_Engine**: The component in `strategy_engine.py` responsible for AE signal generation, validation, and backtesting.
- **Fundamental_Data_Provider**: The component in `fundamental_data_provider.py` responsible for fetching and caching FMP fundamental data.
- **Strategy_Proposer**: The component in `strategy_proposer.py` responsible for proposing strategies, scoring symbols, and managing blacklists.
- **Autonomous_Manager**: The component in `autonomous_strategy_manager.py` responsible for orchestrating strategy cycles (propose → backtest → evaluate → activate).
- **Earnings_Surprise**: The difference between actual reported EPS and the consensus analyst estimate, expressed as a percentage of the estimate.
- **Sequential_EPS_Change**: The current (broken) computation that compares EPS between consecutive quarters (Q1 vs Q2) instead of actual vs estimated.
- **Rejection_Blacklist**: A proposed mechanism to track template+symbol combinations that are repeatedly rejected at activation, preventing re-proposal.
- **Zero_Trade_Blacklist**: The existing mechanism that blocks template+symbol combinations producing zero trades in backtesting.
- **FMP**: Financial Modeling Prep, the fundamental data API provider (Starter plan, 300 calls/min).
- **AE_Template**: An Alpha Edge strategy template definition in `strategy_templates.py`.
- **Symbol_Scoring**: The process in `_score_symbol_for_template()` that rates how suitable a symbol is for a given AE template.

## Requirements

### Requirement 1: Real Earnings Surprise Data

**User Story:** As a trading system operator, I want the Fundamental_Data_Provider to compute earnings surprise from analyst estimates vs actual EPS, so that Earnings Momentum and Earnings Miss strategies use accurate fundamental signals.

#### Acceptance Criteria

1. WHEN fetching historical fundamentals for a symbol, THE Fundamental_Data_Provider SHALL call the FMP `/analyst-estimates` endpoint to retrieve consensus EPS estimates for each quarter.
2. WHEN both actual EPS and estimated EPS are available for a quarter, THE Fundamental_Data_Provider SHALL compute earnings_surprise as `(actual_eps - estimated_eps) / abs(estimated_eps)`.
3. IF the `/analyst-estimates` endpoint returns no data for a quarter, THEN THE Fundamental_Data_Provider SHALL fall back to the sequential EPS change computation and tag the quarter with `earnings_surprise_source: "sequential_fallback"`.
4. WHEN storing quarterly fundamental data, THE Fundamental_Data_Provider SHALL include both `actual_eps` and `estimated_eps` fields with their true values (not the previous quarter's EPS as estimated).
5. FOR ALL quarters where both actual and estimated EPS are available, fetching then computing then re-fetching SHALL produce the same earnings_surprise value (round-trip consistency).

### Requirement 2: Real Insider Trading Data Integration

**User Story:** As a trading system operator, I want the Fundamental_Data_Provider to fetch real insider trading data from FMP, so that the Insider Buying template uses actual insider purchase signals instead of earnings surprise as a proxy.

#### Acceptance Criteria

1. THE Fundamental_Data_Provider SHALL expose a `get_insider_trading(symbol, months=6)` method that calls the FMP `/insider-trading` endpoint.
2. WHEN insider trading data is retrieved, THE Fundamental_Data_Provider SHALL aggregate net insider purchases (buys minus sells) over a configurable lookback window (default: 90 days).
3. WHEN the Insider Buying backtest simulation runs, THE Strategy_Engine SHALL use real insider net purchase data instead of the current proxy (`earnings_surprise > 0.02 OR revenue_growth > 0.05`).
4. WHEN the Insider Buying live signal check runs, THE Strategy_Engine SHALL use real insider net purchase data to determine entry signals.
5. IF the `/insider-trading` endpoint returns no data for a symbol, THEN THE Fundamental_Data_Provider SHALL return an empty result and THE Strategy_Engine SHALL skip the Insider Buying signal for that symbol.
6. THE Fundamental_Data_Provider SHALL cache insider trading data with a TTL of 24 hours to minimize API calls.

### Requirement 3: Fix Quality Mean Reversion Backtest

**User Story:** As a trading system operator, I want the Quality Mean Reversion backtest to use quarterly-granularity ROE and debt-to-equity data, so that the template produces meaningful backtest results instead of S=0.00 wr=0%.

#### Acceptance Criteria

1. WHEN fetching historical fundamentals, THE Fundamental_Data_Provider SHALL request quarterly key-metrics from FMP (endpoint `/key-metrics` with `period=quarter`) in addition to annual data.
2. WHEN quarterly ROE and debt-to-equity are available, THE Strategy_Engine SHALL use the quarterly values for the Quality Mean Reversion backtest instead of applying annual values uniformly across all quarters.
3. IF quarterly key-metrics are unavailable for a specific quarter, THEN THE Strategy_Engine SHALL interpolate from the nearest available annual data and tag the quarter with `quality_data_source: "annual_interpolated"`.
4. WHEN simulating Quality Mean Reversion trades, THE Strategy_Engine SHALL use an RSI threshold of 45 (configurable) instead of the current effective threshold of 50 that combines with the strict ROE/D/E filter to produce zero entries.
5. WHEN Quality Mean Reversion conditions are met for a quarter, THE Strategy_Engine SHALL enter at most one trade per quarter to prevent overtrading from annual data matching every quarter.

### Requirement 4: Fix Sector Rotation to Use FMP Sector Data

**User Story:** As a trading system operator, I want the Sector Rotation template to use real FMP sector performance data, so that it rotates into outperforming sectors instead of falling back to a 60-day momentum price proxy.

#### Acceptance Criteria

1. THE Fundamental_Data_Provider SHALL expose a `get_sector_performance()` method that calls the FMP `/stock-price-change` or `/sector-performance` endpoint to retrieve sector-level returns.
2. WHEN simulating Sector Rotation trades, THE Strategy_Engine SHALL rank sectors by their trailing performance over a configurable period (default: 3 months) and select the top N sectors (default: 3).
3. WHEN generating live Sector Rotation signals, THE Strategy_Engine SHALL use real sector performance rankings instead of the current price-proxy fallback.
4. IF the FMP sector performance endpoint returns no data, THEN THE Strategy_Engine SHALL fall back to computing sector returns from individual sector ETF price data and log a warning.
5. THE Strategy_Engine SHALL re-evaluate sector rankings at a configurable interval (default: monthly) to avoid excessive rotation.

### Requirement 5: Fix Dividend Aristocrat Overtrading

**User Story:** As a trading system operator, I want the Dividend Aristocrat backtest to avoid entering every quarter when annual data meets criteria, so that the template does not produce S=-12.19 wr=0% from overtrading.

#### Acceptance Criteria

1. WHEN simulating Dividend Aristocrat trades, THE Strategy_Engine SHALL enter at most one trade per 6-month period for the same symbol to prevent overtrading from annual data matching every quarter.
2. WHEN evaluating Dividend Aristocrat entry conditions, THE Strategy_Engine SHALL require a technical confirmation signal (price pullback of at least 5% from 52-week high OR RSI below 40) in addition to the fundamental criteria (dividend_yield > 2%, ROE > 10%).
3. WHEN quarterly dividend yield data is available from FMP, THE Strategy_Engine SHALL use the quarterly value instead of the annual value applied uniformly.
4. IF a Dividend Aristocrat trade is already open for a symbol, THEN THE Strategy_Engine SHALL skip new entries for that symbol until the existing trade closes.

### Requirement 6: Rejection Blacklist

**User Story:** As a trading system operator, I want a rejection blacklist that prevents re-proposing template+symbol combinations rejected N consecutive times, so that the system stops wasting proposal slots on dead strategies.

#### Acceptance Criteria

1. WHEN a strategy is rejected at the activation stage, THE Autonomous_Manager SHALL increment a rejection counter for the (template_name, primary_symbol) combination.
2. WHEN a (template_name, primary_symbol) combination reaches a configurable rejection threshold (default: 3 consecutive rejections), THE Strategy_Proposer SHALL exclude that combination from future proposals.
3. WHEN a previously blacklisted combination is re-evaluated after a configurable cooldown period (default: 30 days), THE Strategy_Proposer SHALL allow one re-proposal attempt.
4. WHEN a previously blacklisted combination passes activation after cooldown, THE Strategy_Proposer SHALL reset the rejection counter to zero.
5. THE Strategy_Proposer SHALL persist the rejection blacklist to disk in the same format as the existing zero-trade blacklist.
6. WHILE the rejection blacklist is loaded, THE Strategy_Proposer SHALL return a score of 0.0 for blacklisted (template, symbol) combinations in `_score_symbol_for_template()`.

### Requirement 7: Improved Symbol Scoring for AE Templates

**User Story:** As a trading system operator, I want AE template symbol scoring to use fundamental fitness criteria, so that templates are matched to symbols where they are most likely to succeed.

#### Acceptance Criteria

1. WHEN scoring a symbol for the Revenue Acceleration template, THE Strategy_Proposer SHALL penalize symbols with inconsistent quarterly revenue (coefficient of variation > 0.5 over the last 8 quarters) and boost symbols with 3+ consecutive quarters of positive revenue growth.
2. WHEN scoring a symbol for the Dividend Aristocrat template, THE Strategy_Proposer SHALL verify the symbol has a dividend yield above 1.5% and a history of stable or growing dividends over the last 4 available periods.
3. WHEN scoring a symbol for the Earnings Momentum template, THE Strategy_Proposer SHALL boost symbols that have reported earnings within the last 45 days and penalize symbols with no earnings data available from FMP.
4. WHEN scoring a symbol for the Insider Buying template, THE Strategy_Proposer SHALL boost symbols with recent insider purchase activity (last 90 days) from the FMP insider trading endpoint.
5. WHEN scoring a symbol for the Quality Mean Reversion template, THE Strategy_Proposer SHALL verify the symbol has ROE data available from FMP and penalize symbols with no quality metrics.
6. THE Strategy_Proposer SHALL cache fundamental scoring data with a TTL of 24 hours to avoid excessive FMP API calls during symbol scoring.

### Requirement 8: Rework End-of-Month Momentum Template

**User Story:** As a trading system operator, I want the End-of-Month Momentum template to either use FMP data for institutional flow detection or be disabled, so that it does not consume proposal slots without adding fundamental value.

#### Acceptance Criteria

1. WHEN the End-of-Month Momentum template is enabled, THE Strategy_Engine SHALL use FMP institutional ownership data or ETF flow data to confirm month-end rebalancing signals instead of relying solely on price momentum.
2. IF FMP does not provide sufficient institutional flow data for the End-of-Month Momentum template, THEN THE Strategy_Proposer SHALL mark the template as disabled with reason `"insufficient_fundamental_data"`.
3. WHEN a template is marked as disabled, THE Strategy_Proposer SHALL exclude the template from all proposal cycles until it is manually re-enabled in configuration.
4. THE Autonomous_Manager SHALL log a warning once per cycle when a disabled template is skipped, including the disable reason.
