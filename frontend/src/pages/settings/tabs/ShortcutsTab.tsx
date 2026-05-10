import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'

/**
 * Shortcuts reference. Static list — the authoritative registration is
 * in src/hooks/useKeyboardShortcuts.ts.
 */
export function ShortcutsTab() {
  return (
    <div className="max-w-[720px] space-y-4">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Keyboard shortcuts</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)]">
          Global shortcuts are active whenever focus is outside a text input. Surface-local
          shortcuts (j/k in tables, number keys to switch tabs, [ / ] to rotate tabs) are listed in
          each surface's help panel.
        </p>
      </div>

      <Card padding="md" className="space-y-4">
        <Group title="Navigation">
          <Row keys={['g', 'c']} label="Go to Command" />
          <Row keys={['g', 'b']} label="Go to Book" />
          <Row keys={['g', 's']} label="Go to Strategies" />
          <Row keys={['g', 'g']} label="Go to Guard" />
          <Row keys={['g', 'r']} label="Go to Research" />
          <Row keys={['g', ',']} label="Go to Settings" />
        </Group>

        <Group title="Global utilities">
          <Row keys={['⌘', 'K']} label="Command palette" />
          <Row keys={['/']} label="Focus page search" />
          <Row keys={['?']} label="Keyboard shortcut help (coming soon)" />
          <Row keys={['Esc']} label="Close modal / dropdown / drawer" />
        </Group>

        <Group title="Tables">
          <Row keys={['j']} label="Move selection down" />
          <Row keys={['k']} label="Move selection up" />
          <Row keys={['x']} label="Toggle row checkbox" />
          <Row keys={['Shift', 'click']} label="Multi-column sort" />
        </Group>

        <Group title="Forms">
          <Row keys={['⌘', 'Enter']} label="Save" />
        </Group>

        <Group title="Research tabs">
          <Row keys={['1'.concat(' - 8')]} label="Jump between tabs" />
          <Row keys={['[']} label="Previous tab" />
          <Row keys={[']']} label="Next tab" />
        </Group>
      </Card>
    </div>
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
    <div className="flex items-center justify-between text-[11px]">
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
