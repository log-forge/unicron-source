/**
 * Log Cache Manager
 *
 * In-memory cache for log data with time-based chunk management.
 * Provides fast access to historical logs with configurable retention.
 *
 * For MVP, uses in-memory Map cache. IndexedDB can be added later for persistence.
 */

// ============================================================================
// Types
// ============================================================================

export interface Log {
  timeStamp: string;
  message: string;

  severity?: string | null;
  stream?: string | null;
  container_key?: string | null;
  container_name?: string | null;
  docker_container_id?: string | null;
  herald_id?: string | null;
  herald_name?: string | null;
  service_name?: string | null;
  service_namespace?: string | null;
  msg_json?: Record<string, unknown> | null;
}

export interface LogChunk {
  cacheKey: string;
  containerId: string;
  containerName: string;
  startTimestamp: string;
  endTimestamp: string;
  logs: Log[];
  cachedAt: number;
  sizeBytes: number;
  lastAccessedAt: number;
}

export interface CacheHitResult {
  hasPartialCoverage: boolean;
  coveragePercentage: number;
  cachedLogs: Log[];
  missingTimeRanges: Array<{ start: Date; end: Date }>;
}

export interface CacheTimeRange {
  start: Date;
  end: Date;
  rounded: {
    start: Date;
    end: Date;
  };
}

export interface CacheStats {
  sizeMB: number;
  entryCount: number;
  containers: Set<string>;
}

// ============================================================================
// Constants
// ============================================================================

const MAX_CACHE_SIZE_MB = 50;
const MAX_CACHE_SIZE_BYTES = MAX_CACHE_SIZE_MB * 1024 * 1024;
const CACHE_EXPIRY_HOURS = 24;
const CHUNK_SIZE_MINUTES = 15;
const CHUNK_SIZE_MS = CHUNK_SIZE_MINUTES * 60 * 1000;

// ============================================================================
// Utilities
// ============================================================================

/**
 * Round timestamp down to nearest chunk boundary
 */
export function roundToBoundary(timestamp: Date): Date {
  const ms = timestamp.getTime();
  return new Date(Math.floor(ms / CHUNK_SIZE_MS) * CHUNK_SIZE_MS);
}

/**
 * Round timestamp up to nearest chunk boundary
 */
export function roundUpToBoundary(timestamp: Date): Date {
  const ms = timestamp.getTime();
  return new Date(Math.ceil(ms / CHUNK_SIZE_MS) * CHUNK_SIZE_MS);
}

// ============================================================================
// Cache Manager
// ============================================================================

class LogCacheManager {
  private cache: Map<string, LogChunk> = new Map();
  private totalSizeBytes = 0;

  /**
   * Estimate chunk size in bytes (JSON stringified * 2 for overhead)
   */
  private estimateChunkSize(chunk: Omit<LogChunk, "sizeBytes" | "cachedAt" | "lastAccessedAt">): number {
    const jsonSize = JSON.stringify({
      logs: chunk.logs,
      cacheKey: chunk.cacheKey,
      containerId: chunk.containerId,
      containerName: chunk.containerName,
      startTimestamp: chunk.startTimestamp,
      endTimestamp: chunk.endTimestamp,
    }).length;

    return jsonSize * 2;
  }

  /**
   * Ensure space for a new chunk by evicting old entries
   */
  private ensureSpaceForChunk(newChunkSize: number): void {
    if (this.totalSizeBytes + newChunkSize <= MAX_CACHE_SIZE_BYTES) {
      return;
    }

    // Get all chunks sorted by last accessed time (oldest first - LRU)
    const chunks = Array.from(this.cache.values()).sort(
      (a, b) => a.lastAccessedAt - b.lastAccessedAt
    );

    const now = Date.now();

    // First, remove expired chunks
    for (const chunk of chunks) {
      if (now - chunk.cachedAt > CACHE_EXPIRY_HOURS * 60 * 60 * 1000) {
        this.cache.delete(chunk.cacheKey);
        this.totalSizeBytes -= chunk.sizeBytes;
      }
    }

    // If still need space, do LRU eviction
    let spaceNeeded =
      this.totalSizeBytes + newChunkSize - MAX_CACHE_SIZE_BYTES;

    const remainingChunks = Array.from(this.cache.values()).sort(
      (a, b) => a.lastAccessedAt - b.lastAccessedAt
    );

    for (const chunk of remainingChunks) {
      if (spaceNeeded <= 0) break;

      this.cache.delete(chunk.cacheKey);
      this.totalSizeBytes -= chunk.sizeBytes;
      spaceNeeded -= chunk.sizeBytes;
    }
  }

  /**
   * Generate a cache key for a chunk
   */
  generateCacheKey(
    containerId: string,
    containerName: string,
    startTimestamp: string,
    endTimestamp: string
  ): string {
    return `${containerId}_${containerName}_${startTimestamp}_${endTimestamp}`;
  }

