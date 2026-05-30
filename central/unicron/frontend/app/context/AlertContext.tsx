/**
 * AlertContext - Global state management for firing alerts.
 *
 * Uses an external mutable store (AlertStore) with useSyncExternalStore for
 * granular subscriptions. Components subscribe to specific data slices and
 * only re-render when their slice changes.
 *
 * WebSocket events (alert:fired, alert:stacked, alert:state_changed) update
 * the store in real-time via GlobalWebSocketService.
 *
 * Phase 59-01: Refactored from useReducer to external store pattern.
 * Phase 59-02: Added REST hydration, WebSocket reconnect re-sync, tab refocus re-sync.
 */

import React, { createContext, useContext, useEffect, useCallback, useRef } from "react";
import { globalWebSocket } from "~/features/alert-engine/services/websocket";
import { acknowledgeAlert as apiAcknowledgeAlert } from "~/utils/api/alert-engine";
import { normalizeAlertCount } from "~/utils/alertStack";
import { httpApp } from "~/utils/http.client";
import { clientLog } from "~/utils/logging/logger.client";

// ============================================================================
// Types
// ============================================================================

/**
 * A single firing alert in the store.
 * Fields match the alert:fired WebSocket payload from alert_websocket.py.
 */
export interface FiringAlert {
  alert_id: string;
  rule_id: string;
  rule_name: string;
  rule_type: string;
  container_name: string;
  host_id: string;
  /** Composite key: `${host_id}:${container_name}` -- per locked decision "keyed by host+container" */
  containerKey: string;
  severity: "critical" | "warning" | "info";
  message: string;
  trigger_value: string;
  threshold: string;
  status: "firing";
  started_at: string;
  updated_at: string;
  count: number;
  last_seen: string;
  organization_id: string;
}

/**
 * Snapshot of the store state. Returned by getSnapshot() and consumed
 * by useSyncExternalStore. Immutable reference -- only recomputed when
 * the store version changes.
 */
export interface AlertStoreSnapshot {
  alerts: Map<string, FiringAlert>;
  byContainer: Map<string, Set<string>>;
  totalAlerts: number;
  alertsBySeverity: { critical: number; warning: number; info: number };
  alertsPerContainer: Map<string, number>;
  isConnected: boolean;
  isStale: boolean;
  version: number;
}

// ============================================================================
// AlertStore Class
// ============================================================================

/**
 * External mutable store for firing alerts.
 *
 * Holds a Map of firing alerts keyed by alert_id with a derived container
 * grouping index using composite key (host_id:container_name).
 *
 * Uses subscriber notification pattern compatible with useSyncExternalStore.
 */
class AlertStore {
  // Primary storage: alert_id -> FiringAlert
  private alerts = new Map<string, FiringAlert>();

  // Derived index: composite containerKey -> Set of alert_ids
  private byContainer = new Map<string, Set<string>>();

  // Version counter: incremented on every mutation for snapshot identity
  private version = 0;

  // Connection status
  private isConnected = false;
  private isStale = false;

  // Subscriber management for useSyncExternalStore
  private listeners = new Set<() => void>();

  // Cached snapshot: only recomputed when version changes
  private cachedSnapshot: AlertStoreSnapshot | null = null;
  private snapshotVersion = -1;

  // Debounced batch updates for alert storms
  private pendingEvents: Array<() => void> = [];
  private flushTimeout: ReturnType<typeof setTimeout> | null = null;
  private lastEventTime = 0;

