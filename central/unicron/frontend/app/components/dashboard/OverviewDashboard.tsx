/**
 * Overview Dashboard Component
 *
 * Displays summary statistics and host overview for the containers page.
 * Shows: hosts online, containers count, running/stopped counts.
 * Receives data as props from the parent containers page (single query source).
 */

import {
  Server,
  Container,
  PlayCircle,
  StopCircle,
  ChevronRight,
} from "lucide-react";
import type { ContainerInfo } from "../containers";

// ============================================================================
// Types
// ============================================================================

interface HostInfo {
  host_id: string;
  online: boolean;
  container_count: number;
  last_seen?: string;
}

interface OverviewDashboardProps {
  hosts: HostInfo[];
  containers: ContainerInfo[];
  onHostClick?: (hostId: string) => void;
}

interface HostStats {
  hostId: string;
  containerCount: number;
  runningCount: number;
  online: boolean;
}

// ============================================================================
// Helper Functions
// ============================================================================

function calculateHostStats(containers: ContainerInfo[], hosts: HostInfo[]): HostStats[] {
  const hostMap = new Map<string, HostStats>();

  // Initialize from host data
  hosts.forEach((h) => {
    hostMap.set(h.host_id, {
      hostId: h.host_id,
      containerCount: 0,
      runningCount: 0,
      online: h.online,
    });
  });

  // Count containers per host
  containers.forEach((container) => {
    const hostId = container.host_id || "local";
    const existing = hostMap.get(hostId);
    const isRunning = container.status === "running";

    if (existing) {
      existing.containerCount += 1;
      if (isRunning) existing.runningCount += 1;
    } else {
      hostMap.set(hostId, {
        hostId,
        containerCount: 1,
        runningCount: isRunning ? 1 : 0,
        // Never infer online from container runtime state.
        // Host presence is authoritative from backend host status.
        online: false,
      });
    }
  });

  return Array.from(hostMap.values()).sort(
    (a, b) => b.containerCount - a.containerCount
  );
}

// ============================================================================
// Stat Card Component
// ============================================================================

interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  iconBgClass: string;
}

function StatCard({
  label,
  value,
  subtitle,
  icon,
  iconBgClass,
}: StatCardProps) {
  return (
    <div className="group rounded-xl border border-neutral/20 bg-background p-md shadow-sm transition-all duration-200 hover:shadow-md dark:bg-neutral-900">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral">
            {label}
          </p>
          <p className="mt-2xs text-2xl font-bold text-text">{value}</p>
          {subtitle && (
            <p className="mt-3xs text-xs text-neutral">{subtitle}</p>
          )}
        </div>
        <div
          className={`rounded-xl p-sm transition-all duration-300 ${iconBgClass}`}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Host Card Component
// ============================================================================

interface HostCardProps {
  host: HostStats;
  onClick: () => void;
}

function HostCard({ host, onClick }: HostCardProps) {
  return (
    <button
      onClick={onClick}
      className={`group flex w-full items-center justify-between rounded-lg border border-neutral/20 bg-background p-sm transition-all hover:border-primary/30 hover:bg-primary/5 dark:bg-neutral-900 ${
        !host.online ? "opacity-50" : ""
      }`}
    >
      <div className="flex items-center gap-sm">
        <div className={`rounded-lg p-2xs ${host.online ? "bg-primary/10" : "bg-neutral/10"}`}>
          <Server className={`h-5 w-5 ${host.online ? "text-primary" : "text-neutral"}`} />
        </div>
        <div className="text-left">
          <div className="flex items-center gap-xs">
            <p className="text-sm font-semibold text-text">{host.hostId}</p>
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                host.online ? "bg-green-500" : "bg-neutral/40"
              }`}
            />
          </div>
          <p className="text-xs text-neutral">
            {host.containerCount} container{host.containerCount !== 1 ? "s" : ""}
            {host.runningCount > 0 && (
              <span className="ml-xs text-success">
                ({host.runningCount} running)
              </span>
            )}
          </p>
        </div>
      </div>
      <ChevronRight className="h-4 w-4 text-neutral transition-transform group-hover:translate-x-1 group-hover:text-primary" />
    </button>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function OverviewDashboard({ hosts, containers, onHostClick }: OverviewDashboardProps) {
  const hostStats = calculateHostStats(containers, hosts);

  // Calculate live stats from currently online hosts when host metadata is available.
  const hasHostMetadata = hosts.length > 0;
  const onlineHostIds = new Set(hosts.filter((h) => h.online).map((h) => h.host_id));
  const liveContainers = hasHostMetadata
    ? containers.filter((c) => onlineHostIds.has(c.host_id || "local"))
    : containers;
  const staleContainers = hasHostMetadata ? Math.max(0, containers.length - liveContainers.length) : 0;

  const totalContainers = liveContainers.length;
  const runningContainers = liveContainers.filter((c) => c.status === "running").length;
  const stoppedContainers = liveContainers.filter(
    (c) => c.status === "exited" || c.status === "stopped"
  ).length;
  const onlineHosts = hosts.filter((h) => h.online).length;
  const totalHosts = hosts.length || hostStats.length;

  return (
    <div className="space-y-md">
      {/* Summary Stats Cards */}
      <div className="grid grid-cols-1 gap-md sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Hosts Online"
          value={`${onlineHosts}/${totalHosts}`}
          subtitle={totalHosts === 0 ? "No hosts" : `${totalHosts} total`}
          icon={<Server className="h-6 w-6 text-primary" />}
          iconBgClass="bg-primary/10"
        />

        <StatCard
          label="Containers"
          value={totalContainers}
          subtitle={
            staleContainers > 0
              ? `${runningContainers} running • ${staleContainers} stale (offline hosts)`
              : `${runningContainers} running`
          }
          icon={<Container className="h-6 w-6 text-success" />}
          iconBgClass="bg-success/10"
        />

        <StatCard
          label="Running"
          value={runningContainers}
          subtitle={onlineHosts === 0 && staleContainers > 0 ? "Live data unavailable (hosts offline)" : "Active containers"}
          icon={<PlayCircle className="h-6 w-6 text-success" />}
          iconBgClass="bg-success/10"
        />

        <StatCard
          label="Stopped"
          value={stoppedContainers}
          subtitle={onlineHosts === 0 && staleContainers > 0 ? "Live data unavailable (hosts offline)" : "Exited containers"}
          icon={<StopCircle className="h-6 w-6 text-neutral" />}
          iconBgClass="bg-neutral/10"
        />
      </div>

      {/* Hosts Overview Section */}
      {hostStats.length > 0 && (
        <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
          <h3 className="mb-sm text-base font-semibold text-text">
            Hosts Overview
          </h3>
          <div className="grid grid-cols-1 gap-sm sm:grid-cols-2 lg:grid-cols-3">
            {hostStats.map((host) => (
              <HostCard
                key={host.hostId}
                host={host}
                onClick={() => onHostClick?.(host.hostId)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
