# Requirements Document: Autonomous Trading UI Overhaul

## Introduction

This document specifies the requirements for overhauling the AlphaCent trading platform frontend to properly represent the autonomous trading system. The current frontend contains outdated references to LLM-based strategy generation and "Vibe Coding" features that are no longer the primary approach. The backend system now uses DSL-based rule interpretation and template-based strategy generation, with fully autonomous strategy proposal, backtesting, activation, and portfolio management capabilities.

The overhaul will remove deprecated Vibe Coding UI components and create a comprehensive monitoring and visualization interface for the autonomous trading system. The focus is on leveraging existing backend capabilities including AutonomousStrategyManager, PortfolioManager, PerformanceDegradationMonitor, MetaStrategy, correlation analysis, position sizing, stop-loss/take-profit management, and market regime detection. All features must use real backend data through existing APIs - no mocks or simulated data.

## Glossary

- **Autonomous_Trading_System**: The backend system that autonomously proposes, backtests, activates, and manages trading strategies without human intervention
- **DSL**: Domain-Specific Language used for defining trading rules and strategy logic
- **Template**: Pre-defined strategy pattern with configurable parameters used for strategy generation
- **Strategy**: A trading algorithm with specific entry/exit rules, risk parameters, and target instruments
- **Market_Regime**: Current market condition classification (trending up, trending down, ranging, volatile)
- **Backtest**: Historical simulation of a strategy's performance using past market data
- **Walk_Forward_Validation**: Advanced backtesting technique that validates strategy performance across multiple time periods
- **Strategy_Pipeline**: The workflow stages a strategy goes through (proposed → backtesting → validated → activated → retired)
- **Portfolio_Manager**: Component responsible for managing active strategies, capital allocation, and risk limits
- **Performance_Degradation**: Condition where a strategy's live performance falls below acceptable thresholds
- **Sharpe_Ratio**: Risk-adjusted return metric (higher is better, >1.0 is good, >2.0 is excellent)
- **Maximum_Drawdown**: Largest peak-to-trough decline in portfolio value
- **VaR**: Value at Risk - statistical measure of potential portfolio loss
- **Position_Sizing**: Algorithm that determines how much capital to allocate to each trade
- **Vibe_Coding**: Deprecated LLM-based strategy generation feature to be removed
- **Frontend**: React/TypeScript web application providing the user interface
- **Backend**: Python-based trading system with APIs for data access
- **WebSocket**: Real-time bidirectional communication protocol for live updates
- **Dashboard**: Main monitoring interface displaying KPIs and system status
- **UI_Component**: Reusable React component in the frontend application

## Requirements

### Requirement 1: Remove Deprecated Vibe Coding UI Components

**User Story:** As a system administrator, I want Vibe Coding UI components removed from the interface, so that the UI focuses on the autonomous trading system and template-based approach.

#### Acceptance Criteria

1. THE Frontend SHALL NOT display the VibeCoding component on any page
2. THE Frontend SHALL remove the VibeCoding component from Dashboard.tsx
3. THE Frontend SHALL remove the VibeCoding component from Trading.tsx
4. THE Frontend SHALL remove VibeCoding component imports and references
5. THE Frontend SHALL maintain the ManualOrderEntry component for manual trading
6. THE Frontend SHALL keep strategy management features that work with DSL and templates
7. THE Frontend SHALL preserve all backend API integrations for autonomous trading

### Requirement 2: Autonomous Trading System Monitoring

**User Story:** As a trader, I want to monitor the autonomous trading system in real-time, so that I can understand what the system is doing and verify it's operating correctly.

#### Acceptance Criteria

1. THE Frontend SHALL display the current status of the Autonomous_Trading_System (enabled/disabled)
2. WHEN the Autonomous_Trading_System is active, THE Frontend SHALL display the current activity being performed
3. THE Frontend SHALL display the last cycle execution timestamp
4. THE Frontend SHALL display the next scheduled cycle timestamp
5. THE Frontend SHALL display the current Market_Regime with confidence level
6. THE Frontend SHALL display strategies in the Strategy_Pipeline with their current stage
7. THE Frontend SHALL display a list of active strategies with their current performance
8. THE Frontend SHALL display recent system events (proposals, activations, retirements, trades)
9. THE Frontend SHALL update all monitoring data in real-time via WebSocket
10. THE Frontend SHALL provide manual controls to trigger a cycle or emergency stop

