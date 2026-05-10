/**
 * Design tokens exposed as TS constants — mirror the CSS vars in
 * `src/styles/tokens.css`. Use when a value must be read from JS
 * (e.g., chart config). Prefer the CSS variable for styling.
 */

export const colors = {
  bg0: 'var(--bg-0)',
  bg1: 'var(--bg-1)',
  bg2: 'var(--bg-2)',
  bg3: 'var(--bg-3)',
  bgHover: 'var(--bg-hover)',
  bgActive: 'var(--bg-active)',

  borderSubtle: 'var(--border-subtle)',
  borderDefault: 'var(--border-default)',
  borderStrong: 'var(--border-strong)',
  borderFocus: 'var(--border-focus)',

  text0: 'var(--text-0)',
  text1: 'var(--text-1)',
  text2: 'var(--text-2)',
  text3: 'var(--text-3)',

  pnlUp: 'var(--pnl-up)',
  pnlUpBg: 'var(--pnl-up-bg)',
  pnlUpFlash: 'var(--pnl-up-flash)',
  pnlDown: 'var(--pnl-down)',
  pnlDownBg: 'var(--pnl-down-bg)',
  pnlDownFlash: 'var(--pnl-down-flash)',
  pnlFlat: 'var(--pnl-flat)',

  regimeUpStrong: 'var(--regime-up-strong)',
  regimeUp: 'var(--regime-up)',
  regimeUpWeak: 'var(--regime-up-weak)',
  regimeRange: 'var(--regime-range)',
  regimeDownWeak: 'var(--regime-down-weak)',
  regimeDown: 'var(--regime-down)',
  regimeDownStrong: 'var(--regime-down-strong)',
  regimeVol: 'var(--regime-vol)',

  accountDemo: 'var(--account-demo)',
  accountLive: 'var(--account-live)',

  accentPrimary: 'var(--accent-primary)',
  accentSecondary: 'var(--accent-secondary)',
  accentTicker: 'var(--accent-ticker)',

  statusWarning: 'var(--status-warning)',
  statusError: 'var(--status-error)',
  statusSuccess: 'var(--status-success)',
  statusInfo: 'var(--status-info)',
} as const

export const fonts = {
  ui: 'var(--font-ui)',
  mono: 'var(--font-mono)',
} as const

export const spacing = {
  sp0: 0,
  sp0_5: 2,
  sp1: 4,
  sp1_5: 6,
  sp2: 8,
  sp3: 12,
  sp4: 16,
  sp5: 20,
  sp6: 24,
  sp8: 32,
  sp10: 40,
  sp12: 48,
} as const

export const motion = {
  easeStandard: 'cubic-bezier(0.4, 0, 0.2, 1)',
  durFlash: 400,
  durFast: 120,
  durBase: 200,
  durSlow: 300,
} as const

/** Resolve a CSS variable at runtime. Returns the computed hex/rgb value. */
export function resolveCssVar(varName: string): string {
  if (typeof window === 'undefined') return ''
  const name = varName.startsWith('--') ? varName : `--${varName}`
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Map a regime string to its token. */
export function regimeColor(regime: string | null | undefined): string {
  if (!regime) return colors.text2
  const key = regime.toLowerCase().replace(/\s+/g, '_')
  switch (key) {
    case 'trending_up_strong':
      return colors.regimeUpStrong
    case 'trending_up':
      return colors.regimeUp
    case 'trending_up_weak':
      return colors.regimeUpWeak
    case 'ranging':
      return colors.regimeRange
    case 'trending_down_weak':
      return colors.regimeDownWeak
    case 'trending_down':
      return colors.regimeDown
    case 'trending_down_strong':
      return colors.regimeDownStrong
    case 'high_vol':
    case 'volatile':
      return colors.regimeVol
    default:
      return colors.text2
  }
}

/** Map a conviction score (0-100) to its gradient token. */
export function convictionColor(score: number): string {
  if (score < 40) return 'var(--conviction-0)'
  if (score < 55) return 'var(--conviction-40)'
  if (score < 65) return 'var(--conviction-55)'
  if (score < 74) return 'var(--conviction-65)'
  if (score < 85) return 'var(--conviction-74)'
  return 'var(--conviction-85)'
}

/** Map a P&L delta to the right token. Flat band: |value| < epsilon. */
export function pnlColor(value: number, epsilon = 0.0001): string {
  if (Math.abs(value) < epsilon) return colors.pnlFlat
  return value > 0 ? colors.pnlUp : colors.pnlDown
}
