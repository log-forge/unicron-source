/**
 * useContainerAlertSummary - Per-container severity breakdown from AlertStore.
 *
 * Returns a Map keyed by containerKey (host_id:container_name) with each
 * container's total alert count, highest severity, and severity breakdown.
 *
 * Uses useSyncExternalStore to subscribe to the AlertStore singleton.
 * Only recomputes when the store version changes (useRef memoization pattern
 * matching useAlertCounts.ts).
 *
 * Phase 65-01: Created for severity-aware alert pill rendering.
 */

import { useSyncExternalStore, useRef } from "react";
import { alertStore } from "~/context/AlertContext";
import type { FiringAlert } from "~/context/AlertContext";

// ============================================================================
// Types
// ============================================================================

export interface ContainerAlertSummary {
  totalCount: number;
  totalOccurrences: number;
  maxOccurrence: number;
  highestSeverity: "critical" | "warning" | "info";
  breakdown: { critical: number; warning: number; info: number };
}

// ============================================================================
// Severity Priority
// ============================================================================

/** Higher number = higher priority. Used to determine highestSeverity. */
const SEVERITY_PRIORITY: Record<string, number> = {
  info: 0,
  warning: 1,
  critical: 2,
};

function higherSeverity(
  a: "critical" | "warning" | "info",
  b: "critical" | "warning" | "info"
): "critical" | "warning" | "info" {
  return (SEVERITY_PRIORITY[a] ?? 0) >= (SEVERITY_PRIORITY[b] ?? 0) ? a : b;
}

// ============================================================================
// Hook
// ============================================================================

export function useContainerAlertSummary(): Map<string, ContainerAlertSummary> {
  const snapshot = useSyncExternalStore(
    alertStore.subscribe.bind(alertStore),
    () => alertStore.getSnapshot(),
    () => alertStore.getSnapshot()
  );

  const prevRef = useRef<{
    version: number;
    result: Map<string, ContainerAlertSummary>;
  }>({
    version: -1,
    result: new Map(),
  });

  if (prevRef.current.version !== snapshot.version) {
    const result = new Map<string, ContainerAlertSummary>();

    for (const [containerKey, alertIds] of snapshot.byContainer) {
      const breakdown = { critical: 0, warning: 0, info: 0 };
      let highest: "critical" | "warning" | "info" = "info";
      let totalOccurrences = 0;
      let maxOccurrence = 1;

      for (const alertId of alertIds) {
        const alert: FiringAlert | undefined = snapshot.alerts.get(alertId);
        if (!alert) continue;

        const alertCount = Number.isFinite(alert.count) && alert.count > 0
          ? Math.trunc(alert.count)
          : 1;
        totalOccurrences += alertCount;
        if (alertCount > maxOccurrence) {
          maxOccurrence = alertCount;
        }

        const sev = alert.severity;
        if (sev in breakdown) {
          breakdown[sev]++;
        }
        highest = higherSeverity(highest, sev);
      }

      const totalCount = breakdown.critical + breakdown.warning + breakdown.info;
      if (totalCount > 0) {
        result.set(containerKey, {
          totalCount,
          totalOccurrences,
          maxOccurrence,
          highestSeverity: highest,
          breakdown,
        });
      }
    }

    prevRef.current = { version: snapshot.version, result };
  }

  return prevRef.current.result;
}
