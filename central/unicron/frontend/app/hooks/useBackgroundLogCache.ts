/**
 * Background Log Cache Hook
 *
 * Manages background loading and caching of container logs using a Web Worker.
 * Provides:
 * - Background loading of 6 hours of logs in 15-minute chunks
 * - Progress reporting during cache loading
 * - Cached log retrieval for time ranges
 * - Worker-based log processing for deduplication
 */

import { useEffect, useRef, useState, useCallback } from "react";
import type {
  WorkerMessage,
  WorkerResponse,
  BatchReadyMessage,
  ProcessLogsMessage,
} from "~/workers/logChunkLoader.worker";
import { logCacheManager, type CacheHitResult, type Log } from "~/utils/logCache";

// ============================================================================
// Types
// ============================================================================

export interface CacheProgress {
  loaded: number;
  total: number;
  phase: "idle" | "loading" | "caching" | "complete";
  currentChunk?: string;
  hoursLoaded: number;
  totalHours: number;
  sizeMB: number;
}

export interface BackgroundCacheOptions {
  containerName: string;
  apiContainerName: string;
  containerId: string;
  hostId?: string | null;
  enabled: boolean;
  startDelay?: number;
  totalHours?: number;
  chunkSizeMinutes?: number;
}

// ============================================================================
// Hook
// ============================================================================

export function useBackgroundLogCache(options: BackgroundCacheOptions) {
  const {
    containerName,
    apiContainerName,
    containerId,
    hostId,
    enabled,
    startDelay = 5000,
    totalHours = 6,
    chunkSizeMinutes = 15,
  } = options;

  const workerRef = useRef<Worker | null>(null);
  const startTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [progress, setProgress] = useState<CacheProgress>({
    loaded: 0,
    total: 0,
    phase: "idle",
    hoursLoaded: 0,
    totalHours,
    sizeMB: 0,
  });

  // Initialize worker
  useEffect(() => {
    if (!enabled) return;

    try {
      workerRef.current = new Worker(
        new URL("../workers/logChunkLoader.worker.ts", import.meta.url),
        { type: "module" }
      );

      workerRef.current.onmessage = (event: MessageEvent<WorkerResponse>) => {
        const message = event.data;

        switch (message.type) {
          case "PROGRESS": {
            const hoursLoaded = (message.loaded / message.total) * totalHours;
            const cacheStats = logCacheManager.getCacheStats();

            setProgress((prev) => ({
              ...prev,
              loaded: message.loaded,
              total: message.total,
              phase: message.phase,
              currentChunk: message.currentChunk,
              hoursLoaded,
              sizeMB: cacheStats.sizeMB,
            }));
            break;
          }

          case "CHUNK_LOADED":
            if (message.success) {
              console.log(
                `Cached chunk: ${message.cacheKey}, logs: ${message.chunkInfo.logCount}`
              );
            } else {
              console.error(
                `Failed to cache chunk: ${message.cacheKey}, error: ${message.error}`
              );
            }
            break;

          case "ERROR":
            console.error("Background cache worker error:", message.error);
            setProgress((prev) => ({ ...prev, phase: "idle" }));
            break;
        }
      };

      workerRef.current.onerror = (error) => {
        console.error("Worker error:", error);
        setProgress((prev) => ({ ...prev, phase: "idle" }));
      };
    } catch (error) {
      console.error("Failed to create worker:", error);
    }

    return () => {
      if (workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
      if (startTimeoutRef.current) {
        clearTimeout(startTimeoutRef.current);
        startTimeoutRef.current = null;
      }
    };
  }, [enabled, totalHours]);

  // Start background loading after delay
  useEffect(() => {
    if (!enabled || !workerRef.current || !containerName || !containerId)
      return;

    // Clear any existing timeout
    if (startTimeoutRef.current) {
      clearTimeout(startTimeoutRef.current);
    }

    startTimeoutRef.current = setTimeout(() => {
      if (workerRef.current) {
        const message: WorkerMessage = {
          type: "LOAD_CHUNKS",
          containerId,
          containerName,
          apiContainerName,
          hostId,
          totalHours,
          chunkSizeMinutes,
        };

        workerRef.current.postMessage(message);
        setProgress((prev) => ({ ...prev, phase: "loading" }));
      }
    }, startDelay);

    return () => {
      if (startTimeoutRef.current) {
        clearTimeout(startTimeoutRef.current);
        startTimeoutRef.current = null;
      }
    };
  }, [
    enabled,
    containerName,
    containerId,
    apiContainerName,
    hostId,
    startDelay,
    totalHours,
    chunkSizeMinutes,
  ]);

  /**
   * Get cached logs for a time range with boundary alignment
   */
  const getCachedLogs = useCallback(
    async (startTime: Date, endTime: Date): Promise<CacheHitResult> => {
      try {
        return await logCacheManager.getCachedLogsWithBoundaryAlignment(
          containerName,
          startTime,
          endTime
        );
      } catch (error) {
        console.error("Error getting cached logs:", error);
        return {
          hasPartialCoverage: false,
          coveragePercentage: 0,
          cachedLogs: [],
          missingTimeRanges: [{ start: startTime, end: endTime }],
        };
      }
    },
    [containerName]
  );

  /**
   * Check if a time range has sufficient cached coverage (>= 80%)
   */
  const isTimeRangeCached = useCallback(
    async (startTime: Date, endTime: Date): Promise<boolean> => {
      try {
        const cacheResult =
          await logCacheManager.getCachedLogsWithBoundaryAlignment(
            containerName,
            startTime,
            endTime
          );

        // Consider cached if we have >= 80% coverage
        return cacheResult.hasPartialCoverage;
      } catch (error) {
        console.error("Error checking cache coverage:", error);
        return false;
      }
    },
    [containerName]
  );

  /**
   * Get current cache statistics
   */
  const getCacheStats = useCallback(() => {
    return logCacheManager.getCacheStats();
  }, []);

  /**
   * Process logs through worker with batching
   */
  const processLogsInWorker = useCallback(
    (
      historicalLogs: Log[],
      liveLogs: Log[],
      onBatchReady: (batch: BatchReadyMessage) => void,
      batchSize = 500
    ) => {
      if (!workerRef.current) {
        console.warn("Worker not available for log processing");
        return;
      }

      // Set up one-time listener for batches from this processing request
      const handleBatch = (event: MessageEvent<WorkerResponse>) => {
        if (event.data.type === "BATCH_READY") {
          onBatchReady(event.data as BatchReadyMessage);
        }
      };

      workerRef.current.addEventListener("message", handleBatch);

      // Send processing request
      const message: ProcessLogsMessage = {
        type: "PROCESS_LOGS",
        historicalLogs,
        liveLogs,
        batchSize,
      };

      workerRef.current.postMessage(message);

      // Return cleanup function
      return () => {
        if (workerRef.current) {
          workerRef.current.removeEventListener("message", handleBatch);
        }
      };
    },
    []
  );

  return {
    progress,
    getCachedLogs,
    isTimeRangeCached,
    getCacheStats,
    processLogsInWorker,
  };
}
