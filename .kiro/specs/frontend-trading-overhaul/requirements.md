# Requirements Document

## Introduction

Comprehensive overhaul of the AlphaCent autonomous trading platform frontend (React/TypeScript/Vite). This feature addresses critical data integrity bugs, missing real-time capabilities, UX deficiencies, missing trading features, performance issues, and polish gaps identified in a full audit. The platform manages ~$415K in eToro DEMO capital across 117 symbols, so data accuracy and real-time reliability are paramount for trading decisions.

## Glossary

- **Dashboard**: The main Overview page (`OverviewNew.tsx`) showing P&L cards, equity curve, account balance, market regime, and health score
- **Risk_Page**: The Risk Management page (`RiskNew.tsx`) displaying VaR, drawdown, exposure, correlation, and risk limits
- **Portfolio_Page**: The Portfolio page (`PortfolioNew.tsx`) showing open/closed positions, pending closures, and fundamental alerts
- **Orders_Page**: The Orders page (`OrdersNew.tsx`) showing order history, execution quality, and pending closures
- **Analytics_Page**: The Analytics page (`AnalyticsNew.tsx`) showing performance metrics, strategy attribution, trade journal, and regime analysis
- **Strategies_Page**: The Strategies page (`StrategiesNew.tsx`) showing strategy listing, details, and lifecycle management
- **Header**: The top bar in `DashboardLayout.tsx` showing WS status, last synced time, sync button, and notifications
- **Sidebar**: The left navigation panel (`Sidebar.tsx`) with fixed 256px width showing nav links and badges
- **Polling_Service**: A periodic data refresh mechanism using `setInterval` or similar to keep page data fresh
- **Mock_Data_Generator**: Functions `generateRiskHistory()` and `generateCorrelationMatrix()` in `RiskNew.tsx` that produce random numbers as fallback data
- **Account_Balance**: The actual portfolio balance (~$415K) from the backend `AccountInfo.balance` field
- **Error_Boundary**: The `ErrorBoundary` React component that catches rendering errors and shows a fallback UI
- **WebSocket_Manager**: The `wsManager` singleton in `websocket.ts` managing real-time data subscriptions
- **API_Client**: The `apiClient` singleton in `api.ts` handling REST API calls with retry logic
- **Formatting_Utilities**: Functions `formatCurrency()`, `formatPercentage()`, `formatNumber()` in `lib/utils.ts`
- **Data_Management_Page**: The Data Management page (`DataManagementNew.tsx`) showing market data sync status, DB cache stats, monitoring processes, and API health
- **Trading_Cycle_Pipeline**: The `TradingCyclePipeline.tsx` component showing the 8-stage autonomous cycle progress with horizontal stepper, metrics summary, and cycle history
- **Autonomous_Page**: The Autonomous Trading page (`AutonomousNew.tsx`) with tabs for Control & Status, Strategy Lifecycle, Recent Activity, Signal Activity, and Performance
- **CycleSummaryCard**: The summary card shown after a cycle completes in the Trading_Cycle_Pipeline, displaying aggregated metrics from all stages

## Requirements

### Requirement 1: Fix Risk Page Hardcoded Values and Portfolio Size

**User Story:** As a trader, I want the Risk page to show actual calculated risk metrics from my portfolio, so that I can make informed risk management decisions based on real data.

#### Acceptance Criteria

1. WHEN the Risk_Page loads, THE Risk_Page SHALL calculate Position Size percentage from actual position values divided by Account_Balance
2. WHEN the Risk_Page loads, THE Risk_Page SHALL calculate Portfolio Exposure percentage from actual total exposure divided by Account_Balance
3. WHEN the Risk_Page calculates risk status via `getRiskStatus()`, THE Risk_Page SHALL use the actual Account_Balance from the backend instead of the hardcoded value of 100000
4. WHEN Account_Balance is unavailable, THE Risk_Page SHALL display "Calculating..." as the risk status message instead of computing with a fallback default

### Requirement 2: Eliminate Silent Mock Data Fallbacks on Risk Page

