import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives'

interface KeyboardShortcutHelpProps {
  open: boolean
  onOpenChange: (v: boolean) => void
}

/**
 * Global shortcut cheat-sheet summoned by `?`. Mirrors the Shortcuts tab
 * under Settings but lives as a modal so it can be opened from any
 * surface. Content is hand-curated rather than reflected from the
 * useKeyboardShortcuts hook — when the hook grows, update both.
 */
export function KeyboardShortcutHelp({ open, onOpenChange }: KeyboardShortcutHelpProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg" className="max-h-[80vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>
            Shortcuts activate when focus is outside a text input. See Settings → Shortcuts for a
            permanent reference.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4 mt-2">
          <Group title="Navigation">
            <Row keys={['g', 'c']} label="Go to Command" />
            <Row keys={['g', 'b']} label="Go to Book" />
            <Row keys={['g', 's']} label="Go to Strategies" />
            <Row keys={['g', 'g']} label="Go to Guard" />
            <Row keys={['g', 'r']} label="Go to Research" />
            <Row keys={['g', 'i']} label="Go to Intel" />
            <Row keys={['g', ',']} label="Go to Settings" />
          </Group>
          <Group title="Utilities">
            <Row keys={['⌘', 'K']} label="Command palette" />
            <Row keys={['?']} label="Toggle this cheat sheet" />
            <Row keys={['/']} label="Focus page search" />
            <Row keys={['Esc']} label="Close modal / drawer" />
            <Row keys={['⌘', 'Enter']} label="Save form" />
          </Group>
          <Group title="Tables">
            <Row keys={['j']} label="Move selection down" />
            <Row keys={['k']} label="Move selection up" />
            <Row keys={['x']} label="Toggle row checkbox" />
            <Row keys={['Shift', 'Click']} label="Multi-column sort" />
          </Group>
          <Group title="Research · tabs">
            <Row keys={['1', '–', '8']} label="Jump to tab N" />
            <Row keys={['[']} label="Previous tab" />
            <Row keys={[']']} label="Next tab" />
          </Group>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{title}</h3>
      <div className="space-y-1">{children}</div>
    </div>
  )
}

function Row({ keys, label }: { keys: string[]; label: string }) {
  return (
    <div className="flex items-center justify-between text-[12px]">
      <span className="text-[var(--text-1)]">{label}</span>
      <div className="flex items-center gap-1">
        {keys.map((k, i) => (
          <kbd
            key={i}
            className="mono text-[10px] px-1.5 py-0.5 bg-[var(--bg-2)] border border-[var(--border-subtle)] rounded-[2px] text-[var(--text-1)]"
          >
            {k}
          </kbd>
        ))}
      </div>
    </div>
  )
}
