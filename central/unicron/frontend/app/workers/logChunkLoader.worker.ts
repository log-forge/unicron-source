/// <reference lib="webworker" />

/**
 * Log Chunk Loader Worker
 *
 * Web Worker for background log processing and caching.
 * Handles:
 * - Log deduplication
 * - Timestamp-based sorting
 * - Batch processing for UI responsiveness
 * - Background chunk loading
 */

import type { Log, LogChunk } from "../utils/logCache";
import { logCacheManager } from "../utils/logCache";

// ============================================================================
// Message Types
// ============================================================================

export interface LoadChunkMessage {
  type: "LOAD_CHUNK";
  containerId: string;
  containerName: string;
  apiContainerName: string;
  hostId?: string | null;
  startTimestamp: string;
  endTimestamp: string;
  minutes: number;
}

export interface LoadChunksMessage {
  type: "LOAD_CHUNKS";
  containerId: string;
  containerName: string;
  apiContainerName: string;
  hostId?: string | null;
  totalHours: number;
  chunkSizeMinutes: number;
}

export interface ProcessLogsMessage {
  type: "PROCESS_LOGS";
  historicalLogs: Log[];
  liveLogs: Log[];
  batchSize?: number;
}

export type WorkerMessage =
  | LoadChunkMessage
  | LoadChunksMessage
  | ProcessLogsMessage;

// ============================================================================
// Response Types
// ============================================================================

export interface ChunkLoadedMessage {
  type: "CHUNK_LOADED";
  cacheKey: string;
  success: boolean;
  error?: string;
  chunkInfo: {
    startTimestamp: string;
    endTimestamp: string;
    logCount: number;
    sizeBytes: number;
  };
}

export interface BatchReadyMessage {
  type: "BATCH_READY";
  logs: Log[];
  batchIndex: number;
  totalBatches: number;
  isComplete: boolean;
}

export interface ProgressMessage {
  type: "PROGRESS";
  loaded: number;
  total: number;
  phase: "loading" | "caching" | "complete";
  currentChunk?: string;
}

export interface ErrorMessage {
  type: "ERROR";
  error: string;
  cacheKey?: string;
}

export type WorkerResponse =
  | ChunkLoadedMessage
  | BatchReadyMessage
  | ProgressMessage
  | ErrorMessage;

// ============================================================================
// Worker Configuration
// ============================================================================

const MAX_PARALLEL_CHUNKS = 3;
const INITIAL_DELAY_MS = 2000;
const RETRY_ATTEMPTS = 3;
const RETRY_DELAY_MS = 1000;

// ============================================================================
// Semaphore for Parallelism Control
// ============================================================================

class Semaphore {
  private permits: number;
  private queue: Array<() => void> = [];

  constructor(permits: number) {
    this.permits = permits;
  }

  async acquire(): Promise<void> {
    return new Promise((resolve) => {
      if (this.permits > 0) {
        this.permits--;
        resolve();
      } else {
        this.queue.push(resolve);
      }
    });
  }

  release(): void {
    if (this.queue.length > 0) {
      const resolve = this.queue.shift()!;
      resolve();
    } else {
      this.permits++;
    }
  }
}

// ============================================================================
// Chunk Loader
// ============================================================================

class ChunkLoader {
  private baseURL: string;

  constructor() {
    // Determine base URL for API calls
    this.baseURL =
      self.location.protocol === "https:"
        ? `https://${self.location.host}/api`
        : `http://${self.location.host}/api`;
  }

  /**
   * Post message to main thread
   */
  private postMessage(message: WorkerResponse): void {
    self.postMessage(message);
  }

  /**
   * Load a single chunk from the API
   */
  async loadSingleChunk(message: LoadChunkMessage): Promise<void> {
    const {
      containerId,
      containerName,
      apiContainerName,
      hostId,
      startTimestamp,
      endTimestamp,
      minutes,
    } = message;

    const cacheKey = logCacheManager.generateCacheKey(
      containerId,
      containerName,
      startTimestamp,
      endTimestamp
    );

    // Check if already cached
    const existingChunk = await logCacheManager.getChunk(cacheKey);
    if (existingChunk) {
      this.postMessage({
        type: "CHUNK_LOADED",
        cacheKey,
        success: true,
        chunkInfo: {
          startTimestamp: existingChunk.startTimestamp,
          endTimestamp: existingChunk.endTimestamp,
          logCount: existingChunk.logs.length,
          sizeBytes: existingChunk.sizeBytes,
        },
      });
      return;
    }

    // Load from API
    try {
      const logs = await this.fetchHistoricalLogs(
        apiContainerName,
        minutes,
        hostId
      );

      // Cache the chunk
      await logCacheManager.cacheChunk({
        cacheKey,
        containerId,
        containerName,
        startTimestamp,
        endTimestamp,
        logs,
      });

      this.postMessage({
        type: "CHUNK_LOADED",
        cacheKey,
        success: true,
        chunkInfo: {
          startTimestamp,
          endTimestamp,
          logCount: logs.length,
          sizeBytes: JSON.stringify(logs).length * 2,
        },
      });
    } catch (error) {
      this.postMessage({
        type: "CHUNK_LOADED",
        cacheKey,
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
        chunkInfo: {
          startTimestamp,
          endTimestamp,
          logCount: 0,
          sizeBytes: 0,
        },
      });
    }
  }

