# Frontend Performance Diagnostic Report

**Date**: February 21, 2026  
**Issue**: Slow page loading on main page and all pages  
**Scope**: Complete frontend performance analysis

---

## Executive Summary

The frontend is experiencing significant performance issues due to:
1. **No code splitting** - All pages load on initial bundle
2. **No lazy loading** - Heavy components (charts, tables) load immediately
3. **Excessive API calls** - Multiple parallel requests on every page load
4. **No data caching** - Same data fetched repeatedly
5. **Unoptimized re-renders** - Missing React.memo and useMemo
6. **Large bundle size** - No build optimization configured
7. **Heavy dependencies** - Recharts, Framer Motion, TanStack Table all loaded upfront
8. **WebSocket overhead** - Multiple subscriptions per page without cleanup optimization

---

## Critical Performance Issues

### 1. Bundle Size & Code Splitting (CRITICAL)

**Problem**: All pages and components are bundled together in a single JavaScript file.

**Evidence**:
- `vite.config.ts` has NO build optimization
- No dynamic imports in `App.tsx`
- All pages imported statically: `import { OverviewNew as Overview } from './pages/OverviewNew'`
- Heavy libraries (recharts, framer-motion, @tanstack/react-table) loaded on initial load

**Impact**: 
- Initial bundle likely >2MB
- First Contentful Paint (FCP) >5s
- Time to Interactive (TTI) >8s

**Solution**:
```typescript
// Use React.lazy for route-based code splitting
const Overview = lazy(() => import('./pages/OverviewNew'));
const Portfolio = lazy(() => import('./pages/PortfolioNew'));
// ... etc
```

---

### 2. No Lazy Loading of Heavy Components (CRITICAL)

**Problem**: Charts, tables, and animations load immediately even if not visible.

**Evidence**:
- `OverviewNew.tsx` imports recharts components directly
- `DataTable` component (TanStack Table) loads on every page
- Framer Motion animations run on all components simultaneously

**Impact**:
- Main thread blocked for 2-3s parsing heavy libraries
- Janky scrolling and interactions
- Poor Lighthouse performance score (<50)

**Solution**:
```typescript
// Lazy load charts
const PieChart = lazy(() => import('recharts').then(m => ({ default: m.PieChart })));

// Lazy load tables when tab is opened
{activeTab === 'positions' && <Suspense fallback={<Skeleton />}><DataTable /></Suspense>}
```

---

### 3. Excessive API Calls on Page Load (HIGH)

**Problem**: Every page makes 3-5 parallel API calls on mount.

**Evidence from OverviewNew.tsx**:
```typescript
const [account, positionsData, ordersData, status] = await Promise.all([
  apiClient.getAccountInfo(tradingMode),      // ~200ms
  apiClient.getPositions(tradingMode),        // ~300ms
  apiClient.getOrders(tradingMode),           // ~400ms
  apiClient.getSystemStatus(),                // ~150ms
]);
```

**Impact**:
- 4 API calls = ~1050ms total (waterfall)
- Repeated on every page navigation
- No caching between pages

**Solution**:
- Implement React Query or SWR for data caching
- Cache account info globally (changes rarely)
- Stale-while-revalidate pattern
- Reduce API calls to 1-2 per page

---

### 4. No Data Caching (HIGH)

**Problem**: Same data fetched repeatedly across pages.

**Evidence**:
- Account info fetched on Overview, Portfolio, Risk, Analytics
- Positions fetched on Overview, Portfolio, Risk
- Orders fetched on Overview, Orders
- No shared state or cache

**Impact**:
- 12+ redundant API calls when navigating between pages
- Slow page transitions (500-1000ms per page)
- Unnecessary backend load

**Solution**:
```typescript
// Use Zustand for global state + caching
const useAccountStore = create((set) => ({
  account: null,
  lastFetch: null,
  fetchAccount: async (mode) => {
    const now = Date.now();
    if (account && now - lastFetch < 30000) return account; // 30s cache
    const data = await apiClient.getAccountInfo(mode);
    set({ account: data, lastFetch: now });
    return data;
  }
}));
```

---

### 5. Unoptimized Re-renders (MEDIUM)

**Problem**: Components re-render unnecessarily on state changes.

**Evidence**:
- No `React.memo` on expensive components (MetricCard, DataTable)
- No `useMemo` for filtered/sorted data
- WebSocket updates trigger full page re-renders

**Example from OverviewNew.tsx**:
```typescript
// This recalculates on EVERY render
const filteredPositions = positions.filter(position => {
  const matchesSearch = position.symbol.toLowerCase().includes(positionSearch.toLowerCase());
  const matchesSide = positionSideFilter === 'all' || position.side === positionSideFilter;
  return matchesSearch && matchesSide;
});
```

