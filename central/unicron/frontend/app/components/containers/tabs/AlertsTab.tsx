/**
 * Alerts Tab Component
 *
 * Displays per-container alerts in a dense table layout with state toggle
 * filter (Active / Acknowledged / All), severity badges, absolute timestamps,
 * inline acknowledge actions, and a detail modal.
 *
 * Phase 66-01: Rewired from dead REST fetch to AlertStore-driven real-time data.
 * Phase 66-02: Rebuilt UI to table layout with state toggle, severity badges,
 *              absolute timestamps, and acknowledge actions per user decisions.
 */

import { useState, useMemo } from "react";
import { CheckCircle2, AlertTriangle, Eye } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useContainerAlerts } from "~/hooks/useContainerAlerts";
import { useAlertStore } from "~/context/AlertContext";
import { alertStore, hydrateAlerts } from "~/context/AlertContext";
import type { FiringAlert } from "~/context/AlertContext";
import { formatAlertStackLabel } from "~/utils/alertStack";
import type { IAlert } from "~/utils/api/alerts";
import { httpApp } from "~/utils/http.client";
import AlertDetailsModal from "./AlertDetailsModal";

// ============================================================================
// Types
// ============================================================================

interface AlertsTabProps {
  containerName: string;
  hostId: string;
  onNavigateToLogs: () => void;
}

type StateFilter = "active" | "acknowledged" | "all";

/** Shape of an acknowledged alert returned from Central REST API */
interface AcknowledgedAlert {
  id: string;
  rule_id: string;
  rule_name: string;
  severity: "critical" | "warning" | "info";
  message: string;
  container_name: string;
  host_id: string;
  started_at: string;
  state: "acknowledged";
  acknowledged_at: string;
  trigger_value?: string;
  threshold?: string;
  count?: number;
}

/** Union type for display rows -- either a firing alert or an acknowledged one */
type DisplayAlert =
  | { kind: "firing"; data: FiringAlert }
  | { kind: "acknowledged"; data: AcknowledgedAlert };

// ============================================================================
// Constants
// ============================================================================

const SEVERITY_BADGE_STYLES: Record<string, string> = {
  critical: "bg-error/15 text-error border border-error/30",
  warning: "bg-warning/15 text-warning border border-warning/30",
  info: "bg-primary/15 text-primary border border-primary/30",
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
};