**User Story:** As a trader, I want to know when risk data is unavailable rather than seeing fabricated numbers, so that I do not make trading decisions based on fake data.

#### Acceptance Criteria

1. WHEN the backend fails to return risk history data, THE Risk_Page SHALL display a "Data unavailable" message in the risk history chart area instead of calling the Mock_Data_Generator
2. WHEN the backend fails to return correlation matrix data, THE Risk_Page SHALL display a "Data unavailable" message in the correlation matrix area instead of calling the Mock_Data_Generator
3. WHEN any risk data section shows "Data unavailable", THE Risk_Page SHALL display a retry button that allows the trader to re-fetch that specific data section
4. THE Risk_Page SHALL remove the `generateRiskHistory()` and `generateCorrelationMatrix()` functions entirely

### Requirement 3: Add Periodic Auto-Refresh Polling Across All Pages

**User Story:** As a trader, I want dashboard data to refresh automatically at regular intervals, so that I see up-to-date information without manually clicking Refresh during active trading hours.

#### Acceptance Criteria

1. THE Dashboard SHALL poll for updated data every 30 seconds while the page is visible
2. THE Portfolio_Page SHALL poll for updated position and account data every 15 seconds while the page is visible
3. THE Orders_Page SHALL poll for updated order data every 15 seconds while the page is visible
4. THE Risk_Page SHALL poll for updated risk metrics every 60 seconds while the page is visible
5. THE Analytics_Page SHALL poll for updated analytics data every 120 seconds while the page is visible
6. THE Strategies_Page SHALL poll for updated strategy data every 60 seconds while the page is visible
7. WHEN the browser tab is not visible (document.hidden is true), THE Polling_Service SHALL pause all polling intervals
8. WHEN the browser tab becomes visible again, THE Polling_Service SHALL immediately fetch fresh data and resume polling
9. WHEN a WebSocket reconnection occurs, THE Polling_Service SHALL immediately fetch fresh data on all active pages

### Requirement 4: Fix Optimistic Auth with Proper Session Validation

**User Story:** As a trader, I want the app to validate my session before showing interactive content, so that I do not experience silent API failures when my session has expired.

#### Acceptance Criteria

1. WHEN the app loads with a cached username in localStorage, THE App SHALL display a lightweight loading indicator while validating the session in the background
2. WHEN background session validation determines the session is invalid, THE App SHALL redirect to the login page within 2 seconds of detection without allowing further API interactions
3. WHEN background session validation determines the session is invalid, THE App SHALL display a toast notification informing the trader that the session has expired
4. WHILE session validation is in progress, THE App SHALL disable navigation and data-fetching actions that would result in authenticated API calls

### Requirement 5: Add Real-Time P&L Ticker in Header

**User Story:** As a trader, I want to see my current portfolio P&L in the header bar at all times, so that I can monitor my performance without navigating to a specific page.

#### Acceptance Criteria

1. THE Header SHALL display the current daily P&L value formatted using Formatting_Utilities
2. THE Header SHALL display the current daily P&L percentage alongside the absolute value
3. THE Header SHALL color the P&L display green when positive and red when negative
4. WHEN a position update is received via WebSocket_Manager, THE Header SHALL update the P&L display within 2 seconds
5. THE Header SHALL poll for updated P&L data every 30 seconds as a fallback when WebSocket is disconnected

### Requirement 6: Surface Pending Closures and Fundamental Alerts as Persistent Banners

**User Story:** As a trader, I want pending closures and fundamental alerts to be prominently visible at the top of the Portfolio page, so that I do not miss urgent position actions buried in tabs.

#### Acceptance Criteria

1. WHEN there are positions flagged for pending closure, THE Portfolio_Page SHALL display a persistent warning banner at the top of the page showing the count and a summary of pending closures
2. WHEN there are fundamental deterioration alerts, THE Portfolio_Page SHALL display a persistent alert banner at the top of the page showing the count and a summary of flagged positions
3. WHEN the trader clicks on a pending closure banner item, THE Portfolio_Page SHALL scroll to or highlight the relevant position in the positions table
4. WHEN the trader dismisses or approves all pending closures, THE Portfolio_Page SHALL remove the pending closure banner
5. WHEN the trader dismisses or closes all fundamental alert positions, THE Portfolio_Page SHALL remove the fundamental alert banner

