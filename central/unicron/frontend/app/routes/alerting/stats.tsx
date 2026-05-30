/**
 * Alert Statistics Page
 *
 * Standalone page for alert statistics accessible at /alerting/stats.
 * Ported from LogForge AlertStatsPage.
 *
 * Real-time updates via WebSocket integration - stats refresh when new alerts arrive.
 * 30s polling remains as fallback when WebSocket disconnects.
 *
 * Sub-tabs:
 *   - Statistics: Analytics and trends for alert activity (default)
 *   - History: Past alert events with filtering and pagination
 *
 * URL params auto-select History sub-tab:
 *   ?tab=history, ?rule_id=..., ?status=...
 */

import { useState, useCallback, useRef } from 'react';
import {
  useAlerts,
  useWebSocketAlerts,
  AlertStatsPage,
} from '~/features/alert-engine';
import type { AlertFilters, Alert } from '~/features/alert-engine';
import AlertHistoryPanel from '~/features/alert-engine/components/stats/AlertHistoryPanel';

type StatsSubTab = 'statistics' | 'history';

// Read URL search params using window.location.search since the alerting
// layout uses window.history.replaceState which bypasses React Router.
function getSearchParams(): URLSearchParams {
  return new URLSearchParams(window.location.search);
}

function getInitialSubTab(): StatsSubTab {
  const params = getSearchParams();
  if (params.get('tab') === 'history' || params.has('rule_id') || params.has('status')) {
    return 'history';
  }
  return 'statistics';
}

export default function AlertStats() {
  const { alerts, alertsMeta, loading, error, addAlert } = useAlerts();
  const [alertFilters, setAlertFilters] = useState<AlertFilters>({});
  const [activeSubTab, setActiveSubTab] = useState<StatsSubTab>(getInitialSubTab);

  // Read filter params for history sub-tab
  const params = getSearchParams();
  const initialRuleId = params.get('rule_id') || undefined;
  const initialStatus = params.get('status') || undefined;

  // Track refresh callback for WebSocket updates
  const refreshStatsRef = useRef<(() => void) | null>(null);

  // Handle new alert from WebSocket
  const handleNewAlert = useCallback((alert: Alert) => {
    addAlert(alert);
    // Trigger stats refresh on next render cycle
    if (refreshStatsRef.current) {
      refreshStatsRef.current();
    }
  }, [addAlert]);

  // Subscribe to WebSocket alerts for real-time updates
  useWebSocketAlerts(handleNewAlert);

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-text dark:text-text">Alert Statistics</h2>
        <p className="mt-1 text-sm text-neutral-text dark:text-neutral-text">
          Analytics and trends for your alert activity
        </p>
      </div>

      {/* Sub-tab navigation */}
      <div className="flex gap-3 border-b dark:border-divider mb-6">
        <button
          onClick={() => setActiveSubTab('statistics')}
          className={`px-3 py-2 text-sm font-medium transition-colors ${
            activeSubTab === 'statistics'
              ? 'border-b-2 border-primary/30 text-info dark:text-info dark:border-primary/30'
              : 'text-neutral-text hover:text-text dark:text-neutral-text dark:hover:text-neutral-text'
          }`}
        >
          Statistics
        </button>
        <button
          onClick={() => setActiveSubTab('history')}
          className={`px-3 py-2 text-sm font-medium transition-colors ${
            activeSubTab === 'history'
              ? 'border-b-2 border-primary/30 text-info dark:text-info dark:border-primary/30'
              : 'text-neutral-text hover:text-text dark:text-neutral-text dark:hover:text-neutral-text'
          }`}
        >
          History
        </button>
      </div>

      {/* Sub-tab content */}
      {activeSubTab === 'statistics' && (
        <>
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="text-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary/30 mx-auto mb-4"></div>
                <p className="text-neutral-text dark:text-neutral-text">Loading statistics...</p>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center py-16">
              <div className="text-center">
                <p className="text-error">{error}</p>
              </div>
            </div>
          ) : (
            <AlertStatsPage
              alerts={alerts}
              meta={alertsMeta}
              onFilterChange={setAlertFilters}
              currentFilters={alertFilters}
              onRefreshRef={refreshStatsRef}
            />
          )}
        </>
      )}

      {activeSubTab === 'history' && (
        <AlertHistoryPanel
          initialRuleId={initialRuleId}
          initialStatus={initialStatus}
        />
      )}
    </div>
  );
}
