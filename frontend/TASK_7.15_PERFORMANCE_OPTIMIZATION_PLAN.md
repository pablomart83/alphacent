# Task 7.15: Performance Optimization Plan

**Status**: Ready to Execute  
**Priority**: HIGH  
**Estimated Time**: 8-12 hours

---

## Problem Summary

The frontend is loading very slowly (5-8 seconds initial load, 1-2 seconds per page navigation) due to:

1. **No code splitting** - All pages bundled together (~2-3MB)
2. **No data caching** - Same API calls repeated across pages
3. **No build optimization** - Vite config missing production settings
4. **Unoptimized re-renders** - Missing React.memo and useMemo
5. **Heavy dependencies loaded upfront** - Recharts, Framer Motion, TanStack Table

---

## Optimization Strategy

### Phase 1: Critical (Biggest Impact)
**Time**: 2-3 hours  
**Impact**: 50-60% improvement

1. **Route-based code splitting**
   - Convert all page imports to `React.lazy()`
   - Add `<Suspense>` boundaries with loading fallbacks
   - Reduce initial bundle from ~2MB to ~500KB

2. **Vite build optimization**
   - Add manual chunk splitting for vendors
   - Enable terser minification
   - Configure tree shaking
   - Add compression

**Files to modify**:
- `frontend/src/App.tsx` (add lazy imports)
- `frontend/vite.config.ts` (add build config)

---

### Phase 2: Data Caching (Second Biggest Impact)
**Time**: 2-3 hours  
**Impact**: 30-40% improvement

1. **Create Zustand cache store**
   - Cache account info (30s TTL)
   - Cache positions (10s TTL)
   - Cache orders (10s TTL)
   - Implement stale-while-revalidate

2. **Reduce API calls**
   - Share cached data across pages
   - Deduplicate parallel requests
   - Combine related endpoints

**Files to create**:
- `frontend/src/stores/dataCache.ts` (new)

**Files to modify**:
- All page components (use cache instead of direct API calls)

---

### Phase 3: Component Optimization
**Time**: 2-3 hours  
**Impact**: 10-20% improvement

1. **Lazy load heavy components**
   - Lazy load DataTable (only when tab opened)
   - Lazy load Charts (only when visible)
   - Lazy load Framer Motion animations

2. **Memoization**
   - Add `React.memo` to MetricCard, DataTable, Card
   - Add `useMemo` for filtered/sorted data
   - Add `useCallback` for event handlers

3. **WebSocket optimization**
   - Move subscriptions to global context
   - Reduce duplicate handlers
   - Optimize throttling

**Files to modify**:
- `frontend/src/pages/OverviewNew.tsx`
- `frontend/src/pages/PortfolioNew.tsx`
- `frontend/src/pages/OrdersNew.tsx`
- `frontend/src/pages/StrategiesNew.tsx`
- `frontend/src/pages/AutonomousNew.tsx`
- `frontend/src/pages/RiskNew.tsx`
- `frontend/src/pages/AnalyticsNew.tsx`
- `frontend/src/components/trading/MetricCard.tsx`
- `frontend/src/components/trading/DataTable.tsx`

---

### Phase 4: Loading States & UX
**Time**: 1-2 hours  
**Impact**: Perceived performance improvement

1. **Add skeleton loaders**
   - Replace "Loading..." text with Skeleton components
   - Show layout structure while loading
   - Progressive loading (layout → data)

2. **Optimistic updates**
   - Update UI immediately on user actions
   - Revert on error

**Files to modify**:
- All page components (replace loading states)

---

### Phase 5: Testing & Validation
**Time**: 1-2 hours

1. **Performance testing**
   - Lighthouse audit (target: 85+)
   - Bundle size analysis (target: <500KB initial)
   - Network waterfall analysis
   - React DevTools profiler

2. **Metrics to achieve**
   - Initial load: <2s (fast), <3s (slow 3G)
   - Page navigation: <500ms
   - Lighthouse score: >85
   - 60 FPS during interactions

---

## Implementation Order

### Step 1: Code Splitting (30 min)
```typescript
// frontend/src/App.tsx
import { lazy, Suspense } from 'react';

const Overview = lazy(() => import('./pages/OverviewNew'));
const Portfolio = lazy(() => import('./pages/PortfolioNew'));
// ... etc

<Route 
  path="/" 
  element={
    <ProtectedRoute>
      <Suspense fallback={<LoadingOverlay message="Loading..." />}>
        <Overview onLogout={handleLogout} />
      </Suspense>
    </ProtectedRoute>
  } 
/>
```

