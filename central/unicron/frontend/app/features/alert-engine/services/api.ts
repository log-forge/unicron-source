import type { AlertRule, Alert, AlertsMeta, AlertsPayload, AlertHistoryItem, ContainerInfo, GroupInfo, HealthStatus, TemplatesByCategory, AvailableMetrics, TemplateActivation } from '../types';
import type { GatekeeperSettings, GatekeeperSettingsUpdate, KeywordSettings, KeywordSettingsUpdate } from '../types';
import { clientEnv } from '~/utils/env.client';

export interface NotificationTargetChannel {
  id: string;
  label?: string;
  type?: string;
  enabled: boolean;
}

export interface NotificationTargetGroup {
  id: string;
  name: string;
  enabled: boolean;
  targets?: {
    channel_ids?: string[];
    preset_ids?: string[];
  };
}

export interface NotificationTargetPreset {
  id: string;
  label?: string;
  type?: string;
  enabled: boolean;
}

export interface NotificationTargets {
  channels: NotificationTargetChannel[];
  groups: NotificationTargetGroup[];
  presets: NotificationTargetPreset[];
}

export interface DeliveryStatus {
  channel_name: string;
  channel_type: string;
  status: 'pending' | 'sent' | 'failed' | 'retrying';
  sent_at?: string;
  attempt_count: number;
}

export interface DryRunResult {
  rule_id: string;
  triggered: boolean;
  value?: string | null;
  message: string;
  context: Record<string, any>;
  evaluated_at: string;
  logs_checked: number;
  sample_matches: Record<string, any>[];
}

export interface TestNotificationResponse {
  status: string;
  alert_id: string;
  message: string;
}

const API_BASE = clientEnv?.VITE_ALERT_ENGINE_API_BASE || '/unicron/api/alert-engine';

/**
 * Transform action_config from frontend format to backend-compatible format.
 * Backend schemas have extra='forbid' and will reject unknown fields.
 */
function transformActionConfig(frontendType: string, backendType: string, config: any): any {
  // NOTIFY action: Frontend and backend both use direct channel/group/preset IDs.
  if (backendType === 'notify') {
    const channelIds: string[] = config.channel_ids || [];
    const groupIds: string[] = config.group_ids || [];
    const presetIds: string[] = config.preset_ids || [];

    return {
      channel_ids: channelIds,
      group_ids: groupIds,
      preset_ids: presetIds,
      ...(config.message_template && { message_template: config.message_template }),
    };
  }

  // CONTAINER actions (restart, stop, start, kill): Frontend {} -> Backend {timeout_seconds, force}
  if (backendType === 'restart' || backendType === 'stop' || backendType === 'start' || backendType === 'kill') {
    return {
      timeout_seconds: config.timeout_seconds ?? 30,
      force: config.force ?? false,
    };
  }

  // RUN_SCRIPT action: Frontend {script?} -> Backend {script, interpreter, timeout_seconds}
  if (backendType === 'run_script') {
    return {
      script: config.script || '# Auto-generated',
      interpreter: config.interpreter || '/bin/sh',
      timeout_seconds: config.timeout_seconds ?? 60,
    };
  }

  // Unknown action type - return empty config
  return {};
}

/**
 * Transform LogForge frontend format to Unicron backend format.
 * Frontend uses: trigger_type (keyword/metric_threshold/container_event), trigger_value, actions[].type
 * Backend uses: trigger_config, actions array, labels dict
 */
