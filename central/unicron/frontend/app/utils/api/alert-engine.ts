/**
 * API client for alert-engine service.
 *
 * Provides typed functions for interacting with the alert-engine backend.
 * Uses axios with credentials for session auth passthrough.
 */

import { httpApp } from "../http.client";
import { clientLog } from "../logging/logger.client";

// ============================================================================
// Types - matching backend schemas from Unicron/services/alert-engine
// ============================================================================

export type TriggerType = "threshold" | "keyword" | "rate" | "absence";
export type ScopeType = "global" | "container" | "group" | "herald";
export type Severity = "critical" | "warning" | "info";

export interface ThresholdConfig {
  metric: string;
  operator: "gt" | "gte" | "lt" | "lte" | "eq" | "ne";
  value: number;
  duration_seconds?: number;
}

export interface KeywordConfig {
  pattern: string;
  is_regex?: boolean;
  case_sensitive?: boolean;
}

export interface RateConfig {
  pattern?: string;
  threshold: number;
  window_seconds?: number;
}

export interface AbsenceConfig {
  pattern?: string;
  window_seconds: number;
}

export type TriggerConfig = ThresholdConfig | KeywordConfig | RateConfig | AbsenceConfig;

// ============================================================================
// Action Types - matching backend schemas from Unicron/services/alert-engine
// ============================================================================

/**
 * Types of remediation actions that can be attached to alert rules.
 */
export type ActionType = "restart" | "stop" | "start" | "kill" | "run_script" | "notify";

/**
 * Configuration for a remediation action attached to an alert rule.
 */
export interface ActionConfig {
  id?: string;
  action_type: ActionType;
  action_config: Record<string, unknown>;
  order_index: number;
  enabled: boolean;
}

/**
 * Configuration for container actions (restart, stop, start, kill).
 */
export interface ContainerActionConfig {
  timeout_seconds?: number;
  force?: boolean;
}

/**
 * Configuration for run_script action.
 */
export interface RunScriptConfig {
  script: string;
  interpreter?: string;
  timeout_seconds?: number;
  working_dir?: string;
  environment?: Record<string, string>;
}

/**
 * Configuration for notify action.
 */
export interface NotifyActionConfig {
  channel_ids: string[];
  message_template?: string;
}

/**
 * Gatekeeper settings for action safety limits.
 */
export interface GatekeeperSettings {
  cooldown_minutes: Record<string, number>;
  backoff_delays: number[];
  max_backoff_minutes: number;
  disable_after_failures: number;
  disable_duration_minutes: number;
  max_actions_per_rule_per_hour: number;
  max_actions_per_container_per_hour: number;
  verification_delay_seconds: number;
  trigger_suppression_enabled: boolean;
  trigger_suppression_minutes: number;
  trigger_suppression_actions: string[];
  trigger_suppression_rule_types: string[];
  dedup_enabled: boolean;
  dedup_window_seconds: number;
}

export interface RuleResponse {
  id: string;
  name: string;
  description: string | null;
  trigger_type: TriggerType;
  trigger_config: Record<string, unknown>;
  scope_type: ScopeType;
  scope_targets: string[];
  severity: Severity;
  labels: Record<string, string>;
  annotations: Record<string, string>;
  enabled: boolean;
  organization_id: string;
  created_by: string | null;
  updated_by: string | null;
  created_at: string;
  updated_at: string;
  actions?: ActionConfig[];
}

export interface RulesListResponse {
  items: RuleResponse[];
  total: number;
}

// ============================================================================
// Alert History Types
// ============================================================================

export type AlertSeverity = "critical" | "warning" | "info";
export type AlertStatus = "firing" | "acknowledged" | "resolved" | "silenced";

/**
 * A single alert history entry from the alert-engine service.
 */
export interface AlertHistoryEntry {
  id: string;
  rule_id: string;
  rule_name: string;
  fingerprint: string;
  severity: AlertSeverity;
  status: AlertStatus;
  context: Record<string, unknown>;
  triggered_at: string;
  resolved_at?: string;
  annotations?: Record<string, string>;
}

/**
 * Query parameters for fetching alert history.
 */
export interface HistoryQueryParams {
  /** Filter alerts triggered after this time (ISO datetime) */
  start_time?: string;
  /** Filter alerts triggered before this time (ISO datetime) */
  end_time?: string;
  /** Filter by severity level */
  severity?: AlertSeverity;
  /** Filter by alert status */
  status?: AlertStatus;
  /** Filter by rule ID */
  rule_id?: string;
  /** Filter by canonical container key */
  container_key?: string;
  /** Pagination limit (default 50) */
  limit?: number;
  /** Pagination offset */
  offset?: number;
}

/**
 * Response from the alert history endpoint.
 */
export interface HistoryResponse {
  items: AlertHistoryEntry[];
  total: number;
  has_more: boolean;
}

/**
 * Minimal rule info for filter dropdowns.
 */
export interface RuleInfo {
  id: string;
  name: string;
}

