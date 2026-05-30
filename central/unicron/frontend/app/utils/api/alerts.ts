/**
 * API utilities for container alerts.
 *
 * Provides typed functions for fetching and managing alerts
 * for specific containers.
 */

import { httpApp } from "../http.client";

// ============================================================================
// Types
// ============================================================================

export interface IAlert {
  id?: string;
  container: string;
  rule_id?: string;
  rule_name?: string;
  timestamp: string;
  message?: string;
  action_type?: string;
  severity?: string;
  metadata?: Record<string, unknown>;
  context?: Record<string, unknown>;
  /** Trigger value that fired the alert (from FiringAlert) */
  trigger_value?: string;
  /** Threshold configured on the rule (from FiringAlert) */
  threshold?: string;
  /** Stack count -- how many times this alert has fired (from FiringAlert) */
  count?: number;
  /** Host identifier (from FiringAlert) */
  host_id?: string;
}

interface ContainerAlertsResponse {
  alerts: IAlert[];
}

interface AcknowledgeResponse {
  remaining: number;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Get alerts for a specific container.
 *
 * @param containerName - The container name or identifier
 * @returns Promise resolving to list of alerts for the container
 */
export async function getContainerAlerts(containerName: string): Promise<IAlert[]> {
  const response = await httpApp.get<ContainerAlertsResponse>("/alert-engine/alerts", {
    params: { container: containerName },
  });
  return response.data.alerts ?? [];
}

/**
 * Acknowledge a single alert.
 *
 * @param alert - The alert to acknowledge
 * @returns Promise resolving to acknowledgement result with remaining count
 */
export async function acknowledgeAlert(alert: IAlert): Promise<AcknowledgeResponse> {
  const response = await httpApp.post<AcknowledgeResponse>("/alert-engine/alerts/acknowledge", {
    alert_id: alert.id,
    container: alert.container,
    rule_id: alert.rule_id,
    timestamp: alert.timestamp,
  });
  return response.data;
}

/**
 * Acknowledge all alerts for a container.
 *
 * @param containerName - The container name or identifier
 * @returns Promise resolving when all alerts are acknowledged
 */
export async function acknowledgeAllContainerAlerts(containerName: string): Promise<void> {
  await httpApp.post("/alert-engine/alerts/acknowledge-all", {
    container: containerName,
  });
}

// ============================================================================
// Query Keys
// ============================================================================

export const CONTAINER_ALERTS_QUERY_KEY = ["container-alerts"] as const;

export const containerAlertsQueryKey = (containerName: string) =>
  [...CONTAINER_ALERTS_QUERY_KEY, containerName] as const;
