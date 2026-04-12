/**
 * Workspace Presets — save/load/switch layout presets for the AlphaCent platform.
 *
 * Each preset snapshots:
 *  - react-resizable-panels layout sizes (per page)
 *  - PanelHeader collapsed states
 *  - BottomWidgetZone visibility
 *
 * Storage keys consumed/produced:
 *  - `react-resizable-panels:${layoutId}:` — panel sizes (written by react-resizable-panels)
 *  - `alphacent_panel_collapsed_${panelId}` — collapse booleans
 *  - `alphacent_bottom_widgets` — widget visibility map
 */

// ── Constants ────────────────────────────────────────────────────────────────

const PRESETS_KEY = 'alphacent_workspace_presets';
const ACTIVE_KEY = 'alphacent_active_preset';
const MAX_USER_PRESETS = 5;

export const WORKSPACE_PRESET_EVENT = 'alphacent:workspace-preset-changed';

// ── Layout IDs used across pages ─────────────────────────────────────────────

const LAYOUT_IDS = [
  'overview-panels',
  'portfolio-panels',
  'orders-panels',
  'strategies-panels',
  'autonomous-panels',
  'risk-panels',
  'data-management-panels',
  'system-health-panels',
  'audit-log-panels',
] as const;

// Panel IDs used in PanelHeader (collapse state)
const PANEL_IDS = [
  'overview-metrics',
  'overview-equity',
  'overview-activity',
  'portfolio-summary',
  'orders-side',
  'strategies-side',
  'autonomous-side',
  'risk-side',
  'syshealth-main',
  'syshealth-side',
  'audit-main',
  'audit-side',
  'data-main',
  'data-side',
] as const;

const WIDGET_KEY = 'alphacent_bottom_widgets';

// ── Types ────────────────────────────────────────────────────────────────────

interface PresetSnapshot {
  /** Panel layout sizes keyed by their full localStorage key */
  panelSizes: Record<string, string>;
  /** Collapsed states keyed by panelId */
  collapsedPanels: Record<string, string>;
  /** Widget visibility JSON string */
  widgetVisibility: string | null;
}

export interface WorkspacePreset {
  name: string;
  isDefault: boolean;
  snapshot: PresetSnapshot;
}

interface PresetsStore {
  presets: WorkspacePreset[];
}

// ── Snapshot helpers ─────────────────────────────────────────────────────────

function captureSnapshot(): PresetSnapshot {
  const panelSizes: Record<string, string> = {};
  const collapsedPanels: Record<string, string> = {};

  // Capture react-resizable-panels layout data
  // The library stores keys like `react-resizable-panels:${id}:` or with panel ids
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith('react-resizable-panels:')) {
      panelSizes[key] = localStorage.getItem(key) ?? '';
    }
  }

  // Capture PanelHeader collapsed states
  for (const pid of PANEL_IDS) {
    const key = `alphacent_panel_collapsed_${pid}`;
    const val = localStorage.getItem(key);
    if (val !== null) {
      collapsedPanels[pid] = val;
    }
  }

  const widgetVisibility = localStorage.getItem(WIDGET_KEY);

  return { panelSizes, collapsedPanels, widgetVisibility };
}

function applySnapshot(snapshot: PresetSnapshot): void {
  // Clear existing panel-related keys first
  const keysToRemove: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key?.startsWith('react-resizable-panels:')) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach(k => localStorage.removeItem(k));

  // Apply panel sizes
  for (const [key, val] of Object.entries(snapshot.panelSizes)) {
    localStorage.setItem(key, val);
  }

  // Apply collapsed states
  for (const pid of PANEL_IDS) {
    const key = `alphacent_panel_collapsed_${pid}`;
    if (pid in snapshot.collapsedPanels) {
      localStorage.setItem(key, snapshot.collapsedPanels[pid]);
    } else {
      localStorage.removeItem(key);
    }
  }

  // Apply widget visibility
  if (snapshot.widgetVisibility !== null) {
    localStorage.setItem(WIDGET_KEY, snapshot.widgetVisibility);
  } else {
    localStorage.removeItem(WIDGET_KEY);
  }
}

// ── Default presets ──────────────────────────────────────────────────────────

function makeLayoutKey(layoutId: string): string {
  return `react-resizable-panels:${layoutId}:`;
}

