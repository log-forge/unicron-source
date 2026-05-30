import type { QueryClient } from "@tanstack/react-query";
import { clientLog } from "../../logging/logger.client";
import type { IHerald, IHeraldsSummary } from "../../../types/api/queries/heraldQueries.types";
import type { IInventorySnapshotResponse } from "../../../types/api/telemetry/inventory.types";
import type { ILogRow } from "../../../types/victoria/logs.types";
import type { IHeraldHealthEventPayload } from "../../../types/socket/herald.types";
import type { ILogsTailPayload } from "../../../types/socket/telemetry.types";
import { HERALD_INVENTORY_QUERY_KEY, HERALD_LIST_QUERY_KEY, HERALD_SUMMARY_QUERY_KEY, TELEMETRY_LOGS_QUERY_KEY } from "../queryKeys";

export const LOGS_TAIL_BUFFER_LIMIT = 500;

function coalesceStatus(value: string | undefined): string {
  if (!value || value.trim().length === 0) return "unknown";
  return value;
}

function buildSummary(heralds: IHerald[], previous?: IHeraldsSummary): IHeraldsSummary {
  const statuses: Record<string, number> = {};
  const groups: Record<string, number> = previous?.groups ? { ...previous.groups } : {};
  const regions: Record<string, number> = {};
  let latestPing: string | null = null;
  let socketOnlineTotal = 0;

  for (const herald of heralds) {
    const statusKey = coalesceStatus(herald.health_status);
    statuses[statusKey] = (statuses[statusKey] ?? 0) + 1;

    if (herald.socket_online) {
      socketOnlineTotal += 1;
    }
    if (herald.region) {
      regions[herald.region] = (regions[herald.region] ?? 0) + 1;
    }
    if (herald.last_ping) {
      if (!latestPing) {
        latestPing = herald.last_ping;
      } else {
        const currentTs = Date.parse(herald.last_ping);
        const storedTs = Date.parse(latestPing);
        if (!Number.isNaN(currentTs) && (Number.isNaN(storedTs) || currentTs > storedTs)) {
          latestPing = herald.last_ping;
        }
      }
    }
  }

  return {
    total: heralds.length,
    statuses,
    last_ping_latest: latestPing,
    socket_online_total: socketOnlineTotal,
    groups,
    regions,
  };
}

function updateHeraldList(queryClient: QueryClient, payload: IHeraldHealthEventPayload): { updated: boolean; data?: IHerald[] } {
  let updated = false;
  const next = queryClient.setQueryData<IHerald[] | undefined>([...HERALD_LIST_QUERY_KEY], (prev) => {
    if (!prev) return prev;

    const idx = prev.findIndex((herald) => herald.herald_id === payload.herald_id);
    if (idx === -1) return prev;

    const cloned = prev.slice();
    const current = cloned[idx];

    cloned[idx] = {
      ...current,
      herald_name: payload.herald_name ?? current.herald_name,
      health_status: payload.status ?? current.health_status,
      health_message: payload.message ?? current.health_message,
      last_ping: payload.last_ping ?? current.last_ping,
      registered_at: payload.registered_at ?? current.registered_at,
      central_url: payload.central_url ?? current.central_url,
      check_in_interval: payload.check_in_interval ?? current.check_in_interval,
      socket_online: payload.socket_online ?? current.socket_online,
      socket_last_seen: payload.socket_last_seen ?? current.socket_last_seen,
      region: payload.region ?? current.region,
      tags: payload.tags ? [...payload.tags] : current.tags,
      herald_version: payload.herald_version ?? current.herald_version,
      hostname: payload.hostname ?? current.hostname,
      herald_os: payload.herald_os ?? current.herald_os,
      os_version: payload.os_version ?? current.os_version,
      architecture: payload.architecture ?? current.architecture,
      cpu_count: payload.cpu_count ?? current.cpu_count,
      host_total_memory_bytes: payload.host_total_memory_bytes ?? current.host_total_memory_bytes,
    };

    updated = true;
    return cloned;
  });

  return { updated, data: next };
}

