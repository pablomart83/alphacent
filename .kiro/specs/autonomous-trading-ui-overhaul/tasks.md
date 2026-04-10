# Implementation Tasks: Autonomous Trading UI Overhaul

## Overview

This implementation transforms the AlphaCent frontend from a generic trading dashboard into a specialized autonomous trading monitoring and control interface. We remove all LLM/Vibe Coding features and create a focused, professional trading interface.

**Timeline**: 4 weeks
**Approach**: Phased migration with minimal disruption to existing functionality

## Phase 1: Remove Legacy Components (Week 1)

- [x] 1.1 Remove VibeCoding Component and LLM References
- Remove `frontend/src/components/VibeCoding.tsx`
- Remove VibeCoding from Dashboard.tsx
- Remove LLM service files from `frontend/src/services/`
- Remove LLM-related utilities
- Update imports across affected files
- Remove unused dependencies from package.json
- _Requirements: 1.1, 1.2_
- **Estimated time: 2-3 hours**

- [x] 1.2 Remove Unused Social and Portfolio Components
- Remove `frontend/src/components/SocialInsightsComponent.tsx`
- Remove `frontend/src/components/SmartPortfoliosComponent.tsx`
- Remove from Dashboard.tsx
- Clean up related types and interfaces
- _Requirements: 1.1, 1.2_
- **Estimated time: 1 hour**

- [x] 1.3 Update Navigation and Routes
- Remove routes for removed features
- Update navigation menu items
- Add placeholder for new Autonomous Trading route
- Update App.tsx routing configuration
- _Requirements: 1.3_
- **Estimated time: 1 hour**

- [x] 1.4 Clean Up Dependencies
- Run `npm prune` to remove unused packages
- Update package.json
- Verify build still works
- Run existing tests to ensure nothing broke
- _Requirements: 1.1_
- **Estimated time: 30 minutes**

## Phase 2: Backend API Implementation (Week 1-2)

- [x] 2.1 Implement Autonomous Status Endpoint
- Create `GET /api/strategies/autonomous/status` endpoint
- Return system status, market regime, cycle stats, portfolio health
- Integrate with existing AutonomousStrategyManager
- Add error handling and validation
- Test with existing backend data
- _Requirements: 2.1, 2.2, 2.3_
- **Estimated time: 2-3 hours**

- [x] 2.2 Implement Autonomous Control Endpoints
- Create `POST /api/strategies/autonomous/trigger` endpoint
- Create `GET /api/strategies/autonomous/config` endpoint
- Create `PUT /api/strategies/autonomous/config` endpoint
- Integrate with autonomous_trading.yaml configuration
- Add validation for configuration updates
- Test manual trigger functionality
- _Requirements: 2.4, 2.5, 3.1, 3.2_
- **Estimated time: 3-4 hours**

- [x] 2.3 Implement Strategy Management Endpoints
- Create `GET /api/strategies/proposals` endpoint
- Create `GET /api/strategies/retirements` endpoint
- Create `GET /api/strategies/templates` endpoint
- Query strategy_proposals and strategy_retirements tables
- Add pagination and filtering
- Return template metadata and statistics
- _Requirements: 2.6, 2.7, 4.1, 4.2_
- **Estimated time: 3-4 hours**

- [x] 2.4 Implement Performance & Analytics Endpoints
- Create `GET /api/performance/metrics` endpoint
- Create `GET /api/performance/portfolio` endpoint
- Create `GET /api/performance/history` endpoint
- Calculate portfolio-level metrics
- Generate correlation matrix
- Return historical events timeline
- _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2_
- **Estimated time: 4-5 hours**

- [x] 2.5 Add WebSocket Event Handlers
- Add `autonomous:status` channel
- Add `autonomous:cycle` channel
- Add `autonomous:strategies` channel
- Add `autonomous:notifications` channel
- Broadcast events during autonomous cycle
- Test real-time event delivery
- _Requirements: 7.1, 7.2, 7.3_
- **Estimated time: 3-4 hours**

- [x] 2.6 Backend Testing and Integration
- Write unit tests for all new endpoints
- Test with existing AutonomousStrategyManager
- Verify data consistency with database
- Test WebSocket event broadcasting
- Load test with multiple concurrent clients
- _Requirements: All Phase 2_
- **Estimated time: 2-3 hours**

## Phase 3: Core Frontend Components (Week 2-3)

- [x] 3.1 Create Autonomous Status Component
- Create `AutonomousStatus.tsx` component
- Display system enabled/disabled status
- Show market regime with color coding
- Display cycle statistics
- Show portfolio health metrics
- Display template usage statistics
- Add manual trigger button
- Integrate with status API endpoint
- _Requirements: 2.1, 2.2, 2.3, 8.1, 8.2_
- **Estimated time: 4-5 hours**

- [x] 3.2 Create Performance Dashboard Component
- Create `PerformanceDashboard.tsx` component
- Build KPI metric cards (Sharpe, Return, Drawdown, Win Rate)
- Implement portfolio value chart (using recharts)
- Create strategy contribution breakdown
- Add time period selector (1M, 3M, 6M, 1Y, ALL)
- Integrate with performance metrics API
- **Add to Home page (`/`) after AutonomousStatus component**
- _Requirements: 5.1, 5.2, 5.3, 8.3, 8.4_
- **Estimated time: 5-6 hours**

- [x] 3.3 Enhance Strategies Component
- Update existing `Strategies.tsx` component (already exists in codebase)
- Add template badge display
- Add DSL rule code block display
- Implement filtering by source, status, template, regime
- Add sorting options
- Display walk-forward validation results
- Show parameter customizations
- Add bulk actions (backtest, retire, activate)
- **Component already used in Home page - just enhance it**
- _Requirements: 4.1, 4.2, 4.3, 4.4, 8.5_
- **Estimated time: 4-5 hours**

- [x] 3.4 Create Configuration Settings Panel
- Create `AutonomousSettings.tsx` component
- Build general settings section
- Build template enable/disable controls
- Create activation threshold sliders
- Create retirement trigger sliders
- Build advanced settings section
- Add validation for all inputs
- Implement save/reset functionality
- Show last updated timestamp
- **Add to Settings page (`/settings`) - check existing Settings.tsx structure first**
- _Requirements: 3.1, 3.2, 3.3, 3.4, 8.6_
- **Estimated time: 5-6 hours**

- [x] 3.5 Implement Notification System
- Create notification Redux slice (if Redux is used, otherwise use React Context)
- Add notification toast component (may already exist - check NotificationToast.tsx)
- Implement WebSocket notification listener
- Create notification preference settings
- Add notification history view
- Implement sound alerts (optional)
- Add action buttons to notifications
- **Check existing notification system first - NotificationToast.tsx already exists**
- _Requirements: 7.1, 7.2, 7.3, 8.7_
- **Estimated time: 3-4 hours**

- [x] 3.6 Integrate WebSocket Updates
- Update wsManager to handle autonomous channels
- Subscribe to autonomous events on connection
- Dispatch Redux actions on events
- Implement throttling for high-frequency updates
- Add reconnection logic
- Test real-time updates across components
- _Requirements: 7.1, 7.2, 7.3_
- **Estimated time: 2-3 hours**

## Phase 4: Autonomous Trading Page (Week 3-4)

