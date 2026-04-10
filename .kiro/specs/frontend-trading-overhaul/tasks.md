# Implementation Plan: Frontend Trading Overhaul

## Overview

Comprehensive frontend overhaul of the AlphaCent trading platform. The implementation is grouped into 7 tasks: shared infrastructure first (dependency for all others), then page-specific fixes in parallel, cross-cutting integration, and finally new pages/features. All code is TypeScript/React.

## Tasks

- [x] 1. Shared Infrastructure — Hooks, utilities, and shared components
  - [x] 1.1 Create `usePolling` hook in `frontend/src/hooks/usePolling.ts`
    - Implement `UsePollingOptions` / `UsePollingReturn` interfaces per design
    - Visibility-aware pausing via `document.addEventListener('visibilitychange')`
    - Immediate fetch on tab-visible and on WebSocket reconnection (`wsManager.onConnectionStateChange`)
    - Concurrent-fetch guard with `useRef` flag
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_
  - [x] 1.2 Create `formatTimestamp` utility, `classifyError` utility, and skeleton components
    - Add `formatTimestamp(dateInput, options?)` to `frontend/src/lib/utils.ts` using `Intl.DateTimeFormat` with `timeZoneName: 'short'`
    - Create `frontend/src/lib/errors.ts` with `classifyError(error, dataName): ClassifiedError` — inspect AxiosError shape for network/5xx/auth/client/unknown
    - Create reusable skeleton loading components in `frontend/src/components/ui/Skeleton.tsx` for cards, tables, and charts
    - _Requirements: 7.1–7.5, 12.1–12.4, 11.1–11.7_
  - [x] 1.3 Create `DataFreshnessIndicator`, `ConfirmDialog`, and `PageErrorBoundary` components
    - `frontend/src/components/ui/DataFreshnessIndicator.tsx` — green (<2min), amber (2–5min), red (>5min "Stale data"), 10s re-eval interval
    - `frontend/src/components/ui/ConfirmDialog.tsx` — built on Radix Dialog, loading state on confirm button
    - `frontend/src/components/PageErrorBoundary.tsx` — wraps existing ErrorBoundary with page-specific fallback showing page name + "Reload Page" button
    - _Requirements: 27.1–27.4, 13.1–13.4, 14.1–14.4_
  - [ ]* 1.4 Write property tests for shared infrastructure
    - **Property 2: usePolling calls fetchFn at the configured interval** — `frontend/src/__tests__/properties/usePolling.property.test.ts`
    - **Property 3: usePolling pauses when hidden and resumes with immediate fetch when visible**
    - **Property 4: usePolling fetches immediately on WebSocket reconnection**
    - **Property 5: formatTimestamp always includes a timezone abbreviation** — `frontend/src/__tests__/properties/formatTimestamp.property.test.ts`
    - **Property 6: classifyError produces contextual error messages** — `frontend/src/__tests__/properties/classifyError.property.test.ts`
    - **Property 7: DataFreshnessIndicator shows correct staleness level** — `frontend/src/__tests__/properties/freshnessIndicator.property.test.ts`
    - **Property 19: PageErrorBoundary shows page-specific error** — `frontend/src/__tests__/properties/pageErrorBoundary.property.test.ts`
    - **Validates: Requirements 3, 7, 12, 27, 14**

- [x] 2. Risk Page Fixes — `RiskNew.tsx` only
  - [x] 2.1 Fix hardcoded values and remove mock data generators
    - Replace `100000` in `getRiskStatus()` with actual `accountBalance` from backend `AccountInfo`
    - Fetch `AccountInfo` in `fetchRiskData` and use `account.balance` for position size %, portfolio exposure %, and risk status
    - Show "Calculating..." when `accountBalance` is unavailable
    - Remove `generateRiskHistory()` and `generateCorrelationMatrix()` functions entirely
    - Replace mock fallbacks with "Data unavailable" message + retry button in risk history chart and correlation matrix areas
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4_
  - [x] 2.2 Integrate `usePolling` and shared utilities into Risk page
    - Add `usePolling({ fetchFn: fetchRiskData, intervalMs: 60000 })` per Req 3.4
    - Use `formatTimestamp` for risk alert timestamps, `classifyError` for error states
    - Add `DataFreshnessIndicator` to page header
    - Use `formatCurrency`/`formatPercentage` consistently for all monetary/percentage values
    - _Requirements: 3.4, 7.5, 8.5, 12.1–12.4, 27.1–27.4_
  - [ ]* 2.3 Write property test for risk calculations
    - **Property 1: Risk metrics use actual account balance** — `frontend/src/__tests__/properties/riskCalculations.property.test.ts`
    - **Validates: Requirements 1.1, 1.2, 1.3**