function transformRuleForBackend(frontendRule: any): any {
  const backend: any = {
    name: frontendRule.name,
    description: frontendRule.description || undefined,
    enabled: frontendRule.enabled ?? true,
    scope_type: (frontendRule.scope_type || 'global').toLowerCase(),
    scope_targets: Array.isArray(frontendRule.scope_targets) ? frontendRule.scope_targets : [],
    severity: (frontendRule.severity || 'warning').toLowerCase(),
    labels: {},
    annotations: {},
  };

  // Map trigger_type (ensure lowercase for enum match)
  const triggerTypeMap: Record<string, string> = {
    keyword: 'keyword',
    metric_threshold: 'threshold',
    container_event: 'container_event',
  };
  backend.trigger_type = triggerTypeMap[frontendRule.trigger_type] || frontendRule.trigger_type;

  // Map trigger_value -> trigger_config
  const triggerValue = frontendRule.trigger_value;
  const timelineMinutes = frontendRule.timeline_minutes || 5;
  const timelineCount = frontendRule.timeline_count || 3;

  if (frontendRule.trigger_type === 'keyword') {
    const normalizedPatterns = Array.from(
      new Set(
        (Array.isArray(triggerValue) ? triggerValue : [triggerValue])
          .map((value) => String(value || '').trim())
          .filter((value) => value.length > 0),
      ),
    ).slice(0, 20);
    const pattern = normalizedPatterns[0] || '';
    const keywordThreshold = Math.max(1, parseInt(String(frontendRule.timeline_count || 3), 10) || 3);
    const keywordWindowMinutes = Math.max(1, parseInt(String(frontendRule.timeline_minutes || 5), 10) || 5);
    backend.trigger_config = {
      pattern,
      patterns: normalizedPatterns,
      is_regex: false,
      case_sensitive: false,
      threshold: keywordThreshold,
      window_seconds: keywordWindowMinutes * 60,
    };
  } else if (frontendRule.trigger_type === 'metric_threshold') {
    const operatorMap: Record<string, string> = {
      '>': 'gt',
      '>=': 'gte',
      '<': 'lt',
      '<=': 'lte',
      '==': 'eq',
      '!=': 'ne'
    };
    backend.trigger_config = {
      metric: triggerValue?.metric_type || 'cpu_percent',
      operator: operatorMap[triggerValue?.operator || '>'] || 'gt',
      value: parseFloat(triggerValue?.threshold) || 0,
      duration_seconds: timelineMinutes * 60,
    };
  } else if (frontendRule.trigger_type === 'container_event') {
    backend.trigger_config = {
      trigger_value: String(triggerValue || ''),
      timeline_minutes: timelineMinutes,
      timeline_count: timelineCount,
    };
  }

  // Map actions array (ensure we send correct ActionCreate format)
  if (frontendRule.actions && Array.isArray(frontendRule.actions)) {
    backend.actions = frontendRule.actions.map((action: any, index: number) => {
      const actionTypeMap: Record<string, string> = {
        notification: 'notify',
        restart_container: 'restart',
        kill_container: 'kill',
        stop_container: 'stop',
        start_container: 'start',
        run_script: 'run_script',
      };
      const backendType = actionTypeMap[action.type] || action.type;
      return {
        action_type: backendType,
        action_config: transformActionConfig(action.type, backendType, action.config || {}),
        order_index: index,
        enabled: action.enabled !== undefined ? action.enabled : true,
      };
    });
  } else if (frontendRule.action_type) {
    // Legacy single action support
    const actionTypeMap: Record<string, string> = {
      notification: 'notify',
      restart_container: 'restart',
      kill_container: 'kill',
      stop_container: 'stop',
      start_container: 'start',
      run_script: 'run_script',
    };
    const backendType = actionTypeMap[frontendRule.action_type] || frontendRule.action_type;
    const frontendConfig = frontendRule.notification_endpoint
      ? { notification_endpoint: frontendRule.notification_endpoint }
      : {};
    backend.actions = [
      {
        action_type: backendType,
        action_config: transformActionConfig(frontendRule.action_type, backendType, frontendConfig),
        order_index: 0,
        enabled: true,
      },
    ];
  }

  // Map tags to labels
  if (frontendRule.tags && Array.isArray(frontendRule.tags) && frontendRule.tags.length > 0) {
    backend.labels.tags = frontendRule.tags.join(',');
  }

  // Preserve template_source if present
  if (frontendRule.template_source) {
    backend.labels.template_source = frontendRule.template_source;
  }

  return backend;
}

/**
 * Transform Unicron backend format to LogForge frontend format.
 * Reverse of transformRuleForBackend.
 */
