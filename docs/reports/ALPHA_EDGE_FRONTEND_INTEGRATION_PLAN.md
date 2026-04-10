# Alpha Edge Frontend Integration Plan

## Overview

This document outlines the frontend components needed to support the Alpha Edge improvements. The integration follows the existing patterns in the trading platform UI.

## Frontend Components Required

### 1. Alpha Edge Settings Tab (Task 9.1-9.2)

**Location:** Settings page → New "Alpha Edge" tab

**Purpose:** Allow users to configure all Alpha Edge parameters through the UI

**Components:**

#### A. Fundamental Filter Settings Card
```typescript
interface FundamentalFilterSettings {
  enabled: boolean;
  min_checks_passed: number; // 1-5 slider
  checks: {
    profitable: boolean;
    growing: boolean;
    reasonable_valuation: boolean;
    no_dilution: boolean;
    insider_buying: boolean;
  };
}
```

**UI Elements:**
- Master toggle: Enable/Disable fundamental filtering
- Slider: Minimum checks required (1-5)
- 5 checkboxes for individual checks
- Info tooltips explaining each check
- Visual indicator showing current pass rate

#### B. ML Filter Settings Card
```typescript
interface MLFilterSettings {
  enabled: boolean;
  min_confidence: number; // 0.5-0.95 slider
  retrain_frequency_days: number; // input field
}
```

**UI Elements:**
- Master toggle: Enable/Disable ML filtering
- Slider: Minimum confidence (50%-95%)
- Number input: Retrain frequency (days)
- Model status indicator (last trained, accuracy)
- Link to model performance metrics

#### C. Trading Frequency Settings Card
```typescript
interface TradingFrequencySettings {
  max_active_strategies: number; // 5-20 slider
  min_conviction_score: number; // 50-90 slider
  min_holding_period_days: number; // input field
  max_trades_per_strategy_per_month: number; // input field
}
```

**UI Elements:**
- Slider: Max active strategies (5-20)
- Slider: Min conviction score (50-90)
- Number input: Min holding period (days)
- Number input: Max trades per strategy per month
- Estimated transaction cost savings display

#### D. Strategy Templates Card
```typescript
interface StrategyTemplateSettings {
  earnings_momentum: {
    enabled: boolean;
    // Additional params if needed
  };
  sector_rotation: {
    enabled: boolean;
  };
  quality_mean_reversion: {
    enabled: boolean;
  };
}
```

**UI Elements:**
- 3 toggle switches for each template
- Brief description of each strategy
- Performance preview (if available)

#### E. API Usage Monitoring Card
```typescript
interface APIUsageStats {
  fmp: {
    calls_made: number;
    max_calls: number;
    usage_percent: number;
    calls_remaining: number;
  };
  alpha_vantage: {
    calls_made: number;
    max_calls: number;
    usage_percent: number;
  };
  cache_size: number;
}
```

**UI Elements:**
- Progress bar: FMP API usage (with warning at 80%)
- Progress bar: Alpha Vantage API usage
- Cache statistics display
- Auto-refresh every 30 seconds

**API Endpoints:**
- `GET /api/settings/alpha-edge` - Get current settings
- `PUT /api/settings/alpha-edge` - Update settings
- `GET /api/alpha-edge/api-usage` - Get API usage stats

---

### 2. Alpha Edge Analytics Tab (Task 9.3)

**Location:** Analytics page → New "Alpha Edge" tab

**Purpose:** Display performance metrics specific to Alpha Edge features

**Components:**

#### A. Fundamental Filter Statistics Card
```typescript
interface FundamentalFilterStats {
  total_symbols_checked: number;
  symbols_passed: number;
  pass_rate: number;
  failure_reasons: Array<{
    reason: string;
    count: number;
    percentage: number;
  }>;
}
```

**UI Elements:**
- Metric cards: Total checked, Passed, Pass rate
- Bar chart: Most common failure reasons
- Trend line: Pass rate over time

#### B. ML Filter Statistics Card
```typescript
interface MLFilterStats {
  total_signals_checked: number;
  signals_passed: number;
  avg_confidence: number;
  model_accuracy: number;
  model_precision: number;
  model_recall: number;
  last_trained: string;
}
```

**UI Elements:**
- Metric cards: Signals filtered, Avg confidence, Accuracy
- Line chart: Confidence distribution
- Model performance metrics table
- Last trained timestamp

#### C. Conviction Score Distribution Chart
```typescript
interface ConvictionDistribution {
  score_ranges: Array<{
    range: string; // "70-75", "75-80", etc.
    count: number;
    avg_return: number;
  }>;
}
```

**UI Elements:**
- Histogram: Conviction score distribution
- Overlay: Average return by score range
- Insights: Optimal conviction threshold