### Requirement 3: Key Performance Indicators Dashboard

**User Story:** As a portfolio manager, I want to see comprehensive KPIs for my trading system, so that I can evaluate overall performance and identify issues quickly.

#### Acceptance Criteria

1. THE Frontend SHALL display total portfolio return for daily, weekly, monthly, and year-to-date periods
2. THE Frontend SHALL display the current portfolio Sharpe_Ratio
3. THE Frontend SHALL display the current Maximum_Drawdown
4. THE Frontend SHALL display historical Maximum_Drawdown
5. THE Frontend SHALL display overall win rate percentage
6. THE Frontend SHALL display profit factor
7. THE Frontend SHALL display the count of active strategies
8. THE Frontend SHALL display capital allocation efficiency metrics
9. THE Frontend SHALL display portfolio risk metrics including VaR
10. WHEN any KPI exceeds a warning threshold, THE Frontend SHALL highlight it visually
11. THE Frontend SHALL update all KPIs in real-time via WebSocket

### Requirement 4: Strategy Performance Visualization

**User Story:** As a trader, I want detailed visualizations of strategy performance, so that I can understand which strategies are working and why.

#### Acceptance Criteria

1. THE Frontend SHALL display individual performance charts for each active strategy
2. THE Frontend SHALL display a strategy comparison view with side-by-side metrics
3. THE Frontend SHALL display Template performance analytics showing which templates perform best
4. THE Frontend SHALL display regime-specific performance showing how strategies perform in different Market_Regime conditions
5. THE Frontend SHALL display per-strategy Sharpe_Ratio
6. THE Frontend SHALL display per-strategy Maximum_Drawdown
7. THE Frontend SHALL display per-strategy win rate and profit factor
8. WHEN displaying strategy performance, THE Frontend SHALL allow filtering by template type
9. WHEN displaying strategy performance, THE Frontend SHALL allow filtering by Market_Regime
10. WHEN displaying strategy performance, THE Frontend SHALL allow sorting by any performance metric

### Requirement 5: Orders and Trade Monitoring

**User Story:** As a trader, I want to monitor all orders and trades in real-time, so that I can verify execution quality and track position changes.

#### Acceptance Criteria

1. THE Frontend SHALL display recent orders with entry and exit details
2. THE Frontend SHALL display order status (filled, pending, cancelled)
3. THE Frontend SHALL display order execution quality metrics including slippage
4. THE Frontend SHALL display fill rate statistics
5. THE Frontend SHALL display trade history with profit and loss for each trade
6. THE Frontend SHALL display current positions with unrealized P&L
7. THE Frontend SHALL display which strategy generated each order
8. WHEN a new order is created, THE Frontend SHALL update the orders list in real-time
9. WHEN an order status changes, THE Frontend SHALL update the display in real-time
10. THE Frontend SHALL allow filtering orders by strategy, symbol, or date range

### Requirement 6: Risk Management Dashboard

**User Story:** As a risk manager, I want comprehensive risk metrics and monitoring, so that I can ensure the portfolio stays within acceptable risk parameters.

#### Acceptance Criteria

1. THE Frontend SHALL display portfolio VaR with confidence intervals
2. THE Frontend SHALL display a correlation matrix showing relationships between active strategies
3. THE Frontend SHALL display Position_Sizing analysis for current positions
4. THE Frontend SHALL display stop-loss and take-profit levels for all positions
5. THE Frontend SHALL display Maximum_Drawdown monitoring with visual alerts
6. THE Frontend SHALL display concentration risk metrics per strategy
7. THE Frontend SHALL display concentration risk metrics per symbol
8. WHEN portfolio risk exceeds defined thresholds, THE Frontend SHALL display prominent visual warnings
9. THE Frontend SHALL display risk-adjusted returns for the portfolio
10. THE Frontend SHALL update all risk metrics in real-time via WebSocket

### Requirement 7: Performance Over Time Visualization

**User Story:** As an analyst, I want to see how performance evolves over time, so that I can identify trends and evaluate long-term system effectiveness.

#### Acceptance Criteria

