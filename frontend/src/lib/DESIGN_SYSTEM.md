# AlphaCent Design System

## Overview

This design system provides a comprehensive set of components, utilities, and patterns for building the AlphaCent trading platform. It's built on top of shadcn/ui, Radix UI primitives, Tailwind CSS, and Framer Motion for animations.

## Technology Stack

### Core Libraries
- **React 19.2.0** - UI framework
- **TypeScript 5.9.3** - Type safety
- **Tailwind CSS 4.1.18** - Utility-first CSS
- **Framer Motion** - Animations and transitions

### UI Components
- **shadcn/ui** - Component library
- **Radix UI** - Accessible primitives
- **Lucide React** - Icon library

### Data & State
- **TanStack Table** - Advanced data tables
- **React Hook Form** - Form management
- **Zustand** - State management
- **date-fns** - Date utilities

### Utilities
- **clsx** - Conditional classes
- **tailwind-merge** - Merge Tailwind classes
- **Sonner** - Toast notifications

## Color Palette

### Theme Colors (shadcn/ui)
```css
--background: 222.2 84% 4.9%      /* Dark background */
--foreground: 210 40% 98%         /* Light text */
--primary: 142.1 76.2% 36.3%      /* Green (success) */
--destructive: 0 62.8% 30.6%      /* Red (danger) */
--muted: 217.2 32.6% 17.5%        /* Muted background */
--accent: 217.2 32.6% 17.5%       /* Accent background */
```

### Trading Colors (Legacy - Keep for compatibility)
```javascript
'accent-green': '#10b981'         // Positive P&L, buy orders
'accent-red': '#ef4444'           // Negative P&L, sell orders
'accent-yellow': '#f59e0b'        // Warnings, pending
'accent-blue': '#3b82f6'          // Info, neutral
```

## Typography

### Font Families
- **Default**: System font stack
- **Monospace**: 'JetBrains Mono', 'Courier New', monospace (for numbers, code)

### Font Sizes
```javascript
xs: '0.75rem'    // 12px - Small labels
sm: '0.875rem'   // 14px - Body text
base: '1rem'     // 16px - Default
lg: '1.125rem'   // 18px - Large text
xl: '1.25rem'    // 20px - Headings
2xl: '1.5rem'    // 24px - Large headings
3xl: '1.875rem'  // 30px - Page titles
```

## Components

### UI Components (shadcn/ui)

#### Button
```tsx
import { Button } from '@/components/ui/button';

<Button variant="default">Primary</Button>
<Button variant="destructive">Delete</Button>
<Button variant="outline">Cancel</Button>
<Button variant="ghost">Link</Button>
<Button size="sm">Small</Button>
<Button size="lg">Large</Button>
```

#### Dialog
```tsx
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';

<Dialog>
  <DialogTrigger asChild>
    <Button>Open</Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Confirm Action</DialogTitle>
      <DialogDescription>
        Are you sure you want to proceed?
      </DialogDescription>
    </DialogHeader>
  </DialogContent>
</Dialog>
```

#### Dropdown Menu
```tsx
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

<DropdownMenu>
  <DropdownMenuTrigger asChild>
    <Button variant="ghost">Actions</Button>
  </DropdownMenuTrigger>
  <DropdownMenuContent>
    <DropdownMenuItem>Edit</DropdownMenuItem>
    <DropdownMenuItem>Delete</DropdownMenuItem>
  </DropdownMenuContent>
</DropdownMenu>
```

#### Tooltip
```tsx
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

<TooltipProvider>
  <Tooltip>
    <TooltipTrigger>Hover me</TooltipTrigger>
    <TooltipContent>
      <p>Helpful information</p>
    </TooltipContent>
  </Tooltip>
</TooltipProvider>
```

#### Tabs
```tsx
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

<Tabs defaultValue="overview">
  <TabsList>
    <TabsTrigger value="overview">Overview</TabsTrigger>
    <TabsTrigger value="details">Details</TabsTrigger>
  </TabsList>
  <TabsContent value="overview">Overview content</TabsContent>
  <TabsContent value="details">Details content</TabsContent>
</Tabs>
```

#### Select
```tsx
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

<Select>
  <SelectTrigger>
    <SelectValue placeholder="Select option" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="1">Option 1</SelectItem>
    <SelectItem value="2">Option 2</SelectItem>
  </SelectContent>
</Select>
```

#### Badge
```tsx
import { Badge } from '@/components/ui/badge';

<Badge variant="success">Active</Badge>
<Badge variant="danger">Error</Badge>
<Badge variant="warning">Pending</Badge>
<Badge variant="info">Info</Badge>
```

#### Card
```tsx
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

<Card>
  <CardHeader>
    <CardTitle>Card Title</CardTitle>
    <CardDescription>Card description</CardDescription>
  </CardHeader>
  <CardContent>
    Card content goes here
  </CardContent>
</Card>
```

### Trading Components

#### MetricCard
```tsx
import { MetricCard } from '@/components/trading/MetricCard';
import { TrendingUp } from 'lucide-react';

<MetricCard
  label="Total P&L"
  value={12345.67}
  format="currency"
  change={5.2}
  trend="up"
  icon={TrendingUp}
  tooltip="Total profit and loss for all positions"
/>
```

#### DataTable
```tsx
import { DataTable } from '@/components/trading/DataTable';
import { ColumnDef } from '@tanstack/react-table';

const columns: ColumnDef<Order>[] = [
  {
    accessorKey: 'symbol',
    header: 'Symbol',
  },
  {
    accessorKey: 'side',
    header: 'Side',
    cell: ({ row }) => (
      <Badge variant={row.original.side === 'BUY' ? 'success' : 'danger'}>
        {row.original.side}
      </Badge>
    ),
  },
];

<DataTable columns={columns} data={orders} pageSize={20} />
```