### Requirement 7: Add Timezone Indicators to All Timestamps

**User Story:** As a trader, I want all timestamps to include timezone information, so that I can correctly interpret when events occurred relative to market hours.

#### Acceptance Criteria

1. THE Dashboard SHALL display all timestamps with a timezone abbreviation (e.g., "EST", "UTC")
2. THE Portfolio_Page SHALL display position opened_at and closed_at timestamps with timezone abbreviation
3. THE Orders_Page SHALL display order created_at and updated_at timestamps with timezone abbreviation
4. THE Analytics_Page SHALL display trade journal entry timestamps with timezone abbreviation
5. THE Risk_Page SHALL display risk alert timestamps with timezone abbreviation

### Requirement 8: Standardize P&L and Percentage Formatting

**User Story:** As a trader, I want all monetary and percentage values to be formatted consistently across the platform, so that I can quickly read and compare numbers without confusion.

#### Acceptance Criteria

1. THE Dashboard SHALL use `formatCurrency()` from Formatting_Utilities for all monetary P&L values instead of inline `.toFixed(2)` calls
2. THE Portfolio_Page SHALL use `formatPercentage()` from Formatting_Utilities for all percentage values
3. THE Orders_Page SHALL use `formatCurrency()` from Formatting_Utilities for all monetary values
4. THE Analytics_Page SHALL use Formatting_Utilities consistently for all monetary and percentage displays
5. THE Risk_Page SHALL use Formatting_Utilities consistently for all monetary and percentage displays

### Requirement 9: Add Strategy Name Tooltip with Proper Styling

**User Story:** As a trader, I want to see full strategy names when they are truncated in table columns, so that I can identify strategies without guessing.

#### Acceptance Criteria

1. WHEN a strategy name is truncated in any DataTable column, THE DataTable SHALL display a styled Radix UI tooltip showing the full strategy name on hover
2. THE tooltip SHALL appear within 300ms of hover and remain visible while the cursor is over the truncated text
3. THE tooltip SHALL use the application's dark theme styling consistent with other Radix UI tooltips in the app

### Requirement 10: Add Data Caching Between Tab Switches

**User Story:** As a trader, I want analytics data to be cached when switching between tabs, so that I do not trigger redundant API calls and experience faster tab transitions.

#### Acceptance Criteria

1. WHEN the trader switches away from a tab on the Analytics_Page, THE Analytics_Page SHALL retain the fetched data in component state
2. WHEN the trader switches back to a previously loaded tab on the Analytics_Page, THE Analytics_Page SHALL display the cached data immediately without re-fetching
3. WHEN the trader clicks the Refresh button, THE Analytics_Page SHALL invalidate all cached data and re-fetch from the backend
4. WHEN cached data is older than 5 minutes, THE Analytics_Page SHALL automatically re-fetch when the tab becomes active

### Requirement 11: Standardize Loading States Across All Pages

**User Story:** As a trader, I want consistent loading indicators across all pages, so that I always know when data is being fetched.

#### Acceptance Criteria

1. THE Dashboard SHALL display a skeleton loading animation while initial data is being fetched
2. THE Portfolio_Page SHALL display a skeleton loading animation while initial data is being fetched
3. THE Orders_Page SHALL display a skeleton loading animation while initial data is being fetched
4. THE Risk_Page SHALL display a skeleton loading animation while initial data is being fetched
5. THE Analytics_Page SHALL display a skeleton loading animation while initial data is being fetched
6. THE Strategies_Page SHALL display a skeleton loading animation while initial data is being fetched
7. WHEN a page is refreshing (not initial load), THE page SHALL display a subtle refresh indicator without replacing the existing content

### Requirement 12: Improve Error Messages with Specific Context

**User Story:** As a trader, I want error messages to tell me specifically what failed, so that I can understand the issue and take appropriate action.

#### Acceptance Criteria