- [x] 4.1 Create Autonomous Page Layout
- Create `Autonomous.tsx` page component (check if it already exists first)
- Add route `/autonomous` to App.tsx (route already exists - verify page implementation)
- Build page layout structure
- Add navigation menu item (check Sidebar.tsx for navigation)
- Implement responsive grid layout
- _Requirements: 9.1, 9.2_
- **Estimated time: 2 hours**

- [x] 4.2 Build Control Panel Section
- Create control panel component for Autonomous page
- Add enable/disable toggle
- Add manual trigger button with confirmation
- Add quick access to settings
- Show current system status
- **Add to Autonomous page (`/autonomous`) created in task 4.1**
- _Requirements: 9.3, 9.4_
- **Estimated time: 2-3 hours**

- [x] 4.3 Build Strategy Lifecycle Visualization
- Create lifecycle flow component
- Show proposed → backtesting → activated → retired flow
- Display counts for each stage
- Add navigation to view each stage
- Implement real-time updates
- **Add to Autonomous page (`/autonomous`)**
- _Requirements: 9.5, 9.6_
- **Estimated time: 3-4 hours**

- [x] 4.4 Build Portfolio Composition View
- Create portfolio composition component
- Implement strategy allocation pie chart
- Build correlation matrix heatmap
- Display risk metrics (VaR, max position, diversification)
- Add interactive tooltips
- **Add to Autonomous page (`/autonomous`)**
- _Requirements: 6.1, 6.2, 6.3, 9.7_
- **Estimated time: 4-5 hours**

- [x] 4.5 Build History & Analytics Section
- Create history timeline component
- Implement event filtering
- Build template performance charts
- Create regime-based analysis view
- Add export to CSV functionality
- Add report generation
- **Add to Autonomous page (`/autonomous`)**
- _Requirements: 6.4, 6.5, 9.8, 9.9_
- **Estimated time: 4-5 hours**

- [x] 4.6 Integrate All Autonomous Page Components
- Connect all sections to Redux store
- Implement data fetching on page load
- Add loading states
- Add error handling
- Ensure recent features and components are integrated and organised professionally in the front end
- Review existing dashboards and pages and ensure no component is using mock data
- Review existing layout and distribution of pages and components, and re-organise following best practices
- Unify buttons, eliminate redundancies
- Review style, colours and visual design, and make improvements to modernise and improve look and feel
- Test all interactionsno 
- _Requirements: 9.1-9.9_
- **Estimated time: 2-3 hours**

## Phase 5: Testing, Polish & Documentation (Week 4)

- [ ] 5.1 Unit Testing
- Write tests for AutonomousStatus component
- Write tests for PerformanceDashboard component
- Write tests for enhanced Strategies component
- Write tests for AutonomousSettings component
- Write tests for Autonomous page components
- Write tests for Redux actions and reducers
- Achieve >80% code coverage
- _Requirements: All_
- **Estimated time: 6-8 hours**

- [ ] 5.2 Integration Testing
- Test API integration for all endpoints
- Test WebSocket event handling
- Test Redux state updates
- Test component interactions
- Test error scenarios
- _Requirements: All_
- **Estimated time: 4-5 hours**

- [ ] 5.3 End-to-End Testing
- Test complete user flow: view status
- Test manual cycle trigger flow
- Test configuration update flow
- Test strategy viewing and filtering
- Test notification reception
- Test responsive design on different devices
- _Requirements: All_
- **Estimated time: 4-5 hours**

- [ ] 5.4 Performance Optimization
- Implement code splitting for heavy components
- Add data caching with appropriate TTLs
- Optimize WebSocket event handling
- Minimize re-renders with React.memo
- Lazy load charts and visualizations
- Run Lighthouse audit and optimize
- _Requirements: 10.1, 10.2, 10.3_
- **Estimated time: 3-4 hours**

- [ ] 5.5 Responsive Design Testing
- Test on mobile devices (< 768px)
- Test on tablets (768px - 1024px)
- Test on desktop (> 1024px)
- Verify all components adapt correctly
- Test touch interactions on mobile
- Fix any layout issues
- _Requirements: 10.4, 10.5_
- **Estimated time: 2-3 hours**

- [ ] 5.6 Accessibility Audit
- Run axe DevTools accessibility scan
- Ensure keyboard navigation works
- Add ARIA labels where needed
- Verify color contrast ratios
- Test with screen reader
- Add focus indicators
- Implement keyboard shortcuts
- _Requirements: 11.1, 11.2, 11.3_
- **Estimated time: 3-4 hours**

- [ ] 5.7 Documentation
- Document all new components with JSDoc
- Create user guide for autonomous trading
- Document API endpoints
- Create troubleshooting guide
- Add inline help text and tooltips
- Update README with new features
- _Requirements: 12.1, 12.2_
- **Estimated time: 3-4 hours**

- [ ] 5.8 Final Polish and Bug Fixes
- Fix any bugs found during testing
- Polish animations and transitions
- Ensure consistent styling
- Optimize loading states
- Add confirmation dialogs for destructive actions
- Final code review
- _Requirements: All_
- **Estimated time: 4-5 hours**

## Notes

**Total Estimated Time**: 100-120 hours (4 weeks with 25-30 hours/week)

**Critical Path**:
1. Phase 2 (Backend) must complete before Phase 3 (Frontend components)
2. Phase 3 must complete before Phase 4 (Autonomous page)
3. Phase 5 runs in parallel with final Phase 4 tasks

**Dependencies**:
- Backend autonomous system must be functional (already complete from intelligent-strategy-system spec)
- Existing test infrastructure (test_full_trading_cycle_v1_2year.py) used as reference
- WebSocket infrastructure already in place
- Redux store already configured

**Risk Mitigation**:
- Incremental approach allows testing at each phase
- Existing functionality preserved until new features ready
- Can deploy phases independently if needed
- Rollback plan: keep old components until new ones proven stable

**Success Criteria**:
- All legacy LLM/Vibe Coding features removed
- Autonomous trading system fully visible and controllable
- Real-time updates working via WebSocket
- Performance metrics displayed accurately
- Configuration changes persist correctly
- All tests passing (unit, integration, E2E)
- Responsive design works on all devices
- Accessibility standards met (WCAG 2.1 AA)


## Phase 2.5: Risk Management & Order Monitoring APIs (Week 2)

- [ ] 2.7 Implement Risk Metrics Endpoints
- Create `GET /api/risk/metrics` endpoint
- Calculate portfolio VaR (95% confidence)
- Calculate current drawdown and max position size
- Calculate leverage and margin utilization
- Calculate portfolio beta
- Compute risk breakdown by strategy
- Include active positions with stop-loss/take-profit
- _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.8_
- **Estimated time: 4-5 hours**

- [ ] 2.8 Implement Risk History and Limits Endpoints
- Create `GET /api/risk/history` endpoint
- Return historical risk metrics over time
- Create `PUT /api/risk/limits` endpoint
- Allow updating risk thresholds
- Validate limit values
- Persist to configuration
- _Requirements: 14.9, 14.7_
- **Estimated time: 2-3 hours**

- [ ] 2.9 Implement Execution Quality Endpoints
- Create `GET /api/orders/execution-quality` endpoint
- Calculate average slippage across orders
- Calculate fill rate and average fill time
- Calculate rejection rate
- Break down metrics by strategy
- Track rejection reasons
- Return historical trends
- _Requirements: 13.6_
- **Estimated time: 3-4 hours**

