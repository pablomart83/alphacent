# AlphaCent Design System

## Overview

This design system provides a consistent visual language across the AlphaCent trading platform. It includes standardized colors, typography, spacing, components, and interaction patterns.

## Color Palette

### Background Colors
- `--color-dark-bg` (#0a0e1a): Main background
- `--color-dark-surface` (#131824): Card/panel backgrounds
- `--color-dark-border` (#1f2937): Border color
- `--color-dark-hover` (#1e293b): Hover state background

### Accent Colors
- **Green** (Success/Positive): `--color-accent-green` (#10b981)
- **Red** (Danger/Negative): `--color-accent-red` (#ef4444)
- **Yellow** (Warning): `--color-accent-yellow` (#f59e0b)
- **Blue** (Info): `--color-accent-blue` (#3b82f6)

### Text Colors
- `--color-text-primary` (#f3f4f6): Primary text
- `--color-text-secondary` (#9ca3af): Secondary text
- `--color-text-tertiary` (#6b7280): Tertiary text
- `--color-text-disabled` (#4b5563): Disabled text

## Typography

### Font Family
- Monospace: `'JetBrains Mono', 'Courier New', monospace`

### Font Sizes
- `xs`: 0.75rem (12px)
- `sm`: 0.875rem (14px)
- `base`: 1rem (16px)
- `lg`: 1.125rem (18px)
- `xl`: 1.25rem (20px)
- `2xl`: 1.5rem (24px)
- `3xl`: 1.875rem (30px)

### Hierarchy
- **H1**: 1.875rem, font-weight 700
- **H2**: 1.5rem, font-weight 600
- **H3**: 1.25rem, font-weight 600
- **H4**: 1.125rem, font-weight 600

## Spacing

- `xs`: 0.25rem (4px)
- `sm`: 0.5rem (8px)
- `md`: 1rem (16px)
- `lg`: 1.5rem (24px)
- `xl`: 2rem (32px)
- `2xl`: 3rem (48px)

## Border Radius

- `sm`: 0.375rem (6px)
- `md`: 0.5rem (8px)
- `lg`: 0.75rem (12px)
- `xl`: 1rem (16px)

## Components

### Buttons

#### Variants
- **Primary**: Green accent, for main actions
- **Secondary**: Neutral, for secondary actions
- **Danger**: Red accent, for destructive actions
- **Warning**: Yellow accent, for caution actions

#### Sizes
- **Small**: `btn-sm` - Compact buttons
- **Default**: `btn` - Standard size
- **Large**: `btn-lg` - Prominent buttons

#### Usage
```tsx
<button className="btn btn-primary">Primary Action</button>
<button className="btn btn-secondary">Secondary Action</button>
<button className="btn btn-danger">Delete</button>
<button className="btn btn-warning">Pause</button>
```

#### States
- **Hover**: Slightly darker background
- **Active**: Even darker background
- **Disabled**: 50% opacity, no pointer events
- **Focus**: Blue outline for keyboard navigation

### Cards/Panels

#### Variants
- **Card**: Main container with padding
- **Card Compact**: Reduced padding
- **Card Inner**: Nested card within a card

#### Usage
```tsx
<div className="card">
  <h2>Card Title</h2>
  <div className="card-inner">
    Nested content
  </div>
</div>
```

### Badges

#### Variants
- **Success**: Green (active, positive states)
- **Danger**: Red (error, negative states)
- **Warning**: Yellow (caution states)
- **Info**: Blue (informational states)
- **Neutral**: Gray (neutral states)

#### Usage
```tsx
<span className="badge badge-success">ACTIVE</span>
<span className="badge badge-danger">ERROR</span>
<span className="badge badge-warning">PAUSED</span>
```

### Tables

#### Features
- Hover effect on rows
- Consistent spacing
- Uppercase column headers
- Alternating row backgrounds (via hover)

#### Usage
```tsx
<table className="table">
  <thead>
    <tr>
      <th>Column 1</th>
      <th>Column 2</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Data 1</td>
      <td>Data 2</td>
    </tr>
  </tbody>
</table>
```

### Inputs

#### Features
- Consistent border and padding
- Hover and focus states
- Disabled state styling
- Placeholder text styling

#### Usage
```tsx
<label className="label">Label Text</label>
<input type="text" className="input" placeholder="Enter value..." />
```

## Transitions

### Durations
- **Fast**: 150ms - Quick interactions (hover, active)
- **Base**: 200ms - Standard transitions
- **Slow**: 300ms - Complex animations

### Easing
- Default: `cubic-bezier(0.4, 0, 0.2, 1)`

## Animations

### Available Animations
- `animate-slide-in-right`: Slide in from right
- `animate-fade-in`: Fade in
- `animate-slide-up`: Slide up with fade
- `animate-pulse`: Pulsing effect

### Usage
```tsx
<div className="animate-fade-in">Content</div>
```

## Accessibility

### Focus States
- All interactive elements have visible focus indicators
- Focus outline: 2px solid blue with 2px offset
- Keyboard navigation fully supported

### Color Contrast
- All text meets WCAG AA standards
- Primary text: #f3f4f6 on #0a0e1a (contrast ratio > 7:1)
- Secondary text: #9ca3af on #0a0e1a (contrast ratio > 4.5:1)

### Interactive Elements
- Minimum touch target size: 44x44px
- Clear hover and active states
- Disabled states clearly indicated

## Best Practices

### Consistency
- Use design tokens (CSS variables) instead of hardcoded values
- Apply consistent spacing using the spacing scale
- Use semantic color names (success, danger, warning, info)

### Performance
- Use CSS transitions instead of JavaScript animations
- Leverage hardware acceleration with transform and opacity
- Minimize repaints and reflows

### Maintainability
- Use utility classes from the design system
- Extend existing components rather than creating new ones
- Document any custom styles or deviations

## Examples

### Card with Button
```tsx
<div className="card">
  <h2 className="text-xl font-semibold mb-4">Card Title</h2>
  <p className="text-gray-400 mb-4">Card description text</p>
  <button className="btn btn-primary">Take Action</button>
</div>
```

### Status Badge
```tsx
<div className="flex items-center gap-2">
  <span className="text-sm">Status:</span>
  <span className="badge badge-success">ACTIVE</span>
</div>
```

### Data Table
```tsx
<div className="card">
  <h2 className="text-lg font-semibold mb-4">Data Table</h2>
  <table className="table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Value</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Item 1</td>
        <td className="font-mono">$1,234.56</td>
        <td><span className="badge badge-success">Active</span></td>
      </tr>
    </tbody>
  </table>
</div>
```
