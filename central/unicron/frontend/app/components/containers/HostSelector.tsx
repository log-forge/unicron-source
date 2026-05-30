/**
 * HostSelector Component
 *
 * Displays available hosts as selectable tabs or dropdown for switching between
 * local and remote agent containers. Shows online/offline status and container counts.
 *
 * Rendering strategy:
 * - 0-1 hosts: renders nothing (no selector needed)
 * - 2-5 hosts: horizontal tab-style selector
 * - 6+ hosts: dropdown select
 */

import React from "react";
import { Server } from "lucide-react";

// ============================================================================
// Types
// ============================================================================

export interface HostInfo {
  host_id: string;
  online: boolean;
  container_count: number;
  last_seen?: string;
}

export interface HostSelectorProps {
  hosts: HostInfo[];
  selectedHost: string | null;
  onHostChange: (hostId: string) => void;
}

// ============================================================================
// Tab Variant (2-5 hosts)
// ============================================================================

interface HostTabProps {
  host: HostInfo;
  isSelected: boolean;
  onClick: () => void;
}

function HostTab({ host, isSelected, onClick }: HostTabProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!host.online}
      className={`
        flex items-center gap-xs rounded-lg border px-sm py-2xs transition-all
        ${
          isSelected
            ? "border-primary/50 bg-primary/10 text-primary"
            : host.online
            ? "border-neutral/20 bg-background text-text hover:border-neutral/40 hover:bg-neutral/5"
            : "cursor-not-allowed border-neutral/10 bg-neutral/5 text-neutral/40 opacity-50"
        }
      `}
      title={host.online ? `Switch to ${host.host_id}` : `${host.host_id} (offline)`}
    >
      <Server className="h-4 w-4" />
      <span
        className={`inline-block h-1.5 w-1.5 rounded-full ${
          host.online ? "bg-green-500" : "bg-neutral/40"
        }`}
      />
      <span className="text-sm font-medium">{host.host_id}</span>
      <span
        className={`rounded-full px-1.5 py-0.5 text-xs font-medium ${
          isSelected
            ? "bg-primary/20 text-primary"
            : host.online
            ? "bg-neutral/10 text-neutral"
            : "bg-neutral/5 text-neutral/40"
        }`}
      >
        {host.container_count}
      </span>
    </button>
  );
}

function TabSelector({ hosts, selectedHost, onHostChange }: HostSelectorProps) {
  return (
    <div className="flex flex-wrap items-center gap-xs rounded-lg border border-neutral/20 bg-muted p-xs">
      {hosts.map((host) => (
        <HostTab
          key={host.host_id}
          host={host}
          isSelected={selectedHost === host.host_id}
          onClick={() => host.online && onHostChange(host.host_id)}
        />
      ))}
    </div>
  );
}

// ============================================================================
// Dropdown Variant (6+ hosts)
// ============================================================================

function DropdownSelector({ hosts, selectedHost, onHostChange }: HostSelectorProps) {
  return (
    <div className="flex items-center gap-sm">
      <label htmlFor="host-select" className="text-sm font-medium text-text">
        Host:
      </label>
      <div className="relative inline-flex items-center gap-xs">
        <Server className="pointer-events-none absolute left-2 h-4 w-4 text-neutral" />
        <select
          id="host-select"
          value={selectedHost || ""}
          onChange={(e) => onHostChange(e.target.value)}
          className="appearance-none rounded-lg border border-neutral/20 bg-background pl-8 pr-10 py-2 text-sm text-text focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        >
          {hosts.map((host) => (
            <option
              key={host.host_id}
              value={host.host_id}
              disabled={!host.online}
            >
              {host.host_id}
              {!host.online && " (offline)"}
              {" ("}
              {host.container_count}
              {")"}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function HostSelector({ hosts, selectedHost, onHostChange }: HostSelectorProps) {
  // No selector needed for 0-1 hosts
  if (hosts.length <= 1) {
    return null;
  }

  // Use tabs for 2-5 hosts, dropdown for 6+
  if (hosts.length <= 5) {
    return <TabSelector hosts={hosts} selectedHost={selectedHost} onHostChange={onHostChange} />;
  }

  return <DropdownSelector hosts={hosts} selectedHost={selectedHost} onHostChange={onHostChange} />;
}

export default HostSelector;
