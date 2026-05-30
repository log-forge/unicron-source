/**
 * Alerts Page
 *
 * Displays active alerts with filtering and a toggle between alerts list and stats analytics view.
 * Ported from LogForge AlertsPage.
 */

import { useState, useMemo } from 'react';
import { AlertCircle, BarChart3 } from 'lucide-react';
import {
  useAlerts,
  AlertsTable,
  AlertStatsPage,
} from '~/features/alert-engine';
import type { Alert, AlertsMeta, AlertFilters } from '~/features/alert-engine';

export default function AlertsPage() {
  // Fetch alerts using the useAlerts hook
  const {
    alerts,
    alertsMeta,
    loading,
    error,
    acknowledgeAlert,
    isAcknowledging,
  } = useAlerts();

  const [activeSubTab, setActiveSubTab] = useState<'alerts' | 'stats'>('alerts');
  const [alertFilters, setAlertFilters] = useState<AlertFilters>({});

  const limited = Boolean(alertsMeta?.hasMore);
  const limitDisplay = alertsMeta?.limit ?? alertsMeta?.requestedLimit ?? 100;

  // Apply filters to alerts for the main table
  const filteredAlerts = useMemo(() => {
    const hasRuleFilters = (alertFilters.ruleIds?.length ?? 0) > 0;
    const hasContainerFilters = (alertFilters.containerIds?.length ?? 0) > 0;
    const hasTimeRange = alertFilters.timeRange != null;

    if (!hasRuleFilters && !hasContainerFilters && !hasTimeRange) {
      return alerts;
    }

    return alerts.filter(alert => {
      if (hasRuleFilters && !alertFilters.ruleIds!.includes(alert.rule_id)) {
        return false;
      }

      if (hasContainerFilters) {
        const containerId = alert.context?.container_identifier;
        if (!containerId || !alertFilters.containerIds!.includes(containerId)) {
          return false;
        }
      }

      if (hasTimeRange && alertFilters.timeRange) {
        const alertTime = new Date(alert.timestamp);
        if (alertTime < alertFilters.timeRange.start || alertTime > alertFilters.timeRange.end) {
          return false;
        }
      }

      return true;
    });
  }, [
    alerts,
    alertFilters.ruleIds,
    alertFilters.containerIds,
    alertFilters.timeRange?.start,
    alertFilters.timeRange?.end
  ]);

  const subTabs = [
    { id: 'alerts' as const, name: 'Alerts', icon: AlertCircle },
    { id: 'stats' as const, name: 'Stats', icon: BarChart3 },
  ];

  // Show loading only on first load (no cached data)
  if (loading && alerts.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary/30 mx-auto mb-4"></div>
          <p className="text-neutral-text">Loading alerts...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-error mx-auto mb-4" />
          <p className="text-error">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-text dark:text-text">Alerts</h2>
        </div>
      </div>

      {limited && (
        <div className="mb-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          Showing the most recent {limitDisplay ?? 100} alerts.
        </div>
      )}

      {/* Sub-tab Navigation */}
      <div className="flex space-x-1 mb-6 bg-alt-foreground dark:bg-foreground rounded-lg p-1">
        {subTabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveSubTab(tab.id)}
              className={`flex items-center space-x-2 px-4 py-2 rounded-md font-medium transition-all duration-200 ${
                activeSubTab === tab.id
                  ? 'bg-background text-info shadow-sm dark:bg-alt-foreground dark:text-info'
                  : 'text-neutral-text hover:text-text hover:bg-neutral/20 dark:text-neutral-text dark:hover:text-text dark:hover:bg-alt-foreground/50'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.name}</span>
            </button>
          );
        })}
      </div>

      {/* Content */}
      {activeSubTab === 'alerts' && (
        <AlertsTable
          alerts={filteredAlerts}
          onAcknowledge={acknowledgeAlert}
          isAcknowledging={isAcknowledging}
        />
      )}

      {activeSubTab === 'stats' && (
        <AlertStatsPage
          alerts={alerts}
          meta={alertsMeta}
          onFilterChange={setAlertFilters}
          currentFilters={alertFilters}
        />
      )}
    </div>
  );
}
