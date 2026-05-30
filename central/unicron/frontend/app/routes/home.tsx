/**
 * Dashboard / Home Page
 *
 * Displays system overview with stats cards, recent alerts, and active rules.
 */

import { useQuery } from "@tanstack/react-query";
import { StatsCards, RecentAlerts, ActiveRules } from "../components/dashboard";
import { getRules, getAlertHistory } from "../utils/api/alert-engine";

// ============================================================================
// Meta
// ============================================================================

export function meta() {
  return [
    { title: "Dashboard - Unicron" },
    { name: "description", content: "Unicron monitoring dashboard overview" },
  ];
}

// ============================================================================
// Component
// ============================================================================

export default function Home() {
  // Fetch rules
  const {
    data: rulesData,
    isLoading: rulesLoading,
  } = useQuery({
    queryKey: ["dashboard", "rules"],
    queryFn: () => getRules({ limit: 100 }),
    staleTime: 30 * 1000,
  });

  // Fetch recent alerts
  const {
    data: alertsData,
    isLoading: alertsLoading,
  } = useQuery({
    queryKey: ["dashboard", "alerts"],
    queryFn: () =>
      getAlertHistory({
        limit: 50,
        offset: 0,
      }),
    staleTime: 30 * 1000,
  });

  const isLoading = rulesLoading || alertsLoading;

  // Calculate stats
  const rules = rulesData?.items ?? [];
  const alerts = alertsData?.items ?? [];
  const totalAlerts = alertsData?.total ?? 0;

  // Calculate alerts in last 24h
  const now = new Date();
  const oneDayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const alertsLast24h = alerts.filter(
    (a) => new Date(a.triggered_at) > oneDayAgo
  ).length;

  const rulesEnabled = rules.filter((r) => r.enabled).length;

  const containersCount = 0;
  const isHealthy = true;

  return (
    <div className="flex w-full max-w-7xl mx-auto flex-col gap-lg">
      {/* Page Header */}
      <div className="flex flex-col gap-xs">
        <h1 className="text-2xl font-bold text-text">Dashboard</h1>
        <p className="text-sm text-neutral">
          Monitor your container infrastructure at a glance.
        </p>
      </div>

      {/* Stats Cards */}
      <StatsCards
        alertsCount={totalAlerts}
        alertsLast24h={alertsLast24h}
        rulesTotal={rules.length}
        rulesEnabled={rulesEnabled}
        containersCount={containersCount}
        isHealthy={isHealthy}
        isLoading={isLoading}
      />

      {/* Two Column Layout for Recent Alerts and Active Rules */}
      <div className="grid grid-cols-1 gap-lg lg:grid-cols-2">
        <RecentAlerts alerts={alerts} isLoading={isLoading} />
        <ActiveRules rules={rules} isLoading={isLoading} />
      </div>
    </div>
  );
}
