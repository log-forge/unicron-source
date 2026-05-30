import { Outlet, redirect, useLoaderData } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import { withAuth } from "../../utils/auth/auth-wrappers.server";

export const loader = withAuth(async ({ request }: LoaderFunctionArgs) => {
  const url = new URL(request.url);

  if (!request.user || !request.session) {
    const returnTo = url.pathname + url.search;
    // Remove the /unicron basename prefix since React Router handles it automatically
    const returnPath = returnTo.startsWith("/unicron") ? returnTo.slice("/unicron".length) || "/" : returnTo;
    return redirect(`/sign-in?returnTo=${encodeURIComponent(returnPath)}`);
  }

  return { user: request.user, session: request.session };
});

export function shouldRevalidate({ formMethod }: { formMethod?: string | null }) {
  // Only revalidate on mutations — auth state doesn't change between tab switches
  if (formMethod && formMethod.toLowerCase() !== "get") return true;
  return false;
}

export default function AuthRequiredLayout() {
  const { user } = useLoaderData<typeof loader>();

  // Client-side fallback: don't render subtree if loader somehow returned no user
  if (!user) return null;

  return <Outlet />;
}