#### D. Strategy Template Performance Table
```typescript
interface TemplatePerformance {
  template: string;
  trades: number;
  win_rate: number;
  total_return: number;
  sharpe_ratio: number;
  avg_holding_period: number;
}
```

**UI Elements:**
- Sortable table with all metrics
- Color coding for performance
- Comparison to baseline strategies

#### E. Transaction Cost Savings Card
```typescript
interface TransactionCostSavings {
  before_costs: number;
  after_costs: number;
  savings_amount: number;
  savings_percent: number;
  cost_as_pct_of_returns: number;
}
```

**UI Elements:**
- Before/after comparison chart
- Savings amount ($ and %)
- Cost efficiency metric

**API Endpoints:**
- `GET /api/analytics/alpha-edge/fundamental-filter-stats`
- `GET /api/analytics/alpha-edge/ml-filter-stats`
- `GET /api/analytics/alpha-edge/conviction-distribution`
- `GET /api/analytics/alpha-edge/template-performance`
- `GET /api/analytics/alpha-edge/transaction-costs`

---

### 3. Trade Journal Tab (Task 9.4)

**Location:** Analytics page → New "Trade Journal" tab

**Purpose:** Detailed trade-by-trade analysis with advanced filtering

**Components:**

#### A. Trade Journal Table
```typescript
interface TradeJournalEntry {
  id: string;
  date: string;
  symbol: string;
  strategy_name: string;
  template?: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_percent: number;
  hold_time_hours: number;
  regime: string;
  conviction_score: number;
  ml_confidence?: number;
  entry_reason: string;
  exit_reason: string;
  mae: number; // Max Adverse Excursion
  mfe: number; // Max Favorable Excursion
}
```

**UI Elements:**
- Sortable, filterable data table
- Filters:
  - Date range picker
  - Strategy dropdown (multi-select)
  - Symbol search
  - Regime dropdown
  - Outcome (win/loss/breakeven)
  - Conviction score range
- Pagination
- Export to CSV button
- Column visibility toggle

#### B. MAE/MFE Scatter Plot
```typescript
interface MAEMFEData {
  trades: Array<{
    mae: number;
    mfe: number;
    outcome: 'win' | 'loss';
    pnl: number;
  }>;
}
```

**UI Elements:**
- Scatter plot: MAE (x-axis) vs MFE (y-axis)
- Color coding: Green (wins), Red (losses)
- Size: Proportional to P&L magnitude
- Quadrant analysis overlay
- Insights: Stop loss optimization suggestions

#### C. Pattern Recognition Insights Card
```typescript
interface PatternInsights {
  best_patterns: Array<{
    pattern: string;
    description: string;
    win_rate: number;
    avg_return: number;
    occurrences: number;
  }>;
  worst_patterns: Array<{
    pattern: string;
    description: string;
    win_rate: number;
    avg_return: number;
    occurrences: number;
  }>;
  recommendations: string[];
}
```

**UI Elements:**
- Two lists: Best and Worst patterns
- Actionable recommendations
- "Apply Recommendation" buttons (if applicable)

#### D. Monthly Report Generation
**UI Elements:**
- Date range selector
- "Generate Report" button
- Download PDF/CSV options
- Email report option

**API Endpoints:**
- `GET /api/trade-journal` - List trades with filters
- `GET /api/trade-journal/mae-mfe` - MAE/MFE data
- `GET /api/trade-journal/patterns` - Pattern insights
- `GET /api/trade-journal/export` - Export CSV
- `POST /api/trade-journal/generate-report` - Generate monthly report

---

### 4. Strategy Details Enhancement (Task 9.5)

**Location:** Strategies page → Strategy detail modal/page

**Purpose:** Show Alpha Edge specific data for each strategy

**Enhancements:**

#### A. Fundamental Data Card (if applicable)
```typescript
interface StrategyFundamentals {
  symbol: string;
  eps: number;
  revenue_growth: number;
  pe_ratio: number;
  roe: number;
  debt_to_equity: number;
  checks_passed: Array<{
    check: string;
    passed: boolean;
    value: number;
    reason: string;
  }>;
}
```

**UI Elements:**
- Fundamental metrics display
- Check results with pass/fail indicators
- Timestamp of data fetch

#### B. Alpha Edge Badges
**UI Elements:**
- ML Confidence badge (if ML filtered)
- Conviction Score badge
- Strategy Template badge (if from template)
- Color coding based on values

**API Endpoints:**
- `GET /api/strategies/{id}/fundamentals` - Get fundamental data
- `GET /api/strategies/{id}/alpha-edge-metrics` - Get Alpha Edge metrics

