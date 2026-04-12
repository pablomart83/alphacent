# Implementation Plan: Quant Platform UI Overhaul

## Overview

This plan transforms the AlphaCent frontend into an institutional-grade trading dashboard across 8 phases. Each task produces a clean-building, independently deployable increment. The existing React 19 + Vite 8 + TypeScript + Recharts + Tailwind CSS 4 stack is preserved. New dependencies are added in Phase 1. Backend endpoints are created alongside their frontend consumers.

## Tasks

- [x] 1. Foundation — Design System & Shared Components
  - [x] 1.1 Define CSS design tokens and standardize theme variables
    - Create `frontend/src/lib/design-tokens.ts` exporting color constants (green #22c55e, red #ef4444, blue #3b82f6, yellow #eab308), spacing, chart theme (dark bg #111827, grid #374151, axis #9ca3af 10px font-mono), and standard card/table/page-layout tokens
    - Update `frontend/src/index.css` with any new CSS custom properties needed
    - Audit existing Card, Table, Badge components in `frontend/src/components/ui/` to ensure they use the new tokens — update where inconsistent
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 1.2 Build the InteractiveChart component with zoom, pan, crosshair, and PeriodSelector
    - Create `frontend/src/components/charts/InteractiveChart.tsx` wrapping Recharts `ResponsiveContainer` with:
      - Mouse-wheel zoom on time axis using `ReferenceArea` for visual selection
      - Click-and-drag pan when zoomed
      - Custom crosshair tooltip with vertical `ReferenceLine` following active index
      - `children` prop for custom reference areas/lines
    - Create `frontend/src/components/charts/PeriodSelector.tsx` with 1W/1M/3M/6M/1Y/ALL buttons, `onPeriodChange` callback
    - Export both from `frontend/src/components/charts/index.ts`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 1.3 Write unit tests for InteractiveChart period filtering and zoom state logic
    - Test period date range calculation for each period option
    - Test zoom state management (refAreaLeft/refAreaRight → filtered data range)
    - _Requirements: 5.4, 5.5_

  - [x] 1.4 Install new dependencies
    - Run `npm install html2canvas jspdf @tanstack/react-virtual fuse.js` in `frontend/`
    - Verify `package.json` updated and `npm run build` succeeds
    - _Requirements: 14.7, 15.2, 21.3, 21.10_

- [x] 2. Checkpoint — Foundation builds clean
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Core Layout — GlobalSummaryBar, Sidebar, Skeletons, WebSocket
  - [x] 3.1 Build the GlobalSummaryBar component
    - Create `frontend/src/components/GlobalSummaryBar.tsx` — persistent 48px bar below header
    - Display: Total Equity, Daily P&L ($ and %), Open Positions, Active Strategies, Market Regime, System Health score
    - Green/red text for P&L values, yellow warning indicator when WebSocket disconnected
    - Data from existing `apiClient.getAccountInfo()`, `apiClient.getDashboardSummary()`, and WebSocket events
    - Poll every 30s as fallback
    - Conditionally show condensed Multi-Timeframe (1D/1W/1M/YTD) at viewport > 1440px
    - Integrate into `frontend/src/components/DashboardLayout.tsx` between header and `<main>`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 16.5_

  - [x] 3.2 Implement Sidebar responsive collapse (icon-only mode below 1024px)
    - Update `frontend/src/components/Sidebar.tsx` to collapse to 64px icon-only mode when viewport < 1024px
    - Add toggle button to expand/collapse
    - _Requirements: 8.1_

  - [x] 3.3 Enhance skeleton loaders for all pages
    - Update `frontend/src/components/ui/loading-skeletons.tsx` and `skeleton.tsx` to provide shape-matching skeletons for each page section
    - Ensure shimmer animation, 200ms fade-in transition to content, 10s timeout → error state with retry button
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 3.4 Optimize WebSocket update flow — reduce REST polling when WS connected
    - Update pages (OverviewNew, PortfolioNew, OrdersNew, RiskNew) to skip REST polling for data covered by WebSocket events when `wsConnected === true`
    - On WS disconnect, fall back to 30s REST polling; on reconnect, full data refresh
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 3.5 Write unit tests for GlobalSummaryBar rendering and WebSocket state
    - Test renders correct metrics, updates on mock WS events, shows warning on disconnect
    - _Requirements: 2.2, 2.3, 2.5_

- [x] 4. Checkpoint — Core layout builds clean
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Overview Page — Equity Curve with SPY Benchmark, MultiTimeframeView, Redesign
  - [x] 5.1 Build the EquityCurveChart with SPY benchmark overlay
    - Create `frontend/src/components/charts/EquityCurveChart.tsx`
    - Two `<Line>` series: portfolio (blue #3b82f6) and SPY (gray dashed), both normalized to 100 at period start
    - Alpha shaded area between lines (green when portfolio > SPY, red otherwise)
    - Crosshair tooltip showing portfolio value, SPY value, and alpha at hovered date
    - Synchronized drawdown sub-chart below sharing same x-axis and PeriodSelector state
    - "Benchmark unavailable" badge when SPY data missing
    - Uses InteractiveChart from task 1.2
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 5.2 Build the MultiTimeframeView component
    - Create `frontend/src/components/charts/MultiTimeframeView.tsx`
    - Compact horizontal row of cells: 1D, 1W, 1M, 3M, 6M, YTD, 1Y, ALL
    - Each cell shows absolute return and benchmark-relative alpha
    - Green/red background tint per cell; clicking a cell updates EquityCurveChart period
    - "N/A" with muted style for unavailable periods
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.6_

  - [x] 5.3 Redesign the Overview page layout
    - Update `frontend/src/pages/OverviewNew.tsx`:
      - Hero section: full-width EquityCurveChart with SPY benchmark
      - Below: MultiTimeframeView row
      - Below: 4-column Metric_Grid (Total Equity, Daily P&L $+%, Sharpe 30d, Max Drawdown)
      - Below: 2-column layout — position summary by asset class (left), recent trades last 10 (right)
      - Below: Strategy_Pipeline visualization (proposed → backtested → active → retired) with clickable navigation to Strategies page filtered by stage
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.4 Backend: SPY benchmark data endpoint
    - Create new endpoint `GET /analytics/spy-benchmark?period=3M` in `src/api/routers/analytics.py`
    - Returns normalized SPY price series aligned to portfolio equity curve dates
    - Source SPY data from existing `historical_price_cache` table or fetch via Yahoo Finance
    - _Requirements: 1.1, 1.4_

  - [ ]* 5.5 Write unit tests for equity normalization and alpha calculation
    - Test normalizing portfolio + SPY to 100 at period start
    - Test alpha = portfolio return - SPY return at each date
    - _Requirements: 1.1, 1.3_

- [x] 6. Checkpoint — Overview page builds clean
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Analytics Tabs — Rolling Statistics, Performance Attribution, Tear Sheet, TCA
  - [x] 7.1 Build the Rolling Statistics tab on Analytics page
    - Add "Rolling Statistics" tab to `frontend/src/pages/AnalyticsNew.tsx`
    - Interactive time-series charts: Rolling Sharpe, Rolling Beta vs SPY, Rolling Alpha, Rolling Volatility
    - Configurable rolling window: 30d, 60d, 90d toggle above charts
    - Metric cards: Probabilistic Sharpe Ratio, Information Ratio, Treynor Ratio, Tracking Error
    - "Minimum N trading days required" message when insufficient data
    - Uses InteractiveChart with PeriodSelector (1M, 3M, 6M, 1Y, ALL)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [x] 7.2 Backend: Rolling statistics endpoint
    - Create `GET /analytics/rolling-statistics?mode=DEMO&period=3M&window=30` in `src/api/routers/analytics.py`
    - Returns `RollingStatsData`: rolling_sharpe, rolling_beta, rolling_alpha, rolling_volatility arrays + PSR, IR, Treynor, tracking error scalars
    - Compute from equity curve and SPY benchmark data in `historical_price_cache`
    - _Requirements: 10.1, 10.5, 10.6_

  - [x] 7.3 Build the Performance Attribution tab on Analytics page
    - Add "Performance Attribution" tab to AnalyticsNew
    - Stacked bar chart: allocation, selection, interaction effects per sector
    - Attribution summary table with all columns from Req 11.3
    - Cumulative effects time-series chart
    - Toggle: by sector vs by asset class
    - PeriodSelector (1M, 3M, 6M, 1Y, ALL)
    - "Minimum N closed trades required" message when insufficient data
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 7.4 Backend: Performance attribution endpoint
    - Create `GET /analytics/performance-attribution?mode=DEMO&period=3M&group_by=sector` in `src/api/routers/analytics.py`
    - Returns `AttributionData`: sectors array with weights/returns/effects + cumulative_effects time series
    - Implement Brinson model decomposition using closed trades and sector weights
    - _Requirements: 11.2, 11.3, 11.4_

  - [x] 7.5 Build the Tear Sheet tab on Analytics page
    - Add "Tear Sheet" tab to AnalyticsNew
    - Create `frontend/src/components/charts/UnderwaterPlot.tsx` — filled area chart (red #ef4444 at 40% opacity)
    - "Worst Drawdowns" table: top 5 drawdowns with start/trough/recovery dates, depth, duration, recovery time
    - Create `frontend/src/components/charts/ReturnDistribution.tsx` — histogram with normal overlay, skew/kurtosis badges
    - "Cumulative Returns by Year" bar chart — green/red per year
    - Create `frontend/src/components/charts/MonthlyReturnsHeatmap.tsx` — year×month grid, diverging color scale, crosshair tooltip with monthly return %, month/year, trades closed
    - All time-series charts use InteractiveChart
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8_

  - [x] 7.6 Backend: Tear sheet data endpoint
    - Create `GET /analytics/tear-sheet?mode=DEMO&period=1Y` in `src/api/routers/analytics.py`
    - Returns `TearSheetData`: underwater_plot, worst_drawdowns, return_distribution, skew, kurtosis, annual_returns, monthly_returns
    - Compute from equity curve and daily returns
    - _Requirements: 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 7.7 Build the TCA tab on Analytics page
    - Add "TCA" tab to AnalyticsNew
    - "Cost as % of Alpha" prominent metric card
    - "Slippage by Symbol" bar chart (red > 0.5%, yellow 0.1-0.5%)
    - "Slippage by Time of Day" heatmap (hours × days)
    - "Slippage by Order Size" bar chart (small/medium/large buckets)
    - "Implementation Shortfall" table with all columns from Req 20.5
    - "Total Implementation Shortfall" metric card
    - "Fill Rate Analysis" grouped bar chart (5s, 30s, 60s, 5min)
    - "Execution Quality Trend" InteractiveChart with rolling window 30d/60d
    - "Per Asset Class" breakdown cards
    - "Worst Executions" table (top 10)
    - PeriodSelector (1M, 3M, 6M, 1Y, ALL)
    - "Minimum 10 closed trades required" message when insufficient data
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8, 20.9, 20.10, 20.11, 20.12, 20.13_

  - [x] 7.8 Backend: TCA data endpoint
    - Create `GET /analytics/tca?mode=DEMO&period=3M` in `src/api/routers/analytics.py`
    - Returns `TCAData`: slippage_by_symbol, slippage_by_hour, slippage_by_size, implementation_shortfall, fill_rate_buckets, cost_as_pct_of_alpha, execution_quality_trend, per_asset_class, worst_executions
    - Extend existing slippage analytics in the backend
    - _Requirements: 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8, 20.9, 20.10, 20.11_

  - [ ]* 7.9 Write unit tests for tear sheet data transformations
    - Test drawdown calculation from equity curve
    - Test monthly returns grid transformation (daily → year×month matrix)
    - Test return distribution binning
    - _Requirements: 12.2, 12.4, 12.6_

- [x] 8. Checkpoint — Analytics tabs build clean
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Page-Specific Improvements — Strategies, Risk, Orders, Autonomous, Portfolio
  - [x] 9.1 Strategies page enhancements — sparklines, sorting, template rankings, blacklists, idle demotions
    - Update `frontend/src/pages/StrategiesNew.tsx`:
      - Add inline mini equity curve (sparkline) for each active strategy row
      - Ensure sortable columns: Sharpe, total return, trades, win rate (already partially implemented — verify and fix)
      - Add "Template Rankings" section: sortable table of 175+ templates with win rate, avg Sharpe, total trades, active count, last proposal date; filterable by family and timeframe
      - Add "Blacklists" section: blocked template+symbol combos with type, dates, reason, summary counts
      - Add "Idle Demotions" log: recently demoted strategies with name, timestamp, reason
    - _Requirements: 6.1, 6.2, 18.1, 18.2, 18.5, 18.6, 18.9, 18.10_

  - [x] 9.2 Risk page enhancements — correlation heatmap, sector pie, risk contribution, turnover, exposure
    - Update `frontend/src/pages/RiskNew.tsx`:
      - Create `frontend/src/components/charts/CorrelationHeatmap.tsx` — pairwise correlations for top 20 positions
      - Add sector exposure pie chart with P&L color coding per slice
      - Add "Risk Contribution" bar chart — each position's % contribution to total portfolio risk, sorted highest to lowest
      - Add "Portfolio Turnover" InteractiveChart — monthly turnover rate over time
      - Add "Long/Short Exposure" stacked area chart — long above zero, short below zero
    - _Requirements: 6.3, 6.4, 13.3, 13.5, 13.6_

  - [x] 9.3 Orders page — order flow timeline visualization
    - Update `frontend/src/pages/OrdersNew.tsx`:
      - Create `frontend/src/components/charts/OrderFlowTimeline.tsx` — horizontal time axis showing order events (placed, filled, cancelled) for last 7 days
      - Integrate into Orders page
    - _Requirements: 6.5_

  - [x] 9.4 Autonomous page enhancements — walk-forward analytics, conviction scores, similarity rejections
    - Update `frontend/src/pages/AutonomousNew.tsx`:
      - Add "Walk-Forward Analytics" section: per-cycle stats (proposals, backtests, pass rate %, avg Sharpe passed/failed)
      - Walk-forward pass rate InteractiveChart over time with PeriodSelector
      - Conviction score decomposition display (signal strength, fundamental quality, regime fit, carry bias, halving cycle) as horizontal stacked bar
      - Similarity rejection display: rejected strategy name, existing strategy, similarity %
    - _Requirements: 6.6, 18.3, 18.4, 18.7, 18.8_

  - [x] 9.5 Portfolio page — position drill-down with asset plot and P&L chart
    - Create `frontend/src/pages/PositionDetailView.tsx` at route `/portfolio/:symbol`
    - Create `frontend/src/components/charts/AssetPlot.tsx` — price chart with buy (green ↑) and sell (red ↓) order annotations
    - P&L time-series chart for individual position over holding period
    - "Order history unavailable" badge when no order data
    - Add route to `frontend/src/App.tsx`
    - Wire click handler on Portfolio page position rows to navigate to `/portfolio/:symbol`
    - _Requirements: 13.1, 13.2, 13.4, 13.7_

  - [x] 9.6 Backend: Template rankings endpoint
    - Create `GET /strategies/template-rankings?mode=DEMO` in `src/api/routers/strategies.py`
    - Returns array of template performance data: name, win rate, avg Sharpe, total trades, active count, last proposal date
    - _Requirements: 18.1_

  - [x] 9.7 Backend: Walk-forward analytics endpoint
    - Create `GET /strategies/autonomous/walk-forward-analytics?mode=DEMO&period=3M` in `src/api/routers/strategies.py`
    - Returns per-cycle walk-forward stats and historical pass rate time series
    - _Requirements: 18.3, 18.4_

  - [x] 9.8 Backend: Position detail endpoint
    - Create `GET /account/positions/:symbol/detail?mode=DEMO` in `src/api/routers/account.py`
    - Returns `PositionDetailData`: price history over holding period, order annotations (buy/sell with dates/prices), P&L time series
    - _Requirements: 13.1, 13.2, 13.4_

  - [ ]* 9.9 Write unit tests for sparkline data extraction and correlation matrix computation
    - Test extracting mini equity curve data for strategy sparklines
    - Test correlation coefficient calculation for position pairs
    - _Requirements: 6.1, 6.3_

- [x] 10. Checkpoint — Page improvements build clean
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. New Pages — Data Management, System Health, Audit Log
  - [x] 11.1 Data Management page enhancements — data quality table, FMP cache, data source health, price sync timeline, coverage heatmap
    - Update `frontend/src/pages/DataManagementNew.tsx`:
      - Add "Data Quality" table: 297 symbols with quality score (color-coded), last update, source, issues, staleness; sortable/filterable by asset class and score range
      - Add "FMP Cache Status" section: last warm time, symbols warmed, API vs cache hits, remaining calls, next warm
      - Add "Data Source Health" section: eToro, Yahoo, FMP, FRED status with last fetch, errors, response time
      - Add "Price Sync Timeline" visualization: quick update (10min) and full sync (55min) with progress bars
      - Add "Historical Data Coverage" heatmap: symbols × date ranges, color-coded by completeness, gaps in red, crosshair tooltip
      - Warning badge for symbols with score < 60
      - Data health indicator in GlobalSummaryBar at viewport > 1440px
    - _Requirements: 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7, 19.8, 19.9, 19.10_

  - [x] 11.2 Build the System Health page
    - Create `frontend/src/pages/SystemHealthPage.tsx` at route `/system-health`
    - Create `frontend/src/lib/stores/system-health-store.ts` (Zustand)
    - Display: Circuit breaker states (3 categories) with green/yellow/red indicators, failure count, cooldown timer
    - Monitoring service sub-task status with last cycle timestamps
    - Trading scheduler: last signal time, next run, signals/orders last run
    - eToro API health: req/min, error rate 5min, avg response ms, rate limit remaining
    - Background thread status: quick price update + full sync details
    - Cache statistics: order/position/historical hit rates, FMP warm status
    - 24-hour event timeline (horizontal time axis)
    - WebSocket-driven real-time updates; prominent alert when circuit breaker OPEN or monitoring stale
    - Add route to App.tsx, add nav item to Sidebar
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.10, 17.11_

  - [x] 11.3 Build the Audit Log page
    - Create `frontend/src/pages/AuditLogPage.tsx` at route `/audit-log`
    - Create `frontend/src/lib/stores/audit-store.ts` (Zustand)
    - Chronological log table with `@tanstack/react-virtual` for 10,000+ entries
    - Columns: timestamp, event type, symbol, strategy name, severity, description
    - Multi-filter: event type dropdown, symbol, strategy, severity, date range
    - Full-text search with 200ms debounce
    - "Trade Lifecycle" detail view (expandable row): signal → risk validation → order → fill → position → trailing stops → close
    - "Signal Rejections" summary section with filters
    - "Strategy Lifecycle Events" section: activations, retirements, demotions, similarity rejections
    - "Risk Limit Events" section: limit type, symbol/sector, exposure, threshold, blocked action
    - CSV export: `AlphaCent_AuditLog_{start}_{end}.csv`
    - 90 days history, most recent 100 on load, infinite scroll/pagination
    - "No audit records" message when empty
    - Add route to App.tsx, add nav item to Sidebar
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9, 21.10, 21.11_

  - [x] 11.4 Backend: System health endpoint
    - Create `GET /control/system-health` in `src/api/routers/control.py`
    - Returns `SystemHealthData`: circuit_breakers, monitoring_service, trading_scheduler, etoro_api, cache_stats, events_24h
    - Compose from existing monitoring service state, circuit breaker instances, and scheduler state
    - _Requirements: 17.2, 17.3, 17.4, 17.5, 17.6, 17.7, 17.9_

  - [x] 11.5 Backend: Audit log endpoint
    - Create `GET /audit/log?event_types=...&symbol=...&severity=...&start_date=...&end_date=...&search=...&offset=0&limit=100` in new `src/api/routers/audit.py`
    - Create `GET /audit/trade-lifecycle/:trade_id` for trade detail view
    - Create `GET /audit/export?...` returning CSV blob
    - Store audit events in a new `audit_log` table (or query from existing signal_log, order, position, strategy tables)
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.8, 21.9, 21.10_

  - [x] 11.6 Backend: Data quality endpoint
    - Create `GET /data/quality` in `src/api/routers/data.py`
    - Returns array of `DataQualityEntry`: symbol, asset_class, quality_score, last_price_update, data_source, active_issues, staleness_seconds
    - Compute quality scores from data_quality_validator or historical_price_cache freshness
    - _Requirements: 19.1, 19.6, 19.10_

  - [ ]* 11.7 Write unit tests for audit log CSV export formatting and virtual scroll data slicing
    - Test CSV string generation from audit entries
    - Test pagination/offset logic for audit log queries
    - _Requirements: 21.8, 21.10_

- [x] 12. Checkpoint — New pages build clean
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Power User Features — Command Palette, PDF Tear Sheet Export
  - [x] 13.1 Build the Command Palette
    - Create `frontend/src/components/CommandPalette.tsx` using Radix Dialog
    - Create `frontend/src/hooks/useFuzzySearch.ts` using fuse.js
    - Triggered by Ctrl+K (Cmd+K on Mac) — register in `useKeyboardShortcuts`
    - Fuzzy search across: Symbols (navigate to position detail), Strategies (navigate to strategy detail), Pages (navigate to page), Actions (trigger sync, etc.)
    - Results grouped by category, keyboard navigation (arrow keys + Enter)
    - "Recent Items" list (last 5) when query empty, stored in localStorage
    - Close on Escape, execute + close within 200ms on selection
    - Search returns results within 100ms for up to 500 items
    - Render at App level in `frontend/src/App.tsx`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [x] 13.2 Build the PDF Tear Sheet export
    - Create `frontend/src/components/pdf/TearSheetGenerator.tsx`
    - "Download Tear Sheet" button on Overview page and Analytics page
    - Configurable period selector before generation (1M, 3M, 6M, 1Y, ALL)
    - PDF contains: equity curve with SPY overlay, key stats table (Sharpe, Sortino, Max DD, CAGR, Win Rate, Profit Factor), Monthly Returns Heatmap, drawdown chart, sector exposure, top 5 / bottom 5 performers
    - Uses `html2canvas` to capture chart DOM → `jspdf` to compose multi-page PDF
    - Professional layout: AlphaCent logo, title, date, period in header
    - Progress indicator during generation, disable button until complete
    - Partial report if sections fail, error message specifying unavailable sections
    - Filename: `AlphaCent_TearSheet_{period}_{YYYY-MM-DD}.pdf`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7_

  - [ ]* 13.3 Write unit tests for fuzzy search scoring and PDF filename generation
    - Test fuse.js search ranking for symbol/strategy/page queries
    - Test filename format: `AlphaCent_TearSheet_{period}_{YYYY-MM-DD}.pdf`
    - _Requirements: 14.7, 15.7_

- [x] 14. Checkpoint — Power user features build clean
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Responsive Layout & Design System Audit
  - [x] 15.1 Implement mobile responsive layout across all pages
    - Metric_Grid: 4 columns → 2 columns below 768px
    - GlobalSummaryBar: show only Equity + Daily P&L below 768px, horizontal scroll for rest
    - Charts: minimum 200px height on mobile
    - 2-column layouts: stack to single column below 640px
    - Test all pages at 640px, 768px, 1024px, 1440px breakpoints
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

  - [x] 15.2 Cross-page design system audit
    - Verify all pages use consistent card padding (16px), border radius (8px), border/bg colors from design tokens
    - Verify consistent color coding (green/red/blue/yellow) across all metric displays
    - Verify all charts use dark bg, grid lines, axis labels per chart theme
    - Verify all tables have alternating rows, sort icons, pagination
    - Verify font-mono for all numeric values, sans for labels
    - Fix any inconsistencies found
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 16. Final Checkpoint — Full build clean, all features integrated
  - Ensure all tests pass, ask the user if questions arise.
  - Update session continuation prompt.
  - Commit, push, ensure new code is in EC2, validate new UI/UX with user, iterate fixes.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation — each phase should build clean and be deployable
- Backend tasks create new API endpoints; frontend tasks consume them
- The existing tech stack (React 19, Recharts, Tailwind CSS 4, Radix UI, Zustand) is preserved throughout
- New dependencies: html2canvas, jspdf, @tanstack/react-virtual, fuse.js, react-resizable-panels
- New routes: `/system-health`, `/audit-log`, `/portfolio/:symbol`
- New Sidebar nav items: System Health, Audit Log (migrated to TopNavBar)

---

---

## Phase 2: QuantFury-Inspired Layout Overhaul (Requirements 22-30)

This phase transforms the AlphaCent layout from a sidebar + vertical-scroll pattern into a QuantFury-inspired horizontal-nav + multi-panel command-center layout. Every page gets a panel layout, every page gets the bottom widget zone, every table gets dense styling. All existing functionality is preserved.

- [x] 17. Layout Foundation — All Shared Components + Dependencies + Backend
  - [x] 17.1 Install react-resizable-panels and build all shared layout components
    - Run `npm install react-resizable-panels` in `frontend/`
    - Create `frontend/src/components/TopNavBar.tsx` — horizontal nav replacing Sidebar: brand left, nav links center (Overview, Portfolio, Orders, Strategies, Autonomous, Risk, Analytics, Data, System, Audit, Settings), account actions right (theme toggle, sync, notifications, user dropdown + logout). Active page: green bottom border + green text. Max 48px. Overflow scroll below 1280px. Hamburger menu below 768px. Preserve badge counts, permission filtering, user info.
    - Create `frontend/src/components/MetricsBar.tsx` — merges Header + GlobalSummaryBar into single 40px row: connection dot, Equity, Daily P&L ($ and %), Positions, Strategies, Regime badge, Health score, Last Synced. Green/red P&L, yellow on WS disconnect. Condensed Multi-Timeframe at >1440px.
    - Create `frontend/src/components/PositionTickerStrip.tsx` — horizontal scrollable strip (36px), top 15 positions by value: symbol, price, P&L % (green/red). Click → `/portfolio/:symbol`. WS-driven updates with flash animation. Hidden below 768px.
    - Create `frontend/src/components/layout/PanelHeader.tsx` — darker bg than panel body, title left, action icons right (collapse/expand, refresh, optional close). Collapse persisted to localStorage.
    - Create `frontend/src/components/layout/ResizablePanelLayout.tsx` — wraps react-resizable-panels. Horizontal/vertical splits, min 250px panels, CSS-based resize during drag, persist sizes to localStorage, single-column below 1024px.
    - Create `frontend/src/components/PageTemplate.tsx` — consistent page shell: header zone (64px, title + actions), main content zone (fills remaining), bottom widget zone (BottomWidgetZone). Used by ALL pages.
    - Create `frontend/src/components/trading/CompactMetricRow.tsx` — single horizontal row, 4-8 metrics inline (label + value + trend), max 40px height.
    - Create `frontend/src/components/BottomWidgetZone.tsx` — horizontal row of closable mini-widgets, each with title bar + close (×), max 200px height, internal scroll, visibility persisted to localStorage, stacks vertically below 1024px. Rendered by PageTemplate, available on ALL pages.
    - Create `frontend/src/components/widgets/TopMoversWidget.tsx` — top 5 gainers + top 5 losers from open positions by daily P&L %
    - Create `frontend/src/components/widgets/RecentSignalsWidget.tsx` — last 5 signals with conviction score, direction, symbol
    - Create `frontend/src/components/widgets/MarketRegimeWidget.tsx` — compact regime for 4 asset classes
    - Create `frontend/src/components/widgets/StrategyAlertsWidget.tsx` — recent activations, retirements, pending closures
    - Create `frontend/src/components/widgets/MacroPulseWidget.tsx` — VIX, Fed Funds, 10Y Treasury, Yield Curve, Inflation from existing regime endpoint
    - Update `frontend/src/components/ui/Table.tsx` — add DenseTable variant: 32px rows, 12px font, 8px/4px padding. Apply as default to ALL data tables platform-wide (positions, orders, strategies, template rankings, blacklists, audit log, data quality, risk tables, autonomous tables).
    - Update `frontend/src/components/ui/Card.tsx` — reduce padding to 12px (p-3), CardTitle to text-base. Replace ALL CardHeader usage across the platform with PanelHeader for consistent visual structure (darker header bg + action icons on every card section, including cards inside tab content on Analytics, Strategies, Risk, etc.).
    - _Requirements: 22.1-22.8, 23.1-23.8, 24.1-24.7, 25.1-25.7, 26.1-26.6, 27.1-27.5, 29.1-29.4_

  - [x] 17.2 Backend: Widget data endpoints
    - Create `GET /dashboard/top-movers?mode=DEMO` in `src/api/routers/account.py` — top 5 gainers + top 5 losers from open positions by daily P&L %
    - Create `GET /dashboard/recent-signals?mode=DEMO&limit=5` in `src/api/routers/strategies.py` — last N signals with conviction score, direction, symbol, strategy, timestamp
    - Create `GET /dashboard/strategy-alerts?mode=DEMO&limit=10` in `src/api/routers/strategies.py` — recent lifecycle events (activations, retirements, pending closures, demotions)
    - Macro data already available from existing `/analytics/regime-comprehensive` endpoint
    - _Requirements: 25.2, 25.6_

  - [x] 17.3 Restructure DashboardLayout
    - Update `frontend/src/components/DashboardLayout.tsx`:
      - Remove Sidebar, existing header, GlobalSummaryBar
      - New structure: `flex flex-col h-screen` → TopNavBar → MetricsBar → PositionTickerStrip → `<main>` (full width)
    - Verify all 11 pages still render correctly
    - _Requirements: 22.1, 22.5, 22.8_

- [ ] 18. Checkpoint — Layout foundation builds clean
  - Verify `npm run build` succeeds
  - Verify TopNavBar renders with correct active states and hamburger menu
  - Verify MetricsBar shows all metrics correctly
  - Verify PositionTickerStrip shows positions with live data
  - Verify all shared components (PanelHeader, ResizablePanelLayout, PageTemplate, CompactMetricRow, BottomWidgetZone, all widgets) render correctly

- [x] 19. Page Redesigns — Every Page Gets Panel Layout + PageTemplate + Widgets
  - [x] 19.1 Overview — 3-panel command center
    - PageTemplate + ResizablePanelLayout: Left (25%): CompactMetricRow + MultiTimeframeView + Strategy Pipeline. Center (50%): EquityCurveChart hero (min 400px, fills vertical, toolbar with PeriodSelector + benchmark toggle + fullscreen). Right (25%): Recent Trades + Position Summary by Asset Class. Center panel is the dominant element (≥60% of non-sidebar content area). All panels use PanelHeader. BottomWidgetZone below.
    - _Requirements: 23.3, 28.1-28.4_

  - [x] 19.2 Portfolio — 2-panel with position focus
    - PageTemplate + ResizablePanelLayout: Main (70%): positions table (DenseTable) with sparklines, tabs within. Side (30%): position summary by asset class + sector exposure pie + allocation bar. PanelHeader on each. BottomWidgetZone below.
    - _Requirements: 23.4_

  - [x] 19.3 Orders — 2-panel with timeline prominence
    - PageTemplate + ResizablePanelLayout: Main (65%): OrderFlowTimeline hero (top 40%) + orders DenseTable with tabs (bottom 60%). Side (35%): CompactMetricRow (total orders, fill rate, avg slippage, pending) + execution quality mini-chart + recent fills list. PanelHeader on each. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.4 Strategies — 2-panel with rankings sidebar
    - PageTemplate + ResizablePanelLayout: Main (65%): strategy DenseTable with sparklines + all existing tabs (all tables within tabs also use DenseTable). Side (35%): CompactMetricRow (active, backtested, avg Sharpe, avg win rate) + top 5 template rankings mini-table + recent lifecycle events list. PanelHeader on each panel and on card sections within tabs. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.5 Autonomous — 2-panel with cycle visibility
    - PageTemplate + ResizablePanelLayout: Main (65%): all existing tabs (tables within tabs use DenseTable). Side (35%): CompactMetricRow (cycle status, pass rate, proposals this week, active count) + cycle progress indicator + WF pass rate sparkline + recent similarity rejections. PanelHeader on each panel and on card sections within tabs. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.6 Risk — 2-panel with correlation hero
    - PageTemplate + ResizablePanelLayout: Main (60%): CorrelationHeatmap hero (top 50%) + tabs below (tables within tabs use DenseTable). Side (40%): CompactMetricRow (VaR, max sector exposure, long/short ratio, beta) + sector exposure pie + risk contribution top 5 bar. PanelHeader on each panel and on card sections within tabs. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.7 Analytics — full-width with compact metrics
    - PageTemplate (no side panel — tab content is data-dense): CompactMetricRow at top (total return, Sharpe, max DD, win rate, profit factor, trades) + 10 tabs below. Each tab's card sections use PanelHeader. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.8 Data Management — 2-panel with quality focus
    - PageTemplate + ResizablePanelLayout: Main (65%): data quality DenseTable (297 symbols). Side (35%): CompactMetricRow (healthy/degraded/stale counts, avg score) + data source health cards + FMP cache + sync progress. PanelHeader on each. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.9 System Health — 2-panel with alerts focus
    - PageTemplate + ResizablePanelLayout: Main (60%): 24h event timeline hero (top 40%) + service status cards below. Side (40%): circuit breaker cards (prominent, color-coded) + CompactMetricRow (uptime, error rate, response, cache hit). PanelHeader on each. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.10 Audit Log — 2-panel with lifecycle sidebar
    - PageTemplate + ResizablePanelLayout: Main (65%): audit DenseTable (virtual scroll) + filters bar. Side (35%): CompactMetricRow (events today, warnings, errors, rejections) + signal rejections summary + lifecycle events summary + risk limit events summary. PanelHeader on each. BottomWidgetZone below.
    - _Requirements: 29.2_

  - [x] 19.11 Settings — full-width with tabs
    - PageTemplate (no side panel — form-based content): tabs as-is. BottomWidgetZone below.
    - _Requirements: 29.2_

- [ ] 20. Checkpoint — All 11 page redesigns build clean
  - Verify `npm run build` succeeds
  - Verify every page renders with PageTemplate + appropriate panel layout
  - Verify PanelHeader on all panels, CompactMetricRow on all pages with metrics
  - Verify DenseTable on all data tables
  - Verify BottomWidgetZone accessible and functional on every page
  - Verify responsive degradation below 1024px on all pages

- [x] 21. Micro-Interactions and Visual Polish
  - [x] 21.1 Animated number transitions — create/update `animated-number.tsx`, count-up/down over 300ms. Apply to MetricsBar, PositionTickerStrip, CompactMetricRow on all pages. _Req: 30.1_
  - [x] 21.2 Value flash on WS update — create/update `flash-wrapper.tsx`, green/red 20% opacity flash fading 500ms. Apply to PositionTickerStrip, MetricsBar. _Req: 30.2_
  - [x] 21.3 Hover glow — Card border-color transition on hover, table row highlight, resize handle highlight, ticker chip scale(1.02). _Req: 30.3, 30.4, 30.6_
  - [x] 21.4 Tab content fade-in — update TabsContent with 150ms fade-in on switch. _Req: 30.5_

- [ ] 22. Checkpoint — Micro-interactions build clean

- [x] 23. Final Integration + Cross-Page Audit + Cleanup
  - [x] 23.1 Full cross-page visual audit — navigate all 11 pages, verify TopNavBar active state, MetricsBar accuracy, PanelHeader consistency, PageTemplate applied, DenseTable used, CompactMetricRow present, BottomWidgetZone functional. Test at 640px, 768px, 1024px, 1440px, 1920px. Fix inconsistencies.
  - [x] 23.2 Performance audit — panel resize jank, WS update re-renders, ticker strip with 15+ updates, widget load impact, DenseTable with 297 rows.
  - [x] 23.3 Clean up deprecated components — remove Sidebar.tsx, GlobalSummaryBar.tsx, update all imports. Verify build clean.

- [x] 24. Final Checkpoint — Full QuantFury overhaul builds clean
  - `npm run build` succeeds
  - All 11 pages render correctly with new layout
  - Responsive behavior works at all breakpoints
  - BottomWidgetZone works on every page
  - Commit, push, deploy to EC2, validate with user


---

## Phase 3: Professional Charting + Real-Time Streaming + Workspace Presets (Requirements 31-33)

This phase replaces Recharts with TradingView Lightweight Charts for all time-series visualizations, adds real-time price streaming via WebSocket, and implements saved workspace presets. Recharts is fully removed after migration.

- [x] 25. TradingView Lightweight Charts Migration
  - [x] 25.1 Install lightweight-charts and build TvChart wrapper component
    - Run `npm install lightweight-charts` in `frontend/`
    - Create `frontend/src/components/charts/TvChart.tsx` — reusable wrapper around TradingView Lightweight Charts API. Supports: area, line, candlestick, histogram series. Props: data, chartType, theme (AlphaCent dark: bg #0a0e1a, grid #1f2937, up #22c55e, down #ef4444, crosshair #9ca3af, text #f3f4f6), height, onCrosshairMove, timeRange. Handles chart creation, resize via ResizeObserver, cleanup on unmount.
    - Create `frontend/src/components/charts/TvPeriodSelector.tsx` — PeriodSelector that integrates with TvChart's time range API (setVisibleRange) instead of filtering data client-side.
    - _Requirements: 31.1, 31.4, 31.5_

  - [x] 25.2 Migrate EquityCurveChart to TradingView
    - Rewrite `frontend/src/components/charts/EquityCurveChart.tsx` using TvChart: portfolio as area series (blue), SPY as line series (gray dashed), alpha shading between them. Crosshair tooltip showing portfolio value, SPY value, alpha. Synchronized drawdown sub-chart below (separate TvChart instance sharing time range). "Benchmark unavailable" badge when SPY missing. PeriodSelector via TvPeriodSelector.
    - _Requirements: 31.2_

  - [x] 25.3 Migrate AssetPlot to TradingView candlestick chart
    - Rewrite `frontend/src/components/charts/AssetPlot.tsx` using TvChart: candlestick series for price data, volume histogram sub-chart, buy/sell markers (green ↑ / red ↓ at order dates/prices). Timeframe selector (5m, 15m, 1h, 4h, 1D) that fetches appropriate granularity data from backend.
    - Backend: extend `GET /account/positions/:symbol/detail` to accept `interval` param (5m/15m/1h/4h/1d) and return OHLCV data at that granularity from historical_price_cache or eToro API.
    - _Requirements: 31.3_

  - [x] 25.4 Migrate all remaining time-series charts to TradingView
    - Migrate InteractiveChart usages across all pages to TvChart: rolling statistics charts (Analytics), equity trend charts (Strategies sparklines can stay as simple SVG), execution quality trend (TCA), walk-forward pass rate (Autonomous), portfolio turnover (Risk), long/short exposure (Risk), order flow timeline (Orders), 24h event timeline (System Health).
    - For each migration: replace Recharts ResponsiveContainer + Line/Area/Bar with TvChart, preserve existing data flow and PeriodSelector behavior.
    - _Requirements: 31.1, 31.4_

  - [x] 25.5 Implement non-time-series chart alternatives
    - Verify that non-time-series visualizations remain functional without Recharts: CorrelationHeatmap (custom Canvas/SVG), ReturnDistribution histogram (custom SVG or lightweight bar renderer), MonthlyReturnsHeatmap (custom grid), sector exposure pie (custom SVG), stacked bar charts (custom SVG).
    - Where these currently use Recharts BarChart/PieChart, replace with lightweight custom SVG components or a minimal utility like `d3-shape` for path generation only (no full D3 dependency).
    - _Requirements: 31.8_

  - [x] 25.6 Remove Recharts dependency
    - Remove `recharts` from `package.json`
    - Run `npm uninstall recharts`
    - Verify `npm run build` succeeds with zero Recharts imports remaining
    - Verify bundle size reduction
    - _Requirements: 31.7_

- [ ] 26. Checkpoint — TradingView migration builds clean
  - Verify `npm run build` succeeds with no Recharts references
  - Verify EquityCurveChart renders with TradingView (area + SPY overlay + drawdown)
  - Verify AssetPlot renders candlesticks with order markers
  - Verify all other time-series charts render with TradingView
  - Verify non-time-series charts (heatmaps, histograms, pies) still render correctly
  - Verify chart theme matches AlphaCent dark theme

- [-] 27. Real-Time Price Streaming
  - [x] 27.1 Backend: WebSocket price streaming for chart symbols
    - Extend `src/services/websocket.py` (or equivalent) to emit `price_tick` events when the monitoring service's quick price update runs (every 10 min) or when position sync detects price changes. Event payload: `{ symbol, price, timestamp, open, high, low, close, volume }`.
    - Alternatively, if eToro API supports streaming: wire eToro price stream → WebSocket broadcast for symbols with open positions.
    - _Requirements: 32.1_

  - [x] 27.2 Frontend: Wire WebSocket price ticks to TradingView charts
    - Update TvChart wrapper to accept an `onNewTick` callback that appends a data point to the active series via `series.update()` (TradingView Lightweight Charts API).
    - Update PositionDetailView to subscribe to `price_tick` events for the viewed symbol and feed ticks to the AssetPlot TvChart.
    - Update EquityCurveChart to subscribe to portfolio equity updates and append to the area series.
    - Show "Live data paused" indicator on chart when WebSocket disconnects, auto-resume on reconnect.
    - _Requirements: 32.1, 32.2, 32.3, 32.4, 32.5_

- [ ] 28. Checkpoint — Real-time streaming works
  - Verify AssetPlot candlestick chart updates in real-time when price ticks arrive
  - Verify EquityCurveChart updates with portfolio equity changes
  - Verify no chart flicker or performance degradation during streaming
  - Verify "Live data paused" indicator shows on WS disconnect

- [x] 29. Saved Workspace Presets
  - [x] 29.1 Build workspace preset system
    - Create `frontend/src/lib/workspace-presets.ts` — manages saving/loading/switching workspace presets in localStorage. Each preset stores: per-page panel sizes, collapsed panel states, widget visibility, active tab per page.
    - Up to 5 user presets + 3 default presets ("Trading", "Monitoring", "Analysis").
    - "Trading" default: chart-dominant panels, position ticker prominent, widgets showing Top Movers + Recent Signals.
    - "Monitoring" default: system health + alerts prominent, widgets showing Strategy Alerts + Market Regime.
    - "Analysis" default: analytics tabs prominent, widgets showing Macro Pulse + Market Regime.
    - _Requirements: 33.1, 33.2, 33.5_

  - [x] 29.2 Build workspace switcher UI
    - Add workspace switcher dropdown to TopNavBar (right side, near account actions) or PageTemplate header.
    - Shows: current preset name, list of saved presets, "Save Current" button, "Reset to Default" button.
    - Switching presets transitions layout within 300ms.
    - _Requirements: 33.3, 33.4_

- [ ] 30. Checkpoint — Workspace presets work
  - Verify presets save and restore correctly
  - Verify switching between presets transitions smoothly
  - Verify default presets provide sensible layouts

- [ ] 31. Final Phase 3 Audit + Deploy
  - [ ] 31.1 Full visual audit — verify all charts render with TradingView theme, real-time streaming works, presets save/load correctly, no Recharts remnants, bundle size improved.
  - [ ] 31.2 Performance audit — chart rendering performance with TradingView (60fps zoom/pan), streaming performance (no jank with 1-10s tick intervals), preset switching speed (<300ms).
  - [ ] 31.3 Cross-browser check — verify TradingView charts render correctly in Chrome, Firefox, Safari.

- [ ] 32. Final Checkpoint — Phase 3 complete
  - `npm run build` succeeds, Recharts fully removed
  - All time-series charts use TradingView Lightweight Charts
  - Real-time price streaming works on position detail and equity curve
  - Workspace presets save/load/switch correctly
  - Commit, push, deploy to EC2, validate with user
