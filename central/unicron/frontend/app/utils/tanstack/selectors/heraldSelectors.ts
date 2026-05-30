import { useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { HERALD_INVENTORY_QUERY_KEY, HERALD_SUMMARY_QUERY_KEY } from "../queryKeys";
import type { IHerald, IHeraldsSummary } from "../../../types/api/queries/heraldQueries.types";
import type { IInventorySnapshotResponse } from "../../../types/api/telemetry/inventory.types";

function getInventorySnapshot(queryClient: QueryClient): IInventorySnapshotResponse | undefined {
  return queryClient.getQueryData<IInventorySnapshotResponse>([...HERALD_INVENTORY_QUERY_KEY]);
}

function getHeraldSummary(queryClient: QueryClient): IHeraldsSummary | undefined {
  return queryClient.getQueryData<IHeraldsSummary>([...HERALD_SUMMARY_QUERY_KEY]);
}

export function selectHeraldById(queryClient: QueryClient, heraldId: string): IHerald | undefined {
  const inventory = getInventorySnapshot(queryClient)?.heralds;
  if (!inventory || inventory.length === 0) return undefined;

  return inventory.find((herald) => herald.herald_id === heraldId);
}

export function selectHeraldRegions(queryClient: QueryClient): string[] {
  const inventory = getInventorySnapshot(queryClient);
  if (!inventory) return [];

  const regions = new Set<string>();
  for (const herald of inventory.heralds) {
    if (herald.region) {
      regions.add(herald.region);
    }
  }

  return [...regions].sort((a, b) => a.localeCompare(b));
}

export function selectHeraldSummary(queryClient: QueryClient): IHeraldsSummary | undefined {
  return getHeraldSummary(queryClient);
}

export function useHeraldById(heraldId: string): IHerald | undefined {
  const queryClient = useQueryClient();
  return useMemo(() => selectHeraldById(queryClient, heraldId), [queryClient, heraldId]);
}

export function useHeraldRegions(): string[] {
  const queryClient = useQueryClient();
  return useMemo(() => selectHeraldRegions(queryClient), [queryClient]);
}

export function useHeraldSummary(): IHeraldsSummary | undefined {
  const queryClient = useQueryClient();
  return useMemo(() => selectHeraldSummary(queryClient), [queryClient]);
}
