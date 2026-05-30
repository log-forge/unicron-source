/**
 * Agent Management Page
 *
 * UI for managing remote monitoring agents:
 * - Enroll new agents (generates docker run command with enrollment token)
 * - View agent status (online/offline with container counts)
 * - Decommission agents
 */

import { useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Server, Plus, Copy, Check, Trash2, X } from "lucide-react";
import { useSearchParams } from "react-router";
import { httpApp } from "../utils/http.client";
import SettingsSubtabs from "../components/settings/SettingsSubtabs";
import PushTelemetryGuide from "../components/settings/PushTelemetryGuide";
import AgentRefusalModal from "../components/agents/AgentRefusalModal";
import { useContainerWebSocket } from "../hooks/useContainerWebSocket";
import { deriveDefaultCentralUrl, normalizeCentralUrlInput } from "../utils/agentEnrollmentCentralUrl";
import {
  ENROLLMENT_POLL_INTERVAL_MS,
  getEnrollmentPollingCutoffMs,
  shouldStopEnrollmentPolling,
  type PendingEnrollment,
} from "../utils/agentEnrollmentPolling";
import { buildAgentFailureDisplay, type AgentFailure, type AgentStatus } from "../utils/agentFailure";
import {
  buildAgentDeregisterPath,
  buildAgentRemovalConfirmation,
  getAgentRemovalLabel,
  getAgentRemovalPendingLabel,
  removeAgentFromRows,
} from "../utils/agentRemoval";
import {
  buildAgentRefusalModalKey,
  clearAgentRefusalModalClaims,
  openFirstBlockedAgentRefusalOnce,
  type AgentRefusalModalData,
} from "../utils/agentRefusalModal";
import { useModal } from "../context/ModalContext";
import type { ContainerEvent } from "../hooks/useContainerWebSocket";

// ============================================================================
// Meta
// ============================================================================

export function meta() {
  return [
    { title: "Agents - Settings - Unicron" },
    { name: "description", content: "Manage remote monitoring agents" },
  ];
}

// ============================================================================
// Types
// ============================================================================

interface AgentInfo {
  agent_id: string;
  agent_name: string;
  status: AgentStatus;
  container_count: number;
  last_seen: number | null;
  last_status_change?: number | null;
  failure?: AgentFailure | null;
}

interface EnrollResponse {
  ok: boolean;
  agent_name: string;
  token: string;
  docker_run_command: string;
  expires_at: number;
}

type QueueMode = "durable" | "memory";
type QueuePreset = "small" | "balanced" | "high-throughput" | "custom";
type InstallTarget = "local" | "remote";

const MEMORY_QUEUE_MIN_MB = 32;
const MEMORY_QUEUE_MAX_MB = 4096;
const DISK_QUEUE_MIN_MB = 128;
const DISK_QUEUE_MAX_MB = 65536;
const DEFAULT_QUEUE_MODE: QueueMode = "memory";
const DEFAULT_QUEUE_PRESET: Exclude<QueuePreset, "custom"> = "balanced";
const QUEUE_PRESET_VALUES: Record<Exclude<QueuePreset, "custom">, { memoryMb: number; diskMb: number; label: string }> = {
  small: { label: "Small", memoryMb: 128, diskMb: 512 },
  balanced: { label: "Balanced", memoryMb: 256, diskMb: 1024 },
  "high-throughput": { label: "High-throughput", memoryMb: 512, diskMb: 4096 },
};
const DEFAULT_MEMORY_QUEUE_MB = QUEUE_PRESET_VALUES[DEFAULT_QUEUE_PRESET].memoryMb;
const DEFAULT_DISK_QUEUE_MB = QUEUE_PRESET_VALUES[DEFAULT_QUEUE_PRESET].diskMb;
const OTelQueueUnitsPerMB = 250;
const OTelQueueMin = 1000;
const OTelQueueMax = 200000;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

// ============================================================================
// API
// ============================================================================

async function fetchAgents(): Promise<AgentInfo[]> {
  type AgentListPage = {
    agents?: AgentInfo[];
    total?: number;
  };
  const pageSize = 1000;
  const agents: AgentInfo[] = [];
  let offset = 0;

  try {
    while (true) {
      const response = await httpApp.get<AgentListPage>("/agent/list", {
        params: { limit: pageSize, offset },
      });
      const pageAgents = Array.isArray(response.data?.agents) ? response.data.agents : [];
      agents.push(...pageAgents);

      const total = Number(response.data?.total ?? agents.length);
      offset += pageAgents.length;
      if (pageAgents.length === 0 || offset >= total) break;
    }
    return agents;
  } catch (error) {
    console.error("Failed to fetch agents:", error);
    return [];
  }
}

// ============================================================================
// Enrollment Dialog Component
// ============================================================================

