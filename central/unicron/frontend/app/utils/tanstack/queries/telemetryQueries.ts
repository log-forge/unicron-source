import { useIsFetching, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
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
import {
  HERALD_INVENTORY_QUERY_KEY,
  victoriaLogsQueryKey,
  victoriaMetricsLabelNamesKey,
  victoriaMetricsLabelValuesKey,
  victoriaMetricsQueryKey,
  victoriaMetricsRangeQueryKey,
} from "../queryKeys";
import {
  getHeraldInventorySnapshot,
  getVictoriaMetricsLabelNames,
  getVictoriaMetricsLabelValues,
  queryVictoriaLogs,
  queryVictoriaMetricsInstant,
  queryVictoriaMetricsRange,
  type MetricsShape,
} from "../functions/telemetryQueryFunctions";

/** Returns false for auth errors (401/403) to prevent infinite retry loops */
function shouldRetry(failureCount: number, error: Error, maxRetries: number): boolean {
  if (failureCount >= maxRetries) return false;
  if (isAxiosError(error)) {
    const status = error.response?.status;
    // Don't retry auth errors - they won't resolve by retrying
    if (status === 401 || status === 403) return false;
  }
  return true;
}

export function useHeraldInventorySnapshot(initialData?: IInventorySnapshotResponse, enabled: boolean = true) {
  const idle = useIsFetching({ queryKey: [...HERALD_INVENTORY_QUERY_KEY] }) === 0;
  return useQuery({
    queryKey: [...HERALD_INVENTORY_QUERY_KEY],
    queryFn: getHeraldInventorySnapshot,
    initialData,
    staleTime: 30 * 1000,
    // Retry up to 2 times, but not for auth errors
    retry: (failureCount, error) => shouldRetry(failureCount, error, 2),
    retryDelay: (attemptIndex) => Math.min(1500, 500 * 2 ** (attemptIndex - 1)),
    enabled: idle && enabled,
    refetchInterval: 1000 * 60 * 5,
    // If loader failed and gave an empty snapshot, don't refetch on mount to avoid loops
    refetchOnMount: false,
  });
}

export function invalidateHeraldInventorySnapshot(exact: boolean = true, client?: QueryClient) {
  const queryClient = client ?? useQueryClient();
  queryClient.invalidateQueries({ queryKey: [...HERALD_INVENTORY_QUERY_KEY], exact });
}

export function useVictoriaLogsQuery(payload: ILogsQueryPayload | null | undefined, enabled: boolean = true) {
  const serialized = payload ? JSON.stringify(payload) : null;

  return useQuery<ILogsQueryResponse>({
    queryKey: victoriaLogsQueryKey(serialized),
    queryFn: () => {
      if (!payload) throw new Error("Missing payload for Victoria logs query");
      return queryVictoriaLogs(payload);
    },
    enabled: Boolean(enabled && payload),
  });
}

export function useVictoriaMetricsInstantQuery(payload: IMetricsInstantPayload | null | undefined, shape: MetricsShape = "raw", enabled: boolean = true) {
  const serialized = payload ? JSON.stringify({ payload, shape }) : null;

  return useQuery<IVMApiResponse | IVMFlatVectorEntry[]>({
    queryKey: victoriaMetricsQueryKey(serialized, shape),
    queryFn: () => {
      if (!payload) throw new Error("Missing payload for Victoria metrics instant query");
      return queryVictoriaMetricsInstant(payload, shape);
    },
    enabled: Boolean(enabled && payload),
  });
}

export function useVictoriaMetricsRangeQuery(payload: IMetricsRangePayload | null | undefined, shape: MetricsShape = "raw", enabled: boolean = true) {
  const serialized = payload ? JSON.stringify({ payload, shape }) : null;

  return useQuery<IVMApiResponse | IVMFlatMatrixEntry[]>({
    queryKey: victoriaMetricsRangeQueryKey(serialized, shape),
    queryFn: () => {
      if (!payload) throw new Error("Missing payload for Victoria metrics range query");
      return queryVictoriaMetricsRange(payload, shape);
    },
    enabled: Boolean(enabled && payload),
  });
}

export function useVictoriaMetricsLabelNames(payload: IMetricsLabelNamesPayload | null | undefined, enabled: boolean = true) {
  const serialized = payload ? JSON.stringify(payload) : null;

  return useQuery<string[]>({
    queryKey: victoriaMetricsLabelNamesKey(serialized),
    queryFn: () => {
      if (!payload) throw new Error("Missing payload for Victoria metrics label names");
      return getVictoriaMetricsLabelNames(payload);
    },
    enabled: Boolean(enabled && payload),
    staleTime: 60 * 1000,
  });
}

export function useVictoriaMetricsLabelValues(payload: IMetricsLabelValuesPayload | null | undefined, enabled: boolean = true) {
  const serialized = payload ? JSON.stringify(payload) : null;

  return useQuery<string[]>({
    queryKey: victoriaMetricsLabelValuesKey(serialized),
    queryFn: () => {
      if (!payload) throw new Error("Missing payload for Victoria metrics label values");
      return getVictoriaMetricsLabelValues(payload);
    },
    enabled: Boolean(enabled && payload),
    staleTime: 60 * 1000,
  });
}
