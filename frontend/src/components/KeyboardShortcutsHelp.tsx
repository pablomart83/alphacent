import { type FC } from 'react';
import { KEYBOARD_SHORTCUTS } from '../hooks/useKeyboardShortcuts';

interface KeyboardShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
}

export const KeyboardShortcutsHelp: FC<KeyboardShortcutsHelpProps> = ({ open, onClose }) => {
  if (!open) return null;

  const categories = {
    navigation: 'Navigation',
    actions: 'Actions',
    general: 'General',
  } as const;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
    >
      <div
        className="rounded-xl border shadow-2xl w-full max-w-md mx-4"
        style={{
          backgroundColor: 'var(--color-dark-surface)',
          borderColor: 'var(--color-dark-border)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          className="flex items-center justify-between px-6 py-4 border-b"
          style={{ borderColor: 'var(--color-dark-border)' }}
        >
          <h2 className="text-lg font-semibold" style={{ color: 'var(--color-text)' }}>
            Keyboard Shortcuts
          </h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-200 transition-colors text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="px-6 py-4 space-y-5 max-h-[60vh] overflow-y-auto">
          {(Object.keys(categories) as Array<keyof typeof categories>).map((cat) => {
            const items = KEYBOARD_SHORTCUTS.filter((s) => s.category === cat);
            if (items.length === 0) return null;
            return (
              <div key={cat}>
                <h3
                  className="text-xs font-semibold uppercase tracking-wider mb-2"
                  style={{ color: 'var(--color-text-secondary)' }}
                >
                  {categories[cat]}
                </h3>
                <div className="space-y-2">
                  {items.map((shortcut) => (
                    <div
                      key={shortcut.key}
                      className="flex items-center justify-between py-1"
                    >
                      <span className="text-sm" style={{ color: 'var(--color-text)' }}>
                        {shortcut.description}
                      </span>
                      <kbd
                        className="px-2 py-0.5 rounded text-xs font-mono border"
                        style={{
                          backgroundColor: 'var(--color-dark-bg)',
                          borderColor: 'var(--color-dark-border)',
                          color: 'var(--color-text-secondary)',
                        }}
                      >
                        {shortcut.label}
                      </kbd>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>

        <div
          className="px-6 py-3 border-t text-center"
          style={{ borderColor: 'var(--color-dark-border)' }}
        >
          <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            Press <kbd className="px-1 py-0.5 rounded text-xs font-mono border mx-1"
              style={{
                backgroundColor: 'var(--color-dark-bg)',
                borderColor: 'var(--color-dark-border)',
              }}
            >?</kbd> or <kbd className="px-1 py-0.5 rounded text-xs font-mono border mx-1"
              style={{
                backgroundColor: 'var(--color-dark-bg)',
                borderColor: 'var(--color-dark-border)',
              }}
            >Esc</kbd> to close
          </span>
        </div>
      </div>
    </div>
  );
};
