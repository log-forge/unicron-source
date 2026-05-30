/**
 * TerminalDock Client Component
 *
 * Provides two variants for terminal display:
 * - "inline": Full height/width for use in tabs
 * - "dock": Floating bottom panel with resize and collapse
 */

import { useState, useCallback, useEffect } from "react";
import { Terminal, X, ChevronUp, ChevronDown, GripHorizontal } from "lucide-react";
import { TerminalView } from "./TerminalView.client";
import { useDragResize } from "~/hooks/useDragResize";

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
// Constants
// ============================================================================

const STORAGE_KEY = "unicron-terminalHeight";
const DEFAULT_HEIGHT = 300;
const MIN_HEIGHT = 150;
const MAX_HEIGHT = 600;

// ============================================================================
// Component
// ============================================================================

export default function TerminalDockClient({
  containerId,
  hostId,
  position = "fixed",
  defaultOpen = true,
  defaultInitHeight,
  defaultMinHeight = MIN_HEIGHT,
  variant = "dock",
}: DockProps) {
  // Load persisted height from localStorage
  const getInitialHeight = (): number => {
    if (typeof window === "undefined") return defaultInitHeight ?? DEFAULT_HEIGHT;
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = parseInt(saved, 10);
        if (!isNaN(parsed) && parsed >= defaultMinHeight && parsed <= MAX_HEIGHT) {
          return parsed;
        }
      }
    } catch {
      // Ignore localStorage errors
    }
    return defaultInitHeight ?? DEFAULT_HEIGHT;
  };

  const [isOpen, setIsOpen] = useState(defaultOpen);

  // Persist height changes
  const handleResize = useCallback((_width: number, height: number) => {
    try {
      localStorage.setItem(STORAGE_KEY, String(height));
    } catch {
      // Ignore localStorage errors
    }
  }, []);

  const { size, resizeHandleProps } = useDragResize({
    initHeight: getInitialHeight(),
    opts: {
      axis: "y",
      minHeight: defaultMinHeight,
      maxHeight: MAX_HEIGHT,
      invertY: true, // Dragging up increases height
      onResize: handleResize,
    },
  });

  // Toggle dock open/close
  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  // ============================================================================
  // Inline Variant
  // ============================================================================

  if (variant === "inline") {
    return (
      <div className="flex h-full w-full flex-col overflow-hidden rounded-lg border border-neutral/20 bg-neutral-900">
        {/* Header */}
        <div className="flex items-center gap-2 border-b border-neutral/20 bg-neutral-800 px-3 py-2">
          <Terminal className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium text-text">Terminal</span>
          <span className="text-xs text-neutral">({containerId})</span>
        </div>

        {/* Terminal */}
        <div className="flex-1 overflow-hidden">
          <TerminalView
            containerKey={containerId}
            hostId={hostId ?? undefined}
          />
        </div>
      </div>
    );
  }

  // ============================================================================
  // Dock Variant
  // ============================================================================

  // Closed state - show floating button
  if (!isOpen) {
    return (
      <button
        onClick={toggleOpen}
        className={`${position} bottom-4 right-4 z-50 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white shadow-lg transition-all hover:bg-primary/90 hover:shadow-xl`}
      >
        <Terminal className="h-4 w-4" />
        Open Terminal
        <ChevronUp className="h-4 w-4" />
      </button>
    );
  }

  // Open state - show dock panel
  return (
    <div
      className={`${position} bottom-0 left-0 right-0 z-50 flex flex-col bg-neutral-900 shadow-2xl`}
      style={{ height: size.height }}
    >
      {/* Resize Handle */}
      <div
        {...resizeHandleProps}
        className="group flex h-3 cursor-ns-resize items-center justify-center border-b border-neutral/20 bg-neutral-800 transition-colors hover:bg-neutral-700"
      >
        <GripHorizontal className="h-3 w-8 text-neutral/50 group-hover:text-neutral" />
      </div>

      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral/20 bg-neutral-800 px-3 py-2">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium text-text">Terminal</span>
          <span className="text-xs text-neutral">({containerId})</span>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={toggleOpen}
            className="rounded p-1 text-neutral transition-colors hover:bg-neutral/20 hover:text-text"
            title="Minimize"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
          <button
            onClick={toggleOpen}
            className="rounded p-1 text-neutral transition-colors hover:bg-error/20 hover:text-error"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Terminal */}
      <div className="flex-1 overflow-hidden">
        <TerminalView
          containerKey={containerId}
          hostId={hostId ?? undefined}
        />
      </div>
    </div>
  );
}
