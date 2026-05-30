/**
 * Overview Tab Component
 *
 * Displays real-time container metrics and container information.
 * Uses on-demand stats streaming: stats only flow while this tab is visible.
 * Opening the container detail page triggers start_stats on the agent;
 * navigating away triggers stop_stats (no wasted resources).
 */

import type { ElementType, ReactNode } from "react";
import { Cpu, MemoryStick, HardDrive, Network, CheckCircle, XCircle } from "lucide-react";
import { useContainerStats } from "~/hooks/useContainerStats";
import type { ContainerInfo } from "~/components/containers";

// ============================================================================
// Types
// ============================================================================

interface OverviewTabProps {
  containerName: string;
  hostId: string | null;
  container?: ContainerInfo & {
    status?: string;
    image?: string;
    created?: number;
    started_at?: string;
    restart_count?: number;
    health_status?: string;
    failing_streak?: number;
    ports?: Record<string, { HostIp: string; HostPort: string }[]>;
    networks?: Record<string, unknown>;
    mounts?: Array<{
      Type: string;
      Source: string;
      Destination: string;
      Mode: string;
    }>;
    env?: string[];
  };
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (!bytes || isNaN(bytes)) return "N/A";

  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function formatRate(bytesPerSec: number | undefined): string {
  if (bytesPerSec === undefined || bytesPerSec === null || isNaN(bytesPerSec)) return "";
  if (bytesPerSec === 0) return "0 B/s";

  const k = 1024;
  const sizes = ["B/s", "KB/s", "MB/s", "GB/s"];
  const i = Math.floor(Math.log(bytesPerSec) / Math.log(k));
  const clampedI = Math.min(i, sizes.length - 1);

  return `${parseFloat((bytesPerSec / Math.pow(k, clampedI)).toFixed(1))} ${sizes[clampedI]}`;
}


function formatDate(value: number | string | null | undefined): string {
  if (!value) return "N/A";

  // Handle Unix timestamp (seconds)
  const date =
    typeof value === "number"
      ? new Date(value > 1e12 ? value : value * 1000)
      : new Date(value);

  if (isNaN(date.getTime())) return "N/A";

  return date.toLocaleString();
}

// ============================================================================
// Helper Components
// ============================================================================

interface StatCardProps {
  icon: ElementType;
  label: string;
  value: ReactNode;
  color?: string;
  loading?: boolean;
}

function StatCard({
  icon: Icon,
  label,
  value,
  color = "text-text",
  loading = false,
}: StatCardProps) {
  return (
    <div className="rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
      <div className="flex items-start gap-sm">
        <div className={`rounded-lg bg-background p-sm shrink-0 ${color}`}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm text-neutral">{label}</div>
          <div className="mt-2xs text-text">
            {loading ? (
              <span className="inline-flex items-center gap-xs text-neutral">
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                Loading
              </span>
            ) : (
              value ?? "N/A"
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface InfoRowProps {
  label: string;
  value: ReactNode;
  mono?: boolean;
}

function InfoRow({ label, value, mono = false }: InfoRowProps) {
  return (
    <div className="flex flex-col gap-2xs">
      <span className="text-xs uppercase text-neutral">{label}</span>
      <span className={`text-sm text-text ${mono ? "font-mono" : ""}`}>
        {value}
      </span>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function OverviewTab({
  containerName,
  hostId,
  container,
}: OverviewTabProps) {
  const resolvedContainerId = container?.container_key ?? "";
  const resolvedHostId = hostId ?? "";

  // On-demand stats streaming: connects only while this tab is visible
  const { stats, connected, loading } = useContainerStats(
    resolvedContainerId,
    resolvedHostId
  );

  // Derive display state from hook return values
  const metricsState: "loading" | "ready" | "offline" =
    loading ? "loading" : stats ? "ready" : connected ? "loading" : "offline";

  if (!container) {
    return (
      <div className="flex h-64 w-full items-center justify-center">
        <p className="text-neutral">Loading container data...</p>
      </div>
    );
  }

  // Parse ports - handle both Docker API format (array) and Docker inspect format (object)
  const ports = (() => {
    if (!container.ports) return [];

    // If ports is an array (Docker API format: [{PrivatePort, PublicPort, Type}])
    if (Array.isArray(container.ports)) {
      return container.ports.map((p: { PrivatePort?: number; PublicPort?: number; Type?: string }) => ({
        container: `${p.PrivatePort || "?"}/${p.Type || "tcp"}`,
        host: p.PublicPort ? String(p.PublicPort) : "N/A",
      }));
    }

    // If ports is an object (Docker inspect format: {"80/tcp": [{HostIp, HostPort}]})
    if (typeof container.ports === "object") {
      return Object.entries(container.ports).map(([containerPort, hostBindings]) => ({
        container: containerPort,
        host:
          Array.isArray(hostBindings) && hostBindings.length > 0
            ? (hostBindings[0] as { HostPort?: string }).HostPort || "N/A"
            : "N/A",
      }));
    }

    return [];
  })();

  // Parse environment variables
  const envVars = container.env || [];

  // Parse networks
  const networks = container.networks ? Object.keys(container.networks) : [];

  // Parse volumes
  const volumes = container.mounts || [];

  return (
    <div className="flex flex-col gap-md">
      {/* Stats Cards - Real-time on-demand metrics */}
      {metricsState === "loading" && (
        <div className="flex items-center justify-center gap-sm rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm text-neutral">Connecting to agent...</span>
        </div>
      )}
      {metricsState === "offline" && (
        <div className="flex items-center justify-center gap-sm rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
          <span className="text-sm text-neutral">Agent offline - stats unavailable</span>
        </div>
      )}
      <div className="grid grid-cols-1 gap-md md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={Cpu}
          label="CPU Usage"
          loading={metricsState === "loading"}
          value={
            metricsState === "ready" && stats && stats.cpu_percent != null ? (
              <div>
                <span className="text-lg font-semibold">
                  {stats.cpu_percent.toFixed(2)}%
                </span>
                <div className="mt-xs h-1.5 w-full rounded-full bg-neutral/20">
                  <div
                    className="h-1.5 rounded-full bg-primary transition-all duration-300"
                    style={{ width: `${Math.min(stats.cpu_percent, 100)}%` }}
                  />
                </div>
              </div>
            ) : (
              "N/A"
            )
          }
          color="text-primary"
        />
        <StatCard
          icon={MemoryStick}
          label="Memory Usage"
          loading={metricsState === "loading"}
          value={
            metricsState === "ready" && stats && stats.memory_usage != null ? (
              <div>
                <span className="text-lg font-semibold">
                  {formatBytes(stats.memory_usage)}
                  {stats.memory_limit != null && stats.memory_limit > 0 &&
                    ` / ${formatBytes(stats.memory_limit)}`}
                </span>
                {stats.memory_percent != null && (
                  <span className="ml-xs text-xs text-neutral">
                    ({stats.memory_percent.toFixed(1)}%)
                  </span>
                )}
                <div className="mt-xs h-1.5 w-full rounded-full bg-neutral/20">
                  <div
                    className="h-1.5 rounded-full bg-success transition-all duration-300"
                    style={{ width: `${Math.min(stats.memory_percent ?? 0, 100)}%` }}
                  />
                </div>
              </div>
            ) : (
              "N/A"
            )
          }
          color="text-success"
        />
        <StatCard
          icon={HardDrive}
          label="Block I/O"
          loading={metricsState === "loading"}
          value={
            metricsState === "ready" && stats && stats.block_read_bytes != null ? (
              <div>
                <span className="text-lg font-semibold">
                  R: {formatBytes(stats.block_read_bytes)} / W:{" "}
                  {formatBytes(stats.block_write_bytes ?? 0)}
                </span>
                {(stats.block_read_bps != null || stats.block_write_bps != null) && (
                  <div className="mt-2xs text-xs text-neutral">
                    {formatRate(stats.block_read_bps)} / {formatRate(stats.block_write_bps)}
                  </div>
                )}
              </div>
            ) : (
              "N/A"
            )
          }
          color="text-warning"
        />
        <StatCard
          icon={Network}
          label="Network I/O"
          loading={metricsState === "loading"}
          value={
            metricsState === "ready" && stats && stats.network_rx_bytes != null ? (
              <div>
                <span className="text-lg font-semibold">
                  RX: {formatBytes(stats.network_rx_bytes)} / TX:{" "}
                  {formatBytes(stats.network_tx_bytes ?? 0)}
                </span>
                {(stats.network_rx_rate_bps != null || stats.network_tx_rate_bps != null) && (
                  <div className="mt-2xs text-xs text-neutral">
                    {formatRate(stats.network_rx_rate_bps)} / {formatRate(stats.network_tx_rate_bps)}
                  </div>
                )}
              </div>
            ) : (
              "N/A"
            )
          }
          color="text-accent"
        />
      </div>

      {/* Container Information */}
      <section className="rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
        <h2 className="mb-md text-base font-semibold text-text">
          Container Information
        </h2>
        <div className="grid grid-cols-1 gap-md md:grid-cols-2">
          <InfoRow
            label="Container ID"
            value={container.container_key || "N/A"}
            mono
          />
          <InfoRow
            label="Image"
            value={container.image || container.image_name || "N/A"}
          />
          <InfoRow label="Status" value={container.status || "N/A"} />
          <InfoRow label="Created" value={formatDate(container.created)} />
          <InfoRow label="Started" value={formatDate(container.started_at)} />
          <InfoRow
            label="Restart Count"
            value={container.restart_count?.toString() || "0"}
          />
        </div>
      </section>

      {/* Health Check */}
      {container.health_status && (
        <section className="rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
          <h2 className="mb-md flex items-center gap-xs text-base font-semibold text-text">
            {container.health_status === "healthy" ? (
              <CheckCircle className="h-5 w-5 text-success" />
            ) : (
              <XCircle className="h-5 w-5 text-error" />
            )}
            Health Check
          </h2>
          <div className="grid grid-cols-1 gap-md md:grid-cols-2">
            <InfoRow label="Status" value={container.health_status} />
            <InfoRow
              label="Failing Streak"
              value={container.failing_streak?.toString() || "0"}
            />
          </div>
        </section>
      )}

      {/* Port Mappings */}
      {ports.length > 0 && (
        <section className="rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
          <h2 className="mb-md text-base font-semibold text-text">
            Port Mappings
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-neutral/20 text-xs uppercase text-neutral">
                <tr>
                  <th className="px-md py-sm">Container Port</th>
                  <th className="px-md py-sm">Host Port</th>
                </tr>
              </thead>
              <tbody>
                {ports.map((port, idx) => (
                  <tr key={idx} className="border-b border-neutral/10">
                    <td className="px-md py-sm font-mono text-text">
                      {port.container}
                    </td>
                    <td className="px-md py-sm font-mono text-text">
                      {port.host}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Networks */}
      {networks.length > 0 && (
        <section className="rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
          <h2 className="mb-md text-base font-semibold text-text">Networks</h2>
          <div className="flex flex-wrap gap-xs">
            {networks.map((network, idx) => (
              <span
                key={idx}
                className="rounded-full bg-primary/10 px-sm py-2xs text-sm text-primary"
              >
                {network}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Volumes & Mounts */}
      {volumes.length > 0 && (
        <section className="rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
          <h2 className="mb-md text-base font-semibold text-text">
            Volumes & Mounts
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-neutral/20 text-xs uppercase text-neutral">
                <tr>
                  <th className="px-md py-sm">Type</th>
                  <th className="px-md py-sm">Source</th>
                  <th className="px-md py-sm">Destination</th>
                  <th className="px-md py-sm">Mode</th>
                </tr>
              </thead>
              <tbody>
                {volumes.map((volume, idx) => (
                  <tr key={idx} className="border-b border-neutral/10">
                    <td className="px-md py-sm text-text">
                      {volume.Type || "N/A"}
                    </td>
                    <td className="px-md py-sm font-mono text-sm text-text">
                      {volume.Source || "N/A"}
                    </td>
                    <td className="px-md py-sm font-mono text-sm text-text">
                      {volume.Destination || "N/A"}
                    </td>
                    <td className="px-md py-sm text-text">
                      {volume.Mode || "N/A"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Environment Variables */}
      {envVars.length > 0 && (
        <section className="rounded-lg border border-neutral/20 bg-neutral/5 p-md dark:bg-neutral-800/50">
          <h2 className="mb-md text-base font-semibold text-text">
            Environment Variables
          </h2>
          <div className="max-h-96 overflow-y-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 border-b border-neutral/20 bg-neutral/5 text-xs uppercase text-neutral dark:bg-neutral-800/50">
                <tr>
                  <th className="px-md py-sm">Variable</th>
                  <th className="px-md py-sm">Value</th>
                </tr>
              </thead>
              <tbody>
                {envVars.map((envVar, idx) => {
                  const [key, ...valueParts] = envVar.split("=");
                  const value = valueParts.join("=");
                  return (
                    <tr key={idx} className="border-b border-neutral/10">
                      <td className="px-md py-sm font-mono text-sm text-text">
                        {key}
                      </td>
                      <td className="px-md py-sm font-mono text-sm text-neutral">
                        {value || "(empty)"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