interface EnrollmentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  defaultAgentName?: string;
  installTarget: InstallTarget;
  onEnrollmentIssued?: (enrollment: { agentName: string; expiresAt: number }) => void;
}

function EnrollmentDialog({
  isOpen,
  onClose,
  defaultAgentName,
  installTarget,
  onEnrollmentIssued,
}: EnrollmentDialogProps) {
  const [agentName, setAgentName] = useState("");
  const [centralUrl, setCentralUrl] = useState<string>(deriveDefaultCentralUrl);
  const [queueMode, setQueueMode] = useState<QueueMode>(DEFAULT_QUEUE_MODE);
  const [queuePreset, setQueuePreset] = useState<QueuePreset>(DEFAULT_QUEUE_PRESET);
  const [memoryQueueMb, setMemoryQueueMb] = useState<string>(String(DEFAULT_MEMORY_QUEUE_MB));
  const [diskQueueMb, setDiskQueueMb] = useState<string>(String(DEFAULT_DISK_QUEUE_MB));
  const [enrollResponse, setEnrollResponse] = useState<EnrollResponse | null>(null);
  const [enrolling, setEnrolling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number>(0);
  const [copied, setCopied] = useState(false);

  // Validate agent name
  const isValidAgentName = (name: string): boolean => {
    if (name.length < 1 || name.length > 63) return false;
    return /^[a-z0-9.-_]+$/.test(name);
  };

  const parseMbField = (value: string): number | null => {
    const parsed = Number.parseInt(value.trim(), 10);
    if (!Number.isFinite(parsed)) return null;
    return parsed;
  };

  const applyPreset = (preset: Exclude<QueuePreset, "custom">) => {
    const values = QUEUE_PRESET_VALUES[preset];
    setQueuePreset(preset);
    setMemoryQueueMb(String(values.memoryMb));
    setDiskQueueMb(String(values.diskMb));
  };

  const memoryMbParsed = parseMbField(memoryQueueMb) ?? DEFAULT_MEMORY_QUEUE_MB;
  const diskMbParsed = parseMbField(diskQueueMb) ?? DEFAULT_DISK_QUEUE_MB;
  const metricsQueueBudgetMb = queueMode === "durable" ? diskMbParsed : memoryMbParsed;
  const effectiveOTelQueueSize = clamp(
    metricsQueueBudgetMb * OTelQueueUnitsPerMB,
    OTelQueueMin,
    OTelQueueMax
  );

  // Countdown timer for token expiry
  useEffect(() => {
    if (!enrollResponse?.expires_at) return;

    const updateCountdown = () => {
      const now = Math.floor(Date.now() / 1000);
      const remaining = enrollResponse.expires_at - now;
      setCountdown(Math.max(0, remaining));
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);
    return () => clearInterval(interval);
  }, [enrollResponse]);

  // Reset copied state after 2s
  useEffect(() => {
    if (copied) {
      const timer = setTimeout(() => setCopied(false), 2000);
      return () => clearTimeout(timer);
    }
  }, [copied]);

  // Prevent background scroll while modal is open.
  useEffect(() => {
    if (!isOpen) return;
    setAgentName((defaultAgentName || "").toLowerCase());
    setCentralUrl(installTarget === "local" ? "https://unicron.central/unicron" : deriveDefaultCentralUrl());
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original || "";
    };
  }, [defaultAgentName, installTarget, isOpen]);

  const handleEnroll = async () => {
    if (!isValidAgentName(agentName)) {
      setError("Agent name must be 1-63 characters: lowercase letters, numbers, dots, dashes, underscores");
      return;
    }

    const memoryMb = parseMbField(memoryQueueMb);
    if (memoryMb === null || memoryMb < MEMORY_QUEUE_MIN_MB || memoryMb > MEMORY_QUEUE_MAX_MB) {
      setError(`Memory queue must be between ${MEMORY_QUEUE_MIN_MB} and ${MEMORY_QUEUE_MAX_MB} MB`);
      return;
    }

    const diskMb = parseMbField(diskQueueMb);
    if (queueMode === "durable") {
      if (diskMb === null || diskMb < DISK_QUEUE_MIN_MB || diskMb > DISK_QUEUE_MAX_MB) {
        setError(`Disk queue must be between ${DISK_QUEUE_MIN_MB} and ${DISK_QUEUE_MAX_MB} MB`);
        return;
      }
    }

    let normalizedCentralUrl: string;
    try {
      normalizedCentralUrl = normalizeCentralUrlInput(centralUrl);
      if (!normalizedCentralUrl) {
        setError("Central URL is required");
        return;
      }
      const parsed = new URL(normalizedCentralUrl);
      if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
        setError("Central URL must use http:// or https://");
        return;
      }
      if (!parsed.hostname) {
        setError("Central URL must include a hostname");
        return;
      }
    } catch {
      setError("Central URL is invalid");
      return;
    }

    setEnrolling(true);
    setError(null);

    try {
      const response = await httpApp.post("/agent/enroll", {
        agent_name: agentName,
        central_url: normalizedCentralUrl,
        install_target: installTarget,
        queue_mode: queueMode,
        memory_queue_mb: memoryMb,
        disk_queue_mb: diskMb ?? DEFAULT_DISK_QUEUE_MB,
      });
      const enrollment = response.data as EnrollResponse;
      setEnrollResponse(enrollment);
      onEnrollmentIssued?.({
        agentName: enrollment.agent_name,
        expiresAt: enrollment.expires_at,
      });
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to generate enrollment token");
    } finally {
      setEnrolling(false);
    }
  };

  const handleCopy = async () => {
    if (!enrollResponse?.docker_run_command) return;
    try {
      await navigator.clipboard.writeText(enrollResponse.docker_run_command);
      setCopied(true);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const handleClose = () => {
    setAgentName("");
    setCentralUrl(deriveDefaultCentralUrl());
    setQueueMode(DEFAULT_QUEUE_MODE);
    setQueuePreset(DEFAULT_QUEUE_PRESET);
    setMemoryQueueMb(String(DEFAULT_MEMORY_QUEUE_MB));
    setDiskQueueMb(String(DEFAULT_DISK_QUEUE_MB));
    setEnrollResponse(null);
    setError(null);
    setCopied(false);
    onClose();
  };

  if (!isOpen) return null;

  if (typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-[120] animate-fade-in">
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={handleClose} />
      <div className="fixed inset-0 flex items-center justify-center p-4 pointer-events-none">
        <div
          className="pointer-events-auto relative flex max-h-[90vh] w-[min(96vw,72rem)] flex-col rounded-xl border border-neutral/20 bg-background shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex flex-shrink-0 items-center justify-between border-b border-neutral/20 px-4 py-3">
            <div className="flex items-center gap-2">
              <Server className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-semibold text-text">
                {installTarget === "local" ? "Enroll Local Agent" : "Enroll New Agent"}
              </h2>
            </div>
            <button
              onClick={handleClose}
              className="flex h-7 w-7 items-center justify-center rounded-full transition-colors hover:bg-neutral/10"
              aria-label="Close"
            >
              <X className="h-4 w-4 text-neutral" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {!enrollResponse ? (
              // Step 1: Agent name input
              <div className="space-y-3">
                <p className="text-sm text-neutral">
                  {installTarget === "local"
                    ? "Create a local host agent. Run the generated command on this machine (or the host you want to monitor)."
                    : "Enter a unique name for this agent. This will identify the agent in the UI and logs."}
                </p>

                <div className="space-y-1">
                  <label htmlFor="agent-name" className="block text-sm font-medium text-text">
                    Agent Name
                  </label>
                  <input
                    id="agent-name"
                    type="text"
                    value={agentName}
                    onChange={(e) => setAgentName(e.target.value.toLowerCase())}
                    placeholder="my-remote-server"
                    className="w-full rounded-md border border-neutral/20 bg-background px-3 py-2 text-sm text-text placeholder:text-neutral/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                    disabled={enrolling}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !enrolling) {
                        handleEnroll();
                      }
                    }}
                  />
                  <p className="text-xs text-neutral">
                    1-63 characters: lowercase letters, numbers, dots, dashes, underscores
                  </p>
                </div>

                <div className="space-y-1">
                  <label htmlFor="central-url" className="block text-sm font-medium text-text">
                    Central URL
                  </label>
                  <input
                    id="central-url"
                    type="text"
                    value={centralUrl}
                    onChange={(e) => setCentralUrl(e.target.value)}
                    placeholder="https://unicron.example.com/unicron"
                    className="w-full rounded-md border border-neutral/20 bg-background px-3 py-2 text-sm text-text placeholder:text-neutral/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                    disabled={enrolling || installTarget === "local"}
                  />
                  <p className="text-xs text-neutral">
                    {installTarget === "local"
                      ? "Auto-configured for local Docker install mode on the shared Docker network."
                      : "Must be reachable from the host where this agent will run."}
                  </p>
                </div>

              <div className="space-y-2 rounded-md border border-neutral/20 bg-neutral/5 p-3">
                <p className="text-sm font-medium text-text">Queue size preset</p>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {(["small", "balanced", "high-throughput"] as const).map((presetKey) => {
                    const preset = QUEUE_PRESET_VALUES[presetKey];
                    const selected = queuePreset === presetKey;
                    return (
                      <button
                        key={presetKey}
                        type="button"
                        onClick={() => applyPreset(presetKey)}
                        className={`rounded-md border px-3 py-2 text-left transition-colors ${
                          selected
                            ? "border-primary bg-primary/10"
                            : "border-neutral/20 bg-background hover:bg-neutral/5"
                        }`}
                      >
                        <p className="text-sm font-medium text-text">{preset.label}</p>
                        <p className="mt-0.5 text-xs text-neutral">
                          {preset.memoryMb}MB mem / {preset.diskMb}MB disk
                        </p>
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => setQueuePreset("custom")}
                    className={`rounded-md border px-3 py-2 text-left transition-colors ${
                      queuePreset === "custom"
                        ? "border-primary bg-primary/10"
                        : "border-neutral/20 bg-background hover:bg-neutral/5"
                    }`}
                  >
                    <p className="text-sm font-medium text-text">Custom</p>
                    <p className="mt-0.5 text-xs text-neutral">Set queue sizes manually</p>
                  </button>
                </div>
                <p className="text-xs text-neutral">
                  Choose a preset based on expected ingest volume, then fine-tune if needed.
                </p>
              </div>

              <div className="space-y-2 rounded-md border border-neutral/20 bg-neutral/5 p-3">
                <p className="text-sm font-medium text-text">Queue durability</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <button
                    type="button"
                    onClick={() => setQueueMode("memory")}
                    className={`rounded-md border px-3 py-2 text-left transition-colors ${
                      queueMode === "memory"
                        ? "border-primary bg-primary/10"
                        : "border-neutral/20 bg-background hover:bg-neutral/5"
                    }`}
                  >
                    <p className="text-sm font-medium text-text">Memory only (default)</p>
                    <p className="mt-0.5 text-xs text-neutral">
                      Avoids persistent queue volumes. Backlog is not retained through restarts.
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => setQueueMode("durable")}
                    className={`rounded-md border px-3 py-2 text-left transition-colors ${
                      queueMode === "durable"
                        ? "border-primary bg-primary/10"
                        : "border-neutral/20 bg-background hover:bg-neutral/5"
                    }`}
                  >
                    <p className="text-sm font-medium text-text">Durable output queue</p>
                    <p className="mt-0.5 text-xs text-neutral">
                      Opt-in disk persistence for Central outages and agent restarts.
                    </p>
                  </button>
                </div>
              </div>

	              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <label htmlFor="memory-queue-mb" className="block text-sm font-medium text-text">
                    In-memory queue max (MB)
                  </label>
                  <input
                    id="memory-queue-mb"
                    type="number"
                    min={MEMORY_QUEUE_MIN_MB}
                    max={MEMORY_QUEUE_MAX_MB}
                    value={memoryQueueMb}
                    onChange={(e) => {
                      setMemoryQueueMb(e.target.value);
                      setQueuePreset("custom");
                    }}
                    className="w-full rounded-md border border-neutral/20 bg-background px-3 py-2 text-sm text-text focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                    disabled={enrolling}
                  />
                  <p className="text-xs text-neutral">
                    Range: {MEMORY_QUEUE_MIN_MB}-{MEMORY_QUEUE_MAX_MB} MB
                  </p>
                </div>
                <div className="space-y-1">
                  <label htmlFor="disk-queue-mb" className="block text-sm font-medium text-text">
                    Durable disk queue max (MB)
                  </label>
                  <input
                    id="disk-queue-mb"
                    type="number"
                    min={DISK_QUEUE_MIN_MB}
                    max={DISK_QUEUE_MAX_MB}
                    value={diskQueueMb}
                    onChange={(e) => {
                      setDiskQueueMb(e.target.value);
                      setQueuePreset("custom");
                    }}
                    className="w-full rounded-md border border-neutral/20 bg-background px-3 py-2 text-sm text-text focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
                    disabled={enrolling || queueMode !== "durable"}
                  />
                  <p className="text-xs text-neutral">
                    {queueMode === "durable"
                      ? `Range: ${DISK_QUEUE_MIN_MB}-${DISK_QUEUE_MAX_MB} MB`
                      : "Disabled in memory-only mode"}
                  </p>
                </div>
	              </div>

              <div className="rounded-md border border-neutral/20 bg-neutral/5 p-3 space-y-1.5">
                <p className="text-sm font-medium text-text">Queue summary</p>
                <p className="text-xs text-neutral">
                  Logging memory buffer (Fluent Bit): <span className="font-mono text-text">{memoryMbParsed} MB</span>
                </p>
                {queueMode === "durable" ? (
                  <p className="text-xs text-neutral">
                    Logging disk backlog (Fluent Bit): <span className="font-mono text-text">{diskMbParsed} MB</span>
                  </p>
                ) : (
                  <p className="text-xs text-neutral">
                    Logging disk backlog (Fluent Bit): <span className="font-mono text-text">disabled</span>
                  </p>
                )}
                <p className="text-xs text-neutral">
                  Metrics in-memory queue (OTel):{" "}
                  <span className="font-mono text-text">{effectiveOTelQueueSize}</span> items
                </p>
                <p className="text-xs text-neutral">
                  Metrics disk backlog (OTel file storage):{" "}
                  <span className="font-mono text-text">{queueMode === "durable" ? "enabled" : "disabled"}</span>
                </p>
                <p className="text-[11px] text-neutral/90">
                  OTel queue is item-count based and derived from a {metricsQueueBudgetMb} MB budget. This is not a strict MB cap.
                </p>
              </div>

	              {error && (
                <div className="flex items-start gap-2 p-2 rounded-md bg-error/10 border border-error/20">
                  <span className="text-error text-sm">{error}</span>
                </div>
              )}

                <button
                  onClick={handleEnroll}
                  disabled={enrolling || !agentName}
                  className={`
                    w-full flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all
                    ${
                      enrolling || !agentName
                        ? "opacity-50 cursor-not-allowed bg-primary/20 text-primary"
                        : "bg-primary text-white hover:bg-primary/90"
                    }
                  `}
                >
                  {enrolling ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      Generating...
                    </>
                  ) : (
                    <>
                      <Plus className="h-4 w-4" />
                      Generate Enrollment Command
                    </>
                  )}
                </button>
              </div>
            ) : (
              // Step 2: Display docker run command
              <div className="space-y-3">
                <div className="flex items-start gap-2 p-2 rounded-md bg-success/10 border border-success/20">
                  <span className="text-success text-base flex-shrink-0">✓</span>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-success">Enrollment token generated</p>
                    <p className="text-xs text-success/80 mt-0.5">
                      Agent: <span className="font-mono">{enrollResponse.agent_name}</span>
                    </p>
                  </div>
                </div>

              {/* Countdown timer */}
              <div className="flex items-center justify-between p-2 rounded-md bg-neutral/5 border border-neutral/20">
                <span className="text-xs text-neutral">Token expires in:</span>
                {countdown > 0 ? (
                  <span className="text-sm font-mono font-bold text-text">
                    {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, '0')}
                  </span>
                ) : (
                  <span className="text-xs font-medium text-error">Token expired - generate a new one</span>
                )}
              </div>

              {/* Docker run command */}
              <div className="space-y-1">
                <label className="block text-xs font-medium text-text">
                  Docker Run Command
                </label>
                <div className="relative">
                  <pre className="overflow-x-auto rounded-md border border-neutral/20 bg-neutral/5 p-2 font-mono text-xs text-text whitespace-pre-wrap break-all">
{enrollResponse.docker_run_command}
                  </pre>
                  <button
                    onClick={handleCopy}
                    disabled={countdown === 0}
                    className={`
                      absolute top-1.5 right-1.5 flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-all
                      ${
                        countdown === 0
                          ? "opacity-50 cursor-not-allowed bg-neutral/20 text-neutral"
                          : copied
                          ? "bg-success/20 text-success"
                          : "bg-primary/20 text-primary hover:bg-primary/30"
                      }
                    `}
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3" />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        Copy
                      </>
                    )}
                  </button>
                </div>
              </div>

              <div className="space-y-1">
                <p className="text-xs font-medium text-text">Next steps:</p>
                <ol className="list-decimal list-inside space-y-0.5 text-xs text-neutral ml-1">
                  <li>Copy the command above</li>
                  <li>
                    {installTarget === "local"
                      ? "Run it on the local host where Docker is running"
                      : "SSH into your remote server"}
                  </li>
                  <li>Run the command to start the agent container</li>
                  <li>Wait a few seconds for the agent to appear in the table</li>
                </ol>
              </div>

                <button
                  onClick={handleClose}
                  className="w-full rounded-md px-3 py-2 text-sm font-medium bg-neutral/10 text-text hover:bg-neutral/20 transition-all"
                >
                  Done
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

