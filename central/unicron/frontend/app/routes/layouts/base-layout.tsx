import { type ComponentType, type ReactNode, isValidElement, useContext, useEffect, useMemo, useState } from "react";
import { Form, matchRoutes, Outlet, UNSAFE_DataRouterContext, useLocation, useMatches, useNavigate, useNavigation } from "react-router";
import { AuthenticityTokenInput } from "remix-utils/csrf/react";
import { useModal } from "../../context/ModalContext";
import { Button } from "../../components/library/buttons/Button";
import SignInModal from "../../components/modal views/sign in/SignInModal";
import { Bug, ChevronDown, ChevronRight, CircleHelp, ExternalLink, LogIn, LogOut, Mail, Settings, UserCircle } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { CSRF_FORM_DATA_KEY } from "../../utils/csrf/constants";
import Tabs, { Tab, TabList } from "../../components/library/Tabs/Tabs";
import { FiringAlertsBadge } from "../../components/alerting/FiringAlertsBadge";
import { FiringAlertsList } from "../../components/alerting/FiringAlertsList";

type RouteSkeletonHandle = {
  skeleton?: ReactNode | ComponentType;
};

const SUPPORT_ISSUES_URL = "https://github.com/log-forge/logforge/issues";
const SUPPORT_EMAIL = "logforge@gmail.com";
const SUPPORT_MAILTO = `mailto:${SUPPORT_EMAIL}`;

const DefaultRouteSkeleton = () => (
  <div className="flex w-full flex-col gap-lg text-text">
    <section className="relative overflow-hidden rounded-2xl border border-neutral/40 bg-neutral/10 p-lg shadow-[0_28px_80px_color-mix(in_oklab,var(--color-neutral),30%)] backdrop-blur">
      <div className="space-y-md">
        <div className="h-4 w-40 animate-pulse rounded-full bg-neutral/10" />
        <div className="h-8 w-2/3 animate-pulse rounded-full bg-neutral/10" />
        <div className="h-4 w-full animate-pulse rounded-full bg-neutral/10" />
        <div className="grid gap-sm sm:grid-cols-2">
          <div className="h-20 animate-pulse rounded-lg bg-neutral/10" />
          <div className="h-20 animate-pulse rounded-lg bg-neutral/10" />
        </div>
      </div>
    </section>

    <section className="grid w-full gap-lg lg:grid-cols-[240px_minmax(0,1fr)]">
      <div className="h-fit rounded-2xl border border-neutral/40 bg-neutral/10 p-sm shadow-[0_8px_30px_color-mix(in_oklab,var(--color-neutral),20%)] backdrop-blur">
        <div className="space-y-2xs">
          <div className="h-3 w-24 animate-pulse rounded-full bg-neutral/10" />
          <div className="h-8 w-full animate-pulse rounded-xl bg-neutral/10" />
          <div className="h-8 w-full animate-pulse rounded-xl bg-neutral/10" />
          <div className="h-8 w-full animate-pulse rounded-xl bg-neutral/10" />
        </div>
      </div>
      <div className="space-y-md">
        <div className="flex w-full items-center justify-between gap-sm">
          <div className="space-y-2xs">
            <div className="h-6 w-64 animate-pulse rounded-full bg-neutral/10" />
            <div className="h-4 w-80 animate-pulse rounded-full bg-neutral/10" />
          </div>
          <div className="h-8 w-32 animate-pulse rounded-full bg-neutral/10" />
        </div>
        <div className="grid gap-lg sm:grid-cols-2">
          <div className="rounded-2xl border border-neutral/40 bg-neutral/10 p-md shadow-[0_12px_40px_color-mix(in_oklab,var(--color-neutral),20%)] backdrop-blur">
            <div className="space-y-sm">
              <div className="h-5 w-40 animate-pulse rounded-full bg-neutral/10" />
              <div className="h-28 w-full animate-pulse rounded-xl bg-neutral/10" />
              <div className="h-10 w-32 animate-pulse rounded-full bg-neutral/10" />
            </div>
          </div>
          <div className="rounded-2xl border border-neutral/40 bg-neutral/10 p-md shadow-[0_12px_40px_color-mix(in_oklab,var(--color-neutral),20%)] backdrop-blur">
            <div className="space-y-sm">
              <div className="h-5 w-44 animate-pulse rounded-full bg-neutral/10" />
              <div className="h-28 w-full animate-pulse rounded-xl bg-neutral/10" />
              <div className="h-10 w-36 animate-pulse rounded-full bg-neutral/10" />
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
);