  // --------------------------------------------------------------------------
  // Subscriber management (useSyncExternalStore interface)
  // --------------------------------------------------------------------------

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): AlertStoreSnapshot => {
    if (this.snapshotVersion !== this.version || !this.cachedSnapshot) {
      this.cachedSnapshot = this.computeSnapshot();
      this.snapshotVersion = this.version;
    }
    return this.cachedSnapshot;
  };

  // --------------------------------------------------------------------------
  // Mutation methods
  // --------------------------------------------------------------------------

  /**
   * Add a firing alert to the store.
   * Computes containerKey from host_id and container_name.
   * If alert_id already exists, treats as stack increment (updates count/last_seen).
   */
  addAlert(alert: FiringAlert): void {
    alert.containerKey = `${alert.host_id}:${alert.container_name}`;

    const existing = this.alerts.get(alert.alert_id);
    if (existing) {
      // Treat as stack increment if alert already exists
      existing.count = alert.count > existing.count ? alert.count : existing.count + 1;
      existing.last_seen = alert.updated_at;
      existing.updated_at = alert.updated_at;
    } else {
      this.alerts.set(alert.alert_id, alert);

      // Update byContainer index
      let containerAlerts = this.byContainer.get(alert.containerKey);
      if (!containerAlerts) {
        containerAlerts = new Set();
        this.byContainer.set(alert.containerKey, containerAlerts);
      }
      containerAlerts.add(alert.alert_id);
    }

    this.invalidate();
  }

  /**
   * Remove an alert from the store.
   * Used for acknowledge/resolve -- looks up containerKey to clean index.
   */
  removeAlert(alertId: string): boolean {
    const alert = this.alerts.get(alertId);
    if (!alert) return false; // Gracefully ignore ack for unknown alert (out-of-order)

    // Remove from primary map
    this.alerts.delete(alertId);

    // Remove from byContainer index
    const containerAlerts = this.byContainer.get(alert.containerKey);
    if (containerAlerts) {
      containerAlerts.delete(alertId);
      if (containerAlerts.size === 0) {
        this.byContainer.delete(alert.containerKey);
      }
    }

    this.invalidate();
    return true;
  }

  /**
   * Update stack count and last_seen on existing alert.
   * No-op if alert not found (out-of-order message handling).
   */
  updateStack(alertId: string, count: number, lastSeen: string): boolean {
    const alert = this.alerts.get(alertId);
    if (!alert) return false;

    alert.count = count;
    alert.last_seen = lastSeen;
    alert.updated_at = lastSeen;

    this.invalidate();
    return true;
  }

  /**
   * Bulk replace all alerts. Clears maps and rebuilds from array.
   * Used for initial hydration and re-sync after reconnect.
   */
  setAlerts(alerts: FiringAlert[]): void {
    this.alerts.clear();
    this.byContainer.clear();

    for (const alert of alerts) {
      alert.containerKey = `${alert.host_id}:${alert.container_name}`;
      this.alerts.set(alert.alert_id, alert);

      let containerAlerts = this.byContainer.get(alert.containerKey);
      if (!containerAlerts) {
        containerAlerts = new Set();
        this.byContainer.set(alert.containerKey, containerAlerts);
      }
      containerAlerts.add(alert.alert_id);
    }

    this.invalidate();
  }

  /**
   * Update connection status.
   * If transitioning from disconnected to connected, clears stale flag.
   */
  setConnected(connected: boolean): void {
    const wasDisconnected = !this.isConnected;
    this.isConnected = connected;
    if (wasDisconnected && connected) {
      this.isStale = false;
    }
    this.invalidate();
  }

  /**
   * Mark data as potentially stale (used during disconnect).
   */
  setStale(stale: boolean): void {
    this.isStale = stale;
    this.invalidate();
  }

  // --------------------------------------------------------------------------
  // Debounced batch updates for alert storms
  // --------------------------------------------------------------------------

  /**
   * Process an event with debounce batching.
   *
   * First event in a quiet period processes immediately (0ms latency).
   * Subsequent events within 150ms are batched and flushed together,
   * incrementing version once and notifying subscribers once.
   */
  processEvent(handler: () => void): void {
    const now = Date.now();
    const BATCH_WINDOW_MS = 150;

    if (this.pendingEvents.length === 0 && (now - this.lastEventTime) > BATCH_WINDOW_MS) {
      // Quiet period -- first event, execute immediately
      this.lastEventTime = now;
      handler();
      return;
    }

    // Storm mode -- buffer the event
    this.pendingEvents.push(handler);

    if (!this.flushTimeout) {
      this.flushTimeout = setTimeout(() => {
        this.flushPendingEvents();
      }, BATCH_WINDOW_MS);
    }
  }

  private flushPendingEvents(): void {
    const events = this.pendingEvents;
    this.pendingEvents = [];
    this.flushTimeout = null;
    this.lastEventTime = Date.now();

    if (events.length === 0) return;

    // Temporarily suppress notifications while processing batch
    const originalInvalidate = this.invalidate.bind(this);
    let mutationCount = 0;
    this.invalidate = () => { mutationCount++; };

    // Execute all buffered events
    for (const event of events) {
      event();
    }

    // Restore invalidate
    this.invalidate = originalInvalidate;

    // Single version increment and notification for the entire batch
    if (mutationCount > 0) {
      this.invalidate();
    }
  }

  // --------------------------------------------------------------------------
  // Internal helpers
  // --------------------------------------------------------------------------

  private invalidate(): void {
    this.version++;
    this.notifyListeners();
  }

  private notifyListeners(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }

  private computeSnapshot(): AlertStoreSnapshot {
    const alertsBySeverity = { critical: 0, warning: 0, info: 0 };
    const alertsPerContainer = new Map<string, number>();

    for (const alert of this.alerts.values()) {
      // Count by severity
      if (alert.severity in alertsBySeverity) {
        alertsBySeverity[alert.severity]++;
      }

      // Count per container
      const current = alertsPerContainer.get(alert.containerKey) || 0;
      alertsPerContainer.set(alert.containerKey, current + 1);
    }

    return {
      alerts: this.alerts,
      byContainer: this.byContainer,
      totalAlerts: this.alerts.size,
      alertsBySeverity,
      alertsPerContainer,
      isConnected: this.isConnected,
      isStale: this.isStale,
      version: this.version,
    };
  }
}

