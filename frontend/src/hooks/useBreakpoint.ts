import { useEffect, useState } from 'react'
import { BREAKPOINTS, type Breakpoint } from '@/lib/design-tokens'

/**
 * Track the current viewport against the canonical breakpoint scale
 * (lib/design-tokens.ts BREAKPOINTS). SSR-safe (assumes desktop until mounted)
 * and driven by matchMedia so it only re-renders on an actual breakpoint cross,
 * not on every resize pixel.
 *
 * Returns the largest matched breakpoint name plus convenience booleans and a
 * `min(bp)` predicate for `viewport >= BREAKPOINTS[bp]`.
 */
export interface BreakpointState {
  /** Largest breakpoint whose min-width the viewport satisfies ('base' below sm). */
  active: Breakpoint | 'base'
  width: number
  /** viewport width >= BREAKPOINTS[bp] */
  min: (bp: Breakpoint) => boolean
  /** viewport width < BREAKPOINTS[bp] */
  below: (bp: Breakpoint) => boolean
  isMobile: boolean // < md (768)
  isTablet: boolean // >= md and < lg
  isDesktop: boolean // >= lg
}

function computeActive(width: number): Breakpoint | 'base' {
  let active: Breakpoint | 'base' = 'base'
  for (const [name, min] of Object.entries(BREAKPOINTS)) {
    if (width >= min) active = name as Breakpoint
  }
  return active
}

function readWidth(): number {
  if (typeof window === 'undefined') return BREAKPOINTS.xl // assume desktop on SSR
  return window.innerWidth
}

export function useBreakpoint(): BreakpointState {
  const [width, setWidth] = useState<number>(readWidth)

  useEffect(() => {
    if (typeof window === 'undefined') return
    // One listener per breakpoint edge — fires only when a boundary is crossed.
    const queries = Object.values(BREAKPOINTS).map((min) =>
      window.matchMedia(`(min-width: ${min}px)`),
    )
    const onChange = () => setWidth(window.innerWidth)
    queries.forEach((q) => q.addEventListener('change', onChange))
    // Sync once on mount (covers the SSR→client hydration gap).
    onChange()
    return () => queries.forEach((q) => q.removeEventListener('change', onChange))
  }, [])

  const active = computeActive(width)
  const min = (bp: Breakpoint) => width >= BREAKPOINTS[bp]
  const below = (bp: Breakpoint) => width < BREAKPOINTS[bp]

  return {
    active,
    width,
    min,
    below,
    isMobile: below('md'),
    isTablet: min('md') && below('lg'),
    isDesktop: min('lg'),
  }
}
