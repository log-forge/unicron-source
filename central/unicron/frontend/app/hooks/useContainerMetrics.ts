/**
 * Container Metrics Hook
 *
 * Subscribe to per-container metrics via the hub's multiplexed /ws/metrics endpoint.
 * The hook opens a dedicated WebSocket, subscribes to the requested container,
 * and returns the latest metrics frame (or null if none received).
 *
 * Simplified from LogForge's useContainerMetrics hook:
 * - Removed host identity canonicalization (not needed for Unicron)
 * - Removed host matchers logic
 * - Kept core WebSocket subscription pattern
 */

import { useEffect, useRef, useState, useMemo } from "react";

// ============================================================================
// Types
// ============================================================================

export interface ContainerMetrics {
  cpu_percent?: number;
  cpu_percent_host?: number;
  mem_bytes?: number;
  mem_limit?: number;
  mem_percent?: number;
  mem_percent_host?: number;
  net_rx_bytes?: number;
  net_tx_bytes?: number;
  net_rx_rate_bps?: number;
  net_tx_rate_bps?: number;
  blk_read_bytes?: number;
  blk_write_bytes?: number;
  blk_read_bps?: number;
  blk_write_bps?: number;
}

export type MetricsStatus = "idle" | "connecting" | "ready" | "error";

export interface UseContainerMetricsOptions {
  containerId?: string | null;
  containerName?: string | null;
  hostId?: string | null;
  enabled?: boolean;
}

export interface UseContainerMetricsResult {
  metrics: ContainerMetrics | null;
  status: MetricsStatus;
  lastUpdated?: number;
}

// ============================================================================
// Hook Implementation
// ============================================================================

