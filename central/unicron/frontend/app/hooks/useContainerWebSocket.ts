import { useEffect, useRef, useState } from "react";
import { useSocket } from "~/context/SocketContext";

export interface ContainerEvent {
  type:
    | "container_event"
    | "host_status"
    | "inventory_update"
    | "initial_state"
    | "monitoring_state_changed"
    | "log_collection_state_changed"
    | "telemetry_health";
  data: any;
}

interface UseContainerWebSocketResult {
  connected: boolean;
  authError: boolean;
}

const FEED_EVENT_MAP = {
  "containers:initial_state": "initial_state",
  "containers:event": "container_event",
  "containers:host_status": "host_status",
  "containers:inventory_update": "inventory_update",
  "containers:monitoring_state_changed": "monitoring_state_changed",
  "containers:log_collection_state_changed": "log_collection_state_changed",
  "containers:telemetry_health": "telemetry_health",
} as const;

export function useContainerWebSocket(
  onEvent: (events: ContainerEvent[]) => void
): UseContainerWebSocketResult {
  const { socket } = useSocket();
  const [connected, setConnected] = useState(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!socket) {
      setConnected(false);
      return;
    }

    const handlers = Object.entries(FEED_EVENT_MAP).map(([socketEvent, type]) => {
      const handler = (data: unknown) => onEventRef.current([{ type, data }]);
      socket.on(socketEvent as keyof typeof FEED_EVENT_MAP, handler as never);
      return { socketEvent, handler };
    });

    const handleConnect = () => {
      setConnected(true);
      socket.emit("containers:initial_state", {});
    };
    const handleDisconnect = () => setConnected(false);

    socket.on("connect", handleConnect);
    socket.on("disconnect", handleDisconnect);
    if (socket.connected) {
      handleConnect();
    }

    return () => {
      socket.off("connect", handleConnect);
      socket.off("disconnect", handleDisconnect);
      handlers.forEach(({ socketEvent, handler }) => {
        socket.off(socketEvent as keyof typeof FEED_EVENT_MAP, handler as never);
      });
    };
  }, [socket]);

  return { connected, authError: false };
}