1. THE Frontend SHALL display an equity curve showing cumulative returns over time
2. THE Frontend SHALL display a benchmark comparison on the equity curve
3. THE Frontend SHALL display rolling Sharpe_Ratio over time
4. THE Frontend SHALL display a monthly returns heatmap
5. THE Frontend SHALL display a quarterly returns heatmap
6. THE Frontend SHALL display Maximum_Drawdown periods with visual highlighting
7. THE Frontend SHALL display a strategy lifecycle timeline showing proposals, activations, and retirements
8. WHEN displaying time-series data, THE Frontend SHALL allow zooming and panning
9. WHEN displaying time-series data, THE Frontend SHALL allow selecting different time ranges
10. THE Frontend SHALL display Market_Regime history correlated with performance

### Requirement 8: Strategy Management Interface

**User Story:** As a trader, I want to manage strategies effectively, so that I can review, compare, and control which strategies are active.

#### Acceptance Criteria

1. THE Frontend SHALL display a list of all strategies with filtering by template type
2. THE Frontend SHALL display a list of all strategies with filtering by Market_Regime
3. THE Frontend SHALL display a list of all strategies with filtering by status (active, retired, proposed)
4. WHEN a user selects a strategy, THE Frontend SHALL display detailed strategy information including DSL rules
5. WHEN a user selects a strategy, THE Frontend SHALL display strategy parameters
6. WHEN a user selects a strategy, THE Frontend SHALL display Backtest results
7. WHEN a user selects a strategy, THE Frontend SHALL display Walk_Forward_Validation results
8. THE Frontend SHALL display a template library browser showing available templates
9. THE Frontend SHALL provide a strategy comparison tool for side-by-side analysis
10. THE Frontend SHALL provide bulk actions for strategy management (activate, retire, backtest)

### Requirement 9: Analytics and Reporting

**User Story:** As an analyst, I want comprehensive analytics and reporting capabilities, so that I can perform deep analysis and generate reports for stakeholders.

#### Acceptance Criteria

1. THE Frontend SHALL display Template performance analytics with aggregated metrics
2. THE Frontend SHALL display regime-specific performance analysis
3. THE Frontend SHALL display trade analytics including win/loss distribution
4. THE Frontend SHALL display trade analytics including holding period statistics
5. THE Frontend SHALL display risk-adjusted returns comparison across strategies
6. THE Frontend SHALL display a correlation matrix heatmap for strategy returns
7. THE Frontend SHALL display attribution analysis showing which strategies contribute most to returns
8. THE Frontend SHALL provide export functionality for data in CSV format
9. THE Frontend SHALL provide export functionality for reports in PDF format
10. WHEN displaying analytics, THE Frontend SHALL allow customizing the analysis time period

### Requirement 10: System Configuration Interface

**User Story:** As a system administrator, I want to configure the autonomous trading system, so that I can adjust parameters and control system behavior.

#### Acceptance Criteria

1. THE Frontend SHALL display configuration options for the Autonomous_Trading_System
2. THE Frontend SHALL display Template management options (enable/disable templates)
3. THE Frontend SHALL display Template customization options
4. THE Frontend SHALL display strategy activation threshold configuration
5. THE Frontend SHALL display strategy retirement threshold configuration
6. THE Frontend SHALL display risk management parameter configuration
7. THE Frontend SHALL display notification preference configuration
8. THE Frontend SHALL display API configuration options
9. WHEN a user changes configuration, THE Frontend SHALL validate the input before submission
10. WHEN a user saves configuration, THE Frontend SHALL confirm the changes were applied successfully

### Requirement 11: Responsive and Accessible Design

**User Story:** As a user, I want the interface to work well on all devices and be accessible, so that I can monitor my trading system from anywhere.

#### Acceptance Criteria

1. THE Frontend SHALL render correctly on desktop displays (1920x1080 and larger)
2. THE Frontend SHALL render correctly on tablet displays (768x1024)
3. THE Frontend SHALL render correctly on mobile displays (375x667 and larger)
4. THE Frontend SHALL adapt layout based on screen size
5. THE Frontend SHALL maintain readability at all supported screen sizes
6. THE Frontend SHALL support keyboard navigation for all interactive elements
7. THE Frontend SHALL provide appropriate ARIA labels for screen readers
8. THE Frontend SHALL maintain color contrast ratios meeting WCAG AA standards
9. THE Frontend SHALL provide text alternatives for all visual information
10. WHEN the viewport size changes, THE Frontend SHALL adjust layout smoothly

### Requirement 12: Real-Time Data Updates

**User Story:** As a trader, I want all data to update in real-time without page refresh, so that I always see current information.