export function useContainerMetrics({
  containerId,
  containerName,
  hostId,
  enabled = true,
}: UseContainerMetricsOptions): UseContainerMetricsResult {
  const [metrics, setMetrics] = useState<ContainerMetrics | null>(null);
  const [status, setStatus] = useState<MetricsStatus>("idle");
  const [lastUpdated, setLastUpdated] = useState<number | undefined>(undefined);
  const wsRef = useRef<WebSocket | null>(null);
  const expectedCloseRef = useRef(false);
  const subscriptionRef = useRef<{
    hostId?: string | null;
    containers: string[];
  }>({ containers: [] });

  // Determine if we can subscribe
  const canSubscribe = useMemo(() => {
    const hasIdentifier =
      Boolean(containerId?.trim()) || Boolean(containerName?.trim());
    return enabled && typeof window !== "undefined" && hasIdentifier;
  }, [containerId, containerName, enabled]);

  useEffect(() => {
    if (!canSubscribe) {
      setStatus(enabled ? "error" : "idle");
      setMetrics(null);
      expectedCloseRef.current = true;
      wsRef.current?.close(1000, "Metrics disabled");
      return;
    }

    // Build container identifiers array
    const containers: string[] = [];
    if (containerId) containers.push(containerId);
    if (containerName && containerName !== containerId)
      containers.push(containerName);
    if (containers.length === 0) {
      containers.push("*");
    }

    const prevSub = subscriptionRef.current;
    const prevContainers = Array.isArray(prevSub?.containers)
      ? prevSub.containers
      : [];
    const nextSub = { hostId, containers };
    subscriptionRef.current = nextSub;

    // Build WebSocket URL
    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsHostWithPort = window.location.host || window.location.hostname;
    const wsUrl = `${wsProtocol}://${wsHostWithPort}/ws/metrics`;

    const sendSubscribe = (socket: WebSocket) => {
      try {
        socket.send(
          JSON.stringify({
            type: "subscribe",
            host_id: subscriptionRef.current.hostId,
            containers: subscriptionRef.current.containers,
          })
        );
      } catch (err) {
        console.error("[ContainerMetrics] Failed to subscribe:", err);
        setStatus("error");
      }
    };

    const sendUnsubscribe = (socket: WebSocket, cont: string[]) => {
      if (!cont || cont.length === 0) return;
      try {
        socket.send(
          JSON.stringify({
            type: "unsubscribe",
            containers: cont,
          })
        );
      } catch {
        // ignore
      }
    };

    const ensureSocket = () => {
      const existing = wsRef.current;
      if (
        existing &&
        (existing.readyState === WebSocket.OPEN ||
          existing.readyState === WebSocket.CONNECTING)
      ) {
        return existing;
      }

      const socket = new WebSocket(wsUrl);
      wsRef.current = socket;
      setStatus("connecting");

      socket.onopen = () => {
        setStatus("connecting");
        sendSubscribe(socket);
      };

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          const targetIds = subscriptionRef.current.containers || [];

          // Check if message matches our subscription
          const matchesContainer =
            targetIds.includes("*") ||
            targetIds.includes(payload.container_id) ||
            targetIds.includes(payload.container_name);
          if (!matchesContainer) return;

          // Check host match (simple comparison, no canonicalization)
          const targetHost = subscriptionRef.current.hostId;
          if (targetHost && payload.host_id) {
            const normalizedTargetHost = targetHost.toLowerCase();
            const normalizedPayloadHost = String(payload.host_id).toLowerCase();
            if (normalizedTargetHost !== normalizedPayloadHost) {
              return;
            }
          }

          setMetrics(payload.metrics || null);
          setStatus("ready");
          setLastUpdated(Date.now());
        } catch (err) {
          console.warn("[ContainerMetrics] Failed to parse message", err);
        }
      };

      socket.onerror = (err) => {
        // Ignore errors triggered by intentional/expected closes
        if (
          expectedCloseRef.current ||
          socket.readyState === WebSocket.CLOSING ||
          socket.readyState === WebSocket.CLOSED
        ) {
          return;
        }
        console.warn("[ContainerMetrics] WebSocket error", err);
        setStatus("error");
      };

      socket.onclose = () => {
        if (!expectedCloseRef.current) {
          setStatus((prev) => (prev === "ready" ? "ready" : "error"));
        }
      };

      return socket;
    };

    // Reset before ensureSocket so reused CONNECTING sockets don't close on dep change
    expectedCloseRef.current = false;
    const socket = ensureSocket();

    // If the subscription changed and the socket is open, reissue subs without closing the connection
    const changedHost = prevSub.hostId !== nextSub.hostId;
    const changedContainers =
      prevContainers.length !== nextSub.containers.length ||
      prevContainers.some((c, idx) => c !== nextSub.containers[idx]);

    if (
      socket?.readyState === WebSocket.OPEN &&
      (changedHost || changedContainers)
    ) {
      sendUnsubscribe(socket, prevSub.containers);
      sendSubscribe(socket);
    }

    return () => {
      expectedCloseRef.current = true;
      const ws = wsRef.current;

      if (!ws) return;

      if (ws.readyState === WebSocket.OPEN) {
        // OPEN: unsubscribe, detach handlers, close, clear ref
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.onopen = null;
        try {
          sendUnsubscribe(ws, subscriptionRef.current.containers);
        } catch {
          // ignore
        }
        ws.close(1000, "Component unmounted");
        wsRef.current = null;
      } else if (ws.readyState === WebSocket.CONNECTING) {
        // CONNECTING: wrap onopen to check expectedCloseRef
        const originalOnopen = (ws as any).__originalOnopen ?? ws.onopen;
        (ws as any).__originalOnopen = originalOnopen;

        ws.onopen = (ev) => {
          if (expectedCloseRef.current) {
            // True unmount - close the socket
            ws.onmessage = null;
            ws.onerror = null;
            ws.onclose = null;
            ws.onopen = null;
            ws.close(1000, "Component unmounted");
            wsRef.current = null;
          } else if (originalOnopen) {
            // Dep change - new effect reset expectedCloseRef, proceed with subscribe
            originalOnopen.call(ws, ev);
          }
        };
      }
      // CLOSING/CLOSED: nothing to do
    };
  }, [canSubscribe, containerId, containerName, hostId, enabled]);

  return { metrics, status, lastUpdated };
}