- [x] 3. Dashboard, Header, Layout, and Sidebar
  - [x] 3.1 Add P&L ticker to header and per-page error boundaries in App.tsx
    - In `DashboardLayout.tsx`: fetch daily P&L from `apiClient.getAccountInfo()`, display formatted value + percentage in header, color green/red, update on WS position events, poll every 30s as fallback
    - In `App.tsx`: wrap each `<Route>` element with `<PageErrorBoundary pageName="...">` inside `<DashboardLayout>`, keep top-level `<ErrorBoundary>` as final fallback
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 14.1, 14.2, 14.3, 14.4_
  - [x] 3.2 Fix auth validation and add regime change notifications
    - In `App.tsx`: replace optimistic auth with lightweight loading indicator during background `authService.checkStatus()`, redirect to login within 2s on invalid session with toast, disable nav/data-fetching while validating
    - Add regime change detection: store last regime in localStorage, compare on WS/polling updates, show toast with previous→new regime and link to Dashboard
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 17.1, 17.2, 17.3_
  - [x] 3.3 Integrate `usePolling` and shared utilities into Overview and Sidebar
    - In `OverviewNew.tsx`: add `usePolling({ fetchFn: fetchDashboard, intervalMs: 30000 })`, add skeleton loading, `DataFreshnessIndicator`, `formatTimestamp` for timestamps, use `formatPercentage` instead of inline `.toFixed(2)`, label P&L period cards clearly (realized/unrealized/combined)
    - In `DashboardLayout.tsx`: use `usePolling` for badge count fetching (30s), ensure WS events update badges within 2s
    - Add Watchlist nav item to `Sidebar.tsx` (path: `/watchlist`, icon: `◧`)
    - _Requirements: 3.1, 5.1–5.5, 8.1, 11.1, 20.1, 20.2, 20.3, 26.4, 26.5, 27.1–27.4_
  - [ ]* 3.4 Write property tests for header and layout
    - **Property 9: P&L color matches sign** — `frontend/src/__tests__/properties/pnlColor.property.test.ts`
    - **Property 17: Regime change detection across values** — `frontend/src/__tests__/properties/regimeChange.property.test.ts`
    - **Validates: Requirements 5.3, 17.1, 17.3**

- [x] 4. Portfolio Page Fixes — `PortfolioNew.tsx`
  - [x] 4.1 Add persistent banners and confirmation dialogs
    - Add `PendingClosureBanner` (amber) and `FundamentalAlertBanner` (red) at top of page above tabs — show count + summary, click to scroll/highlight position, auto-dismiss when resolved
    - Wire `ConfirmDialog` for single position close (show symbol, quantity, P&L), bulk close (list all positions + total P&L impact), and order cancellation
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 13.1, 13.2, 13.3, 13.4_
  - [x] 4.2 Fix P&L labels and integrate shared utilities
    - Rename "Daily P&L" → "Unrealized P&L", "Win Rate" → "Positions in Profit" for open positions
    - Add "Win Rate (Closed)" metric from closed positions (wins / total closed)
    - Add `usePolling({ fetchFn: fetchData, intervalMs: 15000 })`, skeleton loading, `DataFreshnessIndicator`
    - Use `formatTimestamp` for opened_at/closed_at, `classifyError` for error states, `formatPercentage` consistently
    - Show loading indicator for Pending Closures and Fundamental Alerts sections while background-fetching
    - _Requirements: 26.1, 26.2, 26.3, 3.2, 7.2, 8.2, 11.2, 25.4, 27.1–27.4_
  - [ ]* 4.3 Write property tests for portfolio features
    - **Property 8: Pending closure and alert banners reflect list state** — `frontend/src/__tests__/properties/banners.property.test.ts`
    - **Property 16: Closed positions win rate calculation** — `frontend/src/__tests__/properties/winRate.property.test.ts`
    - **Property 18: Bulk close confirmation lists all selected positions** — `frontend/src/__tests__/properties/bulkClose.property.test.ts`
    - **Validates: Requirements 6.1, 6.2, 6.4, 6.5, 26.3, 13.3**

