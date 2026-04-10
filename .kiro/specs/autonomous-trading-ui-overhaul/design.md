# Design Document: Autonomous Trading UI Overhaul

## Overview

This design transforms the AlphaCent frontend from a generic trading dashboard into a specialized autonomous trading monitoring and control interface. The system removes all LLM/Vibe Coding features and creates a focused, professional trading interface centered around the autonomous strategy system.

### Current State Analysis

**Existing Components to Remove:**
- VibeCoding component (LLM-based order generation)
- SocialInsightsComponent (not used)
- SmartPortfoliosComponent (not used)
- LLM-related services and utilities

**Existing Components to Enhance:**
- Dashboard layout (add autonomous section)
- Strategies component (add template/DSL display)
- System status (integrate autonomous status)
- Settings page (add autonomous configuration)

**Backend Integration Points:**
- Existing WebSocket infrastructure (wsManager)
- Existing API services (authService, etc.)
- Strategy Engine with DSL and templates
- Portfolio Manager with risk metrics
- Market Analyzer with regime detection

## Architecture

### High-Level Component Structure

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend Application                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   Main Dashboard                      │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  System Status (Trading Mode, Health)          │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Autonomous Trading Status (NEW)               │  │  │
│  │  │  - System enabled/disabled                     │  │  │
│  │  │  - Market regime indicator                     │  │  │
│  │  │  - Cycle statistics                            │  │  │
│  │  │  - Portfolio health metrics                    │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Performance Dashboard (NEW)                   │  │  │
│  │  │  - KPI cards (Sharpe, Return, Drawdown)       │  │  │
│  │  │  - Performance charts over time               │  │  │
│  │  │  - Strategy contribution breakdown            │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Account Overview & Positions                  │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Active Strategies (Enhanced)                  │  │  │
│  │  │  - Template badges                             │  │  │
│  │  │  - DSL rule display                            │  │  │
│  │  │  - Performance metrics                         │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Orders & Risk Monitoring                      │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Autonomous Trading Page (NEW)            │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Control Panel                                 │  │  │
│  │  │  - Enable/disable system                       │  │  │
│  │  │  - Manual trigger button                       │  │  │
│  │  │  - Configuration quick access                  │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Strategy Lifecycle View                       │  │  │
│  │  │  - Proposed strategies                         │  │  │
│  │  │  - Backtesting in progress                     │  │  │
│  │  │  - Activation decisions                        │  │  │
│  │  │  - Retirement events                           │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  Portfolio Composition                         │  │  │
│  │  │  - Strategy allocations                        │  │  │
│  │  │  - Correlation matrix                          │  │  │
│  │  │  - Risk metrics                                │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  │  ┌────────────────────────────────────────────────┐  │  │
│  │  │  History & Analytics                           │  │  │
│  │  │  - Timeline of events                          │  │  │
│  │  │  - Template performance                        │  │  │
│  │  │  - Regime-based analysis                       │  │  │
│  │  └────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Backend API │    │  WebSocket   │    │  Services    │
│  Endpoints   │    │  Events      │    │  Layer       │
└──────────────┘    └──────────────┘    └──────────────┘
```


## Component Design

### 1. Autonomous Trading Status Component

**Purpose**: Real-time status display of the autonomous trading system

**Location**: Dashboard (full width, below System Status)

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Autonomous Trading System                    [●] ENABLED │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Market Regime: [TRENDING_UP ↗]  Last Cycle: 2h ago         │
│  Next Run: in 5d 3h              Cycle Duration: 45m         │
│                                                               │
│  📊 Cycle Statistics                                         │
│  ├─ Proposals: 6 strategies                                  │
│  ├─ Backtested: 6/6 completed                               │
│  ├─ Activated: 2 strategies (Sharpe > 1.5)                  │
│  └─ Retired: 1 strategy (drawdown > 15%)                    │
│                                                               │
│  💼 Portfolio Health                                         │
│  ├─ Active Strategies: 8/10                                  │
│  ├─ Total Allocation: 95%                                    │
│  ├─ Avg Correlation: 0.42 (Good diversity)                  │
│  └─ Portfolio Sharpe: 1.85                                   │
│                                                               │
│  📋 Template Usage (Last 30 days)                            │
│  ├─ RSI Mean Reversion: 45% success, 12 uses                │
│  ├─ MACD Momentum: 38% success, 8 uses                      │
│  └─ Bollinger Breakout: 60% success, 5 uses                 │
│                                                               │
│  [⚙️ Settings] [📊 View History] [▶️ Trigger Cycle Now]     │
└─────────────────────────────────────────────────────────────┘
```

**State Management**:
```typescript
interface AutonomousStatus {
  enabled: boolean;
  marketRegime: 'TRENDING_UP' | 'TRENDING_DOWN' | 'RANGING' | 'VOLATILE';
  lastCycleTime: Date;
  nextScheduledRun: Date;
  cycleDuration: number; // seconds
  cycleStats: {
    proposalsCount: number;
    backtestedCount: number;
    activatedCount: number;
    retiredCount: number;
  };
  portfolioHealth: {
    activeStrategies: number;
    maxStrategies: number;
    totalAllocation: number;
    avgCorrelation: number;
    portfolioSharpe: number;
  };
  templateStats: Array<{
    name: string;
    successRate: number;
    usageCount: number;
  }>;
}
```

