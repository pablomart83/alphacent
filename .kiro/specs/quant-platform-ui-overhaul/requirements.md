# Requirements Document

## Introduction

AlphaCent is an autonomous quant trading platform managing ~$465K equity across 297 symbols with ~101 active strategies. The current React 19 frontend suffers from inconsistent page layouts, low information density, missing benchmark comparisons, static charts, and no persistent summary bar. This UI/UX overhaul brings the frontend to institutional-grade standards inspired by QuantConnect, Bloomberg Terminal, Bloomberg PORT, pyfolio tear sheets, and TradingView — prioritizing data density, benchmark visibility, chart interactivity, advanced analytics, and visual consistency across all 11 pages. The overhaul includes rolling performance statistics, performance attribution analysis, drawdown and return distribution tear sheets, position-level drill-down analytics, a command palette for rapid navigation, PDF tear sheet export, multi-timeframe performance comparison, system observability for all backend services, strategy lifecycle intelligence exposing autonomous decision-making rationale, data pipeline monitoring for all 297 symbols across multiple data sources, execution quality and transaction cost analysis surfacing slippage and implementation shortfall metrics, and a comprehensive audit trail providing full traceability of every trading decision from signal generation through execution.

## Glossary

- **Dashboard**: The main application shell comprising the Sidebar, Header, Global_Summary_Bar, and page content area
- **Global_Summary_Bar**: A persistent horizontal bar rendered below the Header on every authenticated page, displaying key portfolio metrics updated in real-time
- **Equity_Curve_Chart**: An interactive time-series chart displaying portfolio equity over time with optional benchmark overlay and synchronized drawdown sub-chart
- **SPY_Benchmark**: The SPDR S&P 500 ETF Trust price series used as the default equity benchmark, normalized to the same starting value as the portfolio equity curve
- **Alpha_Line**: A derived data series showing the difference between portfolio cumulative return and SPY cumulative return over the same period
- **Period_Selector**: A set of clickable time-range buttons (1W, 1M, 3M, 6M, 1Y, ALL) that filter time-series chart data
- **Design_System**: The standardized set of colors, spacing, typography, card styles, chart themes, and table patterns applied consistently across all pages
- **Metric_Grid**: A dense, multi-column grid of key performance indicators using compact cards with consistent sizing
- **Interactive_Chart**: A chart component supporting zoom, pan, crosshair tooltip, and period selection
- **Skeleton_Loader**: A placeholder UI element that mimics the shape of content while data is loading, preventing layout shift
- **Strategy_Pipeline**: A visual representation of strategy lifecycle stages: proposed → backtested → active → retired
- **Correlation_Matrix**: A heatmap visualization showing pairwise correlation coefficients between open positions or asset classes
- **WebSocket_Feed**: The real-time data stream from the backend providing live updates for positions, orders, P&L, and system events
- **Chart_Crosshair**: An interactive overlay on charts that follows the cursor and displays exact data values at the hovered point
- **Rolling_Statistics**: Time-series of performance metrics (Sharpe, beta, alpha, volatility) calculated over a sliding window of configurable length (30d, 60d, 90d)
- **Performance_Attribution**: Decomposition of portfolio returns into allocation effect (sector weight decisions), selection effect (stock picking within sectors), and interaction effect
- **Underwater_Plot**: An area chart showing the portfolio's percentage drawdown from its running peak over time, visualizing time spent "underwater"
- **Probabilistic_Sharpe_Ratio**: A statistical measure representing the probability that the estimated Sharpe ratio exceeds a benchmark Sharpe ratio, accounting for estimation uncertainty
- **Command_Palette**: A searchable overlay triggered by Ctrl+K (Cmd+K on Mac) for quick navigation to symbols, strategies, pages, and actions via fuzzy search
- **Tear_Sheet**: A standardized PDF report summarizing portfolio performance metrics, equity curve, drawdown chart, monthly returns heatmap, and key statistics suitable for investor communication
- **Risk_Contribution**: The percentage of total portfolio risk (measured by VaR or volatility) attributable to each individual position
- **Asset_Plot**: A price chart for an individual security annotated with buy/sell order events (green arrows for buys, red arrows for sells)
- **Monthly_Returns_Heatmap**: A grid visualization with months as columns and years as rows, color-coded by monthly return magnitude (green for positive, red for negative)
- **Return_Distribution_Histogram**: A bar chart showing the frequency distribution of daily returns with a normal distribution overlay, annotated with skew and kurtosis values
- **Multi_Timeframe_View**: A compact display showing portfolio returns across multiple time horizons (1D, 1W, 1M, 3M, 6M, YTD, 1Y, ALL) side by side
- **Circuit_Breaker**: A fault-tolerance mechanism that monitors eToro API call failures per category (orders, positions, market_data) and automatically blocks requests after consecutive failures, transitioning through CLOSED → OPEN → HALF_OPEN states
- **Monitoring_Service**: The 24/7 background service that keeps the database synchronized with eToro, manages trailing stops, partial exits, pending closures, and daily maintenance tasks
- **Trading_Scheduler**: The background service that generates trading signals from active strategies and coordinates order execution, triggered by price sync completion
- **Autonomous_Cycle**: The weekly strategy lifecycle process that proposes, validates, backtests, and activates new trading strategies through 8 sequential stages
- **Template_Performance**: Historical performance metrics aggregated across all strategies that used a specific strategy template
- **Conviction_Score**: A composite score combining signal strength, fundamental data quality, regime fit, and asset-class-specific factors (carry bias for forex, halving cycle for crypto) that determines signal priority
- **Data_Quality_Score**: A 0-100 score assigned to each symbol's market data based on checks for gaps, price jumps, stale data, null values, and high-low inversions
- **Blacklist**: A time-limited block on specific template+symbol combinations that have historically produced zero trades or been rejected multiple times at activation
- **System_Health_Page**: A dedicated page or Settings tab displaying real-time health and status of all backend services, circuit breakers, and API integrations
- **Walk_Forward_Pass_Rate**: The percentage of proposed strategies that pass walk-forward backtesting validation in a given Autonomous_Cycle
- **Idle_Demotion**: The automatic transition of a DEMO strategy back to BACKTESTED status when the strategy has no open positions and no pending orders
- **Transaction_Cost_Analysis**: Quantitative analysis of execution quality measuring slippage, implementation shortfall, market impact, and fill rates across all trades
- **Implementation_Shortfall**: The difference between the decision price (when the signal was generated) and the actual execution price, measuring the total cost of trading including market impact and timing
- **Audit_Trail**: A chronological record of every system decision including signal generation, risk validation, order execution, strategy lifecycle events, and risk limit breaches, providing full traceability for any trade

