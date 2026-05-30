import type { IContainerSelector } from "../api/telemetry/telemetry.types";
import type { ILogRow } from "../victoria/logs.types";

export interface ILogsTailPayload extends IContainerSelector {
  filter?: string | null;
  start_offset?: string | null;
  offset?: string | null;
  refresh_interval?: string | null;
  account_id?: number | null;
  project_id?: number | null;
}

export interface ITailDataEvent {
  type: "logs:tail:data";
  row: ILogRow;
}

export interface ITailErrorEvent {
  type: "logs:tail:error";
  error: string;
}
