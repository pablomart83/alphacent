# System Readiness Improvements - Requirements

## Overview
Implement critical improvements identified in the system readiness audit to ensure profitable trading.

## User Stories

### 1. Transaction Costs in Backtesting
**As a** trader  
**I want** backtests to include realistic transaction costs  
**So that** I can accurately evaluate strategy profitability

**Acceptance Criteria**:
- Backtest includes eToro spread costs (0.15-0.25% per trade)
- Backtest includes estimated slippage (0.05-0.15% per trade)
- Total transaction cost per round trip: ~0.4-0.8%
- Backtest results show gross profit, transaction costs, and net profit separately
- Strategies with negative net profit after costs are flagged
- Configuration allows adjusting spread and slippage assumptions

### 2. Improved Strategy Retirement Logic
**As a** trader  
**I want** strategies to be evaluated fairly before retirement  
**So that** good strategies aren't retired during normal drawdown periods

**Acceptance Criteria**:
- Strategies require minimum 20 live trades before retirement evaluation
- Retirement uses rolling 60-day metrics, not point-in-time
- Retirement requires 3 consecutive evaluation failures
- Configuration includes probation period for new strategies
- Retirement reasons are logged with detailed metrics

### 3. Data Quality Validation
**As a** trader  
**I want** market data to be validated for quality  
**So that** I don't get false signals from bad data

**Acceptance Criteria**:
- Detect missing data gaps (> 1 day)
- Detect price jumps > 20% (potential splits)
- Detect zero volume days
- Detect stale data (> 24 hours old for daily data)
- Alert on data quality issues
- Log data quality metrics per symbol

### 4. Comprehensive System Readiness Test
**As a** developer  
**I want** an automated test that validates all critical system components  
**So that** I can verify system readiness before live trading

**Acceptance Criteria**:
- Test verifies transaction cost implementation
- Test verifies walk-forward analysis
- Test verifies market regime detection
- Test verifies dynamic position sizing
- Test verifies correlation management
- Test verifies execution quality monitoring
- Test verifies data quality checks
- Test verifies strategy retirement logic
- Test produces detailed readiness report
- Test fails if any critical component is missing

## Technical Requirements

### Transaction Costs
- Add `transaction_cost_pct` parameter to backtest configuration
- Default: 0.006 (0.6% round trip = 0.3% entry + 0.3% exit)
- Apply costs to each trade in backtest
- Store gross_profit and net_profit separately in BacktestResults

### Strategy Retirement
- Add `min_live_trades_before_retirement` to config (default: 20)
- Add `retirement_rolling_window_days` to config (default: 60)
- Add `retirement_consecutive_failures` to config (default: 3)
- Track retirement evaluation history per strategy

### Data Quality
- Create `DataQualityValidator` class
- Implement validation methods for each quality check
- Add data quality metrics to market data cache
- Create alerts for quality issues

### System Readiness Test
- Create `scripts/test_system_readiness.py`
- Implement feature detection (not assumptions)
- Generate markdown report with pass/fail for each component
- Include recommendations for failed components

## Non-Functional Requirements

- Performance: Transaction cost calculation should add < 5% to backtest time
- Reliability: Data quality checks should not block trading if validation fails
- Maintainability: All thresholds should be configurable
- Testability: Each component should have unit tests

## Out of Scope

- Parameter stability testing (nice to have, not critical)
- Monte Carlo simulation (nice to have, not critical)
- Advanced data cleaning (just detection, not correction)