function transformRuleFromBackend(backendRule: any): any {
  const frontend: any = {
    id: backendRule.id,
    name: backendRule.name,
    description: backendRule.description,
    enabled: backendRule.enabled,
    scope_type: backendRule.scope_type,
    scope_targets: backendRule.scope_targets || [],
    severity: backendRule.severity || 'warning',
  };

  // Reverse trigger_type mapping
  const triggerTypeReverseMap: Record<string, string> = {
    keyword: 'keyword',
    threshold: 'metric_threshold',
    container_event: 'container_event',
    rate: 'container_event',
  };
  frontend.trigger_type = triggerTypeReverseMap[backendRule.trigger_type] || backendRule.trigger_type;

  // Reverse trigger_config -> trigger_value
  const config = backendRule.trigger_config || {};

  if (backendRule.trigger_type === 'keyword') {
    const configPatterns = Array.isArray(config.patterns)
      ? config.patterns
          .map((value: unknown) => String(value || '').trim())
          .filter((value: string) => value.length > 0)
      : [];
    const normalizedPatterns = configPatterns.length > 0
      ? Array.from(new Set(configPatterns)).slice(0, 20)
      : (config.pattern ? [String(config.pattern).trim()] : []);
    frontend.trigger_value = normalizedPatterns.length > 1
      ? normalizedPatterns
      : (normalizedPatterns[0] || '');
    frontend.timeline_minutes = Math.round((config.window_seconds || 300) / 60);
    frontend.timeline_count = config.threshold || 1;
  } else if (backendRule.trigger_type === 'threshold') {
    const operatorReverseMap: Record<string, string> = {
      gt: '>',
      gte: '>=',
      lt: '<',
      lte: '<=',
      eq: '==',
      ne: '!='
    };
    // For edit mode, extract fields to top-level so RuleBuilder can populate form
    frontend.metric_type = config.metric || 'cpu_percent';
    frontend.threshold = config.value || 0;
    frontend.operator = operatorReverseMap[config.operator] || '>';
    frontend.timeline_minutes = Math.round((config.duration_seconds || 300) / 60);

    // Also set trigger_value for backward compatibility
    frontend.trigger_value = {
      metric_type: frontend.metric_type,
      threshold: frontend.threshold,
      operator: frontend.operator,
    };
  } else if (backendRule.trigger_type === 'container_event' || backendRule.trigger_type === 'rate') {
    frontend.trigger_value = config.trigger_value || config.pattern || '';
    frontend.timeline_minutes = config.timeline_minutes || Math.round((config.window_seconds || 300) / 60);
    frontend.timeline_count = config.timeline_count || config.threshold || 3;
  }

  // Reverse actions array
  if (backendRule.actions && Array.isArray(backendRule.actions)) {
    const actionTypeReverseMap: Record<string, string> = {
      notify: 'notification',
      restart: 'restart_container',
      kill: 'kill_container',
      stop: 'stop_container',
      start: 'start_container',
      run_script: 'run_script',
    };
    frontend.actions = backendRule.actions.map((action: any) => {
      const frontendType = actionTypeReverseMap[action.action_type] || action.action_type;
      let config = action.action_config || {};

      if (action.action_type === 'notify') {
        config = {
          channel_ids: Array.isArray(config.channel_ids) ? config.channel_ids : [],
          group_ids: Array.isArray(config.group_ids) ? config.group_ids : [],
          preset_ids: Array.isArray(config.preset_ids) ? config.preset_ids : [],
          ...(config.message_template && { message_template: config.message_template }),
        };
      }

      return {
        type: frontendType,
        config,
      };
    });

    if (backendRule.actions.length > 0) {
      frontend.action_type = frontend.actions[0].type;
      if (frontend.actions[0].config?.notification_endpoint) {
        frontend.notification_endpoint = frontend.actions[0].config.notification_endpoint;
      }
    }
  }

  // Extract tags from labels
  const labels = backendRule.labels || {};
  if (labels.tags) {
    frontend.tags = labels.tags.split(',').filter((t: string) => t.trim().length > 0);
  } else {
    frontend.tags = [];
  }

  // Extract template_source
  if (labels.template_source) {
    frontend.template_source = labels.template_source;
  }

  return frontend;
}

