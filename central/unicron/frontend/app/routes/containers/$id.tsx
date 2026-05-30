/**
 * Container Detail Page
 *
 * Displays detailed view of a single container with tabbed navigation
 * for: Overview, Alerts, Logs, Terminal, and Files.
 */

import { useState, Suspense, lazy, useMemo } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  AlertTriangle,
  FileText,
  Terminal,
  FolderOpen,
  ArrowLeft,
  Container,
} from "lucide-react";
import { httpApp } from "~/utils/http.client";
import type { ContainerInfo } from "~/components/containers";
import { OverviewTab, AlertsTab } from "~/components/containers/tabs";
import { AppShellError } from "~/components/library/errors";

// Lazy load heavy tab components (Monaco editor, xterm.js, react-window)
const FilesTab = lazy(() => import("~/components/containers/tabs/FilesTab"));
const TerminalTab = lazy(() => import("~/components/containers/tabs/TerminalTab"));
const LogsTab = lazy(() => import("~/components/containers/tabs/LogsTab"));

// ============================================================================
// Meta
// ============================================================================

export function meta() {
  return [
    { title: "Container Details - Unicron" },
    { name: "description", content: "Container detail view" },
  ];
}

// Prevent SSR roundtrip on navigation - this route is fully client-side
export function clientLoader() {
  return null;
}

// ============================================================================
// Types
// ============================================================================

type TabId = "overview" | "alerts" | "logs" | "terminal" | "files";

interface Tab {
  id: TabId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

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
    monitoring_enabled?: boolean;
  }>;
}

interface ContainersResponse {
  containers: ContainerInfo[];
  groups: { groupId: number; name: string; containerIds: string[] }[];
}

function resolveReturnTo(value: string | null): string {
  if (!value) return "/overview";

  const candidate = (() => {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  })();

  if (candidate === "/overview" || candidate.startsWith("/overview/")) return candidate;
  if (candidate.startsWith("/containers")) return candidate;
  return "/overview";
}

// ============================================================================
// Constants
// ============================================================================

const tabs: Tab[] = [
  { id: "overview", label: "Overview", icon: BarChart3 },
  { id: "alerts", label: "Alerts", icon: AlertTriangle },
  { id: "logs", label: "Logs", icon: FileText },
  { id: "terminal", label: "Terminal", icon: Terminal },
  { id: "files", label: "Files", icon: FolderOpen },
];

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
    monitoring_enabled: Boolean(c.monitoring_enabled),
  }));
  return { containers: mappedContainers, groups: [] };
}

// ============================================================================
// Status Badge Component
// ============================================================================

interface StatusBadgeProps {
  status?: string;
}

function StatusBadge({ status }: StatusBadgeProps) {
  const isRunning = status === "running";
  const statusText = status || "unknown";

  return (
    <span
      className={`inline-flex items-center gap-xs rounded-full px-sm py-3xs text-xs font-medium ${
        isRunning
          ? "bg-success/10 text-success"
          : status === "exited" || status === "stopped"
            ? "bg-error/10 text-error"
            : "bg-neutral/10 text-neutral"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          isRunning
            ? "bg-success animate-pulse"
            : status === "exited" || status === "stopped"
              ? "bg-error"
              : "bg-neutral"
        }`}
      />
      {statusText}
    </span>
  );
}

// ============================================================================
// Tab Button Component
// ============================================================================

interface TabButtonProps {
  tab: Tab;
  isActive: boolean;
  onClick: () => void;
}

