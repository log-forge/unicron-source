import { useQuery, useQueryClient, useIsFetching, type QueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { HERALD_LIST_QUERY_KEY, HERALD_SUMMARY_QUERY_KEY } from "../queryKeys";
import { getHeralds, getHeraldsSummary } from "../functions/heraldQueryFunctions";
import type { IHerald, IHeraldsSummary } from "../../../types/api/queries/heraldQueries.types";

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

// Query hook for fetching all heralds
export function useHeralds(initialData?: IHerald[], enabled: boolean = true) {
  const idle = useIsFetching({ queryKey: [...HERALD_LIST_QUERY_KEY] }) === 0;
  return useQuery({
    queryKey: [...HERALD_LIST_QUERY_KEY],
    queryFn: getHeralds,
    initialData,
    staleTime: 30 * 1000,
    // Retry failed queries up to 2 times, but not for auth errors
    retry: (failureCount, error) => shouldRetry(failureCount, error, 2),
    retryDelay: (attemptIndex) => Math.min(1000, 500 * 2 ** (attemptIndex - 1)),
    enabled: idle && enabled,
    refetchInterval: 1000 * 60 * 5, // refresh every minute
    refetchOnMount: false,
  });
}

// Invalidation helper for heralds list
export function invalidateHeralds(exact: boolean = true, client?: QueryClient) {
  const queryClient = client ?? useQueryClient();
  queryClient.invalidateQueries({ queryKey: [...HERALD_LIST_QUERY_KEY], exact });
}

// Query hook for fetching heralds summary
export function useHeraldsSummary(initialData?: IHeraldsSummary, enabled: boolean = true) {
  const idle = useIsFetching({ queryKey: [...HERALD_SUMMARY_QUERY_KEY] }) === 0;
  return useQuery({
    queryKey: [...HERALD_SUMMARY_QUERY_KEY],
    queryFn: getHeraldsSummary,
    initialData,
    staleTime: 30 * 1000,
    // Retry up to 2 times, but not for auth errors
    retry: (failureCount, error) => shouldRetry(failureCount, error, 2),
    retryDelay: (attemptIndex) => Math.min(1000, 500 * 2 ** (attemptIndex - 1)),
    enabled: idle && enabled,
    refetchInterval: 1000 * 60 * 5, // refresh every minute
    refetchOnMount: false,
  });
}

// Invalidation helper for heralds summary
export function invalidateHeraldsSummary(exact: boolean = true, client?: QueryClient) {
  const queryClient = client ?? useQueryClient();
  queryClient.invalidateQueries({ queryKey: [...HERALD_SUMMARY_QUERY_KEY], exact });
}
