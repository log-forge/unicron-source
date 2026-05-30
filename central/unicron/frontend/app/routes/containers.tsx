/**
 * Containers Page
 *
 * Displays all monitored containers with expandable groups.
 * Supports both table and grid view modes with persistent preference.
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { data as routeData, redirect, useLoaderData, useNavigate, type ActionFunctionArgs, type LoaderFunctionArgs } from "react-router";
import { isAxiosError } from "axios";
import { List, LayoutGrid, Loader2 } from "lucide-react";
import { useAlertCounts } from "../hooks/useAlertCounts";
import { useContainerAlertSummary } from "../hooks/useContainerAlertSummary";
import { useContainerWebSocket } from "../hooks/useContainerWebSocket";
import type { ContainerEvent } from "../hooks/useContainerWebSocket";
import { ContainersTable, ContainerGrid, FilterSidebar, EmptyState } from "../components/containers";
import { TelemetryBanner } from "../components/containers/TelemetryBanner";
import { HostSelector } from "../components/containers/HostSelector";
import type { ContainerInfo, GroupInfo, FilterState } from "../components/containers";
import {
  mergeLogCollectionStateIntoContainers,
  type LogCollectionIssue,
  type LogCollectionStatus,
} from "../components/containers/logCollection";
import { OverviewDashboard } from "../components/dashboard";
import Toast from "../features/alert-engine/components/ui/Toast";
import { httpApp } from "../utils/http.client";
import { createServerHttpClient } from "../utils/http.server";
import { AppShellError } from "../components/library/errors";
import { normalizeReturnTo } from "../utils/auth/return-to";
import { changeLocalAdminPassword } from "../utils/auth/password-change.server";
import { withCsrfValidation } from "../utils/csrf/csrfWrapper.server";
import { dismissBootstrapPasswordNotice } from "../utils/cookies/bootstrap-password-notice.server";
import { removeHostFromContainersCache } from "../utils/containerRealtimeCache";

// ============================================================================
// Meta
// ============================================================================

export function meta() {
  return [
    { title: "Containers - Unicron" },
    { name: "description", content: "Monitored containers overview" },
  ];
}

// ============================================================================
// Types
// ============================================================================

type ViewMode = "table" | "grid";
type HostAvailabilityFilter = "live" | "all" | "disconnected";

interface ContainersApiResponse {
  hosts: Array<{
    host_id: string;
    online: boolean;
    container_count: number;
    last_seen?: string;
  }>;
  containers: Array<{
    container_key: string;
    docker_container_id?: string | null;
    name: string;
    status?: string;
    image?: string;
    host_id?: string;
    labels?: Record<string, string>;
    ports?: Record<string, any>;
    started_at?: string;
    log_collection_status?: LogCollectionStatus | null;
    log_collection_issue?: LogCollectionIssue | null;
  }>;
}

interface HostInfo {
  host_id: string;
  online: boolean;
  container_count: number;
  last_seen?: string;
}

interface ContainersResponse {
  containers: ContainerInfo[];
  groups: GroupInfo[];
  hosts: HostInfo[];
}

// ============================================================================
// API
// ============================================================================

function mapContainersResponse(payload: ContainersApiResponse): ContainersResponse {
  const mappedContainers: ContainerInfo[] = payload.containers.map((c) => ({
    identifier: c.container_key,
    name: c.name,
    container_key: c.container_key,
    docker_container_id: c.docker_container_id,
    status: c.status || "unknown",
    image_name: c.image || "",
    host_id: c.host_id || "local",
    labels: c.labels || {},
    ports: c.ports || {},
    started_at: c.started_at || "",
    last_seen: c.started_at || "",
    log_collection_status: c.log_collection_status ?? undefined,
    log_collection_issue: c.log_collection_issue ?? undefined,
  }));
  const hosts: HostInfo[] = (payload.hosts || []).map((h) => ({
    host_id: h.host_id,
    online: h.online,
    container_count: h.container_count,
    last_seen: h.last_seen,
  }));
  return { containers: mappedContainers, groups: [], hosts };
}

function redirectToSignIn(request: Request) {
  const url = new URL(request.url);
  const returnTo = url.pathname + url.search;
  const returnPath = returnTo.startsWith("/unicron") ? returnTo.slice("/unicron".length) || "/" : returnTo;
  const params = new URLSearchParams({
    returnTo: returnPath,
    reason: "reauth",
  });
  return redirect(`/sign-in?${params.toString()}`);
}

function getSafeReturnTo(form: FormData): string {
  return normalizeReturnTo(String(form.get("returnTo") ?? "/overview"));
}

function withBootstrapPasswordStatus(returnTo: string, status: "invalid" | "failed"): string {
  const url = new URL(returnTo, "http://unicron.local");
  url.searchParams.set("bootstrapPassword", status);
  return `${url.pathname}${url.search}${url.hash}`;
}

export async function loader({ request }: LoaderFunctionArgs) {
  try {
    const client = createServerHttpClient({ request });
    const response = await client.get<ContainersApiResponse>("/containers/overview");
    return routeData<ContainersResponse>(mapContainersResponse(response.data), { status: 200 });
  } catch (err) {
    if (isAxiosError(err)) {
      const status = err.response?.status;
      if (status === 401 || status === 403) {
        throw redirectToSignIn(request);
      }
    }
    throw err;
  }
}

export const action = withCsrfValidation(async ({ request }: ActionFunctionArgs) => {
  const form = await request.formData();
  const intent = form.get("_intent");
  const safeReturnTo = getSafeReturnTo(form);

  if (intent === "dismiss-bootstrap-password") {
    return redirect(safeReturnTo, {
      headers: {
        "Set-Cookie": await dismissBootstrapPasswordNotice(),
      },
    });
  }

  if (form.get("_intent") !== "bootstrap-password") {
    return routeData({ error: "Unsupported overview action." }, { status: 400 });
  }

  const currentPassword = String(form.get("currentPassword") ?? "");
  const newPassword = String(form.get("newPassword") ?? "");
  const result = await changeLocalAdminPassword(request, {
    currentPassword,
    newPassword,
    revokeOtherSessions: true,
    clearBootstrapNoticeDismissal: true,
  });

  if (!result.ok) {
    return redirect(withBootstrapPasswordStatus(safeReturnTo, result.kind));
  }

  return redirect(safeReturnTo, { headers: result.headers });
});

async function getContainers(): Promise<ContainersResponse> {
  const response = await httpApp.get<ContainersApiResponse>("/containers/overview");
  return mapContainersResponse(response.data);
}

// ============================================================================
// View Toggle Component
// ============================================================================

interface ViewToggleProps {
  viewMode: ViewMode;
  onViewChange: (mode: ViewMode) => void;
}

function ViewToggle({ viewMode, onViewChange }: ViewToggleProps) {
  return (
    <div className="flex items-center gap-xs rounded-lg border border-neutral/20 bg-background p-0.5 dark:bg-neutral-900">
      <button
        type="button"
        onClick={() => onViewChange("table")}
        className={`
          flex items-center justify-center rounded-md p-1.5 transition-colors
          ${
            viewMode === "table"
              ? "bg-primary/10 text-primary"
              : "text-neutral hover:bg-neutral/10 hover:text-text"
          }
        `}
        title="Table view"
        aria-label="Switch to table view"
        aria-pressed={viewMode === "table"}
      >
        <List className="h-5 w-5" />
      </button>
      <button
        type="button"
        onClick={() => onViewChange("grid")}
        className={`
          flex items-center justify-center rounded-md p-1.5 transition-colors
          ${
            viewMode === "grid"
              ? "bg-primary/10 text-primary"
              : "text-neutral hover:bg-neutral/10 hover:text-text"
          }
        `}
        title="Grid view"
        aria-label="Switch to grid view"
        aria-pressed={viewMode === "grid"}
      >
        <LayoutGrid className="h-5 w-5" />
      </button>
    </div>
  );
}

// ============================================================================
// Local Storage Helpers
// ============================================================================

const STORAGE_KEY = "containers-view";

function getStoredViewMode(): ViewMode {
  if (typeof window === "undefined") return "table";
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "grid" || stored === "table") return stored;
  return "table";
}

function setStoredViewMode(mode: ViewMode): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_KEY, mode);
  }
}

// ============================================================================
// Host Status Badges
// ============================================================================

function SyncingBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
      <Loader2 className="h-3 w-3 animate-spin" />
      Syncing...
    </span>
  );
}

function OfflineBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-neutral/10 px-2 py-0.5 text-xs font-medium text-neutral">
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-neutral/60" />
      Offline
    </span>
  );
}

interface HostAvailabilityFilterProps {
  value: HostAvailabilityFilter;
  onChange: (value: HostAvailabilityFilter) => void;
  hosts: HostInfo[];
}

function HostAvailabilityFilterControl({
  value,
  onChange,
  hosts,
}: HostAvailabilityFilterProps) {
  const liveCount = hosts.filter((host) => host.online).length;
  const disconnectedCount = hosts.length - liveCount;

  const options: Array<{
    key: HostAvailabilityFilter;
    label: string;
    count: number;
  }> = [
    { key: "live", label: "Live", count: liveCount },
    { key: "all", label: "All", count: hosts.length },
    { key: "disconnected", label: "Disconnected", count: disconnectedCount },
  ];

  return (
    <div className="inline-flex items-center rounded-lg border border-neutral/20 bg-background p-0.5 dark:bg-neutral-900">
      {options.map((option) => {
        const active = value === option.key;
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => onChange(option.key)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              active
                ? "bg-primary/10 text-primary"
                : "text-neutral hover:bg-neutral/10 hover:text-text"
            }`}
          >
            {option.label} ({option.count})
          </button>
        );
      })}
    </div>
  );
}

// ============================================================================
// Filter Logic
// ============================================================================

function applyFilters(containers: ContainerInfo[], filters: FilterState): ContainerInfo[] {
  return containers.filter((container) => {
    // Host filter
    if (filters.hosts.length > 0) {
      const hostId = container.host_id || "local";
      if (!filters.hosts.includes(hostId)) return false;
    }

    // Status filter
    if (filters.statuses.length > 0) {
      const status = container.status?.toLowerCase() || "unknown";
      const matchesRunning = filters.statuses.includes("running") && status === "running";
      const matchesStopped = filters.statuses.includes("stopped") &&
        (status === "stopped" || status === "exited");
      if (!matchesRunning && !matchesStopped) return false;
    }

    // Text search filter
    if (filters.searchText) {
      const search = filters.searchText.toLowerCase();
      const matchesName = container.name.toLowerCase().includes(search);
      const matchesId = container.identifier.toLowerCase().includes(search);
      const matchesImage = container.image_name?.toLowerCase().includes(search);
      if (!matchesName && !matchesId && !matchesImage) return false;
    }

    // Alert filter (requires alertsByContainer data)
    // Will be integrated when alerts data is available

    return true;
  });
}

// ============================================================================
// Component
// ============================================================================

export default function ContainersPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const initialOverview = useLoaderData<typeof loader>();
  const [viewMode, setViewMode] = useState<ViewMode>(() => getStoredViewMode());
  const [filters, setFilters] = useState<FilterState>({
    hosts: [],
    statuses: [],
    hasAlerts: null,
    searchText: "",
  });
  const [monitoringStates, setMonitoringStates] = useState<Record<string, boolean>>({});
  const [togglingContainers, setTogglingContainers] = useState<Set<string>>(new Set());
  const [errorToast, setErrorToast] = useState<string | null>(null);
  const [selectedHost, setSelectedHost] = useState<string | null>(null);
  const [hostAvailabilityFilter, setHostAvailabilityFilter] =
    useState<HostAvailabilityFilter>("live");

  const { data: containersData, error, isLoading, refetch } = useQuery({
    queryKey: ["containers"],
    queryFn: getContainers,
    initialData: initialOverview,
    staleTime: 10 * 1000,
    refetchOnMount: true,
  });

  // Auto-dismiss error toast after 5 seconds
  useEffect(() => {
    if (errorToast) {
      const timer = setTimeout(() => setErrorToast(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [errorToast]);

  const setMonitoringConfirmed = useCallback((containerId: string, enabled: boolean) => {
    setMonitoringStates((prev) => ({ ...prev, [containerId]: enabled }));
  }, []);

  const clearTogglingContainers = useCallback((containerIds: string[]) => {
    if (containerIds.length === 0) return;

    setTogglingContainers((prev) => {
      const next = new Set(prev);
      containerIds.forEach((containerId) => next.delete(containerId));
      return next;
    });
  }, []);

  const resolveLatestContainers = useCallback(
    async (sourceContainers: ContainerInfo[]) => {
      if (sourceContainers.length === 0) return sourceContainers;

      const latest = await queryClient.fetchQuery({
        queryKey: ["containers"],
        queryFn: getContainers,
        staleTime: 0,
      });
      const latestByKey = new Map<string, ContainerInfo>(
        latest.containers.map((container) => [
          `${container.host_id || "local"}:${container.name}`,
          container,
        ] as const)
      );

      return sourceContainers.map((container) => {
        const key = `${container.host_id || "local"}:${container.name}`;
        return latestByKey.get(key) ?? container;
      });
    },
    [queryClient]
  );

  // Fetch initial monitoring states when containers are available
  useEffect(() => {
    const fetchMonitoringStates = async () => {
      // Wait for containers to be loaded
      if (!containersData?.containers?.length) return;

      try {
        const response = await httpApp.get("/containers/monitoring-states");
        if (response.data?.states) {
          setMonitoringStates(response.data.states as Record<string, boolean>);
        }
      } catch (error) {
        console.error("Failed to fetch monitoring states:", error);
      }
    };
    fetchMonitoringStates();
  }, [containersData?.containers]);

  // Real-time WebSocket updates
  const handleWebSocketEvents = useCallback((events: ContainerEvent[]) => {
    for (const event of events) {
      if (event.type === "monitoring_state_changed") {
        const { container_key, monitoring_enabled } = event.data;
        setMonitoringConfirmed(container_key, monitoring_enabled);
        clearTogglingContainers([container_key]);
      } else if (event.type === "log_collection_state_changed") {
        queryClient.setQueryData<ContainersResponse>(["containers"], (old) => {
          if (!old) return old;
          return {
            ...old,
            containers: mergeLogCollectionStateIntoContainers(old.containers, event.data),
          };
        });
      } else if (event.type === "initial_state" && event.data?.monitoring_states) {
        setMonitoringStates(prev => ({ ...prev, ...event.data.monitoring_states }));
      } else if (event.type === "container_event") {
        const { container_key, docker_container_id, name, status, action, host_id } = event.data;
        queryClient.setQueryData<ContainersResponse>(["containers"], (old) => {
          if (!old) return old;
          const existing = old.containers.find((c) => c.container_key === container_key);
          if (existing) {
            // Update existing container status
            return {
              ...old,
              containers: old.containers.map((c) =>
                c.container_key === container_key
                  ? { ...c, status: status || action }
                  : c
              ),
            };
          }
          // New container - add to list
          const newContainer: ContainerInfo = {
            identifier: container_key,
            name: name || container_key,
            container_key,
            docker_container_id,
            status: status || "unknown",
            image_name: "",
            host_id: host_id || "local",
            labels: {},
            ports: {},
            started_at: "",
            last_seen: "",
          };
          return { ...old, containers: [...old.containers, newContainer] };
        });
      } else if (event.type === "inventory_update") {
        const { host_id: eventHostId, containers: eventContainers } = event.data;
        if (Array.isArray(eventContainers)) {
          queryClient.setQueryData<ContainersResponse>(["containers"], (old) => {
            if (!old) return old;
            // Remove old containers for this host, add new ones
            const otherContainers = old.containers.filter(
              (c) => (c.host_id || "local") !== eventHostId
            );
            const newContainers: ContainerInfo[] = eventContainers.map((c: any) => ({
              identifier: c.container_key,
              name: c.name || c.container_key,
              container_key: c.container_key,
              docker_container_id: c.docker_container_id,
              status: c.status || "unknown",
              image_name: c.image || "",
              host_id: eventHostId || "local",
              labels: c.labels || {},
              ports: c.ports || {},
              started_at: c.started_at || "",
              last_seen: c.started_at || "",
            }));
            return { ...old, containers: [...otherContainers, ...newContainers] };
          });
        }
      } else if (event.type === "host_status") {
        if (event.data?.removed === true && typeof event.data?.host_id === "string") {
          queryClient.setQueryData<ContainersResponse>(["containers"], (old) =>
            removeHostFromContainersCache(old, event.data.host_id)
          );
        }
        // Force immediate host-list refresh after applying the realtime projection.
        queryClient.invalidateQueries({ queryKey: ["containers"] });
      }
    }
  }, [clearTogglingContainers, queryClient, setMonitoringConfirmed]);

  const { connected } = useContainerWebSocket(handleWebSocketEvents);

  // Invalidate containers query when WebSocket reconnects
  useEffect(() => {
    if (connected) {
      // Small delay to let initial_state event arrive first
      const timer = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["containers"] });
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [connected, queryClient]);

  // Persist view mode to localStorage
  useEffect(() => {
    setStoredViewMode(viewMode);
  }, [viewMode]);

  const containers = containersData?.containers ?? [];
  const groups = containersData?.groups ?? [];
  const hosts = containersData?.hosts ?? [];

  // Alert counts from AlertStore (real-time via WebSocket)
  const { alertsPerContainer } = useAlertCounts();
  const alertSummaries = useContainerAlertSummary();

  // Bridge key format: AlertStore uses "host_id:container_name", ContainerGrid expects counts by container.identifier (container_key)
  const alertsByContainer = useMemo(() => {
    const result: Record<string, number> = {};
    for (const container of containers) {
      const containerKey = `${container.host_id || "local"}:${container.name}`;
      const count = alertsPerContainer.get(containerKey);
      if (count && count > 0) {
        result[container.identifier] = count;
      }
    }
    return result;
  }, [containers, alertsPerContainer]);

  // Bridge severity data: same composite key pattern, maps to container identifier
  const alertSeverityByContainer = useMemo(() => {
    const result: Record<string, { highestSeverity: "critical" | "warning" | "info"; breakdown: { critical: number; warning: number; info: number } }> = {};
    for (const container of containers) {
      const containerKey = `${container.host_id || "local"}:${container.name}`;
      const summary = alertSummaries.get(containerKey);
      if (summary && summary.totalCount > 0) {
        result[container.identifier] = {
          highestSeverity: summary.highestSeverity,
          breakdown: summary.breakdown,
        };
      }
    }
    return result;
  }, [containers, alertSummaries]);

  const alertStackCountByContainer = useMemo(() => {
    const result: Record<string, number> = {};
    for (const container of containers) {
      const containerKey = `${container.host_id || "local"}:${container.name}`;
      const summary = alertSummaries.get(containerKey);
      if (!summary) continue;

      if (summary.totalCount === 1 && summary.maxOccurrence > 1) {
        result[container.identifier] = summary.maxOccurrence;
      }
    }
    return result;
  }, [containers, alertSummaries]);

  const hostStatusMap = useMemo(() => {
    const map: Record<string, HostInfo> = {};
    hosts.forEach((h) => {
      map[h.host_id] = h;
    });
    return map;
  }, [hosts]);

  const visibleHosts = useMemo(() => {
    if (hostAvailabilityFilter === "all") return hosts;
    if (hostAvailabilityFilter === "live") {
      return hosts.filter((host) => host.online);
    }
    return hosts.filter((host) => !host.online);
  }, [hosts, hostAvailabilityFilter]);

  const visibleHostIds = useMemo(
    () => new Set(visibleHosts.map((host) => host.host_id)),
    [visibleHosts]
  );

  const availabilityFilteredContainers = useMemo(() => {
    // When host list is unavailable, keep backward-compatible behavior.
    if (hosts.length === 0 || hostAvailabilityFilter === "all") {
      return containers;
    }
    return containers.filter((container) =>
      visibleHostIds.has(container.host_id || "local")
    );
  }, [containers, hostAvailabilityFilter, hosts.length, visibleHostIds]);

  // Initialize selectedHost when hosts are first loaded
  useEffect(() => {
    if (visibleHosts.length > 1 && selectedHost === null) {
      const localHost = visibleHosts.find((host) => host.host_id === "local");
      const defaultHost = localHost || visibleHosts[0];
      if (defaultHost) {
        setSelectedHost(defaultHost.host_id);
      }
    }
  }, [visibleHosts, selectedHost]);

  // Clear selection if the selected host disappears after decommission/removal.
  useEffect(() => {
    if (!selectedHost) return;
    const stillExists = visibleHosts.some((host) => host.host_id === selectedHost);
    if (!stillExists) {
      setSelectedHost(null);
    }
  }, [visibleHosts, selectedHost]);

  // Derive unique hosts from host data (or from containers as fallback)
  const uniqueHosts = useMemo(() => {
    if (visibleHosts.length > 0) {
      return visibleHosts.map((h) => h.host_id);
    }
    const hostSet = new Set<string>();
    availabilityFilteredContainers.forEach((container) => {
      hostSet.add(container.host_id || "local");
    });
    return Array.from(hostSet);
  }, [visibleHosts, availabilityFilteredContainers]);

  // Calculate container counts by host
  const containerCountsByHost = useMemo(() => {
    const counts: Record<string, number> = {};
    availabilityFilteredContainers.forEach((container) => {
      const hostId = container.host_id || "local";
      counts[hostId] = (counts[hostId] || 0) + 1;
    });
    return counts;
  }, [availabilityFilteredContainers]);

  // Apply host selection filter (only when multiple hosts exist)
  const hostFilteredContainers = useMemo(() => {
    if (visibleHosts.length <= 1) {
      // Single host or no hosts: show all containers (backward compatible)
      return availabilityFilteredContainers;
    }
    if (selectedHost === null) {
      // No host selected yet: show all containers
      return availabilityFilteredContainers;
    }
    // Filter containers by selected host
    return availabilityFilteredContainers.filter(
      (c) => (c.host_id || "local") === selectedHost
    );
  }, [availabilityFilteredContainers, visibleHosts.length, selectedHost]);

  // Apply additional filters to host-filtered containers
  const filteredContainers = useMemo(
    () => applyFilters(hostFilteredContainers, filters),
    [hostFilteredContainers, filters]
  );

  // Memoized filter change handler to prevent infinite loops
  const handleFilterChange = useCallback((newFilters: FilterState) => {
    setFilters(newFilters);
  }, []);

  const handleContainerClick = (container: ContainerInfo) => {
    const returnTo = encodeURIComponent("/overview");
    navigate(`/containers/${container.identifier}?returnTo=${returnTo}`);
  };

  const handleAlertClick = (container: ContainerInfo) => {
    // Navigate to container's Alerts tab
    const returnTo = encodeURIComponent("/overview");
    navigate(`/containers/${container.identifier}?tab=alerts&returnTo=${returnTo}`);
  };

  const handleMonitoringChange = async (container: ContainerInfo, enabled: boolean) => {
    let targetContainer = container;
    try {
      const [latestContainer] = await resolveLatestContainers([container]);
      if (latestContainer) {
        targetContainer = latestContainer;
      }
    } catch (error) {
      console.error("Failed to refresh container inventory before toggling monitoring:", error);
    }

    const containerId = targetContainer.identifier;
    const hostId = targetContainer.host_id || "local";

    setTogglingContainers((prev) => new Set(prev).add(containerId));

    try {
      const response = await httpApp.post(
        `/containers/${encodeURIComponent(containerId)}/monitoring?host_id=${encodeURIComponent(hostId)}`,
        { enabled }
      );

      const confirmedId = response.data?.container_key || containerId;
      const confirmedState = response.data?.monitoring_enabled ?? enabled;
      setMonitoringConfirmed(confirmedId, confirmedState);
      clearTogglingContainers([containerId, confirmedId]);
    } catch (error: any) {
      clearTogglingContainers([containerId]);

      const message = error?.response?.data?.detail || "Failed to toggle monitoring";
      if (
        error?.response?.status === 404 &&
        message === "Container not found in inventory"
      ) {
        await queryClient.invalidateQueries({ queryKey: ["containers"] });
        setErrorToast(
          "This container restarted and is no longer in the current inventory. The list was refreshed."
        );
        return;
      }

      setErrorToast(message);
    }
  };

  const handleHostClick = (hostId: string) => {
    navigate(`/containers/host/${encodeURIComponent(hostId)}`);
  };

  const handleCreateLocalAgent = () => {
    navigate("/settings/agents?enroll=local");
  };

  const handleCreateRemoteAgent = () => {
    navigate("/settings/agents?enroll=remote");
  };

  // Determine page state
  const hasNoHosts = !isLoading && hosts.length === 0 && containers.length === 0;
  const hasNoHostsForFilter =
    !isLoading &&
    !hasNoHosts &&
    visibleHosts.length === 0 &&
    hosts.length > 0;

  if (error && !containersData) {
    return (
      <AppShellError
        error={error}
        title="Unable to load containers"
        message="We couldn't refresh the container inventory right now. Please try again."
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="flex w-full flex-col gap-lg">
      {/* Dashboard Stats */}
      <OverviewDashboard hosts={hosts} containers={containers} onHostClick={handleHostClick} />

      {/* Telemetry Health Banner */}
      <TelemetryBanner />

      {/* Host Availability + Selector */}
      {hosts.length > 0 && (
        <div className="flex flex-col gap-sm sm:flex-row sm:items-center sm:justify-between">
          <HostAvailabilityFilterControl
            value={hostAvailabilityFilter}
            onChange={setHostAvailabilityFilter}
            hosts={hosts}
          />
          {visibleHosts.length > 1 && (
            <HostSelector
              hosts={visibleHosts}
              selectedHost={selectedHost}
              onHostChange={setSelectedHost}
            />
          )}
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col gap-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-xs">
          <h1 className="text-2xl font-bold text-text">Containers</h1>
          <p className="text-sm text-neutral">
            View and manage monitored container instances.
          </p>
        </div>
        <div className="flex items-center gap-sm">
          <div className="flex items-center gap-xs text-xs">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                connected ? "bg-green-500" : "bg-neutral/40"
              }`}
            />
            <span className={connected ? "text-green-600 dark:text-green-400" : "text-neutral"}>
              {connected ? "Live" : "Connecting..."}
            </span>
          </div>
          <ViewToggle viewMode={viewMode} onViewChange={setViewMode} />
        </div>
      </div>

      {/* Empty State: No hosts connected */}
      {hasNoHosts && (
        <EmptyState
          onCreateLocalAgent={handleCreateLocalAgent}
          onCreateRemoteAgent={handleCreateRemoteAgent}
        />
      )}

      {hasNoHostsForFilter && (
        <div className="rounded-lg border border-neutral/20 bg-neutral/5 px-sm py-sm text-sm text-neutral">
          No {hostAvailabilityFilter} hosts match the current view. Switch host filter to{" "}
          <button
            type="button"
            onClick={() => setHostAvailabilityFilter("all")}
            className="font-medium text-primary hover:underline"
          >
            All
          </button>{" "}
          to inspect offline hosts.
        </div>
      )}

      {/* Host Status Badges (syncing / offline) */}
      {!hasNoHosts && visibleHosts.length > 0 && (
        <div className="flex flex-wrap gap-sm">
          {visibleHosts.map((host) => {
            const isSyncing = host.online && host.container_count === 0;
            const isOffline = !host.online;
            if (!isSyncing && !isOffline) return null;
            return (
              <div
                key={host.host_id}
                className={`flex items-center gap-xs rounded-lg border border-neutral/20 px-sm py-2xs ${
                  isOffline ? "opacity-50" : ""
                }`}
              >
                <span className="text-xs font-medium text-text">{host.host_id}</span>
                {isSyncing && <SyncingBadge />}
                {isOffline && <OfflineBadge />}
              </div>
            );
          })}
        </div>
      )}

      {/* Main Content with Filter Sidebar */}
      {!hasNoHosts && !hasNoHostsForFilter && (
        <div className="flex gap-md">
          <FilterSidebar
            hosts={uniqueHosts}
            onFilterChange={handleFilterChange}
            containerCounts={containerCountsByHost}
          />
          <div className="flex-1 min-w-0">
            {/* Offline host overlay for containers */}
            {viewMode === "table" ? (
              <ContainersTable
                containers={filteredContainers}
                groups={groups}
                isLoading={isLoading}
                onContainerClick={handleContainerClick}
                onHostClick={handleHostClick}
                monitoredByContainer={monitoringStates}
                authoritativeHostStatuses={hostStatusMap}
              />
            ) : (
              <ContainerGrid
                containers={filteredContainers}
                groups={groups}
                isLoading={isLoading}
                onContainerClick={handleContainerClick}
                onAlertClick={handleAlertClick}
                alertsByContainer={alertsByContainer}
                alertSeverityByContainer={alertSeverityByContainer}
                alertStackCountByContainer={alertStackCountByContainer}
                onMonitoringChange={handleMonitoringChange}
                onHostClick={handleHostClick}
                monitoredByContainer={monitoringStates}
                togglingContainers={togglingContainers}
                authoritativeHostStatuses={hostStatusMap}
              />
            )}

            {/* Per-host offline overlay: grey out containers from offline hosts */}
            {visibleHosts.some((h) => !h.online) && filteredContainers.length > 0 && (
              <style>{`
                ${visibleHosts
                  .filter((h) => !h.online)
                  .map((h) => `[data-host-id="${h.host_id}"]`)
                  .join(", ")} {
                  opacity: 0.5;
                  pointer-events: none;
                }
              `}</style>
            )}
          </div>
        </div>
      )}

      {/* Error Toast */}
      {errorToast && (
        <Toast
          variant="error"
          message={errorToast}
          onClose={() => setErrorToast(null)}
          position="bottom-right"
        />
      )}
    </div>
  );
}
