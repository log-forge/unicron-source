import { useState } from "react";
import type { LoaderFunctionArgs } from "react-router";
import { Outlet, data, redirect, useHref, useLoaderData, useLocation, useSearchParams } from "react-router";
import { HydrationBoundary, QueryClient, QueryClientProvider, dehydrate, type DehydratedState } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { AuthenticityTokenInput } from "remix-utils/csrf/react";

import { SocketProvider } from "../../context/SocketContext";
import { AlertProvider } from "../../context/AlertContext";
import { createServerHttpClient } from "../../utils/http.server";
import { HERALD_INVENTORY_QUERY_KEY, HERALD_LIST_QUERY_KEY, HERALD_SUMMARY_QUERY_KEY } from "../../utils/tanstack/queryKeys";
import { useHeralds, useHeraldsSummary } from "../../utils/tanstack/queries/heraldQueries";
import { useHeraldInventorySnapshot } from "../../utils/tanstack/queries/telemetryQueries";
import type { IHerald, IHeraldsSummary } from "../../types/api/queries/heraldQueries.types";
import type { IInventorySnapshotResponse } from "../../types/api/telemetry/inventory.types";
import useDehydratedState from "../../utils/useDehydratedState";
import { AppShellError } from "../../components/library/errors";
import { useAuth } from "../../context/AuthContext";
import { isBootstrapPasswordNoticeDismissed } from "../../utils/cookies/bootstrap-password-notice.server";
import { CSRF_FORM_DATA_KEY } from "../../utils/csrf/constants";

type LoaderError = {
  status?: number;
  message: string;
} | null;

type AppShellLoaderData = {
  heralds: IHerald[];
  summary: IHeraldsSummary;
  inventorySnapshot: IInventorySnapshotResponse;
  dehydratedState?: DehydratedState;
  loaderError?: LoaderError;
  bootstrapPasswordNoticeDismissed: boolean;
};

