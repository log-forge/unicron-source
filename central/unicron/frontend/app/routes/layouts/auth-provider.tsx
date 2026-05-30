import type { LoaderFunctionArgs } from "react-router";
import { data, Outlet, useLoaderData } from "react-router";
import { AuthProvider } from "../../context/AuthContext";
import { getAuthFromRequest, type BetterAuthSession } from "../../utils/auth/auth.server";

type LoaderData = {
  auth: BetterAuthSession;
};

export async function loader({ request }: LoaderFunctionArgs) {
  const auth = await getAuthFromRequest(request);
  return data<LoaderData>({ auth }, { status: 200 });
}

export function shouldRevalidate({
  formMethod,
  currentUrl,
  nextUrl,
}: {
  formMethod?: string | null;
  currentUrl: URL;
  nextUrl: URL;
  defaultShouldRevalidate: boolean;
}) {
  if (formMethod && formMethod.toLowerCase() !== "get") return true;

  const isSignIn = (url: URL) => url.pathname.includes("sign-in");
  if (isSignIn(currentUrl) || isSignIn(nextUrl)) return true;

  return false;
}

export default function AuthProviderLayout() {
  const { auth } = useLoaderData<typeof loader>();

  return (
    <AuthProvider initial={auth}>
      <Outlet />
    </AuthProvider>
  );
}