#### Acceptance Criteria

1. THE Frontend SHALL establish a WebSocket connection when authenticated
2. WHEN portfolio value changes, THE Frontend SHALL update the display within 1 second
3. WHEN a new order is created, THE Frontend SHALL update the orders list within 1 second
4. WHEN a strategy status changes, THE Frontend SHALL update the strategy display within 1 second
5. WHEN Market_Regime changes, THE Frontend SHALL update the regime indicator within 1 second
6. WHEN the WebSocket connection is lost, THE Frontend SHALL display a connection status warning
7. WHEN the WebSocket connection is restored, THE Frontend SHALL remove the warning and refresh data
8. THE Frontend SHALL handle WebSocket reconnection automatically
9. THE Frontend SHALL queue updates during disconnection and apply them upon reconnection
10. THE Frontend SHALL not refresh the entire page when receiving real-time updates

### Requirement 13: Error Handling and Loading States

**User Story:** As a user, I want clear feedback when data is loading or errors occur, so that I understand the system state.

#### Acceptance Criteria

1. WHEN data is loading, THE Frontend SHALL display a loading indicator
2. WHEN an API request fails, THE Frontend SHALL display an error message
3. WHEN an API request fails, THE Frontend SHALL provide a retry option
4. THE Frontend SHALL display specific error messages for different error types
5. WHEN a component fails to render, THE Frontend SHALL display an error boundary message
6. WHEN a component fails to render, THE Frontend SHALL prevent the entire application from crashing
7. THE Frontend SHALL log errors to the console for debugging
8. WHEN network connectivity is lost, THE Frontend SHALL display a connectivity warning
9. WHEN data is stale, THE Frontend SHALL indicate the last update timestamp
10. THE Frontend SHALL provide graceful degradation when optional features fail

### Requirement 14: Performance Optimization

**User Story:** As a user, I want the interface to load quickly and respond smoothly, so that I can work efficiently.

#### Acceptance Criteria

1. THE Frontend SHALL load the initial page within 3 seconds on a standard broadband connection
2. THE Frontend SHALL use lazy loading for components not immediately visible
3. THE Frontend SHALL use virtualization for lists with more than 100 items
4. THE Frontend SHALL debounce user input for search and filter operations
5. THE Frontend SHALL cache API responses where appropriate
6. THE Frontend SHALL minimize re-renders of unchanged components
7. THE Frontend SHALL use code splitting to reduce initial bundle size
8. THE Frontend SHALL compress images and assets
9. WHEN rendering large datasets, THE Frontend SHALL paginate or virtualize the display
10. THE Frontend SHALL maintain 60 FPS during animations and transitions

### Requirement 15: Backend Integration

**User Story:** As a developer, I want the frontend to integrate seamlessly with existing backend services, so that all displayed data comes from real backend APIs without mocks.

#### Acceptance Criteria

1. THE Frontend SHALL use existing Backend API endpoints from AutonomousStrategyManager
2. THE Frontend SHALL use existing Backend API endpoints from PortfolioManager
3. THE Frontend SHALL use existing Backend API endpoints from PerformanceDegradationMonitor
4. THE Frontend SHALL use existing Backend API endpoints from MetaStrategy
5. THE Frontend SHALL use existing Backend API endpoints from CorrelationAnalyzer
6. THE Frontend SHALL use existing Backend API endpoints from MarketStatisticsAnalyzer
7. THE Frontend SHALL NOT create mock data or simulated responses
8. THE Frontend SHALL NOT modify Backend code during frontend updates
9. THE Frontend SHALL use the existing WebSocket infrastructure for real-time updates
10. THE Frontend SHALL follow current React and TypeScript patterns in the codebase

### Requirement 16: Visual Design and User Experience

**User Story:** As a trader, I want a professional and sophisticated interface, so that I can quickly find information and make decisions with confidence.

#### Acceptance Criteria

1. THE Frontend SHALL use a professional trading UI design inspired by Bloomberg Terminal and TradingView
2. THE Frontend SHALL use a sophisticated color palette with proper contrast and visual hierarchy
3. THE Frontend SHALL use modern UI components with smooth animations and transitions
4. THE Frontend SHALL use consistent iconography throughout the application
5. THE Frontend SHALL provide tooltips for complex metrics and features
6. THE Frontend SHALL use appropriate chart types for different data (line charts for time series, bar charts for comparisons, heatmaps for correlations)
7. THE Frontend SHALL maintain consistent spacing and alignment using a design system
8. THE Frontend SHALL use readable typography with appropriate font sizes and weights
9. THE Frontend SHALL use glassmorphism or modern card designs for component containers
10. THE Frontend SHALL provide clear visual feedback for all user interactions

