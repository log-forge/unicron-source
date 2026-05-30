import React from "react";
import Card from "../ui/Card";
import { AlertCircle, Shield, Container, Bell } from "lucide-react";
import type { Alert, AlertRule, ContainerInfo } from "../../types";
import { getStatusIconClasses, getStatusSoftSurfaceClasses } from "~/utils/theme";

interface StatsCardsProps {
  alerts: Alert[];
  totalAlerts: number;
  rules: AlertRule[];
  containers?: ContainerInfo[];
  containerCount?: number;
  health: any;
  loading?: boolean;
}

const StatsCards: React.FC<StatsCardsProps> = ({
  alerts,
  totalAlerts,
  rules,
  containers,
  containerCount,
  health,
  loading = false,
}) => {
  const valueClass = "mt-2 text-3xl font-bold text-text";
  const subtextClass = "mt-1 text-xs text-neutral-text";
  const streamTotals = health?.backpressure?.streams?.totals;
  const pressureAlerts: string[] = health?.backpressure?.alerts || [];
  const pressureStatus = health?.backpressure?.status;
  const hasCriticalPressure = pressureStatus === 'critical';
  const hasWarningPressure = pressureStatus === 'warning';
  const systemStatusLabel =
    health?.status === 'error'
      ? 'Error'
      : hasCriticalPressure
      ? 'Critical'
      : health?.status === 'degraded' || hasWarningPressure
      ? 'Degraded'
      : 'Healthy';
  const systemStatusValue =
    systemStatusLabel === "Healthy"
      ? "healthy"
      : systemStatusLabel === "Degraded"
      ? "degraded"
      : "critical";
  const systemSecondaryText = pressureAlerts.length > 0
    ? pressureAlerts[0]
    : streamTotals
    ? `Lag ${streamTotals.lag ?? 0} • Pending ${streamTotals.pending ?? 0} • DLQ ${streamTotals.dlq_depth ?? 0}`
    : 'Engine status';
  const effectiveContainerCount =
    typeof containerCount === "number"
      ? containerCount
      : Array.isArray(containers)
      ? containers.length
      : 0;

  const renderPrimaryValue = (value: string | number) => (
    loading ? (
      <div className="mt-2 h-9 w-16 animate-pulse rounded bg-neutral/20 dark:bg-alt-foreground" />
    ) : (
      <p className={valueClass}>{value}</p>
    )
  );

  const renderSecondaryValue = (value: string) => (
    loading ? (
      <div className="mt-1 h-3 w-24 animate-pulse rounded bg-neutral/20 dark:bg-alt-foreground" />
    ) : (
      <p className={subtextClass}>{value}</p>
    )
  );

  return (
  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6">
    <Card className="p-6 card-hover group">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold uppercase tracking-wide text-neutral-text">Total Alerts</p>
          {renderPrimaryValue(totalAlerts)}
          {renderSecondaryValue(
            `${alerts.filter(a => new Date(a.timestamp) > new Date(Date.now() - 24*60*60*1000)).length} in last 24h`
          )}
        </div>
        <div className="rounded-2xl border p-4 transition-all duration-300 group-hover:brightness-105 bg-error/10 text-error border-error/30">
          <AlertCircle className="w-8 h-8 transition-transform duration-300 group-hover:scale-110" />
        </div>
      </div>
    </Card>

    <Card className="p-6 card-hover group">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold uppercase tracking-wide text-neutral-text">Active Rules</p>
          {renderPrimaryValue(rules.filter(r => r.enabled).length)}
          {renderSecondaryValue(`${rules.length - rules.filter(r => r.enabled).length} disabled`)}
        </div>
        <div className="rounded-2xl border border-info/30 bg-info/10 p-4 text-info transition-all duration-300 group-hover:brightness-105">
          <Shield className="w-8 h-8 transition-transform duration-300 group-hover:scale-110" />
        </div>
      </div>
    </Card>

    <Card className="p-6 card-hover group">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold uppercase tracking-wide text-neutral-text">Containers</p>
          {renderPrimaryValue(effectiveContainerCount)}
          {renderSecondaryValue('Monitored instances')}
        </div>
        <div className="rounded-2xl border border-success/30 bg-success/10 p-4 text-success transition-all duration-300 group-hover:brightness-105">
          <Container className="w-8 h-8 transition-transform duration-300 group-hover:scale-110" />
        </div>
      </div>
    </Card>

    <Card className="p-6 card-hover group">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold uppercase tracking-wide text-neutral-text">System Status</p>
          {renderPrimaryValue(systemStatusLabel)}
          {renderSecondaryValue(systemSecondaryText)}
        </div>
        <div className={`rounded-2xl border p-4 transition-all duration-300 group-hover:brightness-105 ${getStatusSoftSurfaceClasses(systemStatusValue)}`}>
          <Bell className={`w-8 h-8 transition-transform duration-300 group-hover:scale-110 ${getStatusIconClasses(systemStatusValue)}`} />
        </div>
      </div>
    </Card>
  </div>
  );
};

export default StatsCards;
