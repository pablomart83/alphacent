# Frontend Strategy Visualization Plan - Alpha Edge Integration

## Overview

Enhanced Task 9 to ensure proper visualization of strategy types (Alpha Edge vs Template-Based) throughout the frontend, particularly in the Active Strategies tab and strategy detail views.

## What Was Added to Task 9

### New Subtask 9.6: Enhance Active Strategies Tab Visualization

**Purpose:** Make it easy for users to distinguish between Alpha Edge strategies (specialized, fundamental-driven) and Template-Based strategies (technical indicators).

#### Active Strategies Table Enhancements
- **New "Category" Column:** Shows "Alpha Edge" or "Template-Based"
- **New "Strategy Type" Column:** Shows specific type (Mean Reversion, Trend Following, Momentum, etc.)
- **Visual Indicators:** Icons for each strategy type
  - 📊 Mean Reversion
  - 📈 Trend Following
  - ⚡ Momentum
  - 💥 Breakout
  - 📉 Volatility
- **Filter Dropdowns:**
  - Category filter: All | Alpha Edge | Template-Based
  - Type filter: All | Mean Reversion | Trend Following | Momentum | etc.

#### Strategy Cards Enhancements
- **Category Badges:** Prominent "Alpha Edge" badge on specialized strategies
- **Strategy Type Icons:** Visual indicator of strategy type
- **Tooltips:** Explain difference between Alpha Edge and Template strategies

#### Distribution Charts
- **Pie Chart:** Alpha Edge vs Template-Based distribution
- **Bar Chart:** Strategy type distribution across all active strategies

#### Strategy Detail Modal
- **Strategy Category Section:**
  - Shows if Alpha Edge or Template-Based
  - Shows if requires fundamental data
  - Shows if requires earnings data
  - Shows specific requirements (e.g., market cap for Quality Mean Reversion)
  - Shows sector ETF list for Sector Rotation

### Enhanced Subtask 9.5: Strategy Details Enhancement

Added strategy category visualization:
- **Category Badge:** "Alpha Edge" (purple/gold) or "Template" (blue/gray)
- **Strategy Type Icon:** Visual indicator
- **Metadata Display:**
  - Fundamental data requirements
  - Earnings data requirements
  - Market cap requirements
  - Sector-specific info

### New Subtask 9.7: Backend API Support for Strategy Metadata

**Purpose:** Ensure backend provides all necessary data for frontend visualization.

#### Enhanced API Responses
All strategy endpoints now include:
```json
{
  "id": "strategy-123",
  "name": "Quality Mean Reversion",
  "template_name": "Quality Mean Reversion",
  "strategy_category": "alpha_edge",  // NEW
  "strategy_type": "mean_reversion",  // NEW
  "requires_fundamental_data": true,  // NEW
  "requires_earnings_data": false,    // NEW
  "metadata": {                        // NEW
    "requires_quality_screening": true,
    "min_market_cap": 10000000000,
    "strategy_category": "alpha_edge"
  },
  // ... existing fields
}
```

#### New API Endpoints
1. **GET /api/strategies/categories**
   - Returns available categories with counts
   ```json
   {
     "categories": [
       {"name": "alpha_edge", "count": 3, "label": "Alpha Edge"},
       {"name": "template_based", "count": 15, "label": "Template-Based"}
     ]
   }
   ```

2. **GET /api/strategies/types**
   - Returns available strategy types with counts
   ```json
   {
     "types": [
       {"name": "mean_reversion", "count": 8, "label": "Mean Reversion"},
       {"name": "trend_following", "count": 5, "label": "Trend Following"},
       {"name": "momentum", "count": 3, "label": "Momentum"},
       {"name": "breakout", "count": 2, "label": "Breakout"}
     ]
   }
   ```

## Visual Design Specifications

### Badge Colors
```css
/* Alpha Edge Badge */
.badge-alpha-edge {
  background: linear-gradient(135deg, #8b5cf6 0%, #fbbf24 100%);
  color: white;
  font-weight: 600;
}

/* Template Badge */
.badge-template {
  background: #3b82f6;
  color: white;
}

/* Strategy Type Badges */
.badge-mean-reversion { background: #10b981; }
.badge-trend-following { background: #3b82f6; }
.badge-momentum { background: #f59e0b; }
.badge-breakout { background: #ef4444; }
.badge-volatility { background: #8b5cf6; }
```

### Strategy Type Icons
Text-based labels only:
- Mean Reversion
- Trend Following
- Momentum
- Breakout
- Volatility

### Tooltip Content
```
Alpha Edge Strategies
━━━━━━━━━━━━━━━━━━━━
Specialized strategies that use fundamental 
analysis and custom logic:

• Earnings Momentum - Post-earnings drift
• Sector Rotation - Macro-driven sector ETFs
• Quality Mean Reversion - Large-cap oversold

Template-Based Strategies
━━━━━━━━━━━━━━━━━━━━━━━━
Technical indicator strategies generated 
from 71+ proven templates:

• RSI, MACD, Bollinger Bands
• Moving Average crossovers
• Breakout patterns
```