### Requirement 22: Enhanced Login and Notification Visuals

**User Story:** As a user, I want a polished login experience and professional notifications, so that the application feels modern and trustworthy.

#### Acceptance Criteria

1. THE Frontend SHALL display a sophisticated login screen with modern design
2. THE Frontend SHALL use smooth transitions when logging in
3. THE Frontend SHALL display a branded logo and tagline on the login screen
4. THE Frontend SHALL use proper visual hierarchy on the login form
5. THE Frontend SHALL display toast notifications with modern styling
6. THE Frontend SHALL use appropriate icons for different notification types (success, error, warning, info)
7. THE Frontend SHALL animate notifications smoothly when appearing and disappearing
8. THE Frontend SHALL position notifications consistently (top-right or bottom-right)
9. THE Frontend SHALL allow dismissing notifications with a close button
10. THE Frontend SHALL auto-dismiss notifications after an appropriate duration

### Requirement 23: Bulk Strategy Management

**User Story:** As a portfolio manager, I want to manage multiple strategies efficiently, so that I can quickly clean up underperforming or inactive strategies.

#### Acceptance Criteria

1. THE Frontend SHALL provide a bulk action toolbar for strategy management
2. THE Frontend SHALL allow selecting multiple strategies using checkboxes
3. THE Frontend SHALL provide a "Select All" option for current filtered view
4. THE Frontend SHALL provide a "Retire All Selected" action
5. THE Frontend SHALL provide a "Retire All Non-Active" action that retires all strategies not in ACTIVE status
6. THE Frontend SHALL provide a "Retire Bad Performance" action that retires strategies below performance thresholds
7. THE Frontend SHALL allow filtering strategies by status (ACTIVE, BACKTESTED, PROPOSED, RETIRED, INVALID)
8. THE Frontend SHALL allow filtering strategies by performance metrics (Sharpe ratio, win rate, drawdown)
9. THE Frontend SHALL allow filtering strategies by template type
10. THE Frontend SHALL confirm bulk actions with a modal showing how many strategies will be affected
11. THE Frontend SHALL display progress when executing bulk actions
12. THE Frontend SHALL provide undo capability for bulk retirement actions
13. WHEN retiring bad performance strategies, THE Frontend SHALL allow configuring thresholds (min Sharpe, max drawdown, min win rate)
14. THE Frontend SHALL display a summary after bulk actions complete (e.g., "Retired 47 strategies")

### Requirement 17: Autonomous Trading Monitor Page

**User Story:** As a trader, I want a dedicated page for monitoring the autonomous trading system, so that I can see all autonomous operations in one place.

#### Acceptance Criteria

1. THE Frontend SHALL provide a dedicated Autonomous Trading Monitor page
2. THE Frontend SHALL display a system status card showing on/off state, last cycle, and next cycle
3. THE Frontend SHALL display a Market_Regime indicator with confidence level
4. THE Frontend SHALL display a Strategy_Pipeline visualization showing all pipeline stages
5. THE Frontend SHALL display an active strategies grid with name, template, performance, and allocation
6. THE Frontend SHALL display a recent events timeline with proposals, activations, retirements, and trades
7. THE Frontend SHALL provide manual controls to trigger a cycle
8. THE Frontend SHALL provide an emergency stop button
9. THE Frontend SHALL provide controls to adjust system settings
10. THE Frontend SHALL update all information in real-time via WebSocket

### Requirement 18: Enhanced Dashboard Page

**User Story:** As a trader, I want an enhanced dashboard with comprehensive KPIs, so that I can see overall system health at a glance.

#### Acceptance Criteria

1. THE Frontend SHALL display a portfolio overview with total value, P&L, and allocation chart
2. THE Frontend SHALL display a performance metrics grid with Sharpe_Ratio, Maximum_Drawdown, and win rate
3. THE Frontend SHALL display an equity curve chart with benchmark comparison
4. THE Frontend SHALL display a strategy performance table that is sortable and filterable
5. THE Frontend SHALL display a recent trades list with execution details
6. THE Frontend SHALL display a risk metrics panel with VaR, correlation, and concentration
7. THE Frontend SHALL display Market_Regime history chart
8. THE Frontend SHALL organize information in a clear grid layout
9. THE Frontend SHALL prioritize the most important metrics at the top
10. THE Frontend SHALL update all dashboard data in real-time via WebSocket

