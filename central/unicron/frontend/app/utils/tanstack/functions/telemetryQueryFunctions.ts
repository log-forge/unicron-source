import { httpApp } from "../../http.client";
import { clientLog } from "../../logging/logger.client";
import type {
  ILogsQueryPayload,
  ILogsQueryResponse,
  IMetricsInstantPayload,
  IMetricsLabelNamesPayload,
  IMetricsLabelValuesPayload,
  IMetricsRangePayload,
  IVMApiResponse,
} from "../../../types/api/telemetry";
import type { IInventorySnapshotResponse } from "../../../types/api/telemetry/inventory.types";
import type { IVMFlatMatrixEntry, IVMFlatVectorEntry } from "../../../types/victoria/series.types";

export const getHeraldInventorySnapshot = async (): Promise<IInventorySnapshotResponse> => {
  const { status, data } = await httpApp.get("/telemetry/inventory/herald");
  if (status !== 200) throw new Error("Failed to fetch herald inventory snapshot");
  clientLog.debug({ data }, "Fetched herald inventory snapshot");

  return data as IInventorySnapshotResponse;
};

export const queryVictoriaLogs = async (payload: ILogsQueryPayload): Promise<ILogsQueryResponse> => {
  const { status, data } = await httpApp.post("/telemetry/victoria/logs/query", payload);
  if (status !== 200) throw new Error("Failed to run Victoria logs query");
  clientLog.debug({ rows: data?.rows?.length ?? 0, query: data?.query }, "Fetched Victoria logs query");

  return data as ILogsQueryResponse;
};

export type MetricsShape = "raw" | "flat";

export const queryVictoriaMetricsInstant = async (payload: IMetricsInstantPayload, shape: MetricsShape = "raw"): Promise<IVMApiResponse | IVMFlatVectorEntry[]> => {
  const { status, data } = await httpApp.post("/telemetry/victoria/metrics/query", payload, {
    params: { shape },
  });
  if (status !== 200) throw new Error("Failed to run Victoria metrics instant query");
  clientLog.debug({ shape, status: data?.status }, "Fetched Victoria metrics instant query");

  return data as IVMApiResponse | IVMFlatVectorEntry[];
};

export const queryVictoriaMetricsRange = async (payload: IMetricsRangePayload, shape: MetricsShape = "raw"): Promise<IVMApiResponse | IVMFlatMatrixEntry[]> => {
  const { status, data } = await httpApp.post("/telemetry/victoria/metrics/query_range", payload, {
    params: { shape },
  });
  if (status !== 200) throw new Error("Failed to run Victoria metrics range query");
  clientLog.debug({ shape, status: data?.status }, "Fetched Victoria metrics range query");

  return data as IVMApiResponse | IVMFlatMatrixEntry[];
};

export const getVictoriaMetricsLabelNames = async (payload: IMetricsLabelNamesPayload): Promise<string[]> => {
  const { status, data } = await httpApp.post("/telemetry/victoria/metrics/labels/names", payload);
  if (status !== 200) throw new Error("Failed to fetch Victoria metrics label names");
  clientLog.debug({ count: data?.length ?? 0 }, "Fetched Victoria metrics label names");

  return data as string[];
};

export const getVictoriaMetricsLabelValues = async (payload: IMetricsLabelValuesPayload): Promise<string[]> => {
  const { status, data } = await httpApp.post("/telemetry/victoria/metrics/labels/values", payload);
  if (status !== 200) throw new Error("Failed to fetch Victoria metrics label values");
  clientLog.debug({ count: data?.length ?? 0, label: payload.label }, "Fetched Victoria metrics label values");

  return data as string[];
};