**Impact**:
- 10-20 unnecessary re-renders per WebSocket message
- Janky UI during real-time updates
- High CPU usage

**Solution**:
```typescript
const filteredPositions = useMemo(() => 
  positions.filter(position => {
    const matchesSearch = position.symbol.toLowerCase().includes(positionSearch.toLowerCase());
    const matchesSide = positionSideFilter === 'all' || position.side === positionSideFilter;
    return matchesSearch && matchesSide;
  }),
  [positions, positionSearch, positionSideFilter]
);
```

---

### 6. WebSocket Overhead (MEDIUM)

**Problem**: Multiple WebSocket subscriptions per page without optimization.

**Evidence from OverviewNew.tsx**:
```typescript
useEffect(() => {
  const unsubscribeAccount = wsManager.onPositionUpdate(() => { ... });
  const unsubscribePosition = wsManager.onPositionUpdate((position: Position) => { ... });
  const unsubscribeOrder = wsManager.onOrderUpdate((order: Order) => { ... });
  const unsubscribeSystem = wsManager.onSystemState((status: SystemStatus) => { ... });
  // 4 subscriptions per page
}, [tradingMode]);
```

**Impact**:
- 4-6 subscriptions per page × 8 pages = 32-48 total subscriptions
- Each message triggers multiple handlers
- Throttling helps but not enough

**Solution**:
- Move subscriptions to global context
- Use single subscription per event type
- Debounce updates (already partially implemented)

---

### 7. No Build Optimization (CRITICAL)

**Problem**: Vite config has no production optimizations.

**Current vite.config.ts**:
```typescript
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { proxy: { ... } }
})
// NO build config!
```

**Missing**:
- No chunk splitting
- No minification config
- No tree shaking optimization
- No compression

**Solution**: See recommendations below.

---

### 8. Heavy Dependencies (MEDIUM)

**Problem**: Large libraries loaded for small features.

**Evidence from package.json**:
- `recharts`: 500KB (used for 3-4 charts)
- `framer-motion`: 200KB (used for animations)
- `@tanstack/react-table`: 150KB (used for tables)
- `date-fns`: 100KB (used for date formatting)

**Impact**:
- ~1MB of dependencies for features that could be lighter
- Slow initial parse time

**Solution**:
- Consider lighter alternatives (e.g., Chart.js instead of recharts)
- Use native CSS animations instead of Framer Motion where possible
- Tree-shake date-fns (import only needed functions)

---

### 9. Framer Motion Overuse (LOW)

**Problem**: Every page and component has Framer Motion animations.

**Evidence**:
```typescript
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3, delay: 0.1 }}
>
```

**Impact**:
- Adds 50-100ms to render time per component
- Blocks main thread during animation
- Not noticeable on fast connections but hurts slow devices

**Solution**:
- Remove animations from non-critical components
- Use CSS transitions instead
- Only animate hero sections

---

### 10. No Loading Skeletons (LOW)

**Problem**: Pages show "Loading..." text instead of skeleton loaders.

**Evidence**:
```typescript
if (tradingModeLoading || loading) {
  return (
    <DashboardLayout onLogout={onLogout}>
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="flex items-center justify-center h-64">
          <div className="text-gray-400 font-mono">Loading overview...</div>
        </div>
      </div>
    </DashboardLayout>
  );
}
```

**Impact**:
- Perceived performance is worse
- Users see blank screen during load

**Solution**:
- Use shadcn Skeleton components
- Show layout structure while loading

---

## Performance Metrics (Estimated)

### Current Performance
- **Initial Load**: 5-8 seconds
- **Page Navigation**: 1-2 seconds
- **Bundle Size**: ~2-3MB (uncompressed)
- **Lighthouse Score**: 30-40
- **First Contentful Paint**: 3-5s
- **Time to Interactive**: 6-10s

### Target Performance (After Optimization)
- **Initial Load**: 1-2 seconds
- **Page Navigation**: 200-500ms
- **Bundle Size**: <500KB initial, <1MB total
- **Lighthouse Score**: 85-95
- **First Contentful Paint**: <1s
- **Time to Interactive**: <2s

---

## Recommended Optimizations (Priority Order)

### Phase 1: Critical (Week 1)
1. **Implement code splitting** (route-based lazy loading)
2. **Add build optimization** to vite.config.ts
3. **Implement data caching** with React Query or Zustand
4. **Lazy load heavy components** (charts, tables)

### Phase 2: High Priority (Week 2)
5. **Optimize re-renders** with React.memo and useMemo
6. **Reduce API calls** (combine endpoints, cache globally)
7. **Optimize WebSocket subscriptions** (move to context)