### Step 2: Vite Build Config (30 min)
```typescript
// frontend/vite.config.ts
export default defineConfig({
  // ... existing config
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'ui-vendor': ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu'],
          'chart-vendor': ['recharts'],
          'table-vendor': ['@tanstack/react-table'],
          'animation-vendor': ['framer-motion'],
        },
      },
    },
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
  },
})
```

### Step 3: Data Cache Store (1 hour)
```typescript
// frontend/src/stores/dataCache.ts
import create from 'zustand';

export const useDataCache = create((set, get) => ({
  accountInfo: null,
  positions: null,
  orders: null,
  
  setAccountInfo: (data) => set({ accountInfo: { data, timestamp: Date.now() } }),
  setPositions: (data) => set({ positions: { data, timestamp: Date.now() } }),
  setOrders: (data) => set({ orders: { data, timestamp: Date.now() } }),
  
  isStale: (key, maxAge) => {
    const entry = get()[key];
    if (!entry) return true;
    return Date.now() - entry.timestamp > maxAge;
  },
}));
```

### Step 4: Update Pages to Use Cache (2-3 hours)
```typescript
// Example: frontend/src/pages/OverviewNew.tsx
const cache = useDataCache();

const fetchData = async () => {
  // Check cache first
  if (!cache.isStale('accountInfo', 30000)) {
    setAccountInfo(cache.accountInfo.data);
  } else {
    const account = await apiClient.getAccountInfo(tradingMode);
    cache.setAccountInfo(account);
    setAccountInfo(account);
  }
  // ... similar for positions, orders
};
```

### Step 5: Add Memoization (2-3 hours)
```typescript
// Add useMemo for expensive calculations
const filteredPositions = useMemo(() => 
  positions.filter(p => /* filter logic */),
  [positions, positionSearch, positionSideFilter]
);

// Memoize components
const MemoizedDataTable = memo(DataTable);
const MemoizedMetricCard = memo(MetricCard);
```

### Step 6: Lazy Load Components (1-2 hours)
```typescript
// Lazy load charts
const PieChart = lazy(() => import('recharts').then(m => ({ default: m.PieChart })));

// Lazy load tables
{activeTab === 'positions' && (
  <Suspense fallback={<Skeleton />}>
    <DataTable data={positions} />
  </Suspense>
)}
```

### Step 7: Add Skeletons (1 hour)
```typescript
// Replace loading states
if (loading) {
  return (
    <DashboardLayout onLogout={onLogout}>
      <div className="p-8 space-y-6">
        <Skeleton className="h-32 w-full" />
        <div className="grid grid-cols-3 gap-4">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      </div>
    </DashboardLayout>
  );
}
```

### Step 8: Test & Validate (1-2 hours)
```bash
# Build and analyze
npm run build
npx vite-bundle-visualizer

# Run Lighthouse
lighthouse http://localhost:5173 --view

# Test on slow network
# Chrome DevTools → Network → Slow 3G
```

---

## Expected Results

### Before Optimization
- Initial load: 5-8s
- Page navigation: 1-2s
- Bundle size: ~2-3MB
- Lighthouse: 30-40

### After Optimization
- Initial load: 1-2s (70-80% faster)
- Page navigation: 200-500ms (75% faster)
- Bundle size: <500KB initial, <1MB total (80% smaller)
- Lighthouse: 85-95 (2-3x better)

---

## Success Criteria

✅ Initial page load < 2s on fast connection  
✅ Initial page load < 3s on slow 3G  
✅ Page navigation < 500ms  
✅ Lighthouse score > 85  
✅ Bundle size < 500KB initial chunk  
✅ No janky scrolling or animations  
✅ Smooth real-time WebSocket updates  
✅ 60 FPS during interactions  

---

## References

- **Diagnostic Report**: `frontend/PERFORMANCE_DIAGNOSTIC_REPORT.md`
- **Task Definition**: `.kiro/specs/autonomous-trading-ui-overhaul/tasks.md` (Task 7.15)

---

**Ready to execute!** All analysis complete, specific changes identified, implementation order defined.
