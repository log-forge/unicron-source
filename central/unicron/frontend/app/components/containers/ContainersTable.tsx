/**
 * Containers Table Component
 *
 * Displays a table of monitored containers grouped by host with expandable sections.
 * Ported from original LogForge alert-engine frontend.
 */

import React, { useState, useEffect, useRef } from "react";
import { ChevronDown, ChevronRight, Container, Server } from "lucide-react";
import { HostStatusDot } from "./HostStatusDot";
import { useHostStatus, getHostStatus } from "../../hooks/useHostStatus";
import {
  LogCollectionBadge,
  type LogCollectionIssue,
  type LogCollectionStatus,
} from "./logCollection";

// ============================================================================
// Types
// ============================================================================

export interface ContainerInfo {
  identifier: string;
  name: string;
  host_id?: string;
  container_key: string;
  docker_container_id?: string | null;
  image_name: string;
  last_seen: string;
  status?: string;
  labels?: Record<string, string>;
  ports?: Record<string, any>;
  started_at?: string;
  monitoring_enabled?: boolean;
  log_collection_status?: LogCollectionStatus | null;
  log_collection_issue?: LogCollectionIssue | null;
}

export interface GroupInfo {
  groupId: number | string;
  name: string;
  containerIds: string[];
  members?: { host_id: string; container_name: string }[];
  monitoredContainerCount?: number;
  monitoredContainers?: string[];
}

interface ContainersTableProps {
  containers: ContainerInfo[];
  groups: GroupInfo[];
  isLoading?: boolean;
  onContainerClick?: (container: ContainerInfo) => void;
  /** Click handler for host row navigation */
  onHostClick?: (hostId: string) => void;
  /** Authoritative host online status from /containers/overview */
  authoritativeHostStatuses?: Record<string, { online: boolean; last_seen?: string }>;
  monitoredByContainer?: Record<string, boolean>;
}

// ============================================================================
// Persistent State Store
// ============================================================================

// Create a persistent store for expanded groups outside of component
const expandedGroupsStore = {
  groups: new Set<number>(),
  listeners: new Set<(groups: Set<number>) => void>(),

  toggle(groupId: number) {
    if (this.groups.has(groupId)) {
      this.groups.delete(groupId);
    } else {
      this.groups.add(groupId);
    }
    this.notify();
  },

  subscribe(listener: (groups: Set<number>) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  },

  notify() {
    this.listeners.forEach((listener) => listener(new Set(this.groups)));
  },
};

// Create a persistent store for expanded hosts outside of component
const expandedHostsStore = {
  hosts: new Set<string>(),
  listeners: new Set<(hosts: Set<string>) => void>(),

  toggle(hostId: string) {
    if (this.hosts.has(hostId)) {
      this.hosts.delete(hostId);
    } else {
      this.hosts.add(hostId);
    }
    this.notify();
  },

  subscribe(listener: (hosts: Set<string>) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  },

  notify() {
    this.listeners.forEach((listener) => listener(new Set(this.hosts)));
  },
};

// ============================================================================
// Helper Functions
// ============================================================================

function formatLocalDateTime(dateString: string): string {
  if (!dateString) return "N/A";
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return "N/A";
  return date.toLocaleString();
}

// ============================================================================
// Skeleton Loader
// ============================================================================

function ContainersTableSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-neutral/20 bg-background shadow-sm dark:bg-neutral-900">
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="border-b border-neutral/20 bg-neutral/5">
              <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                Container/Group
              </th>
              <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                Image
              </th>
              <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                ID
              </th>
              <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                Last Seen
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral/10">
            {[1, 2, 3, 4, 5].map((i) => (
              <tr key={i}>
                <td className="px-md py-sm">
                  <div className="flex items-center gap-sm">
                    <div className="h-9 w-9 animate-pulse rounded-xl bg-neutral/20" />
                    <div className="space-y-2">
                      <div className="h-4 w-32 animate-pulse rounded bg-neutral/20" />
                      <div className="h-3 w-24 animate-pulse rounded bg-neutral/20" />
                    </div>
                  </div>
                </td>
                <td className="px-md py-sm">
                  <div className="h-4 w-24 animate-pulse rounded bg-neutral/20" />
                </td>
                <td className="px-md py-sm">
                  <div className="h-6 w-28 animate-pulse rounded bg-neutral/20" />
                </td>
                <td className="px-md py-sm">
                  <div className="h-4 w-32 animate-pulse rounded bg-neutral/20" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export const ContainersTable: React.FC<ContainersTableProps> = React.memo(
  ({
    containers,
    groups,
    isLoading = false,
    onContainerClick,
    onHostClick,
    authoritativeHostStatuses,
    monitoredByContainer = {},
  }) => {
    const [expandedHosts, setExpandedHosts] = useState<Set<string>>(
      expandedHostsStore.hosts
    );
    const hasInitiallyLoadedRef = useRef(false);

    // Subscribe to the persistent expanded hosts store
    useEffect(() => {
      const unsubscribe = expandedHostsStore.subscribe(setExpandedHosts);

      // Mark as initially loaded after first data load
      if (!hasInitiallyLoadedRef.current && containers.length > 0) {
        hasInitiallyLoadedRef.current = true;
      }

      return unsubscribe;
    }, [containers.length]);

    const toggleHost = (hostId: string) => {
      expandedHostsStore.toggle(hostId);
    };

    // Use hook for host status (2-minute stale threshold with lastSeen)
    const hostStatuses = useHostStatus(containers, authoritativeHostStatuses);

    if (isLoading) {
      return <ContainersTableSkeleton />;
    }

    // Group containers by host_id, sorted alphabetically
    const containersByHost = new Map<string, ContainerInfo[]>();
    containers.forEach((container) => {
      const hostId = container.host_id || "local";
      if (!containersByHost.has(hostId)) {
        containersByHost.set(hostId, []);
      }
      containersByHost.get(hostId)!.push(container);
    });

    // Sort hosts alphabetically
    const sortedHosts = Array.from(containersByHost.keys()).sort((a, b) =>
      a.localeCompare(b)
    );

    return (
      <div className="overflow-hidden rounded-xl border border-neutral/20 bg-background shadow-sm dark:bg-neutral-900">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="border-b border-neutral/20 bg-neutral/5">
                <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                  Host/Container
                </th>
                <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                  Image
                </th>
                <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                  ID
                </th>
                <th className="px-md py-sm text-left text-xs font-semibold uppercase tracking-wider text-neutral">
                  Last Seen
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral/10">
              {/* Render hosts with expandable containers */}
              {sortedHosts.map((hostId) => {
                const hostContainers = containersByHost.get(hostId) || [];
                const hostStatus = getHostStatus(hostStatuses, hostId);
                const isExpanded = expandedHosts.has(hostId);

                return (
                  <React.Fragment key={hostId}>
                    {/* Host header row */}
                    <tr
                      className="cursor-pointer border-b border-neutral/20 bg-neutral/10 transition-colors hover:bg-neutral/15 dark:bg-neutral-800/50"
                      onClick={() => toggleHost(hostId)}
                    >
                      <td className="px-md py-sm">
                        <div className="flex items-center">
                          <div className="mr-2xs rounded-md p-3xs transition-all hover:bg-neutral/20">
                            {isExpanded ? (
                              <ChevronDown className="h-5 w-5 text-neutral" />
                            ) : (
                              <ChevronRight className="h-5 w-5 text-neutral" />
                            )}
                          </div>
                          <div className="mr-sm rounded-xl bg-primary/10 p-2xs">
                            <Server className="h-5 w-5 text-primary" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-sm">
                              <span
                                className="truncate text-sm font-bold text-text hover:underline"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onHostClick?.(hostId);
                                }}
                              >
                                {hostId}
                              </span>
                              {/* Status Dot */}
                              <HostStatusDot
                                isOnline={hostStatus.isOnline}
                                lastSeen={hostStatus.lastSeen ?? undefined}
                                size="sm"
                              />
                            </div>
                            <div className="text-xs text-neutral">
                              {hostStatus.containerCount} container{hostStatus.containerCount !== 1 ? "s" : ""}
                              {hostStatus.runningCount > 0 && (
                                <span className="ml-xs text-success">
                                  ({hostStatus.runningCount} running)
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-md py-sm">
                        <span className="rounded-full bg-primary/10 px-2xs py-4xs text-xs font-medium text-primary">
                          Host
                        </span>
                      </td>
                      <td className="px-md py-sm">
                        <span className="text-neutral">-</span>
                      </td>
                      <td className="px-md py-sm">
                        <span className="text-neutral">-</span>
                      </td>
                    </tr>

                    {/* Host containers */}
                    {isExpanded &&
                      hostContainers.map((container) => (
                        <tr
                          key={container.identifier}
                          className={`bg-neutral/5 transition-colors hover:bg-neutral/10 ${
                            onContainerClick
                              ? "cursor-pointer hover:bg-primary/5"
                              : ""
                          }`}
                          onClick={
                            onContainerClick
                              ? () => onContainerClick(container)
                              : undefined
                          }
                        >
                          <td className="px-md py-sm">
                            <div className="ml-lg flex items-center">
                              <div className="mr-sm rounded-lg bg-primary/5 p-3xs">
                                <Container className="h-4 w-4 text-primary/70" />
                              </div>
                              <div className="min-w-0">
                                <div className="truncate text-sm font-medium text-text">
                                  {container.name}
                                </div>
                                <div className="truncate text-xs text-neutral">
                                  {container.identifier}
                                </div>
                                <LogCollectionBadge
                                  monitored={monitoredByContainer[container.identifier] ?? false}
                                  status={container.log_collection_status}
                                  issue={container.log_collection_issue}
                                  size="sm"
                                  className="mt-1"
                                />
                              </div>
                            </div>
                          </td>
                          <td className="px-md py-sm">
                            <div className="text-sm text-text">
                              {container.image_name || "N/A"}
                            </div>
                          </td>
                          <td className="px-md py-sm">
                            <div className="rounded bg-background px-2xs py-4xs font-mono text-sm text-neutral dark:bg-neutral-900">
                              {(container.docker_container_id || container.container_key).slice(0, 12)}...
                            </div>
                          </td>
                          <td className="px-md py-sm">
                            <div className="font-mono text-sm text-neutral">
                              {formatLocalDateTime(container.last_seen)}
                            </div>
                          </td>
                        </tr>
                      ))}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>

          {/* Empty state */}
          {containers.length === 0 && groups.length === 0 && (
            <div className="py-xl text-center">
              <div className="mx-auto mb-md flex h-20 w-20 items-center justify-center rounded-full bg-neutral/10">
                <Container className="h-10 w-10 text-neutral" />
              </div>
              <h3 className="mb-2xs text-base font-semibold text-text">
                No containers registered
              </h3>
              <p className="text-sm text-neutral">
                Connect your containers to the Unicron system to start
                monitoring.
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }
);

ContainersTable.displayName = "ContainersTable";

export default ContainersTable;