---

## Implementation Order

### Phase 1: Backend API Endpoints (Task 9.1)
1. Settings endpoints for Alpha Edge config
2. API usage statistics endpoint
3. Analytics endpoints for Alpha Edge metrics
4. Trade journal endpoints

### Phase 2: Settings UI (Task 9.2)
1. Create Alpha Edge settings tab
2. Implement all settings cards
3. Add API usage monitoring
4. Add save/reset functionality
5. Add validation

### Phase 3: Analytics UI (Task 9.3)
1. Create Alpha Edge analytics tab
2. Implement fundamental filter stats
3. Implement ML filter stats
4. Add conviction distribution chart
5. Add template performance table
6. Add transaction cost savings

### Phase 4: Trade Journal UI (Task 9.4)
1. Create Trade Journal tab
2. Implement filterable table
3. Add MAE/MFE visualization
4. Add pattern recognition insights
5. Add export functionality

### Phase 5: Strategy Details (Task 9.5)
1. Add fundamental data display
2. Add Alpha Edge badges
3. Update strategy detail API

### Phase 6: Testing (Task 11.3)
1. Test all UI components
2. Test API integration
3. Test real-time updates
4. Performance testing
5. User acceptance testing

---

## Design Patterns to Follow

### 1. Consistent with Existing UI
- Use existing Card, Button, Input components
- Follow color scheme and typography
- Match spacing and layout patterns
- Use existing icons from lucide-react

### 2. Real-time Updates
- Use polling or WebSocket for API usage stats
- Auto-refresh analytics every 30-60 seconds
- Show loading states during updates

### 3. Error Handling
- Display user-friendly error messages
- Show validation errors inline
- Provide retry mechanisms
- Log errors for debugging

### 4. Responsive Design
- Mobile-friendly layouts
- Collapsible sections on small screens
- Touch-friendly controls

### 5. Performance
- Lazy load heavy components
- Paginate large tables
- Cache API responses
- Debounce filter inputs

---

## User Experience Considerations

### 1. Onboarding
- Tooltips explaining each setting
- Default values that work well
- "Recommended" badges on optimal settings
- Link to documentation

### 2. Feedback
- Success toasts on save
- Loading indicators during operations
- Progress bars for long operations
- Confirmation dialogs for destructive actions

### 3. Insights
- Highlight important metrics
- Show trends and changes
- Provide actionable recommendations
- Compare to benchmarks

### 4. Accessibility
- Keyboard navigation
- Screen reader support
- High contrast mode
- Focus indicators

---

## Testing Checklist

### Settings Tab
- [ ] All settings load correctly
- [ ] Changes save successfully
- [ ] Reset button works
- [ ] Validation prevents invalid values
- [ ] API usage updates in real-time
- [ ] Tooltips display correctly

### Analytics Tab
- [ ] All metrics display correctly
- [ ] Charts render properly
- [ ] Filters work as expected
- [ ] Data refreshes automatically
- [ ] Export functions work

### Trade Journal Tab
- [ ] Table loads with pagination
- [ ] Filters work correctly
- [ ] Sorting works on all columns
- [ ] MAE/MFE chart displays
- [ ] Export to CSV works
- [ ] Pattern insights display

### Strategy Details
- [ ] Fundamental data displays
- [ ] Badges show correct values
- [ ] Data updates when strategy changes

---

## Documentation Needed

1. **User Guide**
   - How to configure Alpha Edge settings
   - Understanding fundamental filters
   - Interpreting ML confidence scores
   - Using the trade journal
   - Reading pattern insights

2. **Developer Guide**
   - API endpoint documentation
   - Component architecture
   - State management
   - Testing procedures

3. **Screenshots/Videos**
   - Settings configuration walkthrough
   - Analytics interpretation guide
   - Trade journal usage examples

---

## Success Metrics

### User Adoption
- % of users who enable Alpha Edge features
- % of users who customize settings
- Time spent on Alpha Edge tabs

### Performance Impact
- Page load times < 2 seconds
- API response times < 500ms
- Chart render times < 1 second

### User Satisfaction
- Positive feedback on new features
- Reduced support tickets
- Increased engagement with analytics

---

## Future Enhancements

1. **Advanced Visualizations**
   - 3D scatter plots for multi-dimensional analysis
   - Interactive regime transition maps
   - Real-time strategy performance streaming

2. **AI-Powered Insights**
   - Automated pattern detection
   - Predictive analytics
   - Personalized recommendations

3. **Mobile App**
   - Native mobile experience
   - Push notifications for alerts
   - Simplified mobile UI

4. **Collaboration Features**
   - Share insights with team
   - Compare performance with peers
   - Community patterns library