function normalizeAlertContext(rawContext: any, labels: Record<string, string> = {}): any {
  const context = rawContext && typeof rawContext === 'object' ? { ...rawContext } : {};

  const rawContainerKey = typeof context.container_key === 'string'
    ? context.container_key
    : typeof labels.container_key === 'string'
      ? labels.container_key
      : '';
  const rawDockerId = typeof context.docker_container_id === 'string'
    ? context.docker_container_id
    : typeof labels.docker_container_id === 'string'
      ? labels.docker_container_id
      : '';

  let hostId = typeof context.host_id === 'string' ? context.host_id : '';
  let containerName = typeof context.container_name === 'string' ? context.container_name : '';

  const compositeSource = rawContainerKey;
  if ((!hostId || !containerName) && compositeSource.includes(':')) {
    const [parsedHostId, ...rest] = compositeSource.split(':');
    const parsedContainerName = rest.join(':');
    hostId = hostId || parsedHostId;
    containerName = containerName || parsedContainerName;
  }

  if (!hostId && typeof labels.host_id === 'string') {
    hostId = labels.host_id;
  }

  if (!containerName) {
    containerName = rawContainerKey.includes(':')
      ? rawContainerKey.split(':').slice(1).join(':')
      : '';
  }

  context.host_id = hostId;
  context.container_name = containerName;
  context.container_key = rawContainerKey || (hostId && containerName ? `${hostId}:${containerName}` : '');
  context.docker_container_id = rawDockerId || undefined;
  context.container_identifier = hostId && containerName
    ? `${hostId}:${containerName}`
    : context.container_key || containerName || '';

  return context;
}