- [x] 5. Autonomous, Pipeline, and Data Management Pages
  - [x] 5.1 Fix Trading Cycle Pipeline metric mapping and Autonomous page layout
    - In `TradingCyclePipeline.tsx`: fix `buildMetricsSummary()` to read `retired` from `cleanup_retirement`, `signals_generated` from `signal_generation`, `orders_submitted` from `order_submission`; map `approved` → "Activated"; show `total_active` from activation stage; display "—" for null/undefined metrics
    - In `AutonomousNew.tsx`: move `TradingCyclePipeline` to top of Control & Status tab below status badges; remove Quick Actions card; merge Control Panel + Scheduled Execution into "Controls" section; merge System Status + Research Filters into "System" section; 2-column grid layout; add compact metric row (Active Strategies, Open Positions, Last Signal, Market Regime) above pipeline
    - _Requirements: 21.1–21.6, 22.1–22.6_
  - [x] 5.2 Fix cycle counting and enhance Data Management page
    - In `AutonomousNew.tsx`: separate "Last Cycle" vs "Cumulative" metrics; label as "Total" vs "Last Cycle"; source last cycle from `getAutonomousCycles` most recent entry; show duration, proposals, backtest pass rate, net activations
    - In `DataManagementNew.tsx`: add Data Quality section (from backend quality report endpoint); add Symbol Coverage section showing stale symbols (>2h hourly, >1d daily); add per-symbol/asset-class sync trigger; add stale data warning banner (>10% stale); promote FMP API usage to prominent progress bar
    - _Requirements: 24.1–24.4, 23.1–23.5_
  - [x] 5.3 Integrate `usePolling` and shared utilities into Autonomous and Data Management pages
    - Add `usePolling` to AutonomousNew (60s) and DataManagementNew (30s)
    - Add skeleton loading, `DataFreshnessIndicator`, `classifyError` error handling, `formatTimestamp` for timestamps
    - _Requirements: 3.5, 3.6, 7.1, 7.4, 11.5, 11.6, 12.1–12.4, 27.1–27.4_
  - [ ]* 5.4 Write property tests for pipeline and cycle metrics
    - **Property 10: Cycle pipeline metric mapping reads from correct stages** — `frontend/src/__tests__/properties/pipelineMetrics.property.test.ts`
    - **Property 14: Stale symbol detection and warning threshold** — `frontend/src/__tests__/properties/staleSymbols.property.test.ts`
    - **Property 15: Last cycle metrics sourced from cycle history** — `frontend/src/__tests__/properties/cycleMetrics.property.test.ts`
    - **Validates: Requirements 21.1–21.6, 23.2, 23.4, 24.3, 24.4**

