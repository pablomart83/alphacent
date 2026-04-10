# Visual Polish Quick Start Guide

## 🚀 Quick Reference for Common Tasks

### 1. Add Animated Numbers

**Before:**
```tsx
<span className="text-2xl font-bold">
  {formatCurrency(value)}
</span>
```

**After:**
```tsx
import { AnimatedNumber } from '@/components/ui/animated-number';

<span className="text-2xl font-bold">
  <AnimatedNumber value={value} format="currency" decimals={2} />
</span>
```

### 2. Add Loading State

**Before:**
```tsx
{loading && <div>Loading...</div>}
```

**After:**
```tsx
import { DashboardSkeleton } from '@/components/ui/loading-skeletons';

{loading && <DashboardSkeleton />}
```

### 3. Add Error State

**Before:**
```tsx
{error && <div className="text-red-500">{error}</div>}
```

**After:**
```tsx
import { ErrorState } from '@/components/ui/error-state';

{error && (
  <ErrorState
    message={error}
    onRetry={fetchData}
  />
)}
```

### 4. Add Page Transition

**Before:**
```tsx
<div className="p-8">
  {/* content */}
</div>
```

**After:**
```tsx
import { PageTransition } from '@/components/ui/page-transition';

<PageTransition>
  <div className="p-8">
    {/* content */}
  </div>
</PageTransition>
```

### 5. Add Card Animation

**Before:**
```tsx
<Card>
  {/* content */}
</Card>
```

**After:**
```tsx
import { CardEntrance } from '@/components/ui/page-transition';

<CardEntrance delay={0.1}>
  <Card>
    {/* content */}
  </Card>
</CardEntrance>
```

### 6. Add Hover Effect

**Before:**
```tsx
<Card className="cursor-pointer" onClick={handleClick}>
  {/* content */}
</Card>
```

**After:**
```tsx
import { HoverLift } from '@/components/ui/micro-interactions';

<HoverLift>
  <Card className="cursor-pointer" onClick={handleClick}>
    {/* content */}
  </Card>
</HoverLift>
```

### 7. Add Flash on Update

**Before:**
```tsx
<div>
  {formatCurrency(position.unrealized_pnl)}
</div>
```

**After:**
```tsx
import { FlashWrapper } from '@/components/ui/flash-wrapper';
import { AnimatedNumber } from '@/components/ui/animated-number';

<FlashWrapper value={position.unrealized_pnl} flashColor="green">
  <AnimatedNumber value={position.unrealized_pnl} format="currency" />
</FlashWrapper>
```

### 8. Add Empty State

**Before:**
```tsx
{data.length === 0 && <div>No data</div>}
```

**After:**
```tsx
import { EmptyState } from '@/components/ui/error-state';
import { BarChart3 } from 'lucide-react';

{data.length === 0 && (
  <EmptyState
    title="No Positions"
    message="You don't have any open positions yet."
    icon={BarChart3}
  />
)}
```

### 9. Use Consistent Styling

**Before:**
```tsx
<h1 className="text-3xl font-bold text-gray-100">
  Page Title
</h1>
```

**After:**
```tsx
import { typography } from '@/lib/visual-polish';

<h1 className={typography.pageTitle}>
  Page Title
</h1>
```

### 10. Add Staggered List Animation

**Before:**
```tsx
<div className="space-y-4">
  {items.map(item => (
    <Card key={item.id}>{item.name}</Card>
  ))}
</div>
```

**After:**
```tsx
import { StaggerChildren, StaggerItem } from '@/components/ui/page-transition';

<StaggerChildren className="space-y-4">
  {items.map(item => (
    <StaggerItem key={item.id}>
      <Card>{item.name}</Card>
    </StaggerItem>
  ))}
</StaggerChildren>
```

## 📋 Complete Page Template

```tsx
import { useState, useEffect } from 'react';
import { PageTransition } from '@/components/ui/page-transition';
import { DashboardSkeleton } from '@/components/ui/loading-skeletons';
import { ErrorState } from '@/components/ui/error-state';
import { CardEntrance } from '@/components/ui/page-transition';
import { AnimatedNumber } from '@/components/ui/animated-number';
import { MetricCard } from '@/components/trading/MetricCard';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { RefreshCw } from 'lucide-react';
import { spacing, typography } from '@/lib/visual-polish';

export function MyPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<any>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      // Fetch data...
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Loading state
  if (loading) return <DashboardSkeleton />;
  
  // Error state
  if (error) return <ErrorState message={error} onRetry={fetchData} />;

  // Main content
  return (
    <PageTransition>
      <div className={spacing.page}>
        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className={typography.pageTitle}>
              ◆ Page Title
            </h1>
            <p className={typography.pageSubtitle}>
              Page description
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={fetchData}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>

        {/* Metrics */}
        <CardEntrance delay={0.1}>
          <div className="grid grid-cols-4 gap-4 mb-6">
            <MetricCard
              label="Total Value"
              value={data.total}
              format="currency"
              icon={DollarSign}
            />
            {/* More metrics... */}
          </div>
        </CardEntrance>

        {/* Main Content */}
        <CardEntrance delay={0.2}>
          <Card>
            <CardHeader>
              <CardTitle>Data Table</CardTitle>
            </CardHeader>
            <CardContent>
              {/* Content... */}
            </CardContent>
          </Card>
        </CardEntrance>
      </div>
    </PageTransition>
  );
}
```

