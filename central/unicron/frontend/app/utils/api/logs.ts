/**
 * Logs API Utility
 *
 * API functions for fetching container logs from VictoriaLogs.
 */

import type { Log } from "~/utils/logCache";
import type { ILogRow } from "~/types/victoria/logs.types";
import { httpApp } from "~/utils/http.client";
import { convertVictoriaRowToLog } from "~/utils/logMessage";

// ============================================================================
// Types
// ============================================================================

interface LogsQueryPayload {
  container_key?: string;
  container_name?: string;
  expr?: string;
  where?: string;
  pipes?: string;
  start?: string;
  end?: string;
  limit?: number;
}

interface LogsQueryResponse {
  rows: ILogRow[];
  count: number;
  query: string;
}

const VICTORIA_LOGS_QUERY_PATH = "/telemetry/victoria/logs/query";

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Convert ILogRow from VictoriaLogs to Log format used by UI components.
 */
export function convertLogRowToLog(row: ILogRow): Log {
  return convertVictoriaRowToLog(row);
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Fetch historical logs for a container from VictoriaLogs.
 *
 * @param containerKey - Canonical container key
 * @param minutes - Number of minutes of logs to fetch
 * @returns Array of log entries
 */
export async function getContainerHistoricalLogs(
  containerKey: string,
  minutes: number
): Promise<Log[]> {
  try {
    // Calculate time range
    const endTime = new Date();
    const startTime = new Date(endTime.getTime() - minutes * 60 * 1000);

    const payload: LogsQueryPayload = {
      container_key: containerKey,
      start: startTime.toISOString(),
      end: endTime.toISOString(),
      limit: 10000, // Reasonable limit for historical queries
    };

    const response = await httpApp.post<LogsQueryResponse>(
      VICTORIA_LOGS_QUERY_PATH,
      payload
    );

    // Convert ILogRow[] to Log[]
    const logs = response.data.rows.map(convertLogRowToLog);

    // Sort by timestamp (oldest first for proper log display)
    logs.sort(
      (a, b) =>
        new Date(a.timeStamp).getTime() - new Date(b.timeStamp).getTime()
    );

    return logs;
  } catch (error) {
    console.error("Failed to fetch historical logs from VictoriaLogs:", error);
    return [];
  }
}

/**
 * Fetch historical logs with a server-side LogsQL filter.
 *
 * Used by vtail and vquery viewer modes to fetch history that matches
 * the user's LogsQL expression.
 *
 * @param containerKey - Canonical container key
 * @param minutes      - Number of minutes of logs to fetch
 * @param where        - LogsQL boolean filter (no pipes)
 * @param pipes        - LogsQL pipe operators (e.g. "| stats count()")
 */
export async function getContainerFilteredLogs(
  containerKey: string,
  minutes: number,
  where?: string,
  pipes?: string,
): Promise<Log[]> {
  try {
    const endTime = new Date();
    const startTime = new Date(endTime.getTime() - minutes * 60 * 1000);

    const payload: LogsQueryPayload = {
      container_key: containerKey,
      start: startTime.toISOString(),
      end: endTime.toISOString(),
      limit: 10000,
    };
    if (where) payload.where = where;
    if (pipes) payload.pipes = pipes;

    const response = await httpApp.post<LogsQueryResponse>(
      VICTORIA_LOGS_QUERY_PATH,
      payload
    );

    const logs = response.data.rows.map(convertLogRowToLog);
    logs.sort(
      (a, b) =>
        new Date(a.timeStamp).getTime() - new Date(b.timeStamp).getTime()
    );
    return logs;
  } catch (error) {
    console.error("Failed to fetch filtered logs from VictoriaLogs:", error);
    return [];
  }
}

/**
 * Fetch historical logs with raw ILogRow response (for advanced use cases).
 *
 * @param containerKey - Canonical container key
 * @param minutes - Number of minutes of logs to fetch
 * @returns Raw LogsQueryResponse from VictoriaLogs
 */
export async function getContainerHistoricalLogsRaw(
  containerKey: string,
  minutes: number
): Promise<LogsQueryResponse | null> {
  try {
    const endTime = new Date();
    const startTime = new Date(endTime.getTime() - minutes * 60 * 1000);

    const payload: LogsQueryPayload = {
      container_key: containerKey,
      start: startTime.toISOString(),
      end: endTime.toISOString(),
      limit: 10000,
    };

    const response = await httpApp.post<LogsQueryResponse>(
      VICTORIA_LOGS_QUERY_PATH,
      payload
    );

    return response.data;
  } catch (error) {
    console.error("Failed to fetch historical logs from VictoriaLogs:", error);
    return null;
  }
}
