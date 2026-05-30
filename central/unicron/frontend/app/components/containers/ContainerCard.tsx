/**
 * ContainerCard Component
 *
 * Card display for a container showing name, status, health, alerts, and monitoring toggle.
 * Used in grid view for visual overview of containers.
 */

import React from "react";
import { AlertTriangle, Info, Container } from "lucide-react";
import { HealthDot } from "./HealthDot";
import type { ContainerInfo } from "./ContainersTable";
import { LogCollectionBadge } from "./logCollection";
import { formatAlertStackLabel } from "~/utils/alertStack";

// ============================================================================
// Types
// ============================================================================

export interface ContainerCardProps {
  /** Container data */
  container: ContainerInfo;
  /** Click handler for card navigation */
  onClick?: () => void;
  /** Click handler for alert pill */
  onAlertClick?: () => void;
  /** Number of alerts for this container */
  alertCount?: number;
  /** Stack occurrences for single-alert containers */
  alertStackCount?: number;
  /** Highest severity among unacknowledged alerts */
  alertSeverity?: "critical" | "warning" | "info";
  /** Severity breakdown for tooltip */
  alertBreakdown?: { critical: number; warning: number; info: number };
  /** Container health status */
  healthStatus?: "healthy" | "unhealthy" | "starting" | "disabled" | null;
  /** Whether container has health check configured */
  hasHealthCheck?: boolean;
  /** Health check failing streak count */
  failingStreak?: number;
  /** Container running status */
  status?: string;
  /** Whether monitoring is enabled for this container */
  isMonitored?: boolean;
  /** Callback when monitoring toggle changes */
  onMonitoringChange?: (enabled: boolean) => void;
  /** Whether a toggle request is in-flight for this container */
  isToggling?: boolean;
}

// ============================================================================
// Helper Functions
// ============================================================================

function getStatusBadgeClasses(status: string | undefined): string {
  const normalizedStatus = status?.toLowerCase() ?? "";

  if (normalizedStatus === "running") {
    return "bg-success/15 text-success border-success/40";
  }
  if (normalizedStatus === "stopped" || normalizedStatus === "exited") {
    return "bg-error/15 text-error border-error/40";
  }
  if (normalizedStatus === "restarting") {
    return "bg-warning/15 text-warning border-warning/40";
  }
  return "bg-neutral/10 text-neutral border-neutral/30";
}

function truncateName(name: string, maxLength: number = 24): string {
  if (name.length <= maxLength) return name;
  return name.slice(0, maxLength - 3) + "...";
}

/**
 * Returns Tailwind CSS classes for the alert pill based on severity.
 * Falls back to warning colors when no severity is provided (backward compat).
 */
function getAlertPillClasses(severity?: "critical" | "warning" | "info"): string {
  switch (severity) {
    case "critical":
      return "bg-error/15 text-error border border-error/30 hover:bg-error/25 focus:ring-error/40";
    case "info":
      return "bg-primary/15 text-primary border border-primary/30 hover:bg-primary/25 focus:ring-primary/40";
    case "warning":
    default:
      return "bg-warning/15 text-warning border border-warning/30 hover:bg-warning/25 focus:ring-warning/40";
  }
}

/**
 * Returns the appropriate icon component for the alert pill severity.
 * Info severity uses Info icon; critical/warning use AlertTriangle.
 */
function AlertPillIcon({ severity }: { severity?: "critical" | "warning" | "info" }) {
  if (severity === "info") {
    return <Info className="h-3 w-3" />;
  }
  return <AlertTriangle className="h-3 w-3" />;
}

/**
 * Formats the severity breakdown into a tooltip string.
 * Omits zero-count severities. Example: "2 critical, 5 warning"
 */
function formatBreakdownTooltip(breakdown?: { critical: number; warning: number; info: number }): string | undefined {
  if (!breakdown) return undefined;
  const parts: string[] = [];
  if (breakdown.critical > 0) parts.push(`${breakdown.critical} critical`);
  if (breakdown.warning > 0) parts.push(`${breakdown.warning} warning`);
  if (breakdown.info > 0) parts.push(`${breakdown.info} info`);
  return parts.length > 0 ? parts.join(", ") : undefined;
}

/** CSS keyframes for pill fade-in animation, rendered once per mount. */
const PILL_FADE_IN_STYLE = `@keyframes pill-fade-in { from { opacity: 0; } to { opacity: 1; } }`;

// ============================================================================
// Toggle Switch Component
// ============================================================================

interface ToggleSwitchProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  label?: string;
  isLoading?: boolean;
  disabled?: boolean;
}

