/**
 * Stats Cards Component
 *
 * Displays a grid of 4 metric cards showing key system statistics:
 * - Total Alerts (with 24h breakdown)
 * - Active Rules (with disabled count)
 * - Containers (monitored instances)
 * - System Status (health indicator)
 */

import { AlertCircle, Bell, Container, Shield } from "lucide-react";

// ============================================================================
// Types
// ============================================================================

interface StatsCardsProps {
  alertsCount: number;
  alertsLast24h: number;
  rulesTotal: number;
  rulesEnabled: number;
  containersCount: number;
  isHealthy: boolean;
  isLoading?: boolean;
}

// ============================================================================
// Stats Card Component
// ============================================================================

interface StatCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  iconBgClass: string;
  iconBgHoverClass: string;
}

function StatCard({ label, value, subtitle, icon, iconBgClass, iconBgHoverClass }: StatCardProps) {
  return (
    <div className="group rounded-xl border border-neutral/20 bg-background p-md shadow-sm transition-all duration-200 hover:shadow-md dark:bg-neutral-900">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-neutral">
            {label}
          </p>
          <p className="mt-2xs text-2xl font-bold text-text">
            {value}
          </p>
          {subtitle && (
            <p className="mt-3xs text-xs text-neutral">
              {subtitle}
            </p>
          )}
        </div>
        <div
          className={`rounded-xl p-sm transition-all duration-300 ${iconBgClass} group-hover:${iconBgHoverClass}`}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// Skeleton Loader
// ============================================================================

function StatsCardsSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-md sm:grid-cols-2 xl:grid-cols-4">
      {[1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="rounded-xl border border-neutral/20 bg-background p-md shadow-sm dark:bg-neutral-900"
        >
          <div className="flex items-center justify-between">
            <div className="min-w-0 flex-1 space-y-2">
              <div className="h-3 w-20 animate-pulse rounded bg-neutral/20" />
              <div className="h-7 w-16 animate-pulse rounded bg-neutral/20" />
              <div className="h-3 w-24 animate-pulse rounded bg-neutral/20" />
            </div>
            <div className="h-12 w-12 animate-pulse rounded-xl bg-neutral/20" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

export function StatsCards({
  alertsCount,
  alertsLast24h,
  rulesTotal,
  rulesEnabled,
  containersCount,
  isHealthy,
  isLoading = false,
}: StatsCardsProps) {
  if (isLoading) {
    return <StatsCardsSkeleton />;
  }

  const rulesDisabled = rulesTotal - rulesEnabled;

  return (
    <div className="grid grid-cols-1 gap-md sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        label="Total Alerts"
        value={alertsCount}
        subtitle={`${alertsLast24h} in last 24h`}
        icon={<AlertCircle className="h-6 w-6 text-error" />}
        iconBgClass="bg-error/10"
        iconBgHoverClass="bg-error/20"
      />

      <StatCard
        label="Active Rules"
        value={rulesEnabled}
        subtitle={`${rulesDisabled} disabled`}
        icon={<Shield className="h-6 w-6 text-primary" />}
        iconBgClass="bg-primary/10"
        iconBgHoverClass="bg-primary/20"
      />

      <StatCard
        label="Containers"
        value={containersCount}
        subtitle="Monitored instances"
        icon={<Container className="h-6 w-6 text-success" />}
        iconBgClass="bg-success/10"
        iconBgHoverClass="bg-success/20"
      />

      <StatCard
        label="System Status"
        value={isHealthy ? "Healthy" : "Error"}
        subtitle="Engine status"
        icon={
          <Bell
            className={`h-6 w-6 ${isHealthy ? "text-success" : "text-error"}`}
          />
        }
        iconBgClass={isHealthy ? "bg-success/10" : "bg-error/10"}
        iconBgHoverClass={isHealthy ? "bg-success/20" : "bg-error/20"}
      />
    </div>
  );
}

export default StatsCards;
