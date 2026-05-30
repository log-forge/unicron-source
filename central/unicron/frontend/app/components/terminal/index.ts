/**
 * Terminal Components
 *
 * Exports terminal-related components for use across the application.
 */

export { TerminalDock } from "./TerminalDock";
export type { DockProps } from "./TerminalDock";

// Re-export client components for direct use when SSR-safety is handled externally
export { TerminalView } from "./TerminalView.client";
export type { TerminalViewProps } from "./TerminalView.client";