- [ ] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Cross-Cutting Polish — Integrate shared infrastructure across all pages
  - [x] 7.1 Standardize formatting, tooltips, and error handling across Orders, Analytics, and Strategies pages
    - In `OrdersNew.tsx`: add `usePolling` (15s), skeleton loading, `DataFreshnessIndicator`, `classifyError` error states with retry, `formatTimestamp` for order timestamps, `formatCurrency` for all monetary values, `ConfirmDialog` for order cancellation
    - In `AnalyticsNew.tsx`: add `usePolling` (120s), skeleton loading, `DataFreshnessIndicator`, tab data caching with 5-min invalidation, `formatTimestamp` for trade journal timestamps
    - In `StrategiesNew.tsx`: add `usePolling` (60s), skeleton loading, `DataFreshnessIndicator`, Radix tooltip for truncated strategy names (300ms delay, dark theme)
    - _Requirements: 3.3, 3.5, 7.3, 7.4, 8.3, 8.4, 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 10.4, 11.3, 11.5, 11.6, 12.1–12.4, 13.2, 27.1–27.4_
  - [x] 7.2 Ensure consistent error handling and secondary data patterns across all pages
    - Apply `classifyError` to all API error paths on every page
    - Ensure primary data uses `Promise.all` (blocks render), secondary data uses non-blocking calls with individual `InlineError` indicators
    - Add retry buttons for all failed data sections
    - Ensure all pages show subtle refresh indicator during polling (not replacing content)
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 11.7, 12.1–12.4_
  - [x] 7.3 Standardize P&L formatting and percentage base indicators
    - Audit all pages for inline `.toFixed()` calls and replace with `formatCurrency`/`formatPercentage`
    - Ensure all P&L percentages indicate whether base is equity or balance
    - _Requirements: 8.1–8.5, 26.4, 26.5_
  - [ ]* 7.4 Write property test for analytics tab caching
    - **Property 20: Analytics tab cache invalidation after 5 minutes** — `frontend/src/__tests__/properties/tabCache.property.test.ts`
    - **Validates: Requirements 10.4**

- [x] 8. New Pages and Features
  - [x] 8.1 Create WatchlistPage
    - Create `frontend/src/pages/WatchlistPage.tsx` with DataTable (TanStack Table): columns for symbol, price, daily change ($), daily change (%), volume
    - Add asset class dropdown filter and text search
    - Use `usePolling` (30s) and `wsManager.onMarketData` for real-time row updates
    - Add skeleton loading, `DataFreshnessIndicator`, `classifyError` error handling
    - Add route in `App.tsx` (`/watchlist`) and nav item in `Sidebar.tsx`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6_
  - [x] 8.2 Add strategy comparison view to StrategiesNew
    - Add "Compare" action allowing two-strategy selection via checkboxes
    - Side-by-side card layout comparing: total return, Sharpe ratio, max drawdown, win rate, total trades, allocation %
    - Highlight better metric in green, worse in red (higher-is-better vs lower-is-better logic)
    - _Requirements: 16.1, 16.2, 16.3_
  - [x] 8.3 Add manual order form and execution quality tab to OrdersNew
    - Add "New Order" button opening Radix Dialog form: symbol (searchable), side (BUY/SELL), order type (MARKET/LIMIT), quantity, price (conditional on LIMIT)
    - Two-step flow: fill form → review step → submit via `apiClient.submitOrder()`
    - Inline validation errors for invalid inputs
    - Add "Execution Quality" tab: aggregate metrics (avg slippage, fill rate, avg fill time), Recharts bar chart for slippage distribution, sortable DataTable for per-order metrics, "Data unavailable" fallback with retry
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 19.1, 19.2, 19.3, 19.4_
  - [ ]* 8.4 Write property tests for new features
    - **Property 11: Watchlist filtering returns correct subset** — `frontend/src/__tests__/properties/watchlistFilter.property.test.ts`
    - **Property 12: Strategy comparison highlights the better metric** — `frontend/src/__tests__/properties/strategyComparison.property.test.ts`
    - **Property 13: Order form validation rejects invalid inputs** — `frontend/src/__tests__/properties/orderValidation.property.test.ts`
    - **Validates: Requirements 15.3, 15.4, 16.2, 16.3, 18.4**

- [ ] 9. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Task 1 (Shared Infrastructure) must be completed first — all other tasks depend on it
- Tasks 2–5 can be done in parallel after Task 1
- Task 7 (Cross-Cutting Polish) depends on Tasks 1–5
- Task 8 (New Pages/Features) depends on Task 1
- Property tests validate universal correctness properties from the design document
- All code is TypeScript/React using the existing Vite + Tailwind + Radix + Recharts stack
