/**
 * Empty State Component
 *
 * Displayed when no agents/hosts are connected to the system.
 * Provides explicit local/remote enrollment entry points.
 */

import { Monitor, Plus } from "lucide-react";

interface EmptyStateProps {
  onCreateLocalAgent: () => void;
  onCreateRemoteAgent: () => void;
}

// ============================================================================
// Component
// ============================================================================

export function EmptyState({ onCreateLocalAgent, onCreateRemoteAgent }: EmptyStateProps) {
  return (
    <div className="w-full rounded-xl border border-neutral/20 bg-neutral/5 p-lg dark:bg-neutral-900/50">
      <div className="flex items-start gap-lg">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-neutral/10">
          <Monitor className="h-8 w-8 text-neutral" />
        </div>
        <div className="flex-1">
          <h3 className="mb-xs text-lg font-semibold text-text">
            No hosts connected
          </h3>
          <p className="mb-md text-sm text-neutral">
            Enroll an agent to start monitoring containers. You can add a local agent on this machine or enroll a remote agent on another host.
          </p>
          <div className="flex flex-wrap items-center gap-sm">
            <button
              type="button"
              onClick={onCreateLocalAgent}
              className="inline-flex cursor-pointer items-center gap-xs rounded-md bg-primary px-sm py-xs text-sm font-medium text-white transition hover:bg-primary/90"
            >
              <Plus className="h-4 w-4" />
              Create Local Agent
            </button>
            <button
              type="button"
              onClick={onCreateRemoteAgent}
              className="inline-flex cursor-pointer items-center gap-xs rounded-md border border-neutral/30 px-sm py-xs text-sm font-medium text-text transition hover:bg-neutral/10"
            >
              <Plus className="h-4 w-4" />
              Add Remote Agent
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