**API Integration**:
- GET `/api/strategies/autonomous/status` - Fetch current status
- POST `/api/strategies/autonomous/trigger` - Manual trigger
- WebSocket: `autonomous:status_update` - Real-time updates

### 2. Performance Dashboard Component

**Purpose**: Visualize key performance indicators and trends

**Location**: Dashboard (full width, after Autonomous Status)

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ 📈 Performance Dashboard                                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Sharpe   │  │ Return   │  │ Drawdown │  │ Win Rate │   │
│  │  1.85    │  │  +24.3%  │  │  -8.2%   │  │  62.5%   │   │
│  │  ↑ 0.15  │  │  ↑ 2.1%  │  │  ↓ 1.3%  │  │  ↑ 3.2%  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                               │
│  📊 Portfolio Value Over Time (90 days)                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                       │   │
│  │     [Line chart showing portfolio growth]            │   │
│  │                                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  🎯 Strategy Contribution (Current Month)                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  RSI Mean Reversion    ████████░░ +8.2% (35%)       │   │
│  │  MACD Momentum         ██████░░░░ +5.1% (25%)       │   │
│  │  Bollinger Breakout    ████░░░░░░ +3.8% (15%)       │   │
│  │  SMA Crossover         ███░░░░░░░ +2.9% (12%)       │   │
│  │  Others                ██░░░░░░░░ +1.3% (13%)       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  [1M] [3M] [6M] [1Y] [ALL]                                  │
└─────────────────────────────────────────────────────────────┘
```

**Data Structure**:
```typescript
interface PerformanceMetrics {
  sharpe: { value: number; change: number };
  totalReturn: { value: number; change: number };
  maxDrawdown: { value: number; change: number };
  winRate: { value: number; change: number };
  portfolioHistory: Array<{
    date: Date;
    value: number;
    benchmark?: number;
  }>;
  strategyContributions: Array<{
    strategyName: string;
    contribution: number; // percentage
    return: number;
  }>;
}
```

### 3. Enhanced Strategies Component

**Purpose**: Display strategies with template/DSL information

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ 🎯 Active Strategies (8)                                     │
│                                                               │
│  Filter: [All ▼] [Status ▼] [Template ▼] [Regime ▼]        │
│  Sort: [Performance ▼]                          [+ New]      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  📋 RSI Mean Reversion - SPY, QQQ          [●] ACTIVE       │
│  Template: RSI Mean Reversion | Regime: RANGING             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Entry: RSI(14) < 30 AND CLOSE < BB_LOWER(20, 2)    │   │
│  │ Exit:  RSI(14) > 70 OR CLOSE > BB_UPPER(20, 2)     │   │
│  └─────────────────────────────────────────────────────┘   │
│  Sharpe: 1.92 | Return: +12.3% | Drawdown: -5.2%           │
│  Allocation: 15% | Trades: 24 | Win Rate: 65%               │
│  [View Details] [Adjust Allocation] [Retire]                │
│                                                               │
│  ─────────────────────────────────────────────────────────  │
│                                                               │
│  📋 MACD Momentum - AAPL, MSFT             [●] ACTIVE       │
│  Template: MACD Momentum | Regime: TRENDING_UP              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Entry: MACD() CROSSES_ABOVE MACD_SIGNAL()          │   │
│  │ Exit:  MACD() CROSSES_BELOW MACD_SIGNAL()          │   │
│  └─────────────────────────────────────────────────────┘   │
│  Sharpe: 1.75 | Return: +9.8% | Drawdown: -6.1%            │
│  Allocation: 12% | Trades: 18 | Win Rate: 61%               │
│  [View Details] [Adjust Allocation] [Retire]                │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Enhanced Strategy Data**:
```typescript
interface EnhancedStrategy {
  id: string;
  name: string;
  status: 'PROPOSED' | 'BACKTESTED' | 'ACTIVE' | 'RETIRED';
  source: 'TEMPLATE' | 'USER';
  templateName?: string;
  marketRegime: string;
  symbols: string[];
  rules: {
    entry: string[]; // DSL syntax
    exit: string[];
  };
  performance: {
    sharpe: number;
    totalReturn: number;
    maxDrawdown: number;
    winRate: number;
    totalTrades: number;
  };
  allocation: number;
  createdAt: Date;
  activatedAt?: Date;
  retiredAt?: Date;
}
```


### 4. Autonomous Trading Page (New)

**Purpose**: Dedicated page for monitoring and controlling autonomous trading

**Route**: `/autonomous`

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│ 🤖 Autonomous Trading                                        │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Control Panel                                         │  │
│  │ [●] System Enabled    [▶️ Trigger Now] [⚙️ Settings]  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Strategy Lifecycle                                    │  │
│  │                                                        │  │
│  │  Proposed (6) → Backtesting (3) → Activated (2)      │  │
│  │                                  ↓                     │  │
│  │                              Retired (1)              │  │
│  │                                                        │  │
│  │  [View Proposals] [View Active] [View Retired]       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Portfolio Composition                                 │  │
│  │                                                        │  │
│  │  [Pie chart: Strategy allocations]                   │  │
│  │  [Heatmap: Correlation matrix]                       │  │
│  │                                                        │  │
│  │  Risk Metrics:                                        │  │
│  │  - Portfolio VaR: $2,450 (95% confidence)           │  │
│  │  - Max Position Size: 15%                            │  │
│  │  - Diversification Score: 0.78                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ History & Analytics                                   │  │
│  │                                                        │  │
│  │  [Timeline view of events]                           │  │
│  │  [Template performance charts]                       │  │
│  │  [Regime-based analysis]                             │  │
│  │                                                        │  │
│  │  [Export CSV] [Generate Report]                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 5. Settings - Autonomous Configuration

**Purpose**: Configure autonomous trading system parameters

**Location**: Settings page, new "Autonomous Trading" section

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ ⚙️ Autonomous Trading Settings                               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  General Settings                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Enable Autonomous System    [✓]                     │   │
│  │ Proposal Frequency          [Weekly ▼]              │   │
│  │ Max Active Strategies       [10] (5-15)             │   │
│  │ Min Active Strategies       [5]  (3-10)             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Template Settings                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ✓ RSI Mean Reversion        Priority: High          │   │
│  │ ✓ MACD Momentum             Priority: Medium        │   │
│  │ ✓ Bollinger Breakout        Priority: Medium        │   │
│  │ ✓ SMA Crossover             Priority: Low           │   │
│  │ ✗ Stochastic Reversion      Priority: Low           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Activation Thresholds                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Min Sharpe Ratio     [1.5]  ────●────────  (0.5-3.0)│   │
│  │ Max Drawdown         [15%]  ────────●────  (5%-30%) │   │
│  │ Min Win Rate         [50%]  ──────●──────  (40%-70%)│   │
│  │ Min Trades           [20]   ────●────────  (10-50)  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Retirement Triggers                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Max Sharpe Threshold [0.5]  ●────────────  (0.0-1.5)│   │
│  │ Max Drawdown         [15%]  ────────●────  (10%-30%)│   │
│  │ Min Win Rate         [40%]  ────●────────  (30%-50%)│   │
│  │ Min Trades for Eval  [30]   ──────●──────  (20-100) │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Advanced Settings                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Backtest Period      [365 days ▼]                   │   │
│  │ Walk-Forward Split   [Train: 240d, Test: 120d]      │   │
│  │ Correlation Threshold [0.7]  ──────●──────  (0.5-0.9)│   │
│  │ Risk-Free Rate       [4.5%]  (for Sharpe calc)      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  [Reset to Defaults] [Save Changes]                         │
│  Last updated: 2 hours ago by admin                         │
└─────────────────────────────────────────────────────────────┘
```