function TabButton({ tab, isActive, onClick }: TabButtonProps) {
  const Icon = tab.icon;

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-xs border-b-2 px-md py-sm text-sm font-medium transition-colors ${
        isActive
          ? "border-primary text-primary"
          : "border-transparent text-neutral hover:border-neutral/30 hover:text-text"
      }`}
    >
      <Icon className="h-4 w-4" />
      {tab.label}
    </button>
  );
}

// ============================================================================
// Skeleton Loader
// ============================================================================

function ContainerDetailSkeleton() {
  return (
    <div className="flex w-full w-full flex-col gap-md">
      {/* Back button skeleton */}
      <div className="h-8 w-32 animate-pulse rounded bg-neutral/20" />

      {/* Header skeleton */}
      <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
        <div className="flex items-center gap-md">
          <div className="h-14 w-14 animate-pulse rounded-xl bg-neutral/20" />
          <div className="space-y-2">
            <div className="h-6 w-48 animate-pulse rounded bg-neutral/20" />
            <div className="h-4 w-32 animate-pulse rounded bg-neutral/20" />
          </div>
        </div>
      </div>

      {/* Tabs skeleton */}
      <div className="flex gap-md border-b border-neutral/20">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="h-10 w-24 animate-pulse rounded bg-neutral/20"
          />
        ))}
      </div>

      {/* Content skeleton */}
      <div className="h-64 animate-pulse rounded-xl bg-neutral/10" />
    </div>
  );
}

// ============================================================================
// Not Found Component
// ============================================================================

function ContainerNotFound({ onBack, backLabel }: { onBack: () => void; backLabel: string }) {
  return (
    <div className="flex w-full w-full flex-col items-center justify-center gap-md py-xl">
      <div className="rounded-full bg-error/10 p-lg">
        <Container className="h-12 w-12 text-error" />
      </div>
      <h2 className="text-xl font-bold text-text">Container Not Found</h2>
      <p className="text-sm text-neutral">
        The container you're looking for doesn't exist or has been removed.
      </p>
      <button
        onClick={onBack}
        className="flex items-center gap-xs rounded-lg bg-primary px-md py-sm text-sm font-medium text-white transition-colors hover:bg-primary/90"
      >
        <ArrowLeft className="h-4 w-4" />
        {backLabel}
      </button>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function ContainerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = useMemo(
    () => resolveReturnTo(searchParams.get("returnTo")),
    [searchParams]
  );
  const backLabel = returnTo.startsWith("/containers/host/")
    ? "Back to Host"
    : "Back to Overview";
  const initialTab = (() => {
    const param = searchParams.get("tab");
    const validTabs: TabId[] = ["overview", "alerts", "logs", "terminal", "files"];
    return validTabs.includes(param as TabId) ? (param as TabId) : "overview";
  })();
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["containers"],
    queryFn: getContainers,
    staleTime: 30 * 1000,
    refetchOnMount: true,
  });

  if (error && !data) {
    return (
      <AppShellError
        error={error}
        title="Unable to load container"
        message="We couldn't refresh the container inventory right now. Please try again."
        onRetry={() => void refetch()}
      />
    );
  }

  if (isLoading) {
    return <ContainerDetailSkeleton />;
  }

  const containers = data?.containers ?? [];
  const container = containers.find((c) => c.identifier === id);

  if (!container) {
    return <ContainerNotFound onBack={() => navigate(returnTo)} backLabel={backLabel} />;
  }

  return (
    <div className="flex w-full w-full flex-col gap-md">
      {/* Back Button */}
      <button
        onClick={() => navigate(returnTo)}
        className="flex w-fit items-center gap-xs text-sm text-neutral transition-colors hover:text-text"
      >
        <ArrowLeft className="h-4 w-4" />
        {backLabel}
      </button>

      {/* Container Header */}
      <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-md">
            <div className="rounded-xl bg-primary/10 p-sm">
              <Container className="h-8 w-8 text-primary" />
            </div>
            <div>
              <div className="flex items-center gap-sm">
                <h1 className="text-xl font-bold text-text">{container.name}</h1>
                <StatusBadge status={container.status} />
              </div>
              <p className="mt-3xs text-sm text-neutral">
                {container.image_name || "No image"}
              </p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-xs text-neutral">Container ID</p>
            <code className="rounded bg-neutral/10 px-2xs py-4xs font-mono text-sm text-neutral">
              {container.docker_container_id ? container.docker_container_id.slice(0, 12) : "N/A"}
            </code>
          </div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2xs border-b border-neutral/20">
        {tabs.map((tab) => (
          <TabButton
            key={tab.id}
            tab={tab}
            isActive={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
          />
        ))}
      </div>

      {/* Tab Content */}
      <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
        {activeTab === "overview" && (
          <OverviewTab
            containerName={container.name}
            hostId={container.host_id ?? null}
            container={container}
          />
        )}

        {activeTab === "alerts" && (
          <AlertsTab
            containerName={container.name}
            hostId={container.host_id || "local"}
            onNavigateToLogs={() => setActiveTab("logs")}
          />
        )}

        {activeTab === "logs" && (
          <Suspense
            fallback={
              <div className="flex h-[500px] items-center justify-center">
                <p className="text-sm text-neutral">Loading logs...</p>
              </div>
            }
          >
            <LogsTab
              containerKey={container.container_key}
              containerName={container.name}
              hostId={container.host_id ?? null}
              monitoringEnabled={Boolean(container.monitoring_enabled)}
            />
          </Suspense>
        )}

        {activeTab === "terminal" && (
          <Suspense
            fallback={
              <div className="flex h-[500px] items-center justify-center">
                <p className="text-sm text-neutral">Loading terminal...</p>
              </div>
            }
          >
            <TerminalTab
              containerKey={container.container_key}
              hostId={container.host_id ?? null}
            />
          </Suspense>
        )}

        {activeTab === "files" && (
          <Suspense
            fallback={
              <div className="flex h-[600px] items-center justify-center">
                <p className="text-sm text-neutral">Loading file explorer...</p>
              </div>
            }
          >
            <FilesTab
              containerKey={container.container_key}
              hostId={container.host_id ?? null}
            />
          </Suspense>
        )}
      </div>
    </div>
  );
}
