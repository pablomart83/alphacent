import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCommandPalette, useUiOverlays } from '@/stores'

/**
 * Registers global keyboard shortcuts.
 *
 * Navigation: g then c/o/b/s/g/r (surfaces) + g , for settings.
 * Utility:    ⌘K / Ctrl+K opens the command palette.
 *             ?            toggles the shortcut help overlay.
 */
export function useKeyboardShortcuts() {
  const navigate = useNavigate()
  const toggleCommandPalette = useCommandPalette((s) => s.toggle)
  const toggleShortcutHelp = useUiOverlays((s) => s.toggleShortcutHelp)

  useEffect(() => {
    let prefixPressed = false
    let prefixTimer: number | null = null

    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const inField =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)

      // ⌘K / Ctrl+K — command palette (works everywhere except native text fields with modifiers)
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        toggleCommandPalette()
        return
      }

      if (inField) return

      // ? opens keyboard-shortcut help. Most browsers render `?` on Shift+/;
      // we match either form so the shortcut works across layouts.
      if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
        e.preventDefault()
        toggleShortcutHelp()
        return
      }

      // g prefix navigation
      if (!prefixPressed && e.key.toLowerCase() === 'g') {
        prefixPressed = true
        if (prefixTimer) window.clearTimeout(prefixTimer)
        prefixTimer = window.setTimeout(() => {
          prefixPressed = false
        }, 1200)
        return
      }

      if (prefixPressed) {
        const k = e.key.toLowerCase()
        const routes: Record<string, string> = {
          c: '/',
          o: '/observatory',
          b: '/book',
          s: '/strategies',
          g: '/guard',
          r: '/research',
          ',': '/settings',
        }
        if (k in routes) {
          e.preventDefault()
          navigate(routes[k])
        }
        prefixPressed = false
        if (prefixTimer) window.clearTimeout(prefixTimer)
        return
      }

      // ? opens keyboard help (future — Sprint 12)
      // Esc handled per component
    }

    window.addEventListener('keydown', handler)
    return () => {
      window.removeEventListener('keydown', handler)
      if (prefixTimer) window.clearTimeout(prefixTimer)
    }
  }, [navigate, toggleCommandPalette, toggleShortcutHelp])
}
