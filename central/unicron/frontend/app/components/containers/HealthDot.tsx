/**
 * HealthDot Component
 *
 * Displays container health status as a colored dot with tooltip.
 * Shows health details on hover including status and failing streak count.
 */

import React, { useState, useRef } from "react";

// ============================================================================
// Types
// ============================================================================

export interface HealthDotProps {
  /** Health status of the container */
  status: "healthy" | "unhealthy" | "starting" | "disabled" | null;
  /** Number of consecutive health check failures */
  failingStreak?: number;
  /** Additional CSS classes */
  className?: string;
}

// ============================================================================
// Helper Functions
// ============================================================================

function getStatusColor(
  status: HealthDotProps["status"]
): string {
  switch (status) {
    case "healthy":
      return "bg-success";
    case "unhealthy":
      return "bg-error";
    case "starting":
      return "bg-warning";
    case "disabled":
    case null:
    default:
      return "bg-neutral/40";
  }
}

function getStatusLabel(status: HealthDotProps["status"]): string {
  switch (status) {
    case "healthy":
      return "Healthy";
    case "unhealthy":
      return "Unhealthy";
    case "starting":
      return "Starting";
    case "disabled":
      return "Disabled";
    case null:
    default:
      return "Unknown";
  }
}

// ============================================================================
// Component
// ============================================================================

export const HealthDot: React.FC<HealthDotProps> = React.memo(
  ({ status, failingStreak, className = "" }) => {
    const [showTooltip, setShowTooltip] = useState(false);
    const dotRef = useRef<HTMLDivElement>(null);

    const colorClass = getStatusColor(status);
    const statusLabel = getStatusLabel(status);

    // Build tooltip content
    let tooltipContent = statusLabel;
    if (failingStreak && failingStreak > 0) {
      tooltipContent += ` (${failingStreak} consecutive failure${failingStreak !== 1 ? "s" : ""})`;
    }

    return (
      <div
        ref={dotRef}
        className={`relative inline-flex items-center justify-center ${className}`}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
      >
        {/* Health Dot */}
        <div
          className={`
            h-3 w-3 rounded-full
            ${colorClass}
            ${status === "unhealthy" ? "animate-pulse" : ""}
          `}
          title={tooltipContent}
        />

        {/* Tooltip Popover */}
        {showTooltip && (
          <div
            className="
              absolute bottom-full left-1/2 z-50 mb-2 -translate-x-1/2
              whitespace-nowrap rounded-md bg-neutral-900 px-2 py-1
              text-xs font-medium text-white shadow-lg
              dark:bg-neutral-100 dark:text-neutral-900
            "
          >
            {tooltipContent}
            {/* Arrow */}
            <div
              className="
                absolute left-1/2 top-full -translate-x-1/2
                border-4 border-transparent border-t-neutral-900
                dark:border-t-neutral-100
              "
            />
          </div>
        )}
      </div>
    );
  }
);

HealthDot.displayName = "HealthDot";

export default HealthDot;
