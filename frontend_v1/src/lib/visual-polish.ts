import { cn } from './utils';

// Typography classes
export const typography = {
  // Page titles
  pageTitle: 'text-2xl sm:text-3xl font-bold text-gray-100 font-mono',
  pageSubtitle: 'text-gray-400 text-sm',
  
  // Section titles
  sectionTitle: 'text-xl font-semibold text-gray-100',
  sectionSubtitle: 'text-sm text-muted-foreground',
  
  // Card titles
  cardTitle: 'text-lg font-semibold text-gray-100',
  cardDescription: 'text-sm text-muted-foreground',
  
  // Body text
  body: 'text-sm text-gray-300',
  bodySmall: 'text-xs text-gray-400',
  
  // Monospace (for numbers, code)
  mono: 'font-mono',
  monoLarge: 'text-2xl font-bold font-mono',
  monoMedium: 'text-lg font-semibold font-mono',
  monoSmall: 'text-sm font-mono',
  
  // Labels
  label: 'text-xs text-muted-foreground uppercase tracking-wide',
  labelNormal: 'text-sm text-muted-foreground',
};

// Spacing utilities
export const spacing = {
  // Page padding
  page: 'p-4 sm:p-6 lg:p-8',
  pageMaxWidth: 'max-w-[1800px] mx-auto',
  
  // Section spacing
  sectionGap: 'space-y-6',
  sectionGapLarge: 'space-y-8',
  
  // Grid gaps
  gridGap: 'gap-4',
  gridGapLarge: 'gap-6',
  
  // Card padding
  cardPadding: 'p-4',
  cardPaddingLarge: 'p-6',
};

// Color utilities for trading
export const tradingColors = {
  // P&L colors
  positive: 'text-accent-green',
  negative: 'text-accent-red',
  neutral: 'text-gray-400',
  
  // Background colors
  positiveBg: 'bg-accent-green/20',
  negativeBg: 'bg-accent-red/20',
  neutralBg: 'bg-gray-500/20',
  
  // Border colors
  positiveBorder: 'border-accent-green/30',
  negativeBorder: 'border-accent-red/30',
  neutralBorder: 'border-gray-500/30',
  
  // Status colors
  active: 'text-accent-green',
  inactive: 'text-gray-400',
  warning: 'text-yellow-400',
  error: 'text-accent-red',
  
  // Side colors (Buy/Sell)
  buy: 'text-accent-green',
  sell: 'text-accent-red',
  buyBg: 'bg-accent-green/20',
  sellBg: 'bg-accent-red/20',
};

// Badge styles
export const badgeStyles = {
  // Status badges
  active: 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-accent-green/20 text-accent-green border border-accent-green/30',
  inactive: 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-gray-500/20 text-gray-400 border border-gray-500/30',
  pending: 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
  error: 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-accent-red/20 text-accent-red border border-accent-red/30',
  
  // Side badges
  buy: 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-accent-green/20 text-accent-green',
  sell: 'px-2 py-0.5 rounded text-xs font-mono font-semibold bg-accent-red/20 text-accent-red',
  
  // Order status badges
  filled: 'px-2 py-0.5 rounded text-xs font-mono font-semibold border bg-accent-green/20 text-accent-green border-accent-green/30',
  cancelled: 'px-2 py-0.5 rounded text-xs font-mono font-semibold border bg-gray-500/20 text-gray-400 border-gray-500/30',
  rejected: 'px-2 py-0.5 rounded text-xs font-mono font-semibold border bg-accent-red/20 text-accent-red border-accent-red/30',
};

// Card styles
export const cardStyles = {
  base: 'bg-card border border-border rounded-lg',
  hover: 'hover:border-accent transition-colors',
  interactive: 'cursor-pointer hover:border-accent hover:shadow-lg transition-all',
  
  // Variants
  default: 'bg-card border border-border rounded-lg',
  elevated: 'bg-card border border-border rounded-lg shadow-lg',
  flat: 'bg-card border-0 rounded-lg',
  
  // Status variants
  success: 'bg-card border border-accent-green/30 rounded-lg',
  warning: 'bg-card border border-yellow-500/30 rounded-lg',
  error: 'bg-card border border-accent-red/30 rounded-lg',
};

// Button styles (complementing shadcn)
export const buttonStyles = {
  // Icon buttons
  iconButton: 'h-8 w-8 p-0',
  iconButtonLarge: 'h-10 w-10 p-0',
  
  // With icon
  withIcon: 'gap-2',
};

// Table styles
export const tableStyles = {
  // Cell alignment
  cellLeft: 'text-left',
  cellRight: 'text-right',
  cellCenter: 'text-center',
  
  // Cell content
  cellMono: 'font-mono text-sm',
  cellMonoBold: 'font-mono font-semibold text-sm',
  
  // Row styles
  row: 'border-b border-border hover:bg-muted/50 transition-colors',
  rowClickable: 'border-b border-border hover:bg-muted/50 cursor-pointer transition-colors',
};

// Input styles
export const inputStyles = {
  search: 'pl-9 w-full sm:w-[200px]',
  searchIcon: 'absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground',
};

// Layout utilities
export const layoutUtils = {
  // Flex utilities
  flexBetween: 'flex items-center justify-between',
  flexCenter: 'flex items-center justify-center',
  flexStart: 'flex items-center justify-start',
  flexEnd: 'flex items-center justify-end',
  
  // Grid utilities
  gridCols2: 'grid grid-cols-1 md:grid-cols-2',
  gridCols3: 'grid grid-cols-1 md:grid-cols-3',
  gridCols4: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
  gridCols5: 'grid grid-cols-2 md:grid-cols-5',
  
  // Responsive utilities
  hideOnMobile: 'hidden sm:block',
  showOnMobile: 'block sm:hidden',
};

// Animation classes
export const animationClasses = {
  // Transitions
  transition: 'transition-all duration-200 ease-in-out',
  transitionFast: 'transition-all duration-100 ease-in-out',
  transitionSlow: 'transition-all duration-300 ease-in-out',
  
  // Hover effects
  hoverScale: 'hover:scale-105 transition-transform',
  hoverLift: 'hover:-translate-y-1 transition-transform',
  hoverBrightness: 'hover:brightness-110 transition-all',
  
  // Loading states
  pulse: 'animate-pulse',
  spin: 'animate-spin',
  bounce: 'animate-bounce',
};

// Helper function to combine styles
export function combineStyles(...styles: (string | undefined | false)[]) {
  return cn(...styles.filter(Boolean));
}

// Responsive breakpoints (for reference)
export const breakpoints = {
  sm: '640px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
  '2xl': '1536px',
};
