import type { QueryClient } from "@tanstack/react-query";
import type { TypedSocket } from "../../context/SocketContext";
import type { IHeraldHealthEventPayload } from "../../types/socket/herald.types";
import type { ILogsTailPayload, ITailDataEvent, ITailErrorEvent } from "../../types/socket/telemetry.types";
import { clientLog } from "../../utils/logging/logger.client";
import {
  appendLogsTailRow,
  applyHeraldHealthUpdate,
  buildLogsTailQueryKey,
  clearLogsTailCache,
  type LogsTailQueryKey,
} from "../../utils/tanstack/functions/telemetryCacheUpdaters";
import { invalidateHeralds, invalidateHeraldsSummary } from "../../utils/tanstack/queries/heraldQueries";
import { invalidateHeraldInventorySnapshot } from "../../utils/tanstack/queries/telemetryQueries";
import { startLogsTail, stopLogsTail } from "../emitter/logsTail";
import { LOGS_TAIL_DATA_EVENT, LOGS_TAIL_ERROR_EVENT } from "../socketConstants";

type LogsTailContext = {
  payload: ILogsTailPayload;
  key: LogsTailQueryKey;
};

let activeLogsTail: LogsTailContext | null = null;

export function handleTelemetry(socket: TypedSocket, queryClient: QueryClient) {
  if (!socket) return;

  socket.off("herald:health");

  socket.on("herald:health", (payload: IHeraldHealthEventPayload) => {
    clientLog.debug({ payload }, "Received herald health event");

    try {
      applyHeraldHealthUpdate(queryClient, payload);
    } catch (error) {
      clientLog.error({ err: error }, "Failed to apply herald health update");
      invalidateHeralds(true, queryClient);
      invalidateHeraldsSummary(true, queryClient);
      invalidateHeraldInventorySnapshot(true, queryClient);
    }
  });

  socket.off(LOGS_TAIL_DATA_EVENT);
  socket.off(LOGS_TAIL_ERROR_EVENT);

  socket.on(LOGS_TAIL_DATA_EVENT, (event: ITailDataEvent) => {
    if (!activeLogsTail) {
      clientLog.warn({ hasActiveTail: false }, "Received logs tail data without an active tail; ignoring");
      return;
    }

    const { payload, key } = activeLogsTail;
    const expectedId = payload.container_key ?? null;
    const actualId = event.row.container_key ?? null;

    const idMatches = expectedId && actualId && (actualId === expectedId || actualId.startsWith(expectedId) || expectedId.startsWith(actualId));

    if (expectedId && !idMatches) {
      clientLog.debug(
        {
          expectedId,
          actualId,
        },
        "Logs tail data container mismatch; skipping row",
      );
      return;
    }

    appendLogsTailRow(queryClient, key, event.row);
  });

  socket.on(LOGS_TAIL_ERROR_EVENT, (event: ITailErrorEvent) => {
    clientLog.error({ err: event.error }, "Logs tail error");
  });
}

export function startVictoriaLogsTail(socket: TypedSocket, queryClient: QueryClient, payload: ILogsTailPayload): void {
  if (activeLogsTail) {
    if (socket) {
      stopLogsTail(socket);
    }
    clearLogsTailCache(queryClient, activeLogsTail.key);
    activeLogsTail = null;
  }

  const key = buildLogsTailQueryKey(payload);
  activeLogsTail = { payload, key };
  clearLogsTailCache(queryClient, key);
  if (socket) {
    startLogsTail(socket, payload);
  }
}

export function stopVictoriaLogsTail(socket: TypedSocket, queryClient: QueryClient): void {
  if (socket) {
    stopLogsTail(socket);
  }
  if (activeLogsTail) {
    clearLogsTailCache(queryClient, activeLogsTail.key);
    activeLogsTail = null;
  }
}

export function clearActiveLogsTailCache(queryClient: QueryClient): void {
  if (!activeLogsTail) return;
  clearLogsTailCache(queryClient, activeLogsTail.key);
  activeLogsTail = null;
}
