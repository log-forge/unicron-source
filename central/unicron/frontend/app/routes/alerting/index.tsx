/**
 * Alerting Dashboard Page
 *
 * Overview page showing alert statistics, recent alerts, and active rules.
 * Ported from LogForge DashboardPage with Unicron adaptations.
 */

import { useIsFetching } from '@tanstack/react-query';
import { useRules, useAlerts, useHealth } from '~/features/alert-engine/hooks/useApi';
import StatsCards from '~/features/alert-engine/components/dashboard/StatsCards';
import AlertsSummary from '~/features/alert-engine/components/alerts/AlertsSummary';
import RulesList from '~/features/alert-engine/components/rules/RulesList';

export default function AlertingDashboard() {
  const { rules, loading: rulesLoading } = useRules();
  const { alerts, alertsMeta, loading: alertsLoading } = useAlerts(5);
  const { health, loading: healthLoading } = useHealth();

  // Check if ANY alert-engine query is fetching in background
  const isFetching = useIsFetching({ queryKey: ['alert-engine'] });

  const totalAlerts = alertsMeta.totalAvailable ?? alerts.length;
  const statsLoading = rulesLoading || alertsLoading || healthLoading;
  const containerCount =
    typeof health?.containers_count === 'number' ? health.containers_count : 0;

  return (
    <div className="space-y-8">
      {/* Subtle background refresh indicator */}
      {isFetching > 0 && (
        <div className="fixed top-4 right-4 z-50">
          <div className="h-2 w-2 rounded-full bg-info animate-pulse" />
        </div>
      )}

      <StatsCards
        alerts={alerts}
        totalAlerts={totalAlerts}
        rules={rules}
        containerCount={containerCount}
        health={health}
        loading={statsLoading}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <AlertsSummary alerts={alerts} totalAlerts={totalAlerts} loading={alertsLoading} />
        <RulesList
          rules={rules.filter(r => r.enabled)}
          onDelete={() => {}}
          onEdit={() => {}}
          onToggleEnabled={() => {}}
          summaryMode
          loading={rulesLoading}
        />
      </div>
    </div>
  );
}