- [ ] 2.10 Enhance Orders Endpoint with Strategy Attribution
- Update `GET /api/orders` to include strategy information
- Add trigger rule and indicator values
- Add execution metrics (slippage, fill time)
- Add P&L for closed positions
- Create `GET /api/orders/by-strategy` endpoint
- Add filtering by strategy, status, date range
- _Requirements: 13.1, 13.2, 13.3, 13.5_
- **Estimated time: 3-4 hours**

- [ ] 2.11 Add Risk and Order WebSocket Events
- Add `risk:alerts` channel for threshold warnings
- Broadcast when risk metrics approach thresholds
- Add `orders:execution` channel for order events
- Broadcast execution quality metrics
- Broadcast rejection events with reasons
- Test real-time alert delivery
- _Requirements: 13.4, 14.7_
- **Estimated time: 2-3 hours**

## Phase 3.5: Risk & Order Monitoring Components (Week 3)

- [ ] 3.7 Create Risk Management Dashboard Component
- Create `RiskDashboard.tsx` component
- Build risk metric cards (VaR, Max Pos, Drawdown, Leverage)
- Implement risk threshold progress bars
- Display risk breakdown by strategy
- Show active positions with SL/TP levels
- Add status indicators (safe/warning/danger)
- Integrate with risk metrics API
- Add real-time WebSocket updates
- _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.8, 14.10_
- **Estimated time: 5-6 hours**

- [ ] 3.8 Create Risk History Visualization
- Create `RiskHistory.tsx` component
- Implement time-series charts for risk metrics
- Add metric selector (VaR, Drawdown, Leverage, Beta)
- Add time period selector (1D, 1W, 1M, 3M)
- Show threshold lines on charts
- Highlight threshold breaches
- Add export functionality
- _Requirements: 14.9_
- **Estimated time: 3-4 hours**

- [ ] 3.9 Enhance Orders Component with Strategy Attribution
- Update `Orders.tsx` component
- Add strategy name and ID display
- Show trigger rule that generated order
- Display indicator values at trigger time
- Show execution metrics (slippage, fill time)
- Display P&L for filled orders
- Add strategy filtering
- Show rejection reasons prominently
- _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_
- **Estimated time: 4-5 hours**

- [ ] 3.10 Create Execution Quality Analytics Component
- Create `ExecutionQuality.tsx` component
- Build metric cards (Slippage, Fill Rate, Fill Time, Rejections)
- Implement slippage by strategy bar chart
- Create fill rate trend line chart
- Build rejection reasons breakdown
- Add time period selector
- Integrate with execution quality API
- _Requirements: 13.6_
- **Estimated time: 4-5 hours**

- [ ] 3.11 Create Risk Configuration Panel
- Create `RiskSettings.tsx` component in Settings
- Build risk limit sliders (VaR, Drawdown, Position, Leverage)
- Add validation for limit values
- Show current vs. new limits comparison
- Implement save/reset functionality
- Add confirmation for risky changes
- Show last updated timestamp
- _Requirements: 14.7_
- **Estimated time: 3-4 hours**

- [ ] 3.12 Implement Risk Alert Notifications
- Add risk alert notification types
- Create alert severity levels (info, warning, danger)
- Implement threshold warning notifications
- Implement threshold breach notifications
- Add action buttons to alerts (View Risk, Adjust Limits)
- Add sound alerts for critical breaches
- Test WebSocket alert delivery
- _Requirements: 14.7_
- **Estimated time: 2-3 hours**

## Phase 4.5: Integrate Risk & Orders into Autonomous Page (Week 3-4)

- [ ] 4.7 Add Risk Monitoring to Autonomous Page
- Add Risk Dashboard to Autonomous page
- Position prominently for visibility
- Add quick access to risk settings
- Add link to risk history
- Ensure real-time updates work
- _Requirements: 14.1-14.10_
- **Estimated time: 1-2 hours**

- [ ] 4.8 Add Order Monitoring to Autonomous Page
- Add enhanced Orders component to Autonomous page
- Add execution quality analytics section
- Add filtering by autonomous strategies only
- Show order flow timeline
- Link orders to strategy details
- _Requirements: 13.1-13.7_
- **Estimated time: 2-3 hours**

- [ ] 4.9 Create Integrated Risk & Performance View
- Create combined view showing risk vs. performance
- Plot strategies on risk/return scatter chart
- Show efficient frontier
- Highlight strategies outside acceptable risk
- Add recommendations for rebalancing
- _Requirements: 14.8, 14.9_
- **Estimated time: 3-4 hours**

## Updated Phase 5 Tasks

- [ ] 5.9 Test Risk Management Features
- Test risk metric calculations
- Test threshold alerts
- Test risk limit updates
- Test risk history visualization
- Test WebSocket risk alerts
- Verify accuracy of VaR calculations
- _Requirements: 14.1-14.10_
- **Estimated time: 3-4 hours**

- [ ] 5.10 Test Order Monitoring Features
- Test strategy attribution display
- Test execution quality metrics
- Test order filtering and search
- Test rejection handling
- Test WebSocket order updates
- Verify slippage calculations
- _Requirements: 13.1-13.7_
- **Estimated time: 2-3 hours**

## Phase 6: Trading Pipeline Regression Fix (Critical)

**Context**: After the UI overhaul (Phases 1-4), the autonomous trading system generates strategies but NEVER produces actual trades. Evidence:
- 27 DEMO strategies exist, system state is ACTIVE
- ZERO orders from any autonomous strategy (all 30 orders are from old manual/vibe_coding)
- 4 open positions are test data (strategy_1/2/3) and one eToro position, none from autonomous strategies
- Trading scheduler runs every 5s (order monitoring) and every 5min (signal generation)
- Signal generation fetches 730+ days of Yahoo Finance data per strategy per cycle — extremely slow with 27 strategies
- The intelligent-strategy-system spec had working end-to-end tests, but the UI overhaul introduced regressions

**Root Cause Hypothesis**:
1. Signal generation never completes within the 5-minute interval (27 strategies × 730 days of data each = massive I/O)
2. DSL rule parsing may produce conditions that never trigger on current market data
3. Risk validation may reject all signals (position sizing, account balance checks)
4. The trading scheduler may be silently erroring during signal generation
5. Test positions (strategy_1/2/3) may interfere with risk validation (fake positions consuming allocation)

- [x] 6.1 Diagnose Signal Generation Pipeline
  - Run a single strategy through the full signal generation pipeline manually (not via scheduler)
  - Pick one DEMO strategy and call `strategy_engine.generate_signals(strategy)` directly
  - Log every step: data fetch duration, indicator calculation, DSL rule evaluation, entry/exit signals
  - Check if signals are generated but rejected by risk manager
  - Check if data fetching is timing out or returning insufficient data
  - Check backend logs for any errors during signal generation cycles
  - Document findings: which step fails and why
  - **Acceptance**: Clear identification of where the pipeline breaks (data fetch, rule eval, risk validation, or order execution)
  - **Estimated time: 2-3 hours**

- [x] 6.2 Clean Up Test Data and Stale Positions
  - Remove fake test positions (strategy_1, strategy_2, strategy_3) from positions table
  - Remove old manual/vibe_coding orders that are no longer relevant
  - Retire all current BACKTESTED strategies that won't be used (123 strategies cluttering the DB)
  - Verify the 27 DEMO strategies are valid and have proper rules/indicators
  - Clean up any orphaned data (positions without strategies, orders without strategies)
  - **Acceptance**: Database contains only valid autonomous strategies and no test artifacts
  - **Estimated time: 1-2 hours**