## Utility Functions

### cn() - Class Name Merger
```tsx
import { cn } from '@/lib/utils';

<div className={cn(
  'base-class',
  isActive && 'active-class',
  'override-class'
)} />
```

### Formatters
```tsx
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
  formatCompactNumber,
} from '@/lib/utils';

formatCurrency(12345.67)        // "$12,345.67"
formatPercentage(5.234)         // "+5.23%"
formatNumber(1234567.89)        // "1,234,567.89"
formatCompactNumber(1234567)    // "1.2M"
```

### Date Utilities
```tsx
import {
  formatDate,
  formatDateTime,
  formatRelativeTime,
  formatSmartDate,
} from '@/lib/date-utils';

formatDate(new Date())                    // "Jan 15, 2024"
formatDateTime(new Date())                // "Jan 15, 2024 14:30:00"
formatRelativeTime(new Date())            // "2 hours ago"
formatSmartDate(new Date())               // "Today at 14:30"
```

### Color Utilities
```tsx
import { getValueColor, getValueBgColor } from '@/lib/utils';

<span className={getValueColor(pnl)}>
  {formatCurrency(pnl)}
</span>
```

## State Management (Zustand)

### Trading Store
```tsx
import { useTradingStore } from '@/lib/stores/trading-store';

function Component() {
  const mode = useTradingStore((state) => state.mode);
  const setMode = useTradingStore((state) => state.setMode);
  const positions = useTradingStore((state) => state.positions);
  
  return (
    <Button onClick={() => setMode('LIVE')}>
      Switch to {mode === 'DEMO' ? 'LIVE' : 'DEMO'}
    </Button>
  );
}
```

### Notification Store
```tsx
import { useNotificationStore } from '@/lib/stores/notification-store';

function Component() {
  const addNotification = useNotificationStore((state) => state.addNotification);
  
  const handleSuccess = () => {
    addNotification({
      type: 'success',
      title: 'Order Placed',
      message: 'Your order has been placed successfully',
    });
  };
}
```

## Animations (Framer Motion)

### Fade In
```tsx
import { motion } from 'framer-motion';

<motion.div
  initial={{ opacity: 0 }}
  animate={{ opacity: 1 }}
  transition={{ duration: 0.3 }}
>
  Content
</motion.div>
```

### Slide Up
```tsx
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3 }}
>
  Content
</motion.div>
```

### Scale Animation
```tsx
<motion.div
  whileHover={{ scale: 1.05 }}
  whileTap={{ scale: 0.95 }}
>
  Interactive Element
</motion.div>
```

### Number Counter
```tsx
import { motion, useSpring, useTransform } from 'framer-motion';

function AnimatedNumber({ value }: { value: number }) {
  const spring = useSpring(value, { stiffness: 100, damping: 30 });
  const display = useTransform(spring, (current) =>
    Math.round(current).toLocaleString()
  );
  
  return <motion.span>{display}</motion.span>;
}
```

## Icons (Lucide React)

### Common Trading Icons
```tsx
import {
  TrendingUp,
  TrendingDown,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  BarChart3,
  PieChart,
  Settings,
  User,
  LogOut,
} from 'lucide-react';

<TrendingUp className="h-4 w-4 text-accent-green" />
<AlertTriangle className="h-5 w-5 text-accent-yellow" />
```

## Responsive Design

### Breakpoints
```javascript
sm: '640px'   // Mobile landscape
md: '768px'   // Tablet
lg: '1024px'  // Desktop
xl: '1280px'  // Large desktop
2xl: '1536px' // Extra large
```

### Usage
```tsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
  {/* Responsive grid */}
</div>
```

## Accessibility

### Keyboard Navigation
- All interactive elements support keyboard navigation
- Focus indicators are visible
- Tab order is logical

### Screen Readers
- ARIA labels are provided
- Semantic HTML is used
- Alt text for images

### Color Contrast
- All text meets WCAG AA standards
- Color is not the only indicator of state

## Best Practices

### Component Structure
```tsx
// Good: Composable, reusable
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardContent>
    Content
  </CardContent>
</Card>

// Bad: Monolithic, hard to customize
<CustomCard title="Title" content="Content" />
```

### Styling
```tsx
// Good: Use cn() for conditional classes
<div className={cn(
  'base-class',
  isActive && 'active-class'
)} />

// Bad: String concatenation
<div className={`base-class ${isActive ? 'active-class' : ''}`} />
```

### Performance
```tsx
// Good: Memoize expensive computations
const formattedValue = React.useMemo(
  () => formatCurrency(value),
  [value]
);

// Good: Use React.memo for expensive components
export const ExpensiveComponent = React.memo(({ data }) => {
  // ...
});
```

## Examples

See the `/examples` directory for complete component examples:
- `DesignSystemExample.tsx` - All UI components
- `LoadingErrorStatesExample.tsx` - Loading and error states
- `WebSocketAutonomousExample.tsx` - Real-time updates

## Migration Guide

### From Legacy Components

#### Button
```tsx
// Old
<button className="btn btn-primary">Click</button>

// New
<Button variant="default">Click</Button>
```

#### Card
```tsx
// Old
<div className="card">
  <div className="card-header">Title</div>
  <div className="card-body">Content</div>
</div>

// New
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
  </CardHeader>
  <CardContent>Content</CardContent>
</Card>
```

## Resources

- [shadcn/ui Documentation](https://ui.shadcn.com)
- [Radix UI Documentation](https://www.radix-ui.com)
- [Tailwind CSS Documentation](https://tailwindcss.com)
- [Framer Motion Documentation](https://www.framer.com/motion)
- [TanStack Table Documentation](https://tanstack.com/table)
- [Lucide Icons](https://lucide.dev)
