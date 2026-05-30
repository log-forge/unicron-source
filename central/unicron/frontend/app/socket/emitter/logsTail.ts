import type { TypedSocket } from "../../context/SocketContext";
import { LOGS_TAIL_START_EVENT, LOGS_TAIL_STOP_EVENT } from "../socketConstants";
import type { ILogsTailPayload } from "../../types/socket/telemetry.types";

export function startLogsTail(socket: TypedSocket, payload: ILogsTailPayload): void {
  if (!socket) return;
  socket.emit(LOGS_TAIL_START_EVENT, payload);
}

export function stopLogsTail(socket: TypedSocket | null): void {
  if (!socket) return;
  socket.emit(LOGS_TAIL_STOP_EVENT);
}
