import React from "react";
import Card from "../ui/Card";
import { AlertCircle } from "lucide-react";
import type { Alert } from "../../types";
import { formatLocalDateTime } from "../../utils/date";

interface AlertsSummaryProps {
  alerts: Alert[];
  totalAlerts: number;
  loading?: boolean;
}

const AlertsSummary: React.FC<AlertsSummaryProps> = ({ alerts, totalAlerts, loading = false }) => (
  <Card className="p-6">
    <div className="flex items-center justify-between mb-6">
      <h3 className="text-xl font-bold text-text dark:text-text">Recent Alerts</h3>
      <div className="status-indicator status-error">
        {totalAlerts} total
      </div>
    </div>
    <div className="space-y-3">
      {loading && alerts.length === 0 && (
        <>
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={`alerts-loading-${index}`}
              className="flex items-start space-x-4 p-4 rounded-xl border border-divider dark:border-divider bg-foreground/70 dark:bg-foreground animate-pulse"
            >
              <div className="h-8 w-8 rounded-lg bg-neutral/20 dark:bg-alt-foreground mt-0.5" />
              <div className="flex-1 min-w-0 space-y-2">
                <div className="h-3 w-32 rounded bg-neutral/20 dark:bg-alt-foreground" />
                <div className="h-3 w-full rounded bg-neutral/20 dark:bg-alt-foreground" />
                <div className="h-3 w-28 rounded bg-neutral/20 dark:bg-alt-foreground" />
              </div>
            </div>
          ))}
        </>
      )}

      {alerts.slice(0, 5).map((alert, index) => (
        <div
          key={alert.id}
          className="flex items-start space-x-4 p-4 bg-gradient-to-r from-foreground/70 to-background dark:from-foreground dark:to-background rounded-xl border border-divider dark:border-divider hover:border-divider dark:hover:border-divider transition-all duration-200 group animate-slide-up"
          style={{animationDelay: `${index * 100}ms`}}
        >
          <div className="p-2 bg-gradient-to-br from-error/15 to-error/15 dark:from-error/20 dark:to-error/20 rounded-lg group-hover:from-error/15 group-hover:to-error/15 dark:group-hover:from-error/30 dark:group-hover:to-error/30 transition-all duration-200 mt-0.5">
            <AlertCircle className="w-4 h-4 text-error" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2 mb-1">
              <p className="text-sm font-semibold text-text dark:text-text truncate">{alert.rule_name}</p>
            </div>
            <p className="text-sm text-neutral-text dark:text-neutral-text truncate">{alert.message}</p>
            <div className="mt-2">
              <p className="text-xs text-neutral-text dark:text-neutral-text font-mono">{formatLocalDateTime(alert.timestamp)}</p>
            </div>
          </div>
        </div>
      ))}
      {alerts.length === 0 && (
        <div className="text-center py-8">
          <div className="p-4 bg-gradient-to-br from-success/15 to-success/15 dark:from-success/20 dark:to-success/20 rounded-2xl w-16 h-16 mx-auto mb-4 flex items-center justify-center">
            <AlertCircle className="w-8 h-8 text-success" />
          </div>
          <h4 className="text-sm font-semibold text-text dark:text-text mb-1">All clear!</h4>
          <p className="text-neutral-text dark:text-neutral-text text-xs">No alerts have been triggered recently</p>
        </div>
      )}
    </div>
  </Card>
);

export default AlertsSummary;