- [x] 6.3 Fix Signal Generation Performance (without reducing strategy quality)
  - **IMPORTANT**: Do NOT reduce the data period if it would degrade indicator accuracy. The goal is to make signal generation fast enough to complete within the 5-minute interval, while preserving the same signal quality as backtesting.
  - Investigate: How much historical data do the indicators actually need? (RSI needs ~14 days warmup, SMA_50 needs ~50 days, Bollinger needs ~20 days). The max indicator period + a safety buffer is the minimum data needed — NOT 730 days.
  - Add a separate `signal_generation_days` config (default: 120 days) distinct from `backtest_days` (730 days). This gives indicators plenty of warmup without fetching 2 years of data every 5 minutes.
  - Add data caching in signal generation: cache Yahoo Finance data for 1 hour to avoid re-fetching the same symbol for multiple strategies (e.g., 10 strategies all trade SPY — fetch SPY once, share the data)
  - Add timeout protection: if signal generation for one strategy takes >60s, skip and log warning
  - Batch strategies by symbol to share data fetches (all SPY strategies use the same SPY data)
  - Log timing for each step: data fetch, indicator calc, rule eval, total per strategy
  - Verify that signals generated with the optimized data period match what the full 730-day period would produce (spot-check 3-5 strategies)
  - **Acceptance**: Full signal generation cycle for 27 strategies completes in <2 minutes AND signal quality is identical to full-data generation
  - **Estimated time: 3-4 hours**

- [x] 6.4 Validate DSL Rules Produce Signals on Current Market Data
  - For each of the 27 DEMO strategies, run signal generation and log:
    - Entry condition evaluation result (True/False) for the latest data point
    - Exit condition evaluation result (True/False) for the latest data point
    - Number of entry signals in last 30 days
    - Number of exit signals in last 30 days
  - If a strategy produces 0 signals in 30 days, flag it as "dormant" and log the reason
  - Create a summary: X/27 strategies would generate signals today, Y/27 are dormant
  - If >50% are dormant, investigate whether DSL rules are too restrictive for current market regime
  - Adjust strategy templates or thresholds if needed to ensure at least some strategies generate signals
  - **Acceptance**: At least 5 of 27 DEMO strategies generate entry signals on current market data
  - **Estimated time: 2-3 hours**

- [x] 6.5 Fix Risk Validation for Autonomous Trades
  - Review risk manager validation logic for autonomous strategy signals
  - Check account balance retrieval: does the eToro client return valid balance for DEMO account?
  - Check position sizing: are position sizes calculated correctly for DEMO mode?
  - Check if existing fake positions (strategy_1/2/3) are consuming risk allocation
  - Verify stop_loss_pct and take_profit_pct are set on DEMO strategies (not None/0)
  - Test risk validation with a known-good signal to confirm it passes
  - If risk validation is too strict, adjust thresholds for DEMO mode
  - **Acceptance**: A valid ENTER_LONG signal for SPY passes risk validation in DEMO mode
  - **Estimated time: 2-3 hours**

## Phase 6.5: Advanced Position Management (Critical Trading Improvements)

**Context**: The current system sets stop-loss and take-profit once when orders are placed, then never adjusts them. This "set and forget" approach misses opportunities to protect profits and optimize exits. Professional traders actively manage positions using trailing stops, partial exits, and dynamic adjustments. This phase implements these critical trading features.

**Priority**: High - These features directly impact profitability and risk management.

- [x] 6.5.1 Implement Trailing Stop-Loss Logic
  - Add `trailing_stop_enabled` field to RiskConfig dataclass (default: False)
  - Add `trailing_stop_activation_pct` field (default: 0.05 = 5% profit before trailing activates)
  - Add `trailing_stop_distance_pct` field (default: 0.03 = 3% trailing distance)
  - Create `PositionManager` class in `src/execution/position_manager.py`:
    - `check_trailing_stops(positions: List[Position]) -> List[Order]`
    - For each open position with profit > activation threshold:
      - Calculate new stop-loss level (current_price - trailing_distance)
      - If new stop > current stop, update stop-loss via eToro API
      - Log stop-loss adjustment
  - Add trailing stop logic to OrderMonitor.run_monitoring_cycle()
  - Add database migration for new RiskConfig fields
  - Add unit tests for trailing stop calculations
  - **Acceptance**: Profitable positions automatically move stop-loss up to protect gains
  - **Estimated time: 4-5 hours**

- [x] 6.5.2 Implement Partial Exit Strategy
  - Add `partial_exit_enabled` field to RiskConfig (default: False)
  - Add `partial_exit_levels` field (default: [{"profit_pct": 0.05, "exit_pct": 0.5}])
  - Extend PositionManager with `check_partial_exits(positions: List[Position]) -> List[Order]`:
    - For each position that hits a profit level:
      - Calculate exit quantity (position_size * exit_pct)
      - Create SELL order for partial quantity
      - Mark position as "partially exited" to avoid re-triggering
      - Log partial exit
  - Add partial exit tracking to Position dataclass (add `partial_exits: List[Dict]` field)
  - Update position P&L calculation to handle partial exits
  - Add database migration for partial exit tracking
  - Add unit tests for partial exit logic
  - **Acceptance**: Positions can take partial profits at predefined levels while letting rest run
  - **Estimated time: 5-6 hours**

- [x] 6.5.3 Implement Correlation-Adjusted Position Sizing
  - Extend RiskManager with `calculate_correlation_adjusted_size()` method
  - Use existing `PortfolioManager.get_correlated_positions()` logic
  - When validating a new signal:
    - Check for correlated positions (same symbol or high strategy correlation)
    - If correlation > 0.7, reduce position size by correlation factor
    - Formula: `adjusted_size = base_size * (1 - correlation * 0.5)`
    - Log size adjustment reason
  - Add `correlation_adjustment_enabled` field to RiskConfig (default: True)
  - Add unit tests for correlation-adjusted sizing
  - **Acceptance**: Position sizes automatically reduced when adding correlated positions
  - **Estimated time: 3-4 hours**

- [x] 6.5.4 Implement Order Cancellation Logic
  - Add `cancel_order(order_id: str, reason: str)` method to OrderExecutor
  - Call eToro API to cancel pending order
  - Update order status to CANCELLED in database
  - Add `cancel_stale_orders()` method to OrderMonitor:
    - Find pending orders older than X hours (configurable, default: 24h)
    - Cancel orders where market conditions changed significantly
    - Log cancellation reason
  - Add order cancellation to OrderMonitor.run_monitoring_cycle()
  - Add unit tests for order cancellation
  - **Acceptance**: Stale pending orders automatically cancelled after timeout
  - **Estimated time: 2-3 hours**

- [x] 6.5.5 Implement Slippage and Execution Quality Tracking
  - Add `expected_price` field to Order dataclass
  - Add `slippage` field to Order dataclass (calculated: filled_price - expected_price)
  - Add `fill_time_seconds` field to Order dataclass
  - Update OrderMonitor.check_submitted_orders() to calculate slippage and fill time
  - Create `ExecutionQualityTracker` class in `src/monitoring/execution_quality.py`:
    - Track average slippage by strategy
    - Track fill rate (filled / submitted)
    - Track average fill time
    - Track rejection rate and reasons
  - Add execution quality metrics to performance dashboard
  - Add database migration for new Order fields
  - Add unit tests for slippage calculations
  - **Acceptance**: All orders tracked for execution quality with slippage and fill time metrics
  - **Estimated time: 3-4 hours**