function buildDefaultPresets(): WorkspacePreset[] {
  // ── Trading: chart-dominant, position ticker prominent ──
  const tradingPanelSizes: Record<string, string> = {};
  // Overview: large center (equity chart)
  // Most 2-panel pages: main gets more space
  for (const lid of LAYOUT_IDS) {
    if (lid === 'overview-panels') {
      // Overview has 3 panels: metrics(20), equity(55), activity(25)
      // We don't set this — let the page defaults handle 3-panel layouts
      // since we can't know the exact panel IDs without running the app
    } else {
      // 2-panel pages: main 65%, side 35% (default-ish, slightly chart-heavy)
      tradingPanelSizes[makeLayoutKey(lid)] = ''; // clear to use page defaults
    }
  }

  const tradingCollapsed: Record<string, string> = {};
  // Keep all panels expanded for trading
  for (const pid of PANEL_IDS) {
    tradingCollapsed[pid] = 'false';
  }

  const tradingWidgets = JSON.stringify({
    'top-movers': true,
    'recent-signals': true,
    'market-regime': false,
    'strategy-alerts': false,
    'macro-pulse': false,
  });

  // ── Monitoring: system health + alerts prominent ──
  const monitoringCollapsed: Record<string, string> = {};
  for (const pid of PANEL_IDS) {
    monitoringCollapsed[pid] = 'false';
  }

  const monitoringWidgets = JSON.stringify({
    'top-movers': false,
    'recent-signals': false,
    'market-regime': true,
    'strategy-alerts': true,
    'macro-pulse': false,
  });

  // ── Analysis: analytics tabs prominent ──
  const analysisCollapsed: Record<string, string> = {};
  for (const pid of PANEL_IDS) {
    analysisCollapsed[pid] = 'false';
  }

  const analysisWidgets = JSON.stringify({
    'top-movers': false,
    'recent-signals': false,
    'market-regime': true,
    'strategy-alerts': false,
    'macro-pulse': true,
  });

  return [
    {
      name: 'Trading',
      isDefault: true,
      snapshot: {
        panelSizes: tradingPanelSizes,
        collapsedPanels: tradingCollapsed,
        widgetVisibility: tradingWidgets,
      },
    },
    {
      name: 'Monitoring',
      isDefault: true,
      snapshot: {
        panelSizes: {},
        collapsedPanels: monitoringCollapsed,
        widgetVisibility: monitoringWidgets,
      },
    },
    {
      name: 'Analysis',
      isDefault: true,
      snapshot: {
        panelSizes: {},
        collapsedPanels: analysisCollapsed,
        widgetVisibility: analysisWidgets,
      },
    },
  ];
}

// ── Persistence ──────────────────────────────────────────────────────────────

function loadStore(): PresetsStore {
  try {
    const raw = localStorage.getItem(PRESETS_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as PresetsStore;
      // Ensure defaults are always present
      const defaults = buildDefaultPresets();
      const defaultNames = new Set(defaults.map(d => d.name));
      const userPresets = parsed.presets.filter(p => !p.isDefault && !defaultNames.has(p.name));
      return { presets: [...defaults, ...userPresets] };
    }
  } catch { /* ignore */ }
  return { presets: buildDefaultPresets() };
}

function saveStore(store: PresetsStore): void {
  try {
    localStorage.setItem(PRESETS_KEY, JSON.stringify(store));
  } catch { /* ignore */ }
}

// ── Public API ───────────────────────────────────────────────────────────────

/** Get all presets (defaults + user). */
export function getPresets(): WorkspacePreset[] {
  return loadStore().presets;
}

/** Get the name of the currently active preset (or null if none / custom). */
export function getActivePreset(): string | null {
  return localStorage.getItem(ACTIVE_KEY);
}

/**
 * Switch to a preset by name.
 * Applies the snapshot to localStorage and reloads the page.
 */
export function setActivePreset(name: string): void {
  const store = loadStore();
  const preset = store.presets.find(p => p.name === name);
  if (!preset) return;

  applySnapshot(preset.snapshot);
  localStorage.setItem(ACTIVE_KEY, name);

  // Dispatch event so components can react (or we just reload)
  window.dispatchEvent(new CustomEvent(WORKSPACE_PRESET_EVENT, { detail: { name } }));
  // Simplest approach: reload to let all components re-read localStorage
  window.location.reload();
}

/**
 * Save the current workspace state as a user preset.
 * Returns false if the max user preset limit is reached.
 */
export function savePreset(name: string): boolean {
  const store = loadStore();
  const userPresets = store.presets.filter(p => !p.isDefault);
  const existingIdx = store.presets.findIndex(p => p.name === name);

  // If updating an existing preset, just overwrite
  if (existingIdx >= 0) {
    store.presets[existingIdx] = {
      name,
      isDefault: store.presets[existingIdx].isDefault,
      snapshot: captureSnapshot(),
    };
  } else {
    // New preset — check limit
    if (userPresets.length >= MAX_USER_PRESETS) return false;
    store.presets.push({
      name,
      isDefault: false,
      snapshot: captureSnapshot(),
    });
  }

  saveStore(store);
  localStorage.setItem(ACTIVE_KEY, name);
  return true;
}

/**
 * Delete a user preset by name. Cannot delete default presets.
 */
export function deletePreset(name: string): void {
  const store = loadStore();
  store.presets = store.presets.filter(p => !(p.name === name && !p.isDefault));
  saveStore(store);

  // If the deleted preset was active, clear active
  if (getActivePreset() === name) {
    localStorage.removeItem(ACTIVE_KEY);
  }
}

/**
 * Reset to the "Trading" default preset.
 */
export function resetToDefault(): void {
  setActivePreset('Trading');
}