export interface GetRulesParams {
  enabled_only?: boolean;
  scope_type?: ScopeType;
  offset?: number;
  limit?: number;
}

// ============================================================================
// API Functions
// ============================================================================

const ALERT_ENGINE_API_PREFIX = "/alert-engine/rules";

/**
 * Get list of alert rules with optional filtering.
 */
export async function getRules(params?: GetRulesParams): Promise<RulesListResponse> {
  const queryParams = new URLSearchParams();

  if (params?.enabled_only) {
    queryParams.set("enabled_only", "true");
  }
  if (params?.scope_type) {
    queryParams.set("scope_type", params.scope_type);
  }
  if (params?.offset !== undefined) {
    queryParams.set("offset", String(params.offset));
  }
  if (params?.limit !== undefined) {
    queryParams.set("limit", String(params.limit));
  }

  const queryString = queryParams.toString();
  const url = queryString ? `${ALERT_ENGINE_API_PREFIX}?${queryString}` : ALERT_ENGINE_API_PREFIX;

  const response = await httpApp.get<RulesListResponse>(url);
  return response.data;
}

/**
 * Get a single alert rule by ID.
 */
export async function getRule(id: string): Promise<RuleResponse> {
  const response = await httpApp.get<RuleResponse>(`${ALERT_ENGINE_API_PREFIX}/${id}`);
  return response.data;
}

/**
 * Delete an alert rule by ID.
 */
export async function deleteRule(id: string): Promise<void> {
  await httpApp.delete(`${ALERT_ENGINE_API_PREFIX}/${id}`);
}

/**
 * Toggle alert rule enabled/disabled state.
 * Uses the POST /rules/{id}/enable or /rules/{id}/disable endpoints.
 */
export async function toggleRuleEnabled(id: string, enabled: boolean): Promise<RuleResponse> {
  const endpoint = enabled ? "enable" : "disable";
  const response = await httpApp.post<RuleResponse>(`${ALERT_ENGINE_API_PREFIX}/${id}/${endpoint}`);
  return response.data;
}

// ============================================================================
// Alert History API Functions
// ============================================================================

const ALERT_HISTORY_API_PREFIX = "/alert-engine/alerts/history";

/**
 * Converts HistoryQueryParams to URLSearchParams for the GET request.
 */
function buildHistoryQueryString(params?: HistoryQueryParams): string {
  if (!params) return "";

  const searchParams = new URLSearchParams();

  if (params.start_time) searchParams.set("start_time", params.start_time);
  if (params.end_time) searchParams.set("end_time", params.end_time);
  if (params.severity) searchParams.set("severity", params.severity);
  if (params.status) searchParams.set("status", params.status);
  if (params.rule_id) searchParams.set("rule_id", params.rule_id);
  if (params.container_key) searchParams.set("container_key", params.container_key);
  if (params.limit !== undefined) searchParams.set("limit", String(params.limit));
  if (params.offset !== undefined) searchParams.set("offset", String(params.offset));

  const qs = searchParams.toString();
  return qs ? `?${qs}` : "";
}

/**
 * Fetches alert history with optional filters.
 *
 * @param params - Optional query parameters for filtering and pagination
 * @returns Promise resolving to the history response
 */
export async function getAlertHistory(params?: HistoryQueryParams): Promise<HistoryResponse> {
  const queryString = buildHistoryQueryString(params);
  const url = `${ALERT_HISTORY_API_PREFIX}${queryString}`;

  const { status, data } = await httpApp.get(url);

  if (status !== 200) {
    throw new Error("Failed to fetch alert history");
  }

  clientLog.debug({ items: data?.items?.length ?? 0, total: data?.total }, "Fetched alert history");

  // Map response to our interface format
  const response: HistoryResponse = {
    items: data.items ?? [],
    total: data.total ?? 0,
    has_more: (data.offset ?? 0) + (data.limit ?? 0) < (data.total ?? 0),
  };

  return response;
}

/**
 * Fetches a single alert history entry by ID.
 *
 * @param historyId - The ID of the history entry to fetch
 * @returns Promise resolving to the alert history entry
 */
export async function getAlertHistoryEntry(historyId: string): Promise<AlertHistoryEntry> {
  const url = `${ALERT_HISTORY_API_PREFIX}/${historyId}`;

  const { status, data } = await httpApp.get(url);

  if (status !== 200) {
    throw new Error(`Failed to fetch alert history entry ${historyId}`);
  }

  clientLog.debug({ historyId }, "Fetched alert history entry");

  return data as AlertHistoryEntry;
}

/**
 * Fetches all alert rules as minimal info for filter dropdowns.
 *
 * @returns Promise resolving to list of rules with id and name
 */
export async function getAlertRulesForFilter(): Promise<RuleInfo[]> {
  const response = await getRules({ limit: 1000 });

  clientLog.debug({ count: response.items.length }, "Fetched alert rules for filter");

  // Map to RuleInfo format
  const rules: RuleInfo[] = response.items.map((rule) => ({
    id: rule.id,
    name: rule.name,
  }));

  return rules;
}