### Requirement 19: Analytics and Reporting Page

**User Story:** As an analyst, I want a dedicated analytics page, so that I can perform deep analysis and generate reports.

#### Acceptance Criteria

1. THE Frontend SHALL provide a dedicated Analytics and Reporting page
2. THE Frontend SHALL display Template performance analytics
3. THE Frontend SHALL display regime-specific performance analysis
4. THE Frontend SHALL display trade analytics with win/loss distribution and holding periods
5. THE Frontend SHALL display risk-adjusted returns comparison
6. THE Frontend SHALL display a correlation matrix heatmap
7. THE Frontend SHALL display attribution analysis
8. THE Frontend SHALL provide export functionality for CSV format
9. THE Frontend SHALL provide export functionality for PDF reports
10. THE Frontend SHALL allow customizing the analysis time period

### Requirement 20: Settings Page Updates

**User Story:** As a system administrator, I want updated settings for the autonomous system, so that I can configure all system parameters.

#### Acceptance Criteria

1. THE Frontend SHALL display Autonomous_Trading_System configuration in the Settings page
2. THE Frontend SHALL display Template management options in the Settings page
3. THE Frontend SHALL display activation and retirement threshold configuration
4. THE Frontend SHALL display risk management parameter configuration
5. THE Frontend SHALL display notification preference configuration
6. THE Frontend SHALL display API configuration options
7. THE Frontend SHALL validate all configuration inputs before submission
8. THE Frontend SHALL provide clear descriptions for each configuration option
9. THE Frontend SHALL group related settings into logical sections
10. THE Frontend SHALL confirm when settings are saved successfully

### Requirement 21: Leverage Existing Backend Features

**User Story:** As a developer, I want to leverage all existing backend enhancements, so that the UI displays real system capabilities without duplication or mocks.

#### Acceptance Criteria

1. THE Frontend SHALL display data from AutonomousStrategyManager.get_status() for system status
2. THE Frontend SHALL display data from PortfolioManager for portfolio risk metrics
3. THE Frontend SHALL display data from PerformanceDegradationMonitor for strategy health alerts
4. THE Frontend SHALL display data from MetaStrategy for ensemble strategy information
5. THE Frontend SHALL display data from CorrelationAnalyzer for strategy correlation matrices
6. THE Frontend SHALL display data from MarketStatisticsAnalyzer for market regime detection
7. THE Frontend SHALL display position sizing information from existing position sizing algorithms
8. THE Frontend SHALL display stop-loss and take-profit data from existing risk management
9. THE Frontend SHALL display walk-forward validation results from existing backtest data
10. THE Frontend SHALL display tiered activation information (Tier 1/2/3) from PortfolioManager

### Requirement 24: Complete Trading Lifecycle Visualization

**User Story:** As a trader, I want to see the complete trading lifecycle from strategy proposal to order execution, so that I understand the full autonomous system flow.

#### Acceptance Criteria

1. THE Frontend SHALL display the strategy proposal stage with count of strategies being generated
2. THE Frontend SHALL display the backtesting stage with progress indicator
3. THE Frontend SHALL display the validation stage showing which strategies pass criteria
4. THE Frontend SHALL display the activation stage with tier assignments (Tier 1/2/3)
5. THE Frontend SHALL display the signal generation stage with current signals
6. THE Frontend SHALL display the risk validation stage showing approved and rejected signals
7. THE Frontend SHALL display the order execution stage with order placement status
8. THE Frontend SHALL display the position monitoring stage with open positions
9. THE Frontend SHALL display the performance tracking stage with live P&L
10. THE Frontend SHALL display the retirement stage showing strategies being retired
11. THE Frontend SHALL provide a visual pipeline or flowchart showing the current stage
12. THE Frontend SHALL highlight the active stage in the lifecycle
13. THE Frontend SHALL show transition timestamps between stages
14. THE Frontend SHALL display error states and recovery actions for each stage

### Requirement 25: Advanced Autonomous System Control

**User Story:** As a system operator, I want granular control over the autonomous system, so that I can manage strategy generation separately from trading execution.

