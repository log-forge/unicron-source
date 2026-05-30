/**
 * Socket.IO event handlers for alert updates.
 *
 * DEPRECATED: alert event handling now rides on the shared Socket.IO browser
 * event layer and higher-level alert providers.
 *
 * This file is retained only for any code that still references the exported
 * types/functions, but the handlers are no longer actively registered.
 *
 * The active alert providers subscribe to `alert:*` events through the shared
 * browser socket service.
 */

import type { TypedSocket } from "../../context/SocketContext";
import { clientLog } from "../../utils/logging/logger.client";

// ============================================================================
// Socket Event Types (retained for any external consumers)
// ============================================================================

/**
 * Payload for alert:fired event when a new alert is triggered.
 */
export interface AlertFiredEvent {
  id: string;
  rule_id: string;
  rule_name: string;
  fingerprint: string;
  severity: "critical" | "warning" | "info";
  status: "firing";
  context: Record<string, unknown>;
  triggered_at: string;
  annotations?: Record<string, string>;
}

/**
 * Payload for alert:acknowledged event.
 */
export interface AlertAcknowledgedEvent {
  id: string;
  fingerprint: string;
  acknowledged_by?: string;
  acknowledged_at: string;
}

/**
 * Payload for alert:resolved event.
 */
export interface AlertResolvedEvent {
  id: string;
  fingerprint: string;
  resolved_at: string;
}

/**
 * Payload for alert:silenced event.
 */
export interface AlertSilencedEvent {
  id: string;
  fingerprint: string;
  silence_id: string;
  silenced_at: string;
}

// ============================================================================
// Event Names
// ============================================================================

export const ALERT_EVENTS = {
  FIRED: "alert:fired",
  ACKNOWLEDGED: "alert:acknowledged",
  RESOLVED: "alert:resolved",
  SILENCED: "alert:silenced",
} as const;

// ============================================================================
// Handler Registration (DEPRECATED - no-ops)
// ============================================================================

/**
 * @deprecated Alert handlers are now wired in AlertProvider via the shared
 * Socket.IO event layer.
 */
export function registerAlertHandlers(
  socket: TypedSocket,
  _dispatch: any
): void {
  clientLog.debug("registerAlertHandlers called but is deprecated. Alert events are handled by AlertProvider.");
}

/**
 * @deprecated Alert handlers are now wired in AlertProvider via the shared
 * Socket.IO event layer.
 */
export function unregisterAlertHandlers(socket: TypedSocket): void {
  // No-op
}

// ============================================================================
// Connection Handlers (DEPRECATED - no-ops)
// ============================================================================

/**
 * @deprecated Connection handling is now done in AlertProvider via the shared
 * Socket.IO event layer.
 */
export function registerAlertConnectionHandlers(
  socket: TypedSocket,
  _dispatch: any,
  _refetchAlerts: () => Promise<void>
): void {
  // No-op
}

/**
 * @deprecated Connection handling is now done in AlertProvider via the shared
 * Socket.IO event layer.
 */
export function unregisterAlertConnectionHandlers(socket: TypedSocket): void {
  // No-op
}
