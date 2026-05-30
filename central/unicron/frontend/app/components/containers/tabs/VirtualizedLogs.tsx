/**
 * Virtualized Logs Component
 *
 * Virtualized log list using react-window List component.
 * Provides:
 * - Fixed height rows with truncated messages (expand via modal)
 * - Auto-scroll to bottom when new logs arrive
 * - Scroll detection for auto-scroll toggle
 * - Viewport change callback for gap filling
 */

import {
  useRef,
  useEffect,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import { List, useListRef } from "react-window";
import VirtualizedLogItem from "./VirtualizedLogItem";
import type { Log } from "~/utils/logCache";

// ============================================================================
// Types
// ============================================================================

interface VirtualizedLogsProps {
  logs: Log[];
  keywords: string[];
  onLogClick: (log: Log) => void;
  height: number;
  width: number;
  isAutoScroll: boolean;
  onScrollChange: (isAtBottom: boolean) => void;
  onViewportChange?: (startIndex: number, endIndex: number) => void;
  className?: string;
}

export interface VirtualizedLogsRef {
  scrollToBottom: () => void;
}

interface RowsRenderedRange {
  startIndex: number;
  stopIndex: number;
}

// ============================================================================
// Constants
// ============================================================================

/**
 * Fixed row height for single-line truncated log entries
 */
const ROW_HEIGHT = 32;

// ============================================================================
// Row Component
// ============================================================================

interface RowProps {
  logs: Log[];
  keywords: string[];
  onLogClick: (log: Log) => void;
}

function LogRow({
  index,
  style,
  logs,
  keywords,
  onLogClick,
}: {
  index: number;
  style: React.CSSProperties;
  logs: Log[];
  keywords: string[];
  onLogClick: (log: Log) => void;
}) {
  return (
    <VirtualizedLogItem
      index={index}
      style={style}
      data={{ logs, keywords, onLogClick }}
    />
  );
}

// ============================================================================
// Component
// ============================================================================

const VirtualizedLogs = forwardRef<VirtualizedLogsRef, VirtualizedLogsProps>(
  (
    {
      logs,
      keywords,
      onLogClick,
      height,
      width,
      isAutoScroll,
      onScrollChange,
      onViewportChange,
      className = "",
    },
    ref
  ) => {
    const listRef = useListRef(null);
    const previousLogsLength = useRef(logs.length);
    const isScrollingToBottom = useRef(false);

    // Fixed row height for single-line truncated entries
    const getRowHeight = useCallback((): number => ROW_HEIGHT, []);

    // Auto-scroll to bottom when new logs arrive and auto-scroll is enabled
    useEffect(() => {
      if (
        isAutoScroll &&
        logs.length > 0 &&
        logs.length > previousLogsLength.current
      ) {
        if (listRef.current) {
          isScrollingToBottom.current = true;
          listRef.current.scrollToRow({
            index: logs.length - 1,
            align: "end",
          });
          setTimeout(() => {
            isScrollingToBottom.current = false;
          }, 100);
        }
      }
      previousLogsLength.current = logs.length;
    }, [logs.length, isAutoScroll, listRef]);

    const handleRowsRendered = useCallback(
      (visibleRange: RowsRenderedRange) => {
        if (onViewportChange) {
          onViewportChange(visibleRange.startIndex, visibleRange.stopIndex);
        }
      },
      [onViewportChange]
    );

    const handleScroll = useCallback(
      (event: React.UIEvent<HTMLDivElement>) => {
        if (isScrollingToBottom.current) {
          return;
        }
        const target = event.currentTarget;
        const isAtBottom = target.scrollTop + target.clientHeight >= target.scrollHeight - 1;
        onScrollChange(isAtBottom);
      },
      [onScrollChange]
    );

    // Scroll to bottom method for external use
    const scrollToBottom = useCallback(() => {
      if (listRef.current && logs.length > 0) {
        isScrollingToBottom.current = true;
        listRef.current.scrollToRow({
          index: logs.length - 1,
          align: "end",
        });
        setTimeout(() => {
          isScrollingToBottom.current = false;
        }, 100);
      }
    }, [logs.length, listRef]);

    // Expose scroll method to parent component via ref
    useImperativeHandle(
      ref,
      () => ({
        scrollToBottom,
      }),
      [scrollToBottom]
    );

    if (logs.length === 0) {
      return (
        <div
          className={`flex h-full items-center justify-center ${className}`}
        >
          <p className="text-neutral">No logs to display</p>
        </div>
      );
    }

    return (
      <div
        className={className}
        style={{ height, width }}
      >
        <List<RowProps>
          listRef={listRef}
          rowCount={logs.length}
          rowHeight={getRowHeight}
          overscanCount={5}
          onScroll={handleScroll}
          onRowsRendered={handleRowsRendered}
          rowComponent={LogRow}
          rowProps={{
            logs,
            keywords,
            onLogClick,
          }}
          style={{ height: "100%", width: "100%" }}
        />
      </div>
    );
  }
);

VirtualizedLogs.displayName = "VirtualizedLogs";

export default VirtualizedLogs;