  /**
   * Create aligned time range for cache operations
   */
  createAlignedTimeRange(startTime: Date, endTime: Date): CacheTimeRange {
    const roundedStart = roundToBoundary(startTime);
    const roundedEnd = roundUpToBoundary(endTime);

    return {
      start: startTime,
      end: endTime,
      rounded: {
        start: roundedStart,
        end: roundedEnd,
      },
    };
  }

  /**
   * Cache a chunk of logs
   */
  async cacheChunk(
    chunk: Omit<LogChunk, "cachedAt" | "sizeBytes" | "lastAccessedAt">
  ): Promise<void> {
    const now = Date.now();
    const sizeBytes = this.estimateChunkSize(chunk);

    const fullChunk: LogChunk = {
      ...chunk,
      cachedAt: now,
      lastAccessedAt: now,
      sizeBytes,
    };

    // Ensure space before adding
    this.ensureSpaceForChunk(sizeBytes);

    // Add to cache
    this.cache.set(fullChunk.cacheKey, fullChunk);
    this.totalSizeBytes += sizeBytes;
  }

  /**
   * Get a chunk from cache
   */
  async getChunk(cacheKey: string): Promise<LogChunk | null> {
    const chunk = this.cache.get(cacheKey);
    if (chunk) {
      chunk.lastAccessedAt = Date.now();
      return chunk;
    }
    return null;
  }

  /**
   * Get chunks for a specific time range
   */
  async getChunksForTimeRange(
    containerName: string,
    startTime: Date,
    endTime: Date
  ): Promise<LogChunk[]> {
    const chunks: LogChunk[] = [];

    for (const chunk of this.cache.values()) {
      if (chunk.containerName !== containerName) continue;

      const chunkStart = new Date(chunk.startTimestamp);
      const chunkEnd = new Date(chunk.endTimestamp);

      // Check if chunk overlaps with requested time range
      if (chunkStart < endTime && chunkEnd > startTime) {
        chunks.push(chunk);
      }
    }

    return chunks;
  }

  /**
   * Get cached logs with boundary alignment
   */
  async getCachedLogsWithBoundaryAlignment(
    containerName: string,
    startTime: Date,
    endTime: Date
  ): Promise<CacheHitResult> {
    const timeRange = this.createAlignedTimeRange(startTime, endTime);
    const { start: alignedStart, end: alignedEnd } = timeRange.rounded;

    // Generate expected chunk boundaries
    const expectedChunks: Array<{ start: Date; end: Date }> = [];
    let currentStart = new Date(alignedStart);

    while (currentStart < alignedEnd) {
      const chunkEnd = new Date(currentStart.getTime() + CHUNK_SIZE_MS);
      expectedChunks.push({
        start: new Date(currentStart),
        end: chunkEnd > alignedEnd ? new Date(alignedEnd) : chunkEnd,
      });
      currentStart = chunkEnd;
    }

    // Check which chunks exist in cache
    const cachedChunks = await this.getChunksForTimeRange(
      containerName,
      alignedStart,
      alignedEnd
    );
    const cachedLogs: Log[] = [];
    const missingTimeRanges: Array<{ start: Date; end: Date }> = [];

    let coveredChunks = 0;

    for (const expectedChunk of expectedChunks) {
      const matchingChunk = cachedChunks.find((cached) => {
        const cachedStart = new Date(cached.startTimestamp);
        const cachedEnd = new Date(cached.endTimestamp);
        return (
          cachedStart <= expectedChunk.start && cachedEnd >= expectedChunk.end
        );
      });

      if (matchingChunk) {
        // Filter logs to only include those within the expected chunk range
        const chunkLogs = matchingChunk.logs.filter((log) => {
          const logTime = new Date(log.timeStamp);
          return logTime >= expectedChunk.start && logTime < expectedChunk.end;
        });
        cachedLogs.push(...chunkLogs);
        coveredChunks++;
      } else {
        missingTimeRanges.push(expectedChunk);
      }
    }

    // Calculate coverage percentage
    const coveragePercentage =
      expectedChunks.length > 0
        ? (coveredChunks / expectedChunks.length) * 100
        : 0;

    // Sort cached logs by timestamp (oldest first for proper log display)
    cachedLogs.sort(
      (a, b) =>
        new Date(a.timeStamp).getTime() - new Date(b.timeStamp).getTime()
    );

    return {
      hasPartialCoverage: coveragePercentage >= 80, // 80% threshold
      coveragePercentage,
      cachedLogs,
      missingTimeRanges,
    };
  }

  /**
   * Get cache statistics
   */
  getCacheStats(): CacheStats {
    const containers = new Set<string>();
    for (const chunk of this.cache.values()) {
      containers.add(chunk.containerName);
    }

    return {
      sizeMB: this.totalSizeBytes / (1024 * 1024),
      entryCount: this.cache.size,
      containers,
    };
  }

  /**
   * Clear all cached data
   */
  clearCache(): void {
    this.cache.clear();
    this.totalSizeBytes = 0;
  }
}

// Export singleton instance
export const logCacheManager = new LogCacheManager();
