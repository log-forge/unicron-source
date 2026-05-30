/**
 * FiringAlertsBadge Component
 *
 * Displays a bell icon with a count badge showing currently firing alerts.
 * Badge color indicates highest severity level:
 * - Red: Critical alerts present
 * - Amber: Warning alerts (no critical)
 * - Gray: No alerts or info only
 *
 * Includes connection status indicator.
 *
 * Phase 59-01: Migrated from useAlerts() to useTotalAlerts/useAlertCounts.
 */

import { useMemo } from "react";
import { Bell } from "lucide-react";
import { useTotalAlerts } from "../../hooks/useTotalAlerts";
import { useAlertCounts } from "../../hooks/useAlertCounts";

// ============================================================================
// Types
// ============================================================================

interface FiringAlertsBadgeProps {
  /** Click handler to open alerts panel */
  onClick: () => void;
  /** Additional CSS classes */
  className?: string;
}

// ============================================================================
// Component
// ============================================================================

export function FiringAlertsBadge({ onClick, className = "" }: FiringAlertsBadgeProps) {
  const firingCount = useTotalAlerts();
  const { alertsBySeverity, isConnected } = useAlertCounts();

  // Determine highest severity
  const highestSeverity = useMemo((): "critical" | "warning" | "info" | null => {
    if (alertsBySeverity.critical > 0) return "critical";
    if (alertsBySeverity.warning > 0) return "warning";
    if (alertsBySeverity.info > 0) return "info";
    return null;
  }, [alertsBySeverity]);

  // Determine badge color based on highest severity
  const badgeColor = useMemo(() => {
    if (firingCount === 0) return "bg-neutral-400";
    switch (highestSeverity) {
      case "critical":
        return "bg-red-500";
      case "warning":
        return "bg-amber-500";
      default:
        return "bg-blue-500";
    }
  }, [firingCount, highestSeverity]);

  // Pulse animation for critical alerts
  const shouldPulse = highestSeverity === "critical" && firingCount > 0;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        group relative inline-flex items-center justify-center
        rounded-lg p-2 text-neutral-600 transition-colors
        hover:bg-neutral-100 hover:text-neutral-900
        focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2
        dark:text-neutral-400 dark:hover:bg-neutral-800 dark:hover:text-neutral-100
        ${className}
      `}
      aria-label={`${firingCount} firing alert${firingCount !== 1 ? "s" : ""}`}
    >
      {/* Bell Icon */}
      <Bell className="h-5 w-5" />

      {/* Count Badge */}
      {firingCount > 0 && (
        <span
          className={`
            absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center
            rounded-full px-1 text-xs font-bold text-white
            ${badgeColor}
            ${shouldPulse ? "animate-pulse" : ""}
          `}
        >
          {firingCount > 99 ? "99+" : firingCount}
        </span>
      )}

      {/* Connection Status Indicator */}
      <span
        className={`
          absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-white
          dark:border-neutral-900
          ${isConnected ? "bg-green-500" : "bg-neutral-400"}
        `}
        title={isConnected ? "Connected" : "Disconnected"}
      />
    </button>
  );
}

// ============================================================================
// Exports
// ============================================================================

export default FiringAlertsBadge;
