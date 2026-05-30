/**
 * Recent Alerts Component
 *
 * Displays the 5 most recent alerts in a card format.
 */

import { AlertCircle, Clock } from "lucide-react";
import { useNavigate } from "react-router";
import type { AlertHistoryEntry } from "../../utils/api/alert-engine";
import { Button } from "../library/buttons/Button";

// ============================================================================
// Types
// ============================================================================

interface RecentAlertsProps {
  alerts: AlertHistoryEntry[];
  isLoading?: boolean;
}

// ============================================================================
// Helper Functions
// ============================================================================

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function getSeverityColor(severity: string): string {
  switch (severity) {
    case "critical":
      return "text-error bg-error/10";
    case "warning":
      return "text-warning bg-warning/10";
    case "info":
    default:
      return "text-primary bg-primary/10";
  }
}

// ============================================================================
// Skeleton Loader
// ============================================================================

function RecentAlertsSkeleton() {
  return (
    <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
      <div className="mb-md flex items-center justify-between">
        <div className="h-5 w-28 animate-pulse rounded bg-neutral/20" />
        <div className="h-8 w-20 animate-pulse rounded bg-neutral/20" />
      </div>
      <div className="space-y-sm">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="flex items-start gap-sm rounded-lg border border-neutral/10 p-sm"
          >
            <div className="h-8 w-8 animate-pulse rounded-lg bg-neutral/20" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-3/4 animate-pulse rounded bg-neutral/20" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-neutral/20" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function RecentAlerts({ alerts, isLoading = false }: RecentAlertsProps) {
  const navigate = useNavigate();

  if (isLoading) {
    return <RecentAlertsSkeleton />;
  }

  const recentAlerts = alerts.slice(0, 5);

  return (
    <div className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900">
      <div className="mb-md flex items-center justify-between">
        <h3 className="text-base font-semibold text-text">Recent Alerts</h3>
        <Button
          variant="ghost"
          tone="primary"
          textSize="xs"
          padding="3xs"
          onPress={() => navigate("/alerting/stats?tab=history")}
        >
          View all
        </Button>
      </div>

      {recentAlerts.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-lg text-center">
          <div className="mb-sm rounded-full bg-neutral/10 p-md">
            <AlertCircle className="h-8 w-8 text-neutral" />
          </div>
          <p className="text-sm text-neutral">No alerts recorded yet</p>
          <p className="text-xs text-neutral/60">
            Alerts will appear here when triggered
          </p>
        </div>
      ) : (
        <div className="space-y-sm">
          {recentAlerts.map((alert) => (
            <div
              key={alert.id}
              className="group flex items-start gap-sm rounded-lg border border-neutral/10 p-sm transition-colors hover:border-neutral/30 hover:bg-neutral/5"
            >
              <div
                className={`rounded-lg p-2xs ${getSeverityColor(alert.severity)}`}
              >
                <AlertCircle className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text">
                  {alert.rule_name}
                </p>
                <div className="mt-3xs flex items-center gap-xs text-xs text-neutral">
                  <Clock className="h-3 w-3" />
                  <span>{formatRelativeTime(alert.triggered_at)}</span>
                  <span className="capitalize">
                    {"\u2022"} {alert.severity}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default RecentAlerts;
