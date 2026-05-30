import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { io } from "socket.io-client";
import type { Socket } from "socket.io-client";
import { resolveSocketEndpoint } from "../socket/resolveSocketEndpoint";
import registerHandlers from "../socket/events";
import { clearActiveLogsTailCache } from "../socket/events/telemetryHandler";
import type { ClientToServerEvents, PingAck, ServerToClientEvents } from "../socket/socket.types";
import { HERALD_INVENTORY_QUERY_KEY, HERALD_LIST_QUERY_KEY, HERALD_SUMMARY_QUERY_KEY } from "../utils/tanstack/queryKeys";
import { clientLog } from "../utils/logging/logger.client";
import { clientEnv } from "../utils/env.client";
import { useAuth } from "./AuthContext";
import { useModal } from "./ModalContext";
import AgentRefusalModal from "../components/agents/AgentRefusalModal";
import { buildAgentRefusalModalKey, type AgentRefusalModalData } from "../utils/agentRefusalModal";

/* ---------- Type‑safe socket instance ---------- */
export type TypedSocket = Socket<ServerToClientEvents, ClientToServerEvents> | null;

/* React context carries the (lazy) socket or null during SSR */
const SocketContext = createContext<{ socket: TypedSocket; isClient: boolean }>({ socket: null, isClient: false });
export default SocketContext;

/* ---------- Provider: exactly one per tab ---------- */
export function SocketProvider({ children }: { children: React.ReactNode }) {
  // SSR guard: do not render or create socket on server
  const isClient = typeof window !== "undefined";
  const { isAuthenticated } = useAuth();
  const canConnect = isAuthenticated;
  const [online, setOnline] = useState<boolean | null>(null);
  const queryClient = useQueryClient();
  const { openModal } = useModal();

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

  // Only create socket on client
  const socket = useMemo<TypedSocket>(() => {
    if (!isClient || !canConnect) return null;

    const { url, path } = resolveSocketEndpoint();
    return io(url, {
      path,
      withCredentials: true,
      transports: ["websocket", "polling"],
      autoConnect: true,
      reconnection: true,
      reconnectionAttempts: 5,
    }) as Socket<ServerToClientEvents, ClientToServerEvents>;
  }, [isClient, canConnect]);

  useEffect(() => {
    if (canConnect) return;
    setOnline(null);
  }, [canConnect]);

  useEffect(() => {
    if (!socket) return;

    socket.connect();
    let heartbeatTimer: number | null = null;

    const sendPing = () => {
      clientLog.debug({ event: "ping" }, "Sending ping to server");
      socket.timeout(5000).emit("ping", (err, resp: PingAck) => {
        if (err) {
          clientLog.error({ err }, "Ping failed");
          return;
        }
        if (resp.ok) clientLog.debug({ message: resp.data?.msg }, "Received pong");
        else clientLog.error({ error: resp.error?.[0] }, "Ping acknowledged with error");
      });
    };

    const handleConnect = () => {
      setOnline(true);
      clientLog.info({ event: "connect" }, "Socket connected");

      // Keep the browser lease fresh so Central can reap orphaned edge sessions after replica loss.
      sendPing();
      if (heartbeatTimer !== null) {
        window.clearInterval(heartbeatTimer);
      }
      heartbeatTimer = window.setInterval(sendPing, 20000);

      setTimeout(() => setOnline(null), 1200);
    };

    const handleDisconnect = (reason: string) => {
      if (heartbeatTimer !== null) {
        window.clearInterval(heartbeatTimer);
        heartbeatTimer = null;
      }
      setOnline(false);
      clientLog.warn({ reason }, "Socket disconnected");
      clearActiveLogsTailCache(queryClient);
      queryClient.invalidateQueries({ queryKey: [...HERALD_LIST_QUERY_KEY], exact: true });
      queryClient.invalidateQueries({ queryKey: [...HERALD_SUMMARY_QUERY_KEY], exact: true });
      queryClient.invalidateQueries({ queryKey: [...HERALD_INVENTORY_QUERY_KEY], exact: true });
    };

    const handleReconnect = (attempt: number) => {
      clientLog.info({ attempt }, "Socket reconnected");
      queryClient.invalidateQueries({ queryKey: [...HERALD_LIST_QUERY_KEY], exact: false });
      queryClient.invalidateQueries({ queryKey: [...HERALD_SUMMARY_QUERY_KEY], exact: false });
      queryClient.invalidateQueries({ queryKey: [...HERALD_INVENTORY_QUERY_KEY], exact: false });
    };

    socket.on("connect", handleConnect);
    socket.on("disconnect", handleDisconnect);
    socket.io.on("reconnect", handleReconnect);

    if (isClient && clientEnv.VITE_NODE_ENV !== "production") {
      socket.onAny((event, ...args) => {
        try {
          console.log("[WS]", event, args);
        } catch {}
        clientLog.debug({ event, args }, "Socket event");
      });
    }

    registerHandlers(socket, queryClient, openAgentRefusalModal);

    return () => {
      if (heartbeatTimer !== null) {
        window.clearInterval(heartbeatTimer);
      }
      socket.off("connect", handleConnect);
      socket.off("disconnect", handleDisconnect);
      socket.io.off("reconnect", handleReconnect);
      socket.disconnect();
      clearActiveLogsTailCache(queryClient);
      clientLog.info({ event: "disconnect", cleanup: true }, "Socket disconnected (cleanup)");
    };
  }, [socket, isClient, queryClient, openAgentRefusalModal]);

  // During SSR, render children without socket context or ribbon
  if (!isClient) {
    return <SocketContext.Provider value={{ socket: null, isClient: false }}>{children}</SocketContext.Provider>;
  }

  return (
    <>
      {online !== null && (
        <div className={`fixed inset-x-0 top-0 z-50 flex justify-center py-sm text-2xs font-semibold text-neutral-text transition-all duration-300`}>
          {online ? "Connected" : "Disconnected – retrying…"}
        </div>
      )}
      <SocketContext.Provider value={{ socket, isClient }}>{children}</SocketContext.Provider>
    </>
  );
}

export const useSocket = () => useContext(SocketContext);
