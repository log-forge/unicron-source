/**
 * useTotalAlerts - Granular hook for total firing alert count.
 *
 * Returns the total number of currently firing alerts.
 * Lightweight hook for components that only need the count (e.g., badges, pills).
 *
 * Uses useSyncExternalStore to subscribe to the AlertStore singleton.
 */

import { useSyncExternalStore } from "react";
import { alertStore } from "~/context/AlertContext";

export function useTotalAlerts(): number {
  const snapshot = useSyncExternalStore(
    alertStore.subscribe.bind(alertStore),
    () => alertStore.getSnapshot(),
    () => alertStore.getSnapshot()
  );

  return snapshot.totalAlerts;
}
