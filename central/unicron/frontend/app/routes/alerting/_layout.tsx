/**
 * Alerting Section Layout
 *
 * Loads the dashboard immediately and lazy-loads the other tab modules on demand.
 * Only mounts tabs when first visited, then keeps them mounted for instant return.
 * Syncs with URL for bookmarking and browser navigation.
 */

import { type ReactNode, useState, useEffect, memo, lazy, Suspense } from "react";
import { useLocation } from "react-router";
import Tabs, { Tab, TabList } from "../../components/library/Tabs/Tabs";
import { LoadingSpinner } from "../../features/alert-engine/components/ui/LoadingSpinner";

// Load the dashboard eagerly because it is the default route.
import Dashboard from "./index";
const Rules = lazy(() => import("./rules"));
const Alerts = lazy(() => import("./alerts"));
const Stats = lazy(() => import("./stats"));
const Containers = lazy(() => import("./containers"));

// Keep the default dashboard stable when switching tabs.
const MemoizedDashboard = memo(Dashboard);

// Prevent SSR roundtrip on navigation - this route is fully client-side
export function clientLoader() {
  return null;
}

// Tab configuration
const ALERTING_TABS = [
  { key: "dashboard", label: "Dashboard", path: "/unicron/alerting" },
  { key: "rules", label: "Rules", path: "/unicron/alerting/rules" },
  { key: "alerts", label: "Alerts", path: "/unicron/alerting/alerts" },
  { key: "stats", label: "Stats", path: "/unicron/alerting/stats" },
  { key: "containers", label: "Containers", path: "/unicron/alerting/containers" },
] as const;

type TabKey = typeof ALERTING_TABS[number]["key"];

// Get tab key from pathname
const getTabFromPath = (pathname: string): TabKey => {
  if (pathname.startsWith("/alerting/rules")) return "rules";
  if (pathname.startsWith("/alerting/alerts")) return "alerts";
  if (pathname.startsWith("/alerting/stats")) return "stats";
  if (pathname.startsWith("/alerting/containers")) return "containers";
  return "dashboard";
};

export default function AlertingLayout() {
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<TabKey>(() => getTabFromPath(location.pathname));
  // Track which tabs have been visited - only mount tabs once visited
  const [visitedTabs, setVisitedTabs] = useState<Set<TabKey>>(() => new Set([getTabFromPath(location.pathname)]));

  // Sync tab with URL when browser navigation occurs (back/forward)
  useEffect(() => {
    const tabFromUrl = getTabFromPath(location.pathname);
    if (tabFromUrl !== activeTab) {
      setActiveTab(tabFromUrl);
      setVisitedTabs(prev => new Set(prev).add(tabFromUrl));
    }
  }, [location.pathname]);

  const handleTabChange = (key: string | number) => {
    const newTab = key as TabKey;
    setActiveTab(newTab);
    setVisitedTabs(prev => new Set(prev).add(newTab));
    // Update URL using history API directly - no React Router involvement
    const tab = ALERTING_TABS.find((t) => t.key === newTab);
    if (tab) {
      window.history.replaceState(null, "", tab.path);
    }
  };

  const renderLazyTab = (
    key: TabKey,
    content: ReactNode,
    loadingText: string,
  ) => (
    visitedTabs.has(key) && (
      <div className="w-full" style={{ display: activeTab === key ? "block" : "none" }}>
        <Suspense fallback={activeTab === key ? <LoadingSpinner text={loadingText} /> : null}>
          {content}
        </Suspense>
      </div>
    )
  );

  return (
    <div className="flex w-full flex-col gap-sm">
      {/* Navigation Tabs */}
      <Tabs selectedKey={activeTab} onSelectionChange={handleTabChange}>
        <TabList
          variant="underline"
          tone="default"
          gap="md"
          padding="0"
          textSize="sm"
          disableBorder={false}
          scrollable
        >
          {ALERTING_TABS.map((tab) => (
            <Tab
              key={tab.key}
              id={tab.key}
              padding={["xs", "2xs"]}
              textSize="sm"
            >
              {tab.label}
            </Tab>
          ))}
        </TabList>
      </Tabs>

      {/* Tab Content - lazy mount: only mount when first visited, keep mounted for instant return */}
      {visitedTabs.has("dashboard") && (
        <div className="w-full" style={{ display: activeTab === "dashboard" ? "block" : "none" }}><MemoizedDashboard /></div>
      )}
      {renderLazyTab("rules", <Rules />, "Loading rules...")}
      {renderLazyTab("alerts", <Alerts />, "Loading alerts...")}
      {renderLazyTab("stats", <Stats />, "Loading statistics...")}
      {renderLazyTab("containers", <Containers />, "Loading containers...")}
    </div>
  );
}