**Configuration Data Structure**:
```typescript
interface AutonomousConfig {
  general: {
    enabled: boolean;
    proposalFrequency: 'daily' | 'weekly' | 'monthly';
    maxActiveStrategies: number;
    minActiveStrategies: number;
  };
  templates: Array<{
    name: string;
    enabled: boolean;
    priority: 'high' | 'medium' | 'low';
  }>;
  activationThresholds: {
    minSharpe: number;
    maxDrawdown: number;
    minWinRate: number;
    minTrades: number;
  };
  retirementTriggers: {
    maxSharpe: number;
    maxDrawdown: number;
    minWinRate: number;
    minTradesForEval: number;
  };
  advanced: {
    backtestPeriod: number; // days
    walkForwardTrain: number; // days
    walkForwardTest: number; // days
    correlationThreshold: number;
    riskFreeRate: number;
  };
}
```

### 6. Notification System Enhancement

**Purpose**: Real-time notifications for autonomous trading events

**Event Types**:
```typescript
type AutonomousEvent = 
  | 'cycle_started'
  | 'cycle_completed'
  | 'strategies_proposed'
  | 'backtest_completed'
  | 'strategy_activated'
  | 'strategy_retired'
  | 'regime_changed'
  | 'portfolio_rebalanced'
  | 'error_occurred';

interface AutonomousNotification {
  type: AutonomousEvent;
  severity: 'info' | 'success' | 'warning' | 'error';
  title: string;
  message: string;
  timestamp: Date;
  data?: any;
  actionButton?: {
    label: string;
    action: string;
  };
}
```

**Notification Examples**:
```
✓ Strategies Proposed
  6 new strategies generated for RANGING market
  [View Proposals]

✓ Strategy Activated
  "RSI Mean Reversion" activated with 15% allocation
  Sharpe: 1.92, Expected Return: +12%
  [View Strategy]

⚠ Strategy Retired
  "MACD Momentum" retired due to drawdown > 15%
  Final Performance: Sharpe 0.42, Return -8.2%
  [View Details]

ℹ Market Regime Changed
  Market regime changed from RANGING to TRENDING_UP
  Next cycle will use momentum templates
  [View Analysis]
```


## API Design

### Backend Endpoints

#### 1. Autonomous Status & Control

