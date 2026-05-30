/**
 * Notifications Section Layout
 *
 * Uses lazy tab mounting for fast initial load.
 * Only mounts tabs when first visited, keeps them mounted for instant return.
 * Syncs with URL for bookmarking and browser navigation.
 */

import { useState, useEffect, memo } from "react";
import { useLocation } from "react-router";
import Tabs, { Tab, TabList } from "../../components/library/Tabs/Tabs";
import { NotifierThemeProvider } from "~/features/notifier/components/NotifierThemeProvider";

// Direct imports for instant tab switching after first mount
import Dashboard from "./index";
import Settings from "./settings";
import MyChannels from "./my-channels";
import Groups from "./groups";
import Logs from "./logs";

// Memoize tab components to prevent re-renders when switching tabs
const MemoizedDashboard = memo(Dashboard);
const MemoizedSettings = memo(Settings);
const MemoizedMyChannels = memo(MyChannels);
const MemoizedGroups = memo(Groups);
const MemoizedLogs = memo(Logs);

// Prevent SSR roundtrip on navigation - this route is fully client-side
export function clientLoader() {
  return null;
}

// Tab configuration
const NOTIFICATIONS_TABS = [
  { key: "dashboard", label: "Dashboard", path: "/notifications" },
  { key: "settings", label: "Settings", path: "/notifications/settings" },
  { key: "my-channels", label: "Channels", path: "/notifications/my-channels" },
  { key: "groups", label: "Groups", path: "/notifications/groups" },
  { key: "logs", label: "Logs", path: "/notifications/logs" },
] as const;

type TabKey = typeof NOTIFICATIONS_TABS[number]["key"];

// Get tab key from pathname
const getTabFromPath = (pathname: string): TabKey => {
  if (pathname.startsWith("/notifications/settings")) return "settings";
  if (pathname.startsWith("/notifications/my-channels")) return "my-channels";
  if (pathname.startsWith("/notifications/groups")) return "groups";
  if (pathname.startsWith("/notifications/logs")) return "logs";
  return "dashboard";
};

export default function NotificationsLayout() {
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
    const tab = NOTIFICATIONS_TABS.find((t) => t.key === newTab);
    if (tab) {
      window.history.replaceState(null, "", tab.path);
    }
  };

  return (
    <NotifierThemeProvider>
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
            {NOTIFICATIONS_TABS.map((tab) => (
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
          <div style={{ display: activeTab === "dashboard" ? "block" : "none" }}><MemoizedDashboard /></div>
        )}
        {visitedTabs.has("settings") && (
          <div style={{ display: activeTab === "settings" ? "block" : "none" }}><MemoizedSettings /></div>
        )}
        {visitedTabs.has("my-channels") && (
          <div style={{ display: activeTab === "my-channels" ? "block" : "none" }}><MemoizedMyChannels /></div>
        )}
        {visitedTabs.has("groups") && (
          <div style={{ display: activeTab === "groups" ? "block" : "none" }}><MemoizedGroups /></div>
        )}
        {visitedTabs.has("logs") && (
          <div style={{ display: activeTab === "logs" ? "block" : "none" }}><MemoizedLogs /></div>
        )}
      </div>
    </NotifierThemeProvider>
  );
}
