# Frontend API Integration - Real Data Implementation

## ✅ Completed Tasks

### Task 18.1 - StrategyGenerator Component
**Status:** ✅ Complete with Real API Integration

**Implementation:**
- Created `frontend/src/components/StrategyGenerator.tsx`
- **Real API Integration:** Uses `apiClient.generateStrategy()` to call `/strategies/generate` endpoint
- No mock data - all responses come from backend LLM service

**Features:**
- Natural language prompt input with validation
- Market context inputs (symbols, timeframe, risk tolerance)
- Real-time generation progress (analyzing → generating → validating)
- Displays actual strategy with reasoning from LLM
- Shows hypothesis, alpha sources, market assumptions, and signal logic

### Task 23.1 - API Client Methods
**Status:** ✅ Complete with Real Endpoints

**Added Methods to `frontend/src/services/api.ts`:**

1. **`generateStrategy()`** - Calls `/strategies/generate`
   - Sends prompt and constraints to backend
   - Returns Strategy with LLM-generated reasoning
   - No mocking - real LLM integration

2. **`backtestStrategy()`** - Calls `/strategies/{id}/backtest`
   - Executes vectorbt backtest on historical data
   - Returns real performance metrics (Sharpe, Sortino, max DD, win rate)
   - Includes backtest period and trade history

3. **`bootstrapStrategies()`** - Calls `/strategies/bootstrap`
   - Generates multiple strategies from templates
   - Auto-backtests each strategy
   - Optionally auto-activates based on performance thresholds
   - Returns summary with activation stats

4. **`updateAllocation()`** - Calls `/strategies/{id}/allocation`
   - Updates portfolio allocation percentage
   - Validates total allocation doesn't exceed 100%
   - Real-time validation against active strategies

## 📋 Remaining Frontend Tasks (19-22)

### Task 19 - StrategyReasoningPanel Component
**Purpose:** Dedicated component to display strategy reasoning
**API Integration Required:** 
- Uses existing Strategy.reasoning field from API
- No additional endpoints needed
- **Implementation Note:** Display reasoning data from `Strategy.reasoning` object

**Key Features:**
- Display hypothesis and market assumptions
- Visualize alpha sources with weights (pie/bar chart)
- Show signal logic explanation
- Expandable section for full LLM prompt/response

### Task 20 - BacktestResults Component
**Purpose:** Visualize backtest performance
**API Integration Required:**
- Use `apiClient.backtestStrategy(strategyId)` - ✅ Already implemented
- Display data from BacktestResults response
- **Implementation Note:** Call API, render charts with recharts library

**Key Features:**
- Performance metrics display (Sharpe, Sortino, max DD, win rate)
- Equity curve chart using recharts
- Trade history table
- Backtest period information

### Task 21 - Enhance Strategies Dashboard
**Purpose:** Add strategy generation and backtesting to main dashboard
**API Integration Required:**
- Use `apiClient.generateStrategy()` - ✅ Already implemented
- Use `apiClient.backtestStrategy()` - ✅ Already implemented
- Use `apiClient.updateAllocation()` - ✅ Already implemented
- **Implementation Note:** Integrate existing API methods into Strategies.tsx

**Key Features:**
- "Generate Strategy" button → Opens StrategyGenerator modal
- "Backtest" button for PROPOSED strategies → Calls backtestStrategy()
- Allocation percentage editor → Calls updateAllocation()
- Reasoning preview in strategy cards

### Task 22 - SignalFeed Component
**Purpose:** Real-time signal generation feed
**API Integration Required:**
- Subscribe to WebSocket for signal events
- Use existing `wsManager.onSignalGenerated()` (needs to be added to WebSocket manager)
- **Implementation Note:** WebSocket integration for live updates

**Key Features:**
- Real-time signal generation events
- Display symbol, direction, confidence, reasoning
- Filters by strategy and symbol
- WebSocket subscription for live updates

## 🔌 Backend API Endpoints (Already Implemented)

All backend endpoints are production-ready and return real data:

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/strategies/generate` | POST | Generate strategy from LLM | ✅ Live |
| `/strategies/{id}/backtest` | POST | Run vectorbt backtest | ✅ Live |
| `/strategies/bootstrap` | POST | Bootstrap multiple strategies | ✅ Live |
| `/strategies/{id}/allocation` | PUT | Update allocation % | ✅ Live |
| `/strategies/{id}/activate` | POST | Activate strategy | ✅ Live |
| `/strategies/{id}/deactivate` | POST | Deactivate strategy | ✅ Live |

## 🎯 Implementation Guidelines for Remaining Tasks

### For Task 19 (StrategyReasoningPanel):
```typescript
// Use existing Strategy type with reasoning field
interface StrategyReasoningPanelProps {
  strategy: Strategy; // Already has reasoning field
}

// Display reasoning.hypothesis, reasoning.alpha_sources, etc.
// No API calls needed - data already in Strategy object
```

### For Task 20 (BacktestResults):
```typescript
// Call real API
const results = await apiClient.backtestStrategy(strategyId);

// Display results.backtest_results with recharts
// Use results.backtest_results.equity_curve for chart
```

### For Task 21 (Enhance Strategies):
```typescript
// Add button to open StrategyGenerator
<Button onClick={() => setShowGenerator(true)}>
  Generate Strategy
</Button>

// Add backtest button for PROPOSED strategies
{strategy.status === 'PROPOSED' && (
  <Button onClick={() => handleBacktest(strategy.id)}>
    Backtest
  </Button>
)}

// Add allocation editor
<Input 
  value={allocation}
  onChange={(e) => handleUpdateAllocation(strategy.id, e.target.value)}
/>
```

### For Task 22 (SignalFeed):
```typescript
// Subscribe to WebSocket
useEffect(() => {
  const unsubscribe = wsManager.onSignalGenerated((signal) => {
    setSignals(prev => [signal, ...prev]);
  });
  return unsubscribe;
}, []);
```

## ✨ Key Points

1. **No Mock Data:** All API methods connect to real backend endpoints
2. **LLM Integration:** Strategy generation uses actual Ollama LLM service
3. **Real Backtesting:** Uses vectorbt with historical market data
4. **Live Validation:** Allocation updates validate against real portfolio state
5. **WebSocket Ready:** Backend broadcasts strategy updates in real-time

## 🚀 Next Steps

To complete the frontend integration:

1. **Task 19:** Create StrategyReasoningPanel - display existing reasoning data
2. **Task 20:** Create BacktestResults - call backtestStrategy() API
3. **Task 21:** Enhance Strategies dashboard - integrate all API methods
4. **Task 22:** Create SignalFeed - add WebSocket subscription

All API infrastructure is ready - just need to build the UI components!