```typescript
// GET /api/strategies/autonomous/status
interface StatusResponse {
  enabled: boolean;
  marketRegime: string;
  lastCycleTime: string;
  nextScheduledRun: string;
  cycleDuration: number;
  cycleStats: CycleStats;
  portfolioHealth: PortfolioHealth;
  templateStats: TemplateStats[];
}

// POST /api/strategies/autonomous/trigger
interface TriggerRequest {
  force?: boolean; // Skip schedule check
}
interface TriggerResponse {
  success: boolean;
  cycleId: string;
  estimatedDuration: number;
}

// GET /api/strategies/autonomous/config
interface ConfigResponse {
  config: AutonomousConfig;
  lastUpdated: string;
  updatedBy: string;
}

// PUT /api/strategies/autonomous/config
interface ConfigUpdateRequest {
  config: Partial<AutonomousConfig>;
}
interface ConfigUpdateResponse {
  success: boolean;
  config: AutonomousConfig;
}
```

#### 2. Strategy Management

```typescript
// GET /api/strategies/proposals
interface ProposalsResponse {
  proposals: Array<{
    id: string;
    strategy: EnhancedStrategy;
    proposedAt: string;
    marketRegime: string;
    backtestResults?: BacktestResults;
    evaluationScore?: number;
  }>;
  total: number;
  page: number;
}

// GET /api/strategies/retirements
interface RetirementsResponse {
  retirements: Array<{
    id: string;
    strategyId: string;
    strategyName: string;
    retiredAt: string;
    reason: string;
    finalMetrics: {
      sharpe: number;
      totalReturn: number;
      maxDrawdown: number;
      winRate: number;
    };
  }>;
  total: number;
  page: number;
}

// GET /api/strategies/templates
interface TemplatesResponse {
  templates: Array<{
    name: string;
    description: string;
    marketRegime: string[];
    indicators: string[];
    entryRules: string[];
    exitRules: string[];
    successRate: number;
    usageCount: number;
  }>;
}
```

#### 3. Performance & Analytics

```typescript
// GET /api/performance/metrics
interface PerformanceMetricsRequest {
  period?: '1M' | '3M' | '6M' | '1Y' | 'ALL';
  strategyId?: string;
}
interface PerformanceMetricsResponse {
  sharpe: MetricWithChange;
  totalReturn: MetricWithChange;
  maxDrawdown: MetricWithChange;
  winRate: MetricWithChange;
  portfolioHistory: HistoryPoint[];
  strategyContributions: Contribution[];
}

// GET /api/performance/portfolio
interface PortfolioResponse {
  strategies: Array<{
    id: string;
    name: string;
    allocation: number;
    performance: StrategyPerformance;
  }>;
  correlationMatrix: number[][];
  riskMetrics: {
    portfolioVaR: number;
    maxPositionSize: number;
    diversificationScore: number;
  };
}

// GET /api/performance/history
interface HistoryRequest {
  startDate?: string;
  endDate?: string;
  eventTypes?: AutonomousEvent[];
}
interface HistoryResponse {
  events: Array<{
    id: string;
    type: AutonomousEvent;
    timestamp: string;
    data: any;
  }>;
  total: number;
}
```

### WebSocket Events

```typescript
// Client → Server subscriptions
ws.send({
  type: 'subscribe',
  channels: [
    'autonomous:status',
    'autonomous:cycle',
    'autonomous:strategies',
    'autonomous:notifications'
  ]
});

// Server → Client events
interface WebSocketEvent {
  channel: string;
  event: string;
  data: any;
  timestamp: string;
}

// Event examples:
{
  channel: 'autonomous:status',
  event: 'status_update',
  data: { enabled: true, marketRegime: 'TRENDING_UP', ... }
}

{
  channel: 'autonomous:cycle',
  event: 'cycle_started',
  data: { cycleId: 'abc123', estimatedDuration: 2700 }
}

{
  channel: 'autonomous:strategies',
  event: 'strategy_activated',
  data: { strategyId: 'xyz789', name: 'RSI Mean Reversion', ... }
}

{
  channel: 'autonomous:notifications',
  event: 'notification',
  data: { type: 'strategy_activated', severity: 'success', ... }
}
```

## Data Flow

### 1. Initial Page Load

```
User → Dashboard
  ↓
Frontend fetches:
  - GET /api/strategies/autonomous/status
  - GET /api/performance/metrics
  - GET /api/strategies (active)
  - GET /api/performance/portfolio
  ↓
WebSocket connects and subscribes:
  - autonomous:status
  - autonomous:notifications
  ↓
UI renders with initial data
```

### 2. Autonomous Cycle Execution

```
User clicks "Trigger Cycle Now"
  ↓
POST /api/strategies/autonomous/trigger
  ↓
Backend starts cycle:
  1. Analyze market conditions
  2. Propose strategies (templates)
  3. Backtest each strategy
  4. Evaluate for activation
  5. Activate high performers
  6. Check retirement triggers
  7. Retire underperformers
  ↓
WebSocket events stream to frontend:
  - cycle_started
  - strategies_proposed (count: 6)
  - backtest_completed (for each)
  - strategy_activated (for qualified)
  - strategy_retired (if any)
  - cycle_completed
  ↓
Frontend updates UI in real-time:
  - Status component shows progress
  - Notifications appear
  - Strategy list updates
  - Performance metrics refresh
```

