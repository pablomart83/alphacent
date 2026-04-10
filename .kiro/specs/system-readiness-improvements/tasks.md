# System Readiness Improvements - Tasks

## Task 1: Add Transaction Costs to Backtesting

### 1.1 Add transaction cost configuration
- [x] Add `transaction_costs` section to `config/autonomous_trading.yaml`
  - `spread_pct`: 0.003 (0.3% per trade)
  - `slippage_pct`: 0.001 (0.1% per trade)
  - `enabled`: true

### 1.2 Update BacktestResults dataclass
- [x] Add `gross_profit` field to BacktestResults
- [x] Add `transaction_costs` field to BacktestResults
- [x] Add `net_profit` field to BacktestResults (gross_profit - transaction_costs)
- [x] Update `total_return` calculation to use net_profit

### 1.3 Implement transaction cost calculation in backtester
- [x] Locate backtest execution in `src/strategy/strategy_engine.py`
- [x] Calculate entry cost: `entry_price * (spread_pct + slippage_pct)`
- [x] Calculate exit cost: `exit_price * (spread_pct + slippage_pct)`
- [x] Sum total transaction costs for all trades
- [x] Calculate net profit: `gross_profit - transaction_costs`
- [x] Update BacktestResults with all three values

### 1.4 Update strategy evaluation to use net profit
- [x] Update activation criteria to check `net_profit` instead of `total_return`
- [x] Update Sharpe ratio calculation to use net returns
- [x] Flag strategies with negative net profit

### 1.5 Update API responses
- [x] Update backtest API response to include gross_profit, transaction_costs, net_profit
- [x] Update strategy details API to show transaction cost impact

### 1.6 Add tests
- [x] Test transaction cost calculation with known trades
- [x] Test that strategies with negative net profit are rejected
- [x] Test configuration loading

## Task 2: Improve Strategy Retirement Logic

### 2.1 Add retirement configuration
- [x] Add `retirement_logic` section to `config/autonomous_trading.yaml`
  - `min_live_trades_before_evaluation`: 20
  - `rolling_window_days`: 60
  - `consecutive_failures_required`: 3
  - `probation_period_days`: 30

### 2.2 Add retirement tracking to database
- [x] Add `retirement_evaluation_history` JSON field to strategies table
- [x] Add `live_trade_count` field to strategies table
- [x] Add `last_retirement_evaluation` timestamp field

### 2.3 Update retirement evaluation logic
- [x] Check if strategy has minimum live trades before evaluation
- [x] Calculate rolling metrics over window period (not point-in-time)
- [x] Track consecutive evaluation failures
- [x] Only retire after consecutive failures threshold met
- [x] Log detailed retirement reason with metrics

### 2.4 Add probation period for new strategies
- [x] Check strategy age before retirement evaluation
- [x] Skip retirement for strategies in probation period
- [x] Log probation status

### 2.5 Update tests
- [x] Test minimum trade count requirement
- [x] Test rolling window calculation
- [x] Test consecutive failures logic
- [x] Test probation period

## Task 3: Add Data Quality Validation

### 3.1 Create DataQualityValidator class
- [x] Create `src/data/data_quality_validator.py`
- [x] Implement `validate_data_quality(data, symbol)` method
- [x] Return DataQualityReport with issues and metrics

### 3.2 Implement quality checks
- [x] Check for missing data gaps (> 1 day between records)
- [x] Check for price jumps > 20% (potential splits)
- [x] Check for zero volume days
- [x] Check for stale data (> 24 hours old)
- [x] Check for duplicate timestamps
- [x] Check for null/NaN values

### 3.3 Integrate with MarketDataManager
- [x] Add quality validation after fetching data
- [x] Store quality metrics in cache
- [x] Log quality issues as warnings
- [x] Continue trading even if validation fails (don't block)

### 3.4 Add quality metrics tracking
- [x] Track quality score per symbol (0-100)
- [x] Track last validation timestamp
- [x] Track issue counts by type

### 3.5 Add API endpoint for data quality
- [x] Create `/api/data-quality` endpoint
- [x] Return quality metrics per symbol
- [x] Return recent quality issues

### 3.6 Add tests
- [x] Test each quality check with known bad data
- [x] Test quality score calculation
- [x] Test that trading continues despite quality issues

## Task 4: Create Comprehensive System Readiness Test

### 4.1 Create system readiness test script
- [x] Create `scripts/test_system_readiness.py`
- [x] Implement feature detection (not assumptions)
- [x] Generate detailed markdown report

### 4.2 Implement component checks
- [x] Check 1: Transaction costs in backtesting
  - Verify config exists
  - Verify BacktestResults has gross/net profit fields
  - Verify costs are applied in backtest
- [x] Check 2: Walk-forward analysis
  - Verify ParameterOptimizer exists
  - Verify out-of-sample validation
  - Verify 67/33 split
- [x] Check 3: Market regime detection
  - Verify MarketStatisticsAnalyzer exists
  - Verify FRED integration
  - Verify sub-regime detection
- [x] Check 4: Dynamic position sizing
  - Verify regime-based sizing
  - Verify correlation-based sizing
  - Verify volatility-based sizing
- [x] Check 5: Strategy correlation management
  - Verify correlation calculation
  - Verify position size adjustment
  - Verify correlation matrix API
- [x] Check 6: Execution quality monitoring
  - Verify ExecutionQualityTracker exists
  - Verify slippage tracking
  - Verify fill rate tracking
- [x] Check 7: Data quality validation
  - Verify DataQualityValidator exists
  - Verify quality checks implemented
- [x] Check 8: Strategy retirement logic
  - Verify minimum trade count check
  - Verify rolling window metrics
  - Verify consecutive failures logic

### 4.3 Generate readiness report
- [x] Create markdown report with pass/fail for each check
- [x] Include implementation details for passed checks
- [x] Include recommendations for failed checks
- [x] Calculate overall readiness score (0-100)
- [x] Provide go/no-go recommendation

### 4.4 Add to CI/CD
- [x] Add readiness test to test suite
- [x] Fail build if critical components missing
- [x] Generate report artifact

## Task 5: Update Task 6.6 E2E Test

### 5.1 Update E2E test to use readiness checks
- [ ] Import system readiness checks
- [ ] Run readiness validation before E2E test
- [ ] Report readiness status in E2E output
- [ ] Skip E2E test if critical components missing

### 5.2 Add transaction cost verification
- [ ] Verify backtest results include transaction costs
- [ ] Verify net profit is calculated correctly
- [ ] Verify strategies are evaluated on net profit

### 5.3 Add data quality verification
- [ ] Verify data quality checks run
- [ ] Verify quality metrics are tracked
- [ ] Verify quality issues are logged

### 5.4 Update E2E test documentation
- [ ] Document readiness prerequisites
- [ ] Document expected readiness score
- [ ] Document how to interpret readiness report

## Task 6: Documentation and Configuration

### 6.1 Update configuration documentation
- [ ] Document transaction cost settings
- [ ] Document retirement logic settings
- [ ] Document data quality settings
- [ ] Provide recommended values

### 6.2 Create migration guide
- [ ] Document database schema changes
- [ ] Provide migration script for retirement tracking fields
- [ ] Document configuration changes

### 6.3 Update README
- [ ] Add system readiness test to README
- [ ] Document how to run readiness test
- [ ] Document readiness score interpretation