## Requirements

### Requirement 1: SPY Benchmark Overlay on Equity Curve

**User Story:** As a portfolio manager, I want to see my equity curve plotted alongside the SPY benchmark, so that I can evaluate whether my portfolio is generating alpha relative to the market.

#### Acceptance Criteria

1. WHEN the Overview page loads, THE Equity_Curve_Chart SHALL display the portfolio equity line and the SPY_Benchmark line on the same chart, both normalized to 100 at the start of the selected period
2. WHEN the user hovers over the Equity_Curve_Chart, THE Chart_Crosshair SHALL display the portfolio equity value, SPY value, and alpha (portfolio return minus SPY return) at the hovered date
3. THE Equity_Curve_Chart SHALL render an Alpha_Line as a shaded area between the portfolio line and the SPY_Benchmark line, colored green (#22c55e) when portfolio outperforms and red (#ef4444) when it underperforms
4. WHEN the user selects a period from the Period_Selector (1W, 1M, 3M, 6M, 1Y, ALL), THE Equity_Curve_Chart SHALL re-normalize both lines to 100 at the start of the newly selected period and update the chart within 500ms
5. THE Equity_Curve_Chart SHALL display a synchronized drawdown sub-chart below the equity chart that shares the same time axis and Period_Selector state
6. IF the SPY benchmark data is unavailable, THEN THE Equity_Curve_Chart SHALL display only the portfolio equity line and show an informational badge stating "Benchmark unavailable"

### Requirement 2: Global Summary Bar

**User Story:** As a trader, I want to see key portfolio metrics persistently on every page, so that I can monitor portfolio health without navigating back to the Overview.

#### Acceptance Criteria

1. THE Global_Summary_Bar SHALL be rendered below the Header and above the page content on every authenticated page
2. THE Global_Summary_Bar SHALL display: Total Equity, Daily P&L (absolute and percentage), Open Positions count, Active Strategies count, Current Market Regime, and System Health score
3. WHEN the WebSocket_Feed delivers a position or account update, THE Global_Summary_Bar SHALL update the affected metrics within 2 seconds without a full page refresh
4. THE Global_Summary_Bar SHALL use green (#22c55e) text for positive P&L values and red (#ef4444) text for negative P&L values
5. WHILE the WebSocket_Feed is disconnected, THE Global_Summary_Bar SHALL display a yellow warning indicator next to the System Health metric
6. THE Global_Summary_Bar SHALL occupy no more than 48 pixels in height to preserve vertical space for page content

### Requirement 3: Overview Page Redesign

**User Story:** As a portfolio manager, I want the Overview page to present a comprehensive command centre layout, so that I can assess portfolio status at a glance.

#### Acceptance Criteria

1. THE Overview page SHALL render the Equity_Curve_Chart with SPY_Benchmark overlay as a full-width hero section at the top of the page
2. THE Overview page SHALL render a 4-column Metric_Grid below the hero section displaying: Total Equity, Daily P&L ($ and %), Sharpe Ratio (30d), and Max Drawdown
3. THE Overview page SHALL render a 2-column layout below the Metric_Grid with position summary by asset class on the left and recent trades (last 10) on the right
4. THE Overview page SHALL render a Strategy_Pipeline visualization below the 2-column layout showing counts for each lifecycle stage (proposed, backtested, active, retired) with clickable navigation to the Strategies page
5. WHEN the user clicks a stage in the Strategy_Pipeline, THE Dashboard SHALL navigate to the Strategies page filtered by that lifecycle stage

### Requirement 4: Consistent Design System

**User Story:** As a user, I want all pages to share a consistent visual language, so that the platform feels cohesive and professional.

#### Acceptance Criteria

1. THE Design_System SHALL define a standard Card component with consistent padding (16px), border radius (8px), border color (var(--color-dark-border)), and background color (var(--color-dark-surface)) used across all pages
2. THE Design_System SHALL enforce consistent color coding: green (#22c55e) for positive values, red (#ef4444) for negative values, blue (#3b82f6) for neutral/informational values, and yellow (#eab308) for warnings
3. THE Design_System SHALL define a standard chart theme with dark background (#111827), grid lines (#374151), axis labels in gray (#9ca3af at 10px font-mono), and consistent tooltip styling across all charts
4. THE Design_System SHALL define a standard table style with alternating row backgrounds, sortable column headers indicated by sort icons, and consistent pagination controls
5. THE Design_System SHALL define a standard page layout pattern: page title with description at top, primary content area, and consistent spacing (24px gap between sections)
6. THE Design_System SHALL define font usage: mono font (font-mono) for all numeric values and data, sans font for labels and descriptions

### Requirement 5: Chart Interactivity

**User Story:** As a trader, I want interactive charts with zoom, pan, and crosshair, so that I can analyze time-series data at different granularities.

#### Acceptance Criteria

1. THE Interactive_Chart component SHALL support mouse-wheel zoom on the time axis, allowing the user to zoom into a specific date range
2. THE Interactive_Chart component SHALL support click-and-drag panning along the time axis when zoomed in
3. WHEN the user hovers over an Interactive_Chart, THE Chart_Crosshair SHALL display a vertical line at the cursor position and a tooltip showing the exact date and all data series values at that point
4. THE Interactive_Chart component SHALL render a Period_Selector with options 1W, 1M, 3M, 6M, 1Y, ALL above the chart area
5. WHEN the user selects a period from the Period_Selector, THE Interactive_Chart SHALL filter the displayed data to the selected time range and re-render within 500ms
6. THE Interactive_Chart component SHALL be used for all time-series charts across the platform: equity curves, drawdown charts, strategy performance charts, and P&L history charts

### Requirement 6: Page-Specific Improvements

**User Story:** As a portfolio manager, I want each page to surface the most actionable data visualizations for its domain, so that I can make informed decisions faster.

#### Acceptance Criteria

1. THE Strategies page SHALL display a mini equity curve (sparkline) for each active strategy in the strategy list, rendered inline within the strategy row
2. THE Strategies page SHALL support sorting the strategy list by Sharpe ratio, total return, number of trades, and win rate via clickable column headers
3. THE Risk page SHALL display a Correlation_Matrix heatmap showing pairwise correlations between the top 20 open positions by allocation size
4. THE Risk page SHALL display a sector exposure pie chart showing allocation percentage by sector with P&L color coding per sector slice
5. THE Orders page SHALL display an order flow timeline visualization showing order events (placed, filled, cancelled) on a horizontal time axis for the last 7 days
6. THE Autonomous page SHALL display a cycle pipeline visualization showing the autonomous trading cycle stages (propose → walk-forward validate → backtest → activate) with counts and status indicators per stage

### Requirement 7: Loading States and Skeleton Loaders

**User Story:** As a user, I want smooth loading transitions when navigating between pages, so that the interface feels responsive and polished.

#### Acceptance Criteria

1. WHEN a page begins loading data, THE Dashboard SHALL display Skeleton_Loader placeholders that match the shape and size of the expected content within 100ms of navigation
2. THE Skeleton_Loader SHALL animate with a subtle shimmer effect to indicate loading is in progress
3. WHEN data arrives for a section, THE Dashboard SHALL transition from the Skeleton_Loader to the actual content with a fade-in animation lasting 200ms
4. WHILE navigating between pages, THE Dashboard SHALL pre-fetch data for the target page during the route transition to minimize visible loading time
5. IF data fetching fails after 10 seconds, THEN THE Dashboard SHALL replace the Skeleton_Loader with an error state showing a retry button and a descriptive error message

### Requirement 8: Mobile and Responsive Layout

**User Story:** As a user accessing the platform from a tablet or smaller screen, I want the layout to adapt gracefully, so that I can monitor my portfolio on any device.

#### Acceptance Criteria

1. WHEN the viewport width is below 1024px, THE Sidebar SHALL collapse to an icon-only mode (64px wide) with a toggle button to expand
2. WHEN the viewport width is below 768px, THE Metric_Grid SHALL reflow from 4 columns to 2 columns, maintaining consistent card sizing
3. WHEN the viewport width is below 768px, THE Global_Summary_Bar SHALL display only Total Equity and Daily P&L, with remaining metrics accessible via a horizontal scroll or expand toggle
4. THE Design_System SHALL ensure all charts maintain a minimum height of 200px on mobile viewports to remain readable
5. WHEN the viewport width is below 640px, THE 2-column layouts SHALL stack vertically into a single column

### Requirement 9: Real-Time WebSocket Updates

**User Story:** As a trader, I want live data updates pushed to the UI without manual refresh, so that I see current portfolio state at all times.

#### Acceptance Criteria

1. WHEN the WebSocket_Feed delivers a position update event, THE Global_Summary_Bar and the active page SHALL update affected metrics within 2 seconds
2. WHEN the WebSocket_Feed delivers an order update event, THE Orders page (if active) SHALL update the order list and the Global_Summary_Bar SHALL update the pending orders count
3. WHILE the WebSocket_Feed is connected, THE Dashboard SHALL not poll the REST API for data that is covered by WebSocket events (positions, orders, account info)
4. IF the WebSocket_Feed disconnects, THEN THE Dashboard SHALL fall back to REST API polling at 30-second intervals and display a reconnection indicator in the Global_Summary_Bar
5. WHEN the WebSocket_Feed reconnects after a disconnection, THE Dashboard SHALL perform a full data refresh to synchronize state and resume WebSocket-driven updates

### Requirement 10: Rolling Statistics and Advanced Performance Metrics

**User Story:** As a portfolio manager, I want to see rolling performance metrics over time, so that I can evaluate whether my strategy's risk-adjusted returns are statistically significant and how they evolve across market conditions.

#### Acceptance Criteria

1. THE Analytics page SHALL display a "Rolling Statistics" tab containing interactive time-series charts for Rolling Sharpe Ratio, Rolling Beta vs SPY, Rolling Alpha, and Rolling Volatility
2. WHEN the Rolling Statistics tab loads, THE Analytics page SHALL render each rolling metric as an Interactive_Chart with Period_Selector support (1M, 3M, 6M, 1Y, ALL)
3. THE Rolling Statistics charts SHALL support configurable rolling window sizes of 30 days, 60 days, and 90 days, selectable via a window-size toggle displayed above the charts
4. WHEN the user changes the rolling window size, THE Analytics page SHALL recalculate and re-render all rolling metric charts within 1 second
5. THE Analytics page SHALL display the Probabilistic_Sharpe_Ratio as a prominent metric card above the rolling charts, showing the probability (0-100%) that the portfolio Sharpe ratio exceeds 0.5
6. THE Analytics page SHALL display Information Ratio, Treynor Ratio, and Tracking Error as metric cards alongside the Probabilistic_Sharpe_Ratio
7. THE Rolling Statistics charts SHALL use the same Interactive_Chart component defined in Requirement 5, supporting zoom, pan, and Chart_Crosshair
8. IF rolling statistics data is unavailable due to insufficient history (fewer data points than the selected window size), THEN THE Analytics page SHALL display a message stating the minimum number of trading days required

### Requirement 11: Performance Attribution

**User Story:** As a portfolio manager, I want to decompose my portfolio returns into allocation, selection, and interaction effects, so that I can understand whether my alpha comes from sector weight decisions or stock picking.

#### Acceptance Criteria

1. THE Analytics page SHALL display a "Performance Attribution" tab accessible from the Analytics tab bar
2. THE Performance_Attribution tab SHALL display a stacked bar chart decomposing total portfolio return into allocation effect, selection effect, and interaction effect for each sector
3. THE Performance_Attribution tab SHALL display an attribution summary table with columns: Sector, Portfolio Weight, Benchmark Weight, Portfolio Return, Benchmark Return, Allocation Effect, Selection Effect, Interaction Effect, and Total Contribution
4. THE Performance_Attribution tab SHALL display a time-series chart showing cumulative allocation effect, cumulative selection effect, and cumulative interaction effect over the selected period
5. WHEN the user selects a period from the Period_Selector (1M, 3M, 6M, 1Y, ALL), THE Performance_Attribution tab SHALL recalculate all attribution metrics for the selected period
6. THE Performance_Attribution tab SHALL support attribution by sector and by asset class, selectable via a toggle
7. IF attribution data is unavailable due to insufficient closed trades, THEN THE Performance_Attribution tab SHALL display a message stating the minimum number of closed trades required for meaningful attribution analysis

### Requirement 12: Drawdown Analysis and Return Distribution

**User Story:** As a portfolio manager, I want detailed drawdown analysis and return distribution visualizations, so that I can assess tail risk, recovery patterns, and the statistical properties of my returns.

#### Acceptance Criteria

1. THE Analytics page SHALL display a "Tear Sheet" tab containing drawdown analysis and return distribution visualizations
2. THE Tear Sheet tab SHALL display an Underwater_Plot showing the portfolio's percentage drawdown from peak over time as a filled area chart (red fill, #ef4444 at 40% opacity)
3. THE Tear Sheet tab SHALL display a "Worst Drawdowns" table listing the top 5 drawdown periods with columns: Rank, Start Date, Trough Date, Recovery Date, Depth (%), Duration (days), and Recovery Time (days)
4. THE Tear Sheet tab SHALL display a Return_Distribution_Histogram of daily returns with a normal distribution overlay curve, annotated with skew and kurtosis values displayed as metric badges
5. THE Tear Sheet tab SHALL display a "Cumulative Returns by Year" bar chart showing annual returns as vertical bars, one per calendar year, color-coded green for positive and red for negative years
6. THE Tear Sheet tab SHALL display a Monthly_Returns_Heatmap with months (Jan-Dec) as columns and years as rows, where each cell is color-coded by return magnitude using a diverging color scale (red for negative, white for zero, green for positive)
7. WHEN the user hovers over a cell in the Monthly_Returns_Heatmap, THE Chart_Crosshair SHALL display the exact monthly return percentage, the month/year label, and the number of trades closed that month
8. ALL charts in the Tear Sheet tab SHALL use the Interactive_Chart component from Requirement 5 where applicable (time-series charts support zoom, pan, crosshair)

### Requirement 13: Position-Level Analytics

**User Story:** As a portfolio manager, I want to drill down into individual position performance and risk contribution, so that I can identify which positions are driving portfolio returns and risk.

#### Acceptance Criteria

1. WHEN the user clicks a position row on the Portfolio page, THE Dashboard SHALL navigate to a position detail view displaying an Asset_Plot for that position's symbol
2. THE Asset_Plot SHALL display the symbol's price chart over the position's holding period with buy order annotations (green upward arrows) and sell order annotations (red downward arrows) at the corresponding dates and prices
3. THE Risk page SHALL display a "Risk Contribution" bar chart showing each open position's percentage contribution to total portfolio risk, sorted from highest to lowest
4. THE Portfolio page position detail view SHALL display a P&L time-series chart showing the individual position's unrealized P&L over its holding period
5. THE Risk page SHALL display a "Portfolio Turnover" Interactive_Chart showing monthly portfolio turnover rate (total value of positions opened and closed divided by average portfolio value) over time
6. THE Risk page SHALL display a "Long/Short Exposure" Interactive_Chart showing a stacked area chart with long exposure above the zero line and short exposure below the zero line over time
7. IF a position has no order history available, THEN THE Asset_Plot SHALL display the price chart without order annotations and show an informational badge stating "Order history unavailable"

### Requirement 14: Command Palette and Quick Navigation

**User Story:** As a power user, I want a keyboard-driven command palette for rapid navigation, so that I can jump to any symbol, strategy, page, or action without using the mouse.

#### Acceptance Criteria

1. WHEN the user presses Ctrl+K (or Cmd+K on Mac), THE Dashboard SHALL display the Command_Palette as a centered modal overlay with a search input field auto-focused
2. THE Command_Palette SHALL support fuzzy search across four categories: Symbols (e.g., typing "AAPL" navigates to the position detail for AAPL), Strategies (typing a strategy name navigates to that strategy's detail), Pages (typing "risk" navigates to the Risk page), and Actions (typing "sync" triggers the eToro sync action)
3. THE Command_Palette SHALL display search results grouped by category with keyboard navigation using arrow keys (up/down) and Enter to select
4. WHEN the Command_Palette opens with an empty query, THE Command_Palette SHALL display a "Recent Items" list showing the last 5 navigated-to items
5. WHEN the user selects a result from the Command_Palette, THE Dashboard SHALL execute the corresponding navigation or action and close the Command_Palette within 200ms
6. WHEN the user presses Escape while the Command_Palette is open, THE Command_Palette SHALL close without executing any action
7. THE Command_Palette search SHALL return results within 100ms of keystroke for up to 500 searchable items

### Requirement 15: PDF Tear Sheet Export

**User Story:** As a portfolio manager, I want to generate a professional PDF tear sheet summarizing portfolio performance, so that I can share it with investors or stakeholders.

#### Acceptance Criteria

1. THE Overview page and the Analytics page SHALL each display a "Download Tear Sheet" button that triggers PDF generation
2. WHEN the user clicks the "Download Tear Sheet" button, THE Dashboard SHALL generate a PDF document containing: equity curve with SPY_Benchmark overlay, key statistics table (Sharpe Ratio, Sortino Ratio, Max Drawdown, CAGR, Win Rate, Profit Factor), Monthly_Returns_Heatmap, drawdown chart, sector exposure breakdown, and top 5 / bottom 5 performers by P&L
3. THE Tear_Sheet PDF SHALL support a configurable reporting period selectable before generation: 1M, 3M, 6M, 1Y, ALL
4. WHEN PDF generation begins, THE Dashboard SHALL display a progress indicator and disable the download button until generation completes
5. THE Tear_Sheet PDF SHALL use a professional layout with the AlphaCent logo, report title, generation date, and selected period displayed in the header
6. IF PDF generation fails due to missing data, THEN THE Dashboard SHALL display an error message specifying which data sections are unavailable and offer to generate a partial report excluding those sections
7. THE generated Tear_Sheet PDF SHALL be downloaded as a file named "AlphaCent_TearSheet_{period}_{YYYY-MM-DD}.pdf"

### Requirement 16: Multi-Timeframe Performance Comparison

**User Story:** As a portfolio manager, I want to see returns across multiple time horizons at a glance, so that I can quickly assess short-term and long-term performance trends.

#### Acceptance Criteria

1. THE Overview page SHALL display a Multi_Timeframe_View showing returns for 1D, 1W, 1M, 3M, 6M, YTD, 1Y, and ALL periods in a compact horizontal row of cells
2. THE Multi_Timeframe_View SHALL display both absolute return and benchmark-relative alpha for each period
3. THE Multi_Timeframe_View SHALL color-code each cell: green (#22c55e) background tint for positive returns and red (#ef4444) background tint for negative returns
4. WHEN the user clicks a timeframe cell in the Multi_Timeframe_View, THE Equity_Curve_Chart Period_Selector SHALL update to the corresponding period and the equity curve SHALL re-render for that time range
5. WHERE the Global_Summary_Bar has available horizontal space (viewport width above 1440px), THE Global_Summary_Bar SHALL display a condensed version of the Multi_Timeframe_View showing 1D, 1W, 1M, and YTD returns
6. IF return data for a specific timeframe is unavailable due to insufficient history, THEN THE Multi_Timeframe_View SHALL display "N/A" in that cell with a muted style

### Requirement 17: System Observability Dashboard

**User Story:** As a system operator, I want to see the health and status of all backend services in real-time, so that I can identify and respond to system issues before they affect trading.

#### Acceptance Criteria

1. THE Dashboard SHALL provide a System_Health_Page accessible from the Settings page or as a dedicated top-level page, displaying the operational status of all backend services
2. THE System_Health_Page SHALL display Circuit_Breaker states for each category (orders, positions, market_data) with visual indicators: green for CLOSED, yellow for HALF_OPEN, red for OPEN, and SHALL show the consecutive failure count and cooldown timer remaining for each Circuit_Breaker
3. THE System_Health_Page SHALL display Monitoring_Service status including running or stopped state and the last cycle timestamp for each sub-task: position sync, trailing stops, partial exits, pending closures, fundamental checks, time-based exits, and stale order cleanup
4. THE System_Health_Page SHALL display Trading_Scheduler status including last signal generation time, next expected run time, number of signals generated in the last run, and number of orders submitted in the last run
5. THE System_Health_Page SHALL display eToro API health metrics: requests per minute, error rate over the last 5 minutes, average response time in milliseconds, and rate limit headroom remaining
6. THE System_Health_Page SHALL display background thread status for the quick price update (last run time, duration in seconds, symbols updated) and the full price sync (last run time, duration in seconds, symbols synced)
7. THE System_Health_Page SHALL display cache statistics: order status cache hit rate, positions cache hit rate, historical data cache hit rate, and FMP cache warm status including last warm time and the ratio of symbols fetched from API versus served from cache
8. WHEN a Circuit_Breaker state changes or the Monitoring_Service completes a heartbeat cycle, THE System_Health_Page SHALL receive the update via the WebSocket_Feed within 2 seconds
9. THE System_Health_Page SHALL display a visual timeline showing system events from the last 24 hours, including Circuit_Breaker state transitions, service restarts, sync completions, and errors, plotted on a horizontal time axis
10. WHEN any Circuit_Breaker is in the OPEN state or the Monitoring_Service has not completed a cycle within 2 times its expected interval, THE System_Health_Page SHALL display a prominent alert indicator next to the affected service
11. WHILE the System_Health_Page is active, THE Dashboard SHALL update all displayed metrics via the WebSocket_Feed and SHALL NOT rely on REST API polling for data covered by WebSocket events

### Requirement 18: Strategy Lifecycle Intelligence

**User Story:** As a portfolio manager, I want to understand the autonomous strategy lifecycle decisions, so that I can evaluate whether the system is making intelligent proposal, activation, and retirement choices.

#### Acceptance Criteria

1. THE Strategies page SHALL display a "Template Rankings" section containing a sortable table of all 175+ strategy templates with columns: template name, win rate, average Sharpe ratio, total trades generated, active strategy count, and last proposal date, sortable by any column header
2. THE Template Rankings table SHALL support filtering by strategy family (Trend Following, Mean Reversion, Breakout, Momentum, Volatility) and by timeframe (Daily, 1H, 4H) via dropdown selectors
3. THE Autonomous page SHALL display a "Walk-Forward Analytics" section showing per-cycle statistics: proposals generated, backtests run, Walk_Forward_Pass_Rate as a percentage, average Sharpe ratio of passed strategies, and average Sharpe ratio of failed strategies
4. THE Walk-Forward Analytics section SHALL display a historical Interactive_Chart of Walk_Forward_Pass_Rate over time with Period_Selector support (1M, 3M, 6M, 1Y, ALL)
5. THE Strategies page SHALL display a "Blacklists" section showing currently blocked template+symbol combinations with columns: template name, symbol, Blacklist type (zero-trade or rejection), blocked since date, unblock date, and reason for blocking
6. THE Blacklists section SHALL display a summary count of currently blocked combinations, grouped by Blacklist type
7. WHEN the user views a signal detail or strategy detail, THE Dashboard SHALL display the Conviction_Score decomposition showing individual component values: signal strength, fundamental quality, regime fit, carry bias (for forex symbols), and halving cycle overlay (for crypto symbols), rendered as a horizontal stacked bar showing each component's proportional contribution
8. WHEN a strategy is rejected during activation due to similarity with an existing strategy, THE Autonomous page SHALL display the rejected strategy name, the existing strategy it was similar to, and the similarity percentage that exceeded the 80% threshold
9. THE Strategies page SHALL display an "Idle Demotions" log showing strategies recently transitioned from DEMO to BACKTESTED via Idle_Demotion, with columns: strategy name, demotion timestamp, and reason (no open positions, no pending orders)
10. IF Template_Performance data is unavailable for a template due to zero historical trades, THEN THE Template Rankings table SHALL display "No data" in the metric columns for that template with a muted style

### Requirement 19: Data Pipeline Observability

**User Story:** As a system operator, I want to monitor the health and freshness of all data sources, so that I can ensure the trading system is operating on accurate, timely data.

#### Acceptance Criteria

1. THE Data Management page SHALL display a "Data Quality" table listing all 297 symbols with columns: symbol, asset class, Data_Quality_Score (0-100) with color coding (green for scores above 80, yellow for scores between 60 and 80, red for scores below 60), last price update time, data source (Yahoo Finance, FMP, or eToro), number of active data quality issues, and a staleness indicator showing time since last update
2. THE Data Quality table SHALL support sorting by any column and filtering by asset class and by Data_Quality_Score range via dropdown selectors
3. THE Data Management page SHALL display an "FMP Cache Status" section showing: last cache warm time, total symbols warmed, API calls used versus cache hits in the last warm cycle, estimated API calls remaining out of the 300 per minute limit, and next scheduled warm time
4. THE Data Management page SHALL display a "Data Source Health" section showing status for each data source (eToro API, Yahoo Finance, FMP, FRED) with columns: source name, status (healthy, degraded, or down), last successful fetch time, error count in the last hour, and average response time in milliseconds
5. THE Data Management page SHALL display a "Price Sync Timeline" visualization showing the quick price update cycle (10-minute interval) and the full price sync cycle (55-minute interval) with: last run time, duration in seconds, symbols updated, and next expected run time, rendered as a horizontal timeline with progress bars during active syncs
6. WHEN any symbol's Data_Quality_Score drops below 60, THE Data Management page SHALL display a warning badge next to that symbol in the Data Quality table
7. WHERE the Global_Summary_Bar has available horizontal space (viewport width above 1440px), THE Global_Summary_Bar SHALL display a data health indicator showing the count of symbols with Data_Quality_Score below 60
8. THE Data Management page SHALL display a "Historical Data Coverage" heatmap showing data availability per symbol as a grid with symbols on the vertical axis and date ranges on the horizontal axis, with cells color-coded by data completeness and gaps highlighted in red
9. WHEN the user hovers over a cell in the Historical Data Coverage heatmap, THE Chart_Crosshair SHALL display the symbol name, date range, number of bars available, and number of expected bars for that period
10. IF Data_Quality_Score data is unavailable for a symbol because the data quality validator has not yet run, THEN THE Data Quality table SHALL display "Pending" in the score column with a muted style

### Requirement 20: Execution Quality and Transaction Cost Analysis

**User Story:** As a portfolio manager, I want to analyze execution quality across all trades, so that I can identify whether execution costs are eroding alpha and optimize order timing.

#### Acceptance Criteria

1. THE Analytics page SHALL display a "TCA" tab accessible from the Analytics tab bar, containing execution quality metrics and Transaction_Cost_Analysis visualizations
2. THE TCA tab SHALL display a "Slippage by Symbol" bar chart showing average entry slippage per symbol sorted from worst (highest slippage) to best (lowest slippage), with bars color-coded red for slippage above 0.5% and yellow for slippage between 0.1% and 0.5%
3. THE TCA tab SHALL display a "Slippage by Time of Day" heatmap with hours (0-23 UTC) on the horizontal axis and days of the week on the vertical axis, where each cell is color-coded by average slippage magnitude using a diverging color scale (green for low slippage, red for high slippage)
4. THE TCA tab SHALL display a "Slippage by Order Size" bar chart grouping trades into size buckets (small: below $1K, medium: $1K-$5K, large: above $5K) and showing average slippage per bucket
5. THE TCA tab SHALL display an "Implementation Shortfall" table listing each closed trade with columns: symbol, expected price (signal generation price), fill price, market close price on fill date, shortfall in dollars, shortfall in basis points, and trade date
6. THE TCA tab SHALL display a prominent "Total Implementation Shortfall" metric card showing the aggregate shortfall in dollars and in basis points across all closed trades for the selected period
7. THE TCA tab SHALL display a "Fill Rate Analysis" visualization showing the percentage of orders filled within 5 seconds, 30 seconds, 60 seconds, and 5 minutes, rendered as a horizontal funnel chart or grouped bar chart
8. THE TCA tab SHALL display a "Cost as % of Alpha" metric card as the most prominent element on the tab, showing total execution costs (slippage plus estimated spread cost) as a percentage of gross portfolio returns for the selected period
9. THE TCA tab SHALL display an "Execution Quality Trend" Interactive_Chart showing rolling average slippage over time with Period_Selector support (1M, 3M, 6M, 1Y, ALL) and configurable rolling window sizes of 30 days and 60 days
10. THE TCA tab SHALL display a "Per Asset Class" breakdown section with separate Transaction_Cost_Analysis summary cards for each asset class (stocks, ETFs, forex, crypto, indices, commodities), each showing average slippage, average Implementation_Shortfall in basis points, and trade count for that asset class
11. THE TCA tab SHALL display a "Worst Executions" table listing the top 10 trades with highest absolute slippage, with columns: symbol, expected price, fill price, slippage percentage, timestamp, order size in dollars, and asset class, sortable by any column header
12. WHEN the user selects a period from the Period_Selector (1M, 3M, 6M, 1Y, ALL), THE TCA tab SHALL recalculate all Transaction_Cost_Analysis metrics for the selected period
13. IF Transaction_Cost_Analysis data is unavailable due to fewer than 10 closed trades in the selected period, THEN THE TCA tab SHALL display a message stating the minimum number of trades required for meaningful execution quality analysis

### Requirement 21: Audit Trail and Decision Log

**User Story:** As a system operator, I want a comprehensive audit trail of every trading decision, so that I can trace the full lifecycle of any trade from signal to execution and understand why the system made each decision.

#### Acceptance Criteria

1. THE Dashboard SHALL provide an "Audit Log" page accessible from the Sidebar, displaying a chronological log of all system decisions with columns: timestamp, event type, symbol, strategy name, severity level, and description
2. THE Audit Log page SHALL support filtering by event type (signal generated, signal rejected, risk limit hit, order submitted, order filled, position opened, position closed, strategy activated, strategy retired, strategy demoted, circuit breaker transition), by symbol, by strategy name, by severity level (info, warning, error), and by date range
3. THE Audit Log page SHALL support full-text search across all log entries, returning matching results within 200ms for up to 10,000 displayed entries
4. WHEN the user clicks a trade entry in the Audit Log, THE Audit Log page SHALL display a "Trade Lifecycle" detail view showing the complete chain of events for that trade: signal generated (with conviction score and signal strength) → risk validated (with position sizing and risk checks passed) → order submitted (with expected price and order parameters) → order filled (with fill price and slippage) → position opened (with stop-loss and take-profit levels) → trailing stop updates (with each adjustment timestamp and new stop level) → position closed (with exit reason and final P&L), each step annotated with its timestamp and key metrics
5. THE Audit Log page SHALL display a "Signal Rejections" summary section showing all rejected signals with columns: timestamp, symbol, strategy name, rejection reason (duplicate signal, correlation above threshold, portfolio balance violation, risk limit breach, insufficient conviction), conviction score, and signal strength, filterable by rejection reason, symbol, strategy name, and date range
6. THE Audit Log page SHALL display a "Strategy Lifecycle Events" section showing: activation decisions with Sharpe ratio, tier assignment, and pass or fail reason; retirement decisions with the performance metrics that triggered retirement; Idle_Demotion events with demotion timestamp and reason; and similarity rejections with the existing strategy name and similarity percentage
7. THE Audit Log page SHALL display a "Risk Limit Events" section showing every instance where a risk limit was triggered, with columns: timestamp, limit type (sector cap, direction cap, daily loss limit, portfolio stop-loss, per-symbol cap, per-strategy cap), symbol or sector affected, current exposure value, limit threshold value, and the action that was blocked
8. THE Audit Log page SHALL support exporting the currently filtered log entries as a CSV file, with the filename format "AlphaCent_AuditLog_{start_date}_{end_date}.csv"
9. THE Audit Log page SHALL display at least 90 days of audit history, with older entries accessible via date range selection
10. WHEN the Audit Log page loads, THE Audit Log page SHALL display the most recent 100 entries sorted by timestamp descending, with infinite scroll or pagination to load additional entries
11. IF audit log data is unavailable for the selected date range, THEN THE Audit Log page SHALL display a message stating that no audit records exist for the selected period
