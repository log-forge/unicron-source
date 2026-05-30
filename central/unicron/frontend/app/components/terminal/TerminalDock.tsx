/**
 * TerminalDock Component
 *
 * SSR-safe wrapper for TerminalDock.client.
 * Lazy loads the client component to avoid xterm.js SSR issues.
 */

import { lazy, Suspense } from "react";

// ============================================================================
// Types
// ============================================================================

export interface DockProps {
  containerId: string;
  hostId?: string | null;
  position?: "fixed" | "absolute";
  defaultOpen?: boolean;
  defaultInitHeight?: number;
  defaultMinHeight?: number;
  variant?: "dock" | "inline";
}

// ============================================================================
// Lazy Load Client Component
// ============================================================================

const TerminalDockClient = lazy(() =>
  import("./TerminalDock.client").then((mod) => ({
    default: mod.default,
  }))
);

// ============================================================================
// Loading Fallback
// ============================================================================

function LoadingFallback({ variant }: { variant?: "dock" | "inline" }) {
  if (variant === "inline") {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-lg border border-neutral/20 bg-neutral-900">
        <div className="flex flex-col items-center gap-2">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-neutral/20 border-t-primary" />
          <span className="text-sm text-neutral">Loading terminal...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex items-center gap-2 rounded-lg bg-neutral-800 px-4 py-2 text-sm font-medium text-neutral shadow-lg">
      <div className="h-4 w-4 animate-spin rounded-full border-2 border-neutral/20 border-t-primary" />
      Loading terminal...
    </div>
  );
}

// ============================================================================
// Component
// ============================================================================

export function TerminalDock(props: DockProps) {
  // Don't render on server
  if (typeof window === "undefined") {
    return null;
  }

  return (
    <Suspense fallback={<LoadingFallback variant={props.variant} />}>
      <TerminalDockClient {...props} />
    </Suspense>
  );
}

export default TerminalDock;
