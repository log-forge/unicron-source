import type { QueryClient } from "@tanstack/react-query";
import type { TypedSocket } from "../../context/SocketContext";
import { handleRegister, type OpenAgentRefusalModal } from "./registerHandler";
import { handleTelemetry } from "./telemetryHandler";

export default function registerHandlers(
  socket: TypedSocket,
  queryClient: QueryClient,
  openAgentRefusalModal?: OpenAgentRefusalModal,
) {
  if (!socket || !queryClient) return;

  // Register the herald registration handler
  handleRegister(socket, queryClient, { openAgentRefusalModal });

  // Register telemetry listeners
  handleTelemetry(socket, queryClient);
}

// Alert-related consumers now ride on the shared Socket.IO container/telemetry
// event layer rather than a separate raw browser websocket path.