## Implementation Flow

### Phase 1: Backend (Task 9.7)
1. Add strategy_category and strategy_type fields to Strategy model
2. Update strategy generation to populate these fields
3. Enhance API endpoints to return metadata
4. Create new /categories and /types endpoints

### Phase 2: Frontend Data Layer (Task 9.6)
1. Update TypeScript Strategy interface
2. Add category and type fields
3. Update API service calls

### Phase 3: Frontend UI (Task 9.5 & 9.6)
1. Create badge components
2. Add columns to Active Strategies table
3. **Update filter logic:**
   - Add `categoryFilter` and `typeFilter` state variables
   - Add `availableCategories` computed property
   - Add `availableTypes` computed property
   - Update `filterStrategies()` to include:
     ```typescript
     const matchesCategory = categoryFilter === 'all' || strategy.strategy_category === categoryFilter;
     const matchesType = typeFilter === 'all' || strategy.strategy_type === typeFilter;
     ```
4. Add filter dropdowns to UI
5. Create distribution charts
6. Enhance strategy detail modal
7. Add tooltips and help text

## Example: Active Strategies Table

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│ Active Strategies (18)                                                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│ Filters: [Search: ___] [Status: All ▼] [Template: All ▼] [Regime: All ▼]             │
│          [Category: All ▼] [Type: All ▼] [Source: All ▼]                              │
├──────────┬────────────────┬──────────────────┬──────────────┬─────────┬────────┬───────┤
│ Name     │ Template       │ Category         │ Type         │ Status  │ Return │ ... │
├──────────┼────────────────┼──────────────────┼──────────────┼─────────┼────────┼───────┤
│ QMR-001  │ Quality MR     │ [Alpha Edge]     │ Mean Rev     │ LIVE    │ +8.2%  │ ... │
│ EM-003   │ Earnings Mom   │ [Alpha Edge]     │ Momentum     │ LIVE    │ +12.5% │ ... │
│ SR-002   │ Sector Rot     │ [Alpha Edge]     │ Momentum     │ LIVE    │ +5.1%  │ ... │
│ RSI-045  │ RSI MR         │ [Template]       │ Mean Rev     │ LIVE    │ +3.8%  │ ... │
│ MACD-023 │ MACD Mom       │ [Template]       │ Trend        │ LIVE    │ +6.2%  │ ... │
│ BB-089   │ BB Bounce      │ [Template]       │ Mean Rev     │ LIVE    │ +4.1%  │ ... │
└──────────┴────────────────┴──────────────────┴──────────────┴─────────┴────────┴───────┘

Note: Existing columns (Symbols, Allocation, etc.) remain unchanged
Category and Type filters work alongside existing Status, Template, Regime, Source filters
```

## Filter Implementation Details

### Current Filters (Existing)
```typescript
const [searchQuery, setSearchQuery] = useState('');
const [statusFilter, setStatusFilter] = useState('all');
const [templateFilter, setTemplateFilter] = useState('all');
const [regimeFilter, setRegimeFilter] = useState('all');
const [sourceFilter, setSourceFilter] = useState('all');
```

### New Filters (To Add)
```typescript
const [categoryFilter, setCategoryFilter] = useState('all');
const [typeFilter, setTypeFilter] = useState('all');

// Computed available values
const availableCategories = useMemo(() => {
  const categories = new Set<string>();
  strategies.forEach(s => {
    if (s.strategy_category) categories.add(s.strategy_category);
  });
  return Array.from(categories).sort();
}, [strategies]);