// ============================================================================
// Singleton Store Instance
// ============================================================================

/** Module-level singleton. Used by AlertProvider and consumer hooks. */
export const alertStore = new AlertStore();

// ============================================================================
// Hydration
// ============================================================================

/**
 * Reverse severity map: Central REST API returns 4-level (critical, high, medium, low).
 * AlertStore uses 3-level (critical, warning, info) matching alert-engine's native format.
 */
const REVERSE_SEVERITY: Record<string, "critical" | "warning" | "info"> = {
  critical: "critical",
  high: "critical",
  medium: "warning",
  low: "info",
};

/**
 * Fetch all firing alerts from Central's REST API and bulk-replace the store.
 *
 * Used for:
 * - Initial hydration on app load
 * - Re-sync after WebSocket reconnect (catches missed events)
 * - Re-sync on tab refocus (catches events missed while tab was inactive)
 * - Recovery after optimistic acknowledge failure
 *
 * Exported so external callers (e.g., ack failure recovery) can invoke directly.
 */
export async function hydrateAlerts(): Promise<void> {
  try {
    const response = await httpApp.get("/alerts", {
      params: { status_filter: "firing", limit: 500 },
    });

    const items: any[] = response.data?.items ?? [];

    const mapped: FiringAlert[] = items.map((item) => ({
      alert_id: item.id,
      rule_id: item.rule_id,
      rule_name: item.rule_name || "",
      rule_type: item.rule_type || "",
      container_name: item.container_name || "",
      host_id: item.host_id || "",
      containerKey: `${item.host_id || ""}:${item.container_name || ""}`,
      severity: REVERSE_SEVERITY[item.severity] ?? "info",
      message: item.message || "",
      trigger_value: item.trigger_value || "",
      threshold: item.threshold || "",
      status: "firing" as const,
      started_at: item.started_at,
      updated_at: item.updated_at,
      count: normalizeAlertCount(item.count),
      last_seen: item.last_seen || item.updated_at,
      organization_id: "",
    }));

    alertStore.setAlerts(mapped);
    clientLog.debug({ count: mapped.length }, "Alert store hydrated from REST API");
  } catch (error) {
    // On failure, log but don't crash. Store stays empty (pills show 0).
    clientLog.error({ err: error }, "Failed to hydrate alerts from REST API");
  }
}

// ============================================================================
// React Context
// ============================================================================

interface AlertContextValue {
  store: AlertStore;
  acknowledgeAlert: (alertId: string) => Promise<void>;
}

const AlertsContext = createContext<AlertContextValue | null>(null);

// ============================================================================
// Provider
// ============================================================================

interface AlertProviderProps {
  children: React.ReactNode;
}

/**
 * AlertProvider -- provides the AlertStore singleton and acknowledgeAlert
 * function via React Context. Wires WebSocket event handlers for real-time
 * alert updates.
 *
 * The store is external (not React state), so this component does not
 * re-render on store changes. Consumer hooks use useSyncExternalStore
 * to subscribe to specific slices.
 */
