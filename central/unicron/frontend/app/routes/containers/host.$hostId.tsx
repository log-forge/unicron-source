/**
 * Host Detail Page
 *
 * Shows all containers for a specific host with:
 * - Breadcrumb navigation (Containers > host-name)
 * - Host header with status and stats
 * - Container grid filtered to this host
 * - Back button navigation
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ArrowLeft, Server, Layers, ChevronDown, Plus, Trash2, Pencil, Shield, AlertTriangle } from "lucide-react";
import { ContainerCard } from "../../components/containers/ContainerCard";
import type { ContainerInfo, GroupInfo } from "../../components/containers";
import { useAlertCounts } from "../../hooks/useAlertCounts";
import { useContainerAlertSummary } from "../../hooks/useContainerAlertSummary";
import { useContainerWebSocket } from "../../hooks/useContainerWebSocket";
import type { ContainerEvent } from "../../hooks/useContainerWebSocket";
import {
  mergeLogCollectionStateIntoContainers,
  type LogCollectionIssue,
  type LogCollectionStatus,
} from "../../components/containers/logCollection";
import { httpApp } from "../../utils/http.client";
import { apiService } from "../../features/alert-engine/services/api";
import Toast from "../../features/alert-engine/components/ui/Toast";
import PushTelemetryGuide from "../../components/settings/PushTelemetryGuide";
import { AppShellError } from "../../components/library/errors";

// ============================================================================
// Meta
// ============================================================================

export function meta({ params }: { params: { hostId: string } }) {
  const hostId = decodeURIComponent(params.hostId);
  return [
    { title: `${hostId} - Containers - Unicron` },
    { name: "description", content: `Containers on host ${hostId}` },
  ];
}

// ============================================================================
// Types
// ============================================================================

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

interface ContainersResponse {
  containers: ContainerInfo[];
  groups: GroupInfo[];
  hosts: HostInfo[];
}

interface HostInfo {
  host_id: string;
  online: boolean;
  container_count: number;
  last_seen?: string;
}

interface HostStatus {
  isOnline: boolean;
  lastSeen: string | null;
  containerCount: number;
  runningCount: number;
}

// ============================================================================
// API
// ============================================================================

async function getContainers(): Promise<ContainersResponse> {
  const response = await httpApp.get<ContainersApiResponse>("/containers/overview");
  const mappedContainers: ContainerInfo[] = response.data.containers.map((c) => ({
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
  const hosts: HostInfo[] = (response.data.hosts || []).map((h) => ({
    host_id: h.host_id,
    online: h.online,
    container_count: h.container_count,
    last_seen: h.last_seen,
  }));
  return { containers: mappedContainers, groups: [], hosts };
}

// ============================================================================
// Host Status Calculation
// ============================================================================

function calculateHostStatus(containers: ContainerInfo[], hostInfo?: HostInfo): HostStatus {
  const runningCount = containers.filter(
    (c) => c.status === "running"
  ).length;

  // Find most recent last_seen timestamp
  let mostRecentLastSeen: string | null = null;
  let mostRecentTime = 0;
  containers.forEach((c) => {
    const lastSeenTime = new Date(c.last_seen).getTime();
    if (lastSeenTime > mostRecentTime) {
      mostRecentTime = lastSeenTime;
      mostRecentLastSeen = c.last_seen;
    }
  });

  // Prefer authoritative host online/container_count from backend overview.
  const isOnline = hostInfo?.online ?? false;
  const containerCount = hostInfo?.container_count ?? containers.length;
  const lastSeen = hostInfo?.last_seen ?? mostRecentLastSeen;

  return {
    isOnline,
    lastSeen,
    containerCount,
    runningCount,
  };
}

// ============================================================================
// Breadcrumb Component
// ============================================================================

interface BreadcrumbProps {
  hostId: string;
}

function Breadcrumb({ hostId }: BreadcrumbProps) {
  return (
    <nav className="flex items-center gap-xs text-sm text-neutral">
      <Link
        to="/overview"
        className="hover:text-primary hover:underline"
      >
        Containers
      </Link>
      <ChevronRight className="h-4 w-4" />
      <span className="font-medium text-text">{hostId}</span>
    </nav>
  );
}

// ============================================================================
// Host Status Dot Component
// ============================================================================

interface HostStatusDotProps {
  isOnline: boolean;
  lastSeen?: string;
  size?: "sm" | "md";
}

function HostStatusDot({ isOnline, lastSeen, size = "sm" }: HostStatusDotProps) {
  const sizeClass = size === "md" ? "h-3 w-3" : "h-2 w-2";

  // Format last seen for tooltip
  let tooltip = isOnline ? "Online" : "Offline";
  if (lastSeen) {
    const lastSeenDate = new Date(lastSeen);
    const now = new Date();
    const diffMs = now.getTime() - lastSeenDate.getTime();
    const diffMins = Math.floor(diffMs / (1000 * 60));

    if (diffMins < 1) {
      tooltip += " - seen just now";
    } else if (diffMins < 60) {
      tooltip += ` - seen ${diffMins}m ago`;
    } else {
      const diffHours = Math.floor(diffMins / 60);
      tooltip += ` - seen ${diffHours}h ago`;
    }
  }

  return (
    <span
      className={`${sizeClass} rounded-full ${
        isOnline ? "bg-success" : "bg-neutral"
      }`}
      title={tooltip}
    />
  );
}

// ============================================================================
// Host Header Component
// ============================================================================

interface HostHeaderProps {
  hostId: string;
  isOnline: boolean;
  lastSeen: string | null;
  containerCount: number;
  runningCount: number;
}

function HostHeader({
  hostId,
  isOnline,
  lastSeen,
  containerCount,
  runningCount,
}: HostHeaderProps) {
  return (
    <div className="flex flex-wrap items-center gap-md rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
      <div className="rounded-xl bg-primary/10 p-sm">
        <Server className="h-8 w-8 text-primary" />
      </div>
      <div className="flex-1">
        <div className="flex items-center gap-sm">
          <h1 className="text-xl font-bold text-text">{hostId}</h1>
          <HostStatusDot
            isOnline={isOnline}
            lastSeen={lastSeen ?? undefined}
            size="md"
          />
        </div>
        <p className="text-sm text-neutral">
          {containerCount} container{containerCount !== 1 ? "s" : ""}
          {runningCount > 0 && (
            <span className="ml-xs text-success">
              ({runningCount} running)
            </span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-xs">
        <div className="flex items-center gap-xs text-xs">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              isOnline ? "bg-success" : "bg-neutral/40"
            }`}
          />
          <span className={isOnline ? "text-success" : "text-neutral"}>
            {isOnline ? "Live" : "Offline"}
          </span>
        </div>
        <PushTelemetryGuide
          hostId={hostId}
          fluentAddress="127.0.0.1:24224"
          buttonLabel="Setup Push Telemetry"
        />
      </div>
    </div>
  );
}

function HostOfflineNotice({ hostId }: { hostId: string }) {
  return (
    <div className="flex items-start gap-sm rounded-lg border border-warning/30 bg-warning/10 px-sm py-sm text-sm text-warning">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <p>
        Host <span className="font-semibold">{hostId}</span> is offline. Container status shown here is
        last known state from when the host was last seen online.
      </p>
    </div>
  );
}

// ============================================================================
// Skeleton Loader
// ============================================================================

function HostDetailSkeleton() {
  return (
    <div className="flex w-full flex-col gap-lg">
      {/* Breadcrumb skeleton */}
      <div className="h-5 w-32 animate-pulse rounded bg-neutral/20" />

      {/* Header skeleton */}
      <div className="flex items-center gap-md rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
        <div className="h-14 w-14 animate-pulse rounded-xl bg-neutral/20" />
        <div className="flex-1 space-y-2">
          <div className="h-6 w-48 animate-pulse rounded bg-neutral/20" />
          <div className="h-4 w-32 animate-pulse rounded bg-neutral/20" />
        </div>
      </div>

      {/* Grid skeleton */}
      <div className="grid grid-cols-1 gap-md sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900"
          >
            <div className="mb-sm flex items-start gap-sm">
              <div className="h-10 w-10 animate-pulse rounded-xl bg-neutral/20" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-24 animate-pulse rounded bg-neutral/20" />
                <div className="h-3 w-32 animate-pulse rounded bg-neutral/20" />
              </div>
            </div>
            <div className="h-5 w-16 animate-pulse rounded-full bg-neutral/20" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Empty State
