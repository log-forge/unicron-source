/**
 * HostStatusDot Component
 *
 * Status indicator dot for host online/offline state.
 * Green = online (seen within 2 minutes)
 * Gray = offline (not seen for > 2 minutes)
 *
 * Tooltip shows "Online since..." or "Last seen..."
 */

import React from "react";

export interface HostStatusDotProps {
  /** Whether host is online (container seen within stale threshold) */
  isOnline: boolean;
  /** Last seen timestamp for tooltip */
  lastSeen?: string;
  /** Size variant */
  size?: "sm" | "md";
}

export const HostStatusDot: React.FC<HostStatusDotProps> = ({
  isOnline,
  lastSeen,
  size = "sm",
}) => {
  const sizeClasses = size === "sm" ? "h-2 w-2" : "h-3 w-3";
  const colorClasses = isOnline ? "bg-success" : "bg-neutral";

  const tooltipText = React.useMemo(() => {
    if (!lastSeen) {
      return isOnline ? "Online" : "Offline";
    }

    const lastSeenDate = new Date(lastSeen);
    const now = new Date();
    const diffMs = now.getTime() - lastSeenDate.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);

    if (isOnline) {
      return `Online - last activity ${formatDuration(diffMinutes)} ago`;
    } else {
      return `Offline - last seen ${formatDuration(diffMinutes)} ago`;
    }
  }, [isOnline, lastSeen]);

  return (
    <div className="group relative inline-flex">
      <span
        className={`${sizeClasses} ${colorClasses} rounded-full`}
        aria-label={tooltipText}
      />
      {/* Tooltip */}
      <div className="invisible absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-800 px-2 py-1 text-xs text-white opacity-0 shadow-lg transition-all group-hover:visible group-hover:opacity-100">
        {tooltipText}
        <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-slate-800" />
      </div>
    </div>
  );
};

function formatDuration(minutes: number): string {
  if (minutes < 1) return "less than a minute";
  if (minutes === 1) return "1 minute";
  if (minutes < 60) return `${minutes} minutes`;

  const hours = Math.floor(minutes / 60);
  if (hours === 1) return "1 hour";
  if (hours < 24) return `${hours} hours`;

  const days = Math.floor(hours / 24);
  if (days === 1) return "1 day";
  return `${days} days`;
}

export default HostStatusDot;