  /**
   * Process logs with deduplication and sorting
   */
  async processLogs(message: ProcessLogsMessage): Promise<void> {
    const { historicalLogs, liveLogs, batchSize = 500 } = message;

    // Step 1: Combine all logs
    const allLogs = [...historicalLogs, ...liveLogs];

    // Step 2: Deduplicate by timestamp + message
    const uniqueLogs = allLogs.reduce((acc, log) => {
      const key = `${log.timeStamp}-${log.message}`;
      if (!acc.has(key)) {
        acc.set(key, log);
      }
      return acc;
    }, new Map<string, Log>());

    // Step 3: Sort by timestamp (oldest first for proper log display)
    const sortedLogs = Array.from(uniqueLogs.values()).sort(
      (a, b) =>
        new Date(a.timeStamp).getTime() - new Date(b.timeStamp).getTime()
    );

    // Step 4: Split into batches and send progressively
    const totalBatches = Math.ceil(sortedLogs.length / batchSize);

    for (let i = 0; i < totalBatches; i++) {
      const startIndex = i * batchSize;
      const endIndex = Math.min(startIndex + batchSize, sortedLogs.length);
      const batch = sortedLogs.slice(startIndex, endIndex);

      const batchMessage: BatchReadyMessage = {
        type: "BATCH_READY",
        logs: batch,
        batchIndex: i,
        totalBatches,
        isComplete: i === totalBatches - 1,
      };

      this.postMessage(batchMessage);

      // Small delay between batches to prevent overwhelming main thread
      if (i < totalBatches - 1) {
        await new Promise((resolve) => setTimeout(resolve, 16)); // ~1 frame delay
      }
    }

    // If no logs, still send completion message
    if (totalBatches === 0) {
      this.postMessage({
        type: "BATCH_READY",
        logs: [],
        batchIndex: 0,
        totalBatches: 1,
        isComplete: true,
      });
    }
  }

  /**
   * Load multiple chunks in batch
   */
  async loadChunksBatch(message: LoadChunksMessage): Promise<void> {
    const {
      containerId,
      containerName,
      apiContainerName,
      hostId,
      totalHours,
      chunkSizeMinutes,
    } = message;

    // Calculate chunk time ranges (reverse chronological - most recent first)
    const chunks = this.generateChunkTimeRanges(totalHours, chunkSizeMinutes);
    const totalChunks = chunks.length;

    this.postMessage({
      type: "PROGRESS",
      loaded: 0,
      total: totalChunks,
      phase: "loading",
    });

    // Phase 1: Load first 2 hours (high priority chunks) with limited parallelism
    const phase1Chunks = chunks.slice(
      0,
      Math.ceil((2 * 60) / chunkSizeMinutes)
    );
    await this.loadChunksWithThrottling(
      phase1Chunks,
      containerId,
      containerName,
      apiContainerName,
      hostId,
      1,
      totalChunks
    );

    // Phase 2: Load remaining chunks with higher parallelism
    const phase2Chunks = chunks.slice(phase1Chunks.length);
    if (phase2Chunks.length > 0) {
      await this.loadChunksWithThrottling(
        phase2Chunks,
        containerId,
        containerName,
        apiContainerName,
        hostId,
        MAX_PARALLEL_CHUNKS,
        totalChunks,
        phase1Chunks.length
      );
    }

    this.postMessage({
      type: "PROGRESS",
      loaded: totalChunks,
      total: totalChunks,
      phase: "complete",
    });
  }

  /**
   * Load chunks with throttling and parallelism control
   */
  private async loadChunksWithThrottling(
    chunks: Array<{ start: Date; end: Date }>,
    containerId: string,
    containerName: string,
    apiContainerName: string,
    hostId: string | null | undefined,
    parallelism: number,
    totalChunks: number,
    loadedSoFar = 0
  ): Promise<void> {
    const semaphore = new Semaphore(parallelism);
    let loadedCount = loadedSoFar;

    const loadPromises = chunks.map(async (chunk, index) => {
      await semaphore.acquire();

      try {
        const startTimestamp = chunk.start.toISOString();
        const endTimestamp = chunk.end.toISOString();
        const minutes = Math.ceil(
          (chunk.end.getTime() - chunk.start.getTime()) / (1000 * 60)
        );

        await this.loadSingleChunk({
          type: "LOAD_CHUNK",
          containerId,
          containerName,
          apiContainerName,
          hostId,
          startTimestamp,
          endTimestamp,
          minutes,
        });

        loadedCount++;
        this.postMessage({
          type: "PROGRESS",
          loaded: loadedCount,
          total: totalChunks,
          phase: "loading",
          currentChunk: `${startTimestamp} - ${endTimestamp}`,
        });

        // Small delay between chunks to avoid overwhelming the backend
        if (index < chunks.length - 1) {
          await new Promise((resolve) =>
            setTimeout(resolve, parallelism === 1 ? INITIAL_DELAY_MS : 500)
          );
        }
      } finally {
        semaphore.release();
      }
    });

    await Promise.all(loadPromises);
  }