### 3. Configuration Update

```
User modifies settings
  ↓
Frontend validates inputs
  ↓
PUT /api/strategies/autonomous/config
  ↓
Backend validates and saves
  ↓
WebSocket broadcasts config_updated
  ↓
All connected clients refresh
```

## State Management

### Redux Store Structure

```typescript
interface RootState {
  autonomous: {
    status: AutonomousStatus | null;
    config: AutonomousConfig | null;
    loading: boolean;
    error: string | null;
  };
  strategies: {
    active: EnhancedStrategy[];
    proposed: StrategyProposal[];
    retired: RetiredStrategy[];
    loading: boolean;
    filters: StrategyFilters;
  };
  performance: {
    metrics: PerformanceMetrics | null;
    portfolio: PortfolioData | null;
    history: HistoryEvent[];
    loading: boolean;
  };
  notifications: {
    items: AutonomousNotification[];
    unreadCount: number;
  };
}
```

### Actions

```typescript
// Autonomous actions
autonomousActions = {
  fetchStatus: () => async dispatch => { ... },
  triggerCycle: () => async dispatch => { ... },
  updateConfig: (config) => async dispatch => { ... },
  toggleSystem: (enabled) => async dispatch => { ... },
};

// Strategy actions
strategyActions = {
  fetchStrategies: (filters) => async dispatch => { ... },
  fetchProposals: () => async dispatch => { ... },
  fetchRetirements: () => async dispatch => { ... },
  retireStrategy: (id, reason) => async dispatch => { ... },
  adjustAllocation: (id, allocation) => async dispatch => { ... },
};

// Performance actions
performanceActions = {
  fetchMetrics: (period) => async dispatch => { ... },
  fetchPortfolio: () => async dispatch => { ... },
  fetchHistory: (filters) => async dispatch => { ... },
};
```


## Styling & Design System

### Color Palette

```typescript
// Autonomous Trading Theme
const autonomousTheme = {
  // Status colors
  enabled: '#10b981',      // green-500
  disabled: '#6b7280',     // gray-500
  warning: '#f59e0b',      // amber-500
  error: '#ef4444',        // red-500
  
  // Market regime colors
  trendingUp: '#10b981',   // green-500
  trendingDown: '#ef4444', // red-500
  ranging: '#3b82f6',      // blue-500
  volatile: '#f59e0b',     // amber-500
  
  // Performance colors
  positive: '#10b981',     // green-500
  negative: '#ef4444',     // red-500
  neutral: '#6b7280',      // gray-500
  
  // Template badges
  template: '#8b5cf6',     // violet-500
  user: '#3b82f6',         // blue-500
  
  // Background
  cardBg: '#1f2937',       // gray-800
  cardBorder: '#374151',   // gray-700
  hover: '#374151',        // gray-700
};
```

### Typography

```typescript
// Font hierarchy
const typography = {
  // Headers
  h1: 'text-3xl font-bold text-gray-100',
  h2: 'text-2xl font-semibold text-gray-100',
  h3: 'text-xl font-semibold text-gray-200',
  h4: 'text-lg font-medium text-gray-200',
  
  // Body
  body: 'text-base text-gray-300',
  bodySmall: 'text-sm text-gray-400',
  caption: 'text-xs text-gray-500',
  
  // Special
  mono: 'font-mono text-sm',
  code: 'font-mono text-xs bg-gray-900 px-2 py-1 rounded',
};
```

### Component Patterns

#### Card Component
```tsx
<Card className="bg-gray-800 border border-gray-700 rounded-lg p-6">
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardActions>
      <Button>Action</Button>
    </CardActions>
  </CardHeader>
  <CardContent>
    {/* Content */}
  </CardContent>
</Card>
```

#### Status Badge
```tsx
<StatusBadge 
  status="enabled" 
  icon={<CheckCircle />}
>
  ENABLED
</StatusBadge>
```

#### Metric Card
```tsx
<MetricCard
  label="Sharpe Ratio"
  value={1.85}
  change={+0.15}
  format="decimal"
  trend="up"
/>
```

#### DSL Code Display
```tsx
<DSLCodeBlock>
  <DSLRule type="entry">
    RSI(14) &lt; 30 AND CLOSE &lt; BB_LOWER(20, 2)
  </DSLRule>
  <DSLRule type="exit">
    RSI(14) &gt; 70 OR CLOSE &gt; BB_UPPER(20, 2)
  </DSLRule>
</DSLCodeBlock>
```

## Responsive Design

### Breakpoints

```typescript
const breakpoints = {
  mobile: '640px',   // sm
  tablet: '768px',   // md
  desktop: '1024px', // lg
  wide: '1280px',    // xl
};
```

### Layout Adaptations

**Mobile (< 768px)**:
- Single column layout
- Collapsible sections
- Bottom navigation
- Simplified charts
- Stacked metric cards

**Tablet (768px - 1024px)**:
- Two column layout
- Side navigation
- Responsive charts
- Grid metric cards

**Desktop (> 1024px)**:
- Three column layout
- Full navigation
- Detailed charts
- Dashboard grid