const ToggleSwitch: React.FC<ToggleSwitchProps> = ({ enabled, onChange, label, isLoading = false, disabled = false }) => {
  return (
    <label className="flex cursor-pointer items-center gap-xs">
      <div
        className={`
          relative h-5 w-9 rounded-full transition-colors
          ${enabled ? "bg-primary" : "bg-neutral/30"}
          ${disabled || isLoading ? "opacity-50 pointer-events-none" : ""}
        `}
        onClick={(e) => {
          e.stopPropagation();
          if (!disabled && !isLoading) {
            onChange(!enabled);
          }
        }}
      >
        <div className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full shadow-sm transition-transform duration-200 ${enabled ? "translate-x-4" : "translate-x-0"} ${isLoading ? "bg-transparent" : "bg-white"}`}>
          {isLoading && (
            <div className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
          )}
        </div>
      </div>
      {label && (
        <span className="text-xs text-neutral">{label}</span>
      )}
    </label>
  );
};

// ============================================================================
// Main Component
// ============================================================================

export const ContainerCard: React.FC<ContainerCardProps> = React.memo(
  ({
    container,
    onClick,
    onAlertClick,
    alertCount = 0,
    alertStackCount,
    alertSeverity,
    alertBreakdown,
    healthStatus,
    hasHealthCheck = false,
    failingStreak,
    status,
    isMonitored = false,
    onMonitoringChange,
    isToggling = false,
  }) => {
    const handleMonitoringChange = (enabled: boolean) => {
      onMonitoringChange?.(enabled);
    };

    const handleAlertClick = (e: React.MouseEvent) => {
      e.stopPropagation();
      onAlertClick?.();
    };

    const statusBadgeClasses = getStatusBadgeClasses(status);
    const displayName = truncateName(container.name);
    const displayAlertCount = alertCount > 9 ? "9+" : alertCount;
    const stackLabel = formatAlertStackLabel(alertStackCount);

    return (
      <div
        className={`
          group relative rounded-xl border border-neutral/20
          bg-background p-md shadow-sm transition-all duration-200
          hover:shadow-md hover:-translate-y-0.5
          dark:bg-neutral-900
          ${onClick ? "cursor-pointer" : ""}
        `}
        onClick={onClick}
      >
        {/* Health Dot - Top Right */}
        {hasHealthCheck && (
          <div className="absolute right-3 top-3">
            <HealthDot
              status={healthStatus ?? null}
              failingStreak={failingStreak}
            />
          </div>
        )}

        {/* Container Icon and Name */}
        <div className="mb-sm flex items-start gap-sm">
          <div className="rounded-xl bg-primary/10 p-2xs transition-all group-hover:bg-primary/20">
            <Container className="h-6 w-6 text-primary" />
          </div>
          <div className="min-w-0 flex-1 pr-4">
            <h3
              className="truncate text-sm font-semibold text-text"
              title={container.name}
            >
              {displayName}
            </h3>
            <p className="truncate text-xs text-neutral" title={container.identifier}>
              {container.identifier}
            </p>
          </div>
        </div>

        {/* Status and Alert Summary */}
        <div className="mb-sm flex flex-wrap items-center gap-2">
          <span
            className={`
              inline-flex items-center rounded-full border px-2 py-0.5
              text-xs font-medium capitalize
              ${statusBadgeClasses}
            `}
          >
            {status ?? "unknown"}
          </span>
          {alertCount > 0 && (
            <>
              <style>{PILL_FADE_IN_STYLE}</style>
              <button
                type="button"
                onClick={handleAlertClick}
                title={formatBreakdownTooltip(alertBreakdown)}
                className={`
                  inline-flex items-center gap-1 rounded-full
                  px-2.5 py-0.5 text-xs font-medium leading-none
                  transition-colors
                  focus:outline-none focus:ring-2
                  ${getAlertPillClasses(alertSeverity)}
                `}
                style={{ animation: "pill-fade-in 200ms ease-out" }}
              >
                <AlertPillIcon severity={alertSeverity} />
                <span>
                  {displayAlertCount} alert{alertCount !== 1 ? "s" : ""}
                </span>
                {stackLabel && (
                  <span className="rounded-full bg-white/70 px-1.5 py-0 text-[10px] font-semibold dark:bg-neutral-900/60">
                    {stackLabel}
                  </span>
                )}
              </button>
            </>
          )}
          <LogCollectionBadge
            monitored={isMonitored}
            status={container.log_collection_status}
            issue={container.log_collection_issue}
          />
        </div>

        {/* Monitoring Toggle */}
        <div className="mt-sm flex items-center justify-between border-t border-neutral/10 pt-sm">
          <span className="text-xs text-neutral">Monitoring</span>
          <ToggleSwitch
            enabled={isMonitored}
            onChange={handleMonitoringChange}
            label={isMonitored ? "On" : "Off"}
            isLoading={isToggling}
            disabled={isToggling}
          />
        </div>
      </div>
    );
  }
);

ContainerCard.displayName = "ContainerCard";

export default ContainerCard;