const availableTypes = useMemo(() => {
  const types = new Set<string>();
  strategies.forEach(s => {
    if (s.strategy_type) types.add(s.strategy_type);
  });
  return Array.from(types).sort();
}, [strategies]);
```

### Updated Filter Function
```typescript
const filterStrategies = (strategyList: Strategy[]) => {
  return strategyList.filter(strategy => {
    const matchesSearch = 
      strategy.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      strategy.symbols.some(s => s.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesStatus = statusFilter === 'all' || strategy.status === statusFilter;
    const matchesTemplate = templateFilter === 'all' || strategy.template_name === templateFilter;
    const matchesRegime = regimeFilter === 'all' || strategy.market_regime === regimeFilter;
    const matchesSource = sourceFilter === 'all' || strategy.source === sourceFilter;
    
    // NEW: Category and Type filters
    const matchesCategory = categoryFilter === 'all' || strategy.strategy_category === categoryFilter;
    const matchesType = typeFilter === 'all' || strategy.strategy_type === typeFilter;
    
    return matchesSearch && matchesStatus && matchesTemplate && 
           matchesRegime && matchesSource && matchesCategory && matchesType;
  });
};
```

## Example: Strategy Detail Modal

```
┌─────────────────────────────────────────────────────────────────┐
│ Strategy Details: Quality Mean Reversion #QMR-001              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ [Alpha Edge Strategy]  Mean Reversion                          │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ Strategy Category                                       │   │
│ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │   │
│ │ Type: Alpha Edge - Quality Mean Reversion              │   │
│ │ Strategy Type: Mean Reversion                           │   │
│ │ Requires Fundamental Data: ✓ Yes                       │   │
│ │ Requires Earnings Data: ✗ No                           │   │
│ │                                                         │   │
│ │ Quality Criteria:                                       │   │
│ │ • Market Cap: > $10B (large-cap only)                  │   │
│ │ • ROE: > 15% (strong profitability)                    │   │
│ │ • Debt/Equity: < 0.5 (healthy balance sheet)           │   │
│ │                                                         │   │
│ │ Entry Conditions:                                       │   │
│ │ • RSI < 30 (oversold)                                   │   │
│ │ • Down >10% in 5 days                                   │   │
│ │ • RSI crosses above 30 (entry signal)                  │   │
│ └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ Fundamental Data                                        │   │
│ │ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ │   │
│ │ Symbol: AAPL                                            │   │
│ │ Market Cap: $2.8T ✓                                     │   │
│ │ ROE: 147.2% ✓                                           │   │
│ │ Debt/Equity: 1.96 ✗                                     │   │
│ │ P/E Ratio: 29.4                                         │   │
│ └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│ [Close]                                                         │
└─────────────────────────────────────────────────────────────────┘
```

## Benefits

### For Users
1. **Clear Distinction:** Immediately see which strategies are specialized Alpha Edge vs standard templates
2. **Better Filtering:** Filter by category and type to focus on specific strategy classes
3. **Informed Decisions:** Understand strategy requirements and characteristics
4. **Visual Clarity:** Icons and badges make scanning large strategy lists easier

### For System
1. **Proper Categorization:** Backend properly tracks strategy categories
2. **Metadata Rich:** All strategy metadata available for analysis
3. **Extensible:** Easy to add new strategy categories or types
4. **Analytics Ready:** Can analyze performance by category/type

## Integration with Existing Features

### Works With:
- ✅ Strategy template system (already has metadata)
- ✅ Fundamental filter (checks strategy category)
- ✅ ML filter (can use category as feature)
- ✅ Trade journal (logs strategy category)
- ✅ Analytics (can compare Alpha Edge vs Template performance)

### Enhances:
- ✅ Strategy selection UI
- ✅ Performance comparison
- ✅ Portfolio diversification view
- ✅ Risk management (different rules for different categories)

## Testing Checklist

### Backend Tests
- [ ] Strategy model includes category and type fields
- [ ] API returns category and type in responses
- [ ] /categories endpoint returns correct counts
- [ ] /types endpoint returns correct counts
- [ ] Metadata properly populated for all strategy types

### Frontend Tests
- [ ] Category badge renders correctly
- [ ] Type icon displays correctly
- [ ] Filters work (category and type)
- [ ] Distribution charts show correct data
- [ ] Strategy detail modal shows metadata
- [ ] Tooltips display on hover

### Integration Tests
- [ ] Alpha Edge strategies show correct badges
- [ ] Template strategies show correct badges
- [ ] Filtering by category works
- [ ] Filtering by type works
- [ ] Charts update when filters change

### Filter Dropdown Options

**Category Filter:**
- All (default)
- Alpha Edge
- Template-Based

**Type Filter:**
- All (default)
- Mean Reversion
- Trend Following
- Momentum
- Breakout
- Volatility

These filters work in combination with existing filters:
- Search (text input)
- Status (All, PROPOSED, BACKTESTED, DEMO, LIVE, RETIRED)
- Template (All, + dynamic list from strategies)
- Regime (All, + dynamic list from strategies)
- Source (All, TEMPLATE, USER)

## Files to Modify

### Backend
- `src/models/dataclasses.py` - Add category/type fields to Strategy
- `src/strategy/strategy_engine.py` - Populate category/type on generation
- `src/api/routes/strategies.py` - Enhance endpoints
- `src/api/routes/strategies.py` - Add /categories and /types endpoints

### Frontend
- `frontend/src/types/index.ts` - Update Strategy interface
- `frontend/src/pages/StrategiesNew.tsx` - Add columns, filters, badges
- `frontend/src/components/ui/Badge.tsx` - Add category badge variants
- `frontend/src/services/api.ts` - Add new endpoint calls

## Summary

Task 9 now includes comprehensive strategy visualization that:
1. ✅ Distinguishes Alpha Edge from Template-Based strategies
2. ✅ Shows strategy types with icons and badges
3. ✅ Provides filtering by category and type
4. ✅ Displays distribution charts
5. ✅ Shows detailed metadata in strategy details
6. ✅ Includes backend API support for all metadata

This ensures users can easily identify, filter, and understand the different types of strategies running in their system, with special emphasis on the new Alpha Edge strategies (Earnings Momentum, Sector Rotation, Quality Mean Reversion).