- [x] 6.5.5.1 Separate Monitoring Service from Trading Scheduler (CRITICAL ARCHITECTURE)
  - **Context**: Currently, order/position monitoring only runs when trading is ACTIVE. When system is PAUSED, database becomes stale and frontend shows outdated data. This violates the principle that monitoring ≠ trading decisions.
  - **Architecture Goal**: Create independent monitoring service that runs 24/7 regardless of trading state
  - **Phase 1: Create MonitoringService Class (2-3 hours)**
    - Create `src/core/monitoring_service.py` with `MonitoringService` class
    - Move monitoring logic from TradingScheduler to MonitoringService:
      - `process_pending_orders()` - submit pending orders to eToro
      - `check_submitted_orders()` - update order status from eToro
      - `sync_positions()` - sync positions from eToro
      - `check_trailing_stops()` - update trailing stops
    - Add configurable intervals:
      - `pending_orders_interval: int = 5` (5s - immediate submission)
      - `order_status_interval: int = 30` (30s - with caching)
      - `position_sync_interval: int = 60` (60s - with caching)
      - `trailing_stops_interval: int = 5` (5s - database only, no API)
    - Implement async run loop similar to TradingScheduler
    - Add start/stop methods
    - Add error handling and logging
  - **Phase 2: Update TradingScheduler (1 hour)**
    - Remove monitoring logic from TradingScheduler._run_trading_cycle()
    - Keep only signal generation and order execution in TradingScheduler
    - TradingScheduler now only runs when state == ACTIVE
    - MonitoringService runs independently of system state
  - **Phase 3: Update main.py Startup (30 min)**
    - Initialize MonitoringService in main.py
    - Start MonitoringService on app startup (always running)
    - Start TradingScheduler only when system state is ACTIVE
    - Ensure both services share same eToro client and database
  - **Phase 4: Update Orders API (30 min)**
    - Remove eToro sync logic from `GET /api/orders` endpoint
    - Endpoint now only queries database (fast, no API calls)
    - Database is always fresh because MonitoringService runs 24/7
    - Remove `order_monitor.check_submitted_orders()` call from endpoint
  - **Phase 5: Testing (1-2 hours)**
    - Test MonitoringService runs when system is PAUSED
    - Test database updates even when trading is paused
    - Test frontend shows fresh data when trading is paused
    - Test TradingScheduler still works when ACTIVE
    - Test both services don't conflict
    - Verify API calls are optimized (caching still works)
  - **Benefits**:
    - Database always has fresh data (even when trading paused)
    - Frontend never calls eToro directly (fast, scalable)
    - Clean separation: monitoring vs trading decisions
    - Orders API is fast (database only, no eToro calls)
  - **Reference**: See conversation analysis for detailed architecture discussion
  - **Acceptance**: 
    - MonitoringService runs independently of trading state
    - Database updates every 5-60s even when PAUSED
    - Orders API returns fresh data without eToro calls
    - TradingScheduler only handles signal generation
    - All tests pass
  - **Estimated time: 4-6 hours**

- [x] 6.5.6 Implement Market Regime-Based Position Sizing
  - Add `regime_based_sizing_enabled` field to RiskConfig (default: False)
  - Add `regime_size_multipliers` field (default: {"high_volatility": 0.5, "low_volatility": 1.0, "trending": 1.2, "ranging": 0.8})
  - Extend RiskManager.validate_signal() to adjust size based on current market regime
  - Use MarketAnalyzer to get current regime
  - Apply regime multiplier to base position size
  - Log regime-based size adjustment
  - Add unit tests for regime-based sizing
  - **Acceptance**: Position sizes automatically adjusted based on market conditions
  - **Estimated time: 2-3 hours**

- [x] 6.5.7 Update Configuration Files and Documentation
  - Add all new fields to `config/autonomous_trading.yaml`:
    ```yaml
    position_management:
      trailing_stops:
        enabled: true
        activation_pct: 0.05  # Start trailing after 5% profit
        distance_pct: 0.03    # Trail 3% below current price
      partial_exits:
        enabled: true
        levels:
          - profit_pct: 0.05  # Take 50% profit at 5% gain
            exit_pct: 0.5
          - profit_pct: 0.10  # Take 25% more at 10% gain
            exit_pct: 0.25
      correlation_adjustment:
        enabled: true
        threshold: 0.7        # Reduce size if correlation > 0.7
        reduction_factor: 0.5 # Reduce by 50% of correlation
      regime_based_sizing:
        enabled: false        # Disabled by default (advanced feature)
        multipliers:
          high_volatility: 0.5
          low_volatility: 1.0
          trending: 1.2
          ranging: 0.8
      order_management:
        cancel_stale_orders: true
        stale_order_hours: 24
    ```
  - Update `config/risk_config.json` with new fields
  - Document all new features in README
  - Add examples of how to configure each feature
  - **Acceptance**: All new features configurable via YAML with sensible defaults
  - **Estimated time: 1-2 hours**

- [x] 6.5.8 Integration Testing for Position Management
  - Test trailing stops with simulated profitable position
  - Test partial exits with position hitting profit levels
  - Test correlation-adjusted sizing with correlated signals
  - Test order cancellation with stale orders
  - Test slippage tracking with filled orders
  - Test regime-based sizing with different market regimes
  - Verify all features work together without conflicts
  - Test with real eToro DEMO account
  - **Acceptance**: All position management features work correctly in integration
  - **Estimated time: 3-4 hours**

- [x] 6.5.9 Implement Pending Order Duplicate Prevention (CRITICAL)
  - **Context**: Strategies generate signals every 5 minutes, creating duplicate orders before previous orders fill (29 OIL orders, 23 JPM orders observed)
  - **Root Cause**: `_coordinate_signals()` checks existing positions but NOT pending/submitted orders
  - Extend `_coordinate_signals()` method to accept `pending_orders` parameter
  - Query database for pending/submitted orders in `_run_trading_cycle()`:
    ```python
    pending_orders = session.query(OrderORM).filter(
        OrderORM.status.in_([OrderStatus.PENDING, OrderStatus.SUBMITTED])
    ).all()
    ```
  - Build `pending_orders_map` by (strategy_id, symbol, side) in `_coordinate_signals()`
  - Filter signals if strategy already has pending order for that symbol/side:
    ```python
    pending_key = (strategy_id, symbol, direction)
    if pending_key in pending_orders_map:
        logger.info(f"Pending order check: {strategy_name} already has pending order for {symbol}")
        continue  # Skip this strategy's signal
    ```
  - Log all filtered signals for visibility
  - Add database unique constraint as safeguard (optional but recommended):
    ```sql
    CREATE UNIQUE INDEX idx_active_orders_per_strategy_symbol 
    ON orders (strategy_id, symbol, side) 
    WHERE status IN ('PENDING', 'SUBMITTED');
    ```
  - Add unit tests for pending order filtering
  - Add integration test: run 2 strategies trading same symbol, verify only 1 order per strategy
  - **Trading Best Practice**: One active trade per symbol per strategy (pending order OR open position)
  - **Reference**: See `DUPLICATE_ORDER_ANALYSIS.md` for detailed analysis
  - **Acceptance**: No duplicate orders created for same strategy-symbol-side combination
  - **Estimated time: 2-3 hours**