function updateInventorySnapshot(queryClient: QueryClient, payload: IHeraldHealthEventPayload): { updated: boolean } {
  let updated = false;
  queryClient.setQueryData<IInventorySnapshotResponse | undefined>([...HERALD_INVENTORY_QUERY_KEY], (prev) => {
    if (!prev) return prev;
    const idx = prev.heralds.findIndex((record) => record.herald_id === payload.herald_id);
    if (idx === -1) return prev;

    const heralds = prev.heralds.slice();
    const current = heralds[idx];

    heralds[idx] = {
      ...current,
      herald_name: payload.herald_name ?? current.herald_name,
      health_status: payload.status ?? current.health_status,
      health_message: payload.message ?? current.health_message,
      last_ping: payload.last_ping ?? current.last_ping,
      registered_at: payload.registered_at ?? current.registered_at,
      check_in_interval: payload.check_in_interval ?? current.check_in_interval,
      socket_online: payload.socket_online ?? current.socket_online,
      socket_last_seen: payload.socket_last_seen ?? current.socket_last_seen,
      region: payload.region ?? current.region,
      tags: payload.tags ? [...payload.tags] : current.tags,
      central_url: payload.central_url ?? current.central_url,
      herald_version: payload.herald_version ?? current.herald_version,
      hostname: payload.hostname ?? current.hostname,
      herald_os: payload.herald_os ?? current.herald_os,
      os_version: payload.os_version ?? current.os_version,
      architecture: payload.architecture ?? current.architecture,
      cpu_count: payload.cpu_count ?? current.cpu_count,
      host_total_memory_bytes: payload.host_total_memory_bytes ?? current.host_total_memory_bytes,
    };

    updated = true;
    return {
      ...prev,
      generated_at: new Date().toISOString(),
      heralds,
    };
  });

  return { updated };
}

export function applyHeraldHealthUpdate(queryClient: QueryClient, payload: IHeraldHealthEventPayload): void {
  const listBefore = queryClient.getQueryData<IHerald[] | undefined>([...HERALD_LIST_QUERY_KEY]);
  const summaryBefore = queryClient.getQueryData<IHeraldsSummary | undefined>([...HERALD_SUMMARY_QUERY_KEY]);
  const inventoryBefore = queryClient.getQueryData<IInventorySnapshotResponse | undefined>([...HERALD_INVENTORY_QUERY_KEY]);

  const { updated: listUpdated, data: listData } = updateHeraldList(queryClient, payload);

  if (listUpdated && listData) {
    queryClient.setQueryData([...HERALD_SUMMARY_QUERY_KEY], buildSummary(listData, summaryBefore));
  } else if (Array.isArray(listBefore) && listBefore.length > 0 && !listUpdated) {
    clientLog.warn({ heraldId: payload.herald_id }, "Health update for unknown herald; forcing herald list refetch");
    queryClient.invalidateQueries({ queryKey: [...HERALD_LIST_QUERY_KEY], exact: true });
    if (summaryBefore) {
      queryClient.invalidateQueries({ queryKey: [...HERALD_SUMMARY_QUERY_KEY], exact: true });
    }
  }

  const { updated: inventoryUpdated } = updateInventorySnapshot(queryClient, payload);

  if (!inventoryUpdated && inventoryBefore) {
    clientLog.debug({ heraldId: payload.herald_id }, "Health update missing from cached inventory snapshot; scheduling refetch");
    queryClient.invalidateQueries({ queryKey: [...HERALD_INVENTORY_QUERY_KEY], exact: true });
  }
}

export const buildLogsTailQueryKey = (payload: ILogsTailPayload) =>
  [...TELEMETRY_LOGS_QUERY_KEY, payload.container_key ?? "unknown", payload.filter ?? ""] as const;

export type LogsTailQueryKey = ReturnType<typeof buildLogsTailQueryKey>;

export function appendLogsTailRow(queryClient: QueryClient, key: LogsTailQueryKey, row: ILogRow, limit: number = LOGS_TAIL_BUFFER_LIMIT): void {
  queryClient.setQueryData<ILogRow[] | undefined>(key, (prev) => {
    const next = Array.isArray(prev) ? [...prev, row] : [row];
    if (next.length > limit) {
      next.splice(0, next.length - limit);
    }
    return next;
  });
}

export function clearLogsTailCache(queryClient: QueryClient, key: LogsTailQueryKey): void {
  queryClient.setQueryData<ILogRow[]>(key, []);
}
