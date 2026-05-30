export interface RuleAction {
  type: 'notification' | 'restart_container' | 'kill_container' | 'stop_container' | 'start_container';
  config: {
    notification_endpoint?: string;
    delay_seconds?: number;
    channel_ids?: string[];
    group_ids?: string[];
    preset_ids?: string[];
    destinations?: string[];
    destination_groups?: string[];
  };
  delay_seconds?: number;
}

export interface AlertRule {
  id: string;
  name: string;
  trigger_type: 'keyword' | 'metric_threshold' | 'container_event';
  trigger_value: string | string[] | MetricThresholdConfig;
  timeline_minutes?: number;
  timeline_count?: number;
  // Legacy fields for backward compatibility
  action_type: 'notification' | 'restart_container' | 'kill_container' | 'stop_container' | 'start_container';
  notification_endpoint?: string;
  // New multi-action support
  actions?: RuleAction[];
  // Rule scope
  scope_type?: 'global' | 'container' | 'group' | 'herald';
  scope_targets?: string[];
  severity?: 'critical' | 'warning' | 'info';
  enabled: boolean;
  template_source?: string;
  tags?: string[];
}

export interface MetricThresholdConfig {
  metric_type: string;
  threshold: number;
  operator: '>' | '<' | '==';
}