- [x] 6.6 End-to-End Trade Execution Test (Updated)
  - Retire all current strategies (clean slate)
  - Trigger a new autonomous cycle with reduced proposal_count (5-10 strategies)
  - Wait for cycle to complete and strategies to be activated in DEMO mode
  - Manually trigger signal generation for the new strategies
  - Verify at least one signal is generated, validated, and an order is placed
  - Check the orders table for new autonomous orders
  - Check the positions table for new autonomous positions
  - Monitor the trading scheduler for 5 minutes to verify it picks up the new strategies
  - **NEW: Test position management features**:
    - Verify trailing stops activate when position becomes profitable
    - Verify partial exits trigger at profit levels
    - Verify correlation-adjusted sizing when adding correlated positions
    - Verify stale orders get cancelled after timeout
    - Verify slippage and execution quality tracked for all orders
  - Document the full flow: cycle → strategies → signals → validation → orders → positions → position management
  - **Acceptance**: At least 1 autonomous order placed, position management features working
  - **Estimated time: 4-5 hours**

- [x] 6.7 Frontend Trading Activity Visibility
  - Verify the Autonomous page shows real trading activity (not just strategy counts)
  - Ensure orders from autonomous strategies appear in the orders view
  - Ensure positions from autonomous strategies appear in the portfolio view
  - Ensure Strategy Lifecycle component in the AutonomousControlPanel shows real data
  - Add a "Recent Trades" section to the AutonomousControlPanel showing last 20 autonomous orders
  - Add signal generation status indicator (last signal check time, signals generated count)
  - Show trading scheduler status (running/paused, last cycle time, next cycle time)
  - **Acceptance**: Frontend accurately reflects autonomous trading activity including orders and positions
  - **Estimated time: 3-4 hours**

## Updated Notes

**Total Estimated Time**: 160-190 hours (6-7 weeks with 25-30 hours/week)

**Additional Components**:
- Risk Management Dashboard (critical for trading)
- Execution Quality Analytics (critical for trading)
- Enhanced Orders with strategy attribution
- Risk alert system
- Risk configuration panel

**Critical for Trading POV**:
- Real-time risk monitoring prevents catastrophic losses
- Execution quality tracking ensures strategies perform as expected
- Order attribution helps debug strategy issues
- Risk alerts enable proactive risk management
- Stop-loss/take-profit visibility ensures protection is active


## Phase 7: Frontend Comprehensive Redesign (Critical)

**Context**: After implementing autonomous trading features, the frontend has become cluttered with duplicate components, illogical navigation, and poor information architecture. The current design doesn't provide professional trading platform visibility. This phase will completely redesign the frontend to match professional trading platform standards while maintaining all backend functionality.

**Reference**: See `FRONTEND_COMPREHENSIVE_ANALYSIS.md` for detailed analysis and design specifications.

- [x] 7.1 Navigation & Page Structure Redesign
  - Analyze current page structure and identify redundancies
  - Design new navigation hierarchy (Overview, Portfolio, Orders, Strategies, Autonomous, Risk, Analytics, Settings)
  - Remove redundant pages (merge Home/Dashboard into Overview)
  - Update Sidebar component with new navigation
  - Update App.tsx routing
  - Create placeholder pages for new structure
  - Ensure no backend changes required
  - **Acceptance**: Clean navigation with 8 logical pages, no redundancy
  - **Estimated time: 4-6 hours**

- [x] 7.2 Design System Implementation with Modern Stack
  - **Install modern UI libraries**: shadcn/ui, Radix UI, Lucide React, Framer Motion
  - **Install data libraries**: TanStack Table, React Hook Form, date-fns, Zustand
  - **Install utilities**: clsx, tailwind-merge, Sonner (toast notifications)
  - Update Tailwind config with shadcn/ui theme
  - Create professional color palette (dark theme for trading)
  - Define typography scale (headers, body, monospace for numbers)
  - Create spacing and layout system
  - Build reusable components using shadcn/ui:
    - Dialog (for modals and confirmations)
    - DropdownMenu (for action menus)
    - Tooltip (for metric explanations)
    - Select (for filters)
    - Tabs (for view switching)
    - Command (for Cmd+K palette)
  - Enhance existing components with Framer Motion animations
  - Create MetricCard component with animations
  - Create DataTable component using TanStack Table
  - Set up Zustand stores for global state
  - Create utility functions (cn(), formatters)
  - Document design system with examples
  - **Reference**: See `MODERN_TECH_STACK_RECOMMENDATIONS.md` for detailed tech stack
  - **Acceptance**: Modern, professional component library with animations and accessibility
  - **Estimated time: 8-10 hours**

- [x] 7.3 Overview Page (New Home) with Modern Components
  - Create new Overview page as default landing
  - Build Portfolio Summary widget using shadcn Card and Framer Motion
  - Build Key Metrics row (6 KPIs using animated MetricCard components)
  - Build Top Positions widget using TanStack Table (5-10 positions with real-time P&L)
  - Build Recent Orders widget using TanStack Table (last 10 orders)
  - Build System Status widget with Lucide icons
  - Build Quick Actions panel using shadcn Buttons with icons
  - Implement 3-column responsive grid layout
  - Add smooth page transitions with Framer Motion
  - Connect all widgets to real backend data
  - Add real-time WebSocket updates with flash animations
  - Use Sonner for toast notifications
  - **Acceptance**: Professional overview page with smooth animations and real data
  - **Estimated time: 8-10 hours**

- [x] 7.4 Portfolio Page Redesign with Tabbed Layout
  - Create dedicated Portfolio page with shadcn Tabs component
  - **Tab 1: Overview**
    - Account Summary section (balance, buying power, margin, daily P&L)
    - Key metrics cards (total positions, total P&L, win rate, avg holding time)
    - Position allocation pie chart
  - **Tab 2: Open Positions**
    - Full positions table using TanStack Table (all positions, not just top 5)
    - Search by symbol
    - Filter by strategy, side (Long/Short)
    - Sortable columns (symbol, P&L, size, entry price, current price)
    - Scrollable table (600px max height)
    - Pagination (20 per page)
    - Shows "X of Y positions"
    - Position actions (close, modify SL/TP) using shadcn DropdownMenu
  - **Tab 3: Closed Positions**
    - Recent closed trades with realized P&L
    - Search by symbol
    - Filter by strategy, date range
    - Sortable columns (symbol, realized P&L, holding time, exit reason)
    - Scrollable table (600px max height)
    - Pagination (20 per page)
  - Implement real-time WebSocket updates with flash animations
  - Add export to CSV functionality
  - Dynamic tab counts update with filters
  - **Reference**: Follow OverviewNew.tsx tabbed pattern
  - **Acceptance**: Professional tabbed portfolio page with proper spacing and filtering
  - **Estimated time: 8-10 hours**