function normalizeSeverity(
  severity?: string
): "critical" | "warning" | "info" {
  switch ((severity || "").toLowerCase()) {
    case "critical":
    case "high":
      return "critical";
    case "warning":
    case "medium":
      return "warning";
    case "info":
    case "low":
    default:
      return "info";
  }
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Format ISO timestamp to absolute display: "Feb 8, 14:32"
 */
function formatAbsoluteTimestamp(iso: string): string {
  try {
    const date = new Date(iso);
    const datePart = date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
    const timePart = date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    return `${datePart}, ${timePart}`;
  } catch {
    return iso;
  }
}

/**
 * Truncate rule name if longer than maxLen characters.
 */
function truncateRuleName(name: string | undefined, maxLen = 40): string {
  if (!name) return "Unnamed Rule";
  if (name.length <= maxLen) return name;
  return name.slice(0, maxLen) + "...";
}

/**
 * Convert a FiringAlert (from AlertStore) to the IAlert shape expected
 * by AlertDetailsModal, preserving backward compatibility. Now includes
 * extended fields added in 66-02.
 */
function firingAlertToIAlert(fa: FiringAlert): IAlert {
  return {
    id: fa.alert_id,
    container: fa.container_name,
    rule_id: fa.rule_id,
    rule_name: fa.rule_name,
    timestamp: fa.started_at,
    message: fa.message,
    severity: normalizeSeverity(fa.severity),
    trigger_value: fa.trigger_value,
    threshold: fa.threshold,
    count: fa.count,
    host_id: fa.host_id,
  };
}

/**
 * Convert an AcknowledgedAlert to the IAlert shape for the modal.
 */
function acknowledgedAlertToIAlert(aa: AcknowledgedAlert): IAlert {
  return {
    id: aa.id,
    container: aa.container_name,
    rule_id: aa.rule_id,
    rule_name: aa.rule_name,
    timestamp: aa.started_at,
    message: aa.message,
    severity: normalizeSeverity(aa.severity),
    trigger_value: aa.trigger_value,
    threshold: aa.threshold,
    count: aa.count,
    host_id: aa.host_id,
  };
}

// ============================================================================
// Sub-Components
// ============================================================================

interface SeverityBadgeProps {
  severity: string;
}

function SeverityBadge({ severity }: SeverityBadgeProps) {
  const normalized = normalizeSeverity(severity);
  const styles = SEVERITY_BADGE_STYLES[normalized];
  const label = SEVERITY_LABELS[normalized];

  return (
    <span
      className={`inline-flex items-center rounded-full px-2xs py-4xs text-xs font-medium ${styles}`}
    >
      {label}
    </span>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export default function AlertsTab({
  containerName,
  hostId,
  onNavigateToLogs,
}: AlertsTabProps) {
  const [stateFilter, setStateFilter] = useState<StateFilter>("active");
  const [selectedAlert, setSelectedAlert] = useState<IAlert | null>(null);
  const [acknowledgingIds, setAcknowledgingIds] = useState<Set<string>>(
    new Set()
  );
  const [isAcknowledgingAll, setIsAcknowledgingAll] = useState(false);

  const queryClient = useQueryClient();
  const acknowledgedAlertsQueryKey = [
    "container-ack-alerts",
    hostId,
    containerName,
  ] as const;

  // Real-time firing alerts from AlertStore via composite key
  const containerKey = `${hostId}:${containerName}`;
  const firingAlerts = useContainerAlerts(containerKey);
  const { acknowledgeAlert: storeAcknowledge } = useAlertStore();

  const mergeAcknowledgedAlerts = (entries: AcknowledgedAlert[]) => {
    if (entries.length === 0) return;

    queryClient.setQueryData<AcknowledgedAlert[]>(
      acknowledgedAlertsQueryKey,
      (previous = []) => {
        const next = new Map(previous.map((entry) => [entry.id, entry]));
        for (const entry of entries) {
          next.set(entry.id, entry);
        }

        return Array.from(next.values()).sort(
          (a, b) =>
            new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
        );
      }
    );
  };

  const toAcknowledgedAlert = (
    source: Pick<
      FiringAlert,
      | "alert_id"
      | "rule_id"
      | "rule_name"
      | "severity"
      | "message"
      | "container_name"
      | "host_id"
      | "started_at"
      | "trigger_value"
      | "threshold"
      | "count"
    >
  ): AcknowledgedAlert => ({
    id: source.alert_id,
    rule_id: source.rule_id,
    rule_name: source.rule_name,
    severity: normalizeSeverity(source.severity),
    message: source.message,
    container_name: source.container_name,
    host_id: source.host_id,
    started_at: source.started_at,
    state: "acknowledged",
    acknowledged_at: new Date().toISOString(),
    trigger_value: source.trigger_value,
    threshold: source.threshold,
    count: source.count,
  });

  // Fetch acknowledged alerts from REST (only when needed)
  const { data: acknowledgedAlerts = [] } = useQuery({
    queryKey: acknowledgedAlertsQueryKey,
    queryFn: async () => {
      const resp = await httpApp.get("/alerts", {
        params: {
          status_filter: "acknowledged",
          container_name: containerName,
          host_id: hostId,
          limit: 100,
        },
      });
      const items: any[] = resp.data?.items ?? [];

      return items.map((item) => ({
        id: item.id,
        rule_id: item.rule_id,
        rule_name: item.rule_name || "Unnamed Rule",
        severity: normalizeSeverity(item.severity),
        message: item.message || "",
        container_name: item.container_name || containerName,
        host_id: item.host_id || hostId,
        started_at: item.started_at,
        state: "acknowledged" as const,
        acknowledged_at: item.updated_at || item.acknowledged_at || item.started_at,
        trigger_value: item.trigger_value,
        threshold: item.threshold,
        count: item.count,
      }));
    },
    enabled: stateFilter === "acknowledged" || stateFilter === "all",
    staleTime: 30_000,
  });

  // Sort newest-first on started_at for firing alerts
  const sortedFiringAlerts = useMemo(
    () =>
      [...firingAlerts].sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime()
      ),
    [firingAlerts]
  );

  // Build display list based on state filter
  const displayAlerts: DisplayAlert[] = useMemo(() => {
    const result: DisplayAlert[] = [];

    if (stateFilter === "active" || stateFilter === "all") {
      for (const fa of sortedFiringAlerts) {
        result.push({ kind: "firing", data: fa });
      }
    }

    if (stateFilter === "acknowledged" || stateFilter === "all") {
      for (const aa of acknowledgedAlerts) {
        result.push({ kind: "acknowledged", data: aa });
      }
    }

    // Sort everything by started_at descending
    result.sort((a, b) => {
      const aTime = new Date(a.data.started_at).getTime();
      const bTime = new Date(b.data.started_at).getTime();
      return bTime - aTime;
    });

    return result;
  }, [stateFilter, sortedFiringAlerts, acknowledgedAlerts]);

  // ---- Acknowledge handlers ----

  const handleAcknowledge = async (alert: FiringAlert) => {
    setAcknowledgingIds((prev) => new Set(prev).add(alert.alert_id));
    try {
      await storeAcknowledge(alert.alert_id);
      mergeAcknowledgedAlerts([toAcknowledgedAlert(alert)]);
      // Invalidate acknowledged alerts cache so it refreshes when switching tab
      void queryClient.invalidateQueries({
        queryKey: acknowledgedAlertsQueryKey,
      });
    } catch (error) {
      console.error("Failed to acknowledge alert:", error);
    } finally {
      setAcknowledgingIds((prev) => {
        const next = new Set(prev);
        next.delete(alert.alert_id);
        return next;
      });
    }
  };

  const handleAcknowledgeAll = async () => {
    const alertIds = firingAlerts.map((a) => a.alert_id);
    if (alertIds.length === 0) return;

    setIsAcknowledgingAll(true);
    try {
      await httpApp.post(
        `/alerts/container/${encodeURIComponent(containerName)}/ack`,
        null,
        {
          params: { host_id: hostId },
        }
      );
      // Optimistically remove all from store
      for (const id of alertIds) {
        alertStore.removeAlert(id);
      }
      mergeAcknowledgedAlerts(firingAlerts.map((alert) => toAcknowledgedAlert(alert)));
      // Invalidate acknowledged alerts cache
      void queryClient.invalidateQueries({
        queryKey: acknowledgedAlertsQueryKey,
      });
    } catch (error) {
      console.error("Failed to acknowledge all alerts:", error);
      hydrateAlerts();
    } finally {
      setIsAcknowledgingAll(false);
    }
  };

  const handleModalAcknowledge = async (alert: IAlert) => {
    if (!alert.id) return;
    setAcknowledgingIds((prev) => new Set(prev).add(alert.id!));
    try {
      await storeAcknowledge(alert.id);
      mergeAcknowledgedAlerts([
        {
          id: alert.id,
          rule_id: alert.rule_id || "",
          rule_name: alert.rule_name || "Unnamed Rule",
          severity: normalizeSeverity(alert.severity),
          message: alert.message || "",
          container_name: alert.container || containerName,
          host_id: alert.host_id || hostId,
          started_at: alert.timestamp,
          state: "acknowledged",
          acknowledged_at: new Date().toISOString(),
          trigger_value: alert.trigger_value,
          threshold: alert.threshold,
          count: alert.count,
        },
      ]);
      void queryClient.invalidateQueries({
        queryKey: acknowledgedAlertsQueryKey,
      });
    } catch (error) {
      console.error("Failed to acknowledge alert from modal:", error);
    } finally {
      setAcknowledgingIds((prev) => {
        const next = new Set(prev);
        next.delete(alert.id!);
        return next;
      });
    }
  };

  // ---- Helpers for display ----

  const hasFiringAlerts = firingAlerts.length > 0;
  const showAckAll =
    hasFiringAlerts && (stateFilter === "active" || stateFilter === "all");

  const getAlertId = (da: DisplayAlert): string =>
    da.kind === "firing" ? da.data.alert_id : da.data.id;

  const toIAlert = (da: DisplayAlert): IAlert =>
    da.kind === "firing"
      ? firingAlertToIAlert(da.data)
      : acknowledgedAlertToIAlert(da.data);

  // ---- Empty state messages ----

  const getEmptyMessage = (): string => {
    if (stateFilter === "active") return "No active alerts";
    if (stateFilter === "acknowledged") return "No acknowledged alerts";
    return "No alerts for this container";
  };

  // ---- Render ----

  return (
    <div className="flex flex-col h-full">
      {/* Header bar: state toggle + acknowledge all */}
      <div className="flex items-center justify-between gap-sm p-sm border-b border-neutral/20">
        {/* State toggle */}
        <div className="inline-flex rounded-lg border border-neutral/20 bg-background p-0.5">
          {(["active", "acknowledged", "all"] as const).map((filter) => (
            <button
              key={filter}
              onClick={() => setStateFilter(filter)}
              className={`px-sm py-xs text-sm font-medium rounded-md transition-colors capitalize ${
                stateFilter === filter
                  ? "bg-primary/10 text-primary"
                  : "text-neutral hover:text-text"
              }`}
            >
              {filter === "active"
                ? "Active"
                : filter === "acknowledged"
                  ? "Acknowledged"
                  : "All"}
            </button>
          ))}
        </div>

        {/* Acknowledge All */}
        {showAckAll && (
          <button
            onClick={handleAcknowledgeAll}
            disabled={isAcknowledgingAll}
            className="flex items-center gap-xs px-sm py-xs text-sm font-medium text-success hover:text-success/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <CheckCircle2 className="h-4 w-4" />
            {isAcknowledgingAll ? "Acknowledging..." : "Acknowledge All"}
          </button>
        )}
      </div>

      {/* Table or empty state */}
      {displayAlerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-xl text-center">
          <AlertTriangle className="mb-sm h-10 w-10 text-neutral/40" />
          <p className="text-sm text-neutral">{getEmptyMessage()}</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-background border-b border-neutral/20">
              <tr>
                <th className="text-left px-sm py-xs font-medium text-neutral">
                  Severity
                </th>
                <th className="text-left px-sm py-xs font-medium text-neutral">
                  Rule Name
                </th>
                <th className="text-left px-sm py-xs font-medium text-neutral">
                  Timestamp
                </th>
                <th className="text-left px-sm py-xs font-medium text-neutral">
                  State
                </th>
                <th className="text-right px-sm py-xs font-medium text-neutral">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {displayAlerts.map((da) => {
                const alertId = getAlertId(da);
                const isFiring = da.kind === "firing";
                const severity = da.data.severity;
                const ruleName =
                  da.kind === "firing"
                    ? da.data.rule_name
                    : da.data.rule_name;
                const startedAt = da.data.started_at;
                const isAcking = acknowledgingIds.has(alertId);
                const stackLabel = formatAlertStackLabel(da.data.count);

                return (
                  <tr
                    key={alertId}
                    className="border-b border-neutral/10 hover:bg-neutral/5 transition-colors"
                  >
                    {/* Severity badge */}
                    <td className="px-sm py-xs">
                      <SeverityBadge severity={severity} />
                    </td>

                    {/* Rule name */}
                    <td className="px-sm py-xs text-text">
                      <div className="inline-flex items-center gap-xs">
                        <span>{truncateRuleName(ruleName)}</span>
                        {stackLabel && (
                          <span className="rounded-full bg-warning/15 px-2xs py-4xs text-[11px] font-semibold text-warning">
                            {stackLabel}
                          </span>
                        )}
                      </div>
                    </td>

                    {/* Timestamp */}
                    <td className="px-sm py-xs text-neutral font-mono text-xs">
                      {formatAbsoluteTimestamp(startedAt)}
                    </td>

                    {/* State */}
                    <td className="px-sm py-xs">
                      {isFiring ? (
                        <span className="inline-flex items-center rounded-full bg-error/10 text-error px-2xs py-4xs text-xs font-medium">
                          Firing
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-neutral/10 text-neutral px-2xs py-4xs text-xs font-medium">
                          Acknowledged
                        </span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="px-sm py-xs text-right">
                      <div className="inline-flex items-center gap-xs">
                        <button
                          onClick={() => setSelectedAlert(toIAlert(da))}
                          className="flex items-center gap-2xs px-xs py-2xs text-sm font-medium text-primary hover:text-primary/80 transition-colors"
                        >
                          <Eye className="h-4 w-4" />
                          Details
                        </button>
                        {isFiring && (
                          <button
                            onClick={() =>
                              handleAcknowledge(da.data as FiringAlert)
                            }
                            disabled={isAcking}
                            className="flex items-center gap-2xs px-xs py-2xs text-sm font-medium text-success hover:text-success/80 transition-colors disabled:opacity-50"
                          >
                            <CheckCircle2 className="h-4 w-4" />
                            {isAcking ? "..." : "Ack"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Alert Details Modal */}
      {selectedAlert && (
        <AlertDetailsModal
          alert={selectedAlert}
          containerName={containerName}
          onJumpToLogs={() => {
            setSelectedAlert(null);
            onNavigateToLogs();
          }}
          onAcknowledge={() => {
            handleModalAcknowledge(selectedAlert);
          }}
          onClose={() => setSelectedAlert(null)}
          acknowledged={acknowledgingIds.has(selectedAlert.id || "")}
        />
      )}
    </div>
  );
}
