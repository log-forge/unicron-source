/**
 * ContainerGrid Component
 *
 * Responsive grid view for displaying containers as cards.
 * Groups containers by host with collapsible sections.
 */

import React, { useState, useEffect } from "react";
import { Container } from "lucide-react";
import { ContainerCard } from "./ContainerCard";
import { HostSection } from "./HostSection";
import type { ContainerInfo, GroupInfo } from "./ContainersTable";
import { useHostStatus, getHostStatus } from "../../hooks/useHostStatus";

// ============================================================================
// Types
// ============================================================================

export interface ContainerGridProps {
  /** List of containers to display */
  containers: ContainerInfo[];
  /** List of container groups */
  groups: GroupInfo[];
  /** Loading state */
  isLoading?: boolean;
  /** Click handler for container card */
  onContainerClick?: (container: ContainerInfo) => void;
  /** Click handler for alert pill on container */
  onAlertClick?: (container: ContainerInfo) => void;
  /** Alert counts by container identifier */
  alertsByContainer?: Record<string, number>;
  /** Alert severity summaries by container identifier (keyed same as alertsByContainer) */
  alertSeverityByContainer?: Record<string, { highestSeverity: "critical" | "warning" | "info"; breakdown: { critical: number; warning: number; info: number } }>;
  /** Stack occurrences for single-alert containers (used for x2..x9+ display) */
  alertStackCountByContainer?: Record<string, number>;
  /** Monitored status by container identifier */
  monitoredByContainer?: Record<string, boolean>;
  /** Callback when monitoring status changes */
  onMonitoringChange?: (container: ContainerInfo, enabled: boolean) => void;
  /** Click handler for host section navigation */
  onHostClick?: (hostId: string) => void;
  /** Set of container identifiers currently being toggled */
  togglingContainers?: Set<string>;
  /** Callback when Manage Monitoring button is clicked */
  onManageMonitoring?: (hostId: string, containers: ContainerInfo[]) => void;
  /** When true, render containers in a flat grid without host grouping */
  disableHostGrouping?: boolean;
  /** Authoritative host online status from /containers/overview */
  authoritativeHostStatuses?: Record<string, { online: boolean; last_seen?: string }>;
}

// ============================================================================
// Persistent State Store for Expanded Hosts
// ============================================================================

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
// Skeleton Loader
// ============================================================================

function ContainerGridSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-md sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
      {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900"
        >
          {/* Icon and Name skeleton */}
          <div className="mb-sm flex items-start gap-sm">
            <div className="h-10 w-10 animate-pulse rounded-xl bg-neutral/20" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-24 animate-pulse rounded bg-neutral/20" />
              <div className="h-3 w-32 animate-pulse rounded bg-neutral/20" />
            </div>
          </div>
          {/* Status badge skeleton */}
          <div className="mb-sm">
            <div className="h-5 w-16 animate-pulse rounded-full bg-neutral/20" />
          </div>
          {/* Toggle skeleton */}
          <div className="mt-sm flex items-center justify-between border-t border-neutral/10 pt-sm">
            <div className="h-3 w-16 animate-pulse rounded bg-neutral/20" />
            <div className="h-5 w-9 animate-pulse rounded-full bg-neutral/20" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// Empty State
// ============================================================================

function EmptyState() {
  return (
    <div className="py-xl text-center">
      <div className="mx-auto mb-md flex h-20 w-20 items-center justify-center rounded-full bg-neutral/10">
        <Container className="h-10 w-10 text-neutral" />
      </div>
      <h3 className="mb-2xs text-base font-semibold text-text">
        No containers registered
      </h3>
      <p className="text-sm text-neutral">
        Connect your containers to the Unicron system to start monitoring.
      </p>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export const ContainerGrid: React.FC<ContainerGridProps> = React.memo(
  ({
    containers,
    groups,
    isLoading = false,
    onContainerClick,
    onAlertClick,
    alertsByContainer = {},
    alertSeverityByContainer,
    alertStackCountByContainer = {},
    monitoredByContainer = {},
    onMonitoringChange,
    onHostClick,
    togglingContainers = new Set(),
    onManageMonitoring,
    disableHostGrouping = false,
    authoritativeHostStatuses,
  }) => {
    const [expandedHosts, setExpandedHosts] = useState<Set<string>>(
      expandedHostsStore.hosts
    );

    // Subscribe to the persistent expanded hosts store
    useEffect(() => {
      const unsubscribe = expandedHostsStore.subscribe(setExpandedHosts);
      return unsubscribe;
    }, []);

    const toggleHost = (hostId: string) => {
      expandedHostsStore.toggle(hostId);
    };

    // Use hook for host status (2-minute stale threshold with lastSeen)
    const hostStatuses = useHostStatus(containers, authoritativeHostStatuses);

    if (isLoading) {
      return <ContainerGridSkeleton />;
    }

    if (containers.length === 0 && groups.length === 0) {
      return <EmptyState />;
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

    // Calculate host alert stats (status comes from hook)
    const getHostAlertCount = (hostContainers: ContainerInfo[]) => {
      return hostContainers.reduce(
        (sum, c) => sum + (alertsByContainer[c.identifier] ?? 0),
        0
      );
    };

    return (
      <div className="space-y-md">
        {disableHostGrouping ? (
          // Flat grid - no host grouping
          <div className="grid grid-cols-1 gap-md sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
            {containers.map((container) => (
              <ContainerCard
                key={container.identifier}
                container={container}
                onClick={() => onContainerClick?.(container)}
                onAlertClick={() => onAlertClick?.(container)}
                alertCount={alertsByContainer[container.identifier] ?? 0}
                alertSeverity={alertSeverityByContainer?.[container.identifier]?.highestSeverity}
                alertBreakdown={alertSeverityByContainer?.[container.identifier]?.breakdown}
                alertStackCount={alertStackCountByContainer[container.identifier]}
                status={container.status}
                isMonitored={monitoredByContainer[container.identifier] ?? false}
                onMonitoringChange={(enabled) => onMonitoringChange?.(container, enabled)}
                isToggling={togglingContainers.has(container.identifier)}
              />
            ))}
          </div>
        ) : (
          // Original host-grouped rendering
          sortedHosts.map((hostId) => {
            const hostContainers = containersByHost.get(hostId) || [];
            const hostStatus = getHostStatus(hostStatuses, hostId);
            const alertCount = getHostAlertCount(hostContainers);
            const isExpanded = expandedHosts.has(hostId);

            return (
              <div key={hostId} className="space-y-sm">
                {/* Host Section Header with Manage Monitoring Button */}
                <div className="flex items-center gap-sm">
                  <div className="flex-1">
                    <HostSection
                      hostId={hostId}
                      containerCount={hostStatus.containerCount}
                      runningCount={hostStatus.runningCount}
                      alertCount={alertCount}
                      isOnline={hostStatus.isOnline}
                      lastSeen={hostStatus.lastSeen}
                      isExpanded={isExpanded}
                      onToggle={() => toggleHost(hostId)}
                      onClick={onHostClick ? () => onHostClick(hostId) : undefined}
                    />
                  </div>
                  {onManageMonitoring && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onManageMonitoring(hostId, hostContainers);
                      }}
                      className="rounded-lg border border-neutral/20 bg-background px-3 py-1.5 text-xs font-medium text-text hover:bg-neutral/5 transition-colors"
                    >
                      Manage Monitoring
                    </button>
                  )}
                </div>

                {/* Host Containers Grid (shown when expanded) */}
                {isExpanded && (
                  <div className="ml-lg grid grid-cols-1 gap-md sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                    {hostContainers.map((container) => (
                      <ContainerCard
                        key={container.identifier}
                        container={container}
                        onClick={() => onContainerClick?.(container)}
                        onAlertClick={() => onAlertClick?.(container)}
                        alertCount={alertsByContainer[container.identifier] ?? 0}
                        alertSeverity={alertSeverityByContainer?.[container.identifier]?.highestSeverity}
                        alertBreakdown={alertSeverityByContainer?.[container.identifier]?.breakdown}
                        alertStackCount={alertStackCountByContainer[container.identifier]}
                        status={container.status}
                        isMonitored={monitoredByContainer[container.identifier] ?? false}
                        onMonitoringChange={(enabled) => onMonitoringChange?.(container, enabled)}
                        isToggling={togglingContainers.has(container.identifier)}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    );
  }
);

ContainerGrid.displayName = "ContainerGrid";

export default ContainerGrid;
