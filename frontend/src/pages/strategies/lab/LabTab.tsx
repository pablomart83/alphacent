import { useEffect, useState } from 'react'
import { FlaskConical } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { BacktestRunnerPanel } from './BacktestRunnerPanel'
import { VibeCodePanel } from './VibeCodePanel'
import { GenerateStrategyPanel } from './GenerateStrategyPanel'
import { BootstrapPanel } from './BootstrapPanel'

/**
 * Lab tab — /strategies/lab.
 *
 * Four research panels:
 *   1. Backtest runner
 *   2. Vibe-code translator
 *   3. Generate strategy (LLM)
 *   4. Bootstrap (batch LLM generation)
 *
 * Responsive layout:
 *   - ≥1280px: 2×2 grid
 *   - <1280px: stacked, with number-key shortcuts (1-4) to jump between panels
 */
export function LabTab() {
  const [isWide, setIsWide] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth >= 1280 : true,
  )

  useEffect(() => {
    const handler = () => setIsWide(window.innerWidth >= 1280)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])

  /* Number-key shortcuts 1-4 jump between panels. */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      )
        return
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (n >= 1 && n <= 4) {
        const el = document.getElementById(`lab-panel-${n}`)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const gridClass = isWide
    ? 'grid grid-cols-2 gap-3'
    : 'grid grid-cols-1 gap-3'

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto">
      <header className="shrink-0 px-3 py-2 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
          <SectionLabel className="mb-0">Research lab</SectionLabel>
          <span className="text-[10px] text-[var(--text-3)]">
            Press 1-4 to jump between panels
          </span>
        </div>
      </header>

      <div className={`${gridClass} p-3`}>
        <div id="lab-panel-1">
          <BacktestRunnerPanel />
        </div>
        <div id="lab-panel-2">
          <VibeCodePanel />
        </div>
        <div id="lab-panel-3">
          <GenerateStrategyPanel />
        </div>
        <div id="lab-panel-4">
          <BootstrapPanel />
        </div>
      </div>
    </div>
  )
}