// ============================================================================
// Agent Table Component
// ============================================================================

interface AgentTableProps {
  agents: AgentInfo[];
  onDecommission: (agentId: string, agentName: string, status: AgentStatus) => void;
  decommissioning: string | null;
}

function AgentTable({ agents, onDecommission, decommissioning }: AgentTableProps) {
  const formatLastSeen = (lastSeen: number | null | undefined): string => {
    if (!lastSeen) return "Unknown";
    try {
      const dt = new Date(lastSeen * 1000);
      if (Number.isNaN(dt.getTime())) return "Unknown";
      const datePart = dt.toLocaleDateString(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
      const timePart = dt.toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        timeZoneName: "short",
      });
      return `${datePart} ${timePart}`;
    } catch {
      return "Unknown";
    }
  };

  if (agents.length === 0) {
    return (
      <div className="rounded-xl border border-neutral/20 bg-neutral/5 p-lg text-center">
        <Server className="h-12 w-12 text-neutral/40 mx-auto mb-sm" />
        <p className="text-base font-medium text-text">No agents enrolled</p>
        <p className="text-sm text-neutral mt-xs">
          Click "Enroll New Agent" to get started
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-neutral/20 bg-background">
      <table className="w-full">
        <thead className="bg-neutral/5 border-b border-neutral/20">
          <tr>
            <th className="px-md py-sm text-left text-xs font-semibold text-neutral uppercase tracking-wider">
              Name
            </th>
            <th className="px-md py-sm text-left text-xs font-semibold text-neutral uppercase tracking-wider">
              Status
            </th>
            <th className="px-md py-sm text-left text-xs font-semibold text-neutral uppercase tracking-wider">
              Containers
            </th>
            <th className="px-md py-sm text-left text-xs font-semibold text-neutral uppercase tracking-wider">
              Last Seen
            </th>
            <th className="px-md py-sm text-left text-xs font-semibold text-neutral uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral/10">
          {agents.map((agent, idx) => {
            const display = buildAgentFailureDisplay(agent.status, agent.failure);
            const isRemoving = decommissioning === agent.agent_id;
            const removalLabel = getAgentRemovalLabel(agent.status);
            const pendingLabel = getAgentRemovalPendingLabel(agent.status);
            return (
              <tr
                key={agent.agent_id}
                className={`
                  transition-colors hover:bg-neutral/5
                  ${idx % 2 === 0 ? 'bg-background' : 'bg-neutral/5'}
                `}
              >
              <td className="px-md py-sm text-sm font-medium text-text">
                <div className="flex items-center gap-sm">
                  <Server className="h-4 w-4 text-neutral" />
                  <span className="font-mono">{agent.agent_name}</span>
                </div>
              </td>
              <td className="px-md py-sm text-sm">
                <div className="flex items-center gap-xs whitespace-nowrap">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      agent.status === "online"
                        ? "bg-green-500"
                        : agent.status === "blocked"
                          ? "bg-amber-500"
                          : "bg-neutral/40"
                    }`}
                  />
                  <span
                    className={`text-sm font-medium ${
                      agent.status === "online"
                        ? "text-green-600 dark:text-green-400"
                        : agent.status === "blocked"
                          ? "text-amber-700 dark:text-amber-300"
                          : "text-neutral"
                    }`}
                  >
                    {display.statusLabel}
                  </span>
                </div>
              </td>
              <td className="px-md py-sm text-sm text-text">
                {agent.container_count}
              </td>
              <td className="px-md py-sm text-sm text-neutral">
                {formatLastSeen(agent.last_seen)}
              </td>
              <td className="px-md py-sm text-sm">
                {agent.status === "blocked" ? (
                  <div className="flex flex-wrap items-center gap-xs">
                    <span
                      className="whitespace-nowrap text-xs font-medium text-neutral"
                      title={display.detail || display.message}
                      aria-label={display.detail || display.message || display.compactDetail}
                    >
                      {display.compactDetail}
                    </span>
                    <button
                      onClick={() => onDecommission(agent.agent_id, agent.agent_name, agent.status)}
                      disabled={isRemoving}
                      className={`
                        flex items-center gap-xs rounded-md px-sm py-2xs text-xs font-medium transition-all
                        ${
                          isRemoving
                            ? "opacity-50 cursor-not-allowed bg-error/20 text-error"
                            : "bg-error/10 text-error hover:bg-error/20"
                        }
                      `}
                      title="Remove refused agent"
                      aria-label={`Remove refused agent ${agent.agent_name}`}
                    >
                      {isRemoving ? (
                        <>
                          <div className="h-3 w-3 animate-spin rounded-full border-2 border-error border-t-transparent"></div>
                          {pendingLabel}
                        </>
                      ) : (
                        <>
                          <Trash2 className="h-3 w-3" />
                          {removalLabel}
                        </>
                      )}
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-xs">
                    <PushTelemetryGuide
                      hostId={agent.agent_name}
                      fluentAddress="127.0.0.1:24224"
                      buttonLabel="Setup Push"
                      disabled={agent.status !== "online"}
                      className="inline-flex cursor-pointer items-center justify-center rounded-md border border-primary/40 bg-primary/10 px-sm py-2xs text-xs font-medium text-primary transition hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
                    />
                    <button
                      onClick={() => onDecommission(agent.agent_id, agent.agent_name, agent.status)}
                      disabled={isRemoving}
                      className={`
                        flex items-center gap-xs rounded-md px-sm py-2xs text-xs font-medium transition-all
                        ${
                          isRemoving
                            ? "opacity-50 cursor-not-allowed bg-error/20 text-error"
                            : "bg-error/10 text-error hover:bg-error/20"
                        }
                      `}
                      title="Remove agent and disconnect immediately"
                    >
                      {isRemoving ? (
                        <>
                          <div className="w-3 h-3 border-2 border-error border-t-transparent rounded-full animate-spin"></div>
                          {pendingLabel}
                        </>
                      ) : (
                        <>
                          <Trash2 className="h-3 w-3" />
                          {removalLabel}
                        </>
                      )}
                    </button>
                  </div>
                )}
              </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function AgentsPage() {
  const queryClient = useQueryClient();
  const { openModal } = useModal();
  const [searchParams, setSearchParams] = useSearchParams();
  const [enrollDialogOpen, setEnrollDialogOpen] = useState(false);
  const [enrollTarget, setEnrollTarget] = useState<InstallTarget>("remote");
  const [defaultAgentName, setDefaultAgentName] = useState("");
  const [decommissioning, setDecommissioning] = useState<string | null>(null);
  const [pendingEnrollment, setPendingEnrollment] = useState<PendingEnrollment | null>(null);

  const { data: agents = [], isLoading } = useQuery({
    queryKey: ["agents"],
    queryFn: fetchAgents,
  });

  const openAgentRefusalModal = useCallback(
    (refusal: AgentRefusalModalData) => {
      openModal(
        <AgentRefusalModal refusal={refusal} />,
        "sm",
        true,
        buildAgentRefusalModalKey(refusal) ?? undefined,
      );
    },
    [openModal],
  );

  useEffect(() => {
    openFirstBlockedAgentRefusalOnce(agents, openAgentRefusalModal);
  }, [agents, openAgentRefusalModal]);

  const handleEnrollmentIssued = useCallback((enrollment: { agentName: string; expiresAt: number }) => {
    setPendingEnrollment({
      agentName: enrollment.agentName.trim().toLowerCase(),
      expiresAt: enrollment.expiresAt,
      issuedAt: Math.floor(Date.now() / 1000),
    });
  }, []);

  useEffect(() => {
    if (!pendingEnrollment) return;
    if (shouldStopEnrollmentPolling(pendingEnrollment, agents, Date.now(), enrollDialogOpen)) {
      setPendingEnrollment(null);
    }
  }, [agents, enrollDialogOpen, pendingEnrollment]);

  useEffect(() => {
    if (!pendingEnrollment || !enrollDialogOpen) return;

    const cutoffMs = getEnrollmentPollingCutoffMs(pendingEnrollment);
    const clearPendingEnrollmentIfCurrent = () => {
      setPendingEnrollment((current) => {
        if (
          current &&
          current.agentName === pendingEnrollment.agentName &&
          current.issuedAt === pendingEnrollment.issuedAt &&
          current.expiresAt === pendingEnrollment.expiresAt
        ) {
          return null;
        }
        return current;
      });
    };

    const refetchAgents = () => {
      if (Date.now() >= cutoffMs) {
        clearPendingEnrollmentIfCurrent();
        return;
      }
      void queryClient.invalidateQueries({ queryKey: ["agents"], exact: true });
    };

    refetchAgents();
    const intervalId = window.setInterval(refetchAgents, ENROLLMENT_POLL_INTERVAL_MS);
    const timeoutId = window.setTimeout(
      clearPendingEnrollmentIfCurrent,
      Math.max(0, cutoffMs - Date.now()),
    );

    return () => {
      window.clearInterval(intervalId);
      window.clearTimeout(timeoutId);
    };
  }, [enrollDialogOpen, pendingEnrollment, queryClient]);

  const upsertAgent = useCallback(
    (
      hostId: string,
      patch: Partial<AgentInfo> & Pick<AgentInfo, "status">,
      nowTs: number,
    ) => {
      queryClient.setQueryData<AgentInfo[]>(["agents"], (current) => {
        const existing = current || [];
        const idx = existing.findIndex(
          (agent) => agent.agent_id === hostId || agent.agent_name === hostId,
        );

        if (idx === -1) {
          return [
            ...existing,
            {
              agent_id: hostId,
              agent_name: hostId,
              status: patch.status,
              container_count: patch.container_count ?? 0,
              last_seen: patch.last_seen ?? nowTs,
              last_status_change: patch.last_status_change ?? nowTs,
            },
          ];
        }

        const next = [...existing];
        next[idx] = {
          ...next[idx],
          ...patch,
          status: patch.status,
          last_seen: patch.last_seen ?? nowTs,
          last_status_change: patch.last_status_change ?? nowTs,
        };
        return next;
      });
    },
    [queryClient],
  );

  const handleRealtimeEvents = useCallback(
    (events: ContainerEvent[]) => {
      const nowTs = Math.floor(Date.now() / 1000);
      for (const event of events) {
        if (event.type === "host_status") {
          const hostIdRaw = event.data?.host_id;
          if (typeof hostIdRaw !== "string" || !hostIdRaw) continue;
          if (event.data?.removed === true) {
            queryClient.setQueryData<AgentInfo[]>(["agents"], (current) =>
              (current || []).filter((agent) => agent.agent_id !== hostIdRaw && agent.agent_name !== hostIdRaw),
            );
            continue;
          }
          const online = Boolean(event.data?.online);
          upsertAgent(
            hostIdRaw,
            {
              status: online ? "online" : "offline",
            },
            nowTs,
          );
          continue;
        }

        if (event.type === "inventory_update") {
          const hostIdRaw = event.data?.host_id;
          if (typeof hostIdRaw !== "string" || !hostIdRaw) continue;
          const containers = Array.isArray(event.data?.containers)
            ? event.data.containers
            : [];
          upsertAgent(
            hostIdRaw,
            {
              status: "online",
              container_count: containers.length,
            },
            nowTs,
          );
          continue;
        }

        if (event.type === "initial_state") {
          const hosts = Array.isArray(event.data?.hosts) ? event.data.hosts : [];
          for (const host of hosts) {
            const hostIdRaw = host?.host_id;
            if (typeof hostIdRaw !== "string" || !hostIdRaw) continue;
            upsertAgent(
              hostIdRaw,
              {
                status: host?.online ? "online" : "offline",
              },
              nowTs,
            );
          }
        }
      }
    },
    [upsertAgent],
  );

  useContainerWebSocket(handleRealtimeEvents);

  const handleDecommission = useCallback(async (agentId: string, agentName: string, status: AgentStatus) => {
    const confirmed = window.confirm(buildAgentRemovalConfirmation(agentName, status));

    if (!confirmed) return;

    setDecommissioning(agentId);

    try {
      await httpApp.delete(buildAgentDeregisterPath(agentId));
      queryClient.setQueryData<AgentInfo[]>(["agents"], (current) =>
        removeAgentFromRows(current, agentId, agentName)
      );
      if (status === "blocked") {
        clearAgentRefusalModalClaims(agentName);
      }
    } catch (error: any) {
      const action = status === "blocked" ? "remove" : "decommission";
      console.error(`Failed to ${action} agent:`, error);
      alert(`Failed to ${action} agent: ${error?.response?.data?.detail || "Unknown error"}`);
    } finally {
      setDecommissioning(null);
    }
  }, [queryClient]);

  useEffect(() => {
    const enrollMode = searchParams.get("enroll");
    if (enrollMode === "local") {
      setEnrollTarget("local");
      setDefaultAgentName("local");
      setEnrollDialogOpen(true);
      return;
    }
    if (enrollMode === "remote") {
      setEnrollTarget("remote");
      setDefaultAgentName("");
      setEnrollDialogOpen(true);
    }
  }, [searchParams]);

  const openEnrollDialog = useCallback((target: InstallTarget) => {
    setEnrollTarget(target);
    setDefaultAgentName(target === "local" ? "local" : "");
    setEnrollDialogOpen(true);
  }, []);

  const handleCloseEnrollDialog = useCallback(() => {
    setEnrollDialogOpen(false);
    setDefaultAgentName("");
    setPendingEnrollment(null);
    if (!searchParams.has("enroll")) return;
    const next = new URLSearchParams(searchParams);
    next.delete("enroll");
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  return (
    <div className="flex w-full flex-col gap-lg">
      {/* Page Header */}
      <div className="flex flex-col gap-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-xs">
          <h1 className="text-2xl font-bold text-text">Agents</h1>
          <p className="text-sm text-neutral">
            Manage remote monitoring agents for distributed container monitoring.
          </p>
        </div>
        <button
          onClick={() => openEnrollDialog("remote")}
          className="flex items-center gap-xs rounded-md bg-primary px-sm py-xs text-sm font-medium text-white hover:bg-primary/90 transition-all"
        >
          <Plus className="h-4 w-4" />
          Enroll New Agent
        </button>
      </div>

      <SettingsSubtabs />

      {/* Agent Table */}
      {isLoading ? (
        <div className="flex items-center justify-center p-lg">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : (
        <AgentTable
          agents={agents}
          onDecommission={handleDecommission}
          decommissioning={decommissioning}
        />
      )}

      {/* Enrollment Dialog */}
      <EnrollmentDialog
        isOpen={enrollDialogOpen}
        onClose={handleCloseEnrollDialog}
        defaultAgentName={defaultAgentName}
        installTarget={enrollTarget}
        onEnrollmentIssued={handleEnrollmentIssued}
      />
    </div>
  );
}
