/**
 * useAlertCounts - Granular hook for alert severity counts and connection status.
 *
 * Returns totalAlerts, alertsBySeverity breakdown, alertsPerContainer counts,
 * and connection status (isConnected, isStale).
 *
 * Uses useSyncExternalStore to subscribe to the AlertStore singleton.
 * Only re-renders when the store version changes.
 */

import { useSyncExternalStore, useRef } from "react";
import { alertStore } from "~/context/AlertContext";

interface AlertCounts {
  totalAlerts: number;
  alertsBySeverity: { critical: number; warning: number; info: number };
  alertsPerContainer: Map<string, number>;
  isConnected: boolean;
  isStale: boolean;
}

export function useAlertCounts(): AlertCounts {
  const snapshot = useSyncExternalStore(
    alertStore.subscribe.bind(alertStore),
    () => alertStore.getSnapshot(),
    () => alertStore.getSnapshot()
  );

  const prevRef = useRef<{ version: number; result: AlertCounts }>({
    version: -1,
    result: {
      totalAlerts: 0,
      alertsBySeverity: { critical: 0, warning: 0, info: 0 },
      alertsPerContainer: new Map(),
      isConnected: false,
      isStale: false,
    },
  });

  if (prevRef.current.version !== snapshot.version) {
    prevRef.current = {
      version: snapshot.version,
      result: {
        totalAlerts: snapshot.totalAlerts,
        alertsBySeverity: snapshot.alertsBySeverity,
        alertsPerContainer: snapshot.alertsPerContainer,
        isConnected: snapshot.isConnected,
        isStale: snapshot.isStale,
      },
    };
  }

  return prevRef.current.result;
}