// ============================================================================
// Query Keys
// ============================================================================

export const ALERT_HISTORY_QUERY_KEY = ["alerting", "history"] as const;
export const ALERT_RULES_QUERY_KEY = ["alerting", "rules"] as const;

export const alertHistoryQueryKey = (params: HistoryQueryParams | null) =>
  [...ALERT_HISTORY_QUERY_KEY, params ? JSON.stringify(params) : null] as const;

export const alertRulesQueryKey = () => [...ALERT_RULES_QUERY_KEY] as const;

// ============================================================================
// Rule Create/Update Types
// ============================================================================

/**
 * Request payload for creating a new alert rule.
 */
export interface RuleCreateRequest {
  name: string;
  description?: string;
  enabled?: boolean;
  severity: Severity;
  trigger_type: TriggerType;
  trigger_config: ThresholdConfig | KeywordConfig | RateConfig | AbsenceConfig;
  scope_type: ScopeType;
  scope_targets?: string[];
  labels?: Record<string, string>;
  annotations?: Record<string, string>;
  actions?: ActionConfig[];
}

/**
 * Request payload for updating an existing alert rule.
 */
export type RuleUpdateRequest = Partial<RuleCreateRequest>;

/**
 * Response from dry-run rule testing endpoint.
 */
export interface DryRunResponse {
  would_trigger: boolean;
  sample_matches?: string[];
  logs_checked: number;
  evaluation_time_ms?: number;
}

// ============================================================================
// Rule CRUD Functions
// ============================================================================

/**
 * Create a new alert rule.
 */
export async function createRule(data: RuleCreateRequest): Promise<RuleResponse> {
  const response = await httpApp.post<RuleResponse>(ALERT_ENGINE_API_PREFIX, data);
  clientLog.debug({ ruleId: response.data.id }, "Created alert rule");
  return response.data;
}

/**
 * Update an existing alert rule.
 */
export async function updateRule(id: string, data: RuleUpdateRequest): Promise<RuleResponse> {
  const response = await httpApp.patch<RuleResponse>(`${ALERT_ENGINE_API_PREFIX}/${id}`, data);
  clientLog.debug({ ruleId: id }, "Updated alert rule");
  return response.data;
}

/**
 * Test a rule configuration without creating it (dry-run mode).
 */
export async function dryRunRule(data: RuleCreateRequest): Promise<DryRunResponse> {
  const response = await httpApp.post<DryRunResponse>(`${ALERT_ENGINE_API_PREFIX}/dry-run`, data);
  clientLog.debug({ wouldTrigger: response.data.would_trigger }, "Dry-run rule test completed");
  return response.data;
}

// ============================================================================
// Alert State Functions
// ============================================================================

/**
 * Acknowledge a firing alert.
 *
 * @param alertId - The ID of the alert to acknowledge
 * @param comment - Optional comment for the acknowledgement
 * @returns Promise resolving to the updated alert
 */
export async function acknowledgeAlert(
  alertId: string,
  comment?: string
): Promise<AlertHistoryEntry> {
  const body = comment ? { comment } : {};
  const response = await httpApp.post<AlertHistoryEntry>(
    `/alerts/${alertId}/ack`,
    body
  );
  clientLog.debug({ alertId }, "Acknowledged alert");
  return response.data;
}

/**
 * Get currently firing alerts.
 *
 * @returns Promise resolving to list of firing alerts
 */
export async function getFiringAlerts(): Promise<AlertHistoryEntry[]> {
  const response = await getAlertHistory({
    status: "firing",
    limit: 100,
    offset: 0,
  });
  return response.items;
}

// ============================================================================
// Gatekeeper API Functions
// ============================================================================

const GATEKEEPER_API_PREFIX = "/alert-engine/gatekeeper";

/**
 * Get current gatekeeper settings.
 */
export async function getGatekeeperSettings(): Promise<GatekeeperSettings> {
  const response = await httpApp.get<GatekeeperSettings>(`${GATEKEEPER_API_PREFIX}/settings`);
  clientLog.debug("Fetched gatekeeper settings");
  return response.data;
}

/**
 * Update gatekeeper settings.
 */
export async function updateGatekeeperSettings(
  settings: Partial<GatekeeperSettings>
): Promise<GatekeeperSettings> {
  const response = await httpApp.put<GatekeeperSettings>(
    `${GATEKEEPER_API_PREFIX}/settings`,
    settings
  );
  clientLog.debug("Updated gatekeeper settings");
  return response.data;
}

// ============================================================================
// Exports
// ============================================================================

export const alertEngineApi = {
  getRules,
  getRule,
  createRule,
  updateRule,
  deleteRule,
  toggleRuleEnabled,
  dryRunRule,
  getAlertHistory,
  getAlertHistoryEntry,
  getAlertRulesForFilter,
  acknowledgeAlert,
  getFiringAlerts,
  getGatekeeperSettings,
  updateGatekeeperSettings,
};
