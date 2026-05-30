/**
 * useContainerAlerts - Granular hook for per-container alert slice.
 *
 * Returns only alerts for a specific container identified by composite key
 * (host_id:container_name). Re-renders only when that container's alerts change.
 *
 * Uses useSyncExternalStore to subscribe to the AlertStore singleton.
 *
 * @param containerKey - Composite key: `${host_id}:${container_name}`
 * @returns Array of FiringAlert objects for that container
 */

import { useSyncExternalStore, useRef } from "react";
import { alertStore } from "~/context/AlertContext";
import type { FiringAlert } from "~/context/AlertContext";

export function useContainerAlerts(containerKey: string): FiringAlert[] {
  const snapshot = useSyncExternalStore(
    alertStore.subscribe.bind(alertStore),
    () => alertStore.getSnapshot(),
    () => alertStore.getSnapshot()
  );

  const prevRef = useRef<{ version: number; containerKey: string; result: FiringAlert[] }>({
    version: -1,
    containerKey: "",
    result: [],
  });

  if (prevRef.current.version !== snapshot.version || prevRef.current.containerKey !== containerKey) {
    const alertIds = snapshot.byContainer.get(containerKey);
    const result = alertIds
      ? Array.from(alertIds)
          .map((id) => snapshot.alerts.get(id))
          .filter((a): a is FiringAlert => a !== undefined)
      : [];
    prevRef.current = { version: snapshot.version, containerKey, result };
  }

  return prevRef.current.result;
}
