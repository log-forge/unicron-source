/**
 * Virtualized Log Item
 *
 * Individual log row renderer for react-window virtualized list.
 * Handles:
 * - Timestamp display with highlighted color
 * - Message display with word-break
 * - Keyword highlighting
 * - Click to expand/view full log
 */

import { memo } from "react";
import clsx from "clsx";
import { Maximize2 } from "lucide-react";
import type { Log } from "~/utils/logCache";

// ============================================================================
// Types
// ============================================================================

interface VirtualizedLogItemProps {
  index: number;
  style: React.CSSProperties;
  data: {
    logs: Log[];
    keywords: string[];
    onLogClick: (log: Log) => void;
  };
}

// ============================================================================
// Component
// ============================================================================

const VirtualizedLogItem = memo(
  ({ index, style, data }: VirtualizedLogItemProps) => {
    const { logs, keywords, onLogClick } = data;
    const log = logs[index];

    if (!log) {
      return <div style={style} />;
    }

    // Create stable key using timestamp + message hash
    const stableKey = log.container_key
      ? `${log.container_key}:${log.timeStamp}:${log.message.length}`
      : `${log.timeStamp}-${log.message.slice(0, 50).replace(/\s+/g, "")}-${log.message.length}`;

    // Check if any keywords match the message
    const hasKeywordMatch =
      keywords.length > 0 &&
      keywords.some((keyword) =>
        log.message.toLowerCase().includes(keyword.toLowerCase())
      );

    // Format timestamp for display
    const formatTimestamp = (ts: string) => {
      try {
        const date = new Date(ts);
        return date.toLocaleString("en-US", {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        });
      } catch {
        return ts;
      }
    };

    return (
      <div
        style={style}
        className={clsx(
          "group/log relative flex w-full flex-row items-center rounded px-xs py-3xs text-sm text-text transition-colors",
          "hover:bg-neutral/10"
        )}
        data-log-key={stableKey}
      >
        {/* Timestamp - fixed width */}
        <span className="shrink-0 whitespace-nowrap font-mono text-primary">
          {formatTimestamp(log.timeStamp)}
        </span>
        <span className="shrink-0 text-neutral">:&nbsp;</span>

        {/* Message - truncated to single line */}
        <span
          className={clsx(
            "flex-1 truncate pr-lg",
            hasKeywordMatch ? "font-medium text-error" : "text-text"
          )}
          title={log.message.length > 100 ? "Click expand to view full message" : log.message}
        >
          {log.message}
        </span>

        {/* Expand button */}
        <button
          onClick={() => onLogClick(log)}
          className="absolute right-xs top-1/2 hidden -translate-y-1/2 rounded bg-primary/10 p-3xs text-primary transition-colors hover:bg-primary/20 group-hover/log:flex"
          title="View full log"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }
);

VirtualizedLogItem.displayName = "VirtualizedLogItem";

export default VirtualizedLogItem;