1. WHEN an API call fails on any page, THE page SHALL display an error message that includes the name of the data that failed to load (e.g., "Failed to load positions" instead of "Failed to load data")
2. WHEN an API call fails with a network error, THE page SHALL indicate that the issue is a network connectivity problem
3. WHEN an API call fails with a server error (5xx), THE page SHALL indicate that the backend service encountered an error
4. WHEN an API call fails, THE page SHALL provide a retry button specific to the failed data section

### Requirement 13: Add Confirmation Dialogs for Destructive Actions

**User Story:** As a trader, I want confirmation dialogs before destructive actions like closing positions or cancelling orders, so that I do not accidentally execute irreversible operations.

#### Acceptance Criteria

1. WHEN the trader initiates a position close action, THE Portfolio_Page SHALL display a confirmation dialog showing the position symbol, quantity, and current P&L before executing
2. WHEN the trader initiates an order cancellation, THE Orders_Page SHALL display a confirmation dialog showing the order details before executing
3. WHEN the trader initiates a bulk close of multiple positions, THE Portfolio_Page SHALL display a confirmation dialog listing all affected positions and total P&L impact
4. THE confirmation dialog SHALL require explicit confirmation (click "Confirm" button) and provide a "Cancel" option

### Requirement 14: Add Per-Page Error Boundaries

**User Story:** As a trader, I want individual page crashes to be contained without taking down the entire application, so that I can continue using other pages if one page encounters an error.

#### Acceptance Criteria

1. THE App SHALL wrap each page route in its own Error_Boundary component
2. WHEN a page-level Error_Boundary catches an error, THE Error_Boundary SHALL display an error message specific to that page with a "Reload Page" button
3. WHEN a page-level Error_Boundary catches an error, THE Sidebar and Header SHALL remain functional and navigable
4. THE App SHALL retain the top-level Error_Boundary as a final fallback

### Requirement 15: Add Watchlist / Market Overview Page

**User Story:** As a trader, I want a market overview showing current prices and daily changes for symbols in the trading universe, so that I can monitor market conditions across all 117 symbols.

#### Acceptance Criteria

1. THE App SHALL include a Watchlist page accessible from the Sidebar navigation
2. THE Watchlist page SHALL display a table of symbols from the trading universe with columns for symbol, current price, daily change (absolute), daily change (percentage), and volume
3. THE Watchlist page SHALL support filtering by asset class (stocks, ETFs, forex, indices, commodities, crypto)
4. THE Watchlist page SHALL support text search to filter symbols by name
5. WHEN market data is received via WebSocket_Manager, THE Watchlist page SHALL update the corresponding symbol row in real-time
6. THE Watchlist page SHALL poll for market data every 30 seconds as a fallback

### Requirement 16: Add Strategy Comparison View

**User Story:** As a trader, I want to compare two strategies side-by-side, so that I can evaluate relative performance and make informed allocation decisions.

#### Acceptance Criteria

1. THE Strategies_Page SHALL include a "Compare" action that allows the trader to select two strategies for comparison
2. WHEN two strategies are selected for comparison, THE Strategies_Page SHALL display a side-by-side view showing key metrics: total return, Sharpe ratio, max drawdown, win rate, total trades, and allocation percentage
3. THE comparison view SHALL highlight which strategy performs better on each metric using color coding

### Requirement 17: Add Regime Change Notifications

**User Story:** As a trader, I want to be notified when the market regime changes, so that I can review my portfolio positioning for the new market conditions.

#### Acceptance Criteria

1. WHEN the market regime changes (detected via WebSocket_Manager or polling), THE App SHALL display a toast notification indicating the previous regime and the new regime
2. WHEN a regime change notification is displayed, THE notification SHALL include a link to navigate to the Dashboard to review the current regime details
3. THE App SHALL store the last known regime in localStorage to detect changes across page reloads

### Requirement 18: Add Manual Order Placement Form

**User Story:** As a trader, I want to place manual orders from the UI, so that I can execute trades outside of the autonomous system when needed.

#### Acceptance Criteria