function BootstrapPasswordNotice({ dismissed }: { dismissed: boolean }) {
  const { adminBootstrap } = useAuth();
  const overviewAction = useHref("/overview");
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const returnTo = `${location.pathname}${location.search}${location.hash}`;
  const status = searchParams.get("bootstrapPassword");
  const message =
    status === "invalid"
      ? "Could not change the password. Check the current password and use at least 8 characters with uppercase, lowercase, number, and special character."
      : status === "failed"
        ? "Could not change the password. Check the current password and try again."
        : null;

  if (!adminBootstrap?.requiresPasswordChange || dismissed) return null;

  return (
    <div className="border-b border-warning/40 bg-warning/10 px-md py-sm text-sm text-warning-text">
      <div className="mx-auto flex max-w-screen-2xl flex-col gap-xs">
        <div className="flex flex-col gap-xs md:flex-row md:items-center md:justify-between">
          <div>
            <div className="font-semibold">Change the administrator password</div>
            <div className="text-xs text-warning-text/80">
              This account is using a generated or bootstrap administrator credential. You can keep using Unicron and rotate it later.
            </div>
          </div>
          <div className="flex flex-wrap items-start gap-xs">
            <details className="group" open={Boolean(message) || undefined}>
              <summary className="w-fit cursor-pointer list-none rounded-md border border-warning/50 px-sm py-2xs text-xs font-semibold hover:bg-warning/20 [&::-webkit-details-marker]:hidden">
                <span className="group-open:hidden">Change password</span>
                <span className="hidden group-open:inline">Hide</span>
              </summary>
              <form
                method="post"
                action={overviewAction}
                className="mt-xs grid gap-xs md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
              >
                <AuthenticityTokenInput name={CSRF_FORM_DATA_KEY} />
                <input type="hidden" name="_intent" value="bootstrap-password" />
                <input type="hidden" name="returnTo" value={returnTo} />
                <input
                  type="password"
                  name="currentPassword"
                  autoComplete="current-password"
                  placeholder="Current password"
                  className="min-w-0 rounded-md border border-warning/40 bg-background px-sm py-2xs text-text outline-none focus:border-warning"
                  required
                />
                <input
                  type="password"
                  name="newPassword"
                  autoComplete="new-password"
                  placeholder="New password"
                  className="min-w-0 rounded-md border border-warning/40 bg-background px-sm py-2xs text-text outline-none focus:border-warning"
                  required
                />
                <button
                  type="submit"
                  className="rounded-md bg-warning px-sm py-2xs text-xs font-semibold text-warning-text hover:brightness-95"
                >
                  Save
                </button>
                {message ? <div className="text-xs text-warning-text/80 md:col-span-3">{message}</div> : null}
              </form>
            </details>
            <form method="post" action={overviewAction}>
              <AuthenticityTokenInput name={CSRF_FORM_DATA_KEY} />
              <input type="hidden" name="_intent" value="dismiss-bootstrap-password" />
              <input type="hidden" name="returnTo" value={returnTo} />
              <button
                type="submit"
                className="rounded-md border border-warning/30 px-sm py-2xs text-xs font-semibold text-warning-text/80 hover:bg-warning/20"
              >
                Dismiss
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}

export async function loader({ context, request }: LoaderFunctionArgs) {
  let heralds: IHerald[] = [];
  let summary: IHeraldsSummary = {
    total: 0,
    statuses: {},
    last_ping_latest: null,
    socket_online_total: 0,
    groups: {},
    regions: {},
  };
  let inventorySnapshot: IInventorySnapshotResponse = {
    generated_at: Date.now().toString(),
    heralds: [],
    containers: [],
  };
  let loaderError: LoaderError = null;
  const bootstrapPasswordNoticeDismissed = await isBootstrapPasswordNoticeDismissed(request);

  try {
    const client = createServerHttpClient({ request });
    const [heraldsRes, summaryRes, inventoryRes] = await Promise.all([
      client.get("/queries/list-heralds"),
      client.get("/queries/heralds-summary"),
      client.get("/telemetry/inventory/herald"),
    ]);
    heralds = heraldsRes.data;
    summary = summaryRes.data;
    inventorySnapshot = inventoryRes.data;
  } catch (err) {
    if (isAxiosError(err)) {
      const status = err.response?.status;
      if (status === 401 || status === 403) {
        const url = new URL(request.url);
        const returnTo = url.pathname + url.search;
        const returnPath = returnTo.startsWith("/unicron") ? returnTo.slice("/unicron".length) || "/" : returnTo;
        const params = new URLSearchParams({
          returnTo: returnPath,
          reason: "reauth",
        });
        throw redirect(`/sign-in?${params.toString()}`);
      }
    }

    context?.log?.error?.({ err }, "Failed to fetch herald data");

    // Capture error details for client-side error display
    if (isAxiosError(err)) {
      loaderError = {
        status: err.response?.status,
        message: err.message,
      };
    } else if (err instanceof Error) {
      loaderError = {
        message: err.message,
      };
    } else {
      loaderError = {
        message: "An unknown error occurred",
      };
    }
  }

  const serverQueryClient = new QueryClient();
  serverQueryClient.setQueryData([...HERALD_LIST_QUERY_KEY], heralds);
  serverQueryClient.setQueryData([...HERALD_SUMMARY_QUERY_KEY], summary);
  serverQueryClient.setQueryData([...HERALD_INVENTORY_QUERY_KEY], inventorySnapshot);
  const dehydratedState = dehydrate(serverQueryClient);

  return data<AppShellLoaderData>(
    { heralds, summary, inventorySnapshot, dehydratedState, loaderError, bootstrapPasswordNoticeDismissed },
    { status: 200 },
  );
}

function AppShellProviders({ heralds, summary, inventorySnapshot, loaderError, bootstrapPasswordNoticeDismissed }: AppShellLoaderData) {
  const heraldsQuery = useHeralds(heralds);
  const summaryQuery = useHeraldsSummary(summary);
  const inventoryQuery = useHeraldInventorySnapshot(inventorySnapshot);

  // If there's a loader error (especially auth), show the error page
  if (loaderError?.status === 401 || loaderError?.status === 403) {
    return (
      <AppShellError error={new Error(loaderError.message)} />
    );
  }

  // Check if any TanStack queries have auth errors.
  const queryError = heraldsQuery.error ?? summaryQuery.error ?? inventoryQuery.error;
  const is402Error = queryError && isAxiosError(queryError) && queryError.response?.status === 402;
  if (queryError && !is402Error) {
    return (
      <AppShellError error={queryError} />
    );
  }

  return (
    <SocketProvider>
      <AlertProvider>
        <BootstrapPasswordNotice dismissed={bootstrapPasswordNoticeDismissed} />
        <Outlet />
      </AlertProvider>
    </SocketProvider>
  );
}

export function shouldRevalidate({ formMethod }: { formMethod?: string | null }) {
  // Only revalidate on mutations — herald/inventory data is managed by TanStack Query client-side
  if (formMethod && formMethod.toLowerCase() !== "get") return true;
  return false;
}

export default function AppShellLayout() {
  const loaderData = useLoaderData<typeof loader>();
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
          },
        },
      }),
  );
  const hookDehydratedState = useDehydratedState();
  const dehydratedState = hookDehydratedState ?? loaderData.dehydratedState;

  return (
    <QueryClientProvider client={queryClient}>
      <HydrationBoundary state={dehydratedState}>
        <AppShellProviders {...loaderData} />
      </HydrationBoundary>
    </QueryClientProvider>
  );
}
