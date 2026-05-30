import { Outlet, redirect, useLoaderData } from "react-router";
import type { LoaderFunctionArgs } from "react-router";
import { withOrganization } from "../../utils/auth/permissions-wrappers.server";

export const loader = withOrganization(async ({ request }: LoaderFunctionArgs) => {
  if (!request.organization) {
    const url = new URL(request.url);
    const returnTo = url.pathname + url.search;

    return redirect(`/alerting?redirectTo=org-dashboard&returnTo=${encodeURIComponent(returnTo)}`);
  }

  return { user: request.user, session: request.session, organization: request.organization };
});

export default function OrgRequiredLayout() {
  const { user, organization } = useLoaderData<typeof loader>();

  if (!user || !organization) return null;

  return <Outlet />;
}
