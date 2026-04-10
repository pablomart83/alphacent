# UI Components Library

This directory contains reusable UI components that implement the AlphaCent design system. All components follow consistent styling, accessibility standards, and interaction patterns.

## Available Components

### Button
Standardized button component with multiple variants and sizes.

```tsx
import { Button } from '@/components/ui';

<Button variant="primary" size="md" onClick={handleClick}>
  Click Me
</Button>
```

**Props:**
- `variant`: 'primary' | 'secondary' | 'danger' | 'warning' (default: 'primary')
- `size`: 'sm' | 'md' | 'lg' (default: 'md')
- `loading`: boolean (default: false)
- `fullWidth`: boolean (default: false)
- All standard button HTML attributes

### Card
Container component for grouping related content.

```tsx
import { Card, CardInner } from '@/components/ui';

<Card>
  <h2>Card Title</h2>
  <CardInner>
    Nested content with darker background
  </CardInner>
</Card>
```

**Props:**
- `compact`: boolean - Reduces padding (default: false)
- `hover`: boolean - Enables hover effect (default: true)
- `className`: string - Additional CSS classes

### Badge
Small status indicator component.

```tsx
import { Badge } from '@/components/ui';

<Badge variant="success">ACTIVE</Badge>
```

**Props:**
- `variant`: 'success' | 'danger' | 'warning' | 'info' | 'neutral' (default: 'neutral')
- `className`: string - Additional CSS classes

### Input
Form input component with label and error support.

```tsx
import { Input, TextArea } from '@/components/ui';

<Input
  label="Username"
  placeholder="Enter username..."
  error="This field is required"
  helperText="Choose a unique username"
/>

<TextArea
  label="Description"
  rows={4}
  placeholder="Enter description..."
/>
```

**Props:**
- `label`: string - Input label
- `error`: string - Error message
- `helperText`: string - Helper text below input
- All standard input HTML attributes

### Table
Structured table component with consistent styling.

```tsx
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui';

<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Name</TableHead>
      <TableHead>Value</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    <TableRow>
      <TableCell>Item 1</TableCell>
      <TableCell>$100</TableCell>
    </TableRow>
  </TableBody>
</Table>
```

## Design Tokens

All components use CSS variables defined in `src/index.css`:

### Colors
- `--color-dark-bg`: Main background
- `--color-dark-surface`: Card backgrounds
- `--color-dark-border`: Border color
- `--color-accent-green`: Success/positive
- `--color-accent-red`: Danger/negative
- `--color-accent-yellow`: Warning
- `--color-accent-blue`: Info

### Spacing
- `--spacing-xs`: 0.25rem (4px)
- `--spacing-sm`: 0.5rem (8px)
- `--spacing-md`: 1rem (16px)
- `--spacing-lg`: 1.5rem (24px)
- `--spacing-xl`: 2rem (32px)

### Typography
- `--font-family-mono`: JetBrains Mono
- Font sizes: xs (12px), sm (14px), base (16px), lg (18px), xl (20px), 2xl (24px), 3xl (30px)

## Accessibility

All components follow accessibility best practices:

- **Keyboard Navigation**: All interactive elements are keyboard accessible
- **Focus Indicators**: Visible focus states for keyboard navigation
- **ARIA Labels**: Proper labeling for screen readers
- **Color Contrast**: WCAG AA compliant color combinations
- **Touch Targets**: Minimum 44x44px for interactive elements

## Usage Guidelines

### Consistency
- Always use these components instead of creating custom ones
- Use design tokens (CSS variables) for colors and spacing
- Follow the established patterns for hover, focus, and active states

### Customization
- Use the `className` prop to add additional styles
- Extend components when you need custom behavior
- Document any deviations from the standard patterns

### Performance
- Components use CSS transitions for smooth animations
- Minimal re-renders through proper React patterns
- Optimized for production builds

## Examples

See `src/examples/DesignSystemExample.tsx` for comprehensive usage examples of all components.

## Contributing

When adding new components:

1. Follow the existing patterns and naming conventions
2. Use TypeScript for type safety
3. Include proper accessibility attributes
4. Add documentation and examples
5. Test keyboard navigation and screen reader compatibility