- [x] 7.5 Orders Page Creation with Tabbed Layout
  - Create new dedicated Orders page with shadcn Tabs component
  - **Tab 1: Overview**
    - Order summary metrics (total orders, pending, filled, cancelled, rejected)
    - Execution quality cards (avg slippage, fill rate, avg fill time)
    - Order flow timeline (last 24 hours)
  - **Tab 2: All Orders**
    - Full orders table using TanStack Table (all orders, not just last 10)
    - Search by symbol
    - Filter by status (Pending/Filled/Cancelled/Rejected)
    - Filter by strategy, side (Buy/Sell), source (Autonomous/Manual)
    - Sortable columns (time, symbol, side, quantity, price, status)
    - Scrollable table (600px max height)
    - Pagination (20 per page)
    - Shows "X of Y orders"
    - Action menu using shadcn DropdownMenu (cancel, view details)
  - **Tab 3: Execution Analytics**
    - Slippage by strategy bar chart
    - Fill rate trend line chart
    - Rejection reasons breakdown
    - Time period selector (1D, 1W, 1M)
  - Add date range picker using shadcn Popover + date-fns
  - Show strategy attribution with Tooltip
  - Real-time updates with flash animations
  - Dynamic tab counts update with filters
  - Use Sonner for action confirmations
  - Export to CSV functionality
  - **Reference**: Follow OverviewNew.tsx tabbed pattern
  - **Acceptance**: Professional tabbed orders page with proper spacing and filtering
  - **Estimated time: 8-10 hours**

- [x] 7.6 Strategies Page Redesign with Tabbed Layout
  - Redesign Strategies page with shadcn Tabs component
  - **Tab 1: Overview**
    - Strategy summary metrics (total active, total retired, avg performance, success rate)
    - Template distribution chart
    - Performance by regime chart
    - Top performing strategies (top 5)
  - **Tab 2: Active Strategies**
    - Full strategies table using TanStack Table (all active strategies)
    - Search by name or symbol
    - Filter by template, regime, source (Autonomous/Manual)
    - Sortable columns (name, template, performance, sharpe, status)
    - Scrollable table (600px max height)
    - Pagination (20 per page)
    - Shows "X of Y strategies"
    - Action menu using shadcn DropdownMenu (view details, backtest, retire)
  - **Tab 3: Retired Strategies**
    - Retired strategies table with retirement reason
    - Search and filter capabilities
    - Shows retirement date and final performance
  - Create Strategy Details Dialog using shadcn Dialog component
  - Add Strategy Comparison tool using nested tabs
  - Implement bulk actions using shadcn Checkbox + DropdownMenu
  - Add strategy search using shadcn Command palette (Cmd+K)
  - Show real-time performance updates with animations
  - Dynamic tab counts update with filters
  - Use Lucide icons for actions and status
  - **Reference**: Follow OverviewNew.tsx tabbed pattern
  - **Acceptance**: Professional tabbed strategies page with proper spacing and filtering
  - **Estimated time: 10-12 hours**

- [x] 7.7 Autonomous Page Redesign with Tabbed Layout
  - Redesign Autonomous page with shadcn Tabs component
  - **Tab 1: Control & Status**
    - Control Panel (start/stop, trigger cycle, enable/disable with clear states)
    - System Status (scheduler state, last signal, last order, uptime)
    - Quick Actions panel
    - Trading mode warning
  - **Tab 2: Strategy Lifecycle**
    - Strategy Lifecycle visualization (proposed → backtested → active → retired with counts)
    - Search by strategy name
    - Filter by lifecycle stage
    - Scrollable table (600px max height)
    - Pagination (20 per page)
    - Shows "X of Y strategies in [stage]"
  - **Tab 3: Recent Activity**
    - Last 50 autonomous orders with details
    - Search by symbol
    - Filter by status, side
    - Scrollable table (600px max height)
    - Pagination (20 per page)
  - **Tab 4: Performance**
    - Autonomous Performance summary (success rate, activation rate, retirement rate)
    - Performance by template chart
    - Configuration quick access (link to settings with current thresholds)
  - Implement real-time updates with flash animations
  - Dynamic tab counts update with filters
  - **Reference**: Follow OverviewNew.tsx tabbed pattern
  - **Acceptance**: Professional tabbed autonomous page with proper spacing and clear monitoring
  - **Estimated time: 8-10 hours**

- [x] 7.8 Risk Page Creation with Tabbed Layout
  - Create new Risk page with shadcn Tabs component
  - **Tab 1: Overview**
    - Risk Metrics Dashboard (VaR, max drawdown, leverage, beta, exposure)
    - Risk status indicators (safe/warning/danger)
    - Risk Alerts section (threshold warnings and breaches)
    - Quick access to risk limit configuration
  - **Tab 2: Position Risk**
    - Position Concentration section (by strategy, by symbol, by sector)
    - All positions with risk metrics
    - Search by symbol
    - Filter by risk level (high/medium/low)
    - Scrollable table (600px max height)
    - Pagination (20 per page)
    - Shows "X of Y positions"
  - **Tab 3: Correlation Analysis**
    - Correlation Matrix heatmap (strategy correlations)
    - Diversification metrics
    - Portfolio beta breakdown
  - **Tab 4: Risk History**
    - Risk history charts (VaR over time, drawdown over time, leverage over time)
    - Time period selector (1D, 1W, 1M, 3M)
    - Risk limit breaches timeline
  - Build Risk Limits section (current vs limits with progress bars)
  - Implement real-time updates with flash animations
  - Dynamic tab counts update with filters
  - **Reference**: Follow OverviewNew.tsx tabbed pattern
  - **Acceptance**: Professional tabbed risk page with proper spacing and comprehensive monitoring
  - **Estimated time: 10-12 hours**

- [x] 7.9 Analytics Page Creation with Tabbed Layout
  - Create new Analytics page with shadcn Tabs component
  - **Tab 1: Performance**
    - Performance summary metrics (total return, Sharpe, max drawdown, win rate)
    - Equity curve chart
    - Drawdown chart
    - Returns distribution histogram
    - Time period selector (1M, 3M, 6M, 1Y, ALL)
  - **Tab 2: Strategy Attribution**
    - Strategy contribution to returns table
    - Search by strategy name
    - Filter by template, regime
    - Sortable columns (strategy, return, contribution, Sharpe)
    - Scrollable table (600px max height)
    - Pagination (20 per page)
    - Performance by strategy bar chart
  - **Tab 3: Trade Analytics**
    - Win/loss distribution chart
    - Holding periods histogram
    - P&L by time of day heatmap
    - P&L by day of week chart
    - Trade statistics table
  - **Tab 4: Regime Analysis**
    - Performance by market regime table
    - Regime transition timeline
    - Strategy performance by regime heatmap
  - Add export functionality (CSV, PDF reports)
  - Implement data visualization with recharts
  - Dynamic tab counts and metrics update with filters
  - **Reference**: Follow OverviewNew.tsx tabbed pattern
  - **Acceptance**: Professional tabbed analytics page with proper spacing and comprehensive analysis
  - **Estimated time: 12-14 hours**

- [x] 7.10 Settings Page Redesign with Form Management
  - Redesign Settings page with organized sections using shadcn Tabs
  - Build Trading Mode section with shadcn Switch + confirmation Dialog
  - Build Autonomous Configuration section using React Hook Form
  - Build Risk Limits section with validated inputs
  - Build Notification Preferences section with shadcn Checkbox groups
  - Build API Configuration section with secure input handling
  - Add form validation using React Hook Form + Zod
  - Add save/reset functionality with Sonner confirmations
  - Show last updated timestamp using date-fns
  - Use Lucide icons for section headers
  - **Acceptance**: Organized settings with proper form validation and UX
  - **Estimated time: 8-10 hours**