// ============================================================================

function EmptyState({ hostId }: { hostId: string }) {
  return (
    <div className="py-xl text-center">
      <div className="mx-auto mb-md flex h-20 w-20 items-center justify-center rounded-full bg-neutral/10">
        <Server className="h-10 w-10 text-neutral" />
      </div>
      <h3 className="mb-2xs text-base font-semibold text-text">
        No containers on this host
      </h3>
      <p className="text-sm text-neutral">
        Host "{hostId}" has no registered containers.
      </p>
    </div>
  );
}

// ============================================================================
// Group Card Component (renders as a card in the container grid)
// ============================================================================

interface GroupCardProps {
  group: GroupInfo;
  containers: ContainerInfo[];
  monitoredCount: number;
  onToggle: () => void;
  onDelete: () => void;
  animate?: boolean;
}

function GroupCard({ group, containers, monitoredCount, onToggle, onDelete, animate }: GroupCardProps) {
  const runningCount = containers.filter((c) => c.status === "running").length;
  const displayName = group.name.includes("/")
    ? group.name.split("/").slice(1).join("/")
    : group.name;

  return (
    <div
      className="relative flex min-h-[230px] cursor-pointer flex-col rounded-xl border border-primary/30 bg-gradient-to-b from-primary/15 via-primary/5 to-background p-md shadow-sm transition-all duration-200 hover:shadow-md hover:border-primary/50 dark:from-primary/10 dark:via-primary/5 dark:to-neutral-900"
      style={animate ? { animation: "groupCardAppear 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards" } : undefined}
      onClick={onToggle}
    >
      {/* Top row: status pills + delete */}
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1 flex-wrap">
          <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-semibold text-success border border-success/30">
            {runningCount}/{containers.length} running
          </span>
          <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary border border-primary/30">
            {monitoredCount}/{containers.length} monitored
          </span>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="rounded p-1 text-neutral/50 hover:text-error hover:bg-error/10 transition-colors"
          title="Delete group"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Center: icon + name */}
      <div className="flex flex-1 flex-col items-center justify-center gap-sm py-sm">
        <div className="rounded-xl bg-primary/10 p-sm">
          <Layers className="h-8 w-8 text-primary" />
        </div>
        <span className="text-sm font-semibold text-text text-center leading-tight">
          {displayName}
        </span>
        <span className="text-xs text-neutral">
          {containers.length} container{containers.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Bottom: container initial previews */}
      <div className="flex items-center justify-center gap-1.5 pt-sm border-t border-neutral/10">
        {containers.slice(0, 5).map((c) => (
          <span
            key={c.identifier}
            className={`flex h-7 w-7 items-center justify-center rounded-md text-[10px] font-bold text-white ${
              c.status === "running" ? "bg-primary/70" : "bg-neutral/40"
            }`}
            title={`${c.name} (${c.status || "unknown"})`}
          >
            {c.name.charAt(0).toUpperCase()}
          </span>
        ))}
        {containers.length > 5 && (
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-neutral/20 text-[10px] font-medium text-neutral">
            +{containers.length - 5}
          </span>
        )}
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function HostDetailPage() {
  const params = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const hostId = decodeURIComponent(params.hostId ?? "");

  // Monitoring state
  const [monitoringStates, setMonitoringStates] = useState<Record<string, boolean>>({});
  const [togglingContainers, setTogglingContainers] = useState<Set<string>>(new Set());
  const [errorToast, setErrorToast] = useState<string | null>(null);

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["containers"],
    queryFn: getContainers,
    staleTime: 30 * 1000,
    refetchOnMount: true,
  });

  const allContainers = data?.containers ?? [];
  const allHosts = data?.hosts ?? [];
  const hostInfo = allHosts.find((host) => host.host_id === hostId);

  // Filter containers to this host
  const containers = allContainers.filter((c) => {
    const containerHostId = c.host_id || "local";
    return containerHostId === hostId;
  });

  const hostStatus = calculateHostStatus(containers, hostInfo);
  const isHostOffline = !hostStatus.isOnline;

  // Fetch groups from alert-engine (background sync)
  const { data: alertEngineData } = useQuery({
    queryKey: ["alert-engine-groups"],
    queryFn: () => apiService.getContainers(),
    staleTime: 30 * 1000,
  });
  const serverGroups = alertEngineData?.groups ?? [];

  // Local groups: created during this session for immediate UI feedback.
  // Server fetch may not return them instantly (containers might not be in
  // alert-engine DB yet), so we track them locally for optimistic rendering.
  const [localGroups, setLocalGroups] = useState<GroupInfo[]>([]);
  // Rename overrides applied on top of both server and local groups.
  // Needed because the server refetch is async and one-step-behind otherwise.
  const [renameOverrides, setRenameOverrides] = useState<Record<string, string>>({});

  // Merge server groups + local groups, deduplicate by name, apply rename overrides
  const hostGroups = useMemo(() => {
    const applyOverride = (g: GroupInfo): GroupInfo => {
      const override = renameOverrides[String(g.groupId)];
      return override ? { ...g, name: override } : g;
    };
    const fromServer = serverGroups
      .filter((g) => g.members?.some((m) => m.host_id === hostId))
      .map(applyOverride);
    // Server groups take precedence; only keep local groups not yet on server
    const serverNames = new Set(fromServer.map((g) => g.name));
    const pending = localGroups
      .filter((g) => !serverNames.has(g.name))
      .map(applyOverride);
    return [...fromServer, ...pending];
  }, [serverGroups, hostId, localGroups, renameOverrides]);

  // Expanded groups state
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const toggleGroup = (groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
        // Clear expand animation tracking so re-expanding animates again
        seenGroupIds.current.delete(`expand-${groupId}`);
        // Clear card animation tracking so collapsing back animates
        seenGroupIds.current.delete(`card-${groupId}`);
      } else {
        next.add(groupId);
        // Clear card tracking so collapsing later animates
        seenGroupIds.current.delete(`card-${groupId}`);
      }
      return next;
    });
  };

  // Compute grouped container keys (host_id:name) to filter ungrouped containers
  const groupedContainerKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const group of hostGroups) {
      if (group.members) {
        for (const m of group.members) {
          keys.add(`${m.host_id}:${m.container_name}`);
        }
      }
    }
    return keys;
  }, [hostGroups]);

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

  // Stack filter: group containers by Docker Compose project
  const [stackFilter, setStackFilter] = useState<string>("all");
  const [showStackDropdown, setShowStackDropdown] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);
  const [renamingGroupId, setRenamingGroupId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);
  // Track which groups have already been rendered so animations only play once
  const seenGroupIds = useRef<Set<string>>(new Set());

  const composeStacks = useMemo(() => {
    const stackCounts = new Map<string, number>();
    let standaloneCount = 0;
    for (const c of containers) {
      const stack = c.labels?.["com.docker.compose.project"];
      if (stack) {
        stackCounts.set(stack, (stackCounts.get(stack) || 0) + 1);
      } else {
        standaloneCount++;
      }
    }
    return {
      stacks: Array.from(stackCounts.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([name, count]) => ({ name, count })),
      standaloneCount,
    };
  }, [containers]);

  const filteredContainers = useMemo(() => {
    if (stackFilter === "all") return containers;
    if (stackFilter === "standalone") {
      return containers.filter((c) => !c.labels?.["com.docker.compose.project"]);
    }
    return containers.filter(
      (c) => c.labels?.["com.docker.compose.project"] === stackFilter
    );
  }, [containers, stackFilter]);

  // Ungrouped containers: those not in any group
  const ungroupedContainers = useMemo(() => {
    if (groupedContainerKeys.size === 0) return filteredContainers;
    return filteredContainers.filter((c) => {
      const key = `${c.host_id || "local"}:${c.name}`;
      return !groupedContainerKeys.has(key);
    });
  }, [filteredContainers, groupedContainerKeys]);

  // Resolve group members to actual container objects, respecting the active stack filter.
  const getGroupContainers = useCallback(
    (group: GroupInfo): ContainerInfo[] => {
      if (!group.members) return [];
      return filteredContainers.filter((c) =>
        group.members!.some(
          (m) => m.host_id === (c.host_id || "local") && m.container_name === c.name
        )
      );
    },
    [filteredContainers]
  );

  // Split stacks into inline buttons vs overflow dropdown
  const MAX_INLINE_STACKS = 3;
  const hasStandalone = composeStacks.standaloneCount > 0;
  const inlineStacks = composeStacks.stacks.slice(0, MAX_INLINE_STACKS);
  const overflowStacks = composeStacks.stacks.slice(MAX_INLINE_STACKS);
  const hasOverflow = overflowStacks.length > 0 || (hasStandalone && composeStacks.stacks.length >= MAX_INLINE_STACKS);

  // Check if a group already exists for the current filter
  const currentFilterGroupExists = useMemo(() => {
    if (stackFilter === "all") return false;
    const stackLabel = stackFilter === "standalone" ? "standalone" : stackFilter;
    const groupName = `${hostId}/${stackLabel}`;
    return hostGroups.some((g) => g.name === groupName);
  }, [stackFilter, hostId, hostGroups]);

  // Close stack dropdown on outside click
  useEffect(() => {
    if (!showStackDropdown) return;
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowStackDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showStackDropdown]);

  // Create alert-engine container group from current stack filter
  const handleCreateGroup = async () => {
    if (stackFilter === "all" || currentFilterGroupExists || filteredContainers.length < 2) return;

    const stackLabel = stackFilter === "standalone" ? "standalone" : stackFilter;
    const groupName = `${hostId}/${stackLabel}`;

    // Build optimistic group from current filtered containers
    const localId = `local-${Date.now()}`;
    const newGroup: GroupInfo = {
      groupId: localId,
      name: groupName,
      containerIds: filteredContainers.map((c) => c.container_key),
      members: filteredContainers.map((c) => ({
        host_id: c.host_id || "local",
        container_name: c.name,
      })),
    };

    // Show group immediately (optimistic)
    setLocalGroups((prev) => [...prev, newGroup]);
    setExpandedGroups((prev) => new Set(prev).add(localId));
    setCreatingGroup(true);

    try {
      const containerIds = filteredContainers.map((c) => c.container_key);
      const result = await apiService.createGroup(groupName, containerIds);

      // Update local group with real server ID
      if (result.group?.id) {
        const serverId = String(result.group.id);
        setLocalGroups((prev) =>
          prev.map((g) => (g.groupId === localId ? { ...g, groupId: serverId } : g))
        );
        setExpandedGroups((prev) => {
          const next = new Set(prev);
          if (next.has(localId)) { next.delete(localId); next.add(serverId); }
          return next;
        });
        // Mark server group as already seen so animations don't replay
        // when the server data replaces the optimistic local data
        seenGroupIds.current.add(`expand-${serverId}`);
        seenGroupIds.current.add(`card-${serverId}`);
      }
      queryClient.invalidateQueries({ queryKey: ["alert-engine-groups"] });
    } catch (error: any) {
      // Roll back optimistic group on failure
      setLocalGroups((prev) => prev.filter((g) => g.groupId !== localId));
      setExpandedGroups((prev) => { const next = new Set(prev); next.delete(localId); return next; });
      setErrorToast(error?.message || "Failed to create container group");
    } finally {
      setCreatingGroup(false);
    }
  };

  // Delete a container group
  const handleDeleteGroup = async (groupId: string) => {
    setLocalGroups((prev) => prev.filter((g) => String(g.groupId) !== groupId));
    if (groupId.startsWith("local-")) return;
    try {
      await apiService.deleteGroup(groupId);
      queryClient.invalidateQueries({ queryKey: ["alert-engine-groups"] });
    } catch (error: any) {
      setErrorToast(error?.message || "Failed to delete group");
    }
  };

  // Rename a container group (inline edit)
  const handleGroupRename = async (groupId: string, newDisplayName: string) => {
    setRenamingGroupId(null);
    const trimmed = newDisplayName.trim();
    if (!trimmed) return;
    const fullName = `${hostId}/${trimmed}`;

    // Apply override immediately (works for both server and local groups)
    setRenameOverrides((prev) => ({ ...prev, [groupId]: fullName }));
    // Also update local groups for consistency
    setLocalGroups((prev) =>
      prev.map((g) => (String(g.groupId) === groupId ? { ...g, name: fullName } : g))
    );

    if (groupId.startsWith("local-")) return;
    try {
      await apiService.renameGroup(groupId, fullName);
      queryClient.invalidateQueries({ queryKey: ["alert-engine-groups"] });
    } catch (error: any) {
      // Revert override on failure
      setRenameOverrides((prev) => {
        const next = { ...prev };
        delete next[groupId];
        return next;
      });
      setErrorToast(error?.message || "Failed to rename group");
    }
  };

  // Batch toggle monitoring for all containers in a group
  const handleGroupMonitoringToggle = async (groupContainers: ContainerInfo[], enabled: boolean) => {
    if (isHostOffline) {
      setErrorToast("Host is offline. Monitoring changes are disabled until it reconnects.");
      return;
    }

    let targetContainers = groupContainers;
    try {
      targetContainers = await resolveLatestContainers(groupContainers);
    } catch (error) {
      console.error("Failed to refresh container inventory before batch monitoring toggle:", error);
    }

    if (targetContainers.length === 0) return;

    setTogglingContainers((prev) => {
      const next = new Set(prev);
      targetContainers.forEach((c) => next.add(c.identifier));
      return next;
    });

    const results = await Promise.allSettled(
      targetContainers.map((c) =>
        httpApp.post(
          `/containers/${encodeURIComponent(c.identifier)}/monitoring?host_id=${encodeURIComponent(c.host_id || "local")}`,
          { enabled }
        )
      )
    );

    const failures: Array<{
      container: ContainerInfo;
      detail: string;
      staleInventory: boolean;
    }> = [];

    results.forEach((result, index) => {
      const target = targetContainers[index];

      if (result.status === "fulfilled") {
        const confirmedId = result.value.data?.container_key || target.identifier;
        const confirmedState = result.value.data?.monitoring_enabled ?? enabled;
        setMonitoringConfirmed(confirmedId, confirmedState);
        clearTogglingContainers([target.identifier, confirmedId]);
        return;
      }

      const detail = result.reason?.response?.data?.detail || "Failed to toggle monitoring";
      clearTogglingContainers([target.identifier]);
      failures.push({
        container: target,
        detail,
        staleInventory:
          result.reason?.response?.status === 404 &&
          detail === "Container not found in inventory",
      });
    });

    if (failures.length > 0) {
      if (failures.some((failure) => failure.staleInventory)) {
        await queryClient.invalidateQueries({ queryKey: ["containers"] });
      }

      if (failures.every((failure) => failure.staleInventory)) {
        setErrorToast(
          "Some containers restarted before monitoring was enabled. The container list was refreshed."
        );
        return;
      }

      const preview = failures
        .slice(0, 2)
        .map((failure) => {
          const detail = failure.staleInventory
            ? "Container restarted; list refreshed"
            : failure.detail;
          return `${failure.container.name}: ${detail}`;
        })
        .join("; ");
      const remainder = failures.length > 2 ? `; +${failures.length - 2} more` : "";
      setErrorToast(preview + remainder);
    }
  };

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
      if (!allContainers.length) return;

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
  }, [allContainers]);

  // Real-time WebSocket updates
  const handleWebSocketEvents = useCallback((events: ContainerEvent[]) => {
    for (const event of events) {
      if (event.type === "container_event") {
        // Single container state change (start/stop/die) from agent ws_handler
        const { container_key, status, host_id, name } = event.data;
        if (!status) continue;
        queryClient.setQueryData<ContainersResponse>(["containers"], (old) => {
          if (!old) return old;
          return {
            ...old,
            containers: old.containers.map((c) => {
              const match =
                (container_key && c.container_key === container_key) ||
                (host_id && name && c.host_id === host_id && c.name === name);
              return match ? { ...c, status } : c;
            }),
          };
        });
      } else if (event.type === "inventory_update" && event.data?.containers) {
        // Batch inventory refresh from the canonical container feed
        const updates = event.data.containers as Array<{ identifier?: string; name?: string; host_id?: string; status?: string }>;
        queryClient.setQueryData<ContainersResponse>(["containers"], (old) => {
          if (!old) return old;
          return {
            ...old,
            containers: old.containers.map((c) => {
              const update = updates.find((u) =>
                (u.name && u.host_id && u.name === c.name && u.host_id === c.host_id)
              );
              return update?.status ? { ...c, status: update.status } : c;
            }),
          };
        });
      } else if (event.type === "monitoring_state_changed") {
        const { container_key, monitoring_enabled } = event.data;
        setMonitoringConfirmed(container_key, monitoring_enabled);
        clearTogglingContainers([container_key]);
      } else if (event.type === "host_status") {
        queryClient.invalidateQueries({ queryKey: ["containers"] });
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
      }
    }
  }, [clearTogglingContainers, queryClient, setMonitoringConfirmed]);

  const { connected } = useContainerWebSocket(handleWebSocketEvents);

  // Invalidate containers query when WebSocket reconnects
  useEffect(() => {
    if (connected) {
      const timer = setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ["containers"] });
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [connected, queryClient]);

  const handleContainerClick = (container: ContainerInfo) => {
    const returnTo = encodeURIComponent(`/containers/host/${encodeURIComponent(hostId)}`);
    navigate(`/containers/${container.identifier}?returnTo=${returnTo}`);
  };

  const handleAlertClick = (container: ContainerInfo) => {
    const returnTo = encodeURIComponent(`/containers/host/${encodeURIComponent(hostId)}`);
    navigate(`/containers/${container.identifier}?tab=alerts&returnTo=${returnTo}`);
  };

  const handleMonitoringChange = async (container: ContainerInfo, enabled: boolean) => {
    if (isHostOffline) {
      setErrorToast("Host is offline. Monitoring changes are disabled until it reconnects.");
      return;
    }

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
    const containerHostId = targetContainer.host_id || "local";

    setTogglingContainers((prev) => new Set(prev).add(containerId));

    try {
      const response = await httpApp.post(
        `/containers/${encodeURIComponent(containerId)}/monitoring?host_id=${encodeURIComponent(containerHostId)}`,
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

  if (isLoading) {
    return <HostDetailSkeleton />;
  }

  if (error && !data) {
    return (
      <AppShellError
        error={error}
        title="Unable to load host inventory"
        message="We couldn't refresh this host's container inventory right now. Please try again."
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <>
    {/* Scoped animations for group expand/collapse/create */}
    <style>{`
      @keyframes groupExpand {
        0% { opacity: 0; max-height: 0; transform: translateY(-16px); }
        60% { opacity: 1; }
        100% { opacity: 1; max-height: 2000px; transform: translateY(0); }
      }
      @keyframes groupCardAppear {
        0% { opacity: 0; transform: scale(0.85) translateY(8px); }
        60% { transform: scale(1.02) translateY(-2px); }
        100% { opacity: 1; transform: scale(1) translateY(0); }
      }
      @keyframes groupCollapse {
        from { opacity: 1; transform: translateY(0); }
        to { opacity: 0; transform: translateY(-8px); }
      }
    `}</style>
    <div className="flex w-full flex-col gap-lg">
      {/* Navigation + Inline Stack Filters */}
      <div className="flex items-center gap-sm flex-wrap">
        <button
          onClick={() => navigate("/overview")}
          className="flex items-center gap-xs rounded-lg border border-neutral/20 bg-background px-sm py-xs text-sm text-neutral transition-colors hover:bg-neutral/10 hover:text-text dark:bg-neutral-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </button>
        <Breadcrumb hostId={hostId} />

        {/* Stack filter pills (inline with breadcrumb) */}
        {containers.length > 0 && composeStacks.stacks.length > 0 && (
          <>
            <div className="h-5 w-px bg-neutral/20" />
            <div className="flex items-center gap-xs">
              <Layers className="h-4 w-4 text-neutral" />
              <div className="inline-flex rounded-lg border border-neutral/20 bg-background p-0.5">
                <button
                  onClick={() => setStackFilter("all")}
                  className={`px-sm py-xs text-xs font-medium rounded-md transition-colors ${
                    stackFilter === "all"
                      ? "bg-primary/10 text-primary"
                      : "text-neutral hover:text-text"
                  }`}
                >
                  All ({containers.length})
                </button>
                {inlineStacks.map(({ name, count }) => (
                  <button
                    key={name}
                    onClick={() => setStackFilter(name)}
                    className={`px-sm py-xs text-xs font-medium rounded-md transition-colors ${
                      stackFilter === name
                        ? "bg-primary/10 text-primary"
                        : "text-neutral hover:text-text"
                    }`}
                  >
                    {name} ({count})
                  </button>
                ))}
                {!hasOverflow && hasStandalone && (
                  <button
                    onClick={() => setStackFilter("standalone")}
                    className={`px-sm py-xs text-xs font-medium rounded-md transition-colors ${
                      stackFilter === "standalone"
                        ? "bg-primary/10 text-primary"
                        : "text-neutral hover:text-text"
                    }`}
                  >
                    Standalone ({composeStacks.standaloneCount})
                  </button>
                )}
              </div>

              {/* Overflow dropdown for additional stacks */}
              {hasOverflow && (
                <div className="relative" ref={dropdownRef}>
                  <button
                    onClick={() => setShowStackDropdown(!showStackDropdown)}
                    className={`flex items-center gap-xs px-sm py-xs text-xs font-medium rounded-md border border-neutral/20 transition-colors ${
                      [...overflowStacks.map((s) => s.name), ...(hasStandalone ? ["standalone"] : [])].includes(stackFilter)
                        ? "bg-primary/10 text-primary border-primary/30"
                        : "text-neutral hover:text-text"
                    }`}
                  >
                    More
                    <ChevronDown className={`h-3 w-3 transition-transform ${showStackDropdown ? "rotate-180" : ""}`} />
                  </button>
                  {showStackDropdown && (
                    <div className="absolute top-full left-0 z-50 mt-1 max-h-48 w-48 overflow-y-auto rounded-lg border border-neutral/20 bg-background shadow-lg dark:bg-neutral-900">
                      {overflowStacks.map(({ name, count }) => (
                        <button
                          key={name}
                          onClick={() => { setStackFilter(name); setShowStackDropdown(false); }}
                          className={`block w-full px-sm py-xs text-left text-xs transition-colors ${
                            stackFilter === name
                              ? "bg-primary/10 text-primary"
                              : "text-neutral hover:bg-neutral/5 hover:text-text"
                          }`}
                        >
                          {name} ({count})
                        </button>
                      ))}
                      {hasStandalone && (
                        <button
                          onClick={() => { setStackFilter("standalone"); setShowStackDropdown(false); }}
                          className={`block w-full px-sm py-xs text-left text-xs transition-colors ${
                            stackFilter === "standalone"
                              ? "bg-primary/10 text-primary"
                              : "text-neutral hover:bg-neutral/5 hover:text-text"
                          }`}
                        >
                          Standalone ({composeStacks.standaloneCount})
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Create Group button (visible when a specific stack/standalone is selected) */}
            {stackFilter !== "all" && (
              <button
                onClick={handleCreateGroup}
                disabled={creatingGroup || currentFilterGroupExists || filteredContainers.length < 2}
                className="ml-auto flex items-center gap-xs rounded-lg border border-primary/30 bg-primary/10 px-sm py-xs text-xs font-medium text-primary transition-colors hover:bg-primary/20 disabled:opacity-40 disabled:cursor-not-allowed"
                title={currentFilterGroupExists ? "Group already exists" : undefined}
              >
                <Plus className="h-3.5 w-3.5" />
                {creatingGroup ? "Creating..." : currentFilterGroupExists ? "Group Exists" : "Create Group"}
              </button>
            )}
          </>
        )}
      </div>

      {/* Host Header */}
      <HostHeader
        hostId={hostId}
        isOnline={hostStatus.isOnline}
        lastSeen={hostStatus.lastSeen}
        containerCount={hostStatus.containerCount}
        runningCount={hostStatus.runningCount}
      />
      {isHostOffline && <HostOfflineNotice hostId={hostId} />}

      {/* Container Grid (groups + ungrouped mixed together) */}
      {containers.length === 0 ? (
        <EmptyState hostId={hostId} />
      ) : (
        <div
          className={`grid grid-cols-1 gap-md sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 ${
            isHostOffline ? "opacity-50" : ""
          }`}
        >
          {/* Expanded groups first (full-width, connected border) */}
          {hostGroups
            .filter((g) => expandedGroups.has(String(g.groupId)))
            .map((group) => {
              const gc = getGroupContainers(group);
              if (gc.length === 0) return null;
              const gid = String(group.groupId);
              const expandKey = `expand-${gid}`;
              const isNewExpand = !seenGroupIds.current.has(expandKey);
              if (isNewExpand) seenGroupIds.current.add(expandKey);
              const displayName = group.name.includes("/")
                ? group.name.split("/").slice(1).join("/")
                : group.name;
              const runningCount = gc.filter((c) => c.status === "running").length;
              const monitoredCount = gc.filter((c) => monitoringStates[c.identifier]).length;
              const allMonitored = monitoredCount === gc.length;
              return (
                <div
                  key={gid}
                  className="col-span-full rounded-xl border border-primary/30 overflow-hidden"
                  style={isNewExpand ? { animation: "groupExpand 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards" } : undefined}
                >
                  {/* Header bar (part of the connected container) */}
                  <div
                    className="flex items-center gap-sm bg-gradient-to-r from-primary/10 to-transparent px-md py-sm cursor-pointer hover:from-primary/15 transition-colors"
                    onClick={() => toggleGroup(gid)}
                  >
                    <Layers className="h-5 w-5 text-primary" />

                    {/* Inline-editable name */}
                    {renamingGroupId === gid ? (
                      <input
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={() => handleGroupRename(gid, renameValue)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleGroupRename(gid, renameValue);
                          if (e.key === "Escape") setRenamingGroupId(null);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        autoFocus
                        className="rounded border border-primary/30 bg-background px-2 py-0.5 text-sm font-semibold text-text outline-none focus:border-primary"
                      />
                    ) : (
                      <button
                        className="group/rename flex items-center gap-1 font-semibold text-text hover:text-primary transition-colors"
                        onClick={(e) => { e.stopPropagation(); setRenamingGroupId(gid); setRenameValue(displayName); }}
                        title="Click to rename"
                      >
                        {displayName}
                        <Pencil className="h-3 w-3 opacity-0 group-hover/rename:opacity-60 transition-opacity" />
                      </button>
                    )}

                    {/* Status pills */}
                    <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-semibold text-success border border-success/30">
                      {runningCount}/{gc.length} running
                    </span>
                    <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] font-semibold text-primary border border-primary/30">
                      {monitoredCount}/{gc.length} monitored
                    </span>

                    <div className="ml-auto flex items-center gap-xs">
                      {/* Manage Monitoring batch toggle */}
                      <button
                        onClick={(e) => { e.stopPropagation(); handleGroupMonitoringToggle(gc, !allMonitored); }}
                        disabled={isHostOffline}
                        className="flex items-center gap-1 rounded-md border border-neutral/20 bg-background px-2 py-1 text-xs font-medium text-text transition-colors hover:bg-neutral/5 disabled:cursor-not-allowed disabled:opacity-50"
                        title={allMonitored ? "Disable monitoring for all" : "Enable monitoring for all"}
                      >
                        <Shield className="h-3.5 w-3.5" />
                        {allMonitored ? "Unmonitor All" : "Monitor All"}
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDeleteGroup(gid); }}
                        className="rounded p-1 text-neutral/50 hover:text-error hover:bg-error/10 transition-colors"
                        title="Delete group"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                      <ChevronDown className="h-4 w-4 text-neutral rotate-180 transition-transform duration-200" />
                    </div>
                  </div>

                  {/* Member containers (inside the same border) */}
                  <div className="border-t border-primary/15 bg-primary/[0.02] p-md">
                    <div className="grid grid-cols-1 gap-md sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                      {gc.map((container) => (
                        <ContainerCard
                          key={container.identifier}
                          container={container}
                          onClick={() => handleContainerClick(container)}
                          onAlertClick={() => handleAlertClick(container)}
                          alertCount={alertsByContainer[container.identifier] ?? 0}
                          alertSeverity={alertSeverityByContainer?.[container.identifier]?.highestSeverity}
                          alertBreakdown={alertSeverityByContainer?.[container.identifier]?.breakdown}
                          alertStackCount={alertStackCountByContainer[container.identifier]}
                          status={container.status}
                          isMonitored={monitoringStates[container.identifier] ?? false}
                          onMonitoringChange={
                            isHostOffline
                              ? undefined
                              : (enabled) => handleMonitoringChange(container, enabled)
                          }
                          isToggling={
                            isHostOffline ? false : togglingContainers.has(container.identifier)
                          }
                        />
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}

          {/* Collapsed groups as cards in the grid */}
          {hostGroups
            .filter((g) => !expandedGroups.has(String(g.groupId)))
            .map((group) => {
              const gc = getGroupContainers(group);
              if (gc.length === 0) return null;
              const gid = String(group.groupId);
              const cardKey = `card-${gid}`;
              const isNewCard = !seenGroupIds.current.has(cardKey);
              if (isNewCard) seenGroupIds.current.add(cardKey);
              const monitoredCount = gc.filter((c) => monitoringStates[c.identifier]).length;
              return (
                <GroupCard
                  key={gid}
                  group={group}
                  containers={gc}
                  monitoredCount={monitoredCount}
                  onToggle={() => toggleGroup(gid)}
                  onDelete={() => handleDeleteGroup(gid)}
                  animate={isNewCard}
                />
              );
            })}

          {/* Ungrouped container cards */}
          {ungroupedContainers.map((container) => (
            <ContainerCard
              key={container.identifier}
              container={container}
              onClick={() => handleContainerClick(container)}
              onAlertClick={() => handleAlertClick(container)}
              alertCount={alertsByContainer[container.identifier] ?? 0}
              alertSeverity={alertSeverityByContainer?.[container.identifier]?.highestSeverity}
              alertBreakdown={alertSeverityByContainer?.[container.identifier]?.breakdown}
              alertStackCount={alertStackCountByContainer[container.identifier]}
              status={container.status}
              isMonitored={monitoringStates[container.identifier] ?? false}
              onMonitoringChange={
                isHostOffline
                  ? undefined
                  : (enabled) => handleMonitoringChange(container, enabled)
              }
              isToggling={
                isHostOffline ? false : togglingContainers.has(container.identifier)
              }
            />
          ))}
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
    </>
  );
}
