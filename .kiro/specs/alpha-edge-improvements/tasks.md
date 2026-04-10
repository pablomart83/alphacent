# Implementation Tasks

## Task 1: Real Earnings Surprise Data (Requirement 1)

- [x] 1.1 Add `/analyst-estimates` FMP call in `get_historical_fundamentals()` in `src/data/fundamental_data_provider.py`
  - [x] 1.1.1 Add `_fmp_request("/analyst-estimates", symbol=symbol, limit=quarters)` call after income statement fetch
  - [x] 1.1.2 Build `estimates_by_date` lookup mapping fiscal date to `estimatedEpsAvg`
  - [x] 1.1.3 Record the API call with `self.fmp_rate_limiter.record_call()`
- [x] 1.2 Replace earnings surprise computation in the quarterly loop of `get_historical_fundamentals()`
  - [x] 1.2.1 Look up `estimated_eps` from `estimates_by_date` using the quarter date
  - [x] 1.2.2 Compute `surprise = (eps - estimated_eps) / abs(estimated_eps)` when both values available
  - [x] 1.2.3 Fall back to sequential EPS change when estimated_eps unavailable
  - [x] 1.2.4 Add `earnings_surprise_source` field ("analyst_estimate" or "sequential_fallback") to each quarter dict
  - [x] 1.2.5 Store true `actual_eps` and `estimated_eps` values (not previous quarter's EPS as estimated)
- [ ] 1.3 Write tests for earnings surprise computation
  - [ ] 1.3.1 Test that analyst estimate data is fetched and used when available
  - [ ] 1.3.2 Test fallback to sequential EPS change when analyst estimates unavailable
  - [ ] 1.3.3 Test that earnings_surprise_source tag is set correctly
  - [ ] 1.3.4 [PBT] Property test: for random (actual_eps, estimated_eps) pairs, `earnings_surprise == (actual - estimated) / abs(estimated)`

## Task 2: Insider Trading Data Integration (Requirement 2)

- [x] 2.1 Add `get_insider_trading()` method to `FundamentalDataProvider` in `src/data/fundamental_data_provider.py`
  - [x] 2.1.1 Implement FMP `/insider-trading` endpoint call with symbol and limit parameters
  - [x] 2.1.2 Parse response into list of `{date, transaction_type, shares, price, name, title}` dicts
  - [x] 2.1.3 Add cache with 24h TTL using `FundamentalDataCache`
- [x] 2.2 Add `get_insider_net_purchases()` method to `FundamentalDataProvider`
  - [x] 2.2.1 Call `get_insider_trading()` and filter by lookback_days (default 90)
  - [x] 2.2.2 Aggregate: `net_shares = sum(buy_shares) - sum(sell_shares)`, `net_value`, `buy_count`, `sell_count`, `last_buy_date`
  - [x] 2.2.3 Return dict with aggregated values
- [x] 2.3 Update Insider Buying backtest simulation in `strategy_engine.py`
  - [x] 2.3.1 In `_simulate_alpha_edge_with_fundamentals()`, replace the `insider_buying` branch to call `get_insider_trading()` and enter on net purchases > threshold
  - [x] 2.3.2 Keep volume confirmation from existing `_simulate_insider_buying_trades()` as secondary filter
  - [x] 2.3.3 Handle empty insider data by returning empty trades list
- [x] 2.4 Update Insider Buying live signal in `_handle_insider_buying()` in `strategy_engine.py`
  - [x] 2.4.1 Replace earnings surprise proxy check with `get_insider_net_purchases()` call
  - [x] 2.4.2 Enter signal when `net_purchases >= min_net_purchases` (configurable, default 3)
- [ ] 2.5 Write tests for insider trading integration
  - [ ] 2.5.1 Test `get_insider_trading()` with mocked FMP response
  - [ ] 2.5.2 Test `get_insider_net_purchases()` aggregation logic
  - [ ] 2.5.3 Test empty data handling (no insider data → no signal)
  - [ ] 2.5.4 [PBT] Property test: for random buy/sell transaction lists, `net_shares == sum(buys) - sum(sells)`

## Task 3: Fix Quality Mean Reversion Backtest (Requirement 3)

- [x] 3.1 Add quarterly key-metrics fetch in `get_historical_fundamentals()` in `src/data/fundamental_data_provider.py`
  - [x] 3.1.1 Add `_fmp_request("/key-metrics", symbol=symbol, period="quarter", limit=quarters)` call
  - [x] 3.1.2 Build `quarterly_metrics_by_date` lookup
  - [x] 3.1.3 In quarterly loop, prefer quarterly ROE/D/E over annual values
  - [x] 3.1.4 Add `quality_data_source` field ("quarterly" or "annual_interpolated") to each quarter dict
- [x] 3.2 Fix Quality Mean Reversion simulation in `_simulate_alpha_edge_with_fundamentals()` in `strategy_engine.py`
  - [x] 3.2.1 Read RSI threshold from `params.get('rsi_threshold', 45)` instead of hardcoded 50
  - [x] 3.2.2 Add per-quarter dedup: track last entry quarter and skip if same quarter
  - [x] 3.2.3 Use quarterly ROE/D/E values from the new `quality_data_source` field
- [ ] 3.3 Write tests for Quality Mean Reversion fix
  - [ ] 3.3.1 Test that quarterly ROE/D/E is used when available
  - [ ] 3.3.2 Test fallback to annual data with interpolation tag
  - [ ] 3.3.3 Test configurable RSI threshold
  - [ ] 3.3.4 [PBT] Property test: for any QMR backtest, `len(trades) <= len(unique_quarters)`

## Task 4: Fix Sector Rotation (Requirement 4)

- [x] 4.1 Add `get_sector_performance()` method to `FundamentalDataProvider` in `src/data/fundamental_data_provider.py`
  - [x] 4.1.1 Implement FMP `/stock-price-change` or `/sector-performance` endpoint call
  - [x] 4.1.2 Parse response into `{sector_name: {1m, 3m, 6m, 1y}}` dict
  - [x] 4.1.3 Add cache with 24h TTL
  - [x] 4.1.4 Implement fallback: compute sector returns from sector ETF prices (XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLRE, XLC, XLB)
- [x] 4.2 Add `_simulate_sector_rotation_with_fundamentals()` method to `StrategyEngine` in `strategy_engine.py`
  - [x] 4.2.1 Fetch sector performance data from `get_sector_performance()`
  - [x] 4.2.2 Rank sectors by configurable trailing period (default 3 months)
  - [x] 4.2.3 Enter long on top N sectors (default 3), rebalance at configurable interval (default monthly)
  - [x] 4.2.4 Fall back to price proxy if no sector data available
- [x] 4.3 Wire sector rotation in `_simulate_alpha_edge_with_fundamentals()`
  - [x] 4.3.1 Replace the `sector_rotation` pass-through with call to `_simulate_sector_rotation_with_fundamentals()`
  - [x] 4.3.2 Update `_check_sector_rotation_signal()` to use real sector data for live signals
- [x] 4.4 Write tests for sector rotation fix
  - [x] 4.4.1 Test `get_sector_performance()` with mocked FMP response
  - [x] 4.4.2 Test sector ranking logic
  - [x] 4.4.3 Test fallback to ETF price data
  - [x] 4.4.4 [PBT] Property test: for any set of sector returns, ranking produces sorted order

## Task 5: Fix Dividend Aristocrat Overtrading (Requirement 5)

- [x] 5.1 Add entry spacing and technical confirmation to Dividend Aristocrat simulation in `strategy_engine.py`
  - [x] 5.1.1 In `_simulate_alpha_edge_with_fundamentals()` dividend_aristocrat branch, track `last_div_entry_date` and enforce 180-day minimum gap
  - [x] 5.1.2 Add technical confirmation: require pullback >= 5% from 252-day high OR RSI < 40 at entry point
  - [x] 5.1.3 Skip new entries while an existing trade is open for the same symbol
  - [x] 5.1.4 Read `min_entry_gap_days`, `pullback_confirmation_pct`, `rsi_confirmation_threshold` from params/config
- [x] 5.2 Update `_simulate_dividend_aristocrat_trades()` price-proxy simulation with same constraints
  - [x] 5.2.1 Add 180-day entry gap enforcement
  - [x] 5.2.2 Ensure no overlapping trades
- [x] 5.3 Use quarterly dividend yield when available
  - [x] 5.3.1 In the dividend_aristocrat branch, prefer quarterly `dividend_yield` from `quarterly_metrics_by_date` over annual value
- [x] 5.4 Write tests for Dividend Aristocrat fix
  - [x] 5.4.1 Test 6-month entry spacing enforcement
  - [x] 5.4.2 Test technical confirmation requirement
  - [x] 5.4.3 Test no overlapping trades
  - [x] 5.4.4 [PBT] Property test: for any DA backtest, all consecutive trade pairs have `entry_gap >= 180 days`
  - [x] 5.4.5 [PBT] Property test: for any DA backtest, no two trades overlap (t1.exit_date <= t2.entry_date)

## Task 6: Rejection Blacklist (Requirement 6)

- [x] 6.1 Add rejection blacklist data structures to `StrategyProposer.__init__()` in `strategy_proposer.py`
  - [x] 6.1.1 Add `_rejection_blacklist`, `_rejection_blacklist_timestamps`, threshold, cooldown_days, file path
  - [x] 6.1.2 Add `_load_rejection_blacklist_from_disk()` method (same format as zero-trade blacklist)
  - [x] 6.1.3 Add `_save_rejection_blacklist_to_disk()` method
  - [x] 6.1.4 Call `_load_rejection_blacklist_from_disk()` in `__init__`
- [x] 6.2 Add rejection tracking methods to `StrategyProposer`
  - [x] 6.2.1 Add `record_rejection(template_name, symbol)` — increment counter, update timestamp, save to disk
  - [x] 6.2.2 Add `reset_rejection(template_name, symbol)` — remove entry, save to disk
  - [x] 6.2.3 Add `is_rejection_blacklisted(template_name, symbol)` — check threshold and cooldown
- [x] 6.3 Integrate rejection blacklist into scoring and proposal
  - [x] 6.3.1 In `_score_symbol_for_template()`, add `is_rejection_blacklisted()` check after zero-trade blacklist check, return 0.0 if blacklisted
  - [x] 6.3.2 In `_evaluate_and_activate()` in `autonomous_strategy_manager.py`, call `record_rejection()` on rejection
  - [x] 6.3.3 In `_evaluate_and_activate()`, call `reset_rejection()` on successful activation
- [x] 6.4 Write tests for rejection blacklist
  - [x] 6.4.1 Test rejection counter increment
  - [x] 6.4.2 Test blacklist threshold enforcement (3 rejections → blacklisted)
  - [x] 6.4.3 Test cooldown expiry allows re-proposal
  - [x] 6.4.4 Test reset on successful activation
  - [x] 6.4.5 Test score returns 0.0 for blacklisted combinations
  - [x] 6.4.6 [PBT] Property test: save then load rejection blacklist produces same state (round-trip)

## Task 7: Improved AE Symbol Scoring (Requirement 7)

- [x] 7.1 Add fundamental scoring cache to `StrategyProposer` in `strategy_proposer.py`
  - [x] 7.1.1 Add `_fundamental_scoring_cache` dict with 24h TTL
  - [x] 7.1.2 Add `_get_cached_quarterly_data(symbol)` helper that fetches from cache or `get_historical_fundamentals()`
  - [x] 7.1.3 Add `_get_cached_insider_net(symbol)` helper that fetches from cache or `get_insider_net_purchases()`
- [x] 7.2 Improve Revenue Acceleration scoring in `_score_symbol_for_template()`
  - [x] 7.2.1 Fetch quarterly revenue data, compute coefficient of variation
  - [x] 7.2.2 Penalize symbols with CV > 0.5 (inconsistent revenue)
  - [x] 7.2.3 Boost symbols with 3+ consecutive quarters of positive revenue growth
- [x] 7.3 Improve Dividend Aristocrat scoring
  - [x] 7.3.1 Verify dividend yield > 1.5% from fundamental data
  - [x] 7.3.2 Check dividend stability over last 4 periods
  - [x] 7.3.3 Penalize symbols with no dividend data
- [x] 7.4 Improve Earnings Momentum scoring
  - [x] 7.4.1 Boost symbols with earnings reported within last 45 days
  - [x] 7.4.2 Penalize symbols with no earnings data from FMP
- [x] 7.5 Improve Insider Buying scoring
  - [x] 7.5.1 Boost symbols with recent insider purchases (last 90 days)
  - [x] 7.5.2 Penalize symbols with no insider activity data
- [x] 7.6 Improve Quality Mean Reversion scoring
  - [x] 7.6.1 Verify ROE data availability from FMP
  - [x] 7.6.2 Penalize symbols with no quality metrics
- [x] 7.7 Write tests for improved scoring
  - [x] 7.7.1 Test Revenue Acceleration scoring with consistent vs inconsistent revenue data
  - [x] 7.7.2 Test Dividend Aristocrat scoring with high vs low yield
  - [x] 7.7.3 Test Earnings Momentum scoring with recent vs stale earnings
  - [x] 7.7.4 Test Insider Buying scoring with and without insider activity
  - [x] 7.7.5 Test Quality Mean Reversion scoring with and without ROE data

## Task 8: End-of-Month Momentum Template Rework (Requirement 8)

- [x] 8.1 Add template disable mechanism to `StrategyProposer` in `strategy_proposer.py`
  - [x] 8.1.1 Add `_is_template_disabled(template)` method checking `template.metadata.get('disabled')`
  - [x] 8.1.2 Integrate disable check in `generate_strategies_from_templates()` — skip disabled templates
  - [x] 8.1.3 Integrate disable check in `_match_templates_to_symbols()` — skip disabled templates
- [x] 8.2 Update End-of-Month Momentum template handling
  - [x] 8.2.1 Check if FMP provides institutional ownership data for the template's target symbols
  - [x] 8.2.2 If insufficient data, mark template as disabled with `disable_reason: "insufficient_fundamental_data"`
  - [x] 8.2.3 If data available, update `_simulate_end_of_month_momentum_trades()` to use institutional flow data
- [x] 8.3 Add disabled template logging in `autonomous_strategy_manager.py`
  - [x] 8.3.1 In `_propose_strategies()` or cycle start, iterate templates and log warning for disabled ones
  - [x] 8.3.2 Include disable reason in log message
- [x] 8.4 Add configuration for End-of-Month Momentum enable/disable
  - [x] 8.4.1 Add `end_of_month_momentum.enabled` to `config/autonomous_trading.yaml`
  - [x] 8.4.2 Read config in template initialization or proposal phase
- [x] 8.5 Write tests for template disable mechanism
  - [x] 8.5.1 Test `_is_template_disabled()` returns True for disabled templates
  - [x] 8.5.2 Test disabled templates are excluded from proposals
  - [x] 8.5.3 Test warning is logged for disabled templates

## Task 9: Configuration Updates

- [x] 9.1 Update `config/autonomous_trading.yaml` with new settings
  - [x] 9.1.1 Add `alpha_edge.rejection_blacklist.threshold: 3` and `cooldown_days: 30`
  - [x] 9.1.2 Add `alpha_edge.quality_mean_reversion.rsi_threshold: 45`
  - [x] 9.1.3 Add `alpha_edge.dividend_aristocrat.min_entry_gap_days: 180`, `pullback_confirmation_pct: 0.05`, `rsi_confirmation_threshold: 40`
  - [x] 9.1.4 Add `alpha_edge.insider_buying.min_net_purchases: 3`, `lookback_days: 90`
  - [x] 9.1.5 Add `alpha_edge.sector_rotation.top_sectors: 3`
  - [x] 9.1.6 Add `alpha_edge.end_of_month_momentum.enabled: true`