  /**
   * Generate chunk time ranges for a given duration
   */
  private generateChunkTimeRanges(
    totalHours: number,
    chunkSizeMinutes: number
  ): Array<{ start: Date; end: Date }> {
    const chunks: Array<{ start: Date; end: Date }> = [];
    const now = new Date();
    const totalMinutes = totalHours * 60;

    // Generate chunks from most recent to oldest
    for (let i = 0; i < totalMinutes; i += chunkSizeMinutes) {
      const endTime = new Date(now.getTime() - i * 60 * 1000);
      const startTime = new Date(
        now.getTime() - (i + chunkSizeMinutes) * 60 * 1000
      );

      chunks.push({ start: startTime, end: endTime });
    }

    return chunks;
  }

  /**
   * Fetch historical logs from API via WebSocket
   */
  private async fetchHistoricalLogs(
    containerName: string,
    minutes: number,
    hostId?: string | null
  ): Promise<Log[]> {
    let lastError: Error = new Error("Unknown error");

    for (let attempt = 1; attempt <= RETRY_ATTEMPTS; attempt++) {
      try {
        const logs = await this.fetchLogsViaWebSocket(containerName, minutes, hostId);
        return logs;
      } catch (error) {
        lastError =
          error instanceof Error ? error : new Error("Unknown error");

        if (attempt < RETRY_ATTEMPTS) {
          await new Promise((resolve) =>
            setTimeout(resolve, RETRY_DELAY_MS * attempt)
          );
        }
      }
    }

    throw lastError;
  }

  /**
   * Fetch logs via WebSocket connection
   */
  private async fetchLogsViaWebSocket(
    containerName: string,
    minutes: number,
    hostId?: string | null
  ): Promise<Log[]> {
    return new Promise((resolve, reject) => {
      const logs: Log[] = [];
      const protocol = self.location.protocol === "https:" ? "wss:" : "ws:";
      const host = self.location.host;
      // Use /api/ prefix to ensure Traefik routes to backend, not frontend
      const path = hostId
        ? `/api/ws/logs/${encodeURIComponent(hostId)}/${encodeURIComponent(containerName)}`
        : `/api/ws/logs/${encodeURIComponent(containerName)}`;
      const wsUrl = `${protocol}//${host}${path}`;

      const ws = new WebSocket(wsUrl);
      let resolved = false;

      const timeout = setTimeout(() => {
        if (!resolved) {
          resolved = true;
          ws.close();
          resolve(logs);
        }
      }, 10000);

      ws.onopen = () => {
        const sinceDate = new Date(Date.now() - minutes * 60 * 1000).toISOString();
        ws.send(JSON.stringify({
          type: "tail",
          follow: false,
          tail: "all",
          since: sinceDate,
        }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          // Handle new format: {timestamp, message}
          if (typeof msg.timestamp === "string" && typeof msg.message === "string") {
            if (msg.message) {
              logs.push({
                timeStamp: msg.timestamp || new Date().toISOString(),
                message: msg.message,
              });
            }
          }
          // Handle error messages
          else if (msg.type === "error" && msg.error) {
            logs.push({
              timeStamp: new Date().toISOString(),
              message: `[ERROR] ${msg.error}`,
            });
          }
        } catch {
          // Fallback: treat as raw string
          if (typeof event.data === "string" && event.data.length > 0) {
            logs.push({
              timeStamp: new Date().toISOString(),
              message: event.data,
            });
          }
        }
      };

      ws.onclose = () => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timeout);
          resolve(logs);
        }
      };

      ws.onerror = () => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timeout);
          reject(new Error("WebSocket connection failed"));
        }
      };
    });
  }
}

// ============================================================================
// Worker Initialization
// ============================================================================

const chunkLoader = new ChunkLoader();

// Handle messages from main thread
self.addEventListener("message", async (event: MessageEvent<WorkerMessage>) => {
  const message = event.data;

  try {
    switch (message.type) {
      case "LOAD_CHUNK":
        await chunkLoader.loadSingleChunk(message);
        break;
      case "LOAD_CHUNKS":
        await chunkLoader.loadChunksBatch(message);
        break;
      case "PROCESS_LOGS":
        await chunkLoader.processLogs(message);
        break;
      default:
        throw new Error(`Unknown message type: ${(message as { type: string }).type}`);
    }
  } catch (error) {
    self.postMessage({
      type: "ERROR",
      error: error instanceof Error ? error.message : "Unknown error occurred",
    } satisfies ErrorMessage);
  }
});
