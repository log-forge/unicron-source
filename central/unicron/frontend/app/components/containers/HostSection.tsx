/**
 * HostSection Component
 *
 * Collapsible section header for a host, showing host name, status indicator,
 * alert count, and container count. Click to expand/collapse.
 */

import React from "react";
import { ChevronDown, ChevronRight, Server } from "lucide-react";
import { HostStatusDot } from "./HostStatusDot";

export interface HostSectionProps {
  hostId: string;
  containerCount: number;
  runningCount: number;
  alertCount: number;
  isOnline: boolean;
  /** Last seen timestamp for tooltip display */
  lastSeen?: string | null;
  isExpanded: boolean;
  onToggle: () => void;
  onClick?: () => void;
}

export const HostSection: React.FC<HostSectionProps> = ({
  hostId,
  containerCount,
  runningCount,
  alertCount,
  isOnline,
  lastSeen,
  isExpanded,
  onToggle,
  onClick,
}) => {
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggle();
  };

  const handleHostClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onClick?.();
  };

  return (
    <div
      className="group flex cursor-pointer items-center justify-between rounded-lg bg-neutral/10 px-md py-sm transition-colors hover:bg-neutral/15 dark:bg-neutral-800/50"
      onClick={handleClick}
    >
      <div className="flex items-center gap-sm">
        {/* Expand/Collapse Chevron */}
        <div className="rounded-md p-3xs transition-all hover:bg-neutral/20">
          {isExpanded ? (
            <ChevronDown className="h-5 w-5 text-neutral" />
          ) : (
            <ChevronRight className="h-5 w-5 text-neutral" />
          )}
        </div>

        {/* Host Icon and Name */}
        <div className="rounded-xl bg-primary/10 p-2xs">
          <Server className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-sm">
            <span
              className="truncate text-sm font-bold text-text hover:underline"
              onClick={handleHostClick}
            >
              {hostId}
            </span>
            {/* Status Dot */}
            <HostStatusDot
              isOnline={isOnline}
              lastSeen={lastSeen ?? undefined}
              size="sm"
            />
          </div>
          <div className="text-xs text-neutral">
            {alertCount > 0 && (
              <span className="mr-xs font-medium text-warning">
                {alertCount} alert{alertCount !== 1 ? "s" : ""}
              </span>
            )}
            <span>
              {containerCount} container{containerCount !== 1 ? "s" : ""}
            </span>
            {runningCount > 0 && (
              <span className="ml-xs text-success">
                ({runningCount} running)
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default HostSection;
