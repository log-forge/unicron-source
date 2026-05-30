import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Clock,
  Loader2,
  RefreshCw,
  XCircle,
} from "lucide-react";
import Modal from "../ui/Modal";
import type { Alert, AlertStatus } from "../../types";
import { apiService, type DeliveryStatus } from "../../services/api";
import { formatAlertStackLabel } from "~/utils/alertStack";
import {
  getSeverityBadgeClasses,
  getStatusBadgeClasses,
  getStatusIconClasses,
  getStatusSoftSurfaceClasses,
} from "~/utils/theme";
import { formatLocalDateTime } from "../../utils/date";

interface AlertDetailsModalProps {
  alert: Alert | null;
  isOpen: boolean;
  onClose: () => void;
  onAcknowledge?: (alertId: string, comment?: string) => Promise<void>;
}

// Status badge component (reused from AlertsTable)
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

// Severity badge component
const SeverityBadge: React.FC<{ severity?: string }> = ({ severity }) => {
  const label = severity || "info";

  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${getSeverityBadgeClasses(label)}`}>
      {label}
    </span>
  );
};

// Delivery status icon component
const DeliveryStatusIcon: React.FC<{ status: DeliveryStatus['status'] }> = ({ status }) => {
  switch (status) {
    case 'sent':
      return <CheckCircle2 className={`w-5 h-5 ${getStatusIconClasses(status)}`} />;
    case 'failed':
      return <XCircle className={`w-5 h-5 ${getStatusIconClasses(status)}`} />;
    case 'retrying':
      return <RefreshCw className={`w-5 h-5 animate-spin ${getStatusIconClasses(status)}`} />;
    case 'pending':
    default:
      return <Clock className={`w-5 h-5 ${getStatusIconClasses(status)}`} />;
  }
};

const AlertDetailsModal: React.FC<AlertDetailsModalProps> = ({
  alert,
  isOpen,
  onClose,
  onAcknowledge,
}) => {
  const [deliveryStatus, setDeliveryStatus] = useState<DeliveryStatus[]>([]);
  const [isLoadingDelivery, setIsLoadingDelivery] = useState(false);
  const [actionLoading, setActionLoading] = useState<'acknowledge' | null>(null);

  // Fetch delivery status when modal opens
  useEffect(() => {
    if (isOpen && alert) {
      setIsLoadingDelivery(true);
      apiService
        .getAlertDeliveryStatus(alert.id)
        .then(setDeliveryStatus)
        .catch((err) => {
          console.error('Failed to fetch delivery status:', err);
          setDeliveryStatus([]);
        })
        .finally(() => setIsLoadingDelivery(false));
    } else {
      setDeliveryStatus([]);
    }
  }, [isOpen, alert?.id]);

  if (!alert) return null;

  const alertStatus: AlertStatus =
    alert.status === 'acknowledged' ? 'acknowledged' : 'firing';
  const canAcknowledge = alertStatus === 'firing' && typeof onAcknowledge === 'function';
  const stackLabel = formatAlertStackLabel(alert.count);
  const alertContext = (alert.context && typeof alert.context === 'object') ? alert.context : {};
  const matchingLog = alertContext?.matching_log;
  const matchingLogMessage =
    typeof matchingLog?.message === 'string' && matchingLog.message.trim().length > 0
      ? matchingLog.message
      : null;
  const hostId =
    typeof alertContext?.host_id === 'string' && alertContext.host_id.trim().length > 0
      ? alertContext.host_id
      : null;
  const containerName =
    typeof alertContext?.container_name === 'string' && alertContext.container_name.trim().length > 0
      ? alertContext.container_name
      : typeof alertContext?.container_identifier === 'string' && alertContext.container_identifier.trim().length > 0
        ? alertContext.container_identifier
        : null;

  const handleAcknowledge = async () => {
    if (!onAcknowledge) return;
    setActionLoading('acknowledge');
    try {
      await onAcknowledge(alert.id);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Alert Details"
      panelClassName="max-w-7xl"
    >
      <div className="space-y-6">
        {/* Alert Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className={`rounded-xl border p-3 ${getStatusSoftSurfaceClasses(alertStatus)}`}>
              <AlertCircle className={`w-6 h-6 ${getStatusIconClasses(alertStatus)}`} />
            </div>
            <div className="min-w-0">
              <h4 className="text-lg font-semibold text-text dark:text-text break-words">
                {alert.rule_name}
              </h4>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <StatusBadge status={alertStatus} />
                <SeverityBadge severity={alert.severity} />
                {stackLabel && (
                  <span className="inline-flex items-center rounded-full border border-warning/30 bg-warning/15 px-2.5 py-0.5 text-xs font-semibold text-warning-800 dark:text-warning-300">
                    {stackLabel}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Alert Message */}
        <div className="bg-foreground/70 dark:bg-foreground/50 rounded-xl p-4">
          <p className="text-text dark:text-neutral-text break-words whitespace-pre-wrap">
            {alert.message}
          </p>
        </div>

        {/* Alert Metadata */}
        <dl className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div className="min-w-0 rounded-xl border border-divider bg-foreground/80 p-4 dark:border-divider dark:bg-foreground/40">
            <dt className="text-sm font-medium text-neutral-text dark:text-neutral-text">Triggered</dt>
            <dd className="mt-1 text-sm text-text dark:text-text font-mono break-words">
              {formatLocalDateTime(alert.timestamp)}
            </dd>
          </div>
          <div className="min-w-0 rounded-xl border border-divider bg-foreground/80 p-4 dark:border-divider dark:bg-foreground/40">
            <dt className="text-sm font-medium text-neutral-text dark:text-neutral-text">Host</dt>
            <dd className="mt-1 text-sm text-text dark:text-text break-words">
              {hostId || 'N/A'}
            </dd>
          </div>
          <div className="min-w-0 rounded-xl border border-divider bg-foreground/80 p-4 dark:border-divider dark:bg-foreground/40">
            <dt className="text-sm font-medium text-neutral-text dark:text-neutral-text">Container</dt>
            <dd className="mt-1 text-sm text-text dark:text-text break-words">
              {containerName || 'N/A'}
            </dd>
          </div>
        </dl>

        {matchingLogMessage && (
          <div className="bg-foreground/70 dark:bg-foreground/50 rounded-xl p-4">
            <dt className="text-sm font-medium text-neutral-text dark:text-neutral-text mb-2">Matching Log</dt>
            <dd className="overflow-x-auto text-sm text-text dark:text-text font-mono break-words whitespace-pre-wrap">
              {matchingLogMessage}
            </dd>
          </div>
        )}

        {/* Action Buttons */}
        {canAcknowledge && (
          <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-divider dark:border-divider">
            <button
              onClick={handleAcknowledge}
              disabled={actionLoading !== null}
              className="inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg
                bg-warning/10 text-warning hover:bg-warning/15
                border border-warning/30
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors duration-200"
            >
              {actionLoading === 'acknowledge' ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Check className="w-4 h-4 mr-2" />
              )}
              Acknowledge
            </button>
          </div>
        )}

        {/* Delivery Status Section */}
        <div className="pt-4 border-t border-divider dark:border-divider">
          <h5 className="text-sm font-semibold text-text dark:text-text mb-3">
            Delivery Status
          </h5>

          {isLoadingDelivery ? (
            <div className="flex items-center justify-center py-6">
              <Loader2 className="w-6 h-6 text-neutral-text animate-spin" />
            </div>
          ) : deliveryStatus.length === 0 ? (
            <div className="text-center py-6">
              <Clock className="w-8 h-8 text-neutral-text dark:text-neutral-text mx-auto mb-2" />
              <p className="text-sm text-neutral-text dark:text-neutral-text">
                No notifications sent yet
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {deliveryStatus.map((status, index) => (
                <div
                  key={index}
                  className="flex flex-col gap-3 rounded-lg bg-foreground/70 p-3 dark:bg-foreground/50 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex items-center gap-3">
                    <DeliveryStatusIcon status={status.status} />
                    <div>
                      <p className="text-sm font-medium text-text dark:text-text">
                        {status.channel_name}
                      </p>
                      <p className="text-xs text-neutral-text dark:text-neutral-text capitalize">
                        {status.channel_type}
                      </p>
                    </div>
                  </div>
                  <div className="text-left sm:text-right">
                    <p className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${getStatusBadgeClasses(status.status)}`}>
                      {status.status}
                    </p>
                    {status.sent_at && (
                      <p className="text-xs text-neutral-text dark:text-neutral-text font-mono">
                        {formatLocalDateTime(status.sent_at)}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Modal>
  );
};

export default AlertDetailsModal;
