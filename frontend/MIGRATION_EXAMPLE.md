# Design System Migration Example

This document shows how to migrate existing components to use the new design system.

## Before: Manual Styling

```tsx
// Old approach - hardcoded classes and inconsistent styling
<button
  onClick={handleClick}
  disabled={loading}
  className="px-4 py-3 rounded-lg text-sm font-mono bg-accent-green/10 text-accent-green border border-accent-green/30 hover:bg-accent-green/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
>
  {loading ? 'Loading...' : 'Submit'}
</button>
```

## After: Design System Components

```tsx
// New approach - using standardized Button component
import { Button } from '@/components/ui';

<Button
  variant="primary"
  size="md"
  onClick={handleClick}
  loading={loading}
>
  Submit
</Button>
```

## Benefits of Migration

### 1. Reduced Code
- 3 lines instead of 8 lines
- No need to remember all the Tailwind classes
- Cleaner, more readable code

### 2. Consistency
- All buttons look and behave the same
- Automatic hover, focus, and disabled states
- Consistent spacing and sizing

### 3. Maintainability
- Change button styles in one place
- Easy to add new variants
- Type-safe props with TypeScript

### 4. Accessibility
- Built-in focus indicators
- Proper disabled state handling
- Loading state with visual feedback

## More Examples

### Cards

**Before:**
```tsx
<div className="bg-dark-surface border border-dark-border rounded-lg p-6">
  <h2 className="text-lg font-semibold text-gray-200 mb-4 font-mono">
    Title
  </h2>
  <div className="bg-dark-bg rounded-lg p-4 border border-dark-border hover:border-gray-600 transition-colors">
    Content
  </div>
</div>
```

**After:**
```tsx
import { Card, CardInner } from '@/components/ui';

<Card>
  <h2 className="text-lg font-semibold mb-4">Title</h2>
  <CardInner>Content</CardInner>
</Card>
```

### Badges

**Before:**
```tsx
<span className="inline-block px-2 py-1 rounded text-xs font-mono font-semibold border bg-accent-green/20 text-accent-green border-accent-green/30">
  ACTIVE
</span>
```

**After:**
```tsx
import { Badge } from '@/components/ui';

<Badge variant="success">ACTIVE</Badge>
```

### Form Inputs

**Before:**
```tsx
<div className="w-full">
  <label className="block mb-1 text-sm font-medium text-gray-400">
    Username
  </label>
  <input
    type="text"
    className="w-full px-3 py-2 text-sm font-mono text-gray-100 bg-dark-bg border border-dark-border rounded-md transition-all hover:border-gray-600 focus:outline-none focus:border-accent-blue focus:ring-2 focus:ring-accent-blue/20"
    placeholder="Enter username..."
  />
  <p className="mt-1 text-xs text-gray-500">Choose a unique username</p>
</div>
```

**After:**
```tsx
import { Input } from '@/components/ui';

<Input
  label="Username"
  placeholder="Enter username..."
  helperText="Choose a unique username"
/>
```

## Migration Checklist

When migrating a component:

- [ ] Replace custom buttons with `<Button>` component
- [ ] Replace div containers with `<Card>` and `<CardInner>`
- [ ] Replace status indicators with `<Badge>` component
- [ ] Replace form inputs with `<Input>` or `<TextArea>`
- [ ] Replace tables with `<Table>` components
- [ ] Use CSS variables instead of hardcoded colors
- [ ] Use spacing scale classes (p-md, mb-lg, etc.)
- [ ] Test keyboard navigation and focus states
- [ ] Verify hover and active states work correctly
- [ ] Check responsive behavior on different screen sizes

## Gradual Migration Strategy

1. **Phase 1**: Use new components for all new features
2. **Phase 2**: Migrate high-traffic pages (Dashboard, Portfolio)
3. **Phase 3**: Migrate remaining pages during maintenance
4. **Phase 4**: Remove old custom styles and consolidate

## Testing After Migration

After migrating a component, verify:

1. **Visual Appearance**: Component looks correct in all states
2. **Interactions**: Hover, focus, and active states work
3. **Keyboard Navigation**: Tab order and focus indicators
4. **Responsive Design**: Works on different screen sizes
5. **Accessibility**: Screen reader compatibility
6. **Performance**: No performance regressions

## Common Patterns

### Button Groups
```tsx
<div className="flex gap-3">
  <Button variant="primary">Save</Button>
  <Button variant="secondary">Cancel</Button>
</div>
```

### Status Display
```tsx
<div className="flex items-center gap-2">
  <span className="text-sm text-gray-400">Status:</span>
  <Badge variant="success">ACTIVE</Badge>
</div>
```

### Form Layout
```tsx
<Card>
  <h2 className="text-xl font-semibold mb-4">Settings</h2>
  <div className="space-y-4">
    <Input label="API Key" type="password" />
    <Input label="Secret" type="password" />
    <Button variant="primary" fullWidth>Save</Button>
  </div>
</Card>
```

### Data Table
```tsx
<Card>
  <h2 className="text-lg font-semibold mb-4">Positions</h2>
  <Table>
    <TableHeader>
      <TableRow>
        <TableHead>Symbol</TableHead>
        <TableHead>Quantity</TableHead>
        <TableHead>P&L</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {positions.map(position => (
        <TableRow key={position.id}>
          <TableCell>{position.symbol}</TableCell>
          <TableCell className="font-mono">{position.quantity}</TableCell>
          <TableCell className={position.pnl >= 0 ? 'text-positive' : 'text-negative'}>
            {formatCurrency(position.pnl)}
          </TableCell>
        </TableRow>
      ))}
    </TableBody>
  </Table>
</Card>
```
