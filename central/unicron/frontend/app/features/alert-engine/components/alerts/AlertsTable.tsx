import React, { useState } from "react";
import Card from "../ui/Card";
import AlertDetailsModal from "./AlertDetailsModal";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import type { Alert, AlertStatus } from "../../types";
import { formatAlertStackLabel } from "~/utils/alertStack";
import {
  getStatusBadgeClasses,
  getStatusIconClasses,
  getStatusSoftSurfaceClasses,
} from "~/utils/theme";
import { formatLocalDateTime } from "../../utils/date";

interface AlertsTableProps {
  alerts: Alert[];
  onAcknowledge?: (alertId: string, comment?: string) => Promise<void>;
  isAcknowledging?: boolean;
}

// Status badge component
const StatusBadge: React.FC<{ status: AlertStatus }> = ({ status }) => {
  const statusLabels: Record<AlertStatus, string> = {
    firing: "Firing",
    acknowledged: "Acknowledged",
  };

  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${getStatusBadgeClasses(status)}`}>
      {statusLabels[status] || statusLabels.firing}
    </span>
  );
};

const AlertsTable: React.FC<AlertsTableProps> = ({
  alerts,
  onAcknowledge,
  isAcknowledging = false,
}) => {
  const [actioningAlertId, setActioningAlertId] = useState<string | null>(null);
  const [actionType, setActionType] = useState<'acknowledge' | null>(null);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleRowClick = (alert: Alert, e: React.MouseEvent) => {
    // Don't open modal if clicking on action buttons
    if ((e.target as HTMLElement).closest('button')) return;
    setSelectedAlert(alert);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedAlert(null);
  };

  const handleAcknowledge = async (alertId: string) => {
    if (!onAcknowledge) return;
    setActioningAlertId(alertId);
    setActionType('acknowledge');
    try {
      await onAcknowledge(alertId);
    } finally {
      setActioningAlertId(null);
      setActionType(null);
    }
  };

  const isActionPending = (alertId: string) => {
    return actioningAlertId === alertId;
  };

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="bg-gradient-to-r from-foreground/70 to-alt-foreground dark:from-foreground dark:to-alt-foreground border-b border-divider/60 dark:border-divider/60">
              <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Alert</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Rule</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Container</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Status</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Time</th>
              <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-divider/40 dark:divide-divider/40">
            {alerts.map((alert, index) => {
              const alertStatus: AlertStatus =
                alert.status === 'acknowledged' ? 'acknowledged' : 'firing';
              const isPending = isActionPending(alert.id);
              const showAcknowledge = alertStatus === 'firing' && onAcknowledge;
              const stackLabel = formatAlertStackLabel(alert.count);

              return (
                <tr
                  key={alert.id}
                  onClick={(e) => handleRowClick(alert, e)}
                  className="hover:bg-foreground/70 dark:hover:bg-foreground/50 transition-colors duration-200 group animate-fade-in cursor-pointer"
                  style={{animationDelay: `${index * 50}ms`}}
                >
                  <td className="px-6 py-5">
                    <div className="flex items-center">
                      <div className={`mr-4 rounded-xl border p-2 transition-all duration-200 group-hover:brightness-105 ${getStatusSoftSurfaceClasses(alertStatus)}`}>
                        <AlertCircle className={`w-5 h-5 ${getStatusIconClasses(alertStatus)}`} />
                      </div>
                      <div>
                        <div className="inline-flex max-w-md items-center gap-2">
                          <span className="truncate text-sm font-semibold text-text dark:text-text">
                            {alert.message}
                          </span>
                          {stackLabel && (
                            <span className="rounded-full border border-warning/30 bg-warning/15 px-1.5 py-0 text-[11px] font-semibold text-warning-800 dark:text-warning-300">
                              {stackLabel}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <div className="status-indicator status-info">
                      {alert.rule_name}
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <div className="text-sm font-medium text-text dark:text-neutral-text">
                      {alert.context?.container_identifier || 'N/A'}
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <StatusBadge status={alertStatus} />
                  </td>
                  <td className="px-6 py-5">
                    <div className="text-sm text-neutral-text dark:text-neutral-text font-mono">{formatLocalDateTime(alert.timestamp)}</div>
                  </td>
                  <td className="px-6 py-5">
                    <div className="flex items-center gap-2">
                      {showAcknowledge && (
                        <button
                          onClick={() => handleAcknowledge(alert.id)}
                          disabled={isPending}
                          className="inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-lg
                            bg-warning/10 text-warning hover:bg-warning/15
                            border border-warning/30
                            disabled:opacity-50 disabled:cursor-not-allowed
                            transition-colors duration-200"
                          title="Acknowledge this alert"
                        >
                          {isPending && actionType === 'acknowledge' ? (
                            <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                          ) : (
                            <Check className="w-3.5 h-3.5 mr-1.5" />
                          )}
                          Acknowledge
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {alerts.length === 0 && (
          <div className="text-center py-16">
            <div className="p-6 bg-gradient-to-br from-alt-foreground to-neutral/20 dark:from-foreground dark:to-alt-foreground rounded-3xl w-24 h-24 mx-auto mb-6 flex items-center justify-center">
              <AlertCircle className="w-12 h-12 text-neutral-text dark:text-neutral-text" />
            </div>
            <h3 className="text-lg font-semibold text-text dark:text-text mb-2">No alerts found</h3>
            <p className="text-neutral-text dark:text-neutral-text">Your system is running smoothly with no alerts to display.</p>
          </div>
        )}
      </div>

      {/* Alert Details Modal */}
      <AlertDetailsModal
        alert={selectedAlert}
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        onAcknowledge={onAcknowledge}
      />
    </Card>
  );
};

export default AlertsTable;
