/**
 * useHostStatus Hook
 *
 * Derives host display status from visible containers and optional authoritative
 * host presence from backend overview payload.
 *
 * Online/offline should come from backend host status when provided.
 */

import { useMemo } from "react";
import type { ContainerInfo } from "../components/containers";

export interface HostStatus {
  hostId: string;
  isOnline: boolean;
  lastSeen: string | null;
  containerCount: number;
  runningCount: number;
}

export interface AuthoritativeHostStatus {
  online: boolean;
  last_seen?: string;
}

export function useHostStatus(
  containers: ContainerInfo[],
  authoritativeHostStatuses?: Record<string, AuthoritativeHostStatus>
): Map<string, HostStatus> {
  return useMemo(() => {
    const hostMap = new Map<string, HostStatus>();

    containers.forEach((container) => {
      const hostId = container.host_id || "local";
      const lastSeenMs = container.last_seen ? new Date(container.last_seen).getTime() : 0;
      const isRunning = (container as { status?: string }).status === "running";

      const existing = hostMap.get(hostId);

      if (existing) {
        // Update if this container was seen more recently
        const existingLastSeenMs = existing.lastSeen
          ? new Date(existing.lastSeen).getTime()
          : 0;

        if (lastSeenMs > existingLastSeenMs) {
          existing.lastSeen = container.last_seen;
        }

        existing.containerCount += 1;
        if (isRunning) existing.runningCount += 1;
      } else {
        hostMap.set(hostId, {
          hostId,
          // Default to offline until authoritative host status is applied.
          isOnline: false,
          lastSeen: container.last_seen || null,
          containerCount: 1,
          runningCount: isRunning ? 1 : 0,
        });
      }
    });

    if (authoritativeHostStatuses) {
      Object.entries(authoritativeHostStatuses).forEach(([hostId, status]) => {
        const existing = hostMap.get(hostId);
        if (existing) {
          existing.isOnline = status.online;
          if (status.last_seen) {
            existing.lastSeen = status.last_seen;
          }
          return;
        }

        hostMap.set(hostId, {
          hostId,
          isOnline: status.online,
          lastSeen: status.last_seen || null,
          containerCount: 0,
          runningCount: 0,
        });
      });
    }

    return hostMap;
  }, [containers, authoritativeHostStatuses]);
}

export function getHostStatus(
  hostStatuses: Map<string, HostStatus>,
  hostId: string
): HostStatus {
  return hostStatuses.get(hostId) ?? {
    hostId,
    isOnline: false,
    lastSeen: null,
    containerCount: 0,
    runningCount: 0,
  };
}

export default useHostStatus;
