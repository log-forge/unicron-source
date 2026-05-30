import type { QueryClient } from "@tanstack/react-query";
import type { TypedSocket } from "../../context/SocketContext";
import type { HeraldRegisterEventData } from "../../types/socket/herald.types";
import { openAgentRefusalModalOnce, type AgentRefusalModalData } from "../../utils/agentRefusalModal";
import { clientLog } from "../../utils/logging/logger.client";
import { invalidateHeralds, invalidateHeraldsSummary } from "../../utils/tanstack/queries/heraldQueries";

type AgentRefusalModalStorage = Parameters<typeof openAgentRefusalModalOnce>[2];

export type OpenAgentRefusalModal = (refusal: AgentRefusalModalData) => void;

export type RegisterHandlerOptions = {
  openAgentRefusalModal?: OpenAgentRefusalModal;
  modalStorage?: AgentRefusalModalStorage;
};

export function handleRegister(socket: TypedSocket, queryClient: QueryClient, options: RegisterHandlerOptions = {}) {
  if (!socket) return;

  socket.off("herald:registered");

  socket.on("herald:registered", (data: HeraldRegisterEventData) => {
    clientLog.info({ data }, "Herald registered");

    if (data.status === "failed") {
      clientLog.error({ heraldId: data.herald_id }, "Herald registration failed");
      if (data.reason) clientLog.error({ reason: data.reason }, "Herald registration failed reason");
      if (options.openAgentRefusalModal) {
        openAgentRefusalModalOnce(data, options.openAgentRefusalModal, options.modalStorage);
      }
    } else if (data.status === "healthy") {
      clientLog.info({ heraldId: data.herald_id, heraldName: data.herald_name }, "Herald successfully registered");
    }

    invalidateHeralds(true, queryClient);
    invalidateHeraldsSummary(true, queryClient);
    queryClient.invalidateQueries({ queryKey: ["agents"], exact: true });
  });
}
