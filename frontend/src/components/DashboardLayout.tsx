/**
 * DashboardLayout — transparent passthrough when inside AppShell.
 *
 * AppShell (in App.tsx) now owns TopNavBar, MetricsBar, PositionTickerStrip,
 * BottomWidgetZone and all their polling. It mounts once and survives navigation.
 *
 * When a page renders <DashboardLayout onLogout={...}>, we detect we're inside
 * AppShell via ShellContext and just render children — no duplicate chrome.
 * This means zero changes needed in any page file.
 */
import { type FC, type ReactNode } from 'react';
import { useShell } from './AppShell';

interface DashboardLayoutProps {
  children: ReactNode;
  onLogout: () => void;
}

export const DashboardLayout: FC<DashboardLayoutProps> = ({ children }) => {
  const shell = useShell();

  // Inside AppShell — just render children, shell provides all the chrome
  if (shell) {
    return <>{children}</>;
  }

  // Fallback: standalone mode (e.g. tests, Storybook) — render minimal wrapper
  return (
    <div className="flex flex-col h-screen overflow-hidden bg-dark-bg">
      <main className="flex-1 overflow-auto min-h-0">
        {children}
      </main>
    </div>
  );
};
