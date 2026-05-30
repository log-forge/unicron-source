/**
 * FiringAlertsList Component
 *
 * Displays a list of currently firing alerts in a slide-out panel.
 * Shows alert severity, rule name, container context, and time since triggered.
 * Provides quick actions: acknowledge and view details.
 *
 * Phase 59-01: Migrated from useAlerts() to useAlertStore + useSyncExternalStore.
 */

import { useState, useMemo, useCallback, useEffect } from "react";
import { useSyncExternalStore } from "react";
import { useNavigate } from "react-router";
import {
  X,
  AlertCircle,
  AlertTriangle,
  Info,
  Check,
  CheckCircle,
  Eye,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Button } from "../library/buttons/Button";
import { useAlertStore, alertStore } from "../../context/AlertContext";
import type { FiringAlert, AlertStoreSnapshot } from "../../context/AlertContext";
import { formatAlertStackLabel } from "../../utils/alertStack";
import { clientLog } from "../../utils/logging/logger.client";

// ============================================================================
// Types
// ============================================================================

type AlertSeverity = "critical" | "warning" | "info";

interface FiringAlertsListProps {
  /** Close handler for the panel */
  onClose: () => void;
  /** Optional handler when clicking an alert to view details */
  onAlertClick?: (alert: FiringAlert) => void;
}

// ============================================================================
// Helpers
// ============================================================================

const SEVERITY_CONFIG: Record<
  AlertSeverity,
  { icon: typeof AlertCircle; className: string; bgClassName: string }
> = {
  critical: {
    icon: AlertCircle,
    className: "text-red-600 dark:text-red-400",
    bgClassName: "bg-red-50 dark:bg-red-900/20",
  },
  warning: {
    icon: AlertTriangle,
    className: "text-amber-600 dark:text-amber-400",
    bgClassName: "bg-amber-50 dark:bg-amber-900/20",
  },
  info: {
    icon: Info,
    className: "text-blue-600 dark:text-blue-400",
    bgClassName: "bg-blue-50 dark:bg-blue-900/20",
  },
};