export function AlertProvider({ children }: AlertProviderProps) {
  /**
   * Optimistic acknowledge: immediately removes alert from store,
   * then calls API. If API fails, re-fetches all alerts to restore
   * correct state (full re-sync is safer than re-adding a single alert).
   */
  const acknowledgeAlert = useCallback(async (alertId: string) => {
    // Optimistic removal
    alertStore.removeAlert(alertId);

    try {
      await apiAcknowledgeAlert(alertId);
      clientLog.debug({ alertId }, "Alert acknowledged successfully");
    } catch (error) {
      clientLog.error({ err: error, alertId }, "Failed to acknowledge alert, re-syncing");
      // Re-sync: restore correct state by fetching all firing alerts
      hydrateAlerts();
    }
  }, []);

  // Track previous connection state for detecting reconnect (false -> true transition)
  const wasConnectedRef = useRef(false);

  // --- 1. Initial hydration on mount ---
  // Fire-and-forget: no loading state, no skeleton. Pills appear when data arrives.
  useEffect(() => {
    if (typeof window === "undefined") return;
    hydrateAlerts();
  }, []);

  // --- 2. Wire WebSocket event handlers + reconnect re-sync ---
  useEffect(() => {
    // Guard against SSR
    if (typeof window === "undefined") return;

    // --- alert:fired handler ---
    const unsubFired = globalWebSocket.on("alert:fired", (message: { data: any }) => {
      const data = message.data;
      if (!data) return;

      const alert: FiringAlert = {
        alert_id: data.alert_id,
        rule_id: data.rule_id,
        rule_name: data.rule_name || "",
        rule_type: data.rule_type || "",
        container_name: data.container_name || "",
        host_id: data.host_id || "",
        containerKey: `${data.host_id || ""}:${data.container_name || ""}`,
        severity: data.severity || "info",
        message: data.message || "",
        trigger_value: data.trigger_value || "",
        threshold: data.threshold || "",
        status: "firing",
        started_at: data.started_at || new Date().toISOString(),
        updated_at: data.updated_at || new Date().toISOString(),
        count: 1,
        last_seen: data.updated_at || new Date().toISOString(),
        organization_id: data.organization_id || "",
      };

      alertStore.processEvent(() => alertStore.addAlert(alert));
      clientLog.debug({ alertId: alert.alert_id, rule: alert.rule_name }, "alert:fired received");
    });

    // --- alert:stacked handler ---
    const unsubStacked = globalWebSocket.on("alert:stacked", (message: { data: any }) => {
      const data = message.data;
      if (!data || !data.alert_id) return;

      const hasAlert = alertStore.getSnapshot().alerts.has(data.alert_id);
      alertStore.processEvent(() =>
        alertStore.updateStack(data.alert_id, data.count, data.last_seen)
      );
      if (!hasAlert) {
        // Recover from missed/out-of-order fired events by rehydrating canonical firing state.
        hydrateAlerts();
      }
      clientLog.debug({ alertId: data.alert_id, count: data.count }, "alert:stacked received");
    });

    // --- alert:state_changed handler ---
    const unsubStateChanged = globalWebSocket.on("alert:state_changed", (message: { data: any }) => {
      const data = message.data;
      if (!data || !data.alert_id) return;

      // Remove alert from store on acknowledge or resolve (optimistic or server-side)
      if (
        data.status === "acknowledged" ||
        data.action === "acknowledged" ||
        data.action === "auto_acknowledged" ||
        data.status === "resolved" ||
        data.action === "resolved"
      ) {
        const hasAlert = alertStore.getSnapshot().alerts.has(data.alert_id);
        alertStore.processEvent(() => alertStore.removeAlert(data.alert_id));
        if (!hasAlert) {
          // If we missed prior events, sync from server to avoid stale/empty store drift.
          hydrateAlerts();
        }
        clientLog.debug({ alertId: data.alert_id, action: data.action, status: data.status }, "alert:state_changed - removed");
      }
      // Ignore other state changes
    });

    // --- Connection change handler with reconnect re-sync ---
    const unsubConnection = globalWebSocket.onConnectionChange((connected: boolean) => {
      if (!connected) {
        alertStore.setConnected(false);
        alertStore.setStale(true);
        wasConnectedRef.current = false;
      } else {
        alertStore.setConnected(true);

        // Reconnect detected: was disconnected (false) -> now connected (true)
        // Re-hydrate to catch any events missed during the disconnection window
        if (!wasConnectedRef.current) {
          hydrateAlerts();
          clientLog.debug("WebSocket reconnected, re-hydrating alerts");
        }
        wasConnectedRef.current = true;
      }
    });

    // Cleanup
    return () => {
      unsubFired();
      unsubStacked();
      unsubStateChanged();
      unsubConnection();
    };
  }, []);

  // --- 3. Tab refocus re-sync ---
  // When the user switches back to this tab, re-fetch all alerts to catch
  // anything missed while the tab was inactive (browsers may throttle WS).
  useEffect(() => {
    if (typeof document === "undefined") return;

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        hydrateAlerts();
        clientLog.debug("Tab refocused, re-hydrating alerts");
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  const contextValue: AlertContextValue = {
    store: alertStore,
    acknowledgeAlert,
  };

  return (
    <AlertsContext.Provider value={contextValue}>
      {children}
    </AlertsContext.Provider>
  );
}

// ============================================================================
// Hooks
// ============================================================================

/**
 * Access the AlertStore from context. Throws if used outside AlertProvider.
 */
export function useAlertStore(): AlertContextValue {
  const context = useContext(AlertsContext);
  if (!context) {
    throw new Error("useAlertStore must be used within an AlertProvider");
  }
  return context;
}

// ============================================================================
// Backward-compatible exports
// ============================================================================

// Re-export types that existing consumers import from this file
export type { AlertHistoryEntry, AlertSeverity, AlertStatus } from "~/utils/api/alert-engine";