1. THE Orders_Page SHALL include an "New Order" button that opens an order entry form
2. THE order entry form SHALL include fields for: symbol (searchable dropdown from trading universe), side (BUY/SELL), order type (MARKET/LIMIT), quantity, and price (for LIMIT orders)
3. WHEN the trader submits a valid order, THE Orders_Page SHALL send the order to the backend via API_Client and display a success or failure toast
4. WHEN the trader submits an order with invalid inputs, THE order entry form SHALL display inline validation errors
5. THE order entry form SHALL display a confirmation step showing order details before final submission

### Requirement 19: Add Execution Quality Dashboard

**User Story:** As a trader, I want a dedicated view for execution quality metrics including slippage tracking, so that I can monitor how well orders are being filled.

#### Acceptance Criteria

1. THE Orders_Page SHALL include an "Execution Quality" tab displaying aggregate slippage metrics, fill rate, and average fill time
2. THE Execution Quality tab SHALL display a chart showing slippage distribution across recent orders
3. THE Execution Quality tab SHALL display per-order slippage and fill time in a sortable table
4. WHEN execution quality data is unavailable from the backend, THE Execution Quality tab SHALL display a "Data unavailable" message

### Requirement 20: Ensure Sidebar Badges Update Reliably in Real-Time

**User Story:** As a trader, I want sidebar badges (pending closures count, queued orders count) to update reliably, so that I always see accurate counts without needing to refresh.

#### Acceptance Criteria

1. WHEN a pending closure event is received via WebSocket_Manager, THE Sidebar badge for Portfolio SHALL update the count within 2 seconds
2. WHEN an order status changes via WebSocket_Manager, THE Sidebar badge for Orders SHALL update the queued count within 2 seconds
3. THE DashboardLayout SHALL poll for badge counts every 30 seconds as a fallback when WebSocket events are missed

### Requirement 21: Fix Trading Cycle Pipeline Stage Metric Mapping

**User Story:** As a trader, I want the Trading Cycle Pipeline to accurately display the correct metrics for each stage, so that I can trust the cycle results I am seeing.

#### Acceptance Criteria

1. THE CycleSummaryCard SHALL read retirement count from the `cleanup_retirement` stage metrics (field: `retired`), not from `signal_generation`
2. THE CycleSummaryCard SHALL read signals count from the `signal_generation` stage metrics (field: `signals_generated`), not from `order_submission`
3. THE CycleSummaryCard SHALL read orders count from the `order_submission` stage metrics (field: `orders_submitted`)
4. THE Trading_Cycle_Pipeline SHALL map the backend's `approved` field to display as "Activated" in both the metrics summary and the CycleSummaryCard
5. THE Trading_Cycle_Pipeline SHALL display the `total_active` count from the activation stage to show total active strategies after the cycle
6. WHEN any metric value is null or undefined, THE Trading_Cycle_Pipeline SHALL display "—" instead of 0

### Requirement 22: Reorganize Autonomous Page Layout

**User Story:** As a trader, I want the Autonomous Trading page to be well-organized with the most important information prominently placed, so that I can quickly assess system status and monitor cycle progress.

#### Acceptance Criteria

1. THE Autonomous_Page SHALL display the Trading_Cycle_Pipeline at the TOP of the Control & Status tab, immediately below the status badges, so it is visible without scrolling
2. THE Autonomous_Page SHALL remove the "Quick Actions" card (it duplicates sidebar navigation)
3. THE Autonomous_Page SHALL group the Control Panel and Scheduled Execution into a single "Controls" section
4. THE Autonomous_Page SHALL group System Status and Research Filters into a single "System" section
5. THE Autonomous_Page SHALL display the Controls section and System section side-by-side in a 2-column grid layout on desktop
6. THE Autonomous_Page SHALL display key metrics (Active Strategies, Open Positions, Last Signal, Market Regime) as a compact metric row above the pipeline, not buried inside a card

### Requirement 23: Enhance Data Management Page with Trader-Relevant Features

**User Story:** As a trader, I want the Data Management page to show me data quality issues and coverage gaps, so that I can ensure my trading decisions are based on complete and accurate data.