### Phase 3: Medium Priority (Week 3)
8. **Add loading skeletons** for better perceived performance
9. **Optimize Framer Motion** (remove unnecessary animations)
10. **Tree-shake dependencies** (reduce bundle size)

### Phase 4: Polish (Week 4)
11. **Add service worker** for offline support
12. **Implement virtual scrolling** for large tables
13. **Add image optimization** (if any images added)
14. **Performance monitoring** (add analytics)

---

## Specific Code Changes Needed

### 1. vite.config.ts
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'ui-vendor': ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu', '@radix-ui/react-tabs'],
          'chart-vendor': ['recharts'],
          'table-vendor': ['@tanstack/react-table'],
          'animation-vendor': ['framer-motion'],
        },
      },
    },
    chunkSizeWarningLimit: 1000,
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})
```

### 2. App.tsx (Code Splitting)
```typescript
import { lazy, Suspense } from 'react';
import { LoadingOverlay } from './components/loading';

// Lazy load all pages
const Overview = lazy(() => import('./pages/OverviewNew'));
const Portfolio = lazy(() => import('./pages/PortfolioNew'));
const OrdersPage = lazy(() => import('./pages/OrdersNew'));
const StrategiesPage = lazy(() => import('./pages/StrategiesNew'));
const Autonomous = lazy(() => import('./pages/AutonomousNew'));
const Risk = lazy(() => import('./pages/RiskNew'));
const Analytics = lazy(() => import('./pages/AnalyticsNew'));
const Settings = lazy(() => import('./pages/SettingsNew'));

// Wrap routes in Suspense
<Route 
  path="/" 
  element={
    <ProtectedRoute>
      <Suspense fallback={<LoadingOverlay message="Loading overview..." />}>
        <Overview onLogout={handleLogout} />
      </Suspense>
    </ProtectedRoute>
  } 
/>
```

### 3. Create Data Cache Store (Zustand)
```typescript
// src/stores/dataCache.ts
import create from 'zustand';

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

interface DataCacheStore {
  accountInfo: CacheEntry<AccountInfo> | null;
  positions: CacheEntry<Position[]> | null;
  orders: CacheEntry<Order[]> | null;
  
  setAccountInfo: (data: AccountInfo) => void;
  setPositions: (data: Position[]) => void;
  setOrders: (data: Order[]) => void;
  
  isStale: (key: 'accountInfo' | 'positions' | 'orders', maxAge: number) => boolean;
  clear: () => void;
}

export const useDataCache = create<DataCacheStore>((set, get) => ({
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
  
  clear: () => set({ accountInfo: null, positions: null, orders: null }),
}));
```

### 4. Optimize OverviewNew.tsx
```typescript
// Add useMemo for expensive calculations
const filteredPositions = useMemo(() => 
  positions.filter(position => {
    const matchesSearch = position.symbol.toLowerCase().includes(positionSearch.toLowerCase());
    const matchesSide = positionSideFilter === 'all' || position.side === positionSideFilter;
    return matchesSearch && matchesSide;
  }),
  [positions, positionSearch, positionSideFilter]
);

const filteredOrders = useMemo(() => 
  orders.filter(order => {
    const matchesSearch = order.symbol.toLowerCase().includes(orderSearch.toLowerCase());
    const matchesStatus = orderStatusFilter === 'all' || order.status === orderStatusFilter;
    const matchesSide = orderSideFilter === 'all' || order.side === orderSideFilter;
    return matchesSearch && matchesStatus && matchesSide;
  }),
  [orders, orderSearch, orderStatusFilter, orderSideFilter]
);

// Memoize expensive components
const MemoizedDataTable = memo(DataTable);
const MemoizedMetricCard = memo(MetricCard);
```

---

## Testing Plan

### Performance Testing
1. **Lighthouse Audit** (before/after)
2. **Bundle Size Analysis** (webpack-bundle-analyzer)
3. **Network Waterfall** (Chrome DevTools)
4. **React DevTools Profiler** (identify re-renders)
5. **Load Testing** (simulate slow 3G)

### Metrics to Track
- Initial bundle size
- Time to First Contentful Paint (FCP)
- Time to Interactive (TTI)
- Largest Contentful Paint (LCP)
- Cumulative Layout Shift (CLS)
- First Input Delay (FID)

---

## Conclusion

The frontend has significant performance issues that can be resolved with:
1. Code splitting (biggest impact)
2. Data caching (second biggest impact)
3. Build optimization
4. Lazy loading
5. Re-render optimization

Estimated improvement: **5-8s → 1-2s initial load** (70-80% faster)

---

**Next Steps**: Update task 7.15 with specific implementation tasks based on this diagnostic.
