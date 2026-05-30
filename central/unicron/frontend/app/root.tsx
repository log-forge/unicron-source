import type { Route } from "../.react-router/types/app/+types/root";
import { isRouteErrorResponse, Links, Meta, Outlet, Scripts, ScrollRestoration, useRouteLoaderData, data, useNavigate, useHref } from "react-router";
import "./app.css";
import { getTheme, type Theme } from "./utils/cookies/theme.server";
import { ClientHintCheck, getHints } from "./utils/client-hints";
import { ThemeProvider } from "./context/ThemeContext";
import { csrf } from "./utils/csrf/csrf.server";
import { AuthenticityTokenProvider } from "remix-utils/csrf/react";
import { RouterProvider as AriaRouterProvider } from "react-aria-components";
import { ModalProvider } from "./context/ModalContext";
import { CSRF_META_NAME } from "./utils/csrf/constants";

export const links: Route.LinksFunction = () => [
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
  { rel: "stylesheet", href: "https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" },
];

interface RootLoaderData {
  theme: string;
  resolvedTheme: string;
  csrfToken: string;
}

const FALLBACK_ROOT_LOADER_DATA: RootLoaderData = {
  theme: "dark",
  resolvedTheme: "dark",
  csrfToken: "",
};

function isResolvedTheme(value: unknown): value is "dark" | "light" {
  return value === "dark" || value === "light";
}

function withRootLoaderFallbacks(loaderData: Partial<RootLoaderData> | null | undefined): RootLoaderData {
  return {
    theme: typeof loaderData?.theme === "string" && loaderData.theme.length > 0 ? loaderData.theme : FALLBACK_ROOT_LOADER_DATA.theme,
    resolvedTheme: isResolvedTheme(loaderData?.resolvedTheme) ? loaderData.resolvedTheme : FALLBACK_ROOT_LOADER_DATA.resolvedTheme,
    csrfToken: typeof loaderData?.csrfToken === "string" ? loaderData.csrfToken : FALLBACK_ROOT_LOADER_DATA.csrfToken,
  };
}

export async function loader({ context, request }: Route.LoaderArgs) {
  const theme = await getTheme(request);
  const hints = getHints(request);
  const resolvedTheme = theme === "system" ? hints.theme || "dark" : theme;

  context?.log?.info?.({ theme, resolvedTheme, hints }, "Loader data");

  // mint or reuse a CSRF token (64 chars)
  const [csrfToken, cookie] = await csrf.commitToken(request, 64);

  const headers: HeadersInit = {};
  if (cookie) headers["Set-Cookie"] = cookie;

  return data<RootLoaderData>({ theme, resolvedTheme, csrfToken }, { status: 200, headers });
}

export function Layout({ children }: { children: React.ReactNode }) {
  const { resolvedTheme, csrfToken } = withRootLoaderFallbacks(useRouteLoaderData<Partial<RootLoaderData>>("root"));

  return (
    <html lang="en" data-theme={resolvedTheme}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <ClientHintCheck />
        <Meta />
        {/* Expose csrf token to non-React clients and helpers */}
        <meta name={CSRF_META_NAME} content={csrfToken} />
        <Links />
      </head>
      <body>
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function App({ loaderData }: Route.ComponentProps) {
  const { theme, csrfToken } = withRootLoaderFallbacks(loaderData as Partial<RootLoaderData> | null | undefined);
  const navigate = useNavigate();

  return (
    <AuthenticityTokenProvider token={csrfToken}>
      <ThemeProvider {...{ initialTheme: theme as Theme }}>
        <ModalProvider>
          <AriaRouterProvider navigate={navigate} useHref={useHref}>
            <Outlet />
          </AriaRouterProvider>
        </ModalProvider>
      </ThemeProvider>
    </AuthenticityTokenProvider>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  let message = "Oops!";
  let details = "An unexpected error occurred.";
  let stack: string | undefined;

  if (isRouteErrorResponse(error)) {
    message = error.status === 404 ? "404" : "Error";
    details = error.status === 404 ? "The requested page could not be found." : error.statusText || details;
  } else if (import.meta.env.DEV && error && error instanceof Error) {
    details = error.message;
    stack = error.stack;
  }

  return (
    <main className="flex min-h-screen w-full items-center justify-center bg-background p-lg text-text">
      <section className="flex w-full max-w-4xl items-center gap-sm text-left">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-error/10">
          <span className="text-h5 font-semibold text-error-text">!</span>
        </div>
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-sm">
          <h1 className="text-h3 font-semibold whitespace-nowrap">{message}</h1>
          <p className="min-w-0 flex-1 text-sm text-neutral-text">{details}</p>
          {stack && (
            <pre className="basis-full max-h-[50vh] w-full overflow-auto rounded-md border border-divider bg-alt-background p-sm text-xs text-neutral-text">
              <code>{stack}</code>
            </pre>
          )}
        </div>
      </section>
    </main>
  );
}
