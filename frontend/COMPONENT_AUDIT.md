# Component Audit - Task 7.11

## Pages Analysis

### Active Pages (Used in App.tsx routing)
- ✅ OverviewNew.tsx (as Overview)
- ✅ PortfolioNew.tsx (as Portfolio)
- ✅ OrdersNew.tsx (as OrdersPage)
- ✅ StrategiesNew.tsx (as StrategiesPage)
- ✅ AutonomousNew.tsx (as Autonomous)
- ✅ RiskNew.tsx (as Risk)
- ✅ AnalyticsNew.tsx (as Analytics)
- ✅ SettingsNew.tsx
- ✅ Login.tsx

### Duplicate/Unused Pages (TO DELETE)
- ❌ Analytics.tsx (replaced by AnalyticsNew.tsx)
- ❌ Autonomous.tsx (replaced by AutonomousNew.tsx)
- ❌ Dashboard.tsx (replaced by OverviewNew.tsx)
- ❌ Home.tsx (replaced by OverviewNew.tsx)
- ❌ Market.tsx (not used in routing)
- ❌ OrdersPage.tsx (replaced by OrdersNew.tsx)
- ❌ Overview.tsx (replaced by OverviewNew.tsx)
- ❌ OverviewTabbed.tsx (replaced by OverviewNew.tsx)
- ❌ Portfolio.tsx (replaced by PortfolioNew.tsx)
- ❌ Risk.tsx (replaced by RiskNew.tsx)
- ❌ Settings.tsx (replaced by SettingsNew.tsx)
- ❌ StrategiesPage.tsx (replaced by StrategiesNew.tsx)
- ❌ System.tsx (not used in routing)
- ❌ Trading.tsx (not used in routing)

## Components Analysis

### Core Components (KEEP - Used by new pages)
- ✅ DashboardLayout.tsx (used by all pages)
- ✅ MetricCard.tsx (trading/MetricCard.tsx - used extensively)
- ✅ DataTable.tsx (trading/DataTable.tsx - used extensively)
- ✅ InlineTerminal.tsx (used by AutonomousNew)
- ✅ NotificationToast.tsx (used in App.tsx)
- ✅ AutonomousNotificationToast.tsx (used in App.tsx)
- ✅ ProtectedRoute.tsx (used in App.tsx)
- ✅ Sidebar.tsx (used by DashboardLayout)
- ✅ WebSocketIndicator.tsx (likely used by DashboardLayout)

### UI Components (KEEP - shadcn/ui library)
All components in `components/ui/` are part of the design system and should be kept.

### Potentially Unused Components (TO REVIEW/DELETE)
- ❓ AccountOverview.tsx (check if used in any new page)
- ❓ AutonomousControlPanel.tsx (check if used in AutonomousNew)
- ❓ AutonomousSettings.tsx (check if used in SettingsNew)
- ❓ AutonomousStatus.tsx (check if used in OverviewNew or AutonomousNew)
- ❓ BackendStatus.tsx (check if used)
- ❓ BacktestResults.tsx (check if used)
- ❓ ControlPanel.tsx (check if used)
- ❓ ErrorMessage.tsx (check if replaced by better error handling)
- ❓ HistoryAnalytics.tsx (check if used in AnalyticsNew)
- ❓ LoadingSpinner.tsx (check if replaced by loading/index.ts)
- ❓ ManualOrderEntry.tsx (check if used)
- ❓ MarketData.tsx (check if used)
- ❓ NotificationDemo.tsx (example file - DELETE)
- ❓ NotificationHistory.tsx (check if used)
- ❓ Notifications.tsx (check if replaced by NotificationToast)
- ❓ NotificationSettings.tsx (check if used in SettingsNew)
- ❓ Orders.tsx (check if replaced by OrdersNew page)
- ❓ PerformanceCharts.tsx (check if used)
- ❓ PerformanceDashboard.tsx (check if used)
- ❓ PortfolioComposition.tsx (check if used)
- ❓ Positions.tsx (check if used)
- ❓ RecentTrades.tsx (check if used)
- ❓ ServicesStatus.tsx (check if used)
- ❓ ServiceUnavailable.tsx (check if used)
- ❓ SignalFeed.tsx (check if used)
- ❓ SignalGenerationStatus.tsx (check if used)
- ❓ SkeletonLoader.tsx (check if replaced by loading/index.ts)
- ❓ Strategies.tsx (check if replaced by StrategiesNew page)
- ❓ StrategyGenerator.tsx (check if used)
- ❓ StrategyLifecycle.tsx (check if used)
- ❓ StrategyReasoningPanel.tsx (check if used)
- ❓ SystemStatusHome.tsx (check if used)
- ❓ TerminalConsole.tsx (check if replaced by InlineTerminal)

### Example Files (TO DELETE)
- ❌ BacktestResults.example.tsx
- ❌ SignalFeed.example.tsx
- ❌ StrategyReasoningPanel.example.tsx
- ❌ examples/ApiServiceExample.tsx
- ❌ examples/DesignSystemExample.tsx
- ❌ examples/LoadingErrorStatesExample.tsx
- ❌ examples/ModernDesignSystemExample.tsx
- ❌ examples/WebSocketAutonomousExample.tsx

### Documentation Files (TO DELETE - keep only main docs)
- ❌ BACKTEST_RESULTS_INTEGRATION.md
- ❌ CONTROL_PANEL_IMPLEMENTATION.md
- ❌ LOADING_ERROR_STATES.md
- ❌ NOTIFICATION_SYSTEM_IMPLEMENTATION.md

## Action Plan

1. Search for actual usage of questionable components in new pages
2. Delete confirmed unused pages
3. Delete confirmed unused components
4. Delete example files
5. Delete redundant documentation
6. Update imports if needed
7. Clean up component directory structure