/**
 * Format time difference as relative string (e.g., "5m ago", "2h ago").
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);

  if (diffSeconds < 60) {
    return `${diffSeconds}s ago`;
  }

  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }

  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

// ============================================================================
// Alert Item Component
// ============================================================================

interface AlertItemProps {
  alert: FiringAlert;
  onAcknowledge: (id: string) => void;
  onView: (alert: FiringAlert) => void;
  isAcknowledging: boolean;
}

function AlertItem({ alert, onAcknowledge, onView, isAcknowledging }: AlertItemProps) {
  const [timeAgo, setTimeAgo] = useState(() => formatRelativeTime(alert.started_at));

  // Update relative time every minute
  useEffect(() => {
    const interval = setInterval(() => {
      setTimeAgo(formatRelativeTime(alert.started_at));
    }, 60000);
    return () => clearInterval(interval);
  }, [alert.started_at]);

  const severityConfig = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;
  const SeverityIcon = severityConfig.icon;
  const stackLabel = formatAlertStackLabel(alert.count);

  return (
    <div
      className={`
        rounded-lg border border-neutral-200 p-3
        transition-colors hover:border-neutral-300
        dark:border-neutral-700 dark:hover:border-neutral-600
        ${severityConfig.bgClassName}
      `}
    >
      <div className="flex items-start gap-3">
        {/* Severity Icon */}
        <div className={`mt-0.5 flex-shrink-0 ${severityConfig.className}`}>
          <SeverityIcon className="h-5 w-5" />
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          {/* Rule Name */}
          <div className="font-medium text-neutral-900 dark:text-neutral-100">
            {alert.rule_name}
          </div>

          {/* Container Info */}
          {alert.container_name && (
            <div className="mt-0.5 text-sm text-neutral-600 dark:text-neutral-400">
              {alert.container_name}
            </div>
          )}

          {/* Stack count + Time */}
          <div className="mt-1 flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-500">
            <span>{timeAgo}</span>
            {stackLabel && (
              <span className="rounded bg-neutral-200 px-1.5 py-0.5 font-mono dark:bg-neutral-700">
                {stackLabel}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-shrink-0 items-center gap-1">
          {/* Acknowledge Button */}
          <button
            type="button"
            onClick={() => onAcknowledge(alert.alert_id)}
            disabled={isAcknowledging}
            className="
              rounded p-1.5 text-neutral-600 transition-colors
              hover:bg-neutral-200 dark:text-neutral-400 dark:hover:bg-neutral-700
              disabled:cursor-not-allowed disabled:opacity-50
            "
            title="Acknowledge"
          >
            {isAcknowledging ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
          </button>

          {/* View Button */}
          <button
            type="button"
            onClick={() => onView(alert)}
            className="
              rounded p-1.5 text-neutral-600 transition-colors
              hover:bg-neutral-200 dark:text-neutral-400 dark:hover:bg-neutral-700
            "
            title="View details"
          >
            <Eye className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function FiringAlertsList({ onClose, onAlertClick }: FiringAlertsListProps) {
  const navigate = useNavigate();
  const { acknowledgeAlert } = useAlertStore();
  const [acknowledgingIds, setAcknowledgingIds] = useState<Set<string>>(new Set());

  // Subscribe to the full snapshot
  const snapshot = useSyncExternalStore(
    alertStore.subscribe,
    alertStore.getSnapshot,
    alertStore.getSnapshot
  );

  // Get all alerts sorted by severity: critical first, then warning, then info
  const sortedAlerts = useMemo(() => {
    const alerts = Array.from(snapshot.alerts.values());
    const critical: FiringAlert[] = [];
    const warning: FiringAlert[] = [];
    const info: FiringAlert[] = [];

    for (const alert of alerts) {
      switch (alert.severity) {
        case "critical":
          critical.push(alert);
          break;
        case "warning":
          warning.push(alert);
          break;
        default:
          info.push(alert);
          break;
      }
    }

    return [...critical, ...warning, ...info];
  }, [snapshot]);

  const firingCount = snapshot.totalAlerts;

  // Handle acknowledge
  const handleAcknowledge = useCallback(
    async (alertId: string) => {
      setAcknowledgingIds((prev) => new Set(prev).add(alertId));

      try {
        await acknowledgeAlert(alertId);
        clientLog.info({ alertId }, "Alert acknowledged successfully");
      } catch (err) {
        clientLog.error({ err, alertId }, "Failed to acknowledge alert");
      } finally {
        setAcknowledgingIds((prev) => {
          const next = new Set(prev);
          next.delete(alertId);
          return next;
        });
      }
    },
    [acknowledgeAlert]
  );

  // Handle view alert
  const handleView = useCallback(
    (alert: FiringAlert) => {
      if (onAlertClick) {
        onAlertClick(alert);
      } else {
        // Navigate to alert history with filter
        navigate(`/alerting/stats?tab=history&rule_id=${alert.rule_id}`);
        onClose();
      }
    },
    [onAlertClick, navigate, onClose]
  );

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral-200 px-4 py-3 dark:border-neutral-700">
        <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Firing Alerts
        </h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onClose}
            className="
              rounded p-1 text-neutral-500 transition-colors
              hover:bg-neutral-100 hover:text-neutral-700
              dark:hover:bg-neutral-800 dark:hover:text-neutral-300
            "
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Empty State */}
        {firingCount === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <CheckCircle className="h-12 w-12 text-green-500" />
            <p className="mt-3 font-medium text-neutral-900 dark:text-neutral-100">
              No firing alerts
            </p>
            <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
              All systems are operating normally.
            </p>
          </div>
        )}

        {/* Alert List */}
        {sortedAlerts.length > 0 && (
          <div className="space-y-2">
            {sortedAlerts.map((alert) => (
              <AlertItem
                key={alert.alert_id}
                alert={alert}
                onAcknowledge={handleAcknowledge}
                onView={handleView}
                isAcknowledging={acknowledgingIds.has(alert.alert_id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      {firingCount > 0 && (
        <div className="border-t border-neutral-200 px-4 py-3 dark:border-neutral-700">
          <Button
            variant="ghost"
            tone="primary"
            padding={["xs", "3xs"]}
            radius="md"
            onPress={() => {
              navigate("/alerting/stats?tab=history&status=firing");
              onClose();
            }}
            className="w-full"
          >
            View all in history
          </Button>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// Exports
// ============================================================================

export default FiringAlertsList;