## 🎨 Styling Utilities Cheat Sheet

### Typography
```tsx
import { typography } from '@/lib/visual-polish';

typography.pageTitle        // Page titles
typography.pageSubtitle     // Page subtitles
typography.sectionTitle     // Section titles
typography.cardTitle        // Card titles
typography.body             // Body text
typography.mono             // Monospace
typography.monoLarge        // Large monospace numbers
```

### Spacing
```tsx
import { spacing } from '@/lib/visual-polish';

spacing.page                // Page padding
spacing.pageMaxWidth        // Max width container
spacing.sectionGap          // Section spacing
spacing.gridGap             // Grid gap
```

### Trading Colors
```tsx
import { tradingColors } from '@/lib/visual-polish';

tradingColors.positive      // Green text
tradingColors.negative      // Red text
tradingColors.positiveBg    // Green background
tradingColors.negativeBg    // Red background
tradingColors.buy           // Buy color
tradingColors.sell          // Sell color
```

### Badges
```tsx
import { badgeStyles } from '@/lib/visual-polish';

badgeStyles.active          // Active badge
badgeStyles.inactive        // Inactive badge
badgeStyles.pending         // Pending badge
badgeStyles.buy             // Buy badge
badgeStyles.sell            // Sell badge
badgeStyles.filled          // Filled order badge
```

## 🔧 Common Patterns

### Pattern 1: Metric Card with Animation
```tsx
<MetricCard
  label="Total P&L"
  value={totalPnL}
  format="currency"
  change={pnlChange}
  trend={totalPnL >= 0 ? 'up' : 'down'}
  icon={TrendingUp}
  tooltip="Total profit and loss from all positions"
/>
```

### Pattern 2: Real-Time Value Display
```tsx
<FlashWrapper value={value} flashColor={value >= 0 ? 'green' : 'red'}>
  <span className={cn(
    typography.monoLarge,
    value >= 0 ? tradingColors.positive : tradingColors.negative
  )}>
    <AnimatedNumber value={value} format="currency" />
  </span>
</FlashWrapper>
```

### Pattern 3: Interactive Card
```tsx
<HoverLift>
  <Card className="cursor-pointer" onClick={handleClick}>
    <CardHeader>
      <CardTitle>Strategy Name</CardTitle>
    </CardHeader>
    <CardContent>
      <AnimatedNumber value={performance} format="percentage" />
    </CardContent>
  </Card>
</HoverLift>
```

### Pattern 4: Status Badge
```tsx
<span className={cn(
  'px-2 py-0.5 rounded text-xs font-mono font-semibold',
  status === 'ACTIVE' ? badgeStyles.active : badgeStyles.inactive
)}>
  {status}
</span>
```

### Pattern 5: Loading Table
```tsx
{loading ? (
  <TableSkeleton rows={10} />
) : data.length > 0 ? (
  <DataTable data={data} columns={columns} />
) : (
  <EmptyState
    title="No Data"
    message="No records found."
  />
)}
```

## 📱 Responsive Utilities

```tsx
import { layoutUtils } from '@/lib/visual-polish';

// Responsive grids
layoutUtils.gridCols2       // 1 col mobile, 2 col desktop
layoutUtils.gridCols3       // 1 col mobile, 3 col desktop
layoutUtils.gridCols4       // 1 col mobile, 2 col tablet, 4 col desktop

// Flex utilities
layoutUtils.flexBetween     // Space between
layoutUtils.flexCenter      // Center items
layoutUtils.flexStart       // Start alignment

// Visibility
layoutUtils.hideOnMobile    // Hide on mobile
layoutUtils.showOnMobile    // Show only on mobile
```

## 🎯 Best Practices

1. **Always provide loading states** - Use skeleton components
2. **Always provide error states** - Use ErrorState with retry
3. **Use animated numbers for metrics** - Smooth value transitions
4. **Add micro-interactions to clickable elements** - Better UX
5. **Use consistent styling utilities** - Maintain design system
6. **Wrap real-time values with FlashWrapper** - Visual feedback
7. **Add page transitions** - Smooth navigation
8. **Use staggered animations for lists** - Professional feel
9. **Respect accessibility** - All animations respect prefers-reduced-motion
10. **Test performance** - Ensure 60 FPS

## 🐛 Troubleshooting

### Animation not working?
- Check Framer Motion is installed
- Verify imports are correct
- Ensure parent has proper layout

### Number not animating?
- Verify value is a number, not string
- Check that value is actually changing
- Ensure AnimatedNumber is receiving new value

### Flash not triggering?
- Verify value is primitive (not object)
- Check that value is actually changing
- Ensure FlashWrapper has proper key if in list

### Performance issues?
- Use React.memo for animated components
- Reduce simultaneous animations
- Check for memory leaks in useEffect

## 📚 Full Documentation

See `ANIMATION_AND_VISUAL_POLISH.md` for complete documentation.
