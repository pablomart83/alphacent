/**
 * Design Tokens for AlphaCent Trading Platform
 *
 * Centralized design constants usable in both TypeScript (Recharts configs)
 * and as references for Tailwind utility classes.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
 */

// ---------------------------------------------------------------------------
// Colors — semantic palette (Req 4.2)
// ---------------------------------------------------------------------------

export const colors = {
  /** Positive values / profit */
  green: '#22c55e',
  /** Negative values / loss */
  red: '#ef4444',
  /** Neutral / informational */
  blue: '#3b82f6',
  /** Warnings */
  yellow: '#eab308',
} as const;

/**
 * Convenience helper – returns the appropriate semantic color for a numeric
 * value (positive → green, negative → red, zero → gray).
 */
export function valueColor(value: number): string {
  if (value > 0) return colors.green;
  if (value < 0) return colors.red;
  return '#9ca3af';
}

// ---------------------------------------------------------------------------
// Chart Theme (Req 4.3)
// ---------------------------------------------------------------------------

export const chartTheme = {
  /** Chart area background */
  bg: '#111827',
  /** Grid / reference lines */
  grid: '#374151',
  /** Axis tick & label color */
  axis: '#9ca3af',
  /** Axis label font size (px) */
  axisFontSize: 10,
  /** Font family for axis labels & tooltips */
  fontFamily: "'JetBrains Mono', 'Courier New', monospace",
  /** Tooltip container styles (for Recharts contentStyle) */
  tooltip: {
    backgroundColor: '#1f2937',
    border: '1px solid #374151',
    borderRadius: '8px',
  },
  /** Standard series palette */
  series: {
    portfolio: '#3b82f6',
    benchmark: '#6b7280',
    drawdown: '#ef4444',
    alpha: '#22c55e',
  },
} as const;

/**
 * Pre-built Recharts axis tick props – spread onto `<XAxis>` / `<YAxis>`.
 *
 * Usage:
 * ```tsx
 * <XAxis {...chartAxisProps} dataKey="date" />
 * ```
 */
export const chartAxisProps = {
  tick: { fill: chartTheme.axis, fontSize: chartTheme.axisFontSize, fontFamily: chartTheme.fontFamily },
  stroke: chartTheme.grid,
} as const;

/**
 * Pre-built Recharts CartesianGrid props.
 */
export const chartGridProps = {
  strokeDasharray: '3 3',
  stroke: chartTheme.grid,
} as const;

/**
 * Pre-built Recharts Tooltip contentStyle.
 */
export const chartTooltipStyle = {
  ...chartTheme.tooltip,
} as const;

// ---------------------------------------------------------------------------
// Card Tokens (Req 4.1)
// ---------------------------------------------------------------------------

export const card = {
  /** Inner padding */
  padding: '16px',
  /** Border radius */
  borderRadius: '8px',
  /** Border color – CSS custom property reference for Tailwind */
  borderColor: 'var(--color-dark-border)',
  /** Background – CSS custom property reference for Tailwind */
  bg: 'var(--color-dark-surface)',
} as const;

// ---------------------------------------------------------------------------
// Table Tokens (Req 4.4)
// ---------------------------------------------------------------------------

export const table = {
  /** Alternating row background (even rows) */
  altRowBg: 'rgba(31, 41, 55, 0.5)',
  /** Header background */
  headerBg: 'var(--color-dark-bg)',
  /** Sort icon color (inactive) */
  sortIconColor: '#6b7280',
  /** Sort icon color (active) */
  sortIconActiveColor: '#f3f4f6',
} as const;

// ---------------------------------------------------------------------------
// Page Layout (Req 4.5)
// ---------------------------------------------------------------------------

export const layout = {
  /** Standard gap between page sections */
  sectionGap: '24px',
  /** Max content width */
  maxWidth: '1800px',
  /** Page horizontal padding (responsive) */
  pagePadding: {
    sm: '16px',
    md: '24px',
    lg: '32px',
  },
} as const;

// ---------------------------------------------------------------------------
// Spacing Scale
// ---------------------------------------------------------------------------

export const spacing = {
  '0': '0px',
  '1': '4px',
  '2': '8px',
  '3': '12px',
  '4': '16px',
  '5': '20px',
  '6': '24px',
  '8': '32px',
  '10': '40px',
  '12': '48px',
  '16': '64px',
} as const;

// ---------------------------------------------------------------------------
// Typography (Req 4.6)
// ---------------------------------------------------------------------------

export const fonts = {
  /** Numeric values, data, code */
  mono: "'JetBrains Mono', 'Courier New', monospace",
  /** Labels, descriptions, UI text */
  sans: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
} as const;

/**
 * Tailwind class helpers for consistent font usage.
 * - Use `fontClass.mono` on any element displaying numeric / data values.
 * - Use `fontClass.sans` on labels and descriptions.
 */
export const fontClass = {
  mono: 'font-mono',
  sans: 'font-sans',
} as const;