- [x] 7.11 Remove Duplicate Components
  - Audit all components and identify duplicates
  - Remove unused components
  - Consolidate similar components (e.g., multiple status displays)
  - Update imports across all pages
  - Remove unused dependencies
  - Clean up component directory structure
  - **Acceptance**: No duplicate components, clean component structure
  - **Estimated time: 3-4 hours**

- [x] 7.12 Visual Design Polish with Modern Animations
  - Apply new color palette consistently across all pages
  - Implement typography scale consistently
  - Add proper spacing and alignment using Tailwind utilities
  - Improve visual hierarchy (size, weight, color)
  - Add Framer Motion animations:
    - Page transitions (fade in/out)
    - Card entrance animations (slide up)
    - Number counting animations for metrics
    - Smooth chart updates
    - Flash animations for real-time updates
  - Improve data density (show more information efficiently)
  - Add proper loading states using shadcn Skeleton
  - Add proper error states with retry using shadcn Alert
  - Add micro-interactions (hover effects, button press animations)
  - **Acceptance**: Professional, animated, consistent visual design
  - **Estimated time: 8-10 hours**

- [ ] 7.13 Responsive Design Implementation
  - Test all pages on mobile (< 768px)
  - Test all pages on tablet (768px - 1024px)
  - Test all pages on desktop (> 1024px)
  - Implement responsive grid layouts
  - Implement responsive navigation (hamburger menu on mobile)
  - Ensure all tables are scrollable on mobile
  - Ensure all charts are responsive
  - Test touch interactions on mobile
  - **Acceptance**: All pages work perfectly on all device sizes
  - **Estimated time: 6-8 hours**

- [x] 7.14 Real-Time Data Integration & API Validation
  - **Phase 1: API Integration Audit**
    - Review all API calls in new pages (OverviewNew, PortfolioNew, OrdersNew, StrategiesNew, AutonomousNew, RiskNew, AnalyticsNew, SettingsNew)
    - Compare frontend data structures with backend API responses
    - Identify field name mismatches (e.g., `max_position_size` vs `max_position_size_pct`)
    - Identify data type mismatches (e.g., percentages vs decimals)
    - Identify missing required fields
    - Document all API integration issues found
  - **Phase 2: Fix API Integration Issues**
    - Fix field name mismatches across all components
    - Add conversion logic where needed (percentages ↔ decimals, dates, etc.)
    - Add missing required fields to forms and API calls
    - Update TypeScript types to match backend models
    - Test each API endpoint with real backend
  - **Phase 3: Mock Data Removal**
    - Search for hardcoded mock data in all components
    - Search for placeholder data (e.g., `data: []`, fake values)
    - Replace all mock data with real API calls
    - Remove commented-out mock data
  - **Phase 4: WebSocket Integration**
    - Implement WebSocket updates for all real-time data
    - Test WebSocket reconnection logic
    - Add flash animations for real-time updates
  - **Phase 5: Error Handling & Loading States**
    - Add proper error handling for all API failures
    - Add proper loading states (skeletons, spinners)
    - Add data refresh functionality
    - Add retry logic for failed requests
  - **Phase 6: Integration Testing**
    - Test all pages with real backend data
    - Test all API calls (GET, POST, PUT, DELETE)
    - Test error scenarios (API down, 422 errors, 500 errors)
    - Test WebSocket updates
    - Verify data displays correctly
  - **Acceptance**: All components show real data with correct API integration, no mock data, proper error handling
  - **Estimated time: 6-8 hours**

- [x] 7.15 Performance Optimization
  - **Phase 1: Critical Optimizations (2-3 hours)**
    - Implement route-based code splitting with React.lazy for all pages
    - Add Suspense boundaries with loading fallbacks
    - Configure Vite build optimization (chunk splitting, minification, tree shaking)
    - Add manual chunks for vendor libraries (react, ui, charts, tables, animations)
    - Enable terser minification with console/debugger removal
  - **Phase 2: Data Caching & API Optimization (2-3 hours)**
    - Create Zustand data cache store for account info, positions, orders
    - Implement stale-while-revalidate pattern (30s cache for account, 10s for positions/orders)
    - Reduce redundant API calls across pages (share cached data)
    - Combine related API calls where possible
    - Add request deduplication for parallel calls
  - **Phase 3: Component Optimization (2-3 hours)**
    - Lazy load heavy components (DataTable, Charts, Framer Motion animations)
    - Add React.memo to expensive components (MetricCard, DataTable, Card components)
    - Add useMemo for filtered/sorted data calculations
    - Add useCallback for event handlers passed to child components
    - Optimize WebSocket subscriptions (move to global context, reduce handlers)
  - **Phase 4: Loading States & UX (1-2 hours)**
    - Replace "Loading..." text with Skeleton components
    - Add progressive loading (show layout first, then data)
    - Implement optimistic updates for user actions
    - Add loading indicators for async operations
  - **Phase 5: Testing & Validation (1-2 hours)**
    - Run Lighthouse audit (target score: 85+)
    - Measure bundle size (target: <500KB initial, <1MB total)
    - Test on slow 3G network (target: <3s initial load)
    - Profile with React DevTools (identify remaining re-render issues)
    - Test page navigation speed (target: <500ms)
    - Verify 60 FPS during interactions and animations
  - **Reference**: See `PERFORMANCE_DIAGNOSTIC_REPORT.md` for detailed analysis
  - **Acceptance**: 
    - Initial page load < 2s on fast connection, < 3s on slow 3G
    - Page navigation < 500ms
    - Lighthouse score > 85
    - Bundle size < 500KB initial chunk
    - No janky scrolling or animations
    - Smooth real-time updates via WebSocket
  - **Estimated time: 8-12 hours**

- [ ] 7.16 Testing & Quality Assurance
  - Test all pages with real backend data
  - Test all user flows (view positions → close position, view orders → cancel order, etc.)
  - Test all filters and sorting
  - Test all real-time updates
  - Test error scenarios (API failures, WebSocket disconnection)
  - Test with different data volumes (0 positions, 100 positions, etc.)
  - Fix all bugs found during testing
  - **Acceptance**: All features work correctly with real data
  - **Estimated time: 6-8 hours**

- [ ] 7.17 Documentation & Handoff
  - Document new page structure and navigation
  - Document design system (colors, typography, components)
  - Document component API (props, usage examples)
  - Create user guide for new interface
  - Document any breaking changes
  - Update README with new features
  - **Acceptance**: Complete documentation for new frontend
  - **Estimated time: 3-4 hours**

## Phase 7 Notes

**Total Estimated Time**: 100-130 hours (4-5 weeks with 25-30 hours/week)

**Critical Success Factors**:
- No backend changes required (only frontend redesign)
- All components show real data from backend APIs
- Professional trading platform look and feel
- Clear information architecture
- Logical navigation structure
- Real-time updates via WebSocket
- Responsive design on all devices

**Risk Mitigation**:
- Incremental approach (one page at a time)
- Test each page before moving to next
- Keep old components until new ones are proven
- Can rollback individual pages if needed

**Dependencies**:
- Backend APIs must be stable and returning correct data
- WebSocket infrastructure must be working
- No changes to backend required

**Success Criteria**:
- Professional trading platform appearance
- Clear visibility into all trading activity
- Easy to understand what's happening
- Easy to take actions (close positions, cancel orders, etc.)
- No duplicate or redundant components
- Consistent visual design
- Fast and responsive
- Works on all devices