#### Acceptance Criteria

1. THE Frontend SHALL provide a manual "Start Generation Cycle" button to initiate strategy proposal and backtesting
2. THE Frontend SHALL provide a "Stop Generation" button to halt strategy proposal and backtesting
3. THE Frontend SHALL allow configuring generation cycle duration (10 minutes, 20 minutes, 1 hour, 2 hours, 4 hours, custom)
4. THE Frontend SHALL display a countdown timer showing time remaining in current generation cycle
5. THE Frontend SHALL allow stopping generation while keeping trading execution active
6. THE Frontend SHALL display separate status indicators for "Generation Active" and "Trading Active"
7. THE Frontend SHALL provide an "Emergency Stop All" button that halts both generation and trading
8. THE Frontend SHALL provide a "Resume Trading" button to restart trading after emergency stop
9. THE Frontend SHALL display the current generation cycle configuration (duration, frequency)
10. THE Frontend SHALL allow scheduling generation cycles (e.g., "Run daily at 9 AM for 1 hour")
11. THE Frontend SHALL display generation cycle history with timestamps and results
12. WHEN generation is stopped, THE Frontend SHALL allow active strategies to continue trading
13. WHEN generation is stopped, THE Frontend SHALL allow portfolio optimization to continue
14. WHEN generation is stopped, THE Frontend SHALL allow performance monitoring to continue

### Requirement 26: Intelligent Capital Allocation

**User Story:** As a portfolio manager, I want the system to intelligently allocate capital based on available cash and strategy performance, so that capital is used efficiently.

#### Acceptance Criteria

1. THE Frontend SHALL display current available cash balance
2. THE Frontend SHALL display total allocated capital across all strategies
3. THE Frontend SHALL display unallocated capital percentage
4. THE Frontend SHALL display per-strategy capital allocation with percentages
5. THE Frontend SHALL provide an "Optimize Allocations" button to rebalance based on performance
6. THE Frontend SHALL display recommended allocation changes before applying them
7. THE Frontend SHALL allow setting maximum allocation per strategy (default 30% for Tier 1, 15% for Tier 2, 10% for Tier 3)
8. THE Frontend SHALL allow setting minimum cash reserve percentage (default 10%)
9. THE Frontend SHALL display allocation efficiency metrics (capital utilization, idle cash)
10. THE Frontend SHALL warn when approaching maximum allocation limits
11. THE Frontend SHALL display allocation history over time
12. WHEN available cash is low, THE Frontend SHALL highlight strategies that could be reduced
13. WHEN available cash is high, THE Frontend SHALL suggest increasing allocations to top performers
14. THE Frontend SHALL display projected allocation after pending orders execute


### Requirement 13: Order Monitoring for Autonomous Strategies

**User Story:** As a trader, I want to monitor all orders generated by autonomous strategies in real-time, so that I can track execution quality and identify issues quickly.

#### Acceptance Criteria

1. WHEN viewing the dashboard, THE system SHALL display recent orders with strategy attribution
2. WHEN an autonomous strategy generates an order, THE system SHALL show which strategy created it
3. WHEN viewing order details, THE system SHALL display entry/exit rules that triggered the order
4. WHEN orders are filled/cancelled/rejected, THE system SHALL update in real-time via WebSocket
5. THE system SHALL provide filtering by strategy, symbol, status, and time range
6. THE system SHALL calculate and display execution quality metrics (slippage, fill rate)
7. THE system SHALL alert on rejected orders or execution issues

### Requirement 14: Risk Management Dashboard

**User Story:** As a trader, I want to monitor portfolio-level risk metrics in real-time, so that I can ensure the autonomous system stays within acceptable risk parameters.

#### Acceptance Criteria

1. WHEN viewing the dashboard, THE system SHALL display current portfolio risk metrics
2. THE system SHALL show Value at Risk (VaR) at 95% confidence level
3. THE system SHALL display maximum position size as percentage of portfolio
4. THE system SHALL show portfolio beta and correlation to market indices
5. THE system SHALL display current drawdown and distance to maximum drawdown threshold
6. THE system SHALL show leverage ratio and margin utilization
7. THE system SHALL alert when risk metrics approach configured thresholds
8. THE system SHALL provide risk breakdown by strategy
9. THE system SHALL show historical risk metrics over time
10. THE system SHALL display stop-loss and take-profit levels for active positions