export default function BaseLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const navigation = useNavigation();
  const matches = useMatches();
  const dataRouterContext = useContext(UNSAFE_DataRouterContext);
  const { openModal } = useModal();
  const { isAuthenticated, user, adminBootstrap } = useAuth();
  const [isAlertsPanelOpen, setIsAlertsPanelOpen] = useState(false);

  const navItems = [
    { key: "overview", label: "Overview", to: "/overview", requiresAuth: true },
    { key: "alerting", label: "Alerting", to: "/alerting", requiresAuth: true },
    { key: "notifications", label: "Notifications", to: "/notifications", requiresAuth: true },
    { key: "settings", label: "Settings", to: "/settings/account", requiresAuth: true, section: "/settings" },
  ];
  const visibleNavItems = navItems.filter((item) => {
    if (item.requiresAuth && !isAuthenticated) return false;
    return true;
  });

  const pendingMatches = useMemo(() => {
    if (!navigation.location || !dataRouterContext?.router?.routes) return null;
    return matchRoutes(dataRouterContext.router.routes, navigation.location);
  }, [dataRouterContext, navigation.location]);

  const resolveSkeleton = (matchList: ReadonlyArray<unknown> | null) => {
    if (!matchList?.length) return null;
    for (let i = matchList.length - 1; i >= 0; i -= 1) {
      const match = matchList[i] as { handle?: RouteSkeletonHandle; route?: { handle?: RouteSkeletonHandle } };
      const handle = match?.handle ?? match?.route?.handle;
      if (handle?.skeleton) return handle.skeleton;
    }
    return null;
  };

  // Only show loading skeleton for cross-section navigation, not sub-tab changes
  // e.g., /alerting/rules → /alerting/alerts = no skeleton (same section)
  //       /alerting → /notifications = show skeleton (different section)
  const getSection = (path: string) => {
    const segments = path.split('/').filter(Boolean);
    return segments[0] || '';
  };

  // Sections with clientLoader that resolve instantly - never show skeleton
  const clientOnlySections = new Set(['alerting', 'notifications', 'containers', 'overview', '']);

  const isRouteLoading =
    navigation.state === "loading" &&
    !!navigation.location &&
    (navigation.location.pathname !== location.pathname || navigation.location.search !== location.search) &&
    getSection(navigation.location.pathname) !== getSection(location.pathname) &&
    !clientOnlySections.has(getSection(navigation.location.pathname));
  const overrideSkeleton = (isRouteLoading ? resolveSkeleton(pendingMatches) : null) ?? resolveSkeleton(matches);

  const resolvedSkeleton = (() => {
    if (!overrideSkeleton) return null;
    if (isValidElement(overrideSkeleton)) return overrideSkeleton;
    if (typeof overrideSkeleton === "function") {
      const Skeleton = overrideSkeleton as ComponentType;
      return <Skeleton />;
    }
    return null;
  })();

  const activePath = navigation.location?.pathname ?? location.pathname;
  const isAlertingSection = activePath.startsWith("/alerting");

  useEffect(() => {
    if (isAlertingSection && isAlertsPanelOpen) {
      setIsAlertsPanelOpen(false);
    }
  }, [isAlertingSection, isAlertsPanelOpen]);

  const selectedTabKey = visibleNavItems.find((item) => {
    const section = "section" in item ? item.section : undefined;
    if (section && activePath.startsWith(section)) return true;
    return item.to === "/" ? activePath === "/" : activePath.startsWith(item.to);
  })?.key;

  const username = String(adminBootstrap?.username ?? user?.username ?? user?.displayUsername ?? user?.name ?? "admin");
  const roleLabel = "Super User";
  const isSigningOut = navigation.state === "submitting" && navigation.formData?.get("_intent") === "sign-out";

  return (
    <>
      {/* Firing Alerts Panel Overlay - rendered outside main container to avoid overflow clipping */}
      {isAlertsPanelOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-[100] bg-black/30 transition-opacity"
            onClick={() => setIsAlertsPanelOpen(false)}
            aria-hidden="true"
          />
          {/* Panel */}
          <div
            className="fixed inset-y-0 z-[101] overflow-hidden border-l border-neutral-200 bg-white shadow-2xl dark:border-neutral-700 dark:bg-neutral-900"
            style={{ right: 0, width: '100%', maxWidth: '24rem' }}
          >
            <FiringAlertsList onClose={() => setIsAlertsPanelOpen(false)} />
          </div>
        </>
      )}
      <div className="flex min-h-screen w-full flex-col items-center justify-start overflow-x-hidden bg-background text-text">
        <header className="sticky top-0 z-30 flex w-full max-w-full min-w-0 flex-row items-center justify-between gap-sm border-b border-foreground bg-background/60 px-md py-3xs text-text backdrop-blur supports-[backdrop-filter]:bg-foreground/20 sm:gap-lg">
        <div className="shrink-0">
          {/* <Button variant="text" tone="default" text="h5" className="!font-semibold !no-underline !outline-none visited:!text-text" to="/"> */}
          <button className="font-semibold! no-underline! outline-none! visited:text-text!" onClick={(e) => navigate("/overview")}>
            Unicron
          </button>
          <div className="-mt-0.5 hidden text-xs whitespace-nowrap text-neutral sm:block">Remote Container Observability</div>
        </div>
        <div className="flex min-w-0 flex-1 flex-row items-center justify-between gap-sm">
          <div className="flex min-w-0 flex-1 items-center justify-start gap-sm">
            <Tabs animated={false} selectedKey={selectedTabKey}>
              <TabList variant="underline" tone="default" gap="sm" padding="0" disableBorder textSize="sm" scrollable>
                {visibleNavItems.map((item) => {
                  return (
                    <Tab key={item.key} id={item.key} padding={["2xs", "4xs"]} textSize="sm" onPress={() => navigate(item.to)}>
                      {item.label}
                    </Tab>
                  );
                })}
              </TabList>
            </Tabs>
          </div>
          <div className="flex shrink-0 items-center justify-end gap-sm">
            {/* Firing Alerts Badge - only show when authenticated */}
            {isAuthenticated && !isAlertingSection && (
              <div className="relative">
                <FiringAlertsBadge onClick={() => setIsAlertsPanelOpen(!isAlertsPanelOpen)} />
              </div>
            )}
            {isAuthenticated && (
              <details className="group relative">
                <summary
                  className="flex min-h-8 cursor-pointer list-none items-center gap-2xs rounded-md border border-neutral/20 bg-background px-xs py-2xs text-sm text-text hover:bg-neutral/5 [&::-webkit-details-marker]:hidden"
                  title={`${username} (${roleLabel})`}
                >
                  <UserCircle className="h-4 w-4 text-primary" aria-hidden="true" />
                  <span className="hidden max-w-32 truncate font-medium lg:inline">{username}</span>
                  <span className="hidden whitespace-nowrap rounded-full bg-primary/10 px-1.5 py-0.5 text-[11px] font-semibold text-primary xl:inline">
                    {roleLabel}
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 text-neutral transition-transform group-open:rotate-180" aria-hidden="true" />
                </summary>
                <div className="absolute right-0 mt-2 w-56 overflow-hidden rounded-lg border border-neutral/20 bg-background shadow-xl">
                  <div className="border-b border-neutral/10 px-sm py-xs">
                    <div className="truncate text-sm font-semibold text-text">{username}</div>
                    <div className="text-xs text-neutral">{roleLabel} - local</div>
                  </div>
                  <button
                    type="button"
                    className="flex w-full items-center gap-xs px-sm py-xs text-left text-sm text-text hover:bg-neutral/5"
                    onClick={() => navigate("/settings/account")}
                  >
                    <Settings className="h-4 w-4 text-neutral" aria-hidden="true" />
                    Account settings
                  </button>
                  <div className="border-t border-neutral/10 px-sm py-2xs text-xs font-medium text-neutral">
                    <span className="flex items-center gap-2xs">
                      <CircleHelp className="h-3.5 w-3.5" aria-hidden="true" />
                      Support
                    </span>
                  </div>
                  <a
                    href={SUPPORT_ISSUES_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="flex w-full items-center gap-xs px-sm py-xs text-left text-sm text-text hover:bg-neutral/5"
                  >
                    <Bug className="h-4 w-4 text-neutral" aria-hidden="true" />
                    <span className="flex-1">Report an issue</span>
                    <ExternalLink className="h-3.5 w-3.5 text-neutral" aria-hidden="true" />
                  </a>
                  <a href={SUPPORT_MAILTO} className="flex w-full items-center gap-xs px-sm py-xs text-left text-sm text-text hover:bg-neutral/5">
                    <Mail className="h-4 w-4 text-neutral" aria-hidden="true" />
                    Contact us
                  </a>
                  <Form method="post" action="/resources/sign-out" className="border-t border-neutral/10">
                    <AuthenticityTokenInput name={CSRF_FORM_DATA_KEY} />
                    <input type="hidden" name="_intent" value="sign-out" />
                    <button
                      type="submit"
                      className="flex w-full items-center gap-xs px-sm py-xs text-left text-sm text-error-700 hover:bg-error/10 disabled:cursor-not-allowed disabled:opacity-60 dark:text-error-300"
                      disabled={isSigningOut}
                    >
                      <LogOut className="h-4 w-4" aria-hidden="true" />
                      {isSigningOut ? "Signing out..." : "Sign out"}
                    </button>
                  </Form>
                </div>
              </details>
            )}
            {!isAuthenticated && (
              <div className="flex flex-row items-center justify-end gap-md">
                <Button
                  variant="ghost"
                  tone="default"
                  textSize="sm"
                  padding="4xs"
                  className="flex flex-row items-center justify-center gap-2xs"
                  onPress={() => openModal(<SignInModal />, "md", true)}
                >
                  Sign in
                  <span className="relative inline-flex h-(--text-sm) w-(--text-sm) overflow-hidden">
                    <ChevronRight
                      className="absolute inset-0 translate-x-0 opacity-100 transition-all duration-100 group-hover/button:-translate-x-full group-hover/button:opacity-0"
                      style={{ height: "var(--text-sm)", width: "var(--text-sm)" }}
                    />
                    <LogIn
                      className="absolute inset-0 translate-x-full opacity-0 transition-all duration-200 group-hover/button:translate-x-0 group-hover/button:opacity-100"
                      style={{ height: "var(--text-sm)", width: "var(--text-sm)" }}
                    />
                  </span>
                </Button>
                <Button variant="glass" tone="primary" textSize="sm" radius="full" padding={["xs", "4xs"]} onPress={() => openModal(<SignInModal />, "md", true)}>
                  Start monitoring
                </Button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="min-h-3xs w-full bg-primary" />
      <main className="flex w-full flex-1 flex-col items-stretch justify-start px-md py-md lg:px-lg" aria-busy={isRouteLoading}>
        {isRouteLoading ? (resolvedSkeleton ?? <DefaultRouteSkeleton />) : <Outlet />}
      </main>
      </div>
    </>
  );
}