## Performance Optimization

### Code Splitting

```typescript
// Lazy load heavy components
const AutonomousPage = lazy(() => import('./pages/Autonomous'));
const PerformanceCharts = lazy(() => import('./components/PerformanceCharts'));
const CorrelationMatrix = lazy(() => import('./components/CorrelationMatrix'));
```

### Data Caching

```typescript
// Cache strategy
const cacheConfig = {
  status: { ttl: 30000 },      // 30 seconds
  metrics: { ttl: 60000 },     // 1 minute
  strategies: { ttl: 120000 }, // 2 minutes
  config: { ttl: 300000 },     // 5 minutes
};
```

### WebSocket Optimization

```typescript
// Throttle high-frequency updates
const throttledUpdate = throttle((data) => {
  dispatch(updateStatus(data));
}, 1000); // Max 1 update per second

// Batch notifications
const batchNotifications = debounce((notifications) => {
  dispatch(addNotifications(notifications));
}, 500);
```

## Testing Strategy

### Unit Tests

```typescript
// Component tests
describe('AutonomousStatus', () => {
  it('displays enabled status correctly', () => { ... });
  it('shows market regime with correct color', () => { ... });
  it('formats cycle statistics', () => { ... });
  it('handles manual trigger click', () => { ... });
});

// Redux tests
describe('autonomousReducer', () => {
  it('updates status on fetch success', () => { ... });
  it('handles trigger cycle action', () => { ... });
  it('updates config correctly', () => { ... });
});
```

### Integration Tests

```typescript
// API integration
describe('Autonomous API', () => {
  it('fetches status successfully', async () => { ... });
  it('triggers cycle and receives events', async () => { ... });
  it('updates configuration', async () => { ... });
});

// WebSocket integration
describe('WebSocket Events', () => {
  it('receives status updates', async () => { ... });
  it('handles cycle events', async () => { ... });
  it('processes notifications', async () => { ... });
});
```

### E2E Tests

```typescript
// User flows
describe('Autonomous Trading Flow', () => {
  it('user can view autonomous status', () => { ... });
  it('user can trigger cycle manually', () => { ... });
  it('user can update configuration', () => { ... });
  it('user receives real-time notifications', () => { ... });
  it('user can view strategy details', () => { ... });
});
```

## Migration Strategy

### Phase 1: Remove Legacy Components (Week 1)

1. Remove VibeCoding component and related code
2. Remove SocialInsights component
3. Remove SmartPortfolios component
4. Remove LLM service references from frontend
5. Clean up unused dependencies
6. Update navigation to remove old routes

### Phase 2: Backend API Implementation (Week 1-2)

1. Implement autonomous status endpoint
2. Implement configuration endpoints
3. Implement proposals/retirements endpoints
4. Implement performance/analytics endpoints
5. Add WebSocket event handlers
6. Test all endpoints with existing backend

### Phase 3: Core Components (Week 2-3)

1. Build AutonomousStatus component
2. Build PerformanceD ashboard component
3. Enhance Strategies component
4. Build configuration UI
5. Implement notification system
6. Add WebSocket integration

### Phase 4: Autonomous Page (Week 3-4)

1. Create Autonomous page layout
2. Build lifecycle visualization
3. Build portfolio composition view
4. Build history & analytics
5. Integrate all components
6. Add routing and navigation

### Phase 5: Testing & Polish (Week 4)

1. Unit test all components
2. Integration test API calls
3. E2E test user flows
4. Performance optimization
5. Responsive design testing
6. Accessibility audit
7. Documentation

## Accessibility

### WCAG 2.1 AA Compliance

- Keyboard navigation for all interactive elements
- ARIA labels for screen readers
- Color contrast ratios > 4.5:1
- Focus indicators on all focusable elements
- Alt text for all images/icons
- Semantic HTML structure

### Keyboard Shortcuts

```typescript
const shortcuts = {
  'Ctrl+T': 'Trigger autonomous cycle',
  'Ctrl+S': 'Open settings',
  'Ctrl+H': 'View history',
  'Ctrl+N': 'View notifications',
  'Esc': 'Close modal/drawer',
};
```

## Error Handling

### Error States

```typescript
interface ErrorState {
  type: 'network' | 'validation' | 'server' | 'unknown';
  message: string;
  details?: string;
  retryable: boolean;
  action?: {
    label: string;
    handler: () => void;
  };
}
```

### Error Display

```tsx
<ErrorBoundary
  fallback={(error) => (
    <ErrorDisplay
      type={error.type}
      message={error.message}
      onRetry={error.retryable ? handleRetry : undefined}
    />
  )}
>
  <AutonomousPage />
</ErrorBoundary>
```

## Security Considerations

### Authentication

- All API calls include JWT token
- Token refresh on expiration
- Logout on 401 responses
- Secure WebSocket connection

### Data Validation

- Validate all user inputs
- Sanitize configuration values
- Prevent XSS in DSL display
- Rate limit API calls

### Permissions

```typescript
interface UserPermissions {
  canViewAutonomous: boolean;
  canTriggerCycle: boolean;
  canModifyConfig: boolean;
  canRetireStrategies: boolean;
}
```