#### Acceptance Criteria

1. THE Data_Management_Page SHALL display a "Data Quality" section showing the most recent data quality report from the backend (if available via `GET /api/data/quality-report` or similar endpoint)
2. THE Data_Management_Page SHALL display a "Symbol Coverage" section showing which symbols have stale data (older than 2 hours for hourly, older than 1 day for daily) with a count and list
3. THE Data_Management_Page SHALL allow the trader to trigger a data sync for a specific symbol or asset class, not just a full sync
4. THE Data_Management_Page SHALL display a warning banner when more than 10% of symbols have stale data
5. THE Data_Management_Page SHALL show the FMP API usage with a visual progress bar and remaining calls count prominently (currently buried in the monitoring section)

### Requirement 24: Fix Autonomous Page Cycle Counting and Status Display

**User Story:** As a trader, I want cycle statistics to clearly distinguish between the last cycle's results and cumulative totals, so that I can accurately assess each cycle's effectiveness.

#### Acceptance Criteria

1. THE Autonomous_Page SHALL display "Last Cycle" metrics separately from "Cumulative" metrics in the System Status section
2. THE Autonomous_Page SHALL label cumulative counts as "Total" (e.g., "Total Activated: 47") and last cycle counts as "Last Cycle" (e.g., "Last Cycle Activated: 3")
3. THE Autonomous_Page SHALL source last cycle metrics from the most recent entry in cycle history (via `getAutonomousCycles`), not from `autonomousStatus.cycle_stats`
4. THE Autonomous_Page SHALL display the last cycle's duration, proposals generated, backtest pass rate, and net activations (activated minus retired)

### Requirement 25: Improve Data Fetching Consistency and Error Handling Across All Pages

**User Story:** As a trader, I want consistent and transparent data loading behavior across all pages, so that I always know what data loaded successfully and what failed.

#### Acceptance Criteria

1. WHEN any primary data fetch fails on any page, THE page SHALL display an inline error state for that data section with a retry button, not just a toast
2. WHEN secondary data fetches fail (pending closures, fundamental alerts, execution quality), THE page SHALL display a subtle "Failed to load" indicator in the relevant section instead of silently returning empty data
3. ALL pages SHALL use a consistent pattern for parallel data fetching: primary data in `Promise.all` (blocks render), secondary data in separate non-blocking calls with individual error handling
4. THE Portfolio_Page SHALL show a loading indicator for the Pending Closures and Fundamental Alerts sections while they are being fetched in the background

### Requirement 26: Improve P&L Calculations and Presentation Accuracy

**User Story:** As a trader, I want P&L calculations and labels to be accurate and not misleading, so that I can trust the numbers I see on every page.

#### Acceptance Criteria

1. THE Portfolio_Page SHALL label the unrealized P&L metric as "Unrealized P&L" not "Daily P&L" or "Today's P&L"
2. THE Portfolio_Page SHALL label the current-positions-in-profit metric as "Positions in Profit" not "Win Rate" (win rate implies closed trade statistics)
3. THE Portfolio_Page SHALL display actual win rate from closed positions (wins / total closed) if closed position data is available, labeled as "Win Rate (Closed)"
4. THE Dashboard SHALL clearly label each P&L period card (Today, Week, Month, All-Time) and indicate whether the values are realized, unrealized, or combined
5. ALL pages displaying P&L percentages SHALL use the same base for calculation (equity or balance) and indicate which base is used

### Requirement 27: Add Data Freshness Indicators to Key Pages

**User Story:** As a trader, I want to see when each page's data was last refreshed, so that I know how current the information I am looking at is.

#### Acceptance Criteria

1. EACH page SHALL display a "Data as of: [timestamp]" indicator near the page header showing when the page data was last fetched
2. WHEN page data is older than 2 minutes, THE indicator SHALL change color to amber as a staleness warning
3. WHEN page data is older than 5 minutes, THE indicator SHALL change color to red and display "Stale data" warning
4. THE indicator SHALL update automatically when data is refreshed via polling, manual refresh, or WebSocket-triggered refresh
