import type { HeraldRegisterEventData, IHeraldHealthEventPayload } from "../types/socket/herald.types";
import type { ILogsTailPayload, ITailDataEvent, ITailErrorEvent } from "../types/socket/telemetry.types";

export type AckOk<T> = { ok: true; data?: T };
export type AckErr<T = string> = { ok: false; error?: Array<T> };
export type Ack<T = string, K = string> = AckOk<T> | AckErr<K>;

export type PingAck = Ack<{ msg: string }>;

export interface ContainerFeedEventPayload {
  host_id?: string;
  container_key?: string;
  docker_container_id?: string | null;
  name?: string;
  status?: string | null;
  action?: string;
  monitoring_enabled?: boolean;
  healthy?: boolean;
  timestamp?: number;
  containers?: Array<Record<string, unknown>>;
  monitoring_states?: Record<string, boolean>;
  [key: string]: unknown;
}

export interface ContainerLiveLogPayload {
  container_key?: string;
  row?: Record<string, unknown>;
  message?: string;
  timestamp?: string;
  type?: string;
  error?: string;
}

export interface ServerToClientEvents {
  "alert:fired": (data: Record<string, unknown>) => void;
  "alert:stacked": (data: Record<string, unknown>) => void;
  "alert:state_changed": (data: Record<string, unknown>) => void;
  "herald:registered": (data: HeraldRegisterEventData) => void;
  "herald:health": (data: IHeraldHealthEventPayload) => void;
  "logs:tail:data": (event: ITailDataEvent) => void;
  "logs:tail:error": (event: ITailErrorEvent) => void;
  "containers:initial_state": (data: ContainerFeedEventPayload) => void;
  "containers:event": (data: ContainerFeedEventPayload) => void;
  "containers:host_status": (data: ContainerFeedEventPayload) => void;
  "containers:inventory_update": (data: ContainerFeedEventPayload) => void;
  "containers:monitoring_state_changed": (data: ContainerFeedEventPayload) => void;
  "containers:log_collection_state_changed": (data: ContainerFeedEventPayload) => void;
  "containers:telemetry_health": (data: ContainerFeedEventPayload) => void;
  "containers:stats:data": (data: Record<string, unknown>) => void;
  "containers:logs:data": (data: ContainerLiveLogPayload) => void;
  "containers:files:response": (data: Record<string, unknown>) => void;
  "containers:terminal:data": (data: Record<string, unknown>) => void;
  error: AckErr<any>;
}

export interface ClientToServerEvents {
  ping: (cb: (resp: PingAck) => void) => void;
  "logs:tail:start": (payload: ILogsTailPayload) => void;
  "logs:tail:stop": () => void;
  "containers:initial_state": (payload?: Record<string, unknown>) => void;
  "containers:stats:subscribe": (payload: { container_key: string; host_id: string }) => void;
  "containers:stats:unsubscribe": (payload: { container_key: string }) => void;
  "containers:logs:start": (
    payload: {
      container_key: string;
      host_id: string;
      history_tail?: string;
      history_since?: string;
    },
    cb?: (resp: { session_id?: string }) => void,
  ) => void;
  "containers:logs:stop": (payload: { session_id: string }) => void;
  "containers:files:request": (
    payload: { container_key: string; host_id: string; action: "list" | "read"; path: string },
    cb?: (resp: { request_id?: string }) => void,
  ) => void;
  "containers:terminal:start": (
    payload: { container_key: string; host_id: string; rows?: number; cols?: number },
    cb?: (resp: { session_id?: string }) => void,
  ) => void;
  "containers:terminal:input": (payload: { session_id: string; data: string }) => void;
  "containers:terminal:resize": (payload: { session_id: string; rows: number; cols: number }) => void;
  "containers:terminal:stop": (payload: { session_id: string }) => void;
}

export interface InterServerEvents {}

export interface SocketData {}