## Documentation

### Component Documentation

Each component includes:
- Purpose and usage
- Props interface
- Example usage
- Accessibility notes
- Testing examples

### API Documentation

Each endpoint includes:
- Request/response types
- Example payloads
- Error responses
- Rate limits
- Authentication requirements

### User Guide

- Getting started with autonomous trading
- Understanding market regimes
- Configuring thresholds
- Interpreting performance metrics
- Troubleshooting common issues



## Additional Components for Trading Operations

### 7. Enhanced Orders Component with Strategy Attribution

**Purpose**: Monitor orders generated by autonomous strategies with full context

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ 📋 Orders & Execution Monitoring                            │
│                                                               │
│  Filter: [All ▼] [Strategy ▼] [Status ▼] [Today ▼]         │
│  Execution Quality: Avg Slippage 0.05% | Fill Rate 98.2%   │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Symbol  Side  Qty    Price    Status    Strategy   Time    │
│  ──────────────────────────────────────────────────────────  │
│  SPY     BUY   10.5   $445.20  FILLED    RSI Mean   10:23   │
│  📋 Entry: RSI(14) < 30 triggered at RSI=28.5               │
│  Slippage: 0.03% | Fill Time: 1.2s                          │
│  [View Strategy] [View Chart]                                │
│                                                               │
│  ──────────────────────────────────────────────────────────  │
│  QQQ     SELL  8.2    $385.10  FILLED    RSI Mean   10:18   │
│  📋 Exit: RSI(14) > 70 triggered at RSI=72.1                │
│  Slippage: 0.04% | Fill Time: 0.8s | P&L: +$124.50 (+3.2%) │
│  [View Strategy] [View Chart]                                │
│                                                               │
│  ──────────────────────────────────────────────────────────  │
│  AAPL    BUY   15.0   $178.45  PENDING   MACD Mom   10:25   │
│  📋 Entry: MACD CROSSES_ABOVE SIGNAL                        │
│  Waiting for fill... [Cancel Order]                         │
│                                                               │
│  ──────────────────────────────────────────────────────────  │
│  MSFT    BUY   12.0   $380.20  REJECTED  Bollinger  10:20   │
│  ⚠️ Reason: Insufficient margin                              │
│  [Retry] [Adjust Quantity] [View Details]                   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

**Enhanced Order Data**:
```typescript
interface EnhancedOrder extends Order {
  strategyId: string;
  strategyName: string;
  triggerRule?: string; // DSL rule that triggered the order
  triggerValue?: number; // Indicator value at trigger
  executionMetrics?: {
    slippage: number; // percentage
    fillTime: number; // seconds
    expectedPrice: number;
    actualPrice: number;
  };
  pnl?: {
    amount: number;
    percentage: number;
  };
  rejectionReason?: string;
}
```

### 8. Risk Management Dashboard Component

**Purpose**: Real-time portfolio risk monitoring and alerts

**Location**: Dashboard (full width, prominent position)

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ ⚠️ Risk Management Dashboard                                 │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Portfolio Risk Metrics                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ VaR 95%  │  │ Max Pos  │  │ Drawdown │  │ Leverage │   │
│  │ $2,450   │  │   15%    │  │  -8.2%   │  │   1.2x   │   │
│  │ ✓ Safe   │  │ ✓ Safe   │  │ ⚠️ Watch  │  │ ✓ Safe   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                               │
│  Risk Thresholds                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Current Drawdown:  ────────●──  -8.2% / -15% max    │   │
│  │ Portfolio VaR:     ──●────────  $2.4K / $5K max     │   │
│  │ Max Position:      ────●──────  15% / 20% max       │   │
│  │ Leverage:          ●──────────  1.2x / 2.0x max     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Risk by Strategy                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ RSI Mean Reversion    VaR: $850  | Beta: 0.85       │   │
│  │ MACD Momentum         VaR: $620  | Beta: 1.15       │   │
│  │ Bollinger Breakout    VaR: $480  | Beta: 0.92       │   │
│  │ SMA Crossover         VaR: $500  | Beta: 1.05       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Active Positions with Stop-Loss/Take-Profit                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ SPY  10.5 @ $445.20  SL: $435.00 (-2.3%)  TP: $460  │   │
│  │ QQQ   8.2 @ $385.10  SL: $377.00 (-2.1%)  TP: $398  │   │
│  │ AAPL 15.0 @ $178.45  SL: $174.50 (-2.2%)  TP: $185  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  [Configure Risk Limits] [View Risk History] [Export]       │
└─────────────────────────────────────────────────────────────┘
```

**Risk Metrics Data Structure**:
```typescript
interface RiskMetrics {
  portfolioVaR: {
    value: number;
    confidence: number; // 0.95 for 95%
    threshold: number;
    status: 'safe' | 'warning' | 'danger';
  };
  maxPositionSize: {
    current: number; // percentage
    threshold: number;
    status: 'safe' | 'warning' | 'danger';
  };
  drawdown: {
    current: number; // percentage
    max: number;
    threshold: number;
    status: 'safe' | 'warning' | 'danger';
  };
  leverage: {
    current: number;
    threshold: number;
    status: 'safe' | 'warning' | 'danger';
  };
  portfolioBeta: number;
  marginUtilization: number; // percentage
  strategyRisk: Array<{
    strategyId: string;
    strategyName: string;
    var: number;
    beta: number;
    contribution: number; // percentage of total risk
  }>;
  activePositions: Array<{
    symbol: string;
    quantity: number;
    entryPrice: number;
    currentPrice: number;
    stopLoss: number;
    takeProfit: number;
    unrealizedPnL: number;
    riskAmount: number;
  }>;
}
```

### 9. Order Execution Quality Analytics

**Purpose**: Track and analyze execution quality over time

**Visual Design**:
```
┌─────────────────────────────────────────────────────────────┐
│ 📊 Execution Quality Analytics                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Last 30 Days                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Avg      │  │ Fill     │  │ Avg Fill │  │ Rejected │   │
│  │ Slippage │  │ Rate     │  │ Time     │  │ Orders   │   │
│  │  0.05%   │  │  98.2%   │  │  1.2s    │  │   2.1%   │   │
│  │  ↓ 0.01% │  │  ↑ 0.3%  │  │  ↓ 0.2s  │  │  ↓ 0.5%  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                               │
│  Slippage by Strategy                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [Bar chart showing avg slippage per strategy]      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Fill Rate Over Time                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  [Line chart showing fill rate trend]               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  Rejection Reasons                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Insufficient Margin    ████████░░ 45%              │   │
│  │  Price Limit Exceeded   ████░░░░░░ 25%              │   │
│  │  Symbol Not Tradeable   ███░░░░░░░ 20%              │   │
│  │  Other                  ██░░░░░░░░ 10%              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```



### Additional API Endpoints for Risk & Orders

```typescript
// GET /api/risk/metrics
interface RiskMetricsResponse {
  portfolioVaR: VaRMetric;
  maxPositionSize: PositionMetric;
  drawdown: DrawdownMetric;
  leverage: LeverageMetric;
  portfolioBeta: number;
  marginUtilization: number;
  strategyRisk: StrategyRiskMetric[];
  activePositions: PositionWithRisk[];
  lastUpdated: string;
}

