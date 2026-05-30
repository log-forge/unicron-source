import type { DehydratedState } from "@tanstack/query-core";
import { useMatches } from "react-router";
import merge from "deepmerge";

/**
 * useDehydratedState
 *
 * Collects and merges `dehydratedState` objects returned from route loaders
 * so a single hydration state can be used at the app root.
 *
 * Notes:
 * - Each route loader may return `dehydratedState: dehydrate(queryClient)`.
 * - This hook uses `useMatches()` to read each match's loader data and merges
 *   any `dehydratedState` values using `deepmerge`.
 * - We wrap `useMatches()` in a try/catch because in some router setups
 *   (non-data routers) `useMatches()` will throw; when it does we return
 *   undefined to avoid crashing the app (see upstream issue #3).
 * - Prefer prefetching on the server (prefetchQuery/fetchQuery) so the
 *   dehydrated state contains the data you want hydrated on the client.
 */
export const useDehydratedState = (): DehydratedState | undefined => {
  let matches;
  try {
    // useMatches throws when not used within a data router; guard and return undefined
    matches = useMatches();
  } catch (e) {
    return undefined;
  }

  if (!Array.isArray(matches)) return undefined;

  const states = matches.map((m) => (m && (m as any).data ? (m as any).data.dehydratedState : undefined)).filter(Boolean) as DehydratedState[];

  if (!states.length) return undefined;

  return states.reduce((acc, cur) => merge(acc, cur), {} as DehydratedState);
};

export default useDehydratedState;
