import type { IContainerSelector } from "./telemetry.types";
import type { ILogRow } from "../../victoria/logs.types";

export interface ILogsQueryPayload extends IContainerSelector {
  expr?: string | null;
  where?: string | null;
  pipes?: string | null;
  start?: string | null;
  end?: string | null;
  limit?: number;
  account_id?: number | null;
  project_id?: number | null;
}

export interface ILogsQueryResponse {
  rows: ILogRow[];
  count: number;
  query: string;
}

export interface ILogsTailTestResponse {
  tail_expr: string;
}
