import { io, type Socket } from "socket.io-client";
import { resolveSocketEndpoint } from "~/socket/resolveSocketEndpoint";
import type { ClientToServerEvents, ServerToClientEvents } from "~/socket/socket.types";
import { ALERT_EVENTS } from "~/socket/events/alerts";
import { feDebug } from "../constants";

type WebSocketMessage = {
  type:
    | "group_created"
    | "group_updated"
    | "group_deleted"
    | "containers:inventory_update"
    | "containers:event"
    | "containers:monitoring_state_changed"
    | typeof ALERT_EVENTS.FIRED
    | "alert:stacked"
    | "alert:state_changed";
  data: any;
};

type EventCallback = (data: any) => void;

class GlobalWebSocketService {
  private static instance: GlobalWebSocketService | null = null;
  private socket: Socket<ServerToClientEvents, ClientToServerEvents> | null = null;
  private connected = false;
  private eventListeners = new Map<string, Set<EventCallback>>();
  private connectionListeners = new Set<(connected: boolean) => void>();

  static getInstance(): GlobalWebSocketService {
    if (!GlobalWebSocketService.instance) {
      GlobalWebSocketService.instance = new GlobalWebSocketService();
    }
    return GlobalWebSocketService.instance;
  }

  private ensureSocket() {
    if (this.socket || typeof window === "undefined") return;
    const { url, path } = resolveSocketEndpoint();
    this.socket = io(url, {
      path,
      withCredentials: true,
      transports: ["websocket", "polling"],
      autoConnect: true,
    }) as Socket<ServerToClientEvents, ClientToServerEvents>;

    const forward = (type: WebSocketMessage["type"]) => (data: any) => {
      const listeners = this.eventListeners.get(type);
      if (listeners) {
        listeners.forEach((callback) => callback({ type, data }));
      }
    };

    this.socket.on("connect", () => {
      this.connected = true;
      this.connectionListeners.forEach((callback) => callback(true));
      this.socket?.emit("containers:initial_state", {});
    });
    this.socket.on("disconnect", () => {
      this.connected = false;
      this.connectionListeners.forEach((callback) => callback(false));
    });
    this.socket.on(ALERT_EVENTS.FIRED, forward(ALERT_EVENTS.FIRED));
    this.socket.on("alert:stacked", forward("alert:stacked"));
    this.socket.on("alert:state_changed", forward("alert:state_changed"));
    this.socket.on("containers:monitoring_state_changed", forward("containers:monitoring_state_changed"));
    this.socket.on("containers:inventory_update", forward("containers:inventory_update"));
    this.socket.on("containers:event", forward("containers:event"));
  }

  onConnectionChange(callback: (connected: boolean) => void): () => void {
    this.ensureSocket();
    this.connectionListeners.add(callback);
    callback(this.connected);
    return () => {
      this.connectionListeners.delete(callback);
    };
  }

  on(eventType: string, callback: EventCallback): () => void {
    this.ensureSocket();
    if (!this.eventListeners.has(eventType)) {
      this.eventListeners.set(eventType, new Set());
    }
    this.eventListeners.get(eventType)?.add(callback);

    return () => {
      const listeners = this.eventListeners.get(eventType);
      if (!listeners) return;
      listeners.delete(callback);
      if (listeners.size === 0) {
        this.eventListeners.delete(eventType);
      }
    };
  }

  isConnected(): boolean {
    return this.connected;
  }

  disconnect() {
    if (feDebug()) console.log("[Socket.IO] Manually disconnecting alert socket");
    this.socket?.disconnect();
    this.socket = null;
    this.connected = false;
  }
}

export const globalWebSocket = GlobalWebSocketService.getInstance();
