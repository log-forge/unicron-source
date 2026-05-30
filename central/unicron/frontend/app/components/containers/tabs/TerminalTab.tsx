/**
 * TerminalTab Component
 *
 * Provides an interactive terminal session for a container.
 * Uses TerminalDock in inline mode to fill the tab content area.
 */

import { TerminalDock } from "~/components/terminal";

// ============================================================================
// Types
// ============================================================================

interface TerminalTabProps {
  containerKey: string;
  hostId: string | null;
}

// ============================================================================
// Component
// ============================================================================

export default function TerminalTab({ containerKey, hostId }: TerminalTabProps) {
  return (
    <div className="h-[500px] w-full bg-background">
      {typeof window !== "undefined" ? (
        <TerminalDock
          containerId={containerKey}
          hostId={hostId ?? undefined}
          variant="inline"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center rounded-lg border border-neutral/20 bg-neutral-900">
          <p className="text-neutral">Loading terminal...</p>
        </div>
      )}
    </div>
  );
}