// GET /api/risk/history
interface RiskHistoryRequest {
  metric: 'var' | 'drawdown' | 'leverage' | 'beta';
  period: '1D' | '1W' | '1M' | '3M';
}
interface RiskHistoryResponse {
  metric: string;
  data: Array<{
    timestamp: string;
    value: number;
    threshold?: number;
  }>;
}

// GET /api/orders/execution-quality
interface ExecutionQualityRequest {
  period?: '1D' | '1W' | '1M' | '3M';
  strategyId?: string;
}
interface ExecutionQualityResponse {
  avgSlippage: MetricWithChange;
  fillRate: MetricWithChange;
  avgFillTime: MetricWithChange;
  rejectionRate: MetricWithChange;
  slippageByStrategy: Array<{
    strategyId: string;
    strategyName: string;
    avgSlippage: number;
    orderCount: number;
  }>;
  fillRateHistory: HistoryPoint[];
  rejectionReasons: Array<{
    reason: string;
    count: number;
    percentage: number;
  }>;
}

// GET /api/orders/by-strategy
interface OrdersByStrategyRequest {
  strategyId?: string;
  status?: OrderStatus;
  startDate?: string;
  endDate?: string;
  limit?: number;
}
interface OrdersByStrategyResponse {
  orders: EnhancedOrder[];
  total: number;
  summary: {
    totalOrders: number;
    filled: number;
    pending: number;
    cancelled: number;
    rejected: number;
    avgSlippage: number;
    totalPnL: number;
  };
}

// PUT /api/risk/limits
interface RiskLimitsUpdateRequest {
  maxVaR?: number;
  maxDrawdown?: number;
  maxPositionSize?: number;
  maxLeverage?: number;
}
interface RiskLimitsUpdateResponse {
  success: boolean;
  limits: RiskLimits;
}
```

### WebSocket Events for Risk & Orders

```typescript
// Risk alerts
{
  channel: 'risk:alerts',
  event: 'threshold_warning',
  data: {
    metric: 'drawdown',
    current: 0.12,
    threshold: 0.15,
    severity: 'warning'
  }
}

{
  channel: 'risk:alerts',
  event: 'threshold_breach',
  data: {
    metric: 'var',
    current: 5200,
    threshold: 5000,
    severity: 'danger',
    action: 'Position reduction recommended'
  }
}

// Order execution events
{
  channel: 'orders:execution',
  event: 'order_filled',
  data: {
    orderId: 'abc123',
    strategyId: 'xyz789',
    strategyName: 'RSI Mean Reversion',
    symbol: 'SPY',
    executionMetrics: {
      slippage: 0.03,
      fillTime: 1.2,
      expectedPrice: 445.00,
      actualPrice: 445.13
    }
  }
}

{
  channel: 'orders:execution',
  event: 'order_rejected',
  data: {
    orderId: 'def456',
    strategyId: 'xyz789',
    symbol: 'MSFT',
    reason: 'Insufficient margin',
    severity: 'error'
  }
}
```

