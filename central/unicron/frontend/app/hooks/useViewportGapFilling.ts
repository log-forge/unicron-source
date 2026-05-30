/**
 * Viewport Gap Filling Hook
 *
 * Detects gaps in log coverage when scrolling and fetches missing data.
 * Provides seamless scrolling experience by loading missing log ranges
 * as they become visible in the viewport.
 */

import { useEffect, useRef, useCallback } from "react";
import type { CacheHitResult, Log } from "~/utils/logCache";

// ============================================================================
// Types
// ============================================================================

export interface UseViewportGapFillingOptions {
  containerName: string;
  cacheResult: CacheHitResult | null;
  logs: Log[];
  onGapFilled: (newLogs: Log[]) => void;
  enabled: boolean;
  hostId: string | null;
  getContainerHistoricalLogs: (
    container: string,
    minutes: number
  ) => Promise<Log[]>;
}

interface ViewportInfo {
  startIndex: number;
  endIndex: number;
  startTime: Date;
  endTime: Date;
}

// ============================================================================
// Hook
// ============================================================================

export function useViewportGapFilling({
  containerName,
  cacheResult,
  logs,
  onGapFilled,
  enabled,
  hostId,
  getContainerHistoricalLogs,
}: UseViewportGapFillingOptions) {
  const activeRequests = useRef<Set<string>>(new Set());
  const lastViewportInfo = useRef<ViewportInfo | null>(null);

  /**
   * Calculate which time ranges are visible in the current viewport
   */
  const calculateViewportTimeRange = useCallback(
    (
      startIndex: number,
      endIndex: number
    ): { start: Date; end: Date } | null => {
      if (!logs.length || startIndex >= logs.length || endIndex < 0)
        return null;

      const safeStartIndex = Math.max(0, startIndex);
      const safeEndIndex = Math.min(logs.length - 1, endIndex);

      const startLog = logs[safeStartIndex];
      const endLog = logs[safeEndIndex];

      if (!startLog || !endLog) return null;

      return {
        start: new Date(startLog.timeStamp),
        end: new Date(endLog.timeStamp),
      };
    },
    [logs]
  );

  /**
   * Find missing gaps that intersect with viewport
   */
  const findViewportGaps = useCallback(
    (viewportStart: Date, viewportEnd: Date) => {
      if (!cacheResult?.missingTimeRanges.length) return [];

      return cacheResult.missingTimeRanges.filter((gap) => {
        // Check if gap intersects with viewport
        return gap.start < viewportEnd && gap.end > viewportStart;
      });
    },
    [cacheResult]
  );

  /**
   * Load a specific gap
   */
  const loadGap = useCallback(
    async (gap: { start: Date; end: Date }) => {
      const gapKey = `${gap.start.toISOString()}-${gap.end.toISOString()}`;

      // Prevent duplicate requests
      if (activeRequests.current.has(gapKey)) return;

      activeRequests.current.add(gapKey);

      try {
        const minutes = Math.ceil(
          (gap.end.getTime() - gap.start.getTime()) / (1000 * 60)
        );
        console.log(
          `Loading viewport gap: ${minutes} minutes from ${gap.start.toISOString()}`
        );

        const gapLogs = await getContainerHistoricalLogs(containerName, minutes);

        // Filter logs to only include those within the gap time range
        const filteredGapLogs = gapLogs.filter((log) => {
          const logTime = new Date(log.timeStamp);
          return logTime >= gap.start && logTime <= gap.end;
        });

        if (filteredGapLogs.length > 0) {
          console.log(`Loaded ${filteredGapLogs.length} logs for viewport gap`);
          onGapFilled(filteredGapLogs);
        }
      } catch (error) {
        console.error(`Failed to load viewport gap:`, error);
      } finally {
        activeRequests.current.delete(gapKey);
      }
    },
    [containerName, getContainerHistoricalLogs, onGapFilled]
  );

  /**
   * Load gaps that are visible in viewport
   */
  const loadViewportGaps = useCallback(
    async (startIndex: number, endIndex: number) => {
      if (!enabled || !cacheResult?.missingTimeRanges.length) return;

      const viewportTimeRange = calculateViewportTimeRange(startIndex, endIndex);
      if (!viewportTimeRange) return;

      const viewportGaps = findViewportGaps(
        viewportTimeRange.start,
        viewportTimeRange.end
      );

      if (viewportGaps.length === 0) return;

      console.log(
        `Found ${viewportGaps.length} gaps in viewport, loading...`
      );

      // Load gaps in parallel, but limit to 2 concurrent requests
      const maxConcurrent = 2;
      for (let i = 0; i < viewportGaps.length; i += maxConcurrent) {
        const batch = viewportGaps.slice(i, i + maxConcurrent);
        await Promise.all(batch.map((gap) => loadGap(gap)));
      }
    },
    [enabled, cacheResult, calculateViewportTimeRange, findViewportGaps, loadGap]
  );

  /**
   * Expose method for manual viewport gap filling
   */
  const fillViewportGaps = useCallback(
    (startIndex: number, endIndex: number) => {
      // Debounce viewport gap filling to avoid excessive requests
      const currentViewport: ViewportInfo = {
        startIndex,
        endIndex,
        startTime: logs[startIndex]
          ? new Date(logs[startIndex].timeStamp)
          : new Date(),
        endTime: logs[endIndex]
          ? new Date(logs[endIndex].timeStamp)
          : new Date(),
      };

      // Skip if viewport hasn't changed significantly
      if (lastViewportInfo.current) {
        const timeDiff = Math.abs(
          currentViewport.startTime.getTime() -
            lastViewportInfo.current.startTime.getTime()
        );
        if (timeDiff < 30 * 1000) {
          // Less than 30 seconds change
          return;
        }
      }

      lastViewportInfo.current = currentViewport;
      loadViewportGaps(startIndex, endIndex);
    },
    [logs, loadViewportGaps]
  );

  // Auto-fill gaps when cache result changes
  useEffect(() => {
    if (enabled && cacheResult?.missingTimeRanges.length && logs.length > 0) {
      // Auto-load gaps for the first viewport (first 50 logs)
      const initialViewportEnd = Math.min(50, logs.length - 1);
      loadViewportGaps(0, initialViewportEnd);
    }
  }, [enabled, cacheResult, logs.length, loadViewportGaps]);

  // Cleanup active requests on unmount
  useEffect(() => {
    return () => {
      activeRequests.current.clear();
    };
  }, []);

  return {
    fillViewportGaps,
    hasActiveRequests: activeRequests.current.size > 0,
    activeRequestCount: activeRequests.current.size,
  };
}