export class ApiService {
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...options?.headers as Record<string, string>,
    };

    const response = await fetch(`${API_BASE}${endpoint}`, {
      credentials: 'include',  // Send cookies for authentication
      headers,
      ...options,
    });

    if (!response.ok) {
      // Try to extract backend-provided error detail for clarity
      try {
        const ct = response.headers.get('content-type') || '';
        if (ct.includes('application/json')) {
          const body: any = await response.json();
          const detail = body?.detail || body?.error || body?.message;
          if (detail) {
            if (typeof detail === 'string') {
              throw new Error(detail);
            } else if (Array.isArray(detail)) {
              const messages = detail.map((d: any) => d.msg || String(d)).join('; ');
              throw new Error(messages);
            } else {
              throw new Error(JSON.stringify(detail));
            }
          }
        } else {
          const text = await response.text();
          if (text) throw new Error(text);
        }
      } catch (e: any) {
        // If parsing above threw with useful message, rethrow; otherwise fall through
        if (e instanceof Error && e.message) throw e;
      }
      throw new Error(`API Error: ${response.status} ${response.statusText}`);
    }

    // Handle 204 No Content (e.g., DELETE responses) - no body to parse
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  async getRules(): Promise<{ rules: AlertRule[], count: number, maxRules: number | null, hostCount?: number | null, rulesPerHost?: number | null }> {
    const data = await this.request<{
      items: any[];
      total: number;
      maxRules?: number | null;
      hostCount?: number | null;
      rulesPerHost?: number | null;
    }>('/rules');
    const rules = (data.items || []).map(transformRuleFromBackend);
    return {
      rules,
      count: data.total || 0,
      maxRules: data.maxRules ?? null,
      hostCount: data.hostCount,
      rulesPerHost: data.rulesPerHost,
    };
  }

  async createRule(rule: Omit<AlertRule, 'id'>): Promise<AlertRule> {
    const backendRule = transformRuleForBackend(rule);
    const createdRule = await this.request<any>('/rules', {
      method: 'POST',
      body: JSON.stringify(backendRule),
    });
    return transformRuleFromBackend(createdRule);
  }

  async updateRule(id: string, rule: Partial<AlertRule>): Promise<AlertRule> {
    const backendRule = transformRuleForBackend(rule as any);
    const updatedRule = await this.request<any>(`/rules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(backendRule),
    });
    return transformRuleFromBackend(updatedRule);
  }

  async toggleRuleEnabled(id: string, enabled: boolean): Promise<void> {
    await this.request(`/rules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    });
  }

  async bulkToggleRules(ruleIds: string[], enabled: boolean): Promise<{ updated: number; errors: any[] }> {
    const response = await this.request(`/rules/bulk-toggle`, {
      method: 'POST',
      body: JSON.stringify({ rule_ids: ruleIds, enabled }),
    });
    return response as { updated: number; errors: any[] };
  }

  async deleteRule(id: string): Promise<void> {
    await this.request(`/rules/${id}`, { method: 'DELETE' });
  }

  async getAlertsPayload(limit?: number): Promise<AlertsPayload> {
    const endpoint = limit != null ? `/alerts?limit=${encodeURIComponent(limit)}` : '/alerts';
    const data = await this.request<{
      items?: any[];
      total?: number;
    }>(endpoint);

    // Backend returns { items: AlertResponse[], total: number }
    // Transform AlertResponse to frontend Alert type
    const transformAlert = (backendAlert: any): Alert => {
      const labels = backendAlert.labels || {};
      const annotations = backendAlert.annotations || {};
      const context = normalizeAlertContext(
        backendAlert.last_trigger_context
          || annotations.evaluation_context
          || backendAlert.context
          || {},
        labels,
      );

      return {
        id: backendAlert.id,
        rule_id: backendAlert.rule_id,
        // Extract rule_name from labels (Prometheus convention) or fallback
        rule_name: labels.rule_name || labels.alertname || 'Unknown Rule',
        // Extract message from annotations (Prometheus convention) or fallback
        message: annotations.message || annotations.summary || 'Alert triggered',
        status: backendAlert.status,
        severity: backendAlert.severity,
        // Map started_at to timestamp for frontend compatibility
        timestamp: backendAlert.started_at || backendAlert.timestamp || new Date().toISOString(),
        context,
        // Default action_type for backward compatibility
        action_type: annotations.action_type || 'notification',
        // Preserve original fields for reference
        labels,
        annotations,
        started_at: backendAlert.started_at,
        ends_at: backendAlert.ends_at,
        updated_at: backendAlert.updated_at,
        count: Number.isFinite(Number(backendAlert.count))
          ? Math.max(1, Math.trunc(Number(backendAlert.count)))
          : 1,
        last_seen: backendAlert.last_seen || backendAlert.updated_at || backendAlert.started_at,
      };
    };

    const alerts = (data.items || []).map(transformAlert);
    const total = data.total || 0;

    // Calculate meta from response
    const actualLimit = limit ?? 100; // Default backend limit
    const hasMore = total > alerts.length;

    const meta: AlertsMeta = {
      limit: actualLimit,
      requestedLimit: limit ?? null,
      hasMore,
      totalAvailable: total,
      edition: 'source_available',
    };

    return {
      alerts,
      meta,
    };
  }

  async getAlerts(limit?: number): Promise<Alert[]> {
    const payload = await this.getAlertsPayload(limit);
    return payload.alerts;
  }


  async getContainers(): Promise<{ containers: ContainerInfo[], groups: GroupInfo[] }> {
    type ContainersPage = {
      containers?: ContainerInfo[];
      groups?: GroupInfo[];
      has_more_containers?: boolean;
      has_more_groups?: boolean;
    };

    const containerPageSize = 500;
    const groupPageSize = 200;

    const buildPageUrl = (
      containerOffset: number,
      groupOffset: number,
      includeContainers: boolean,
      includeGroups: boolean,
    ) => {
      const params = new URLSearchParams({
        container_offset: String(containerOffset),
        container_limit: String(containerPageSize),
        group_offset: String(groupOffset),
        group_limit: String(groupPageSize),
        include_containers: includeContainers ? 'true' : 'false',
        include_groups: includeGroups ? 'true' : 'false',
      });
      return `/containers?${params.toString()}`;
    };

    let containerOffset = 0;
    let groupOffset = 0;
    let includeContainers = true;
    let includeGroups = true;
    const allContainers: ContainerInfo[] = [];
    const allGroups: GroupInfo[] = [];
    const seenContainers = new Set<string>();
    const seenGroups = new Set<string>();

    while (includeContainers || includeGroups) {
      const data: ContainersPage = await this.request(
        buildPageUrl(containerOffset, groupOffset, includeContainers, includeGroups),
      );

      const pageContainers = Array.isArray(data.containers) ? data.containers : [];
      const pageGroups = Array.isArray(data.groups) ? data.groups : [];

      const hasPagingMetadata =
        data.has_more_containers !== undefined || data.has_more_groups !== undefined;
      if (!hasPagingMetadata && containerOffset === 0 && groupOffset === 0) {
        return {
          containers: pageContainers,
          groups: pageGroups,
        };
      }

      if (includeContainers) {
        for (const container of pageContainers) {
          const key = container.container_key || `${container.host_id || 'local'}:${container.name}`;
          if (seenContainers.has(key)) continue;
          seenContainers.add(key);
          allContainers.push(container);
        }
        containerOffset += pageContainers.length;
        includeContainers = Boolean(data.has_more_containers) && pageContainers.length > 0;
      }

      if (includeGroups) {
        for (const group of pageGroups) {
          const key = String(group.groupId);
          if (seenGroups.has(key)) continue;
          seenGroups.add(key);
          allGroups.push(group);
        }
        groupOffset += pageGroups.length;
        includeGroups = Boolean(data.has_more_groups) && pageGroups.length > 0;
      }
    }

    return { containers: allContainers, groups: allGroups };
  }

  async createGroup(name: string, containerIds: string[]): Promise<{ success: boolean; message: string; group?: any }> {
    return this.request<{ success: boolean; message: string; group?: any }>('/groups', {
      method: 'POST',
      body: JSON.stringify({ name, container_ids: containerIds }),
    });
  }

  async deleteGroup(groupId: string): Promise<void> {
    await this.request(`/groups/${groupId}`, { method: 'DELETE' });
  }

  async renameGroup(groupId: string, name: string): Promise<{ success: boolean; message: string; group?: any }> {
    return this.request<{ success: boolean; message: string; group?: any }>(`/groups/${groupId}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
  }

  async getHealth(): Promise<HealthStatus> {
    return this.request<HealthStatus>('/health');
  }

  async sendTestNotification(
    rulePreview?: string,
    channelIds?: string[],
    groupIds?: string[],
    presetIds?: string[],
    severity?: string,
  ): Promise<TestNotificationResponse> {
    return this.request<TestNotificationResponse>('/test-notification', {
      method: 'POST',
      body: JSON.stringify({
        rule_preview: rulePreview,
        severity,
        channel_ids: channelIds,
        group_ids: groupIds,
        preset_ids: presetIds,
      }),
    });
  }

  async testRuleConfig(frontendRule: any): Promise<DryRunResult> {
    const backend = transformRuleForBackend(frontendRule);
    const payload = {
      name: backend.name,
      trigger_type: backend.trigger_type,
      trigger_config: backend.trigger_config || {},
      scope_type: backend.scope_type || 'global',
      scope_targets: backend.scope_targets || [],
      severity: backend.severity || 'warning',
    };

    return this.request<DryRunResult>('/rules/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getRuleTemplates(): Promise<TemplatesByCategory> {
    const data = await this.request<{ templates: TemplatesByCategory }>('/rule-templates');
    return data.templates;
  }

  async getAvailableMetrics(): Promise<AvailableMetrics> {
    return this.request<AvailableMetrics>('/metrics/available');
  }

  async getNotificationTargets(): Promise<NotificationTargets> {
    return this.request<NotificationTargets>('/notification/targets');
  }

  async getGatekeeperSettings(): Promise<GatekeeperSettings> {
    return this.request<GatekeeperSettings>('/gatekeeper/settings');
  }

  async updateGatekeeperSettings(update: GatekeeperSettingsUpdate): Promise<GatekeeperSettings> {
    return this.request<GatekeeperSettings>('/gatekeeper/settings', {
      method: 'PUT',
      body: JSON.stringify(update),
    });
  }

  async getKeywordSettings(): Promise<KeywordSettings> {
    return this.request<KeywordSettings>('/keyword-settings');
  }

  async updateKeywordSettings(update: KeywordSettingsUpdate): Promise<KeywordSettings> {
    return this.request<KeywordSettings>('/keyword-settings', {
      method: 'PATCH',
      body: JSON.stringify(update),
    });
  }

  async activateTemplate(templateId: string, activation: TemplateActivation): Promise<{ status: string; message: string; rule_id: string }> {
    return this.request<{ status: string; message: string; rule_id: string }>(`/rule-templates/${templateId}/activate`, {
      method: 'POST',
      body: JSON.stringify(activation),
    });
  }

  async convertRuleToCustom(ruleId: string): Promise<{ status: string; message: string; rule: any }> {
    return this.request<{ status: string; message: string; rule: any }>(`/rules/${ruleId}/convert-to-custom`, {
      method: 'POST',
    });
  }

  async checkDuplicateRule(templateId: string, activation: TemplateActivation): Promise<{ is_duplicate: boolean; similar_rules: AlertRule[]; similar_rule?: AlertRule }> {
    return this.request<{ is_duplicate: boolean; similar_rules: AlertRule[]; similar_rule?: AlertRule }>(`/rule-templates/${templateId}/check-duplicate`, {
      method: 'POST',
      body: JSON.stringify(activation),
    });
  }

  async getCurrentUser(): Promise<{ authenticated: boolean; user: { id: string; email: string; role: string } | null }> {
    return this.request<{ authenticated: boolean; user: { id: string; email: string; role: string } | null }>('/auth/me');
  }

  async getUsage(): Promise<{
    edition: string;
    usage: { rules: number; alertHistory: number };
    limits: { maxRules: number | null; alertHistoryLimit: number | null };
    user: { id: string; email: string; role: string } | null;
  }> {
    return this.request<{
      edition: string;
      usage: { rules: number; alertHistory: number };
      limits: { maxRules: number | null; alertHistoryLimit: number | null };
      user: { id: string; email: string; role: string } | null;
    }>('/rules/usage');
  }

  async validateContainerScripts(containerNames: string[], scriptFilename?: string): Promise<{ results: Record<string, { valid: boolean; reason: string; resolved_script?: string }> }> {
    return this.request<{ results: Record<string, { valid: boolean; reason: string; resolved_script?: string }> }>('/containers/validate-scripts', {
      method: 'POST',
      body: JSON.stringify({
        container_names: containerNames,
        script_filename: scriptFilename
      }),
    });
  }

  async acknowledgeAlert(alertId: string, comment?: string): Promise<void> {
    await this.request(`/alerts/${alertId}/acknowledge`, {
      method: 'POST',
      body: JSON.stringify({ comment }),
    });
  }

  async getAlertDeliveryStatus(alertId: string): Promise<DeliveryStatus[]> {
    const data = await this.request<{ items: DeliveryStatus[] }>(`/alerts/${alertId}/delivery-status`);
    return data.items;
  }

  async getAlertHistory(params: {
    start_time?: string;
    end_time?: string;
    severity?: string;
    status?: string;
    rule_id?: string;
    container_key?: string;
    offset?: number;
    limit?: number;
  }): Promise<{ items: AlertHistoryItem[]; total: number; offset: number; limit: number }> {
    const searchParams = new URLSearchParams();
    const normalizedStatus = params.status === 'firing' ? 'triggered' : params.status;
    if (params.start_time) searchParams.set('start_time', params.start_time);
    if (params.end_time) searchParams.set('end_time', params.end_time);
    if (params.severity) searchParams.set('severity', params.severity);
    if (normalizedStatus) searchParams.set('status', normalizedStatus);
    if (params.rule_id) searchParams.set('rule_id', params.rule_id);
    if (params.container_key) searchParams.set('container_key', params.container_key);
    searchParams.set('offset', String(params.offset ?? 0));
    searchParams.set('limit', String(params.limit ?? 50));

    return this.request<{ items: AlertHistoryItem[]; total: number; offset: number; limit: number }>(
      `/alerts/history?${searchParams.toString()}`
    );
  }
}

export const apiService = new ApiService();
